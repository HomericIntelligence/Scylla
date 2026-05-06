"""Checkpoint management for E2E experiment pause/resume.

This module provides checkpoint state tracking for E2E experiments,
enabling pause/resume functionality for overnight runs with rate limit handling.

Checkpoint Versions:
    - v2.0: run-level granularity (passed/failed/agent_complete per run)
    - v3.0: fine-grained state machine (RunState/SubtestState/TierState/ExperimentState)
            Adds: experiment_state, tier_states, subtest_states, run_states, last_heartbeat
            Backward compat: completed_runs preserved as derived view
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from scylla.e2e.models import ExperimentConfig

logger = logging.getLogger(__name__)


class CheckpointError(Exception):
    """Base exception for checkpoint-related errors."""

    pass


class ConfigMismatchError(CheckpointError):
    """Raised when checkpoint config doesn't match current config."""

    pass


class E2ECheckpoint(BaseModel):
    """Checkpoint state for E2E experiment resume capability.

    Stored at: results/{experiment}/checkpoint.json

    v3.0: Fine-grained state machine with hierarchical state tracking.
    Each run has an explicit RunState enum value, enabling resume from
    any point in the run lifecycle (not just at run completion).

    v3.1: Expanded to 16-state run lifecycle. Added states:
    dir_structure_created, symlinks_applied, config_committed,
    prompt_written, replay_generated, diff_captured, judge_pipeline_run,
    judge_prompt_built, run_finalized, report_written.
    Removed: workspace_configured, agent_ready, judge_ready, run_complete.

    Backward compatibility: completed_runs is preserved for v2.0 consumers.
    It is derived from run_states on load and kept in sync on write.

    Attributes:
        version: Checkpoint format version (3.1)
        experiment_id: Unique experiment identifier
        experiment_dir: Absolute path to experiment directory
        config_hash: SHA256 hash of config for strict validation
        experiment_state: Overall experiment state (ExperimentState enum value)
        tier_states: tier_id -> TierState enum value
        subtest_states: tier_id -> subtest_id -> SubtestState enum value
        run_states: tier_id -> subtest_id -> run_num -> RunState enum value
        completed_runs: tier_id -> subtest_id -> {run_number: status}
                       Backward compat: "passed", "failed", "agent_complete"
        started_at: ISO timestamp of experiment start
        last_updated_at: ISO timestamp of last checkpoint update
        last_heartbeat: ISO timestamp of last heartbeat (for zombie detection)
        status: Current status (running, paused_rate_limit, completed, failed)
        rate_limit_source: Source of rate limit (agent or judge)
        rate_limit_until: ISO timestamp when rate limit expires
        pause_count: Number of times paused for rate limits
        pid: Process ID of running experiment

    """

    version: str = Field(default="3.1", description="Checkpoint format version")
    experiment_id: str = Field(default="", description="Unique experiment identifier")
    experiment_dir: str = Field(default="", description="Absolute path to experiment directory")
    config_hash: str = Field(default="", description="SHA256 hash of config")

    # v3.0 hierarchical state tracking
    experiment_state: str = Field(
        default="initializing", description="Overall experiment state (ExperimentState value)"
    )
    tier_states: dict[str, str] = Field(
        default_factory=dict, description="tier_id -> TierState value"
    )
    subtest_states: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="tier_id -> subtest_id -> SubtestState value"
    )
    run_states: dict[str, dict[str, dict[str, str]]] = Field(
        default_factory=dict,
        description="tier_id -> subtest_id -> run_num_str -> RunState value",
    )

    # v2.0 backward compat: tier_id -> subtest_id -> {run_number: status}
    # status: "passed", "failed", "agent_complete"
    completed_runs: dict[str, dict[str, dict[int, str]]] = Field(
        default_factory=dict, description="Completed runs tracking (backward compat)"
    )

    # Timing
    started_at: str = Field(default="", description="ISO timestamp of experiment start")
    last_updated_at: str = Field(default="", description="ISO timestamp of last update")
    last_heartbeat: str = Field(default="", description="ISO timestamp of last heartbeat")

    # Rate limit state
    status: str = Field(default="running", description="Current status")
    rate_limit_source: str | None = Field(default=None, description="Source of rate limit")
    rate_limit_until: str | None = Field(
        default=None, description="ISO timestamp when rate limit expires"
    )
    pause_count: int = Field(default=0, description="Number of times paused")

    # Process info for monitoring
    pid: int | None = Field(default=None, description="Process ID of running experiment")

    # -------------------------------------------------------------------------
    # v3.0 State machine helpers
    # -------------------------------------------------------------------------

    def get_run_state(self, tier_id: str, subtest_id: str, run_num: int) -> str:
        """Get the fine-grained RunState for a run.

        Args:
            tier_id: Tier identifier (e.g., "T0")
            subtest_id: Subtest identifier (e.g., "00-empty")
            run_num: Run number (1-based)

        Returns:
            RunState value string, or "pending" if not found

        """
        key = str(run_num)
        return self.run_states.get(tier_id, {}).get(subtest_id, {}).get(key, "pending")

    def set_run_state(self, tier_id: str, subtest_id: str, run_num: int, state: str) -> None:
        """Set the fine-grained RunState for a run.

        Also syncs completed_runs for backward compatibility:
        - run_complete / checkpointed / worktree_cleaned -> preserve existing status or "passed"
        - agent_complete -> "agent_complete"
        - failed -> "failed"

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            run_num: Run number (1-based)
            state: RunState value string

        """
        key = str(run_num)
        if tier_id not in self.run_states:
            self.run_states[tier_id] = {}
        if subtest_id not in self.run_states[tier_id]:
            self.run_states[tier_id][subtest_id] = {}
        self.run_states[tier_id][subtest_id][key] = state
        self.last_updated_at = datetime.now(timezone.utc).isoformat()

        # Sync to completed_runs for v2.0 backward compat consumers
        # Includes both v3.0 (run_complete) and v3.1 (run_finalized, report_written) names
        terminal_complete = {
            "run_complete",  # v3.0 name (kept for migration compat)
            "run_finalized",  # v3.1 name
            "report_written",  # v3.1 name
            "checkpointed",
            "worktree_cleaned",
        }
        if state in terminal_complete:
            # Preserve existing status (passed/failed), default to "passed"
            existing = self.get_run_status(tier_id, subtest_id, run_num)
            compat_status = existing if existing in ("passed", "failed") else "passed"
            self.mark_run_completed(tier_id, subtest_id, run_num, status=compat_status)
        elif state == "agent_complete":
            self.mark_run_completed(tier_id, subtest_id, run_num, status="agent_complete")
        elif state == "failed":
            self.mark_run_completed(tier_id, subtest_id, run_num, status="failed")

    def get_tier_state(self, tier_id: str) -> str:
        """Get the TierState for a tier.

        Args:
            tier_id: Tier identifier

        Returns:
            TierState value string, or "pending" if not found

        """
        return self.tier_states.get(tier_id, "pending")

    def set_tier_state(self, tier_id: str, state: str) -> None:
        """Set the TierState for a tier.

        Args:
            tier_id: Tier identifier
            state: TierState value string

        """
        self.tier_states[tier_id] = state
        self.last_updated_at = datetime.now(timezone.utc).isoformat()

    def get_subtest_state(self, tier_id: str, subtest_id: str) -> str:
        """Get the SubtestState for a subtest.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier

        Returns:
            SubtestState value string, or "pending" if not found

        """
        return self.subtest_states.get(tier_id, {}).get(subtest_id, "pending")

    def set_subtest_state(self, tier_id: str, subtest_id: str, state: str) -> None:
        """Set the SubtestState for a subtest.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            state: SubtestState value string

        """
        if tier_id not in self.subtest_states:
            self.subtest_states[tier_id] = {}
        self.subtest_states[tier_id][subtest_id] = state
        self.last_updated_at = datetime.now(timezone.utc).isoformat()

    def update_heartbeat(self) -> None:
        """Update the heartbeat timestamp to now."""
        self.last_heartbeat = datetime.now(timezone.utc).isoformat()

    # -------------------------------------------------------------------------
    # v2.0 backward compat helpers
    # -------------------------------------------------------------------------

    def mark_run_completed(
        self, tier_id: str, subtest_id: str, run_number: int, status: str = "passed"
    ) -> None:
        """Mark a run as completed in the checkpoint with status.

        Args:
            tier_id: Tier identifier (e.g., "T0", "T1")
            subtest_id: Subtest identifier (e.g., "00-empty")
            run_number: Run number (1-based)
            status: Run status - "passed", "failed", or "agent_complete"

        """
        if status not in ("passed", "failed", "agent_complete"):
            raise ValueError(
                f"Invalid status: {status}. Must be 'passed', 'failed', or 'agent_complete'."
            )

        if tier_id not in self.completed_runs:
            self.completed_runs[tier_id] = {}
        if subtest_id not in self.completed_runs[tier_id]:
            self.completed_runs[tier_id][subtest_id] = {}

        self.completed_runs[tier_id][subtest_id][run_number] = status
        self.last_updated_at = datetime.now(timezone.utc).isoformat()

    def unmark_run_completed(self, tier_id: str, subtest_id: str, run_number: int) -> None:
        """Remove a run from completed runs (for re-running invalid runs).

        Args:
            tier_id: Tier identifier (e.g., "T0", "T1")
            subtest_id: Subtest identifier (e.g., "00-empty")
            run_number: Run number (1-based)

        """
        if (
            tier_id in self.completed_runs
            and subtest_id in self.completed_runs[tier_id]
            and run_number in self.completed_runs[tier_id][subtest_id]
        ):
            del self.completed_runs[tier_id][subtest_id][run_number]
            self.last_updated_at = datetime.now(timezone.utc).isoformat()

    def get_run_status(self, tier_id: str, subtest_id: str, run_number: int) -> str | None:
        """Get the status of a run.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            run_number: Run number (1-based)

        Returns:
            Run status ("passed", "failed", "agent_complete") or None if not found

        """
        if tier_id in self.completed_runs and subtest_id in self.completed_runs[tier_id]:
            return self.completed_runs[tier_id][subtest_id].get(run_number)
        return None

    def is_run_completed(self, tier_id: str, subtest_id: str, run_number: int) -> bool:
        """Check if a run has been fully completed (passed or failed).

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            run_number: Run number (1-based)

        Returns:
            True if run status is "passed" or "failed", False otherwise

        """
        status = self.get_run_status(tier_id, subtest_id, run_number)
        return status in ("passed", "failed")

    def get_completed_run_count(self) -> int:
        """Get total number of completed runs across all tiers/subtests.

        Returns:
            Total count of completed runs

        """
        total = 0
        for tier_runs in self.completed_runs.values():
            for subtest_runs in tier_runs.values():
                total += len(subtest_runs)
        return total

    @classmethod
    def _convert_completed_runs_keys(
        cls, raw: dict[str, dict[str, dict[str, str]]]
    ) -> dict[str, dict[str, dict[int, str]]]:
        """Convert completed_runs run_number keys from JSON strings to int.

        JSON serialization converts Python int dict keys to strings.
        When loading from disk, we must convert them back to int for
        correct lookups via get_run_status() and is_run_completed().

        Args:
            raw: completed_runs dict with string keys (from JSON)

        Returns:
            completed_runs dict with int keys (Python native)

        """
        result: dict[str, dict[str, dict[int, str]]] = {}
        for tier_id, subtests in raw.items():
            result[tier_id] = {}
            for subtest_id, runs in subtests.items():
                result[tier_id][subtest_id] = {int(k): v for k, v in runs.items()}
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> E2ECheckpoint:
        """Create from dictionary with version validation and migration.

        Supports:
        - v2.0: migrated to v3.0 then v3.1 automatically
        - v3.0: migrated to v3.1 automatically (state name remapping)
        - v3.1: loaded as-is
        - v1.0 or unknown: rejected (must start fresh)

        Args:
            data: Dictionary representation

        Returns:
            E2ECheckpoint instance

        Raises:
            CheckpointError: If checkpoint version is incompatible

        """
        version = data.get("version", "1.0")

        if version == "2.0":
            # Migrate v2.0 -> v3.0 -> v3.1
            data = cls._migrate_v2_to_v3(data)
            data = cls._migrate_v3_to_v3_1(data)
        elif version == "3.0":
            # Convert string keys to int keys for completed_runs (JSON serialization)
            if "completed_runs" in data:
                data["completed_runs"] = cls._convert_completed_runs_keys(data["completed_runs"])
            data = cls._migrate_v3_to_v3_1(data)
        elif version == "3.1":
            # Convert string keys to int keys for completed_runs (JSON serialization)
            if "completed_runs" in data:
                data["completed_runs"] = cls._convert_completed_runs_keys(data["completed_runs"])
        else:
            raise CheckpointError(
                f"Incompatible checkpoint version {version}. "
                "This version requires checkpoint format 2.0, 3.0, or 3.1. "
                "Please delete the old checkpoint and re-run the experiment."
            )

        return super().model_validate(data)

    @classmethod
    def _migrate_v2_to_v3(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate v2.0 checkpoint data to v3.0 schema.

        Derives run_states from completed_runs:
        - "passed" -> RunState.RUN_COMPLETE (run fully done, passed)
        - "failed" -> RunState.RUN_COMPLETE (run fully done, failed)
        - "agent_complete" -> RunState.AGENT_COMPLETE

        Tier/subtest states are inferred as best-effort from completed_runs.

        Args:
            data: v2.0 checkpoint dict

        Returns:
            v3.0 checkpoint dict ready for model_validate

        """
        logger.info("Migrating checkpoint from v2.0 to v3.0")
        data = dict(data)  # shallow copy to avoid mutating caller's dict

        # Convert completed_runs keys (JSON string -> int)
        completed_runs_raw = data.get("completed_runs", {})
        completed_runs = cls._convert_completed_runs_keys(completed_runs_raw)
        data["completed_runs"] = completed_runs

        # Derive run_states from completed_runs
        run_states: dict[str, dict[str, dict[str, str]]] = {}
        tier_states: dict[str, str] = {}
        subtest_states: dict[str, dict[str, str]] = {}

        for tier_id, subtests in completed_runs.items():
            run_states[tier_id] = {}
            subtest_states[tier_id] = {}
            for subtest_id, runs in subtests.items():
                run_states[tier_id][subtest_id] = {}
                for run_num, status in runs.items():
                    # "passed" or "failed" -> run was fully completed; "agent_complete" stays
                    run_state = "agent_complete" if status == "agent_complete" else "run_complete"
                    run_states[tier_id][subtest_id][str(run_num)] = run_state
                subtest_states[tier_id][subtest_id] = "runs_in_progress"
            tier_states[tier_id] = "subtests_running"

        data["run_states"] = run_states
        data["tier_states"] = tier_states
        data["subtest_states"] = subtest_states
        data["experiment_state"] = "tiers_running"
        data["last_heartbeat"] = data.get("last_updated_at", "")
        data["version"] = "3.0"

        return data

    @classmethod
    def _migrate_v3_to_v3_1(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate v3.0 checkpoint data to v3.1 schema.

        Maps old state names (10-state pipeline) to new state names
        (16-state pipeline). States that were split map to the final
        sub-state of the split group (meaning the full original work
        was done, so we advance to the most complete equivalent).

        State mapping (old v3.0 -> new v3.1):
          workspace_configured -> config_committed  (split: symlinks_applied + config_committed)
          agent_ready          -> replay_generated  (split: prompt_written + replay_generated)
          judge_ready          -> judge_prompt_built (split: diff_captured + judge_pipeline_run
                                                      + judge_prompt_built)
          run_complete         -> report_written    (split: included report generation)

        Args:
            data: v3.0 checkpoint dict (already has int keys in completed_runs)

        Returns:
            v3.1 checkpoint dict ready for model_validate

        """
        logger.info("Migrating checkpoint from v3.0 to v3.1")
        data = dict(data)  # shallow copy

        # State name mapping: old v3.0 name -> new v3.1 name
        state_map = {
            "workspace_configured": "config_committed",
            "agent_ready": "replay_generated",
            "judge_ready": "judge_prompt_built",
            "run_complete": "report_written",  # run_complete included reports
        }

        run_states = data.get("run_states", {})
        migrated_run_states: dict[str, dict[str, dict[str, str]]] = {}

        for tier_id, subtests in run_states.items():
            migrated_run_states[tier_id] = {}
            for subtest_id, runs in subtests.items():
                migrated_run_states[tier_id][subtest_id] = {}
                for run_num_str, state_str in runs.items():
                    new_state = state_map.get(state_str, state_str)
                    migrated_run_states[tier_id][subtest_id][run_num_str] = new_state

        data["run_states"] = migrated_run_states
        data["version"] = "3.1"

        return data


# Lock protecting checkpoint serialization. With ThreadPoolExecutor, multiple
# threads may call save_checkpoint() concurrently. Without this lock, thread A
# could serialize stale state (before thread B's mutation) and overwrite B's
# checkpoint on the atomic rename. The lock ensures serialize + rename is atomic
# with respect to other threads.
_checkpoint_write_lock = threading.Lock()


def save_checkpoint(checkpoint: E2ECheckpoint, path: Path) -> None:
    """Save checkpoint to file with atomic write, serialized across threads.

    All worker threads share the same in-memory checkpoint object. This function
    serializes access so that mutations from one thread are not lost when another
    thread writes concurrently.

    Args:
        checkpoint: Checkpoint to save
        path: Path to checkpoint file

    Raises:
        CheckpointError: If save fails

    """
    with _checkpoint_write_lock:
        try:
            # Update timestamp
            checkpoint.last_updated_at = datetime.now(timezone.utc).isoformat()

            # Atomic write: write to temp file, then rename.
            # Include both PID and thread ID in the temp filename so concurrent threads
            # in the same process each get a unique file, preventing ENOENT when one
            # thread renames the file before another can.
            tid = threading.get_ident()
            temp_path = path.parent / f"{path.stem}.tmp.{os.getpid()}.{tid}{path.suffix}"
            data = checkpoint.model_dump()

            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename — each writer has a unique temp file (PID+TID)
            temp_path.replace(path)

        except OSError as e:
            raise CheckpointError(f"Failed to save checkpoint to {path}: {e}") from e


def load_checkpoint(path: Path) -> E2ECheckpoint:
    """Load checkpoint from file.

    Args:
        path: Path to checkpoint file

    Returns:
        Loaded E2ECheckpoint

    Raises:
        CheckpointError: If load fails or file doesn't exist

    """
    if not path.exists():
        raise CheckpointError(f"Checkpoint file not found: {path}")

    try:
        with open(path) as f:
            data = json.load(f)
        return E2ECheckpoint.from_dict(data)
    except (OSError, json.JSONDecodeError) as e:
        raise CheckpointError(f"Failed to load checkpoint from {path}: {e}") from e


def compute_config_hash(config: ExperimentConfig) -> str:
    """Compute hash of experiment config for validation.

    Includes all fields that affect experiment execution.
    Excludes fields that don't affect results (max_subtests, legacy parallel_* fields).

    Args:
        config: Experiment configuration

    Returns:
        16-character hex hash (first 16 chars of SHA256)

    """
    config_dict = config.model_dump(mode="json")

    # Remove fields that don't affect results
    config_dict.pop("parallel_subtests", None)  # Legacy parallelization setting
    config_dict.pop("parallel_high", None)  # Legacy parallelization setting
    config_dict.pop("parallel_med", None)  # Legacy parallelization setting
    config_dict.pop("parallel_low", None)  # Legacy parallelization setting
    config_dict.pop("max_subtests", None)  # Development/testing only
    config_dict.pop("tiers_to_run", None)  # Tiers are additive across resumes
    # Remove ephemeral --until flags (changing these between runs must not break resume)
    config_dict.pop("until_run_state", None)
    config_dict.pop("until_tier_state", None)
    config_dict.pop("until_experiment_state", None)
    # Remove ephemeral --from flags
    config_dict.pop("from_run_state", None)
    config_dict.pop("from_tier_state", None)
    config_dict.pop("from_experiment_state", None)
    # Remove ephemeral filters
    config_dict.pop("filter_tiers", None)
    config_dict.pop("filter_subtests", None)
    config_dict.pop("filter_runs", None)
    config_dict.pop("filter_statuses", None)
    config_dict.pop("filter_judge_slots", None)
    # Remove ephemeral resource management flags
    config_dict.pop("keep_failed_workspaces", None)
    config_dict.pop("max_concurrent_workspaces", None)
    config_dict.pop("max_concurrent_agents", None)
    config_dict.pop("fail_on_resource_check", None)

    # Stable JSON serialization (sorted keys)
    config_json = json.dumps(config_dict, sort_keys=True)
    return hashlib.sha256(config_json.encode()).hexdigest()[:16]


def validate_checkpoint_config(checkpoint: E2ECheckpoint, config: ExperimentConfig) -> bool:
    """Validate that checkpoint config matches current config.

    Requirement: Strict match - config must be identical to resume.

    Args:
        checkpoint: Loaded checkpoint
        config: Current experiment configuration

    Returns:
        True if configs match, False otherwise

    """
    current_hash = compute_config_hash(config)
    return checkpoint.config_hash == current_hash


def get_experiment_status(experiment_dir: Path) -> dict[str, Any]:
    """Get current experiment status for monitoring.

    Checks checkpoint file and PID file to determine if experiment
    is running, paused, or completed.

    Args:
        experiment_dir: Path to experiment directory

    Returns:
        Dict with status information:
        - running: bool - whether process is active
        - status: str - status from checkpoint
        - completed_runs: int - number of completed runs
        - rate_limit_until: str | None - when rate limit expires
        - pid: int | None - process ID if running

    """
    checkpoint_path = experiment_dir / "checkpoint.json"
    pid_path = experiment_dir / "experiment.pid"

    result: dict[str, Any] = {"running": False, "status": "unknown"}

    # Load checkpoint if exists
    if checkpoint_path.exists():
        try:
            checkpoint = load_checkpoint(checkpoint_path)
            result["status"] = checkpoint.status
            result["completed_runs"] = checkpoint.get_completed_run_count()
            if checkpoint.rate_limit_until:
                result["rate_limit_until"] = checkpoint.rate_limit_until
        except CheckpointError as e:
            logger.debug("Could not load checkpoint for status check: %s", e)

    # Check if process is running
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
            result["running"] = True
            result["pid"] = pid
        except (OSError, ValueError):
            # Process doesn't exist or PID file is invalid
            result["running"] = False
            result["pid"] = None

    return result


def reset_runs_for_from_state(  # noqa: C901  # state reset with many filter/condition branches
    checkpoint: E2ECheckpoint,
    from_state: str,
    tier_filter: list[str] | None = None,
    subtest_filter: list[str] | None = None,
    run_filter: list[int] | None = None,
    status_filter: list[str] | None = None,
) -> int:
    """Reset qualifying runs to PENDING for re-execution from the given state.

    Resets runs whose current state is AT or PAST from_state (in the normal
    run sequence). Also resets corresponding subtest_states to pending and
    tier_states to pending. Removes reset runs from completed_runs.

    Per design: always resets to PENDING (full workspace recreation).

    Args:
        checkpoint: The experiment checkpoint (mutated in place)
        from_state: RunState value string (e.g. "replay_generated")
        tier_filter: If set, only reset runs in these tiers
        subtest_filter: If set, only reset runs in these subtests
        run_filter: If set, only reset these run numbers (1-based)
        status_filter: If set, only reset runs with these statuses
            (from completed_runs: "passed"/"failed"/"agent_complete")

    Returns:
        Count of runs reset to PENDING

    """
    from scylla.e2e.state_machine import _RUN_STATE_SEQUENCE

    # Build index map for ordering
    state_index = {state.value: idx for idx, state in enumerate(_RUN_STATE_SEQUENCE)}
    from_index = state_index.get(from_state)
    if from_index is None:
        logger.warning(f"Unknown from_state {from_state!r}, no runs reset")
        return 0

    reset_count = 0
    affected_tiers: set[str] = set()
    affected_subtests: set[tuple[str, str]] = set()

    for tier_id, subtests in checkpoint.run_states.items():
        if tier_filter and tier_id not in tier_filter:
            continue
        for subtest_id, runs in subtests.items():
            if subtest_filter and subtest_id not in subtest_filter:
                continue
            for run_num_str, run_state_str in runs.items():
                run_num = int(run_num_str)
                if run_filter and run_num not in run_filter:
                    continue

                # Check status filter (from completed_runs)
                if status_filter:
                    run_status = checkpoint.get_run_status(tier_id, subtest_id, run_num)
                    if run_status not in status_filter:
                        continue

                # Check if current state is at or past from_state.
                # Terminal states (failed, rate_limited) are not in the normal
                # sequence (index == -1). If they passed status_filter, reset them.
                current_index = state_index.get(run_state_str, -1)
                if current_index >= from_index or (current_index == -1 and status_filter):
                    checkpoint.run_states[tier_id][subtest_id][run_num_str] = "pending"
                    checkpoint.unmark_run_completed(tier_id, subtest_id, run_num)
                    affected_tiers.add(tier_id)
                    affected_subtests.add((tier_id, subtest_id))
                    reset_count += 1

    # Cascade: reset affected subtest states to pending
    for tier_id, subtest_id in affected_subtests:
        checkpoint.set_subtest_state(tier_id, subtest_id, "pending")

    # Cascade: reset affected tier states to pending
    for tier_id in affected_tiers:
        checkpoint.set_tier_state(tier_id, "pending")

    # Reset experiment state if any tiers were affected
    if affected_tiers:
        checkpoint.experiment_state = "tiers_running"

    return reset_count


def reset_tiers_for_from_state(
    checkpoint: E2ECheckpoint,
    from_state: str,
    tier_filter: list[str] | None = None,
) -> int:
    """Reset qualifying tiers to PENDING for re-execution from the given state.

    Args:
        checkpoint: The experiment checkpoint (mutated in place)
        from_state: TierState value string (e.g. "subtests_running")
        tier_filter: If set, only reset these tiers

    Returns:
        Count of tiers reset

    """
    from scylla.e2e.tier_state_machine import _TIER_STATE_SEQUENCE

    state_index = {state.value: idx for idx, state in enumerate(_TIER_STATE_SEQUENCE)}
    from_index = state_index.get(from_state)
    if from_index is None:
        logger.warning(f"Unknown from_state (tier) {from_state!r}, no tiers reset")
        return 0

    reset_count = 0
    affected_tiers: list[str] = []

    for tier_id, tier_state_str in checkpoint.tier_states.items():
        if tier_filter and tier_id not in tier_filter:
            continue
        current_index = state_index.get(tier_state_str, -1)
        if current_index >= from_index:
            checkpoint.set_tier_state(tier_id, "pending")
            affected_tiers.append(tier_id)
            reset_count += 1

    # Reset experiment state if any tiers were affected
    if affected_tiers:
        checkpoint.experiment_state = "tiers_running"

    return reset_count


def reset_experiment_for_from_state(
    checkpoint: E2ECheckpoint,
    from_state: str,
) -> int:
    """Reset experiment state for re-execution from the given state.

    Args:
        checkpoint: The experiment checkpoint (mutated in place)
        from_state: ExperimentState value string (e.g. "tiers_running")

    Returns:
        1 if experiment state was reset, 0 otherwise

    """
    from scylla.e2e.experiment_state_machine import _EXPERIMENT_STATE_SEQUENCE

    state_index = {state.value: idx for idx, state in enumerate(_EXPERIMENT_STATE_SEQUENCE)}
    from_index = state_index.get(from_state)
    if from_index is None:
        logger.warning(f"Unknown from_state (experiment) {from_state!r}, not reset")
        return 0

    current_index = state_index.get(checkpoint.experiment_state, -1)
    if current_index >= from_index:
        checkpoint.experiment_state = from_state
        return 1

    return 0
