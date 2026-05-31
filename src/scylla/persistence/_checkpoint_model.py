"""E2ECheckpoint Pydantic model and associated exceptions.

Split from :mod:`scylla.persistence.checkpoint` to keep that module under
600 lines while preserving the full public API via re-exports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

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


__all__ = ["CheckpointError", "ConfigMismatchError", "E2ECheckpoint"]
