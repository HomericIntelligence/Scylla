"""Stage functions and RunContext for the state machine-driven E2E runner.

Each stage function corresponds to a RunState transition, extracting logic
from the original monolithic _execute_single_run() and run_subtest() methods.

Stage functions mutate a shared RunContext dataclass, passing results from
earlier stages to later ones without complex argument threading.

build_actions_dict() assembles the {RunState -> Callable} map expected by
StateMachine.advance_to_completion().

20-stage pipeline (19 explicit stage functions + 1 implicit auto-transition):
  PENDING                  -> stage_create_dir_structure()
  DIR_STRUCTURE_CREATED    -> stage_create_worktree()
  WORKTREE_CREATED         -> stage_apply_symlinks()
  SYMLINKS_APPLIED         -> stage_commit_config()
  CONFIG_COMMITTED         -> stage_capture_baseline()
  BASELINE_CAPTURED        -> stage_write_prompt()
  PROMPT_WRITTEN           -> stage_generate_replay()
  REPLAY_GENERATED         -> stage_execute_agent()
  AGENT_COMPLETE           -> stage_commit_agent_changes()
  AGENT_CHANGES_COMMITTED  -> stage_capture_diff()
  DIFF_CAPTURED            -> stage_promote_to_completed()
  PROMOTED_TO_COMPLETED    -> stage_run_judge_pipeline()
  JUDGE_PIPELINE_RUN       -> stage_build_judge_prompt()
  JUDGE_PROMPT_BUILT       -> stage_execute_judge()
  JUDGE_COMPLETE           -> stage_finalize_run()
  RUN_FINALIZED            -> stage_write_report()
  REPORT_WRITTEN           -> (no-op: StateMachine auto-saves checkpoint after every transition,
                               so no explicit stage_save_checkpoint function is needed here)
  CHECKPOINTED             -> stage_cleanup_worktree()
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scylla.e2e.models import (
    E2ERunResult,
    ExperimentConfig,
    RunState,
    SubTestConfig,
    TierBaseline,
    TierConfig,
    TierID,
)
from scylla.e2e.paths import get_agent_dir, get_judge_dir
from scylla.e2e.rate_limit import InfrastructureFailureError
from scylla.e2e.stage_finalization import (
    stage_cleanup_worktree as stage_cleanup_worktree,
)
from scylla.e2e.stage_finalization import (
    stage_execute_judge as stage_execute_judge,
)
from scylla.e2e.stage_finalization import (
    stage_finalize_run as stage_finalize_run,
)
from scylla.e2e.stage_finalization import (
    stage_write_report as stage_write_report,
)
from scylla.e2e.stage_process_metrics import (
    _build_change_results as _build_change_results,
)
from scylla.e2e.stage_process_metrics import (
    _build_progress_steps as _build_progress_steps,
)
from scylla.e2e.stage_process_metrics import (
    _finalize_change_results as _finalize_change_results,
)
from scylla.e2e.stage_process_metrics import (
    _finalize_progress_steps as _finalize_progress_steps,
)
from scylla.e2e.stage_process_metrics import (
    _get_diff_stat as _get_diff_stat,
)
from scylla.e2e.stage_process_metrics import (
    _load_process_metrics_from_run_result as _load_process_metrics_from_run_result,
)
from scylla.e2e.stage_process_metrics import (
    _parse_diff_numstat_output as _parse_diff_numstat_output,
)
from scylla.metrics.emitter import get_default_emitter
from scylla.metrics.process import (
    ChangeResult,
    ProgressStep,
)
from scylla.utils.tracing import get_tracer

if TYPE_CHECKING:
    from scylla.adapters.base import AdapterConfig, AdapterResult
    from scylla.adapters.claude_code import ClaudeCodeAdapter
    from scylla.e2e.checkpoint import E2ECheckpoint
    from scylla.e2e.llm_judge_models import BuildPipelineResult
    from scylla.e2e.models import JudgeResultSummary
    from scylla.e2e.parallel_executor import RateLimitCoordinator
    from scylla.e2e.resource_manager import ResourceManager
    from scylla.e2e.tier_manager import TierManager
    from scylla.e2e.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)
_tracer = get_tracer(__name__)

# Fallback lock for pipeline serialization when no ResourceManager is configured.
# Prefer ctx.resource_manager.pipeline_slot() when available.
_pipeline_lock = threading.Lock()


@dataclass
class RunContext:
    """All state needed by stage functions for a single run.

    Immutable config fields are set at construction time. Mutable fields
    (agent_result, judgment, etc.) are populated by stage functions and
    consumed by later stages.

    Attributes:
        config: Experiment configuration
        tier_id: Tier identifier
        tier_config: Tier configuration
        subtest: SubTestConfig for this run
        baseline: Previous tier's best baseline (if any)
        run_number: 1-based run number

        run_dir: Directory for this run's outputs (e.g., T0/00/run_01/)
        workspace: Workspace directory for this run (run_dir/workspace/)
        experiment_dir: Root experiment directory (for T5 inheritance, prompts)

        tier_manager: Tier configuration manager (shared across worker threads)
        workspace_manager: Workspace manager (shared across worker threads)
        adapter: Claude Code adapter for building commands

        pipeline_baseline: Build pipeline baseline captured before first run
        task_prompt: Task prompt text (loaded once by SubTestExecutor)

        agent_result: Result from agent execution (set by stage_execute_agent)
        agent_duration: Agent execution duration in seconds
        agent_ran: True if agent was actually executed (False if resumed)
        diff_result: Workspace diff captured after agent (set by stage_capture_diff)
        judge_pipeline_result: Build pipeline result on agent workspace (stage_run_judge_pipeline)
        judge_prompt: Assembled judge prompt text (set by stage_build_judge_prompt)
        judgment: Judge consensus dict (set by stage_execute_judge)
        judges: Individual judge result summaries
        judge_duration: Judge execution duration in seconds
        run_result: Final E2ERunResult (set by stage_finalize_run)

        coordinator: Rate limit coordinator for cross-thread pause/resume
        checkpoint: Experiment checkpoint (mutated by StateMachine)
        checkpoint_path: Path to checkpoint file

    """

    # Immutable config
    config: ExperimentConfig
    tier_id: TierID
    tier_config: TierConfig
    subtest: SubTestConfig
    baseline: TierBaseline | None
    run_number: int

    # Paths
    run_dir: Path
    workspace: Path
    experiment_dir: Path | None

    # Managers (shared across worker threads)
    tier_manager: TierManager
    workspace_manager: WorkspaceManager
    adapter: ClaudeCodeAdapter

    # Shared per-subtest state
    pipeline_baseline: BuildPipelineResult | None = None
    task_prompt: str = ""

    # Per-run mutable state (populated by stages, consumed by later stages)
    agent_result: AdapterResult | None = None
    agent_duration: float = 0.0
    agent_ran: bool = False
    diff_result: dict[str, Any] | None = None  # {workspace_state, patchfile, deleted_files}
    judge_pipeline_result: BuildPipelineResult | None = None
    judge_prompt: str = ""
    judgment: dict[str, Any] | None = None
    judges: list[JudgeResultSummary] = field(default_factory=list)
    judge_duration: float = 0.0
    run_result: E2ERunResult | None = None

    # Adapter config passed between stage_generate_replay and stage_execute_agent
    adapter_config: AdapterConfig | None = None

    # Process metrics tracking (populated by stage_capture_diff, finalized in stage_finalize_run)
    progress_steps: list[ProgressStep] | None = None
    change_results: list[ChangeResult] | None = None

    # Cross-thread coordination
    coordinator: RateLimitCoordinator | None = None
    checkpoint: E2ECheckpoint | None = None
    checkpoint_path: Path | None = None

    # Resource management (shared across all runs in a batch)
    resource_manager: ResourceManager | None = None


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------


def stage_create_dir_structure(ctx: RunContext) -> None:
    """PENDING -> DIR_STRUCTURE_CREATED: Create run directory structure.

    Creates run_dir, agent/, and judge/ subdirectories. Does NOT create
    the git worktree (that is the next stage).

    Args:
        ctx: Run context

    """
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    ctx.workspace.mkdir(parents=True, exist_ok=True)

    agent_dir = get_agent_dir(ctx.run_dir)
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_dir.chmod(0o777)

    judge_dir = get_judge_dir(ctx.run_dir)
    judge_dir.mkdir(parents=True, exist_ok=True)
    judge_dir.chmod(0o777)


def stage_create_worktree(ctx: RunContext) -> None:
    """DIR_STRUCTURE_CREATED -> WORKTREE_CREATED: Create git worktree for this run.

    Sets up the git worktree in ctx.workspace. Preserves existing workspace
    if run already passed (checkpoint resume).

    Acquires _workspace_semaphore to limit concurrent live workspaces.
    The semaphore is released in stage_cleanup_worktree.

    Args:
        ctx: Run context

    """
    from scylla.e2e.command_logger import CommandLogger
    from scylla.e2e.workspace_setup import _setup_workspace

    # Check if run already passed and workspace exists - preserve it
    run_status = None
    if ctx.checkpoint:
        run_status = ctx.checkpoint.get_run_status(
            ctx.tier_id.value, ctx.subtest.id, ctx.run_number
        )

    if run_status == "passed" and ctx.workspace.exists():
        logger.info(
            f"Run {ctx.run_number} already passed (checkpoint), preserving existing workspace"
        )
        return

    _setup_workspace(
        workspace=ctx.workspace,
        command_logger=CommandLogger(log_dir=ctx.run_dir),
        tier_id=ctx.tier_id,
        subtest_id=ctx.subtest.id,
        run_number=ctx.run_number,
        base_repo=ctx.workspace_manager.base_repo,
        task_commit=ctx.config.task_commit,
        experiment_id=ctx.config.experiment_id,
    )


def stage_apply_symlinks(ctx: RunContext) -> None:
    """WORKTREE_CREATED -> SYMLINKS_APPLIED: Apply tier resource symlinks to workspace.

    Calls tier_manager.prepare_workspace() to symlink tier resources
    (CLAUDE.md blocks, agents, skills) into the workspace. For T5 subtests
    with inherit_best_from, builds a merged baseline from lower tiers.

    Args:
        ctx: Run context

    """
    # Build merged resources for T5 subtests with inherit_best_from
    merged_resources = None
    if ctx.tier_id == TierID.T5 and ctx.subtest.inherit_best_from and ctx.experiment_dir:
        try:
            merged_resources = ctx.tier_manager.build_merged_baseline(
                ctx.subtest.inherit_best_from,
                ctx.experiment_dir,
            )
        except ValueError as e:
            logger.error(f"Failed to build merged baseline for T5/{ctx.subtest.id}: {e}")
            raise

    thinking_enabled = ctx.config.thinking_mode is not None and ctx.config.thinking_mode != "None"
    ctx.tier_manager.prepare_workspace(
        workspace=ctx.workspace,
        tier_id=ctx.tier_id,
        subtest_id=ctx.subtest.id,
        baseline=ctx.baseline,
        merged_resources=merged_resources,
        thinking_enabled=thinking_enabled,
    )

    # Symlink .pixi to shared directory so worktrees reuse one pixi environment
    ctx.workspace_manager.symlink_pixi(ctx.workspace)


def stage_commit_config(ctx: RunContext) -> None:
    """SYMLINKS_APPLIED -> CONFIG_COMMITTED: Commit test config to workspace.

    Runs git add CLAUDE.md .claude/ and git commit to initialize
    the test configuration in the workspace's git history.

    Args:
        ctx: Run context

    """
    from scylla.e2e.workspace_setup import _commit_test_config

    _commit_test_config(ctx.workspace)


def stage_capture_baseline(ctx: RunContext) -> None:
    """CONFIG_COMMITTED -> BASELINE_CAPTURED: Capture pipeline baseline.

    Load order (first match wins):
    1. ctx.pipeline_baseline already set — skip (shared by runs in SubTestExecutor)
    2. <experiment_dir>/pipeline_baseline.json — experiment-level baseline (preferred)
    3. <subtest_dir>/pipeline_baseline.json — backward-compat for old checkpoints
    4. Run inline (should not happen when _capture_experiment_baseline ran first)

    Args:
        ctx: Run context (mutates ctx.pipeline_baseline)

    """
    from scylla.e2e.subtest_executor import _load_pipeline_baseline, _save_pipeline_baseline

    if ctx.pipeline_baseline is not None:
        # Already captured by a previous run in this subtest — skip
        return

    # Try experiment-level baseline first (written by _capture_experiment_baseline)
    if ctx.experiment_dir is not None:
        ctx.pipeline_baseline = _load_pipeline_baseline(ctx.experiment_dir)

    if ctx.pipeline_baseline is None:
        # Backward compat: check subtest-level baseline from older checkpoints
        subtest_dir = ctx.run_dir.parent
        ctx.pipeline_baseline = _load_pipeline_baseline(subtest_dir)

    if ctx.pipeline_baseline is None:
        from scylla.e2e.build_pipeline import _run_build_pipeline

        logger.info("Capturing pipeline baseline inline (experiment-level baseline unavailable)")
        _lock = ctx.resource_manager.pipeline_slot() if ctx.resource_manager else _pipeline_lock
        with _lock:
            ctx.pipeline_baseline = _run_build_pipeline(
                workspace=ctx.workspace,
                language=ctx.config.language,
            )
        # Save at subtest level for this run's use
        _save_pipeline_baseline(ctx.run_dir.parent, ctx.pipeline_baseline)

        baseline_status = "ALL PASSED ✓" if ctx.pipeline_baseline.all_passed else "SOME FAILED ✗"
        logger.info(f"Pipeline baseline: {baseline_status}")


def stage_write_prompt(ctx: RunContext) -> None:
    """BASELINE_CAPTURED -> PROMPT_WRITTEN: Write task prompt to disk.

    Writes task_prompt.md (as symlink to experiment prompt or direct file),
    injects thinking keyword if configured.

    Args:
        ctx: Run context

    """
    # Write task_prompt.md
    prompt_file = ctx.run_dir / "task_prompt.md"
    if prompt_file.exists() or prompt_file.is_symlink():
        prompt_file.unlink()

    if ctx.experiment_dir is not None:
        experiment_prompt = ctx.experiment_dir / "prompt.md"
        if experiment_prompt.exists():
            prompt_file.symlink_to(experiment_prompt.resolve())
        else:
            prompt_file.write_text(ctx.task_prompt)
    else:
        prompt_file.write_text(ctx.task_prompt)


def stage_generate_replay(ctx: RunContext) -> None:
    """PROMPT_WRITTEN -> REPLAY_GENERATED: Build adapter command and generate replay.sh.

    If a valid agent result already exists (checkpoint resume), loads it into
    ctx.agent_result so stage_execute_agent becomes a no-op.

    Args:
        ctx: Run context (mutates ctx.agent_result if resuming)

    """
    from scylla.adapters.base import AdapterConfig
    from scylla.e2e.agent_runner import _has_valid_agent_result, _load_agent_result
    from scylla.e2e.command_logger import CommandLogger

    agent_dir = get_agent_dir(ctx.run_dir)

    # Check for valid agent result (resume case)
    if _has_valid_agent_result(ctx.run_dir):
        from scylla.e2e.paths import get_agent_result_file

        agent_result_file = get_agent_result_file(ctx.run_dir)
        logger.info(f"[SKIP] Agent already completed: {agent_result_file}")
        ctx.agent_result = _load_agent_result(agent_dir)
        # Load persisted timing
        agent_timing_file = agent_dir / "timing.json"
        if agent_timing_file.exists():
            timing_data = json.loads(agent_timing_file.read_text())
            ctx.agent_duration = timing_data.get("agent_duration_seconds", 0.0)
        ctx.agent_ran = False
        return

    # Inject thinking keyword if configured
    final_prompt = ctx.task_prompt
    if ctx.config.thinking_mode and ctx.config.thinking_mode != "None":
        thinking_keywords = {
            "Low": "think",
            "High": "think hard",
            "UltraThink": "ultrathink",
        }
        keyword = thinking_keywords.get(ctx.config.thinking_mode, "")
        if keyword:
            final_prompt = f"{keyword}\n\n{ctx.task_prompt}"

    agent_prompt_file = agent_dir / "prompt.md"
    agent_prompt_file.write_text(final_prompt)

    # Build extra args for adapter
    extra_args: list[str] = []
    if ctx.config.max_turns is not None:
        extra_args.extend(["--max-turns", str(ctx.config.max_turns)])

    # Extract agent name for T3/T4 delegation tiers
    agent_name = None
    if ctx.subtest.resources and "agents" in ctx.subtest.resources:
        agents_spec = ctx.subtest.resources["agents"]
        agent_names_list = agents_spec.get("names", [])
        if agent_names_list:
            agent_name = agent_names_list[0].replace(".md", "")
            logger.info(f"Using agent: {agent_name}")

    prompt_file = ctx.run_dir / "task_prompt.md"
    adapter_config = AdapterConfig(
        model=ctx.config.models[0],
        prompt_file=prompt_file,
        workspace=ctx.workspace,
        output_dir=agent_dir,
        timeout=ctx.config.timeout_seconds,
        extra_args=extra_args,
    )

    cmd = ctx.adapter._build_command(
        adapter_config,
        str(agent_prompt_file.resolve()),
        None,
        ctx.subtest.system_prompt_mode,
        agent_name,
    )

    command_logger = CommandLogger(log_dir=agent_dir)
    command_logger.log_command(
        cmd=cmd,
        stdout="",
        stderr="",
        exit_code=0,
        duration=0.0,
        cwd=str(ctx.workspace.resolve()),
    )
    command_logger.save()
    command_logger.save_replay_script()
    # Store adapter_config for use in stage_execute_agent
    ctx.adapter_config = adapter_config


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    """Kill a subprocess and its entire process group.

    Sends SIGTERM first, then SIGKILL if needed.

    Args:
        proc: Popen process to kill.

    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        proc.wait()


def _communicate_with_shutdown_check(
    proc: subprocess.Popen[str],
    timeout: float,
    ctx: RunContext,
) -> tuple[str, str]:
    """Poll subprocess with periodic shutdown checks.

    Calls proc.communicate(timeout=poll_interval) in a loop so that
    Ctrl+C can interrupt a long-running agent (timeout can be up to 3600s).
    communicate(timeout=N) does NOT consume partial output on TimeoutExpired,
    so calling it in a loop is safe — the successful call returns all output.

    Args:
        proc: Running subprocess.
        timeout: Overall timeout in seconds.
        ctx: Run context for error messages.

    Returns:
        Tuple of (stdout, stderr) from the completed process.

    Raises:
        ShutdownInterruptedError: If shutdown is requested during execution.
        subprocess.TimeoutExpired: If the overall timeout expires.

    """
    poll_interval = 2.0
    remaining = float(timeout)
    while True:
        try:
            return proc.communicate(timeout=poll_interval)
        except subprocess.TimeoutExpired:
            remaining -= poll_interval
            if remaining <= 0:
                raise
            from scylla.e2e.shutdown import ShutdownInterruptedError, is_shutdown_requested

            if is_shutdown_requested():
                _kill_process_group(proc)
                raise ShutdownInterruptedError(
                    f"Shutdown requested during agent execution for run "
                    f"{ctx.run_number} ({ctx.tier_id.value}/{ctx.subtest.id})"
                ) from None


def stage_execute_agent(ctx: RunContext) -> None:
    """REPLAY_GENERATED -> AGENT_COMPLETE: Execute agent and save outputs.

    If ctx.agent_result is already set (resume), this is a no-op.
    Otherwise, runs via replay.sh and saves all agent artifacts.

    Wraps execution in an OTel span (``scylla.adapter.call``) and emits
    ``scylla_adapter_call_duration_seconds`` and ``scylla_adapter_tokens_total``
    via the default MetricEmitter. Both are no-ops when env vars are unset.

    Args:
        ctx: Run context (mutates ctx.agent_result, ctx.agent_duration, ctx.agent_ran)

    """
    if ctx.agent_result is not None:
        # Resumed — agent result already loaded by stage_generate_replay
        logger.debug(f"Skipping agent execution for run {ctx.run_number} (resumed)")
        return

    with _tracer.start_as_current_span(
        "scylla.adapter.call",
        attributes={
            "scylla.tier_id": ctx.tier_id.value,
            "scylla.subtest_id": ctx.subtest.id,
            "scylla.run_num": ctx.run_number,
            "scylla.adapter": ctx.adapter.get_name(),
            "scylla.model": ctx.config.models[0] if ctx.config.models else "",
        },
    ) as _adapter_span:
        try:
            _stage_execute_agent_body(ctx)
        except Exception as _exc:
            _adapter_span.record_exception(_exc)
            raise
        finally:
            _emit_adapter_metrics(ctx)


def _emit_adapter_metrics(ctx: RunContext) -> None:
    """Emit adapter call duration + token counters. Best-effort, never raises."""
    try:
        emitter = get_default_emitter()
        labels = {
            "tier": ctx.tier_id.value,
            "subtest": ctx.subtest.id,
            "model": ctx.config.models[0] if ctx.config.models else "",
        }
        if ctx.agent_duration is not None:
            emitter.emit_gauge(
                "scylla_adapter_call_duration_seconds",
                float(ctx.agent_duration),
                labels=labels,
            )
        if ctx.agent_result is not None:
            tok = ctx.agent_result.token_stats
            if tok.input_tokens:
                emitter.emit_counter(
                    "scylla_adapter_tokens_total",
                    int(tok.input_tokens),
                    labels={**labels, "kind": "input"},
                )
            if tok.output_tokens:
                emitter.emit_counter(
                    "scylla_adapter_tokens_total",
                    int(tok.output_tokens),
                    labels={**labels, "kind": "output"},
                )
    except Exception as e:  # emitter must never break the run
        logger.debug(f"Adapter metric emission failed (non-fatal): {e}")


def _stage_execute_agent_body(ctx: RunContext) -> None:
    """Body of :func:`stage_execute_agent`, wrapped in a tracing span by caller."""
    from scylla.adapters.base import AdapterResult
    from scylla.e2e.agent_runner import (
        _create_agent_model_md,
        _save_agent_result,
    )
    from scylla.e2e.command_logger import CommandLogger

    agent_dir = get_agent_dir(ctx.run_dir)
    adapter_config = ctx.adapter_config
    if adapter_config is None:
        # Resuming into replay_generated: stage_generate_replay was skipped, so
        # adapter_config was never set. Reconstruct it from the run context.
        from scylla.adapters.base import AdapterConfig

        adapter_config = AdapterConfig(
            model=ctx.config.models[0],
            prompt_file=ctx.run_dir / "task_prompt.md",
            workspace=ctx.workspace,
            output_dir=agent_dir,
            timeout=ctx.config.timeout_seconds,
            extra_args=(
                ["--max-turns", str(ctx.config.max_turns)]
                if ctx.config.max_turns is not None
                else []
            ),
        )
        ctx.adapter_config = adapter_config
    replay_script = agent_dir / "replay.sh"

    logger.info(f"[AGENT] Running agent with model[{ctx.config.models[0]}]")

    agent_start = datetime.now(timezone.utc)
    try:
        # Use Popen with start_new_session so the agent subprocess gets its own
        # process group. This lets us kill it (and its children) cleanly on shutdown.
        proc = subprocess.Popen(
            ["bash", str(replay_script.resolve())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=ctx.workspace.resolve(),
            start_new_session=True,
        )
        try:
            # Poll subprocess with periodic shutdown checks so Ctrl+C can interrupt
            # a long-running agent (timeout can be up to 3600s).
            # communicate(timeout=N) does NOT consume partial output on TimeoutExpired,
            # so calling it in a loop is safe — the successful call returns all output.
            stdout, stderr = _communicate_with_shutdown_check(proc, adapter_config.timeout, ctx)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            raise

        # If the agent was killed by a shutdown signal (Ctrl+C), do NOT advance the
        # run state — leave it at REPLAY_GENERATED so the next invocation can retry
        # cleanly.  The subprocess returns normally (no Python exception) but with a
        # signal exit code, so we must check the shutdown flag explicitly here.
        from scylla.e2e.shutdown import ShutdownInterruptedError, is_shutdown_requested

        if is_shutdown_requested():
            _kill_process_group(proc)
            raise ShutdownInterruptedError(
                f"Shutdown requested during agent execution for run {ctx.run_number} "
                f"({ctx.tier_id.value}/{ctx.subtest.id})"
            )

        token_stats = ctx.adapter._parse_token_stats(stdout, stderr)
        api_calls = ctx.adapter._parse_api_calls(stdout, stderr)
        cost = ctx.adapter._parse_cost(stdout)

        if cost == 0.0 and (token_stats.input_tokens > 0 or token_stats.output_tokens > 0):
            total_input = token_stats.input_tokens + token_stats.cache_read_tokens
            cost = ctx.adapter.calculate_cost(
                total_input, token_stats.output_tokens, adapter_config.model
            )

        ctx.adapter.write_logs(agent_dir, stdout, stderr)

        agent_result = AdapterResult(
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            token_stats=token_stats,
            cost_usd=cost,
            api_calls=api_calls,
        )
    except Exception as e:
        from scylla.adapters.base import AdapterResult, AdapterTokenStats
        from scylla.e2e.shutdown import ShutdownInterruptedError

        if isinstance(e, ShutdownInterruptedError):
            raise

        agent_result = AdapterResult(
            exit_code=-1,
            stdout="",
            stderr=str(e),
            token_stats=AdapterTokenStats(),
            cost_usd=0.0,
            api_calls=0,
        )
    ctx.agent_duration = (datetime.now(timezone.utc) - agent_start).total_seconds()
    ctx.agent_result = agent_result
    ctx.agent_ran = True

    # Update command logger with actual results
    command_log_path = agent_dir / "command_log.json"
    if command_log_path.exists():
        command_logger = CommandLogger.load(agent_dir)
    else:
        command_logger = CommandLogger(log_dir=agent_dir)
    if command_logger.commands:
        command_logger.update_last_command(
            stdout=agent_result.stdout,
            stderr=agent_result.stderr,
            exit_code=agent_result.exit_code,
            duration=ctx.agent_duration,
        )
        command_logger.save()

    # Persist timing for resume capability
    agent_timing_file = agent_dir / "timing.json"
    with open(agent_timing_file, "w") as f:
        json.dump(
            {
                "agent_duration_seconds": ctx.agent_duration,
                "measured_at": datetime.now(timezone.utc).isoformat(),
            },
            f,
            indent=2,
        )

    # Save output and result
    (agent_dir / "output.txt").write_text(agent_result.stdout or "")
    _save_agent_result(agent_dir, agent_result)
    _create_agent_model_md(agent_dir, ctx.config.models[0])

    logger.info(f"[AGENT] Complete ({ctx.agent_duration:.1f}s)")


def stage_commit_agent_changes(ctx: RunContext) -> None:
    """AGENT_COMPLETE -> AGENT_CHANGES_COMMITTED: Commit agent changes to worktree branch.

    Detects infrastructure failures (exit_code=-1 with zero tokens) and moves
    the run to a .failed/ archive directory, then raises to abort the pipeline.
    For normal runs, stages and commits all workspace changes so the worktree
    can be safely cleaned up between phases.

    Args:
        ctx: Run context (reads ctx.agent_result, ctx.workspace, ctx.run_dir)

    Raises:
        RuntimeError: If an infrastructure failure is detected (exit_code=-1, zero tokens)

    """
    import shutil

    agent_result = ctx.agent_result
    if agent_result is not None:
        is_infra_failure = (
            agent_result.exit_code == -1
            and agent_result.token_stats.input_tokens == 0
            and agent_result.token_stats.output_tokens == 0
        )
        if is_infra_failure:
            # Move run directory to .failed/ archive under the subtest dir to prevent
            # phantom 0.0 scores from polluting pass_rate statistics
            failed_archive = ctx.run_dir.parent / ".failed"
            failed_archive.mkdir(exist_ok=True)
            dest = failed_archive / ctx.run_dir.name
            if dest.exists():
                shutil.rmtree(str(dest))
            shutil.move(str(ctx.run_dir), str(dest))
            logger.warning(
                f"[AGENT] Infrastructure failure detected (exit_code=-1, zero tokens) — "
                f"run moved to {dest}"
            )
            raise InfrastructureFailureError(
                f"Infrastructure failure in run {ctx.run_number} "
                f"({ctx.tier_id.value}/{ctx.subtest.id}): agent crashed before making any API calls"
            )

    # Commit all workspace changes so they survive worktree cleanup between phases
    if ctx.workspace.exists():
        commit_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=ctx.workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if commit_result.returncode != 0:
            logger.warning(f"[AGENT] git add -A failed: {commit_result.stderr.strip()}")
        else:
            commit_result = subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "[scylla] Agent changes"],
                cwd=ctx.workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if commit_result.returncode != 0:
                logger.warning(
                    f"[AGENT] git commit failed (may be empty): {commit_result.stderr.strip()}"
                )
            else:
                logger.info("[AGENT] Agent changes committed to worktree branch")
    else:
        logger.warning(f"[AGENT] Workspace not found at {ctx.workspace} — skipping commit")


def stage_promote_to_completed(ctx: RunContext) -> None:
    """DIFF_CAPTURED -> PROMOTED_TO_COMPLETED: Move run directory to completed/.

    Moves the run directory from in_progress/<tier>/<subtest>/run_NN/ to
    completed/<tier>/<subtest>/run_NN/ and updates ctx.run_dir and ctx.workspace
    to point to the new location. Also promotes pipeline_baseline.json if present.

    Args:
        ctx: Run context (mutates ctx.run_dir and ctx.workspace)

    """
    from scylla.e2e.paths import get_experiment_dir_from_run, promote_run_to_completed

    experiment_dir = get_experiment_dir_from_run(ctx.run_dir)
    new_run_dir = promote_run_to_completed(
        experiment_dir, ctx.tier_id.value, ctx.subtest.id, ctx.run_number
    )

    # Update ctx paths to point to new location
    old_workspace_name = ctx.workspace.name
    ctx.run_dir = new_run_dir
    ctx.workspace = new_run_dir / old_workspace_name

    logger.info(f"[PROMOTE] Run moved to completed: {new_run_dir}")


def stage_capture_diff(ctx: RunContext) -> None:
    """AGENT_CHANGES_COMMITTED -> DIFF_CAPTURED: Capture workspace diff and state.

    Runs git diff/status to capture changes made by the agent.
    Saves diff data to ctx.diff_result for use by later stages.
    Also populates ctx.progress_steps and ctx.change_results for process
    metrics emission in stage_finalize_run.

    If judge result can be reused (resume case), also loads existing
    judgment to make subsequent judge stages no-ops.

    Args:
        ctx: Run context (mutates ctx.diff_result, ctx.progress_steps,
            ctx.change_results, and optionally ctx.judgment)

    """
    from scylla.e2e.judge_runner import _has_valid_judge_result, _load_judge_result
    from scylla.e2e.llm_judge import _get_deleted_files, _get_patchfile, _get_workspace_state

    judge_dir = get_judge_dir(ctx.run_dir)

    # Only reuse judge result if agent was also reused (not re-run)
    if not ctx.agent_ran and _has_valid_judge_result(ctx.run_dir):
        from scylla.e2e.paths import get_judge_result_file

        judge_result_file = get_judge_result_file(ctx.run_dir)
        logger.info(f"[SKIP] Judge already completed: {judge_result_file}")
        ctx.judgment = _load_judge_result(judge_dir)
        # Load persisted timing
        judge_timing_file = judge_dir / "timing.json"
        if judge_timing_file.exists():
            timing_data = json.loads(judge_timing_file.read_text())
            ctx.judge_duration = timing_data.get("judge_duration_seconds", 0.0)
        # diff_result not needed since judge is already done
        ctx.diff_result = {}
        ctx.progress_steps = []
        ctx.change_results = []
        return

    # Capture workspace diff
    workspace_state = _get_workspace_state(ctx.workspace)
    patchfile = _get_patchfile(ctx.workspace)
    deleted_files = _get_deleted_files(ctx.workspace)

    ctx.diff_result = {
        "workspace_state": workspace_state,
        "patchfile": patchfile,
        "deleted_files": deleted_files,
    }

    # Build preliminary process metrics data (judge outcome not yet known)
    diff_stat = _get_diff_stat(ctx.workspace)
    ctx.progress_steps = _build_progress_steps(
        workspace_state, judge_score=0.0, diff_stat=diff_stat
    )
    ctx.change_results = _build_change_results(diff_stat, judge_passed=False, pipeline_passed=True)


def stage_run_judge_pipeline(ctx: RunContext) -> None:
    """DIFF_CAPTURED -> JUDGE_PIPELINE_RUN: Run build pipeline on agent workspace.

    Runs the language-appropriate build pipeline (compileall, ruff, pytest,
    pre-commit for Python; Mojo pipeline for Mojo) on the agent-modified workspace.
    Saves pipeline results to ctx.judge_pipeline_result.

    If judgment already loaded (resume), this is a no-op.

    Args:
        ctx: Run context (mutates ctx.judge_pipeline_result)

    """
    if ctx.judgment is not None:
        # Resumed — judge result already loaded in stage_capture_diff
        return

    from scylla.e2e.build_pipeline import _run_build_pipeline
    from scylla.e2e.pipeline_scripts import _save_pipeline_commands

    logger.info(f"Running {ctx.config.language} build pipeline for judge evaluation")
    _lock = ctx.resource_manager.pipeline_slot() if ctx.resource_manager else _pipeline_lock
    with _lock:
        ctx.judge_pipeline_result = _run_build_pipeline(
            workspace=ctx.workspace,
            language=ctx.config.language,
        )

    # Save pipeline commands for debugging
    _save_pipeline_commands(ctx.run_dir, ctx.workspace, language=ctx.config.language)

    # Save pipeline outputs
    from scylla.e2e.pipeline_scripts import _save_pipeline_outputs

    _save_pipeline_outputs(ctx.run_dir, ctx.judge_pipeline_result, language=ctx.config.language)

    status = "ALL PASSED ✓" if ctx.judge_pipeline_result.all_passed else "SOME FAILED ✗"
    logger.info(f"Judge pipeline: {status}")


def stage_build_judge_prompt(ctx: RunContext) -> None:
    """JUDGE_PIPELINE_RUN -> JUDGE_PROMPT_BUILT: Assemble full judge prompt.

    Combines task prompt, agent output, workspace state, diff, pipeline results,
    rubric, and criteria into the complete judge evaluation prompt.
    Saves prompt to judge/prompt.md for debugging and resume.

    If judgment already loaded (resume), this is a no-op.

    Args:
        ctx: Run context (mutates ctx.judge_prompt)

    """
    if ctx.judgment is not None:
        # Resumed — judge result already loaded in stage_capture_diff
        return

    # Find rubric path (symlinked at experiment root)
    from scylla.e2e.paths import get_experiment_dir_from_run
    from scylla.judge.prompts import build_task_prompt

    experiment_dir_calc = get_experiment_dir_from_run(ctx.run_dir)
    rubric_path = experiment_dir_calc / "rubric.yaml"

    rubric_content = None
    if rubric_path.exists():
        try:
            rubric_content = rubric_path.read_text()
        except Exception as e:
            logger.warning(f"Failed to load rubric from {rubric_path}: {e}")

    # Format pipeline result strings
    pipeline_result_str = None
    if ctx.judge_pipeline_result:
        overall_status = "ALL PASSED ✓" if ctx.judge_pipeline_result.all_passed else "SOME FAILED ✗"
        pipeline_result_str = (
            f"**Overall Status**: {overall_status}\n\n"
            f"{ctx.judge_pipeline_result.to_context_string()}"
        )

    baseline_pipeline_str = None
    if ctx.pipeline_baseline:
        baseline_status = "ALL PASSED ✓" if ctx.pipeline_baseline.all_passed else "SOME FAILED ✗"
        baseline_pipeline_str = (
            f"**Overall Status**: {baseline_status}\n\n{ctx.pipeline_baseline.to_context_string()}"
        )

    diff_data = ctx.diff_result or {}
    ctx.judge_prompt = build_task_prompt(
        task_prompt=ctx.task_prompt,
        agent_output=ctx.agent_result.stdout if ctx.agent_result else "",
        workspace_state=diff_data.get("workspace_state", ""),
        patchfile=diff_data.get("patchfile"),
        deleted_files=diff_data.get("deleted_files"),
        reference_patch=None,
        pipeline_result_str=pipeline_result_str,
        rubric_content=rubric_content,
        baseline_pipeline_str=baseline_pipeline_str,
    )

    # Save assembled judge prompt to disk for debugging and resume
    judge_prompt_path = ctx.run_dir / "judge_prompt.md"
    if not judge_prompt_path.exists():
        judge_prompt_path.write_text(ctx.judge_prompt)


# ---------------------------------------------------------------------------
# Stage map builder
# ---------------------------------------------------------------------------


def build_actions_dict(
    ctx: RunContext,
) -> dict[RunState, Callable[..., Any]]:
    """Build the {RunState -> Callable} map for StateMachine.advance_to_completion().

    Each entry maps from_state -> callable that performs the work for the
    transition starting at that state.

    Args:
        ctx: Run context holding all state for this run

    Returns:
        Dict mapping RunState to callable stage function

    """

    def _agent_with_slot() -> None:
        """Execute agent within agent_slot context manager (RAM protection)."""
        if ctx.resource_manager:
            with ctx.resource_manager.agent_slot():
                stage_execute_agent(ctx)
        else:
            stage_execute_agent(ctx)

    def _judge_with_slot() -> None:
        """Execute judge within agent_slot context manager (RAM protection)."""
        if ctx.resource_manager:
            with ctx.resource_manager.agent_slot():
                stage_execute_judge(ctx)
        else:
            stage_execute_judge(ctx)

    return {
        RunState.PENDING: lambda: stage_create_dir_structure(ctx),
        RunState.DIR_STRUCTURE_CREATED: lambda: stage_create_worktree(ctx),
        RunState.WORKTREE_CREATED: lambda: stage_apply_symlinks(ctx),
        RunState.SYMLINKS_APPLIED: lambda: stage_commit_config(ctx),
        RunState.CONFIG_COMMITTED: lambda: stage_capture_baseline(ctx),
        RunState.BASELINE_CAPTURED: lambda: stage_write_prompt(ctx),
        RunState.PROMPT_WRITTEN: lambda: stage_generate_replay(ctx),
        RunState.REPLAY_GENERATED: _agent_with_slot,
        RunState.AGENT_COMPLETE: lambda: stage_commit_agent_changes(ctx),
        RunState.AGENT_CHANGES_COMMITTED: lambda: stage_capture_diff(ctx),
        RunState.DIFF_CAPTURED: lambda: stage_promote_to_completed(ctx),
        RunState.PROMOTED_TO_COMPLETED: lambda: stage_run_judge_pipeline(ctx),
        RunState.JUDGE_PIPELINE_RUN: lambda: stage_build_judge_prompt(ctx),
        RunState.JUDGE_PROMPT_BUILT: _judge_with_slot,
        RunState.JUDGE_COMPLETE: lambda: stage_finalize_run(ctx),
        RunState.RUN_FINALIZED: lambda: stage_write_report(ctx),
        RunState.CHECKPOINTED: lambda: stage_cleanup_worktree(ctx),
    }
