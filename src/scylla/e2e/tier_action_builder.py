"""Tier state machine action builder.

Encapsulates the _build_tier_actions() logic from E2ERunner, building the
TierState -> Callable action map for TierStateMachine execution.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from functools import reduce
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.judge_selection import save_selection, select_best_subtest
from scylla.e2e.models import (
    ExperimentConfig,
    TierBaseline,
    TierID,
    TierResult,
    TierState,
    TokenStats,
)
from scylla.e2e.parallel_executor import run_tier_subtests_parallel

if TYPE_CHECKING:
    from scylla.e2e.resource_manager import ResourceManager
    from scylla.e2e.runner import TierContext
    from scylla.e2e.tier_manager import TierManager
    from scylla.e2e.workspace_manager import WorkspaceManager
    from scylla.persistence.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)


class TierActionBuilder:
    """Builds the TierState -> Callable action map for a single tier execution.

    Encapsulates all six closure-based action functions that drive the
    TierStateMachine through PENDING -> COMPLETE. State is accumulated
    progressively into the shared TierContext.

    Receives runner state as explicit constructor arguments (no runner reference)
    to avoid circular coupling.
    """

    def __init__(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
        tier_ctx: TierContext,
        config: ExperimentConfig,
        tier_manager: TierManager,
        workspace_manager: WorkspaceManager | None,
        checkpoint: E2ECheckpoint | None,
        experiment_dir: Path | None,
        save_tier_result_fn: Callable[[TierID, TierResult], None],
        resource_manager: ResourceManager | None = None,
    ) -> None:
        """Initialize TierActionBuilder with all required collaborators.

        Args:
            tier_id: The tier to run.
            baseline: Previous tier's winning baseline (may be None).
            tier_ctx: Mutable TierContext for inter-action state accumulation.
            config: Experiment configuration (read-only).
            tier_manager: Provides tier config loading and baseline retrieval.
            workspace_manager: Workspace lifecycle manager (may be None).
            checkpoint: Current E2ECheckpoint for persistence (may be None).
            experiment_dir: Root directory for this experiment's outputs (may be None).
            save_tier_result_fn: Callable injected from the runner to save tier results.
            resource_manager: Optional resource limiter for concurrency control.

        """
        self.tier_id = tier_id
        self.baseline = baseline
        self.tier_ctx = tier_ctx
        self.config = config
        self.tier_manager = tier_manager
        self.workspace_manager = workspace_manager
        self.checkpoint = checkpoint
        self.experiment_dir = experiment_dir
        self.save_tier_result_fn = save_tier_result_fn
        self.resource_manager = resource_manager

    def build(self) -> dict[TierState, Callable[[], None]]:
        """Build and return the TierState -> Callable action map.

        Each returned callable is a bound method of this builder.
        Actions are executed in state order by TierStateMachine.

        Returns:
            Dict mapping each TierState to its corresponding action callable.

        """
        return {
            TierState.PENDING: self._action_pending,
            TierState.CONFIG_LOADED: self._action_config_loaded,
            TierState.SUBTESTS_RUNNING: self._action_subtests_running,
            TierState.SUBTESTS_COMPLETE: self._action_subtests_complete,
            TierState.BEST_SELECTED: self._action_best_selected,
            TierState.REPORTS_GENERATED: self._action_reports_generated,
        }

    def _action_pending(self) -> None:
        """Handle PENDING -> CONFIG_LOADED: Load config, limit subtests, create tier dir."""
        tier_config = self.tier_manager.load_tier_config(self.tier_id, self.config.skip_agent_teams)

        if self.config.max_subtests is not None:
            original_count = len(tier_config.subtests)
            tier_config.subtests = tier_config.subtests[: self.config.max_subtests]
            if len(tier_config.subtests) < original_count:
                logger.info(
                    f"Limiting sub-tests from {original_count} to {len(tier_config.subtests)}"
                )

        logger.info(f"Tier {self.tier_id.value}: {len(tier_config.subtests)} sub-tests")

        if self.experiment_dir is None:
            raise RuntimeError("experiment_dir must be set before loading tier config")
        from scylla.e2e.paths import get_tier_dir

        tier_dir = get_tier_dir(self.experiment_dir, self.tier_id.value, completed=False)
        tier_dir.mkdir(parents=True, exist_ok=True)

        self.tier_ctx.tier_config = tier_config
        self.tier_ctx.tier_dir = tier_dir

    def _action_config_loaded(self) -> None:
        """Handle CONFIG_LOADED -> SUBTESTS_RUNNING: Execute all subtests."""
        if self.tier_ctx.tier_config is None:
            raise RuntimeError("tier_config must be set before running subtests")
        if self.tier_ctx.tier_dir is None:
            raise RuntimeError("tier_dir must be set before running subtests")
        if self.experiment_dir is None:
            raise RuntimeError("experiment_dir must be set before running subtests")
        checkpoint_path = self.experiment_dir / "checkpoint.json" if self.checkpoint else None
        subtest_results = run_tier_subtests_parallel(
            config=self.config,
            tier_id=self.tier_id,
            tier_config=self.tier_ctx.tier_config,
            tier_manager=self.tier_manager,
            workspace_manager=self.workspace_manager,  # type: ignore[arg-type]
            baseline=self.baseline,
            results_dir=self.tier_ctx.tier_dir,
            checkpoint=self.checkpoint,
            checkpoint_path=checkpoint_path,
            experiment_dir=self.experiment_dir,
            resource_manager=self.resource_manager,
        )
        self.tier_ctx.subtest_results = subtest_results

    def _action_subtests_running(self) -> None:
        """Handle SUBTESTS_RUNNING -> SUBTESTS_COMPLETE: Select best subtest."""
        if self.tier_ctx.tier_dir is None:
            raise RuntimeError("tier_dir must be set before selecting best subtest")

        self._rehydrate_subtest_results_if_needed()

        subtest_results = self.tier_ctx.subtest_results
        selection = select_best_subtest(subtest_results, judge_models=self.config.judge_models)

        if selection.winning_subtest in subtest_results:
            subtest_results[selection.winning_subtest].selected_as_best = True
            subtest_results[selection.winning_subtest].selection_reason = (
                selection.tiebreaker_result.reasoning
                if selection.tiebreaker_result
                else f"Highest median score ({selection.winning_score:.3f})"
            )

        # Save best_subtest.json to completed/ tier dir (where results live)
        if self.experiment_dir is not None:
            from scylla.e2e.paths import get_tier_dir

            completed_tier_dir = get_tier_dir(
                self.experiment_dir, self.tier_id.value, completed=True
            )
            completed_tier_dir.mkdir(parents=True, exist_ok=True)
            save_selection(selection, str(completed_tier_dir / "best_subtest.json"))
        else:
            save_selection(selection, str(self.tier_ctx.tier_dir / "best_subtest.json"))
        self.tier_ctx.selection = selection

    def _action_subtests_complete(self) -> None:
        """Handle SUBTESTS_COMPLETE -> BEST_SELECTED: Aggregate stats, build TierResult."""
        self._rehydrate_subtest_results_if_needed()
        self._rehydrate_selection_if_needed()

        if self.tier_ctx.selection is None:
            raise RuntimeError("selection must be set before aggregating subtest results")
        subtest_results = self.tier_ctx.subtest_results
        selection = self.tier_ctx.selection
        start_time = self.tier_ctx.start_time

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        token_stats = reduce(
            lambda a, b: a + b,
            [s.token_stats for s in subtest_results.values()],
            TokenStats(),
        )

        tier_result = TierResult(
            tier_id=self.tier_id,
            subtest_results=subtest_results,
            best_subtest=selection.winning_subtest,
            best_subtest_score=selection.winning_score,
            inherited_from=self.baseline,
            tiebreaker_needed=selection.tiebreaker_needed,
            total_cost=sum(s.total_cost for s in subtest_results.values()),
            total_duration=duration,
            token_stats=token_stats,
        )
        self.tier_ctx.tier_result = tier_result

    def _action_best_selected(self) -> None:
        """Handle BEST_SELECTED -> REPORTS_GENERATED: Save tier result and generate reports."""
        if self.tier_ctx.tier_result is None:
            raise RuntimeError("tier_result must be set before saving reports")
        self.save_tier_result_fn(self.tier_id, self.tier_ctx.tier_result)

    def _action_reports_generated(self) -> None:
        """Handle REPORTS_GENERATED -> COMPLETE: No-op (state machine marks complete)."""

    def _rehydrate_subtest_results_if_needed(self) -> None:
        """Reload subtest results from disk if the context is empty.

        This occurs when TierSM resumes from SUBTESTS_RUNNING+ and
        action_config_loaded was skipped.

        """
        if self.experiment_dir is None or self.tier_ctx.subtest_results:
            return
        from scylla.e2e.paths import get_tier_dir
        from scylla.persistence.rehydrate import load_tier_subtest_results

        completed_tier_dir = get_tier_dir(self.experiment_dir, self.tier_id.value, completed=True)
        if completed_tier_dir.exists():
            self.tier_ctx.subtest_results = load_tier_subtest_results(
                completed_tier_dir, self.tier_id
            )
            if self.tier_ctx.subtest_results:
                logger.info(
                    f"Re-hydrated {len(self.tier_ctx.subtest_results)} subtest results "
                    f"from disk for {self.tier_id.value}"
                )

    def _rehydrate_selection_if_needed(self) -> None:
        """Reload selection from disk if the context is empty.

        This occurs when TierSM resumes from SUBTESTS_COMPLETE+ and
        action_subtests_running was skipped.

        """
        if self.tier_ctx.selection is not None or self.experiment_dir is None:
            return
        from scylla.e2e.paths import get_tier_dir
        from scylla.persistence.rehydrate import load_tier_selection

        completed_tier_dir = get_tier_dir(self.experiment_dir, self.tier_id.value, completed=True)
        self.tier_ctx.selection = load_tier_selection(completed_tier_dir)
