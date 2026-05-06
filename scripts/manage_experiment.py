#!/usr/bin/env python3
r"""Unified experiment management CLI.

Replaces the following individual scripts:
  - run_e2e_experiment.py  (use: manage_experiment.py run)
  - run_e2e_batch.py       (use: manage_experiment.py run --config <dir>/)
  - rerun_agents.py        (use: manage_experiment.py run --from replay_generated)
  - rerun_judges.py        (use: manage_experiment.py run --from judge_pipeline_run)
  - regenerate_results.py  (use: manage_experiment.py run --from run_finalized)
  - repair_checkpoint.py   (use: manage_experiment.py repair)

All subcommands support --until / --until-tier / --until-experiment for
incremental validation: stop execution at a specific state (inclusive) without
marking the run as failed, enabling resume from that point.

Usage:
    # Run experiment (single test)
    python scripts/manage_experiment.py run \\
        --config tests/fixtures/tests/test-001 \\
        --tiers T0 --runs 1

    # Batch run all tests in a parent dir
    python scripts/manage_experiment.py run \\
        --config tests/fixtures/tests/ --threads 4

    # Batch run specific tests
    python scripts/manage_experiment.py run \\
        --config tests/fixtures/tests/ --tests test-001 test-005

    # Re-run agents (from replay_generated forward)
    python scripts/manage_experiment.py run \\
        --config tests/fixtures/tests/test-001 --from replay_generated \\
        --filter-tier T0 --filter-status failed

    # Re-run judges (from judge_pipeline_run forward)
    python scripts/manage_experiment.py run \\
        --config tests/fixtures/tests/test-001 --from judge_pipeline_run \\
        --filter-tier T0

    # Regenerate reports from existing data
    python scripts/manage_experiment.py run \\
        --config tests/fixtures/tests/test-001 --from run_finalized

    # Repair corrupt checkpoint
    python scripts/manage_experiment.py repair /path/to/checkpoint.json

    # Stop all runs after agent_complete for incremental validation (inclusive)
    python scripts/manage_experiment.py run \\
        --config tests/fixtures/tests/test-001 \\
        --tiers T0 --runs 1 --until agent_complete

    # Subscribe to experiment events from config/defaults.yaml
    python scripts/manage_experiment.py subscribe

    # Subscribe to experiment events from custom config directory
    python scripts/manage_experiment.py subscribe \\
        --config-dir /path/to/project/root
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

# Configure logging with thread-local context (tier/subtest/run)
from scylla.config.constants import DEFAULT_AGENT_MODEL, DEFAULT_JUDGE_MODEL
from scylla.e2e.log_context import ContextFilter

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s [%(levelname)s] [T:%(thread)d]"
        " [%(tier_id)s/%(subtest_id)s/%(run_num)s]"
        " %(name)s: %(message)s"
    ),
    datefmt="%Y-%m-%d %H:%M:%S",
)
for _handler in logging.getLogger().handlers:
    _handler.addFilter(ContextFilter())
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the 'run' subcommand."""
    parser.add_argument(
        "--config",
        action="append",
        type=Path,
        default=None,
        help="Path to test config directory or YAML file (repeatable for batch mode). "
        "When a single directory containing test-* subdirs is given, auto-expands "
        "to batch mode. When specified multiple times, runs all tests in parallel.",
    )
    parser.add_argument("--repo", type=str, help="Task repository URL (default: from test.yaml)")
    parser.add_argument("--commit", type=str, help="Task commit hash (default: from test.yaml)")
    parser.add_argument(
        "--prompt", type=Path, help="Path to task prompt file (default: from test.yaml)"
    )
    parser.add_argument("--experiment-id", type=str, default=None, help="Experiment identifier")
    parser.add_argument(
        "--tiers",
        nargs="+",
        type=str,
        default=["T0", "T1"],
        help="Tiers to run (default: T0 T1)",
    )
    parser.add_argument("--runs", type=int, default=10, help="Runs per sub-test (default: 10)")
    parser.add_argument(
        "--timeout", type=int, default=None, help="Timeout per run in seconds (default: 3600)"
    )
    parser.add_argument("--max-subtests", type=int, default=None, help="Limit sub-tests per tier")
    parser.add_argument(
        "--skip-agent-teams", action="store_true", help="Skip agent teams sub-tests"
    )
    parser.add_argument(
        "--use-containers",
        action="store_true",
        help="Run agents/judges in Docker containers",
    )
    parser.add_argument("--model", type=str, default=DEFAULT_AGENT_MODEL, help="Primary model")
    parser.add_argument(
        "--judge-model", type=str, default=DEFAULT_JUDGE_MODEL, help="Model for judging"
    )
    parser.add_argument(
        "--add-judge",
        action="append",
        nargs="?",
        const=DEFAULT_JUDGE_MODEL,
        metavar="MODEL",
        help="Add additional judge model (use multiple times)",
    )
    parser.add_argument(
        "--thinking",
        choices=["None", "Low", "High", "UltraThink"],
        default="None",
        help="Thinking mode (default: None)",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Path to results directory (default: results)",
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Start fresh, ignoring existing checkpoint"
    )
    parser.add_argument(
        "--until",
        "--until-run",
        dest="until",
        type=str,
        default=None,
        metavar="STATE",
        help="Stop all runs AFTER reaching this RunState (inclusive). "
        "E.g., --until agent_complete executes the agent and stops. "
        "Preserves state for future resume.",
    )
    parser.add_argument(
        "--until-tier",
        type=str,
        default=None,
        metavar="STATE",
        help="Stop each tier AFTER reaching this TierState (inclusive). "
        "Preserves state for future resume.",
    )
    parser.add_argument(
        "--until-experiment",
        type=str,
        default=None,
        metavar="STATE",
        help="Stop the experiment AFTER reaching this ExperimentState (inclusive). "
        "Preserves state for future resume.",
    )
    # --from arguments for re-execution
    parser.add_argument(
        "--from",
        "--from-run",
        dest="from_run",
        type=str,
        default=None,
        metavar="STATE",
        help="Reset runs to PENDING and re-execute from this RunState forward. "
        "E.g., --from replay_generated to re-run agents. "
        "Requires an existing experiment with a checkpoint.",
    )
    parser.add_argument(
        "--from-tier",
        type=str,
        default=None,
        metavar="STATE",
        help="Reset tiers to before this TierState and re-execute.",
    )
    parser.add_argument(
        "--from-experiment",
        type=str,
        default=None,
        metavar="STATE",
        help="Reset experiment to this ExperimentState and re-execute.",
    )
    # Filter arguments for --from
    parser.add_argument(
        "--filter-tier",
        action="append",
        type=str,
        default=None,
        help="Only apply --from to these tiers (repeatable)",
    )
    parser.add_argument(
        "--filter-subtest",
        action="append",
        type=str,
        default=None,
        help="Only apply --from to these subtests (repeatable)",
    )
    parser.add_argument(
        "--filter-run",
        action="append",
        type=int,
        default=None,
        help="Only apply --from to these run numbers (repeatable)",
    )
    parser.add_argument(
        "--filter-status",
        action="append",
        type=str,
        default=None,
        help="Only apply --from to runs with these statuses: passed/failed/agent_complete",
    )
    parser.add_argument(
        "--filter-judge-slot",
        action="append",
        type=int,
        default=None,
        help="Only apply --from to these judge slot numbers (1-indexed). "
        "NOTE: judge-slot-level filtering is not yet implemented in the reset logic; "
        "this argument is accepted but has no effect.",
    )
    # Batch mode arguments
    parser.add_argument(
        "--threads", type=int, default=4, help="Parallel threads for batch mode (default: 4)"
    )
    parser.add_argument(
        "--tests",
        nargs="+",
        type=str,
        default=None,
        help="Filter to specific test IDs (batch mode)",
    )
    # Scheduling arguments
    parser.add_argument(
        "--off-peak",
        action="store_true",
        default=False,
        help="Wait for off-peak API hours before each subtest (avoids 8AM-2PM ET weekdays)",
    )
    # Resource management arguments
    parser.add_argument(
        "--keep-failed-workspaces",
        action="store_true",
        default=False,
        help="Preserve workspaces for failed runs (default: clean up all)",
    )
    parser.add_argument(
        "--max-concurrent-workspaces",
        type=int,
        default=None,
        metavar="N",
        help="Max live workspaces at any time (default: cpu_count * 2)",
    )
    parser.add_argument(
        "--max-concurrent-agents",
        type=int,
        default=None,
        metavar="N",
        help="Max concurrent claude CLI processes (default: min(threads, cpu_count))",
    )
    parser.add_argument(
        "--fail-on-resource-check",
        action="store_true",
        default=False,
        help=(
            "Abort instead of warn when pre-flight RAM/disk are below the "
            "warning thresholds. Critical-threshold breaches always abort."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")


def _find_checkpoint_path(results_dir: Path, experiment_id: str) -> Path | None:
    """Find the most recent checkpoint for an experiment using timestamp-prefixed glob.

    Experiments are stored as ``<results_dir>/<timestamp>-<experiment_id>/``.
    When the caller only knows the experiment_id (no timestamp), we glob for
    ``*-<experiment_id>`` and return the checkpoint from the most-recent match.

    Args:
        results_dir: Base directory that contains experiment subdirectories.
        experiment_id: Bare experiment ID without timestamp prefix.

    Returns:
        Path to checkpoint.json if found, else None.

    """
    pattern = f"*-{experiment_id}"
    matching_dirs = sorted(
        [d for d in results_dir.glob(pattern) if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    for exp_dir in matching_dirs:
        cp = exp_dir / "checkpoint.json"
        if cp.exists():
            return cp
    return None


def _checkpoint_has_retryable_runs(checkpoint_path: Path) -> bool:
    """Return True if checkpoint contains any non-completed runs.

    Checks for infra failures or mid-pipeline crashes. Runs in worktree_cleaned
    state (even with bad grades) are NOT considered retryable.
    """
    import json

    try:
        with open(checkpoint_path) as f:
            data = json.load(f)
        for subtests in data.get("run_states", {}).values():
            for runs in subtests.values():
                for state in runs.values():
                    if state != "worktree_cleaned":
                        return True
    except Exception:
        pass
    return False


def _reset_non_completed_runs(checkpoint: Any) -> int:
    """Reset failed/rate-limited runs to pending; cascade tier/subtest for all non-completed runs.

    Failed and rate-limited runs are reset to ``pending`` so they restart from scratch.
    Runs stuck in intermediate states (e.g. ``judge_prompt_built``, ``replay_generated``)
    keep their current state so they resume where they left off, but their containing
    subtest and tier are cascaded to ``pending`` so the run loop re-enters and
    ``advance_to_completion`` picks them up.

    Runs in ``worktree_cleaned`` or ``promoted_to_completed`` state are never reset —
    worktree_cleaned represents completed runs with a valid judge result, and
    promoted_to_completed runs have data safely in completed/ (resetting them would
    cause stage_promote_to_completed to fail with ENOENT since in_progress/ is gone).

    Args:
        checkpoint: Loaded E2ECheckpoint to mutate in-place.

    Returns:
        Number of non-completed runs found (terminal resets + intermediate).

    """
    terminal_states = ("failed", "rate_limited")
    reset_count = 0
    affected_tiers: set[str] = set()
    affected_subtests: set[tuple[str, str]] = set()

    for tier_id, subtests in checkpoint.run_states.items():
        for subtest_id, runs in subtests.items():
            for run_num_str, state in list(runs.items()):
                if state in ("worktree_cleaned", "promoted_to_completed"):
                    continue  # Completed/promoted run — never reset
                # All non-completed runs trigger the tier/subtest cascade
                affected_tiers.add(tier_id)
                affected_subtests.add((tier_id, subtest_id))
                reset_count += 1  # Count ALL non-completed runs
                if state in terminal_states:
                    # Terminal runs restart from scratch
                    runs[run_num_str] = "pending"
                    checkpoint.unmark_run_completed(tier_id, subtest_id, int(run_num_str))
                # else: intermediate state — leave run state as-is; cascade handles re-entry

    for tier_id, subtest_id in affected_subtests:
        checkpoint.set_subtest_state(tier_id, subtest_id, "pending")
    for tier_id in affected_tiers:
        checkpoint.set_tier_state(tier_id, "pending")
    if affected_tiers:
        checkpoint.experiment_state = "tiers_running"

    return reset_count


def _reconcile_checkpoint_with_disk(checkpoint: Any, experiment_dir: Path) -> int:
    """Reconcile checkpoint run_states with on-disk artifacts.

    For each run in the checkpoint, infer the true state from which files
    exist on disk. Updates run_states and completed_runs to match reality.
    Only advances states forward — never regresses a more advanced state.

    Args:
        checkpoint: Loaded E2ECheckpoint to mutate in-place.
        experiment_dir: Path to the experiment directory containing tier subdirs.

    Returns:
        Number of run states corrected.

    """
    from scylla.e2e.agent_runner import _has_valid_agent_result
    from scylla.e2e.judge_runner import _has_valid_judge_result

    # State ordering: later states take priority over earlier ones
    state_order = [
        "pending",
        "dir_structure_created",
        "worktree_created",
        "symlinks_applied",
        "config_committed",
        "baseline_captured",
        "prompt_written",
        "replay_generated",
        "failure_injected",
        "agent_complete",
        "agent_changes_committed",
        "failure_cleared",
        "diff_captured",
        "promoted_to_completed",
        "judge_pipeline_run",
        "judge_prompt_built",
        "judge_complete",
        "run_finalized",
        "report_written",
        "checkpointed",
        "worktree_cleaned",
    ]
    state_rank = {s: i for i, s in enumerate(state_order)}

    corrected = 0

    from scylla.e2e.paths import get_run_dir

    for tier_id, subtests in checkpoint.run_states.items():
        for subtest_id, runs in subtests.items():
            for run_num_str, current_state in list(runs.items()):
                run_num = int(run_num_str)
                # Check completed/ first (promoted runs), then in_progress/ (active runs)
                run_dir = get_run_dir(experiment_dir, tier_id, subtest_id, run_num, completed=True)
                if not run_dir.exists():
                    run_dir = get_run_dir(
                        experiment_dir, tier_id, subtest_id, run_num, completed=False
                    )

                if not run_dir.exists():
                    continue

                # Infer state from disk artifacts
                run_result_file = run_dir / "run_result.json"
                report_md = run_dir / "report.md"
                workspace_dir = run_dir / "workspace"

                inferred_state: str | None = None
                inferred_status: str | None = None

                if run_result_file.exists():
                    if not _has_valid_agent_result(run_dir):
                        continue  # Skip — _reset_invalid_runs will handle
                    try:
                        import json as _json

                        run_result_data = _json.loads(run_result_file.read_text())
                        judge_passed = run_result_data.get("judge_passed", False)
                        inferred_status = "passed" if judge_passed else "failed"
                    except (OSError, ValueError, KeyError):
                        inferred_status = None

                    if report_md.exists() and not workspace_dir.exists():
                        inferred_state = "worktree_cleaned"
                    elif report_md.exists():
                        inferred_state = "report_written"
                    else:
                        inferred_state = "run_finalized"
                elif _has_valid_judge_result(run_dir):
                    if not _has_valid_agent_result(run_dir):
                        continue  # Skip — _reset_invalid_runs will handle
                    inferred_state = "judge_complete"
                elif _has_valid_agent_result(run_dir):
                    inferred_state = "agent_complete"

                if inferred_state is None:
                    continue

                current_rank = state_rank.get(current_state, 0)
                inferred_rank = state_rank.get(inferred_state, 0)

                if inferred_rank > current_rank:
                    checkpoint.set_run_state(tier_id, subtest_id, run_num, inferred_state)
                    if inferred_status is not None:
                        checkpoint.mark_run_completed(
                            tier_id, subtest_id, run_num, status=inferred_status
                        )
                    corrected += 1

    return corrected


def _run_batch(test_dirs: list[Path], args: argparse.Namespace) -> int:
    """Run multiple tests using in-process ThreadPoolExecutor.

    Each test runs run_experiment() directly in its own thread.
    Results are saved incrementally to batch_summary.json.

    Args:
        test_dirs: List of test directories to run
        args: Parsed CLI arguments

    Returns:
        0 on success, 1 on failure

    """
    import threading
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
    from datetime import datetime, timezone

    import yaml

    from scylla.e2e.models import ExperimentConfig, ExperimentState, RunState, TierID, TierState
    from scylla.e2e.runner import request_shutdown, run_experiment
    from scylla.utils.terminal import install_signal_handlers, terminal_guard

    # Install signal handlers on the main thread before spawning worker threads.
    # terminal_guard() inside run_one_test runs in a worker thread and cannot
    # install signal handlers (signal.signal() only works on the main thread).
    install_signal_handlers(request_shutdown)

    # --- Early validation of global args (before spawning threads) ---
    _batch_tier_ids = []
    for _tier_str in args.tiers:
        try:
            _batch_tier_ids.append(TierID[_tier_str])
        except KeyError:
            logger.error(f"Unknown tier: {_tier_str!r}")
            return 1

    _batch_until_run: RunState | None = None
    if args.until:
        try:
            _batch_until_run = RunState(args.until)
        except ValueError:
            logger.error(
                f"Unknown --until state: {args.until!r}. "
                f"Valid values: {[s.value for s in RunState]}"
            )
            return 1

    _batch_until_tier: TierState | None = None
    if args.until_tier:
        try:
            _batch_until_tier = TierState(args.until_tier)
        except ValueError:
            logger.error(
                f"Unknown --until-tier state: {args.until_tier!r}. "
                f"Valid values: {[s.value for s in TierState]}"
            )
            return 1

    _batch_until_experiment: ExperimentState | None = None
    if args.until_experiment:
        try:
            _batch_until_experiment = ExperimentState(args.until_experiment)
        except ValueError:
            logger.error(
                f"Unknown --until-experiment state: {args.until_experiment!r}. "
                f"Valid values: {[s.value for s in ExperimentState]}"
            )
            return 1

    _batch_from_run: RunState | None = None
    if args.from_run:
        try:
            _batch_from_run = RunState(args.from_run)
        except ValueError:
            logger.error(
                f"Unknown --from state: {args.from_run!r}. "
                f"Valid values: {[s.value for s in RunState]}"
            )
            return 1

    _batch_from_tier: TierState | None = None
    if args.from_tier:
        try:
            _batch_from_tier = TierState(args.from_tier)
        except ValueError:
            logger.error(
                f"Unknown --from-tier state: {args.from_tier!r}. "
                f"Valid values: {[s.value for s in TierState]}"
            )
            return 1

    _batch_from_experiment: ExperimentState | None = None
    if args.from_experiment:
        try:
            _batch_from_experiment = ExperimentState(args.from_experiment)
        except ValueError:
            logger.error(
                f"Unknown --from-experiment state: {args.from_experiment!r}. "
                f"Valid values: {[s.value for s in ExperimentState]}"
            )
            return 1
    # --- End early validation ---

    # Validate all models upfront before spawning threads
    from scylla.config.constants import normalize_model_id
    from scylla.e2e.model_validation import validate_model

    _batch_model_id = normalize_model_id(args.model)
    _batch_judge_model_id = normalize_model_id(args.judge_model)
    _batch_judge_models_list = [_batch_judge_model_id]
    if args.add_judge:
        for _extra_judge in args.add_judge:
            _resolved = normalize_model_id(_extra_judge) if _extra_judge else _extra_judge
            if _resolved and _resolved not in _batch_judge_models_list:
                _batch_judge_models_list.append(_resolved)

    _all_models = [_batch_model_id, *_batch_judge_models_list]
    _invalid_models = [
        m for m in dict.fromkeys(_all_models) if not validate_model(m, max_retries=1, base_delay=5)
    ]
    if _invalid_models:
        logger.error(
            f"Invalid model(s): {', '.join(_invalid_models)}. "
            f"Use full model IDs (e.g., 'claude-sonnet-4-6') or short aliases (e.g., 'sonnet')."
        )
        return 1

    _save_lock = threading.Lock()

    def save_result(result: dict[str, Any]) -> None:
        """Save a single result to batch_summary.json (thread-safe)."""
        import json

        summary_path = args.results_dir / "batch_summary.json"
        tmp_path = args.results_dir / f"batch_summary.json.tmp.{threading.get_ident()}"
        with _save_lock:
            if summary_path.exists():
                try:
                    with open(summary_path) as f:
                        summary = json.load(f)
                except Exception:
                    summary = {"results": []}
            else:
                summary = {"results": []}
            summary["results"].append(result)
            with open(tmp_path, "w") as f:
                json.dump(summary, f, indent=2)
            tmp_path.rename(summary_path)

    def run_one_test(test_dir: Path) -> dict[str, Any]:
        """Run a single test and return result dict."""
        test_id = test_dir.name
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            # Load test.yaml
            test_config: dict[str, Any] = {}
            if (test_dir / "test.yaml").exists():
                try:
                    from scylla.e2e.models import TestFixture

                    fixture = TestFixture.from_directory(test_dir)
                    test_config = {
                        "experiment_id": fixture.id,
                        "task_repo": fixture.source_repo,
                        "task_commit": fixture.source_hash,
                        "task_prompt_file": "prompt.md",
                        "timeout_seconds": fixture.timeout_seconds,
                        "language": fixture.language,
                    }
                except Exception:
                    with open(test_dir / "test.yaml") as f:
                        test_config = yaml.safe_load(f) or {}

            task_repo = args.repo or test_config.get("task_repo") or test_config.get("repo")
            task_commit = args.commit or test_config.get("task_commit") or test_config.get("commit")
            experiment_id = args.experiment_id or test_config.get("experiment_id") or test_id
            language = test_config.get("language", "python")

            prompt_file = args.prompt
            if prompt_file is None:
                prompt_name = test_config.get("task_prompt_file", "prompt.md")
                prompt_file = test_dir / prompt_name

            if not task_repo or not task_commit:
                return {
                    "test_id": test_id,
                    "status": "error",
                    "error": "Missing task_repo or task_commit",
                }

            model_id = normalize_model_id(args.model)
            judge_model_id = normalize_model_id(args.judge_model)
            judge_models = [judge_model_id]
            if args.add_judge:
                for extra_judge in args.add_judge:
                    _resolved = normalize_model_id(extra_judge) if extra_judge else extra_judge
                    if _resolved and _resolved not in judge_models:
                        judge_models.append(_resolved)

            tier_ids = _batch_tier_ids
            until_run_state = _batch_until_run
            until_tier_state = _batch_until_tier
            until_experiment_state = _batch_until_experiment
            from_run_state = _batch_from_run
            from_tier_state = _batch_from_tier
            from_experiment_state = _batch_from_experiment

            timeout_seconds = (
                args.timeout
                if args.timeout is not None
                else int(test_config.get("timeout_seconds", 3600))
            )

            config = ExperimentConfig(
                experiment_id=experiment_id,
                task_repo=task_repo,
                task_commit=task_commit,
                task_prompt_file=prompt_file,
                language=language,
                models=[model_id],
                runs_per_subtest=args.runs,
                judge_models=judge_models,
                timeout_seconds=timeout_seconds,
                max_subtests=args.max_subtests,
                skip_agent_teams=args.skip_agent_teams,
                use_containers=args.use_containers,
                thinking_mode=args.thinking or "None",
                tiers_to_run=tier_ids,
                until_run_state=until_run_state,
                until_tier_state=until_tier_state,
                until_experiment_state=until_experiment_state,
                from_run_state=from_run_state,
                from_tier_state=from_tier_state,
                from_experiment_state=from_experiment_state,
                filter_tiers=args.filter_tier,
                filter_subtests=args.filter_subtest,
                filter_runs=args.filter_run,
                filter_statuses=args.filter_status,
                filter_judge_slots=args.filter_judge_slot,
                off_peak=args.off_peak,
                keep_failed_workspaces=args.keep_failed_workspaces,
                max_concurrent_workspaces=args.max_concurrent_workspaces,
                max_concurrent_agents=args.max_concurrent_agents,
                fail_on_resource_check=args.fail_on_resource_check,
            )

            # If --from specified, load existing checkpoint and reset states
            if from_run_state or from_tier_state or from_experiment_state:
                from scylla.e2e.checkpoint import (
                    load_checkpoint,
                    reset_experiment_for_from_state,
                    reset_runs_for_from_state,
                    reset_tiers_for_from_state,
                    save_checkpoint,
                )

                checkpoint_path = args.results_dir / experiment_id / "checkpoint.json"
                if checkpoint_path.exists():
                    checkpoint = load_checkpoint(checkpoint_path)
                    reset_count = 0
                    if from_run_state:
                        reset_count += reset_runs_for_from_state(
                            checkpoint,
                            from_run_state.value,
                            tier_filter=args.filter_tier,
                            subtest_filter=args.filter_subtest,
                            run_filter=args.filter_run,
                            status_filter=args.filter_status,
                        )
                    if from_tier_state:
                        reset_count += reset_tiers_for_from_state(
                            checkpoint,
                            from_tier_state.value,
                            tier_filter=args.filter_tier,
                        )
                    if from_experiment_state:
                        reset_count += reset_experiment_for_from_state(
                            checkpoint,
                            from_experiment_state.value,
                        )
                    save_checkpoint(checkpoint, checkpoint_path)
                    logger.info(f"[{test_id}] Reset {reset_count} items for --from. Resuming...")
                else:
                    logger.warning(
                        f"[{test_id}] --from specified but no checkpoint at {checkpoint_path}; "
                        "starting fresh"
                    )

            # Always reconcile and reset infra failures before re-running
            from scylla.e2e.checkpoint import (
                load_checkpoint as _load_cp,
            )
            from scylla.e2e.checkpoint import (
                save_checkpoint as _save_cp,
            )

            _cp_path = _find_checkpoint_path(args.results_dir, experiment_id)
            if _cp_path is not None:
                _cp = _load_cp(_cp_path)
                _exp_dir = Path(_cp.experiment_dir)
                # Step 1: Reconcile checkpoint with disk state
                _reconcile_count = _reconcile_checkpoint_with_disk(_cp, _exp_dir)
                if _reconcile_count > 0:
                    logger.info(f"[{test_id}] reconciled {_reconcile_count} run state(s) with disk")
                # Step 2: Reset non-completed runs (infra failures and mid-pipeline crashes)
                _reset_count = _reset_non_completed_runs(_cp)
                if _reconcile_count > 0 or _reset_count > 0:
                    _save_cp(_cp, _cp_path)
                    logger.info(f"[{test_id}] reset {_reset_count} non-completed run(s) for retry")

            with terminal_guard():
                results = run_experiment(
                    config=config,
                    tiers_dir=test_dir,
                    results_dir=args.results_dir,
                    fresh=args.fresh,
                    resource_manager=batch_resource_manager,
                )

            status = "success" if results else "error"
            result = {"test_id": test_id, "status": status, "started_at": started_at}
        except Exception as e:
            logger.error(f"Test {test_id} failed with exception: {e}")
            result = {
                "test_id": test_id,
                "status": "error",
                "error": str(e),
                "started_at": started_at,
            }

        save_result(result)
        return result

    args.results_dir.mkdir(parents=True, exist_ok=True)

    # Load existing batch_summary to skip already-completed tests
    completed_ids: set[str] = set()
    if not args.fresh:
        import json

        summary_path = args.results_dir / "batch_summary.json"
        if summary_path.exists():
            try:
                with open(summary_path) as f:
                    summary = json.load(f)
                # Build last-entry-per-test (last entry in list wins)
                last_by_test: dict[str, dict[str, Any]] = {}
                for r in summary.get("results", []):
                    last_by_test[r["test_id"]] = r

                for test_id, r in last_by_test.items():
                    if r.get("status") == "error":
                        continue  # Batch-level errors always re-run
                    # Check checkpoint for infra failures or mid-pipeline crashes
                    cp_path = _find_checkpoint_path(args.results_dir, test_id)
                    if cp_path is not None and _checkpoint_has_retryable_runs(cp_path):
                        continue  # Has infra failures or mid-pipeline crashes
                    # If --max-subtests was specified, check whether the checkpoint
                    # has fewer subtests than requested. If so, re-run to expand.
                    if args.max_subtests is not None:
                        result_dir = r.get("result_dir")
                        if not result_dir:
                            continue  # Cannot verify subtest count; don't mark completed
                        cp_path = Path(result_dir) / "checkpoint.json"
                        try:
                            with open(cp_path) as cp_f:
                                cp = json.load(cp_f)
                            subtest_states = cp.get("subtest_states", {})
                            needs_expansion = False
                            for tier_subtests in subtest_states.values():
                                if len(tier_subtests) < args.max_subtests:
                                    needs_expansion = True
                                    break
                            if needs_expansion:
                                continue
                        except Exception:
                            pass
                    completed_ids.add(test_id)
            except Exception:
                pass

    # Apply --tests filter
    if args.tests:
        test_dirs = [d for d in test_dirs if d.name in args.tests]

    # Skip already-completed tests
    to_run = [d for d in test_dirs if d.name not in completed_ids]

    if not to_run:
        logger.info("All tests already completed in batch. Nothing to run.")
        return 0

    logger.info(f"Batch mode: running {len(to_run)} tests with {args.threads} threads")

    # Create shared ResourceManager for all experiments in this batch.
    # Passed to each run_experiment() so all threads share the same semaphores.
    from scylla.e2e.resource_manager import ResourceManager

    batch_resource_manager = ResourceManager(
        max_workspaces=args.max_concurrent_workspaces,
        max_agents=args.max_concurrent_agents,
        threads=args.threads,
    )

    failed_count = 0

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(run_one_test, d): d for d in to_run}
        # Poll with timeout so shutdown can interrupt blocking waits
        pending = set(futures.keys())
        while pending:
            from scylla.e2e.runner import is_shutdown_requested

            if is_shutdown_requested():
                logger.warning("Shutdown requested, cancelling remaining batch tests...")
                for pending_future in pending:
                    pending_future.cancel()
                break

            done, pending = wait(pending, timeout=2.0, return_when=FIRST_COMPLETED)
            for future in done:
                test_dir = futures[future]
                try:
                    result = future.result(timeout=0)
                    if result.get("status") != "success":
                        failed_count += 1
                        logger.warning(
                            f"Test {test_dir.name} completed with status: {result['status']}"
                        )
                    else:
                        logger.info(f"Test {test_dir.name} completed successfully")
                except Exception as e:
                    logger.error(f"Test {test_dir.name} raised exception: {e}")
                    failed_count += 1

    total = len(to_run)
    passed = total - failed_count
    logger.info(f"Batch complete: {passed}/{total} tests succeeded")

    return 0 if failed_count == 0 else 1


def cmd_run(args: argparse.Namespace) -> int:  # CLI dispatch with many command branches
    """Execute the 'run' subcommand (single test or batch mode)."""
    import yaml

    from scylla.e2e.models import ExperimentConfig, ExperimentState, RunState, TierID, TierState
    from scylla.e2e.runner import request_shutdown, run_experiment
    from scylla.utils.terminal import terminal_guard

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    # Resolve configs list
    configs: list[Path] = args.config or [Path("tests/claude-code/shared")]

    # Auto-expand: if a single path is a parent of test-* dirs, discover batch
    if len(configs) == 1 and configs[0].is_dir():
        parent = configs[0]
        test_dirs = sorted(
            d for d in parent.glob("test-*") if d.is_dir() and d.name != "test-config-loader"
        )
        if test_dirs:
            # This is a parent dir containing test-* subdirs → batch mode
            return _run_batch(test_dirs, args)

    # Multiple configs → batch mode
    if len(configs) > 1:
        return _run_batch(configs, args)

    # Single config → existing single-test behavior
    tiers_dir = configs[0]

    # Check that the config path exists before proceeding
    if not tiers_dir.exists():
        logger.error(f"Config path does not exist: {tiers_dir}")
        return 1

    # Load test.yaml defaults if present
    test_config: dict[str, Any] = {}
    if tiers_dir and (tiers_dir / "test.yaml").exists():
        try:
            from scylla.e2e.models import TestFixture

            fixture = TestFixture.from_directory(tiers_dir)
            test_config = {
                "experiment_id": fixture.id,
                "task_repo": fixture.source_repo,
                "task_commit": fixture.source_hash,
                "task_prompt_file": "prompt.md",
                "timeout_seconds": fixture.timeout_seconds,
                "language": fixture.language,
            }
        except Exception:
            with open(tiers_dir / "test.yaml") as f:
                raw = yaml.safe_load(f) or {}
            test_config = raw

    # Load YAML config file if provided (single file path)
    yaml_config: dict[str, Any] = {}
    if tiers_dir and tiers_dir.is_file() and tiers_dir.suffix in (".yaml", ".yml"):
        with open(tiers_dir) as f:
            yaml_config = yaml.safe_load(f) or {}
        tiers_dir = tiers_dir.parent

    # Merge: CLI overrides yaml_config overrides test_config
    merged = {**test_config, **yaml_config}

    task_repo = args.repo or merged.get("task_repo") or merged.get("repo")
    task_commit = args.commit or merged.get("task_commit") or merged.get("commit")
    experiment_id = args.experiment_id or merged.get("experiment_id") or "experiment"
    language = merged.get("language", "python")

    # Resolve prompt file
    prompt_file = args.prompt
    if prompt_file is None:
        prompt_name = merged.get("task_prompt_file", "prompt.md")
        prompt_file = tiers_dir / prompt_name

    if not task_repo:
        logger.error("--repo is required (or set in test.yaml)")
        return 1
    if not task_commit:
        logger.error("--commit is required (or set in test.yaml)")
        return 1

    from scylla.config.constants import normalize_model_id
    from scylla.e2e.model_validation import validate_model

    model_id = normalize_model_id(args.model)
    judge_model_id = normalize_model_id(args.judge_model)
    judge_models = [judge_model_id]
    if args.add_judge:
        for extra_judge in args.add_judge:
            _resolved = normalize_model_id(extra_judge) if extra_judge else extra_judge
            if _resolved and _resolved not in judge_models:
                judge_models.append(_resolved)

    # Validate all models upfront before starting any work
    all_models_to_validate = [model_id, *judge_models]
    invalid_models = [
        m
        for m in dict.fromkeys(all_models_to_validate)
        if not validate_model(m, max_retries=1, base_delay=5)
    ]
    if invalid_models:
        logger.error(
            f"Invalid model(s): {', '.join(invalid_models)}. "
            f"Use full model IDs (e.g., 'claude-sonnet-4-6') or short aliases (e.g., 'sonnet')."
        )
        return 1

    # Resolve tiers
    tier_ids = []
    for tier_str in args.tiers:
        try:
            tier_ids.append(TierID[tier_str])
        except KeyError:
            logger.error(f"Unknown tier: {tier_str!r}")
            return 1

    # Parse --until / --until-run state
    until_run_state: RunState | None = None
    if args.until:
        try:
            until_run_state = RunState(args.until)
        except ValueError:
            logger.error(
                f"Unknown --until state: {args.until!r}. "
                f"Valid values: {[s.value for s in RunState]}"
            )
            return 1

    # Parse --until-tier state
    until_tier_state: TierState | None = None
    if args.until_tier:
        try:
            until_tier_state = TierState(args.until_tier)
        except ValueError:
            logger.error(
                f"Unknown --until-tier state: {args.until_tier!r}. "
                f"Valid values: {[s.value for s in TierState]}"
            )
            return 1

    # Parse --until-experiment state
    until_experiment_state: ExperimentState | None = None
    if args.until_experiment:
        try:
            until_experiment_state = ExperimentState(args.until_experiment)
        except ValueError:
            logger.error(
                f"Unknown --until-experiment state: {args.until_experiment!r}. "
                f"Valid values: {[s.value for s in ExperimentState]}"
            )
            return 1

    # Parse --from state
    from_run_state: RunState | None = None
    if args.from_run:
        try:
            from_run_state = RunState(args.from_run)
        except ValueError:
            logger.error(
                f"Unknown --from state: {args.from_run!r}. "
                f"Valid values: {[s.value for s in RunState]}"
            )
            return 1

    from_tier_state: TierState | None = None
    if args.from_tier:
        try:
            from_tier_state = TierState(args.from_tier)
        except ValueError:
            logger.error(
                f"Unknown --from-tier state: {args.from_tier!r}. "
                f"Valid values: {[s.value for s in TierState]}"
            )
            return 1

    from_experiment_state: ExperimentState | None = None
    if args.from_experiment:
        try:
            from_experiment_state = ExperimentState(args.from_experiment)
        except ValueError:
            logger.error(
                f"Unknown --from-experiment state: {args.from_experiment!r}. "
                f"Valid values: {[s.value for s in ExperimentState]}"
            )
            return 1

    timeout_seconds = (
        args.timeout if args.timeout is not None else int(merged.get("timeout_seconds", 3600))
    )

    config = ExperimentConfig(
        experiment_id=experiment_id,
        task_repo=task_repo,
        task_commit=task_commit,
        task_prompt_file=prompt_file,
        language=language,
        models=[model_id],
        runs_per_subtest=args.runs,
        judge_models=judge_models,
        timeout_seconds=timeout_seconds,
        max_subtests=args.max_subtests,
        skip_agent_teams=args.skip_agent_teams,
        use_containers=args.use_containers,
        thinking_mode=args.thinking or "None",
        tiers_to_run=tier_ids,
        until_run_state=until_run_state,
        until_tier_state=until_tier_state,
        until_experiment_state=until_experiment_state,
        from_run_state=from_run_state,
        from_tier_state=from_tier_state,
        from_experiment_state=from_experiment_state,
        filter_tiers=args.filter_tier,
        filter_subtests=args.filter_subtest,
        filter_runs=args.filter_run,
        filter_statuses=args.filter_status,
        filter_judge_slots=args.filter_judge_slot,
        off_peak=args.off_peak,
        keep_failed_workspaces=args.keep_failed_workspaces,
        max_concurrent_workspaces=args.max_concurrent_workspaces,
        max_concurrent_agents=args.max_concurrent_agents,
        fail_on_resource_check=args.fail_on_resource_check,
    )

    # If --from specified, load existing checkpoint and reset states
    if from_run_state or from_tier_state or from_experiment_state:
        from scylla.e2e.checkpoint import (
            load_checkpoint,
            reset_experiment_for_from_state,
            reset_runs_for_from_state,
            reset_tiers_for_from_state,
            save_checkpoint,
        )

        checkpoint_path = _find_checkpoint_path(args.results_dir, experiment_id)
        if checkpoint_path is None:
            logger.error(
                f"--from requires existing experiment with checkpoint for '{experiment_id}'"
            )
            return 1

        checkpoint = load_checkpoint(checkpoint_path)
        reset_count = 0

        if from_run_state:
            reset_count += reset_runs_for_from_state(
                checkpoint,
                from_run_state.value,
                tier_filter=args.filter_tier,
                subtest_filter=args.filter_subtest,
                run_filter=args.filter_run,
                status_filter=args.filter_status,
            )
        if from_tier_state:
            reset_count += reset_tiers_for_from_state(
                checkpoint,
                from_tier_state.value,
                tier_filter=args.filter_tier,
            )
        if from_experiment_state:
            reset_count += reset_experiment_for_from_state(
                checkpoint,
                from_experiment_state.value,
            )

        save_checkpoint(checkpoint, checkpoint_path)
        logger.info(f"Reset {reset_count} items for --from. Resuming execution...")

    # Always reconcile and reset infra failures before running (unless --from was used)
    if not (from_run_state or from_tier_state or from_experiment_state):
        from scylla.e2e.checkpoint import load_checkpoint, save_checkpoint

        checkpoint_path = _find_checkpoint_path(args.results_dir, experiment_id)
        if checkpoint_path is not None:
            checkpoint = load_checkpoint(checkpoint_path)
            exp_dir = Path(checkpoint.experiment_dir)
            # Step 1: Reconcile checkpoint with disk state
            reconcile_count = _reconcile_checkpoint_with_disk(checkpoint, exp_dir)
            if reconcile_count > 0:
                logger.info(f"reconciled {reconcile_count} run state(s) with disk")
            # Step 2: Reset non-completed runs (infra failures and mid-pipeline crashes)
            reset_count = _reset_non_completed_runs(checkpoint)
            if reconcile_count > 0 or reset_count > 0:
                save_checkpoint(checkpoint, checkpoint_path)
                logger.info(f"reset {reset_count} non-completed run(s) for retry")

    try:
        with terminal_guard(request_shutdown):
            results = run_experiment(
                config=config,
                tiers_dir=tiers_dir,
                results_dir=args.results_dir,
                fresh=args.fresh,
            )
    except Exception as e:
        logger.error(f"Experiment failed with exception: {e}")
        return 1

    if results:
        logger.info("Experiment complete")
        return 0
    else:
        logger.error("Experiment failed or returned no results")
        return 1


# ---------------------------------------------------------------------------
# Subcommand: repair
# ---------------------------------------------------------------------------


def _add_repair_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the 'repair' subcommand."""
    parser.add_argument("checkpoint_path", type=Path, help="Path to checkpoint JSON file")


def cmd_repair(args: argparse.Namespace) -> int:
    """Execute the 'repair' subcommand."""
    import json

    from scylla.e2e.checkpoint import load_checkpoint, save_checkpoint

    checkpoint_path = args.checkpoint_path
    if not checkpoint_path.exists():
        logger.error(f"Checkpoint not found: {checkpoint_path}")
        return 1

    logger.info(f"Repairing checkpoint: {checkpoint_path}")

    checkpoint = load_checkpoint(checkpoint_path)
    experiment_dir = Path(checkpoint.experiment_dir)

    from scylla.e2e.paths import get_run_dir

    fixed_count = 0
    for tier_id in checkpoint.run_states:
        for subtest_id in checkpoint.run_states[tier_id]:
            for run_num_str in checkpoint.run_states[tier_id][subtest_id]:
                run_num = int(run_num_str)
                # Check completed/ first, then in_progress/ (run may be in either)
                run_dir = get_run_dir(experiment_dir, tier_id, subtest_id, run_num, completed=True)
                if not run_dir.exists():
                    run_dir = get_run_dir(
                        experiment_dir, tier_id, subtest_id, run_num, completed=False
                    )
                run_result_path = run_dir / "run_result.json"
                if run_result_path.exists():
                    try:
                        result_data = json.loads(run_result_path.read_text())
                        passed = result_data.get("judge_passed", False)
                        status = "passed" if passed else "failed"
                        existing = (
                            checkpoint.completed_runs.get(tier_id, {})
                            .get(subtest_id, {})
                            .get(run_num)
                        )
                        if existing is None:
                            if tier_id not in checkpoint.completed_runs:
                                checkpoint.completed_runs[tier_id] = {}
                            if subtest_id not in checkpoint.completed_runs[tier_id]:
                                checkpoint.completed_runs[tier_id][subtest_id] = {}
                            checkpoint.completed_runs[tier_id][subtest_id][run_num] = status
                            fixed_count += 1
                            logger.info(
                                f"Repaired: {tier_id}/{subtest_id}/run_{run_num:02d} = {status}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Could not repair {tier_id}/{subtest_id}/run_{run_num:02d}: {e}"
                        )

    if fixed_count > 0:
        save_checkpoint(checkpoint, checkpoint_path)
        logger.info(f"Repaired {fixed_count} run(s). Checkpoint saved.")
    else:
        logger.info("No repairs needed.")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: visualize
# ---------------------------------------------------------------------------


def _color(text: str, code: str, enabled: bool) -> str:
    """Wrap text in ANSI escape codes if color is enabled."""
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def _state_color(state: str, enabled: bool) -> str:
    """Color a state string based on semantic meaning."""
    # ANSI color codes
    green = "32"
    red = "31"
    yellow = "33"
    dim = "2"
    terminal_states = {"complete", "passed", "worktree_cleaned", "aggregated"}
    failed_states = {"failed", "interrupted", "rate_limited"}
    pending_states = {"pending", "initializing"}
    if state in terminal_states:
        return _color(state, green, enabled)
    if state in failed_states:
        return _color(state, red, enabled)
    if state in pending_states:
        return _color(state, dim, enabled)
    # in-progress / transitional states
    return _color(state, yellow, enabled)


_RUN_TERMINAL_STATES = frozenset({"worktree_cleaned", "failed", "rate_limited"})


def _derive_run_result(
    checkpoint: E2ECheckpoint,  # type: ignore[name-defined]  # noqa: F821
    tier_id: str,
    subtest_id: str,
    run_num_int: int,
    run_state_raw: str,
) -> str:
    """Derive a human-readable run result from state and completed_runs.

    Returns one of: "passed", "failed", "agent_complete", "in_progress", or "".
    """
    stored: str | None = checkpoint.get_run_status(tier_id, subtest_id, run_num_int)
    if stored is not None:
        return stored
    # Not in completed_runs — infer from run_state
    if run_state_raw in ("pending", ""):
        return ""
    if run_state_raw in _RUN_TERMINAL_STATES:
        # Terminal but not in completed_runs (shouldn't normally happen)
        return run_state_raw
    # Any non-pending, non-terminal state means the run is in progress
    return "in_progress"


def _tier_sort_key(tier_id: str) -> tuple[int, str]:
    """Sort tiers numerically (T0 < T1 < ... < T6)."""
    if len(tier_id) >= 2 and tier_id[0] == "T" and tier_id[1:].isdigit():
        return (int(tier_id[1:]), tier_id)
    return (999, tier_id)


def _format_duration(started: str, ended: str) -> str:
    """Calculate duration between two ISO timestamps, return e.g. '24m23s'."""
    from datetime import datetime, timezone

    try:
        fmt_start = datetime.fromisoformat(started)
        fmt_end = datetime.fromisoformat(ended)
        # Normalize to UTC if no tz
        if fmt_start.tzinfo is None:
            fmt_start = fmt_start.replace(tzinfo=timezone.utc)
        if fmt_end.tzinfo is None:
            fmt_end = fmt_end.replace(tzinfo=timezone.utc)
        delta = int((fmt_end - fmt_start).total_seconds())
        if delta < 0:
            delta = 0
        minutes, seconds = divmod(delta, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h{minutes}m{seconds}s"
        if minutes > 0:
            return f"{minutes}m{seconds}s"
        return f"{seconds}s"
    except Exception:
        return "?"


def _add_visualize_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the 'visualize' subcommand."""
    parser.add_argument(
        "path",
        type=Path,
        help="Path to checkpoint.json or experiment directory",
    )
    parser.add_argument(
        "--format",
        choices=["tree", "table", "json"],
        default="tree",
        dest="output_format",
        help="Output format (default: tree)",
    )
    parser.add_argument(
        "--tier",
        action="append",
        default=None,
        dest="tier",
        help="Filter to specific tier(s) (repeatable, e.g. --tier T0 --tier T1)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Show additional details (timestamps, PID, heartbeat)",
    )
    parser.add_argument(
        "--states-only",
        action="store_true",
        default=False,
        help="Show states-only table: EXP / TIER / SUBTEST / RUN / STATE (no result column)",
    )


def _visualize_tree(
    checkpoint: E2ECheckpoint,  # type: ignore[name-defined]  # noqa: F821
    tier_filter: list[str] | None,
    verbose: bool,
    use_color: bool,
) -> None:
    """Print experiment state as an ASCII tree."""
    exp_state = _state_color(checkpoint.experiment_state, use_color)
    print(f"Experiment: {checkpoint.experiment_id} [{exp_state}]")

    if verbose:
        if checkpoint.started_at:
            duration = ""
            if checkpoint.last_updated_at:
                dur = _format_duration(checkpoint.started_at, checkpoint.last_updated_at)
                duration = f"  Duration: {dur}"
            print(f"  Started: {checkpoint.started_at}{duration}")
        if checkpoint.pid:
            print(f"  PID: {checkpoint.pid}")
        if checkpoint.last_heartbeat:
            print(f"  Heartbeat: {checkpoint.last_heartbeat}")

    tier_ids = sorted(checkpoint.tier_states.keys(), key=_tier_sort_key)
    if tier_filter:
        tier_ids = [t for t in tier_ids if t in tier_filter]

    if not tier_ids:
        print("  (no tiers)")
        return

    for tier_idx, tier_id in enumerate(tier_ids):
        is_last_tier = tier_idx == len(tier_ids) - 1
        tier_prefix = r"  \--" if is_last_tier else "  +--"
        tier_state = _state_color(checkpoint.tier_states.get(tier_id, "pending"), use_color)
        print(f"{tier_prefix} {tier_id} [{tier_state}]")

        subtest_map = checkpoint.subtest_states.get(tier_id, {})
        subtest_ids = sorted(subtest_map.keys())
        subtests_in_run_states = sorted(checkpoint.run_states.get(tier_id, {}).keys())
        all_subtests = sorted(set(subtest_ids) | set(subtests_in_run_states))

        if not all_subtests:
            continue

        tree_cont = "  |   " if not is_last_tier else "      "
        for sub_idx, subtest_id in enumerate(all_subtests):
            is_last_sub = sub_idx == len(all_subtests) - 1
            sub_connector = r"\--" if is_last_sub else "+--"
            sub_state_raw = subtest_map.get(subtest_id, "pending")
            sub_state = _state_color(sub_state_raw, use_color)
            print(f"{tree_cont} {sub_connector} {subtest_id} [{sub_state}]")

            run_map = checkpoint.run_states.get(tier_id, {}).get(subtest_id, {})
            run_nums = sorted(run_map.keys(), key=lambda r: int(r) if r.isdigit() else 0)

            run_cont = f"{tree_cont} |   " if not is_last_sub else f"{tree_cont}     "
            for run_idx, run_num_str in enumerate(run_nums):
                is_last_run = run_idx == len(run_nums) - 1
                run_connector = r"\--" if is_last_run else "+--"
                run_state_raw = run_map[run_num_str]
                run_state = _state_color(run_state_raw, use_color)
                run_num_int = int(run_num_str) if run_num_str.isdigit() else 0
                result = _derive_run_result(
                    checkpoint, tier_id, subtest_id, run_num_int, run_state_raw
                )
                result_str = f" -> {_state_color(result, use_color)}" if result else ""
                run_label = f"run_{int(run_num_str):02d}"
                print(f"{run_cont} {run_connector} {run_label} [{run_state}]{result_str}")


def _visualize_table(
    checkpoint: E2ECheckpoint,  # type: ignore[name-defined]  # noqa: F821
    tier_filter: list[str] | None,
    use_color: bool,
) -> None:
    """Print experiment state as a compact table."""
    print(f"{'TIER':<6}{'SUBTEST':<12}{'RUN':<5}{'STATE':<20}{'RESULT'}")
    print("-" * 53)

    tier_ids = sorted(checkpoint.run_states.keys(), key=_tier_sort_key)
    if tier_filter:
        tier_ids = [t for t in tier_ids if t in tier_filter]

    if not tier_ids:
        # Also check tier_states in case there are tiers with no runs yet
        tier_ids_ts = sorted(checkpoint.tier_states.keys(), key=_tier_sort_key)
        if tier_filter:
            tier_ids_ts = [t for t in tier_ids_ts if t in tier_filter]
        for tier_id in tier_ids_ts:
            tier_state = _state_color(checkpoint.tier_states.get(tier_id, "pending"), use_color)
            print(f"{tier_id:<6}{'':<12}{'':<5}{tier_state:<20}{''}")
        return

    for tier_id in tier_ids:
        subtest_map = checkpoint.run_states.get(tier_id, {})
        for subtest_id in sorted(subtest_map.keys()):
            run_map = subtest_map[subtest_id]
            for run_num_str in sorted(run_map.keys(), key=lambda r: int(r) if r.isdigit() else 0):
                run_state_raw = run_map[run_num_str]
                run_state = _state_color(run_state_raw, use_color)
                run_num_int = int(run_num_str) if run_num_str.isdigit() else 0
                result = _derive_run_result(
                    checkpoint, tier_id, subtest_id, run_num_int, run_state_raw
                )
                print(f"{tier_id:<6}{subtest_id:<12}{run_num_str:<5}{run_state:<20}{result}")


def _visualize_json(
    checkpoint: E2ECheckpoint,  # type: ignore[name-defined]  # noqa: F821
    tier_filter: list[str] | None,
) -> None:
    """Print filtered JSON dump of state fields."""
    import json as _json

    data: dict[str, object] = {
        "experiment_id": checkpoint.experiment_id,
        "experiment_state": checkpoint.experiment_state,
        "started_at": checkpoint.started_at,
        "last_updated_at": checkpoint.last_updated_at,
        "status": checkpoint.status,
    }

    if tier_filter:
        data["tier_states"] = {k: v for k, v in checkpoint.tier_states.items() if k in tier_filter}
        data["subtest_states"] = {
            k: v for k, v in checkpoint.subtest_states.items() if k in tier_filter
        }
        data["run_states"] = {k: v for k, v in checkpoint.run_states.items() if k in tier_filter}
    else:
        data["tier_states"] = checkpoint.tier_states
        data["subtest_states"] = checkpoint.subtest_states
        data["run_states"] = checkpoint.run_states

    print(_json.dumps(data, indent=2))


def _find_checkpoint_paths(path: Path) -> list[Path]:
    """Resolve path to one or more checkpoint.json files.

    Rules:
    - If path is a .json file: use it directly.
    - If path is a directory containing checkpoint.json: single experiment.
    - If path is a directory without checkpoint.json but with subdirectories
      that each contain checkpoint.json: batch/results directory mode.

    Returns:
        Sorted list of checkpoint.json paths found.

    """
    if path.is_file():
        return [path]

    if path.is_dir():
        direct = path / "checkpoint.json"
        if direct.exists():
            return [direct]
        # Batch mode: look for subdirectory checkpoints
        found = sorted(path.glob("*/checkpoint.json"))
        return found

    return []


def _visualize_states_table(
    checkpoints: list[E2ECheckpoint],  # type: ignore[name-defined]  # noqa: F821
    tier_filter: list[str] | None,
    use_color: bool,
) -> None:
    """Print a unified states-only table across one or more checkpoints.

    Columns: EXP | TIER | SUBTEST | RUN | STATE (no RESULT column).
    When a single checkpoint is provided, the EXP column is omitted.
    """
    multi = len(checkpoints) > 1
    if multi:
        print(f"{'EXP':<16}{'TIER':<6}{'SUBTEST':<12}{'RUN':<5}{'STATE'}")
        print("-" * 55)
    else:
        print(f"{'TIER':<6}{'SUBTEST':<12}{'RUN':<5}{'STATE'}")
        print("-" * 33)

    for checkpoint in checkpoints:
        tier_ids = sorted(checkpoint.run_states.keys(), key=_tier_sort_key)
        if tier_filter:
            tier_ids = [t for t in tier_ids if t in tier_filter]

        if not tier_ids:
            # Tiers exist but no runs yet — show tier-level state
            tier_ids_ts = sorted(checkpoint.tier_states.keys(), key=_tier_sort_key)
            if tier_filter:
                tier_ids_ts = [t for t in tier_ids_ts if t in tier_filter]
            for tier_id in tier_ids_ts:
                tier_state = _state_color(checkpoint.tier_states.get(tier_id, "pending"), use_color)
                if multi:
                    exp = checkpoint.experiment_id
                    print(f"{exp:<16}{tier_id:<6}{'':<12}{'':<5}{tier_state}")
                else:
                    print(f"{tier_id:<6}{'':<12}{'':<5}{tier_state}")
            continue

        for tier_id in tier_ids:
            subtest_map = checkpoint.run_states.get(tier_id, {})
            for subtest_id in sorted(subtest_map.keys()):
                run_map = subtest_map[subtest_id]
                for run_num_str in sorted(
                    run_map.keys(), key=lambda r: int(r) if r.isdigit() else 0
                ):
                    run_state = _state_color(run_map[run_num_str], use_color)
                    if multi:
                        exp = checkpoint.experiment_id
                        print(f"{exp:<16}{tier_id:<6}{subtest_id:<12}{run_num_str:<5}{run_state}")
                    else:
                        print(f"{tier_id:<6}{subtest_id:<12}{run_num_str:<5}{run_state}")


def cmd_visualize(args: argparse.Namespace) -> int:  # CLI dispatch with many visualization modes
    """Execute the 'visualize' subcommand."""
    import sys

    from scylla.e2e.checkpoint import load_checkpoint

    path: Path = args.path

    if not path.exists():
        logger.error(f"Path not found: {path}")
        return 1

    checkpoint_paths = _find_checkpoint_paths(path)

    if not checkpoint_paths:
        logger.error(f"No checkpoint.json found at or under: {path}")
        return 1

    use_color = sys.stdout.isatty()
    tier_filter: list[str] | None = args.tier
    any_error = False

    # --states-only: load all checkpoints then render a single unified table
    if args.states_only:
        loaded = []
        for cp_path in checkpoint_paths:
            try:
                loaded.append(load_checkpoint(cp_path))
            except Exception as e:
                logger.error(f"Failed to load checkpoint {cp_path}: {e}")
                any_error = True
        if loaded:
            _visualize_states_table(loaded, tier_filter, use_color)
        return 1 if any_error else 0

    fmt = args.output_format

    for cp_path in checkpoint_paths:
        try:
            checkpoint = load_checkpoint(cp_path)
        except Exception as e:
            logger.error(f"Failed to load checkpoint {cp_path}: {e}")
            any_error = True
            continue

        if fmt == "tree":
            _visualize_tree(checkpoint, tier_filter, args.verbose, use_color)
        elif fmt == "table":
            _visualize_table(checkpoint, tier_filter, use_color)
        elif fmt == "json":
            _visualize_json(checkpoint, tier_filter)

        # Separator between multiple experiments
        if len(checkpoint_paths) > 1:
            print()

    return 1 if any_error else 0


# ---------------------------------------------------------------------------
# Subcommand: subscribe
# ---------------------------------------------------------------------------


def _add_subscribe_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the 'subscribe' subcommand."""
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("."),
        help="Project root directory containing config/defaults.yaml (default: .)",
    )


def cmd_subscribe(args: argparse.Namespace) -> int:
    """Execute the 'subscribe' subcommand.

    Starts a long-running NATS JetStream subscriber that listens for task
    events on the ``hi.tasks.*`` subject hierarchy.  Press Ctrl+C to stop.
    """
    import signal
    import threading

    from scylla.config import ConfigLoader, ConfigurationError

    loader = ConfigLoader(args.config_dir)

    try:
        defaults = loader.load_defaults()
    except ConfigurationError as exc:
        logger.error("Error loading configuration: %s", exc)
        return 1

    nats_config = defaults.nats

    if not nats_config.enabled:
        logger.error(
            "NATS subscription is disabled in config/defaults.yaml "
            "(nats.enabled=false). Set nats.enabled to true or use "
            "NATS_URL env var to enable."
        )
        return 1

    try:
        from scylla.nats import NATSSubscriberThread, create_default_router
    except (ImportError, ModuleNotFoundError):
        logger.error("nats-py is not installed. Install with: pip install 'scylla[nats]'")
        return 1

    # Configure logging from defaults
    log_level = getattr(logging, defaults.logging.level, logging.INFO)
    logging.getLogger().setLevel(log_level)

    router = create_default_router()
    subscriber = NATSSubscriberThread(config=nats_config, handler=router.dispatch)

    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: object) -> None:
        logger.info("Shutdown requested (signal %s)", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info(
        "Subscribing to NATS at %s (stream=%s)",
        nats_config.url,
        nats_config.stream,
    )
    subscriber.start()

    # Block until shutdown signal
    stop_event.wait()

    logger.info("Stopping subscriber...")
    subscriber.stop()
    logger.info("Subscriber stopped.")
    return 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="manage_experiment.py",
        description="Unified experiment management CLI for ProjectScylla E2E testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  run        Run single or batch experiments with optional --from re-execution
  repair     Repair corrupt checkpoint (rebuilds from run_result.json files)
  visualize  Show experiment state from checkpoint
  subscribe  Subscribe to NATS JetStream events from ProjectHermes

Use 'manage_experiment.py <subcommand> --help' for subcommand-specific options.

Equivalence mapping (old → new):
  batch --results-dir X --threads 4
    → run --config tests/fixtures/tests/ --threads 4 --results-dir X
  rerun-agents /exp/ --tier T0 --status failed
    → run --config <test-dir> --results-dir /exp/ --from replay_generated
          --filter-tier T0 --filter-status failed
  rerun-judges /exp/ --tier T0 --judge-slot 1 2
    → run --config <test-dir> --results-dir /exp/ --from judge_pipeline_run
          --filter-tier T0 --filter-judge-slot 1 2
  regenerate /exp/
    → run --config <test-dir> --results-dir /exp/ --from run_finalized
        """,
    )

    subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    subparsers.required = True

    # run subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run single or batch E2E experiments (with optional --from re-execution)",
        description="Run E2E experiments. Supports single test, batch mode (multi-config or "
        "parent dir), and re-execution via --from.",
    )
    _add_run_args(run_parser)

    # repair subcommand (kept as-is)
    repair_parser = subparsers.add_parser(
        "repair",
        help="Repair corrupt checkpoint by rebuilding from run_result.json files",
        description="Fix checkpoints where completed_runs is empty despite having completed runs.",
    )
    _add_repair_args(repair_parser)

    # visualize subcommand
    visualize_parser = subparsers.add_parser(
        "visualize",
        help="Show experiment state from checkpoint",
        description=(
            "Read checkpoint.json and display experiment state hierarchy. "
            "Accepts a checkpoint.json file, an experiment directory, "
            "or a results directory containing multiple experiment subdirectories."
        ),
    )
    _add_visualize_args(visualize_parser)

    # subscribe subcommand
    subscribe_parser = subparsers.add_parser(
        "subscribe",
        help="Subscribe to NATS JetStream events from ProjectHermes",
        description=(
            "Start a long-running subscriber that listens for task events "
            "on the hi.tasks.* subject hierarchy. Press Ctrl+C to stop."
        ),
    )
    _add_subscribe_args(subscribe_parser)

    return parser


def main() -> int:
    """Run the experiment management CLI."""
    parser = build_parser()
    args = parser.parse_args()

    subcommand_map = {
        "run": cmd_run,
        "repair": cmd_repair,
        "visualize": cmd_visualize,
        "subscribe": cmd_subscribe,
    }

    handler = subcommand_map.get(args.subcommand)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
