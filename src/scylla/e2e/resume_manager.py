"""Resume manager for E2E experiment checkpoint handling.

Extracted from E2ERunner._initialize_or_resume_experiment() to separate
the 4 distinct resume concerns into focused, testable methods.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scylla.e2e.agent_runner import _has_valid_agent_result
from scylla.e2e.health import DEFAULT_HEARTBEAT_TIMEOUT_SECONDS, is_zombie, reset_zombie_checkpoint
from scylla.e2e.models import ExperimentConfig, RunState, TierID
from scylla.persistence.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint

# Run states past AGENT_COMPLETE where a valid agent_result is required.
# If the agent result is invalid at these states, the run must be reset.
_STATES_PAST_AGENT_COMPLETE = frozenset(
    {
        RunState.AGENT_COMPLETE.value,
        RunState.AGENT_CHANGES_COMMITTED.value,
        RunState.DIFF_CAPTURED.value,
        RunState.PROMOTED_TO_COMPLETED.value,
        RunState.JUDGE_PIPELINE_RUN.value,
        RunState.JUDGE_PROMPT_BUILT.value,
        RunState.JUDGE_COMPLETE.value,
        RunState.RUN_FINALIZED.value,
        RunState.REPORT_WRITTEN.value,
        RunState.CHECKPOINTED.value,
    }
)

if TYPE_CHECKING:
    from scylla.e2e.tier_manager import TierManager

logger = logging.getLogger(__name__)


class ResumeManager:
    """Manages experiment resume logic extracted from E2ERunner.

    Handles the 4 distinct concerns of _initialize_or_resume_experiment:
    1. Restoring ephemeral CLI args over the checkpoint-loaded config
    2. Resetting failed/interrupted states for re-execution
    3. Merging new CLI tiers and resetting incomplete tier/subtest states
    4. Determining which tiers need execution

    Receives checkpoint, config, and tier_manager as collaborators.
    Methods return updated (config, checkpoint) tuples so the caller can
    apply the results — no shared mutable state after construction.

    Example:
        >>> rm = ResumeManager(checkpoint, config, tier_manager)
        >>> config, checkpoint = rm.restore_cli_args(cli_ephemeral)
        >>> config, checkpoint = rm.reset_failed_states()
        >>> config, checkpoint = rm.merge_cli_tiers_and_reset_incomplete(
        ...     cli_tiers, checkpoint_path
        ... )

    """

    def __init__(
        self,
        checkpoint: E2ECheckpoint,
        config: ExperimentConfig,
        tier_manager: TierManager,
    ) -> None:
        """Initialize with experiment state objects.

        Args:
            checkpoint: Current experiment checkpoint.
            config: Current experiment configuration.
            tier_manager: Tier configuration manager.

        """
        self.checkpoint = checkpoint
        self.config = config
        self.tier_manager = tier_manager

    def handle_zombie(
        self,
        checkpoint_path: Path,
        experiment_dir: Path | None,
        heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    ) -> tuple[ExperimentConfig, E2ECheckpoint]:
        """Check for zombie experiment and reset checkpoint if detected.

        A zombie is a running experiment whose process has died without a clean
        shutdown. If detected, the checkpoint status is reset to 'interrupted'
        so the experiment can be safely resumed.

        Args:
            checkpoint_path: Path to checkpoint file for atomic save on reset.
            experiment_dir: Path to experiment directory used for zombie detection.
                If None, this method is a no-op (no checkpoint to inspect).
            heartbeat_timeout_seconds: Seconds after which a heartbeat is considered
                stale. Defaults to DEFAULT_HEARTBEAT_TIMEOUT_SECONDS (120).

        Returns:
            Updated (config, checkpoint) tuple.

        """
        if experiment_dir is None:
            return self.config, self.checkpoint

        if is_zombie(self.checkpoint, experiment_dir, heartbeat_timeout_seconds):
            logger.warning("Zombie experiment detected — resetting to 'interrupted'")
            reset_checkpoint = reset_zombie_checkpoint(self.checkpoint, checkpoint_path)
            return self.config, reset_checkpoint

        return self.config, self.checkpoint

    def restore_cli_args(
        self, cli_ephemeral: dict[str, Any]
    ) -> tuple[ExperimentConfig, E2ECheckpoint]:
        """Restore ephemeral CLI args over checkpoint-loaded config.

        max_subtests is always restored from the CLI value: None means "no limit"
        (clears any saved value), a positive int caps subtests.  All other ephemeral
        fields are only restored when the CLI explicitly provides a non-None value,
        so omitting a flag keeps the saved value from the checkpoint config.

        Args:
            cli_ephemeral: Dict of ephemeral CLI field names to values.
                Keys may include: until_run_state, until_tier_state,
                until_experiment_state, max_subtests.

        Returns:
            Updated (config, checkpoint) tuple.

        """
        # max_subtests is always restored when present in cli_ephemeral (None = clear saved limit).
        # When the key is absent entirely, the saved value is preserved.
        _sentinel = object()
        max_subtests_cli = cli_ephemeral.get("max_subtests", _sentinel)
        if max_subtests_cli is not _sentinel:
            self.config = self.config.model_copy(update={"max_subtests": max_subtests_cli})
        # All other ephemeral fields: only restore when explicitly set on CLI (non-None)
        non_none_rest = {
            k: v for k, v in cli_ephemeral.items() if k != "max_subtests" and v is not None
        }
        if non_none_rest:
            self.config = self.config.model_copy(update=non_none_rest)
        return self.config, self.checkpoint

    def _reset_infra_error_runs(self) -> int:
        """Reset failed/rate_limited run_states to pending for retry.

        Infrastructure errors (crashed runs, rate limits) are always retried on resume.
        Completed runs (worktree_cleaned) are never reset regardless of judge grade.

        Returns:
            Number of run_states reset.

        """
        count = 0
        for tier_id in self.checkpoint.run_states:
            for subtest_id in self.checkpoint.run_states[tier_id]:
                for run_num, state in list(self.checkpoint.run_states[tier_id][subtest_id].items()):
                    if state in ("failed", "rate_limited"):
                        self.checkpoint.run_states[tier_id][subtest_id][run_num] = "pending"
                        self.checkpoint.unmark_run_completed(tier_id, subtest_id, int(run_num))
                        count += 1
        return count

    def _find_tiers_with_intermediate_runs(self) -> dict[str, list[str]]:
        """Find tiers that have runs in non-terminal, non-pending states.

        These are runs that were interrupted mid-pipeline (e.g. report_written)
        and need to be resumed to reach a terminal state.

        Returns:
            Dict mapping tier_id -> list of "subtest_id/run_num" descriptors.

        """
        from scylla.e2e.state_machine import is_terminal_state

        result: dict[str, list[str]] = {}
        for tier_id, subtests in self.checkpoint.run_states.items():
            intermediate: list[str] = []
            for subtest_id, runs in subtests.items():
                for run_num, state_str in runs.items():
                    try:
                        state = RunState(state_str)
                    except ValueError:
                        continue
                    if not is_terminal_state(state) and state != RunState.PENDING:
                        intermediate.append(f"{subtest_id}/run_{run_num}")
            if intermediate:
                result[tier_id] = intermediate
        return result

    def _find_orphaned_subtest_states(self) -> dict[str, list[str]]:
        """Find subtests marked as aggregated but with no corresponding run_states.

        This detects checkpoint integrity issues where a subtest was marked
        complete without recording its runs.

        Returns:
            Dict mapping tier_id -> list of orphaned subtest_ids.

        """
        result: dict[str, list[str]] = {}
        for tier_id, subtests in self.checkpoint.subtest_states.items():
            orphaned: list[str] = []
            for subtest_id, sub_state in subtests.items():
                if sub_state in ("aggregated", "runs_complete"):
                    runs = self.checkpoint.run_states.get(tier_id, {}).get(subtest_id, {})
                    if not runs:
                        orphaned.append(subtest_id)
            if orphaned:
                result[tier_id] = orphaned
        return result

    _COMPLETE_FAMILY_STATES = ("complete", "tiers_complete", "reports_generated")
    _COMPLETE_TIER_STATES = ("complete", "subtests_complete", "best_selected", "reports_generated")

    def _reset_experiment_to_tiers_running(self) -> None:
        """Reset experiment_state to tiers_running if in a complete-family state."""
        if self.checkpoint.experiment_state in self._COMPLETE_FAMILY_STATES:
            self.checkpoint.experiment_state = "tiers_running"

    def _reset_tier_to_config_loaded(self, tier_id: str) -> None:
        """Reset a tier to config_loaded if in a complete-family state."""
        if self.checkpoint.tier_states.get(tier_id, "") in self._COMPLETE_TIER_STATES:
            self.checkpoint.tier_states[tier_id] = "config_loaded"

    def _reset_intermediate_runs_in_complete_experiment(self) -> None:
        """Reset complete experiments that have runs stuck in intermediate states.

        Intermediate runs (e.g. report_written) need the experiment/tier reset
        so the pipeline re-enters and finishes them.

        """
        tiers_with_intermediate = self._find_tiers_with_intermediate_runs()
        if not tiers_with_intermediate:
            return
        if self.checkpoint.experiment_state not in self._COMPLETE_FAMILY_STATES:
            return

        total = sum(len(v) for v in tiers_with_intermediate.values())
        logger.info(
            "Resetting experiment from '%s' to 'tiers_running' — %d intermediate runs in tiers: %s",
            self.checkpoint.experiment_state,
            total,
            list(tiers_with_intermediate.keys()),
        )
        self.checkpoint.experiment_state = "tiers_running"
        for tier_id in tiers_with_intermediate:
            self._reset_tier_to_config_loaded(tier_id)
            for sub_id, sub_state in self.checkpoint.subtest_states.get(tier_id, {}).items():
                if sub_state in (
                    "aggregated",
                    "runs_complete",
                ) and self._subtest_has_incomplete_runs(tier_id, sub_id):
                    self.checkpoint.subtest_states[tier_id][sub_id] = "runs_in_progress"

    def _reset_orphaned_subtest_states(self) -> None:
        """Reset subtests marked aggregated/runs_complete but with no run_states entries.

        These are checkpoint integrity issues where a subtest was marked
        complete without recording its runs.

        """
        orphaned = self._find_orphaned_subtest_states()
        if not orphaned:
            return

        total_orphaned = sum(len(v) for v in orphaned.values())
        logger.info(
            "Resetting %d orphaned subtest_states (aggregated without run_states): %s",
            total_orphaned,
            orphaned,
        )
        for tier_id, sub_ids in orphaned.items():
            for sub_id in sub_ids:
                self.checkpoint.subtest_states[tier_id][sub_id] = "pending"
            self._reset_experiment_to_tiers_running()
            self._reset_tier_to_config_loaded(tier_id)

    def _reset_failed_and_interrupted(self) -> None:
        """Reset failed/interrupted experiment, tier, and subtest states.

        Also resets runs with invalid agent results to replay_generated
        for re-execution (defense-in-depth).
        """
        # Always reset invalid runs regardless of experiment state,
        # since they can exist even in non-failed experiments.
        invalid_count = self._reset_invalid_runs()
        if invalid_count > 0:
            logger.info("Reset %d run(s) with invalid agent results", invalid_count)
        if self.checkpoint.experiment_state not in ("failed", "interrupted"):
            return

        logger.info(
            "Resetting experiment state from '%s' to 'tiers_running' for re-execution",
            self.checkpoint.experiment_state,
        )
        self.checkpoint.experiment_state = "tiers_running"

        for tier_id, tier_state in self.checkpoint.tier_states.items():
            if tier_state == "failed":
                self.checkpoint.tier_states[tier_id] = "pending"

        for tier_id in self.checkpoint.subtest_states:
            for subtest_id, sub_state in self.checkpoint.subtest_states[tier_id].items():
                if sub_state == "failed":
                    self.checkpoint.subtest_states[tier_id][subtest_id] = "pending"

    def reset_failed_states(self) -> tuple[ExperimentConfig, E2ECheckpoint]:
        """Reset failed/interrupted experiment, tier, subtest, and run states for re-execution.

        Resets:
        - run_states: failed/rate_limited → pending (always, regardless of experiment_state)
        - experiment_state: failed/interrupted → tiers_running
        - experiment_state: complete-family → tiers_running (when intermediate runs exist)
        - tier_states: failed → pending
        - tier_states: complete-family → config_loaded (when tier has intermediate runs)
        - subtest_states: failed → pending
        - subtest_states: aggregated without run_states → pending (orphaned)

        Run-state reset is unconditional: individual runs can be failed/rate_limited
        even when the experiment itself is in tiers_running (partial failures).

        Returns:
            Updated (config, checkpoint) tuple.

        """
        run_reset_count = self._reset_infra_error_runs()
        if run_reset_count > 0:
            logger.info("Reset %d failed/rate_limited run_states to pending", run_reset_count)

        self._reset_intermediate_runs_in_complete_experiment()
        self._reset_orphaned_subtest_states()
        self._reset_failed_and_interrupted()

        return self.config, self.checkpoint

    def _reset_invalid_runs(self) -> int:
        """Reset runs with invalid agent results to replay_generated.

        Scans all run states and checks for runs that advanced past
        AGENT_COMPLETE but have invalid agent results (exit_code=-1
        with zero token stats). These runs are reset to
        REPLAY_GENERATED so they get re-executed from the agent stage.

        Returns:
            Number of runs reset.

        """
        reset_count = 0
        experiment_dir = Path(self.checkpoint.experiment_dir)
        for tier_id, subtests in self.checkpoint.run_states.items():
            for subtest_id, runs in subtests.items():
                for run_id, state in runs.items():
                    if state not in _STATES_PAST_AGENT_COMPLETE:
                        continue
                    # Build run directory path — check completed/ first, then in_progress/
                    from scylla.e2e.paths import get_run_dir

                    run_num = int(run_id)
                    run_dir = get_run_dir(
                        experiment_dir, tier_id, subtest_id, run_num, completed=True
                    )
                    if not run_dir.exists():
                        run_dir = get_run_dir(
                            experiment_dir, tier_id, subtest_id, run_num, completed=False
                        )
                    if not _has_valid_agent_result(run_dir):
                        logger.info(
                            "Resetting invalid run %s/%s/%s from '%s' to 'replay_generated'",
                            tier_id,
                            subtest_id,
                            run_id,
                            state,
                        )
                        runs[run_id] = RunState.REPLAY_GENERATED.value
                        reset_count += 1
        return reset_count

    def _reset_tier_state_for_rerun(self, tier_id_str: str) -> None:
        """Reset a tier's checkpoint state so it can be re-executed.

        Chooses the minimal reset state based on whether subtests are missing or
        whether existing runs are incomplete.

        Args:
            tier_id_str: Tier ID string (e.g. "T0").

        """
        has_missing = self._tier_has_missing_subtests(TierID(tier_id_str))
        if has_missing:
            self.checkpoint.tier_states[tier_id_str] = "pending"
            return

        any_incomplete = any(
            self._subtest_has_incomplete_runs(tier_id_str, sub_id)
            for sub_id in self.checkpoint.subtest_states.get(tier_id_str, {})
        )
        if any_incomplete:
            self.checkpoint.tier_states[tier_id_str] = "config_loaded"
            for sub_id, sub_state in self.checkpoint.subtest_states.get(tier_id_str, {}).items():
                if sub_state in (
                    "aggregated",
                    "runs_complete",
                ) and self._subtest_has_incomplete_runs(tier_id_str, sub_id):
                    self.checkpoint.subtest_states[tier_id_str][sub_id] = "runs_in_progress"
        else:
            self.checkpoint.tier_states[tier_id_str] = "subtests_running"

    def merge_cli_tiers_and_reset_incomplete(
        self,
        cli_tiers: list[TierID],
        checkpoint_path: Path,
    ) -> tuple[ExperimentConfig, E2ECheckpoint]:
        """Merge new CLI tiers and reset incomplete tier/subtest states.

        Adds any CLI-requested tiers that are not yet in the saved config.
        Then detects if any requested tiers need (re-)execution and, if so,
        resets completed experiment/tier/subtest states so they can re-run.

        Args:
            cli_tiers: Tiers requested on the CLI for this invocation.
            checkpoint_path: Path to checkpoint file for saving updates.

        Returns:
            Updated (config, checkpoint) tuple.

        """
        existing_tier_ids = {t.value for t in self.config.tiers_to_run}
        new_tiers = [t for t in cli_tiers if t.value not in existing_tier_ids]
        if new_tiers:
            tier_names = [t.value for t in new_tiers]
            logger.info("Adding CLI-specified tiers to run: %s", tier_names)
            self.config = self.config.model_copy(
                update={"tiers_to_run": self.config.tiers_to_run + new_tiers}
            )
            self._save_config()
            self.checkpoint.config_hash = compute_config_hash(self.config)

        needs_execution = self.check_tiers_need_execution(cli_tiers)

        if needs_execution and self.checkpoint.experiment_state in (
            "complete",
            "tiers_complete",
            "reports_generated",
        ):
            logger.info(
                "Resetting experiment from '%s' to 'tiers_running' "
                "— CLI-requested tiers need execution",
                self.checkpoint.experiment_state,
            )
            self.checkpoint.experiment_state = "tiers_running"

            for tier_id_str in needs_execution:
                existing_tier_state = self.checkpoint.tier_states.get(tier_id_str)
                if existing_tier_state in (
                    "complete",
                    "subtests_complete",
                    "best_selected",
                    "reports_generated",
                ):
                    self._reset_tier_state_for_rerun(tier_id_str)

        save_checkpoint(self.checkpoint, checkpoint_path)
        return self.config, self.checkpoint

    def _tier_has_incomplete_run_states(self, tid: str) -> bool:
        """Return True if any run in the tier is not in a terminal state.

        Args:
            tid: Tier ID string (e.g. "T0").

        Returns:
            True if at least one run is non-terminal.

        """
        from scylla.e2e.state_machine import is_terminal_state

        for _sub_id, runs in self.checkpoint.run_states.get(tid, {}).items():
            for state_str in runs.values():
                try:
                    state = RunState(state_str)
                except ValueError:
                    continue
                if not is_terminal_state(state):
                    return True
        return False

    def _tier_has_missing_subtests(self, tier_id: TierID) -> bool:
        """Return True if the tier config lists subtests not yet in the checkpoint.

        Args:
            tier_id: TierID to check.

        Returns:
            True if config has subtests absent from the checkpoint.

        """
        tid = tier_id.value
        try:
            tier_config = self.tier_manager.load_tier_config(tier_id, self.config.skip_agent_teams)
            config_subtests = {s.id for s in tier_config.subtests}
            if self.config.max_subtests is not None:
                config_subtests = {s.id for s in tier_config.subtests[: self.config.max_subtests]}
            checkpoint_subtests = set(self.checkpoint.subtest_states.get(tid, {}).keys())
            return bool(config_subtests - checkpoint_subtests)
        except Exception:
            return False

    def check_tiers_need_execution(self, cli_tiers: list[TierID]) -> set[str]:
        """Return tier IDs that need execution.

        New tiers, tiers with incomplete runs, or tiers with subtests missing from
        the checkpoint (e.g. max_subtests expanded).

        Args:
            cli_tiers: Tiers requested on the CLI for this invocation.

        Returns:
            Set of tier ID strings that require execution.

        """
        needs_work: set[str] = set()
        for tier_id in cli_tiers:
            tid = tier_id.value
            # New tier (not yet in checkpoint)
            if tid not in self.checkpoint.tier_states:
                needs_work.add(tid)
                continue
            # Tier with runs that have not yet reached a terminal state
            if self._tier_has_incomplete_run_states(tid):
                needs_work.add(tid)
                continue
            # Subtests present in tier config but absent from checkpoint — this
            # happens when max_subtests is expanded (or removed) on resume.
            if self._tier_has_missing_subtests(tier_id):
                needs_work.add(tid)
        return needs_work

    def _subtest_has_incomplete_runs(self, tier_id: str, subtest_id: str) -> bool:
        """Return True if any run in this subtest is not in a terminal state.

        Args:
            tier_id: Tier identifier string (e.g. "T0").
            subtest_id: Subtest identifier string (e.g. "T0_00").

        Returns:
            True if at least one run is not in a terminal state.

        """
        from scylla.e2e.state_machine import is_terminal_state

        runs = self.checkpoint.run_states.get(tier_id, {}).get(subtest_id, {})
        for state_str in runs.values():
            try:
                state = RunState(state_str)
            except ValueError:
                continue
            if not is_terminal_state(state):
                return True
        return False

    def _save_config(self) -> None:
        """Persist updated config via tier_manager's save path.

        Delegates to the runner's _save_config pattern by writing config
        to the experiment directory derived from the checkpoint.

        """
        import json

        experiment_dir = Path(self.checkpoint.experiment_dir)
        config_dir = experiment_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "experiment.json"
        config_path.write_text(json.dumps(self.config.model_dump(mode="json"), indent=2))
        logger.debug("Saved updated config to %s", config_path)
