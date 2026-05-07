"""Main E2E experiment runner.

This module provides the main entry point for running E2E experiments,
coordinating tier execution, inheritance, result aggregation, and report generation.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scylla.e2e.judge_selection import JudgeSelection
    from scylla.e2e.models import SubTestResult, TierConfig
    from scylla.e2e.resource_manager import ResourceManager

import contextlib

from scylla.e2e.checkpoint import (
    E2ECheckpoint,
    compute_config_hash,
    load_checkpoint,
    save_checkpoint,
    validate_checkpoint_config,
)
from scylla.e2e.checkpoint_finalizer import CheckpointFinalizer
from scylla.e2e.experiment_result_writer import ExperimentResultWriter
from scylla.e2e.experiment_setup_manager import ExperimentSetupManager

# Note: Judge prompts are now generated dynamically via scylla.judge.prompts.build_task_prompt()
from scylla.e2e.models import (
    TIER_DEPENDENCIES,
    ExperimentConfig,
    ExperimentResult,
    ExperimentState,
    TierBaseline,
    TierID,
    TierResult,
    TierState,
    TokenStats,
)
from scylla.e2e.parallel_tier_runner import ParallelTierRunner
from scylla.e2e.resume_manager import ResumeManager
from scylla.e2e.shutdown import (
    ShutdownInterruptedError,
    is_shutdown_requested,
    request_shutdown,
)
from scylla.e2e.tier_action_builder import TierActionBuilder
from scylla.e2e.tier_manager import TierManager
from scylla.e2e.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)

# Checkpoint status constant (kept as string for JSON serialization compatibility)
_STATUS_RUNNING = "running"

# Shutdown coordination is re-exported from scylla.e2e.shutdown for backward
# compatibility (see __all__ below). Callers needing only these symbols should
# import scylla.e2e.shutdown directly. shutdown.py is a leaf module (only
# stdlib imports) so no cycle is created by the top-level import above.

__all__ = [
    "ShutdownInterruptedError",
    "is_shutdown_requested",
    "request_shutdown",
]


@dataclass
class TierContext:
    """Mutable namespace for inter-action state within a single tier execution.

    Passed via closure to each action in _build_tier_actions(). Fields are
    populated progressively as the TierStateMachine advances through states.

    Attributes:
        start_time: When the tier started (set in action_pending)
        tier_config: Loaded tier configuration (set in action_pending)
        tier_dir: Tier results directory (set in action_pending)
        subtest_results: Results from parallel subtest execution (set in action_config_loaded)
        selection: Best subtest selection (set in action_subtests_running)
        tier_result: Final aggregated TierResult (set in action_subtests_complete)

    """

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tier_config: TierConfig | None = None
    tier_dir: Path | None = None
    subtest_results: dict[str, SubTestResult] = field(default_factory=dict)
    selection: JudgeSelection | None = None
    tier_result: TierResult | None = None


class E2ERunner:
    """Main runner for E2E experiments.

    Orchestrates the complete E2E experiment lifecycle:
    1. Initialize experiment directory
    2. For each tier (T0 → T6):
       a. Load tier configuration
       b. Run all sub-tests in parallel
       c. Select best sub-test
       d. Set baseline for next tier
    3. Generate cross-tier analysis
    4. Create final report

    Example:
        >>> config = ExperimentConfig(
        ...     experiment_id="exp-001",
        ...     task_repo="https://github.com/example/repo",
        ...     task_commit="abc123",
        ...     task_prompt_file=Path("prompt.md"),
        ... )
        >>> runner = E2ERunner(config, Path("tests/fixtures/tests/test-001"), Path("results"))
        >>> result = runner.run()

    """

    def __init__(
        self,
        config: ExperimentConfig,
        tiers_dir: Path,
        results_base_dir: Path,
        fresh: bool = False,
    ) -> None:
        """Initialize the E2E runner.

        Args:
            config: Experiment configuration
            tiers_dir: Path to tier configurations
            results_base_dir: Base directory for results
            fresh: If True, ignore existing checkpoints and start fresh

        """
        self.config = config
        self.tier_manager = TierManager(tiers_dir)
        self.results_base_dir = results_base_dir
        self.experiment_dir: Path | None = None
        self.workspace_manager: WorkspaceManager | None = None
        self.checkpoint: E2ECheckpoint | None = None
        self._fresh = fresh
        self._last_experiment_result: ExperimentResult | None = None
        self._resource_manager: ResourceManager | None = None

    def _result_writer(self) -> ExperimentResultWriter:
        """Create an ExperimentResultWriter bound to current state.

        Returns:
            ExperimentResultWriter with current experiment_dir and tier_manager.

        """
        return ExperimentResultWriter(
            experiment_dir=self.experiment_dir,
            tier_manager=self.tier_manager,
        )

    @staticmethod
    def _get_tier_groups(tiers_to_run: list[TierID]) -> list[list[TierID]]:
        """Group tiers by dependencies for parallel execution.

        Tiers within each group can run in parallel. Groups are executed sequentially.

        Args:
            tiers_to_run: List of tier IDs to run

        Returns:
            List of tier groups, where each group can be run in parallel.
            Example: [[T0, T1, T2, T3, T4], [T5], [T6]]

        """
        if not tiers_to_run:
            return []

        groups: list[list[TierID]] = []
        remaining = set(tiers_to_run)
        completed: set[TierID] = set()

        while remaining:
            # Find all tiers whose dependencies are satisfied
            ready = [
                tier
                for tier in remaining
                if all(
                    dep in completed or dep not in tiers_to_run for dep in TIER_DEPENDENCIES[tier]
                )
            ]

            if not ready:
                # Circular dependency or missing dependency
                raise ValueError(
                    f"Unable to resolve tier dependencies. "
                    f"Remaining: {remaining}, Completed: {completed}"
                )

            groups.append(sorted(ready))  # Sort for deterministic ordering
            completed.update(ready)
            remaining -= set(ready)

        return groups

    def _log_checkpoint_resume(self, checkpoint_path: Path) -> None:
        """Log checkpoint resume status with completed run count.

        Args:
            checkpoint_path: Path to checkpoint.json file

        """
        if self.checkpoint is None:
            raise RuntimeError("checkpoint must be set before logging resume status")
        logger.info(f"📂 Resuming from checkpoint: {checkpoint_path}")
        logger.info(f"   Previously completed: {self.checkpoint.get_completed_run_count()} runs")

    def _load_checkpoint_and_config(self, checkpoint_path: Path) -> tuple[E2ECheckpoint, Path]:
        """Load and validate checkpoint and configuration from existing checkpoint.

        Args:
            checkpoint_path: Path to checkpoint.json file

        Returns:
            Tuple of (checkpoint, experiment_dir)

        Raises:
            ValueError: If config validation fails or experiment directory doesn't exist
            Exception: If checkpoint loading fails

        """
        self.checkpoint = load_checkpoint(checkpoint_path)
        self.experiment_dir = Path(self.checkpoint.experiment_dir)

        # Load config from checkpoint's saved experiment.json
        # This ensures checkpoint config takes precedence over CLI args
        saved_config_path = self.experiment_dir / "config" / "experiment.json"
        if saved_config_path.exists():
            self._log_checkpoint_resume(checkpoint_path)
            logger.info(f"📋 Loading config from checkpoint: {saved_config_path}")
            self.config = ExperimentConfig.load(saved_config_path)
        else:
            # Fallback: validate CLI config matches checkpoint
            logger.warning(
                f"⚠️  Checkpoint config not found at {saved_config_path}, using CLI config"
            )
            if not validate_checkpoint_config(self.checkpoint, self.config):
                raise ValueError(
                    f"Config has changed since checkpoint. Use --fresh to start over.\n"
                    f"Checkpoint: {checkpoint_path}"
                )
            self._log_checkpoint_resume(checkpoint_path)

        # Validate experiment directory exists
        if not self.experiment_dir.exists():
            raise ValueError(f"Checkpoint references non-existent directory: {self.experiment_dir}")

        return self.checkpoint, self.experiment_dir

    def _create_fresh_experiment(self) -> Path:
        """Create new experiment directory and initialize checkpoint.

        Returns:
            Path to the created checkpoint file

        """
        setup = self._setup_manager()
        self.experiment_dir = setup.create_experiment_dir()
        setup.save_config(self.experiment_dir)

        self.checkpoint = E2ECheckpoint(
            experiment_id=self.config.experiment_id,
            experiment_dir=str(self.experiment_dir),
            config_hash=compute_config_hash(self.config),
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status=_STATUS_RUNNING,
            rate_limit_source=None,
            rate_limit_until=None,
            pause_count=0,
            pid=os.getpid(),
        )

        checkpoint_path = self.experiment_dir / "checkpoint.json"
        save_checkpoint(self.checkpoint, checkpoint_path)
        logger.info(f"💾 Created checkpoint: {checkpoint_path}")

        return checkpoint_path

    def _initialize_or_resume_experiment(self) -> Path:
        """Initialize fresh experiment or resume from checkpoint.

        Handles:
        - Finding existing checkpoint
        - Loading checkpoint and validating config
        - Creating fresh experiment directory if needed
        - Writing PID file for monitoring

        Returns:
            Path to checkpoint file for this experiment

        """
        # Check for existing checkpoint (auto-resume unless --fresh)
        checkpoint_path = self._find_existing_checkpoint()

        if checkpoint_path and not self._fresh:
            # STEP 1: Capture CLI fields before _load_checkpoint_and_config overwrites self.config
            _cli_tiers = list(self.config.tiers_to_run)
            _cli_ephemeral = {
                "until_run_state": self.config.until_run_state,
                "until_tier_state": self.config.until_tier_state,
                "until_experiment_state": self.config.until_experiment_state,
                "max_subtests": self.config.max_subtests,
            }

            try:
                # STEP 1 (continued): Load checkpoint — overwrites self.config from saved JSON
                self._load_checkpoint_and_config(checkpoint_path)

                if self.checkpoint:
                    rm = ResumeManager(self.checkpoint, self.config, self.tier_manager)

                    # STEP 1 (continued): Check for zombie (crashed) experiment
                    self.config, self.checkpoint = rm.handle_zombie(
                        checkpoint_path, self.experiment_dir
                    )

                    # STEP 2: Restore ephemeral CLI args
                    self.config, self.checkpoint = rm.restore_cli_args(_cli_ephemeral)

                    # STEP 3: Reset failed/interrupted states for re-execution
                    self.config, self.checkpoint = rm.reset_failed_states()

                    # STEP 4: Merge CLI tiers and reset incomplete tier/subtest states
                    self.config, self.checkpoint = rm.merge_cli_tiers_and_reset_incomplete(
                        _cli_tiers, checkpoint_path
                    )

            except Exception as e:  # broad catch: resume can fail from JSON/IO/state errors
                logger.warning(f"Failed to resume from checkpoint: {e}")
                logger.warning("Starting fresh experiment instead")
                self.checkpoint = None
                self.experiment_dir = None

        if not self.experiment_dir:
            checkpoint_path = self._create_fresh_experiment()

        # Write PID file for status monitoring
        self._write_pid_file()

        if self.experiment_dir is None:
            raise RuntimeError("experiment_dir must be set before getting checkpoint path")
        return self.experiment_dir / "checkpoint.json"

    def _setup_workspace(self) -> None:
        """Set up workspace manager for execution.

        Creates and configures the WorkspaceManager if not already initialized.
        """
        if not hasattr(self, "workspace_manager") or self.workspace_manager is None:
            # Use centralized repos directory for shared clones across experiments
            repos_dir = self.results_base_dir / "repos"
            if self.experiment_dir is None:
                raise RuntimeError(
                    "experiment_dir must be set before initializing workspace manager"
                )
            self.workspace_manager = WorkspaceManager(
                experiment_dir=self.experiment_dir,
                repo_url=self.config.task_repo,
                commit=self.config.task_commit,
                repos_dir=repos_dir,
            )
            # Setup base repo (idempotent - checks for existing clone internally)
            self.workspace_manager.setup_base_repo()

    def _capture_experiment_baseline(self) -> None:
        """Capture pipeline baseline once at experiment level from a clean repo state."""
        assert self.experiment_dir is not None  # noqa: S101
        assert self.workspace_manager is not None  # noqa: S101
        self._setup_manager().capture_baseline(self.experiment_dir, self.workspace_manager)

    def _finalizer(self) -> CheckpointFinalizer:
        """Create a CheckpointFinalizer bound to current state."""
        return CheckpointFinalizer(self.config, self.results_base_dir)

    def _handle_experiment_interrupt(self, checkpoint_path: Path) -> None:
        """Handle graceful shutdown on interrupt."""
        self._finalizer().handle_experiment_interrupt(self.checkpoint, checkpoint_path)

    def _validate_filesystem_on_resume(self, current_state: ExperimentState) -> None:
        """Cross-validate filesystem against checkpoint state on resume."""
        if not self.experiment_dir:
            return
        self._finalizer().validate_filesystem_on_resume(self.experiment_dir, current_state)

    def _execute_tier_groups(
        self,
        tier_groups: list[list[TierID]],
        previous_baseline: TierBaseline | None = None,
    ) -> dict[TierID, TierResult]:
        """Execute all tier groups sequentially.

        Args:
            tier_groups: List of tier groups for execution
            previous_baseline: Optional baseline from previous tier

        Returns:
            Dictionary mapping tier IDs to their results

        """
        return ParallelTierRunner(
            config=self.config,
            tier_manager=self.tier_manager,
            experiment_dir=self.experiment_dir,
            run_tier_fn=self._run_tier,
            save_tier_result_fn=self._save_tier_result,
        ).execute_tier_groups(tier_groups, previous_baseline)

    def _create_baseline_from_tier_result(
        self,
        tier_id: TierID,
        tier_result: TierResult,
    ) -> TierBaseline | None:
        """Create a baseline from a tier result's best subtest.

        Args:
            tier_id: The tier the result belongs to.
            tier_result: The result from which to derive the baseline.

        Returns:
            TierBaseline for the best subtest, or None if no best subtest exists.

        """
        return ParallelTierRunner(
            config=self.config,
            tier_manager=self.tier_manager,
            experiment_dir=self.experiment_dir,
            run_tier_fn=self._run_tier,
            save_tier_result_fn=self._save_tier_result,
        ).create_baseline_from_tier_result(tier_id, tier_result)

    def _aggregate_results(
        self,
        tier_results: dict[TierID, TierResult],
        start_time: datetime,
    ) -> ExperimentResult:
        """Create experiment result from accumulated tier results.

        Used for both normal completion and interrupted (partial) results.

        Args:
            tier_results: Accumulated tier results
            start_time: Experiment start timestamp

        Returns:
            ExperimentResult with completed tiers

        """
        return self._result_writer().aggregate_results(self.config, tier_results, start_time)

    def _action_exp_initializing(self) -> None:
        """Handle INITIALIZING -> DIR_CREATED transition.

        No-op: setup was already done in _initialize_or_resume_experiment.
        """
        # experiment_dir and checkpoint were created/loaded in _initialize_or_resume_experiment
        pass

    def _action_exp_dir_created(self) -> None:
        """DIR_CREATED -> REPO_CLONED: Setup workspace and capture baseline."""
        self._setup_workspace()
        self._capture_experiment_baseline()

    def _action_exp_repo_cloned(self, tier_groups: list[list[TierID]]) -> None:
        """REPO_CLONED -> TIERS_RUNNING: Pre-flight checks and log tier groups.

        Args:
            tier_groups: Tier dependency groups for parallel execution.

        """
        # Single pre-flight rate limit check for the entire experiment
        from scylla.e2e.rate_limit import check_api_rate_limit_status, wait_for_rate_limit

        rate_limit_info = check_api_rate_limit_status()
        if rate_limit_info:
            logger.warning("Pre-flight rate limit detected, waiting...")
            if self.checkpoint and self.experiment_dir:
                checkpoint_path = self.experiment_dir / "checkpoint.json"
                wait_for_rate_limit(
                    rate_limit_info.retry_after_seconds,
                    self.checkpoint,
                    checkpoint_path,
                )

        logger.info(f"Tier groups for parallel execution: {tier_groups}")

    def _action_exp_tiers_running(
        self,
        tier_groups: list[list[TierID]],
        tier_results: dict[TierID, TierResult],
    ) -> None:
        """TIERS_RUNNING -> TIERS_COMPLETE: Execute all tier groups.

        Args:
            tier_groups: Tier dependency groups for execution.
            tier_results: Mutable dict updated in-place with execution results.

        """
        results = self._execute_tier_groups(tier_groups)
        tier_results.update(results)

    def _action_exp_tiers_complete(
        self,
        tier_results: dict[TierID, TierResult],
        start_time: datetime,
    ) -> None:
        """TIERS_COMPLETE -> REPORTS_GENERATED: Aggregate results and finalize.

        Args:
            tier_results: Accumulated tier results from TIERS_RUNNING.
            start_time: Experiment start timestamp for duration calculation.

        Raises:
            RuntimeError: If experiment_dir is not set.

        """
        if self.experiment_dir is None:
            raise RuntimeError("experiment_dir must be set before aggregating tier results")

        # Re-hydrate tier_results from disk if empty — occurs when ExperimentSM resumes
        # from TIERS_COMPLETE+, which skips _action_exp_tiers_running.
        if not tier_results and self.experiment_dir.exists():
            from scylla.e2e.rehydrate import load_experiment_tier_results

            rehydrated = load_experiment_tier_results(self.experiment_dir, self.config)
            tier_results.update(rehydrated)
            if rehydrated:
                logger.info(f"Re-hydrated {len(rehydrated)} tier results from disk")

        result = self._aggregate_results(tier_results, start_time)
        self._save_final_results(result)
        self._generate_report(result)
        self._last_experiment_result = result

    def _action_exp_reports_generated(self) -> None:
        """REPORTS_GENERATED -> COMPLETE: Mark checkpoint completed and log summary."""
        self._mark_checkpoint_completed()
        if self._last_experiment_result is not None:
            logger.info(
                f"✅ Experiment completed in "
                f"{self._last_experiment_result.total_duration_seconds:.1f}s, "
                f"total cost: ${self._last_experiment_result.total_cost:.2f}"
            )

    def _build_experiment_actions(
        self,
        tier_groups: list[list[TierID]],
        tier_results: dict[TierID, TierResult],
        start_time: datetime,
    ) -> dict[ExperimentState, Callable[[], None]]:
        """Build the ExperimentState -> Callable action map for ExperimentStateMachine.

        Each action corresponds to the work done when transitioning OUT of that state.
        Results are accumulated into the shared tier_results dict via closures.

        Args:
            tier_groups: Tier dependency groups computed before SM starts
            tier_results: Mutable dict accumulated by TIERS_RUNNING action
            start_time: Experiment start time for duration calculation

        Returns:
            Dict mapping ExperimentState to callable

        """
        return {
            ExperimentState.INITIALIZING: self._action_exp_initializing,
            ExperimentState.DIR_CREATED: self._action_exp_dir_created,
            ExperimentState.REPO_CLONED: lambda: self._action_exp_repo_cloned(tier_groups),
            ExperimentState.TIERS_RUNNING: lambda: self._action_exp_tiers_running(
                tier_groups, tier_results
            ),
            ExperimentState.TIERS_COMPLETE: lambda: self._action_exp_tiers_complete(
                tier_results, start_time
            ),
            ExperimentState.REPORTS_GENERATED: self._action_exp_reports_generated,
        }

    def run(self) -> ExperimentResult:  # noqa: C901  # orchestration with many retry/outcome paths
        """Run the complete E2E experiment with auto-resume support.

        Automatically resumes from checkpoint if one exists (unless --fresh flag).
        Checkpoints are saved after each completed run for crash recovery and
        rate limit pause/resume.

        Returns:
            ExperimentResult with all tier results and analysis.

        """
        from scylla.e2e.experiment_state_machine import ExperimentStateMachine

        start_time = datetime.now(timezone.utc)

        # Initialize or resume from checkpoint
        checkpoint_path = self._initialize_or_resume_experiment()

        # Update PID in checkpoint (important for zombie detection on resume)
        if self.checkpoint:
            self.checkpoint.pid = os.getpid()

        # Initialize resource manager and log pre-flight resource availability
        from scylla.e2e.health import log_resource_preflight
        from scylla.e2e.resource_manager import ResourceManager

        log_resource_preflight(fail_on_warn=self.config.fail_on_resource_check)
        if self._resource_manager is None:
            self._resource_manager = ResourceManager(
                max_workspaces=self.config.max_concurrent_workspaces,
                max_agents=self.config.max_concurrent_agents,
            )

        # Start heartbeat thread to prevent zombie detection on long runs
        from scylla.e2e.health import HeartbeatThread

        if self.checkpoint is None:
            raise RuntimeError("checkpoint must be set before starting heartbeat thread")
        heartbeat = HeartbeatThread(self.checkpoint, checkpoint_path, interval_seconds=30)
        heartbeat.start()

        # Compute tier groups up front (needed by action_repo_cloned and action_tiers_running)
        tier_groups = self._get_tier_groups(self.config.tiers_to_run)

        # Shared mutable state accumulated by the TIERS_RUNNING action
        tier_results: dict[TierID, TierResult] = {}

        # Pre-seed workspace: on resume from TIERS_RUNNING or later states,
        # action_dir_created will be skipped so we must set up workspace now.

        _current_exp_state = ExperimentState.INITIALIZING
        if self.checkpoint:
            with contextlib.suppress(ValueError):
                _current_exp_state = ExperimentState(self.checkpoint.experiment_state)

        _resume_states = {
            ExperimentState.TIERS_RUNNING,
            ExperimentState.TIERS_COMPLETE,
            ExperimentState.REPORTS_GENERATED,
        }
        if _current_exp_state in _resume_states:
            # Filesystem cross-validation: verify expected dirs exist before resuming
            self._validate_filesystem_on_resume(_current_exp_state)
            self._setup_workspace()

        # Build ExperimentStateMachine actions
        actions = self._build_experiment_actions(
            tier_groups=tier_groups,
            tier_results=tier_results,
            start_time=start_time,
        )

        if self.checkpoint is None:
            raise RuntimeError("checkpoint must be set before creating experiment state machine")
        esm = ExperimentStateMachine(self.checkpoint, checkpoint_path)

        try:
            esm.advance_to_completion(
                actions,
                until_state=self.config.until_experiment_state,
            )
        except KeyboardInterrupt:
            logger.warning("Shutdown requested (Ctrl+C), cleaning up...")
        except (
            Exception
        ) as e:  # broad catch: top-level experiment boundary; re-raised after logging
            logger.error(f"Experiment failed: {e}")
            raise
        finally:
            heartbeat.stop()
            heartbeat.join(timeout=5)

            if is_shutdown_requested():
                self._handle_experiment_interrupt(checkpoint_path)
            self._cleanup_pid_file()

        # Handle interrupt / partial results
        if is_shutdown_requested():
            logger.warning("Experiment interrupted - returning partial results")
            return self._aggregate_results(tier_results, start_time)

        # Fast path: experiment was already complete before the state machine ran.
        # No transitions occurred, no work done — skip expensive rehydrate.
        if _current_exp_state == ExperimentState.COMPLETE and self._last_experiment_result is None:
            logger.info("Experiment already complete — nothing to do")
            return self._aggregate_results(tier_results, start_time)

        # Handle early stop (--until-experiment)
        final_state = esm.get_state()
        if final_state not in (ExperimentState.COMPLETE, ExperimentState.FAILED) and (
            self.config.until_experiment_state and final_state == self.config.until_experiment_state
        ):
            logger.info(f"Stopped at --until-experiment {final_state.value}")
            return self._aggregate_results(tier_results, start_time)

        # Return result (populated by action_tiers_complete)
        if self._last_experiment_result is not None:
            return self._last_experiment_result

        # Fallback: aggregate from tier_results (e.g. resumed past TIERS_COMPLETE)
        if not tier_results and self.experiment_dir and self.experiment_dir.exists():
            from scylla.e2e.rehydrate import load_experiment_tier_results

            tier_results.update(load_experiment_tier_results(self.experiment_dir, self.config))
        return self._aggregate_results(tier_results, start_time)

    def _setup_manager(self) -> ExperimentSetupManager:
        """Create an ExperimentSetupManager bound to current state."""
        return ExperimentSetupManager(self.config, self.results_base_dir)

    def _build_tier_actions(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
        tier_ctx: TierContext,
    ) -> dict[TierState, Callable[[], None]]:
        """Build the TierState -> Callable action map for TierStateMachine.

        Results are accumulated into the shared TierContext via closures,
        allowing later actions to consume results from earlier ones.

        Args:
            tier_id: The tier to run
            baseline: Previous tier's winning baseline
            tier_ctx: Mutable TierContext for inter-action state

        Returns:
            Dict mapping TierState to callable

        """
        return TierActionBuilder(
            tier_id=tier_id,
            baseline=baseline,
            tier_ctx=tier_ctx,
            config=self.config,
            tier_manager=self.tier_manager,
            workspace_manager=self.workspace_manager,
            checkpoint=self.checkpoint,
            experiment_dir=self.experiment_dir,
            save_tier_result_fn=self._save_tier_result,
            resource_manager=self._resource_manager,
        ).build()

    def _run_tier(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
    ) -> TierResult:
        """Run a single tier's evaluation.

        Args:
            tier_id: The tier to run
            baseline: Previous tier's winning baseline

        Returns:
            TierResult with all sub-test results.

        """
        from scylla.e2e.tier_state_machine import TierStateMachine

        # Typed mutable namespace passed to closures in _build_tier_actions()
        tier_ctx = TierContext()

        checkpoint_path = (
            self.experiment_dir / "checkpoint.json"
            if self.checkpoint and self.experiment_dir
            else Path("/dev/null")
        )

        # If no checkpoint, build a minimal one for the state machine
        checkpoint = self.checkpoint
        if checkpoint is None:
            checkpoint = E2ECheckpoint(
                experiment_id=self.config.experiment_id,
                experiment_dir=str(self.experiment_dir or tempfile.gettempdir()),
                config_hash="",
                completed_runs={},
                started_at=datetime.now(timezone.utc).isoformat(),
                last_updated_at=datetime.now(timezone.utc).isoformat(),
                status=_STATUS_RUNNING,
                rate_limit_source=None,
                rate_limit_until=None,
                pause_count=0,
                pid=os.getpid(),
            )

        tsm = TierStateMachine(checkpoint, checkpoint_path)

        # On resume, action_pending() is skipped for tiers that are already past
        # PENDING in the checkpoint. Pre-populate tier_ctx so that later actions
        # (action_config_loaded, action_subtests_complete, etc.) which assert
        # tier_ctx.tier_config is not None do not fail with AssertionError.
        _tier_resume_state = tsm.get_state(tier_id.value)
        if _tier_resume_state not in (TierState.PENDING, TierState.COMPLETE, TierState.FAILED):
            logger.info(
                f"Resuming {tier_id.value} from {_tier_resume_state.value} — "
                "pre-loading tier config for resume"
            )
            _resume_tier_config = self.tier_manager.load_tier_config(
                tier_id, self.config.skip_agent_teams
            )
            if self.config.max_subtests is not None:
                _resume_tier_config.subtests = _resume_tier_config.subtests[
                    : self.config.max_subtests
                ]
            tier_ctx.tier_config = _resume_tier_config
            if self.experiment_dir:
                from scylla.e2e.paths import get_tier_dir

                tier_ctx.tier_dir = get_tier_dir(
                    self.experiment_dir, tier_id.value, completed=False
                )

        actions = self._build_tier_actions(
            tier_id=tier_id,
            baseline=baseline,
            tier_ctx=tier_ctx,
        )

        # Filesystem cross-validation on resume
        _tier_current = tsm.get_state(tier_id.value)
        if _tier_current == TierState.SUBTESTS_COMPLETE and self.experiment_dir:
            from scylla.e2e.paths import get_tier_dir

            tier_dir = get_tier_dir(self.experiment_dir, tier_id.value, completed=True)
            run_results = list(tier_dir.rglob("run_result.json")) if tier_dir.exists() else []
            if not run_results:
                logger.warning(
                    f"⚠️  Resuming {tier_id.value} from SUBTESTS_COMPLETE but no "
                    f"run_result.json found under {tier_dir}"
                )

        tsm.advance_to_completion(
            tier_id.value,
            actions,
            until_state=self.config.until_tier_state,
        )

        # Return result if available (may be absent if stopped early via until_tier_state)
        if tier_ctx.tier_result is not None:
            return tier_ctx.tier_result

        # If stopped early, build a minimal partial TierResult from whatever was accumulated
        from functools import reduce

        # Re-hydrate subtest_results from disk if empty — occurs when TierSM resumes
        # past CONFIG_LOADED and tier_result was never set (e.g. stopped early).
        subtest_results = tier_ctx.subtest_results
        if not subtest_results and self.experiment_dir:
            from scylla.e2e.paths import get_tier_dir
            from scylla.e2e.rehydrate import load_tier_subtest_results

            tier_dir = get_tier_dir(self.experiment_dir, tier_id.value, completed=True)
            if tier_dir.exists():
                subtest_results = load_tier_subtest_results(tier_dir, tier_id)
                tier_ctx.subtest_results = subtest_results
        selection = tier_ctx.selection
        end_time = datetime.now(timezone.utc)
        duration = (end_time - tier_ctx.start_time).total_seconds()

        token_stats = (
            reduce(
                lambda a, b: a + b,
                [s.token_stats for s in subtest_results.values()],
                TokenStats(),
            )
            if subtest_results
            else TokenStats()
        )

        return TierResult(
            tier_id=tier_id,
            subtest_results=subtest_results,
            best_subtest=selection.winning_subtest if selection else None,
            best_subtest_score=selection.winning_score if selection else 0.0,
            inherited_from=baseline,
            tiebreaker_needed=selection.tiebreaker_needed if selection else False,
            total_cost=sum(s.total_cost for s in subtest_results.values()),
            total_duration=duration,
            token_stats=token_stats,
        )

    def _save_tier_result(self, tier_id: TierID, result: TierResult) -> None:
        """Save tier results to file and generate hierarchical reports.

        Args:
            tier_id: The tier identifier
            result: The tier result

        """
        self._result_writer().save_tier_result(tier_id, result)

    def _save_final_results(self, result: ExperimentResult) -> None:
        """Save final experiment results.

        Args:
            result: The complete experiment result

        """
        self._result_writer().save_final_results(result)

    def _generate_report(self, result: ExperimentResult) -> None:
        """Generate hierarchical experiment reports.

        Args:
            result: The complete experiment result

        """
        self._result_writer().generate_report(result)

    def _find_existing_checkpoint(self) -> Path | None:
        """Find existing checkpoint file in results directory."""
        return self._finalizer().find_existing_checkpoint()

    def _write_pid_file(self) -> None:
        """Write PID file for status monitoring."""
        if self.experiment_dir:
            self._setup_manager().write_pid_file(self.experiment_dir)

    def _cleanup_pid_file(self) -> None:
        """Remove PID file on completion."""
        if self.experiment_dir:
            self._setup_manager().cleanup_pid_file(self.experiment_dir)

    def _mark_checkpoint_completed(self) -> None:
        """Mark checkpoint as completed."""
        if self.checkpoint and self.experiment_dir:
            self._finalizer().mark_checkpoint_completed(self.checkpoint, self.experiment_dir)


def run_experiment(
    config: ExperimentConfig,
    tiers_dir: Path,
    results_dir: Path,
    fresh: bool = False,
    resource_manager: ResourceManager | None = None,
) -> ExperimentResult:
    """Run an experiment with the given configuration.

    Args:
        config: Experiment configuration
        tiers_dir: Path to tier configurations
        results_dir: Path to results directory
        fresh: If True, ignore existing checkpoints and start fresh
        resource_manager: Optional shared ResourceManager for concurrency control.
            When running in batch mode, all experiments share the same instance.

    Returns:
        ExperimentResult with all results.

    """
    try:
        runner = E2ERunner(config, tiers_dir, results_dir, fresh=fresh)
        runner._resource_manager = resource_manager
        return runner.run()
    except (
        Exception
    ) as e:  # broad catch: public API boundary; provides rate-limit diagnostics before re-raising
        # Check if this is a rate limit error that needs handling
        if "rate limit" in str(e).lower() or "you've hit your limit" in str(e).lower():
            logger.error(f"Experiment failed due to rate limit: {e}")
            logger.error("The experiment encountered a Claude API rate limit.")
            logger.error(
                "Rate limits are automatically handled by the system when checkpoints are enabled."
            )
            logger.error(
                "Please run with checkpoint support (default) and the experiment "
                "will resume after the rate limit expires."
            )
            logger.error("If this persists, try reducing runs_per_subtest in your config.")

            # Re-raise with context
            raise RuntimeError(
                f"Experiment failed due to Claude API rate limit. "
                f"This indicates the API usage limit has been reached. "
                f"The system will automatically resume after the rate limit expires "
                f"when using checkpoints. "
                f"Error details: {e}"
            ) from e
        else:
            # Re-raise other errors as-is
            raise
