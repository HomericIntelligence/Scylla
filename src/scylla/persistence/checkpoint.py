"""Checkpoint management for E2E experiment pause/resume.

This module provides checkpoint state tracking for E2E experiments,
enabling pause/resume functionality for overnight runs with rate limit handling.

Checkpoint Versions:
    - v2.0: run-level granularity (passed/failed/agent_complete per run)
    - v3.0: fine-grained state machine (RunState/SubtestState/TierState/ExperimentState)
            Adds: experiment_state, tier_states, subtest_states, run_states, last_heartbeat
            Backward compat: completed_runs preserved as derived view

The :class:`E2ECheckpoint` Pydantic model lives in
:mod:`scylla.persistence._checkpoint_model` and is re-exported from here for
backward compatibility.
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

from scylla.metrics.emitter import get_default_emitter
from scylla.persistence._checkpoint_model import (
    CheckpointError as CheckpointError,
)
from scylla.persistence._checkpoint_model import (
    ConfigMismatchError as ConfigMismatchError,
)
from scylla.persistence._checkpoint_model import (
    E2ECheckpoint as E2ECheckpoint,
)
from scylla.utils.tracing import get_tracer

if TYPE_CHECKING:
    from scylla.e2e.models import ExperimentConfig

logger = logging.getLogger(__name__)
_tracer = get_tracer(__name__)


# Lock protecting checkpoint serialization. With ThreadPoolExecutor, multiple
# threads may call save_checkpoint() concurrently. Without this lock, thread A
# could serialize stale state (before thread B's mutation) and overwrite B's
# checkpoint on the atomic rename. The lock ensures serialize + rename is atomic
# with respect to other threads.
_checkpoint_write_lock = threading.Lock()


def save_checkpoint(checkpoint: E2ECheckpoint, path: Path) -> None:
    """Save checkpoint to file with atomic write and rolling .bak backup.

    Before overwriting, renames the existing checkpoint to ``<path>.bak`` so
    that ``load_checkpoint`` can fall back to it if the new primary file is
    ever corrupt on the next read.

    All worker threads share the same in-memory checkpoint object. This function
    serializes access so that mutations from one thread are not lost when another
    thread writes concurrently.

    Args:
        checkpoint: Checkpoint to save
        path: Path to checkpoint file

    Raises:
        CheckpointError: If save fails

    """
    import time as _time

    _save_start = _time.monotonic()
    _outcome = "error"
    with (
        _checkpoint_write_lock,
        _tracer.start_as_current_span(
            "scylla.checkpoint.save",
            attributes={"scylla.experiment_id": checkpoint.experiment_id},
        ) as _span,
    ):
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

            # Rolling single-level backup: rename existing primary → .bak before
            # promoting the new temp file.  Both operations are atomic renames on
            # the same filesystem so the window where neither file exists is
            # vanishingly small.
            bak_path = path.with_suffix(".json.bak")
            if path.exists():
                path.rename(bak_path)

            # Atomic rename — each writer has a unique temp file (PID+TID)
            temp_path.replace(path)
            _outcome = "ok"

        except OSError as e:
            _span.record_exception(e)
            raise CheckpointError(f"Failed to save checkpoint to {path}: {e}") from e
        finally:
            try:
                emitter = get_default_emitter()
                labels = {"experiment": checkpoint.experiment_id}
                _elapsed = float(_time.monotonic() - _save_start)
                emitter.emit_gauge(
                    "scylla_checkpoint_save_duration_seconds",
                    _elapsed,
                    labels=labels,
                )
                emitter.emit_histogram(
                    "scylla_checkpoint_save_seconds",
                    _elapsed,
                    labels=labels,
                )
                emitter.emit_counter(
                    "scylla_checkpoint_save_total",
                    1,
                    labels={**labels, "outcome": _outcome},
                )
            except Exception as _e:  # never break checkpoint save
                logger.debug(f"Checkpoint metric emission failed (non-fatal): {_e}")


def _load_checkpoint_from_path(path: Path) -> E2ECheckpoint:
    """Parse and validate a single checkpoint file.

    Args:
        path: Path to an existing checkpoint file

    Returns:
        Loaded E2ECheckpoint

    Raises:
        CheckpointError: If the file cannot be read, parsed, or validated

    """
    try:
        with open(path) as f:
            data = json.load(f)
        return E2ECheckpoint.from_dict(data)
    except (OSError, json.JSONDecodeError) as e:
        raise CheckpointError(f"Failed to load checkpoint from {path}: {e}") from e


def load_checkpoint(path: Path) -> E2ECheckpoint:
    """Load checkpoint from file, falling back to .bak on parse/validation failure.

    If the primary ``checkpoint.json`` cannot be read or fails JSON parsing or
    Pydantic validation, the loader tries ``checkpoint.json.bak`` (written by
    the most recent successful ``save_checkpoint`` call).  A structured warning
    is emitted when the fallback is used so operators know to investigate.

    Args:
        path: Path to checkpoint file (primary)

    Returns:
        Loaded E2ECheckpoint (from primary or .bak)

    Raises:
        CheckpointError: If primary file doesn't exist AND no .bak is available,
            or if both primary and .bak fail to load

    """
    if not path.exists():
        raise CheckpointError(f"Checkpoint file not found: {path}")

    try:
        return _load_checkpoint_from_path(path)
    except CheckpointError as primary_err:
        bak_path = path.with_suffix(".json.bak")
        if not bak_path.exists():
            raise

        logger.warning(
            "Primary checkpoint failed to load; falling back to backup",
            extra={
                "checkpoint_path": str(path),
                "backup_path": str(bak_path),
                "primary_error": str(primary_err),
                "fallback": True,
            },
        )
        try:
            return _load_checkpoint_from_path(bak_path)
        except CheckpointError as bak_err:
            raise CheckpointError(
                f"Both primary checkpoint ({path}) and backup ({bak_path}) failed to load. "
                f"Primary error: {primary_err}. Backup error: {bak_err}"
            ) from bak_err


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


def _should_reset_run(
    checkpoint: E2ECheckpoint,
    tier_id: str,
    subtest_id: str,
    run_num: int,
    run_state_str: str,
    from_index: int,
    state_index: dict[str, int],
    run_filter: list[int] | None,
    status_filter: list[str] | None,
) -> bool:
    """Determine whether a single run qualifies for reset.

    Args:
        checkpoint: The experiment checkpoint
        tier_id: Tier identifier string
        subtest_id: Subtest identifier string
        run_num: Run number (1-based)
        run_state_str: Current run state string
        from_index: Target state index to reset from
        state_index: Mapping of state name to sequence index
        run_filter: If set, only reset these run numbers
        status_filter: If set, only reset runs with these statuses

    Returns:
        True if the run should be reset.

    """
    if run_filter and run_num not in run_filter:
        return False

    if status_filter:
        run_status = checkpoint.get_run_status(tier_id, subtest_id, run_num)
        if run_status not in status_filter:
            return False

    # Terminal states (failed, rate_limited) are not in the normal sequence
    # (index == -1). If they passed status_filter, reset them.
    current_index = state_index.get(run_state_str, -1)
    return current_index >= from_index or (current_index == -1 and bool(status_filter))


def _reset_subtest_runs(
    checkpoint: E2ECheckpoint,
    tier_id: str,
    subtest_id: str,
    runs: dict[str, str],
    from_index: int,
    state_index: dict[str, int],
    run_filter: list[int] | None,
    status_filter: list[str] | None,
) -> int:
    """Reset qualifying runs within a single subtest.

    Args:
        checkpoint: The experiment checkpoint (mutated in place)
        tier_id: Tier identifier string
        subtest_id: Subtest identifier string
        runs: Mapping of run_num_str -> run_state_str for this subtest
        from_index: Target state index threshold
        state_index: Mapping of state name to sequence index
        run_filter: If set, only reset these run numbers
        status_filter: If set, only reset runs with these statuses

    Returns:
        Count of runs reset in this subtest.

    """
    count = 0
    for run_num_str, run_state_str in runs.items():
        run_num = int(run_num_str)
        if _should_reset_run(
            checkpoint,
            tier_id,
            subtest_id,
            run_num,
            run_state_str,
            from_index,
            state_index,
            run_filter,
            status_filter,
        ):
            checkpoint.run_states[tier_id][subtest_id][run_num_str] = "pending"
            checkpoint.unmark_run_completed(tier_id, subtest_id, run_num)
            count += 1
    return count


def reset_runs_for_from_state(
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
            n = _reset_subtest_runs(
                checkpoint,
                tier_id,
                subtest_id,
                runs,
                from_index,
                state_index,
                run_filter,
                status_filter,
            )
            if n:
                reset_count += n
                affected_tiers.add(tier_id)
                affected_subtests.add((tier_id, subtest_id))

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
