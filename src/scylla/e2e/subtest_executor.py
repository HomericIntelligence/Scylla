"""Sub-test executor for E2E testing.

This module handles executing individual sub-tests, including
workspace preparation, agent execution, judging, and result aggregation.

This file was decomposed from a 2269-line god class into focused modules:
- parallel_executor.py: Parallel execution and rate limit coordination
- agent_runner.py: Agent execution helpers
- judge_runner.py: Judge execution and consensus
- workspace_setup.py: Workspace management
- subtest_executor.py: Core SubTestExecutor class (this file)

See GitHub Issue #478 for decomposition history.
"""

from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scylla.e2e.llm_judge_models import BuildPipelineResult
    from scylla.e2e.resource_manager import ResourceManager

from scylla.adapters.claude_code import ClaudeCodeAdapter

# Import helpers from decomposed modules
from scylla.e2e.agent_runner import (
    _create_agent_model_md,
    _has_valid_agent_result,
    _load_agent_result,
    _save_agent_result,
)
from scylla.e2e.judge_runner import (
    _compute_judge_consensus,
    _has_valid_judge_result,
    _load_judge_result,
    _run_judge,
    _save_judge_result,
)
from scylla.e2e.log_context import current_tier_id
from scylla.e2e.models import (
    E2ERunResult,
    ExperimentConfig,
    SubTestConfig,
    SubTestResult,
    TierBaseline,
    TierConfig,
    TierID,
    TokenStats,
)
from scylla.e2e.rate_limit import RateLimitError
from scylla.e2e.tier_manager import TierManager
from scylla.e2e.workspace_manager import WorkspaceManager
from scylla.e2e.workspace_setup import (
    _commit_test_config,
    _move_to_failed,
    _setup_workspace,
)
from scylla.metrics.emitter import get_default_emitter
from scylla.utils.tracing import get_tracer

if TYPE_CHECKING:
    from scylla.e2e.parallel_executor import RateLimitCoordinator
    from scylla.persistence.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)
_tracer = get_tracer(__name__)
_emitter = get_default_emitter()

__all__ = [
    "SubTestExecutor",
    "_commit_test_config",
    "_compute_judge_consensus",
    "_create_agent_model_md",
    "_has_valid_agent_result",
    "_has_valid_judge_result",
    "_load_agent_result",
    "_load_judge_result",
    "_move_to_failed",
    "_restore_run_context",
    "_run_judge",
    "_save_agent_result",
    "_save_judge_result",
    "_setup_workspace",
    "aggregate_run_results",
]


def _emit_subtest_metrics(
    tier_id: str,
    subtest_id: str,
    duration_seconds: float,
    outcome: str,
) -> None:
    """Emit subtest duration gauge + outcome counter. Best-effort, never raises."""
    try:
        emitter = get_default_emitter()
        labels = {"tier": tier_id, "subtest": subtest_id}
        emitter.emit_gauge(
            "scylla_subtest_duration_seconds",
            float(duration_seconds),
            labels=labels,
        )
        emitter.emit_counter(
            "scylla_subtest_outcome_total",
            1,
            labels={**labels, "outcome": outcome},
        )
    except Exception as e:  # emitter must never break subtest execution
        logger.debug(f"Subtest metric emission failed (non-fatal): {e}")


def _restore_run_context(ctx: Any, current_state: str) -> None:
    """Restore RunContext fields from disk for resume from intermediate states.

    When resuming from a state past PENDING, earlier stages are skipped,
    so their outputs (agent_result, judge_prompt, etc.) must be reloaded
    from the on-disk artifacts saved during the original run.

    Args:
        ctx: RunContext instance to populate in-place
        current_state: Current run state string from checkpoint

    """
    from scylla.e2e.models import RunState
    from scylla.e2e.paths import get_agent_dir
    from scylla.e2e.state_machine import is_at_or_past_state

    run_state = RunState(current_state)

    # If past REPLAY_GENERATED, agent_result should be available on disk
    past_agent = is_at_or_past_state(run_state, RunState.AGENT_COMPLETE)
    if past_agent and ctx.agent_result is None:
        if _has_valid_agent_result(ctx.run_dir):
            agent_dir = get_agent_dir(ctx.run_dir)
            ctx.agent_result = _load_agent_result(agent_dir)
            agent_timing = agent_dir / "timing.json"
            if agent_timing.exists():
                ctx.agent_duration = json.loads(agent_timing.read_text()).get(
                    "agent_duration_seconds", 0.0
                )
            ctx.agent_ran = False
        else:
            raise RuntimeError(
                f"Resuming run at state '{current_state}' but agent result is "
                f"invalid at {ctx.run_dir} "
                f"— run should have been reset by _reset_invalid_runs()"
            )

    # If past JUDGE_PROMPT_BUILT, the saved judge_prompt.md is the source of truth
    if is_at_or_past_state(run_state, RunState.JUDGE_PROMPT_BUILT) and not ctx.judge_prompt:
        saved_prompt = ctx.run_dir / "judge_prompt.md"
        if saved_prompt.exists():
            ctx.judge_prompt = saved_prompt.read_text()

    # If past JUDGE_COMPLETE, judgment should be available on disk
    if is_at_or_past_state(run_state, RunState.JUDGE_COMPLETE) and ctx.judgment is None:
        _restore_judgment(ctx)

    # If past RUN_FINALIZED, run_result should be available on disk
    if is_at_or_past_state(run_state, RunState.RUN_FINALIZED) and ctx.run_result is None:
        _restore_run_result(ctx, current_state)


def _restore_judgment(ctx: Any) -> None:
    """Restore ctx.judgment from on-disk judge result."""
    from scylla.e2e.judge_runner import _has_valid_judge_result, _load_judge_result
    from scylla.e2e.paths import get_judge_dir

    judge_dir = get_judge_dir(ctx.run_dir)
    if _has_valid_judge_result(ctx.run_dir):
        ctx.judgment = _load_judge_result(judge_dir)
        judge_timing = judge_dir / "timing.json"
        if judge_timing.exists():
            ctx.judge_duration = json.loads(judge_timing.read_text()).get(
                "judge_duration_seconds", 0.0
            )


def _restore_run_result(ctx: Any, current_state: str) -> None:
    """Restore ctx.run_result from on-disk run_result.json."""
    run_result_path = ctx.run_dir / "run_result.json"
    if run_result_path.exists():
        ctx.run_result = _load_run_result(run_result_path)
    else:
        logger.warning(
            "Resuming run at state '%s' but run_result.json missing at %s",
            current_state,
            ctx.run_dir,
        )


def _load_run_result(run_result_path: Path) -> Any:
    """Load E2ERunResult from run_result.json, ignoring extra keys.

    The on-disk run_result.json contains extra keys (process_metrics,
    progress_tracking, changes) that are not part of E2ERunResult.
    We filter to known fields before validation.

    Args:
        run_result_path: Path to run_result.json

    Returns:
        E2ERunResult instance

    """
    from scylla.e2e.models import E2ERunResult

    data = json.loads(run_result_path.read_text())
    known_fields = set(E2ERunResult.model_fields.keys())
    filtered = {k: v for k, v in data.items() if k in known_fields}
    return E2ERunResult.model_validate(filtered)


def _save_pipeline_baseline(results_dir: Path, result: BuildPipelineResult) -> None:
    """Save pipeline baseline result to JSON.

    Args:
        results_dir: Directory to save baseline (e.g., results/T2/01/)
        result: BuildPipelineResult to save

    """
    baseline_path = results_dir / "pipeline_baseline.json"
    baseline_path.write_text(json.dumps(result.model_dump(), indent=2))
    logger.info(f"Saved pipeline baseline to {baseline_path}")


def _load_pipeline_baseline(results_dir: Path) -> BuildPipelineResult | None:
    """Load pipeline baseline result from JSON.

    Args:
        results_dir: Directory containing baseline (e.g., results/T2/01/)

    Returns:
        BuildPipelineResult if file exists, None otherwise

    """
    from scylla.e2e.llm_judge_models import BuildPipelineResult

    baseline_path = results_dir / "pipeline_baseline.json"
    if not baseline_path.exists():
        return None

    try:
        data = json.loads(baseline_path.read_text())
        return BuildPipelineResult(**data)
    except Exception as e:
        logger.warning(f"Failed to load pipeline baseline from {baseline_path}: {e}")
        return None


def aggregate_run_results(
    tier_id: TierID,
    subtest_id: str,
    runs: list[E2ERunResult],
) -> SubTestResult:
    """Aggregate results from multiple runs into a SubTestResult.

    Shared implementation used by both SubTestExecutor and regenerate.

    Args:
        tier_id: The tier identifier
        subtest_id: The sub-test identifier
        runs: List of run results

    Returns:
        SubTestResult with aggregated statistics.

    """
    from functools import reduce

    from scylla.e2e.models import GRADE_ORDER

    if not runs:
        return SubTestResult(
            subtest_id=subtest_id,
            tier_id=tier_id,
            runs=[],
        )

    scores = [r.judge_score for r in runs]
    costs = [r.cost_usd for r in runs]

    pass_count = sum(1 for r in runs if r.judge_passed)
    pass_rate = pass_count / len(runs)

    mean_score = statistics.mean(scores)
    median_score = statistics.median(scores)
    std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0

    # Consistency: 1 - coefficient of variation
    cv = std_dev / mean_score if mean_score > 0 else 1.0
    consistency = max(0.0, 1.0 - cv)

    # Aggregate token stats from all runs
    token_stats = reduce(
        lambda a, b: a + b,
        [r.token_stats for r in runs],
        TokenStats(),
    )

    # Aggregate grades
    grades = [r.judge_grade for r in runs if r.judge_grade]
    grade_distribution: dict[str, int] | None = None
    modal_grade: str | None = None
    min_grade: str | None = None
    max_grade: str | None = None

    if grades:
        # Build distribution
        grade_distribution = {}
        for g in grades:
            grade_distribution[g] = grade_distribution.get(g, 0) + 1

        # Modal grade (most common)
        modal_grade = max(grade_distribution, key=lambda g: grade_distribution.get(g, 0))

        # Grade ordering for min/max (F=worst, S=best)
        grade_indices = [GRADE_ORDER.index(g) for g in grades if g in GRADE_ORDER]
        if grade_indices:
            min_grade = GRADE_ORDER[min(grade_indices)]
            max_grade = GRADE_ORDER[max(grade_indices)]

    return SubTestResult(
        subtest_id=subtest_id,
        tier_id=tier_id,
        runs=runs,
        pass_rate=pass_rate,
        mean_score=mean_score,
        median_score=median_score,
        std_dev_score=std_dev,
        mean_cost=statistics.mean(costs),
        total_cost=sum(costs),
        consistency=consistency,
        token_stats=token_stats,
        grade_distribution=grade_distribution,
        modal_grade=modal_grade,
        min_grade=min_grade,
        max_grade=max_grade,
    )


class SubTestExecutor:
    """Executes sub-tests and aggregates results.

    Handles the complete lifecycle of running a sub-test:
    1. Create workspace (clone repo, checkout commit)
    2. Prepare tier configuration (inheritance + overlay)
    3. Execute agent N times
    4. Judge each run
    5. Aggregate results

    Example:
        >>> executor = SubTestExecutor(config, tier_manager)
        >>> result = executor.run_subtest(
        ...     tier_id=TierID.T2,
        ...     subtest=subtest_config,
        ...     baseline=previous_baseline,
        ...     results_dir=Path("/results/T2/01"),
        ... )

    """

    def __init__(
        self,
        config: ExperimentConfig,
        tier_manager: TierManager,
        workspace_manager: WorkspaceManager,
        adapter: ClaudeCodeAdapter | None = None,
        resource_manager: ResourceManager | None = None,
    ) -> None:
        """Initialize the executor.

        Args:
            config: Experiment configuration
            tier_manager: Tier configuration manager
            workspace_manager: Workspace manager for git worktrees
            adapter: Optional adapter (defaults to ClaudeCodeAdapter)
            resource_manager: Optional resource limiter for concurrency control

        """
        self.config = config
        self.tier_manager = tier_manager
        self.workspace_manager = workspace_manager
        self.adapter = adapter or ClaudeCodeAdapter()
        self._resource_manager = resource_manager

    def run_subtest(
        self,
        tier_id: TierID,
        tier_config: TierConfig,
        subtest: SubTestConfig,
        baseline: TierBaseline | None,
        results_dir: Path,
        checkpoint: E2ECheckpoint | None = None,
        checkpoint_path: Path | None = None,
        coordinator: RateLimitCoordinator | None = None,
        experiment_dir: Path | None = None,
    ) -> SubTestResult:
        """Run a single sub-test N times and aggregate results.

        Creates workspace at subtest level (shared across runs) for efficiency.
        Each run gets its own directory for output.txt, judgment.json, etc.

        Supports checkpoint/resume: skips completed runs and saves after each run.

        Args:
            tier_id: The tier being executed
            tier_config: Tier configuration
            subtest: Sub-test configuration
            baseline: Previous tier's winning baseline (if any)
            results_dir: Directory to store results (subtest directory)
            checkpoint: Optional checkpoint for resume capability
            checkpoint_path: Path to checkpoint file for saving
            coordinator: Optional rate limit coordinator for parallel execution
            experiment_dir: Path to experiment directory (needed for T5 inheritance)

        Returns:
            SubTestResult with aggregated metrics.

        """
        import time as _time

        _subtest_start = _time.monotonic()
        _outcome = "error"
        with _tracer.start_as_current_span(
            "scylla.subtest",
            attributes={
                "scylla.tier_id": tier_id.value,
                "scylla.subtest_id": subtest.id,
                "scylla.experiment_id": self.config.experiment_id,
            },
        ) as _subtest_span:
            try:
                _result = self._run_subtest_body(
                    tier_id=tier_id,
                    tier_config=tier_config,
                    subtest=subtest,
                    baseline=baseline,
                    results_dir=results_dir,
                    checkpoint=checkpoint,
                    checkpoint_path=checkpoint_path,
                    coordinator=coordinator,
                    experiment_dir=experiment_dir,
                )
                _outcome = "pass" if _result.pass_rate > 0 else "fail"
                return _result
            except Exception as _exc:
                _subtest_span.record_exception(_exc)
                raise
            finally:
                _emit_subtest_metrics(
                    tier_id=tier_id.value,
                    subtest_id=subtest.id,
                    duration_seconds=_time.monotonic() - _subtest_start,
                    outcome=_outcome,
                )

    def _run_subtest_body(  # noqa: C901  # orchestration with many retry/outcome paths
        self,
        tier_id: TierID,
        tier_config: TierConfig,
        subtest: SubTestConfig,
        baseline: TierBaseline | None,
        results_dir: Path,
        checkpoint: E2ECheckpoint | None = None,
        checkpoint_path: Path | None = None,
        coordinator: RateLimitCoordinator | None = None,
        experiment_dir: Path | None = None,
    ) -> SubTestResult:
        """Body of :meth:`run_subtest`, wrapped in a tracing span by the caller."""
        from scylla.e2e.models import SubtestState
        from scylla.e2e.stages import RunContext, build_actions_dict
        from scylla.e2e.state_machine import StateMachine
        from scylla.e2e.subtest_state_machine import SubtestStateMachine

        runs: list[E2ERunResult] = []
        results_dir.mkdir(parents=True, exist_ok=True)

        # Load task prompt once
        task_prompt = self.config.task_prompt_file.read_text()

        # Track last workspace for resource manifest
        last_workspace = None

        # Pipeline baseline is shared across runs; stored in RunContext and
        # propagated back to subsequent RunContext instances below.
        pipeline_baseline: BuildPipelineResult | None = None

        # Build subtest state machine if checkpoint is available
        ssm = (
            SubtestStateMachine(
                checkpoint=checkpoint,
                checkpoint_path=checkpoint_path,
            )
            if checkpoint and checkpoint_path
            else None
        )

        def _run_loop() -> None:  # noqa: C901  # run loop with many retry/skip/state paths
            nonlocal last_workspace, pipeline_baseline

            for run_num in range(1, self.config.runs_per_subtest + 1):
                with _tracer.start_as_current_span(
                    "scylla.run",
                    attributes={
                        "scylla.tier_id": tier_id.value,
                        "scylla.subtest_id": subtest.id,
                        "scylla.run_num": run_num,
                        "scylla.experiment_id": self.config.experiment_id,
                    },
                ) as _run_span:
                    try:
                        # Check for shutdown before starting run
                        if coordinator and coordinator.is_shutdown_requested():
                            logger.warning(
                                f"Shutdown requested before run {run_num} of "
                                f"{tier_id.value}/{subtest.id}, stopping..."
                            )
                            break

                        # Check coordinator for pause signal before each run
                        if coordinator:
                            coordinator.check_if_paused()

                        run_dir = results_dir / f"run_{run_num:02d}"
                        workspace = run_dir / "workspace"

                        # Build checkpoint/state-machine objects for this run
                        sm = (
                            StateMachine(
                                checkpoint=checkpoint,
                                checkpoint_path=checkpoint_path,
                            )
                            if checkpoint and checkpoint_path
                            else None
                        )

                        # Skip runs already at or past the --until target state (they are not
                        # terminal but have completed their allowed work for this invocation).
                        if sm and self.config.until_run_state is not None:
                            from scylla.e2e.state_machine import is_at_or_past_state

                            current_run_state = sm.get_state(tier_id.value, subtest.id, run_num)
                            if is_at_or_past_state(current_run_state, self.config.until_run_state):
                                logger.debug(
                                    f"Skipping run {tier_id.value}/{subtest.id}/run_{run_num:02d} "
                                    f"— already at or past --until state: "
                                    f"{self.config.until_run_state.value} "
                                    f"(current: {current_run_state.value})"
                                )
                                continue

                        # Check if already in a terminal state (fully complete or previously failed)
                        if sm and sm.is_complete(tier_id.value, subtest.id, run_num):
                            # Completed runs are promoted to completed/ — check there first
                            if experiment_dir is not None:
                                from scylla.e2e.paths import get_run_dir

                                completed_run_dir = get_run_dir(
                                    experiment_dir,
                                    tier_id.value,
                                    subtest.id,
                                    run_num,
                                    completed=True,
                                )
                                if completed_run_dir.exists():
                                    run_dir = completed_run_dir
                            run_result_file = run_dir / "run_result.json"
                            if run_dir.exists() and run_result_file.exists():
                                from scylla.e2e.rate_limit import validate_run_result

                                is_valid, failure_reason = validate_run_result(run_dir)
                                if not is_valid:
                                    logger.warning(
                                        f"Previously completed run is invalid"
                                        f" ({failure_reason}), re-running..."
                                    )
                                    _move_to_failed(run_dir)
                                    if checkpoint and checkpoint_path:
                                        checkpoint.unmark_run_completed(
                                            tier_id.value, subtest.id, run_num
                                        )
                                        from scylla.persistence.checkpoint import save_checkpoint

                                        save_checkpoint(checkpoint, checkpoint_path)
                                    # Fall through to re-run
                                else:
                                    logger.info(
                                        f"Skipping completed run: "
                                        f"{tier_id.value}/{subtest.id}/run_{run_num:02d}"
                                    )
                                    with open(run_result_file) as f:
                                        report_data = json.load(f)

                                    run_result = E2ERunResult(
                                        run_number=report_data["run_number"],
                                        exit_code=report_data["exit_code"],
                                        token_stats=TokenStats.from_dict(
                                            report_data["token_stats"]
                                        ),
                                        cost_usd=report_data["cost_usd"],
                                        duration_seconds=report_data["duration_seconds"],
                                        agent_duration_seconds=report_data.get(
                                            "agent_duration_seconds", 0.0
                                        ),
                                        judge_duration_seconds=report_data.get(
                                            "judge_duration_seconds", 0.0
                                        ),
                                        judge_score=report_data["judge_score"],
                                        judge_passed=report_data["judge_passed"],
                                        judge_grade=report_data["judge_grade"],
                                        judge_reasoning=report_data["judge_reasoning"],
                                        workspace_path=Path(report_data["workspace_path"]),
                                        logs_path=Path(report_data["logs_path"]),
                                        command_log_path=(
                                            Path(report_data["command_log_path"])
                                            if report_data.get("command_log_path")
                                            else None
                                        ),
                                        criteria_scores=report_data.get("criteria_scores") or {},
                                        baseline_pipeline_summary=report_data.get(
                                            "baseline_pipeline_summary"
                                        ),
                                    )
                                    runs.append(run_result)
                                    last_workspace = workspace
                                    continue

                        # If the run was previously promoted to completed/ (and possibly
                        # had its checkpoint state regressed), the artifacts live in
                        # completed/ even though the state may be as early as
                        # AGENT_COMPLETE.  Prefer the completed/ directory when it
                        # exists so _restore_run_context finds agent/judge artifacts.
                        if sm and experiment_dir is not None:
                            from scylla.e2e.models import RunState
                            from scylla.e2e.state_machine import is_at_or_past_state

                            _cur = sm.get_state(tier_id.value, subtest.id, run_num)
                            if is_at_or_past_state(_cur, RunState.AGENT_COMPLETE):
                                from scylla.e2e.paths import get_run_dir

                                completed_run_dir = get_run_dir(
                                    experiment_dir,
                                    tier_id.value,
                                    subtest.id,
                                    run_num,
                                    completed=True,
                                )
                                if completed_run_dir.exists():
                                    run_dir = completed_run_dir
                                    workspace = run_dir / "workspace"

                        run_dir.mkdir(parents=True, exist_ok=True)
                        workspace.mkdir(parents=True, exist_ok=True)
                        last_workspace = workspace

                        # Build RunContext for this run
                        ctx = RunContext(
                            config=self.config,
                            tier_id=tier_id,
                            tier_config=tier_config,
                            subtest=subtest,
                            baseline=baseline,
                            run_number=run_num,
                            run_dir=run_dir,
                            workspace=workspace,
                            experiment_dir=experiment_dir,
                            tier_manager=self.tier_manager,
                            workspace_manager=self.workspace_manager,
                            adapter=self.adapter,
                            pipeline_baseline=pipeline_baseline,
                            task_prompt=task_prompt,
                            coordinator=coordinator,
                            checkpoint=checkpoint,
                            checkpoint_path=checkpoint_path,
                            resource_manager=self._resource_manager,
                        )

                        # Set thread-local log context for structured logging
                        from scylla.e2e.log_context import set_log_context

                        set_log_context(
                            tier_id=tier_id.value,
                            subtest_id=subtest.id,
                            run_num=run_num,
                        )

                        actions = build_actions_dict(ctx)

                        # Restore RunContext fields from disk when resuming from an
                        # intermediate state — earlier stages were skipped, so their
                        # outputs (agent_result, judge_prompt) must be reloaded.
                        if sm:
                            _current_run_state = sm.get_state(tier_id.value, subtest.id, run_num)
                            if _current_run_state.value != "pending":
                                _restore_run_context(ctx, _current_run_state.value)

                        try:
                            # Wrap entire run in workspace_slot to guarantee release on
                            # any exception (including ShutdownInterruptedError).
                            import contextlib
                            from contextlib import AbstractContextManager

                            ws_ctx: AbstractContextManager[Any] = (
                                self._resource_manager.workspace_slot()
                                if self._resource_manager
                                else contextlib.nullcontext()
                            )

                            with ws_ctx:
                                if sm:
                                    sm.advance_to_completion(
                                        tier_id.value,
                                        subtest.id,
                                        run_num,
                                        actions,
                                        until_state=self.config.until_run_state,
                                    )
                                else:
                                    # No checkpoint — run all stages directly without state machine
                                    for action in actions.values():
                                        action()

                            if ctx.run_result:
                                runs.append(ctx.run_result)

                            # Propagate pipeline_baseline to subsequent runs
                            if ctx.pipeline_baseline is not None and pipeline_baseline is None:
                                pipeline_baseline = ctx.pipeline_baseline

                        except RateLimitError as e:
                            # Move the run directory to .failed/ so run number can be reused
                            if run_dir.exists():
                                _move_to_failed(run_dir)

                            try:
                                _emitter.emit_counter(
                                    "scylla_errors_total",
                                    1,
                                    labels={
                                        "error_class": type(e).__name__,
                                        "tier": current_tier_id(),
                                    },
                                )
                            except Exception as _me:
                                logger.warning(f"Error metric emission failed (non-fatal): {_me}")

                            # Signal coordinator if available
                            if coordinator:
                                coordinator.signal_rate_limit(e.info)
                            # Re-raise to be handled at higher level
                            raise

                    except Exception as _exc:
                        try:
                            _emitter.emit_counter(
                                "scylla_errors_total",
                                1,
                                labels={
                                    "error_class": type(_exc).__name__,
                                    "tier": current_tier_id(),
                                },
                            )
                        except Exception as _me:
                            logger.warning(f"Error metric emission failed (non-fatal): {_me}")
                        _run_span.record_exception(_exc)
                        raise

        def _save_resource_manifest() -> None:
            nonlocal last_workspace

            # Save resource manifest for inheritance (no file copying)
            # Use last workspace if available, otherwise use the final run's workspace path
            if last_workspace is None and self.config.runs_per_subtest > 0:
                # No runs were executed (all completed via checkpoint), use last run's workspace
                last_run_num = self.config.runs_per_subtest
                last_workspace = results_dir / f"run_{last_run_num:02d}" / "workspace"

            if last_workspace is not None:
                self.tier_manager.save_resource_manifest(
                    results_dir=results_dir,
                    tier_id=tier_id,
                    subtest=subtest,
                    workspace=last_workspace,
                    baseline=baseline,
                )

        result: SubTestResult | None = None

        def _aggregate() -> None:
            nonlocal result
            result = self._aggregate_results(tier_id, subtest.id, runs)

        def _run_loop_and_save_manifest() -> None:
            _run_loop()
            _save_resource_manifest()
            # If --until stopped every run before reaching a terminal state, signal
            # SubtestSM to stay in RUNS_IN_PROGRESS (not advance to RUNS_COMPLETE).
            if self.config.until_run_state is not None and ssm is not None:
                from scylla.e2e.models import RunState
                from scylla.e2e.state_machine import is_terminal_state
                from scylla.e2e.subtest_state_machine import UntilHaltError

                run_map = ssm.checkpoint.run_states.get(tier_id.value, {}).get(subtest.id, {})
                any_non_terminal = any(
                    not is_terminal_state(RunState(s))
                    for s in run_map.values()
                    if s in {e.value for e in RunState}
                )
                if any_non_terminal:
                    raise UntilHaltError(
                        f"Runs for {tier_id.value}/{subtest.id} stopped at "
                        f"--until={self.config.until_run_state.value}; "
                        "leaving subtest in RUNS_IN_PROGRESS for future resume."
                    )

        subtest_actions = {
            SubtestState.PENDING: _run_loop_and_save_manifest,
            SubtestState.RUNS_IN_PROGRESS: _run_loop_and_save_manifest,
            SubtestState.RUNS_COMPLETE: _aggregate,
        }

        if ssm:
            ssm.advance_to_completion(tier_id.value, subtest.id, subtest_actions)
        else:
            _run_loop_and_save_manifest()
            _aggregate()

        if result is not None:
            return result

        # Re-hydrate runs from disk if empty — occurs when SubtestSM resumes from
        # AGGREGATED (terminal), which skips _run_loop and leaves `runs` empty.
        if not runs and results_dir.exists():
            from scylla.persistence.rehydrate import load_subtest_run_results

            runs = load_subtest_run_results(results_dir)
            if runs:
                logger.info(
                    f"Re-hydrated {len(runs)} run results from disk for "
                    f"{tier_id.value}/{subtest.id}"
                )

        return self._aggregate_results(tier_id, subtest.id, runs)

    def _compute_judge_consensus(
        self, judges: list[Any]
    ) -> tuple[float | None, bool | None, str | None]:
        """Compute consensus score from multiple judges using simple average.

        This is a wrapper method for backward compatibility.
        The actual implementation is in judge_runner._compute_judge_consensus.

        Args:
            judges: List of individual judge results

        Returns:
            Tuple of (consensus_score, passed, grade)

        """
        return _compute_judge_consensus(judges)

    def _aggregate_results(
        self,
        tier_id: TierID,
        subtest_id: str,
        runs: list[E2ERunResult],
    ) -> SubTestResult:
        """Aggregate results from multiple runs.

        Args:
            tier_id: The tier identifier
            subtest_id: The sub-test identifier
            runs: List of run results

        Returns:
            SubTestResult with aggregated statistics.

        """
        return aggregate_run_results(tier_id, subtest_id, runs)
