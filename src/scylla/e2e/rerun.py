"""Re-run agents for failed, never-run, or incomplete runs.

This module scans an experiment directory and identifies runs that need
agent re-execution. It handles multiple categories:
1. Complete - Agent succeeded, judge succeeded, run_result.json exists
2. Agent completed, missing results - Agent finished, outputs exist, but run_result.json deleted
3. Agent failed - Agent ran but failed (stderr, no output.txt)
4. Agent partial - Agent started but incomplete (some files exist, incomplete execution)
5. Never started - Run directory doesn't exist at all
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from scylla.e2e.checkpoint import load_checkpoint, save_checkpoint
from scylla.e2e.models import E2ERunResult, ExperimentConfig, TierBaseline, TierID
from scylla.e2e.rerun_base import load_rerun_context, print_dry_run_summary
from scylla.e2e.subtest_executor import SubTestExecutor, _commit_test_config
from scylla.e2e.tier_manager import TierManager
from scylla.e2e.workspace_manager import WorkspaceManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    """Status of a run in the experiment."""

    COMPLETED = "completed"  # Agent + judge + run_result.json all exist
    MISSING = "missing"  # Run directory doesn't exist (never started)
    FAILED = "failed"  # Agent ran but failed (stderr, no valid output)
    PARTIAL = "partial"  # Agent started but incomplete
    RESULTS = "results"  # Agent finished, but run_result.json or agent/result.json missing


class RerunStats(BaseModel):
    """Statistics from rerun process."""

    total_expected_runs: int = 0
    completed: int = 0
    results: int = 0
    failed: int = 0
    partial: int = 0
    missing: int = 0
    runs_rerun_success: int = 0
    runs_rerun_failed: int = 0
    runs_regenerated: int = 0
    runs_skipped_by_filter: int = 0

    def print_summary(self) -> None:
        """Print a summary of rerun statistics."""
        print("\n" + "=" * 70)  # noqa: T201
        print("RUN STATUS CLASSIFICATION")  # noqa: T201
        print("=" * 70)  # noqa: T201
        print(f"Total expected runs:     {self.total_expected_runs}")  # noqa: T201
        print(f"  ✓ completed:           {self.completed}")  # noqa: T201
        print(f"  ⚠ results:             {self.results}")  # noqa: T201
        print(f"  ✗ failed:              {self.failed}")  # noqa: T201
        print(f"  ⋯ partial:             {self.partial}")  # noqa: T201
        print(f"  ○ missing:             {self.missing}")  # noqa: T201
        print(f"  - skipped (filter):    {self.runs_skipped_by_filter}")  # noqa: T201
        print()  # noqa: T201
        print("RERUN RESULTS")  # noqa: T201
        print("=" * 70)  # noqa: T201
        print(f"Successfully rerun:      {self.runs_rerun_success}")  # noqa: T201
        print(f"Failed rerun:            {self.runs_rerun_failed}")  # noqa: T201
        print(f"Regenerated:             {self.runs_regenerated}")  # noqa: T201
        print("=" * 70)  # noqa: T201


class RunToRerun(BaseModel):
    """A single run that needs re-running."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tier_id: str  # e.g., "T0"
    subtest_id: str  # e.g., "00"
    run_number: int  # 1-based
    run_dir: Path  # Full path to run_NN/ directory
    status: RunStatus  # Current status
    reason: str  # Human-readable description


def _classify_run_status(run_dir: Path) -> RunStatus:
    """Classify the status of a run based on what files exist.

    Args:
        run_dir: Path to run directory

    Returns:
        RunStatus classification

    """
    if not run_dir.exists():
        return RunStatus.MISSING

    # Check for key files
    agent_dir = run_dir / "agent"
    agent_output = agent_dir / "output.txt"
    agent_result = agent_dir / "result.json"
    agent_stderr = agent_dir / "stderr.log"
    agent_timing = agent_dir / "timing.json"
    agent_command_log = agent_dir / "command_log.json"
    judge_dir = run_dir / "judge"
    run_result = run_dir / "run_result.json"

    # Completed: agent output + agent result + judge + run_result all exist
    if (
        agent_output.exists()
        and agent_output.stat().st_size > 0
        and agent_result.exists()
        and judge_dir.exists()
        and run_result.exists()
    ):
        return RunStatus.COMPLETED

    # Results: agent finished successfully but run_result.json or agent/result.json missing
    # (can be regenerated from logs without re-running agent)
    if (
        agent_output.exists()
        and agent_output.stat().st_size > 0
        and agent_timing.exists()
        and agent_command_log.exists()
        and (not run_result.exists() or not agent_result.exists())
    ):
        return RunStatus.RESULTS

    # Failed: stderr exists but no valid output
    if agent_stderr.exists() and (not agent_output.exists() or agent_output.stat().st_size == 0):
        return RunStatus.FAILED

    # Partial: some agent files exist but incomplete
    if agent_dir.exists() and (
        not agent_output.exists() or not agent_timing.exists() or not agent_command_log.exists()
    ):
        return RunStatus.PARTIAL

    # Default to missing if we can't determine
    return RunStatus.MISSING


def scan_runs_needing_rerun(  # noqa: C901  # experiment rerun with many retry/skip conditions
    experiment_dir: Path,
    config: ExperimentConfig,
    tier_manager: TierManager,
    tier_filter: list[str] | None = None,
    subtest_filter: list[str] | None = None,
    run_filter: list[int] | None = None,
    status_filter: list[RunStatus] | None = None,
    stats: RerunStats | None = None,
) -> dict[RunStatus, list[RunToRerun]]:
    """Scan experiment directory and classify runs by status.

    Args:
        experiment_dir: Path to experiment directory
        config: Experiment configuration
        tier_manager: TierManager instance
        tier_filter: Only process these tiers (e.g., ["T0", "T1"])
        subtest_filter: Only process these subtests (e.g., ["00", "01"])
        run_filter: Only process these run numbers (e.g., [1, 3, 5])
        status_filter: Only include runs with these statuses
        stats: RerunStats instance to update (optional)

    Returns:
        Dictionary mapping RunStatus to list of RunToRerun instances

    """
    if stats is None:
        stats = RerunStats()

    runs_by_status: dict[RunStatus, list[RunToRerun]] = {status: [] for status in RunStatus}

    # Iterate over all tiers to run
    for tier_id in config.tiers_to_run:
        tier_str = tier_id.value

        # Apply tier filter
        if tier_filter and tier_str not in tier_filter:
            continue

        # Load tier config to get subtests
        tier_config = tier_manager.load_tier_config(tier_id)

        # Limit subtests if max_subtests is set
        subtests = tier_config.subtests
        if config.max_subtests is not None:
            subtests = subtests[: config.max_subtests]

        # Iterate over all subtests
        for subtest in subtests:
            subtest_id = subtest.id

            # Apply subtest filter
            if subtest_filter and subtest_id not in subtest_filter:
                continue

            subtest_dir = experiment_dir / tier_str / subtest_id

            # Iterate over all expected runs
            for run_number in range(1, config.runs_per_subtest + 1):
                # Apply run filter
                if run_filter and run_number not in run_filter:
                    stats.runs_skipped_by_filter += 1
                    continue

                stats.total_expected_runs += 1
                run_dir = subtest_dir / f"run_{run_number:02d}"

                # Classify run status
                status = _classify_run_status(run_dir)

                # Update stats
                if status == RunStatus.COMPLETED:
                    stats.completed += 1
                elif status == RunStatus.RESULTS:
                    stats.results += 1
                elif status == RunStatus.FAILED:
                    stats.failed += 1
                elif status == RunStatus.PARTIAL:
                    stats.partial += 1
                elif status == RunStatus.MISSING:
                    stats.missing += 1

                # Apply status filter
                if status_filter and status not in status_filter:
                    continue

                # Create human-readable reason
                reason_map = {
                    RunStatus.COMPLETED: "Completed (no action needed)",
                    RunStatus.RESULTS: "Agent finished, missing result files",
                    RunStatus.FAILED: "Agent ran but failed",
                    RunStatus.PARTIAL: "Agent started but incomplete",
                    RunStatus.MISSING: "Run never started",
                }

                runs_by_status[status].append(
                    RunToRerun(
                        tier_id=tier_str,
                        subtest_id=subtest_id,
                        run_number=run_number,
                        run_dir=run_dir,
                        status=status,
                        reason=reason_map[status],
                    )
                )

    return runs_by_status


def _archive_existing_run_dir(run_info: RunToRerun) -> None:
    """Move an existing run directory to .failed/ before re-running.

    Args:
        run_info: Run information containing run_dir and run_number.

    """
    if not run_info.run_dir.exists():
        return
    failed_dir = run_info.run_dir.parent / ".failed"
    failed_dir.mkdir(exist_ok=True)
    failed_run_dir = failed_dir / f"run_{run_info.run_number:02d}"
    counter = 1
    while failed_run_dir.exists():
        failed_run_dir = failed_dir / f"run_{run_info.run_number:02d}_failed_{counter}"
        counter += 1
    logger.info(f"Moving old run to {failed_run_dir}")
    run_info.run_dir.rename(failed_run_dir)


def rerun_single_run(
    run_info: RunToRerun,
    experiment_dir: Path,
    config: ExperimentConfig,
    tier_manager: TierManager,
    workspace_manager: WorkspaceManager,
    baseline: TierBaseline | None,
) -> E2ERunResult | None:
    """Re-run a single agent+judge for a failed/missing run.

    Steps:
    1. If run_dir exists with old data, move to .failed/
    2. Create fresh run_dir
    3. Create workspace (git worktree)
    4. Prepare tier configuration in workspace
    5. Execute agent via SubTestExecutor._execute_single_run()
    6. Return the RunResult (or None on failure)

    Args:
        run_info: Information about the run to re-execute
        experiment_dir: Path to experiment directory
        config: Experiment configuration
        tier_manager: TierManager instance
        workspace_manager: WorkspaceManager instance
        baseline: Baseline configuration from previous tier (or None for T0)

    Returns:
        E2ERunResult if successful, None if failed

    """
    logger.info(
        f"Re-running {run_info.tier_id}/{run_info.subtest_id}/run_{run_info.run_number:02d}: "
        f"{run_info.reason}"
    )

    # Load tier config
    tier_id = TierID.from_string(run_info.tier_id)
    tier_config = tier_manager.load_tier_config(tier_id)

    # Find the subtest config
    subtest_config = None
    for subtest in tier_config.subtests:
        if subtest.id == run_info.subtest_id:
            subtest_config = subtest
            break

    if not subtest_config:
        logger.error(f"Subtest {run_info.subtest_id} not found in tier {run_info.tier_id}")
        return None

    # Create SubTestExecutor instance
    executor = SubTestExecutor(
        config=config,
        tier_manager=tier_manager,
        workspace_manager=workspace_manager,
    )

    # Safety check: don't destroy workspaces for completed or results-only runs
    # These should be handled by regenerate or rerun_judges, not full agent rerun
    if run_info.status in (RunStatus.COMPLETED, RunStatus.RESULTS):
        logger.error(
            f"Refusing to rerun {run_info.tier_id}/{run_info.subtest_id}/"
            f"run_{run_info.run_number:02d}: status is {run_info.status.value}, "
            f"which should not require agent re-execution. "
            f"Use regenerate.py for RESULTS status or rerun_judges.py for COMPLETED status."
        )
        return None

    _archive_existing_run_dir(run_info)

    # Setup run directory and workspace
    run_dir = run_info.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)

    # Create workspace per run in run_N/workspace/
    workspace = run_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # Setup workspace with git worktree
    from scylla.e2e.command_logger import CommandLogger
    from scylla.e2e.workspace_setup import _setup_workspace

    _setup_workspace(
        workspace=workspace,
        command_logger=CommandLogger(log_dir=run_dir),
        tier_id=tier_id,
        subtest_id=subtest_config.id,
        run_number=run_info.run_number,
        base_repo=workspace_manager.base_repo,
        task_commit=config.task_commit,
    )

    # Build merged resources for T5 subtests with inherit_best_from
    merged_resources = None
    if tier_id == TierID.T5 and subtest_config.inherit_best_from and experiment_dir:
        try:
            merged_resources = tier_manager.build_merged_baseline(
                subtest_config.inherit_best_from,
                experiment_dir,
            )
        except ValueError as e:
            logger.error(
                f"Failed to build merged baseline for T5/{subtest_config.id}: {e}. "
                f"Skipping this run - parent tiers must complete first."
            )
            branch_name = f"{tier_id.value}_{subtest_config.id}_run_{run_info.run_number:02d}"
            workspace_manager.cleanup_worktree(workspace, branch_name)
            return None

    # Prepare tier configuration in workspace
    thinking_enabled = config.thinking_mode is not None and config.thinking_mode != "None"
    tier_manager.prepare_workspace(
        workspace=workspace,
        tier_id=tier_id,
        subtest_id=subtest_config.id,
        baseline=baseline,
        merged_resources=merged_resources,
        thinking_enabled=thinking_enabled,
    )

    # Commit test configs so agent sees them as existing state
    _commit_test_config(workspace)

    # Load task prompt
    task_prompt = config.task_prompt_file.read_text()

    # Execute the run using RunContext + build_actions_dict
    from scylla.e2e.stages import RunContext, build_actions_dict

    try:
        ctx = RunContext(
            config=config,
            tier_id=tier_id,
            tier_config=tier_config,
            subtest=subtest_config,
            baseline=baseline,
            run_number=run_info.run_number,
            run_dir=run_dir,
            workspace=workspace,
            task_prompt=task_prompt,
            experiment_dir=experiment_dir,
            tier_manager=tier_manager,
            workspace_manager=workspace_manager,
            adapter=executor.adapter,
        )
        actions = build_actions_dict(ctx)
        for action in actions.values():
            action()
        return ctx.run_result
    except Exception as e:
        logger.error(f"Failed to re-run: {e}")
        return None


def rerun_experiment(  # noqa: C901  # orchestration with many retry/outcome paths
    experiment_dir: Path,
    dry_run: bool = False,
    verbose: bool = False,
    tier_filter: list[str] | None = None,
    subtest_filter: list[str] | None = None,
    run_filter: list[int] | None = None,
    status_filter: list[RunStatus] | None = None,
    skip_regenerate: bool = False,
) -> RerunStats:
    """Re-run agents for failed/missing runs in an experiment.

    Args:
        experiment_dir: Path to experiment directory
        dry_run: Show what would be done without executing
        verbose: Enable verbose logging
        tier_filter: Only process these tiers (e.g., ["T0", "T1"])
        subtest_filter: Only process these subtests (e.g., ["00", "01"])
        run_filter: Only process these run numbers (e.g., [1, 3, 5])
        status_filter: Only rerun runs with these statuses
        skip_regenerate: Skip the regenerate step for agent-complete runs

    Returns:
        RerunStats with summary of what was done

    """
    # Configure logging
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load experiment config and auto-detect tiers directory
    ctx = load_rerun_context(experiment_dir)
    config = ctx.config
    tier_manager = ctx.tier_manager

    # Create workspace manager with centralized repo discovery
    import hashlib

    # Try centralized repos directory first (new layout)
    repos_dir = experiment_dir.parent / "repos"
    repo_uuid = hashlib.sha256(config.task_repo.encode()).hexdigest()[:16]
    centralized_repo = repos_dir / repo_uuid
    legacy_repo = experiment_dir / "repo"

    if centralized_repo.exists() and (centralized_repo / ".git").exists():
        base_repo = centralized_repo
        ws_repos_dir = repos_dir
        logger.info(f"Using centralized base repo: {base_repo}")
    elif legacy_repo.exists():
        base_repo = legacy_repo
        ws_repos_dir = None
        logger.info(f"Using legacy base repo: {base_repo}")
    else:
        raise FileNotFoundError(
            f"Base repository not found at {centralized_repo} or {legacy_repo}. "
            f"Cannot create worktrees for re-runs."
        )

    workspace_manager = WorkspaceManager(
        experiment_dir=experiment_dir,
        repo_url=config.task_repo,
        commit=config.task_commit,
        repos_dir=ws_repos_dir,
    )

    # Mark workspace_manager as setup (base repo already exists)
    workspace_manager._is_setup = True
    workspace_manager.base_repo = base_repo

    # Scan for runs by status
    stats = RerunStats()
    runs_by_status = scan_runs_needing_rerun(
        experiment_dir=experiment_dir,
        config=config,
        tier_manager=tier_manager,
        tier_filter=tier_filter,
        subtest_filter=subtest_filter,
        run_filter=run_filter,
        status_filter=status_filter,
        stats=stats,
    )

    # Print classification summary
    logger.info("Classification complete:")
    logger.info(f"  completed: {stats.completed}")
    logger.info(f"  results:   {stats.results}")
    logger.info(f"  failed:    {stats.failed}")
    logger.info(f"  partial:   {stats.partial}")
    logger.info(f"  missing:   {stats.missing}")

    if dry_run:
        # Use shared dry-run summary formatter
        status_names = {status: status.value.upper().replace("_", " ") for status in RunStatus}
        print_dry_run_summary(runs_by_status, status_names)

        stats.print_summary()
        return stats

    # Load or create checkpoint
    checkpoint_path = experiment_dir / "checkpoint.json"
    if checkpoint_path.exists():
        checkpoint = load_checkpoint(checkpoint_path)
        logger.info(f"Loaded checkpoint: {checkpoint_path}")
    else:
        logger.warning("No checkpoint found - creating new one")
        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash

        checkpoint = E2ECheckpoint(
            experiment_id=config.experiment_id,
            experiment_dir=str(experiment_dir),
            config_hash=compute_config_hash(config),
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="rerunning",
            rate_limit_source=None,
            rate_limit_until=None,
            pause_count=0,
            pid=os.getpid(),
        )

    # Determine which runs to actually rerun
    # 'results' status -> regenerate only (no agent rerun)
    # All other non-completed statuses -> agent rerun
    needs_agent_rerun = []
    needs_regenerate = runs_by_status[RunStatus.RESULTS]

    for status in [
        RunStatus.FAILED,
        RunStatus.PARTIAL,
        RunStatus.MISSING,
    ]:
        needs_agent_rerun.extend(runs_by_status[status])

    logger.info(f"Runs needing agent re-execution: {len(needs_agent_rerun)}")
    logger.info(f"Runs needing regenerate only: {len(needs_regenerate)}")

    # Re-run agents sequentially
    for run_info in needs_agent_rerun:
        # Note: Baseline resolution deferred - reruns currently execute without baseline context.
        # This is acceptable for failed runs as they will be re-evaluated independently.
        baseline = None

        # Execute the rerun
        run_result = rerun_single_run(
            run_info=run_info,
            experiment_dir=experiment_dir,
            config=config,
            tier_manager=tier_manager,
            workspace_manager=workspace_manager,
            baseline=baseline,
        )

        if run_result:
            stats.runs_rerun_success += 1

            # Update checkpoint with pass/fail status based on judge result
            run_status = "passed" if run_result.judge_passed else "failed"
            checkpoint.mark_run_completed(
                tier_id=run_info.tier_id,
                subtest_id=run_info.subtest_id,
                run_number=run_info.run_number,
                status=run_status,
            )
            checkpoint.last_updated_at = datetime.now(timezone.utc).isoformat()
            save_checkpoint(checkpoint, checkpoint_path)
        else:
            stats.runs_rerun_failed += 1
            logger.error(
                f"Failed to rerun {run_info.tier_id}/{run_info.subtest_id}/"
                f"run_{run_info.run_number:02d}"
            )

    # Regenerate result files for runs with 'results' status
    if needs_regenerate:
        logger.info(f"Regenerating result files for {len(needs_regenerate)} runs...")

        for run_info in needs_regenerate:
            agent_dir = run_info.run_dir / "agent"

            # Check if agent/result.json is missing
            if not (agent_dir / "result.json").exists():
                # Import regenerate function from regenerate_agent_results
                import json

                try:
                    # Read existing files
                    stdout = (agent_dir / "stdout.log").read_text()
                    stderr = (agent_dir / "stderr.log").read_text()

                    with open(agent_dir / "command_log.json") as f:
                        cmd_log = json.load(f)

                    # Parse Claude Code JSON output
                    stdout_json = json.loads(stdout.strip())
                    usage = stdout_json.get("usage", {})

                    # Build token_stats structure
                    token_stats = {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                    }

                    # Extract cost and exit code
                    cost_usd = stdout_json.get("total_cost_usd", 0.0)
                    exit_code = cmd_log["commands"][0]["exit_code"]

                    # Build and save result.json
                    result_data = {
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "token_stats": token_stats,
                        "cost_usd": cost_usd,
                        "api_calls": 1,
                    }

                    with open(agent_dir / "result.json", "w") as f:
                        json.dump(result_data, f, indent=2)

                    stats.runs_regenerated += 1
                    logger.debug(f"Regenerated {agent_dir / 'result.json'}")

                except Exception as e:
                    logger.error(f"Failed to regenerate {agent_dir / 'result.json'}: {e}")

            # Handle missing run_result.json when agent/result.json exists
            elif not (run_info.run_dir / "run_result.json").exists():
                import json

                try:
                    # Read agent result
                    with open(agent_dir / "result.json") as f:
                        agent_result = json.load(f)

                    # Read judge result
                    judge_dir = run_info.run_dir / "judge"
                    with open(judge_dir / "result.json") as f:
                        judge_result = json.load(f)

                    # Read agent timing
                    with open(agent_dir / "timing.json") as f:
                        agent_timing = json.load(f)

                    # Sum judge timings from all judge_NN directories
                    judge_duration_total = 0.0
                    for judge_subdir in sorted(judge_dir.glob("judge_*")):
                        timing_file = judge_subdir / "timing.json"
                        if timing_file.exists():
                            with open(timing_file) as f:
                                judge_timing = json.load(f)
                                judge_duration_total += judge_timing.get(
                                    "judge_duration_seconds", 0.0
                                )

                    # Build judges array from judge_NN directories
                    judges = []
                    for judge_subdir in sorted(judge_dir.glob("judge_*")):
                        judgment_file = judge_subdir / "judgment.json"
                        model_file = judge_subdir / "MODEL.md"

                        if judgment_file.exists() and model_file.exists():
                            # Extract judge number from directory name (judge_01 -> 1)
                            judge_num = int(judge_subdir.name.split("_")[1])

                            # Read judgment
                            with open(judgment_file) as f:
                                judgment = json.load(f)

                            # Extract model from MODEL.md
                            model_md = model_file.read_text()
                            model = "unknown"
                            for line in model_md.split("\n"):
                                if line.startswith("**Model**:"):
                                    model = line.split(":", 1)[1].strip()
                                    break

                            # Build judge entry
                            judge_entry = {
                                "model": model,
                                "score": judgment.get("score", 0.0),
                                "passed": judgment.get("passed", False),
                                "grade": judgment.get("grade", "F"),
                                "reasoning": judgment.get("reasoning", ""),
                                "judge_number": judge_num,
                            }
                            judges.append(judge_entry)

                    # Calculate total duration
                    total_duration = (
                        agent_timing.get("agent_duration_seconds", 0.0) + judge_duration_total
                    )

                    # Build run_result.json
                    token_stats = agent_result.get("token_stats", {})
                    run_result_data = {
                        "run_number": run_info.run_number,
                        "exit_code": agent_result.get("exit_code", 1),
                        "token_stats": token_stats,
                        "tokens_input": (
                            token_stats.get("input_tokens", 0)
                            + token_stats.get("cache_read_tokens", 0)
                        ),
                        "tokens_output": token_stats.get("output_tokens", 0),
                        "cost_usd": agent_result.get("cost_usd", 0.0),
                        "duration_seconds": total_duration,
                        "agent_duration_seconds": agent_timing.get("agent_duration_seconds", 0.0),
                        "judge_duration_seconds": judge_duration_total,
                        "judge_score": judge_result.get("score", 0.0),
                        "judge_passed": judge_result.get("passed", False),
                        "judge_grade": judge_result.get("grade", "F"),
                        "judge_reasoning": judge_result.get("reasoning", ""),
                        "judges": judges,
                        "workspace_path": str(run_info.run_dir / "workspace"),
                        "logs_path": str(run_info.run_dir / "agent"),
                        "command_log_path": str(run_info.run_dir / "agent" / "command_log.json"),
                        "criteria_scores": judge_result.get("criteria_scores") or {},
                    }

                    # Save run_result.json
                    with open(run_info.run_dir / "run_result.json", "w") as f:
                        json.dump(run_result_data, f, indent=2)

                    stats.runs_regenerated += 1
                    logger.debug(f"Regenerated {run_info.run_dir / 'run_result.json'}")

                except Exception as e:
                    logger.error(
                        f"Failed to regenerate {run_info.run_dir / 'run_result.json'}: {e}"
                    )

        logger.info(f"✓ Regenerated {stats.runs_regenerated} result files")

    stats.print_summary()
    return stats
