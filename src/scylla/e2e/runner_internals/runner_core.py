"""Thin E2ERunner orchestrator — delegates to four collaborators.

Responsibilities are split across:

* :class:`scylla.e2e.runner_internals.runner_setup.RunnerSetup` — init,
  config, workspace prep, baseline capture, PID file lifecycle.
* :class:`scylla.e2e.runner_internals.runner_resume.RunnerResume` —
  resume-from-checkpoint detection, validation, and CLI-flag merge.
* :class:`scylla.e2e.runner_internals.runner_execution.RunnerExecution` —
  tier dependency grouping, parallel tier execution, single-tier state
  machine orchestration.
* :class:`scylla.e2e.runner_internals.runner_finalization.RunnerFinalization`
  — result aggregation, report generation, metric emission, and checkpoint
  finalization.

``E2ERunner`` itself holds shared state (``config``, ``experiment_dir``,
``checkpoint``, ``workspace_manager``, ``tier_manager``) and exposes the
``run()`` entry point plus the ``_action_exp_*`` callbacks used by
``ExperimentStateMachine``.

Imports of ``load_checkpoint`` and ``validate_checkpoint_config`` are
retained at module scope to preserve existing ``patch`` targets in tests
under ``tests/unit/e2e/`` that reference
``scylla.e2e.runner_internals.runner_core.<name>``.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.checkpoint_finalizer import CheckpointFinalizer
from scylla.e2e.experiment_setup_manager import ExperimentSetupManager
from scylla.e2e.models import (
    ExperimentConfig,
    ExperimentResult,
    ExperimentState,
    TierBaseline,
    TierID,
    TierResult,
    TierState,
)
from scylla.e2e.runner_internals.runner_execution import RunnerExecution
from scylla.e2e.runner_internals.runner_finalization import RunnerFinalization
from scylla.e2e.runner_internals.runner_resume import RunnerResume
from scylla.e2e.runner_internals.runner_setup import RunnerSetup
from scylla.e2e.runner_internals.tier_context import TierContext
from scylla.e2e.shutdown import is_shutdown_requested
from scylla.metrics.emitter import MetricEmitter, get_default_emitter

# Imported at module scope so tests can patch
# ``scylla.e2e.runner_internals.runner_core.{load_checkpoint, validate_checkpoint_config}``
# (see tests/unit/e2e/test_runner.py). After PR #1940 the implementation lives in
# scylla.persistence.checkpoint; patching the e2e back-compat shim no longer
# affects the real call site.
from scylla.persistence.checkpoint import (
    E2ECheckpoint,
    load_checkpoint,
    validate_checkpoint_config,
)
from scylla.persistence.experiment_result_writer import ExperimentResultWriter
from scylla.utils.tracing import get_tracer

if TYPE_CHECKING:
    from scylla.e2e.checkpoint_finalizer import CheckpointFinalizer
    from scylla.e2e.resource_manager import ResourceManager
    from scylla.e2e.workspace_manager import WorkspaceManager

# Re-export for backwards compatibility / external imports.
__all__ = ["E2ERunner", "load_checkpoint", "validate_checkpoint_config"]

logger = logging.getLogger(__name__)
# Re-exported so tests under ``tests/unit/e2e/test_tracing_integration.py``
# can import ``_tracer`` from this module after the decomposition. The actual
# span creation lives in :mod:`scylla.e2e.runner_internals.runner_execution`.
_tracer = get_tracer(__name__)


class E2ERunner:
    """Thin orchestrator for E2E experiments.

    Holds shared state and delegates work to four collaborators:
    :class:`RunnerSetup`, :class:`RunnerResume`, :class:`RunnerExecution`,
    and :class:`RunnerFinalization`. The public method ``run()`` and the
    ``_action_exp_*`` callbacks remain here as orchestration glue.

    Example:
        >>> config = ExperimentConfig(
        ...     experiment_id="exp-001",
        ...     task_repo="https://github.com/example/repo",
        ...     task_commit="abc123",
        ...     task_prompt_file=Path("prompt.md"),
        ... )
        >>> runner = E2ERunner(config, Path("tiers"), Path("results"))
        >>> result = runner.run()

    """

    def __init__(
        self,
        config: ExperimentConfig,
        tiers_dir: Path,
        results_base_dir: Path,
        fresh: bool = False,
        emitter: MetricEmitter | None = None,
    ) -> None:
        """Initialize the E2E runner.

        Args:
            config: Experiment configuration.
            tiers_dir: Path to tier configurations.
            results_base_dir: Base directory for results.
            fresh: If True, ignore existing checkpoints and start fresh.
            emitter: Optional metric emitter for time-series export.

        """
        # Local import keeps the static module-load graph identical to the
        # previous shape (and avoids a circular import risk at decompose-time).
        from scylla.e2e.tier_manager import TierManager

        self.config = config
        self.tier_manager = TierManager(tiers_dir)
        self.results_base_dir = results_base_dir
        self.experiment_dir: Path | None = None
        self.workspace_manager: WorkspaceManager | None = None
        self.checkpoint: E2ECheckpoint | None = None
        self._fresh = fresh
        self._last_experiment_result: ExperimentResult | None = None
        self._resource_manager: ResourceManager | None = None
        self._emitter = emitter if emitter is not None else get_default_emitter()

        # Collaborators — each holds a back-reference to self.
        self.setup = RunnerSetup(self)
        self.resume = RunnerResume(self)
        self.execution = RunnerExecution(self)
        self.finalization = RunnerFinalization(self)

    # ------------------------------------------------------------------
    # Thin delegating methods — preserved for backwards compatibility with
    # existing callers and tests under ``tests/unit/e2e/``.
    # ------------------------------------------------------------------

    def _result_writer(self) -> ExperimentResultWriter:
        return self.finalization.result_writer()

    def _setup_manager(self) -> ExperimentSetupManager:
        return self.setup.setup_manager()

    def _finalizer(self) -> CheckpointFinalizer:
        return self.finalization.finalizer()

    @staticmethod
    def _get_tier_groups(tiers_to_run: list[TierID]) -> list[list[TierID]]:
        return RunnerExecution.get_tier_groups(tiers_to_run)

    def _log_checkpoint_resume(self, checkpoint_path: Path) -> None:
        self.resume.log_checkpoint_resume(checkpoint_path)

    def _load_checkpoint_and_config(self, checkpoint_path: Path) -> tuple[E2ECheckpoint, Path]:
        return self.resume.load_checkpoint_and_config(checkpoint_path)

    def _create_fresh_experiment(self) -> Path:
        return self.setup.create_fresh_experiment()

    def _initialize_or_resume_experiment(self) -> Path:
        return self.resume.initialize_or_resume_experiment()

    def _setup_workspace(self) -> None:
        self.setup.setup_workspace()

    def _capture_experiment_baseline(self) -> None:
        self.setup.capture_experiment_baseline()

    def _handle_experiment_interrupt(self, checkpoint_path: Path) -> None:
        self.finalization.handle_experiment_interrupt(checkpoint_path)

    def _validate_filesystem_on_resume(self, current_state: ExperimentState) -> None:
        self.finalization.validate_filesystem_on_resume(current_state)

    def _execute_tier_groups(
        self,
        tier_groups: list[list[TierID]],
        previous_baseline: TierBaseline | None = None,
    ) -> dict[TierID, TierResult]:
        return self.execution.execute_tier_groups(tier_groups, previous_baseline)

    def _create_baseline_from_tier_result(
        self,
        tier_id: TierID,
        tier_result: TierResult,
    ) -> TierBaseline | None:
        return self.execution.create_baseline_from_tier_result(tier_id, tier_result)

    def _aggregate_results(
        self,
        tier_results: dict[TierID, TierResult],
        start_time: datetime,
    ) -> ExperimentResult:
        return self.finalization.aggregate_results(tier_results, start_time)

    def _build_tier_actions(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
        tier_ctx: TierContext,
    ) -> dict[TierState, Callable[[], None]]:
        return self.execution.build_tier_actions(tier_id, baseline, tier_ctx)

    def _run_tier(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
    ) -> TierResult:
        return self.execution.run_tier(tier_id, baseline)

    def _run_tier_body(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
    ) -> TierResult:
        return self.execution.run_tier_body(tier_id, baseline)

    def _save_tier_result(self, tier_id: TierID, result: TierResult) -> None:
        self.finalization.save_tier_result(tier_id, result)

    def _save_final_results(self, result: ExperimentResult) -> None:
        self.finalization.save_final_results(result)

    def _generate_report(self, result: ExperimentResult) -> None:
        self.finalization.generate_report(result)

    def _find_existing_checkpoint(self) -> Path | None:
        return self.resume.find_existing_checkpoint()

    def _write_pid_file(self) -> None:
        self.setup.write_pid_file()

    def _cleanup_pid_file(self) -> None:
        self.setup.cleanup_pid_file()

    def _mark_checkpoint_completed(self) -> None:
        self.finalization.mark_checkpoint_completed()

    def _emit_experiment_metrics(
        self,
        tier_results: dict[TierID, TierResult],
        result: ExperimentResult,
    ) -> None:
        self.finalization.emit_experiment_metrics(tier_results, result)

    # ------------------------------------------------------------------
    # ExperimentStateMachine action callbacks.
    # ------------------------------------------------------------------

    def _action_exp_initializing(self) -> None:
        """Handle INITIALIZING -> DIR_CREATED (no-op; resume orchestration did the work)."""
        # experiment_dir and checkpoint were created/loaded earlier.

    def _action_exp_dir_created(self) -> None:
        """DIR_CREATED -> REPO_CLONED: setup workspace and capture baseline."""
        self._setup_workspace()
        self._capture_experiment_baseline()

    def _action_exp_repo_cloned(self, tier_groups: list[list[TierID]]) -> None:
        """REPO_CLONED -> TIERS_RUNNING: pre-flight checks and log tier groups."""
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
        """TIERS_RUNNING -> TIERS_COMPLETE: execute all tier groups."""
        results = self._execute_tier_groups(tier_groups)
        tier_results.update(results)

    def _action_exp_tiers_complete(
        self,
        tier_results: dict[TierID, TierResult],
        start_time: datetime,
    ) -> None:
        """TIERS_COMPLETE -> REPORTS_GENERATED: aggregate, save, and finalize."""
        if self.experiment_dir is None:
            raise RuntimeError("experiment_dir must be set before aggregating tier results")

        if not tier_results and self.experiment_dir.exists():
            from scylla.persistence.rehydrate import load_experiment_tier_results

            rehydrated = load_experiment_tier_results(self.experiment_dir, self.config)
            tier_results.update(rehydrated)
            if rehydrated:
                logger.info(f"Re-hydrated {len(rehydrated)} tier results from disk")

        result = self._aggregate_results(tier_results, start_time)
        self._save_final_results(result)
        self._generate_report(result)
        self._emit_experiment_metrics(tier_results, result)
        self._last_experiment_result = result

    def _action_exp_reports_generated(self) -> None:
        """REPORTS_GENERATED -> COMPLETE: mark checkpoint completed and log summary."""
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
        """Build the ExperimentState -> Callable action map."""
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

    # ------------------------------------------------------------------
    # Public entry point.
    # ------------------------------------------------------------------

    def run(self) -> ExperimentResult:  # noqa: C901  # top-level orchestration with branching outcome paths
        """Run the complete E2E experiment with auto-resume support."""
        from scylla.e2e.experiment_state_machine import ExperimentStateMachine
        from scylla.e2e.health import HeartbeatThread, log_resource_preflight
        from scylla.e2e.resource_manager import ResourceManager

        start_time = datetime.now(timezone.utc)

        checkpoint_path = self._initialize_or_resume_experiment()

        if self.checkpoint:
            self.checkpoint.pid = os.getpid()

        log_resource_preflight(fail_on_warn=self.config.fail_on_resource_check)
        if self._resource_manager is None:
            self._resource_manager = ResourceManager(
                max_workspaces=self.config.max_concurrent_workspaces,
                max_agents=self.config.max_concurrent_agents,
            )

        if self.checkpoint is None:
            raise RuntimeError("checkpoint must be set before starting heartbeat thread")
        heartbeat = HeartbeatThread(self.checkpoint, checkpoint_path, interval_seconds=30)
        heartbeat.start()

        tier_groups = self._get_tier_groups(self.config.tiers_to_run)
        tier_results: dict[TierID, TierResult] = {}

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
            self._validate_filesystem_on_resume(_current_exp_state)
            self._setup_workspace()

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
        except Exception as e:  # broad: top-level boundary
            logger.error(f"Experiment failed: {e}")
            raise
        finally:
            heartbeat.stop()
            heartbeat.join(timeout=5)

            if is_shutdown_requested():
                self._handle_experiment_interrupt(checkpoint_path)
            self._cleanup_pid_file()

        if is_shutdown_requested():
            logger.warning("Experiment interrupted - returning partial results")
            return self._aggregate_results(tier_results, start_time)

        if _current_exp_state == ExperimentState.COMPLETE and self._last_experiment_result is None:
            logger.info("Experiment already complete — nothing to do")
            return self._aggregate_results(tier_results, start_time)

        final_state = esm.get_state()
        if final_state not in (ExperimentState.COMPLETE, ExperimentState.FAILED) and (
            self.config.until_experiment_state and final_state == self.config.until_experiment_state
        ):
            logger.info(f"Stopped at --until-experiment {final_state.value}")
            return self._aggregate_results(tier_results, start_time)

        if self._last_experiment_result is not None:
            return self._last_experiment_result

        if not tier_results and self.experiment_dir and self.experiment_dir.exists():
            from scylla.persistence.rehydrate import load_experiment_tier_results

            tier_results.update(load_experiment_tier_results(self.experiment_dir, self.config))
        return self._aggregate_results(tier_results, start_time)
