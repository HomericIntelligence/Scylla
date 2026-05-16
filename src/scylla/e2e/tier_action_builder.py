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

    def build(self) -> dict[TierState, Callable[[], None]]:  # noqa: C901  # action map with many tier state branches
        """Build and return the TierState -> Callable action map.

        Each returned callable is a closure over this builder's attributes.
        Actions are executed in state order by TierStateMachine.

        Returns:
            Dict mapping each TierState to its corresponding action callable.

        """
        tier_id = self.tier_id
        baseline = self.baseline
        tier_ctx = self.tier_ctx
        config = self.config
        tier_manager = self.tier_manager
        workspace_manager = self.workspace_manager
        checkpoint = self.checkpoint
        experiment_dir = self.experiment_dir
        save_tier_result_fn = self.save_tier_result_fn

        def action_pending() -> None:
            # PENDING -> CONFIG_LOADED: Load config, limit subtests, create tier dir.
            tier_config = tier_manager.load_tier_config(tier_id, config.skip_agent_teams)

            if config.max_subtests is not None:
                original_count = len(tier_config.subtests)
                tier_config.subtests = tier_config.subtests[: config.max_subtests]
                if len(tier_config.subtests) < original_count:
                    logger.info(
                        f"Limiting sub-tests from {original_count} to {len(tier_config.subtests)}"
                    )

            logger.info(f"Tier {tier_id.value}: {len(tier_config.subtests)} sub-tests")

            if experiment_dir is None:
                raise RuntimeError("experiment_dir must be set before loading tier config")
            from scylla.e2e.paths import get_tier_dir

            tier_dir = get_tier_dir(experiment_dir, tier_id.value, completed=False)
            tier_dir.mkdir(parents=True, exist_ok=True)

            tier_ctx.tier_config = tier_config
            tier_ctx.tier_dir = tier_dir

        def action_config_loaded() -> None:
            # CONFIG_LOADED -> SUBTESTS_RUNNING: Execute all subtests sequentially.
            if tier_ctx.tier_config is None:
                raise RuntimeError("tier_config must be set before running subtests")
            if tier_ctx.tier_dir is None:
                raise RuntimeError("tier_dir must be set before running subtests")
            if experiment_dir is None:
                raise RuntimeError("experiment_dir must be set before running subtests")
            checkpoint_path = experiment_dir / "checkpoint.json" if checkpoint else None
            subtest_results = run_tier_subtests_parallel(
                config=config,
                tier_id=tier_id,
                tier_config=tier_ctx.tier_config,
                tier_manager=tier_manager,
                workspace_manager=workspace_manager,  # type: ignore[arg-type]  # pre-existing: Optional passed to non-Optional
                baseline=baseline,
                results_dir=tier_ctx.tier_dir,
                checkpoint=checkpoint,
                checkpoint_path=checkpoint_path,
                experiment_dir=experiment_dir,
                resource_manager=self.resource_manager,
            )
            tier_ctx.subtest_results = subtest_results

        def action_subtests_running() -> None:
            # SUBTESTS_RUNNING -> SUBTESTS_COMPLETE: Select best subtest.
            if tier_ctx.tier_dir is None:
                raise RuntimeError("tier_dir must be set before selecting best subtest")

            # Re-hydrate subtest_results from disk if empty — occurs when TierSM resumes
            # from SUBTESTS_RUNNING+, which skips action_config_loaded.
            # Rehydration reads from completed/ since runs are promoted after diff capture.
            if experiment_dir is not None and not tier_ctx.subtest_results:
                from scylla.e2e.paths import get_tier_dir
                from scylla.persistence.rehydrate import load_tier_subtest_results

                completed_tier_dir = get_tier_dir(experiment_dir, tier_id.value, completed=True)
                if completed_tier_dir.exists():
                    tier_ctx.subtest_results = load_tier_subtest_results(
                        completed_tier_dir, tier_id
                    )
                    if tier_ctx.subtest_results:
                        logger.info(
                            f"Re-hydrated {len(tier_ctx.subtest_results)} subtest results "
                            f"from disk for {tier_id.value}"
                        )

            subtest_results = tier_ctx.subtest_results

            selection = select_best_subtest(
                subtest_results,
                judge_models=config.judge_models,
            )

            if selection.winning_subtest in subtest_results:
                subtest_results[selection.winning_subtest].selected_as_best = True
                subtest_results[selection.winning_subtest].selection_reason = (
                    selection.tiebreaker_result.reasoning
                    if selection.tiebreaker_result
                    else f"Highest median score ({selection.winning_score:.3f})"
                )

            # Save best_subtest.json to completed/ tier dir (where results live)
            if experiment_dir is not None:
                from scylla.e2e.paths import get_tier_dir

                completed_tier_dir = get_tier_dir(experiment_dir, tier_id.value, completed=True)
                completed_tier_dir.mkdir(parents=True, exist_ok=True)
                save_selection(selection, str(completed_tier_dir / "best_subtest.json"))
            else:
                save_selection(selection, str(tier_ctx.tier_dir / "best_subtest.json"))
            tier_ctx.selection = selection

        def action_subtests_complete() -> None:
            # SUBTESTS_COMPLETE -> BEST_SELECTED: Aggregate token stats, build TierResult.

            # Re-hydrate subtest_results and selection from disk if empty — occurs when
            # TierSM resumes from SUBTESTS_COMPLETE+, which skips action_config_loaded
            # and action_subtests_running.
            # Rehydration reads from completed/ since runs are promoted after diff capture.
            if experiment_dir is not None and not tier_ctx.subtest_results:
                from scylla.e2e.paths import get_tier_dir
                from scylla.persistence.rehydrate import load_tier_subtest_results

                completed_tier_dir = get_tier_dir(experiment_dir, tier_id.value, completed=True)
                if completed_tier_dir.exists():
                    tier_ctx.subtest_results = load_tier_subtest_results(
                        completed_tier_dir, tier_id
                    )
                    if tier_ctx.subtest_results:
                        logger.info(
                            f"Re-hydrated {len(tier_ctx.subtest_results)} subtest results "
                            f"from disk for {tier_id.value}"
                        )

            if tier_ctx.selection is None and experiment_dir is not None:
                from scylla.e2e.paths import get_tier_dir
                from scylla.persistence.rehydrate import load_tier_selection

                completed_tier_dir = get_tier_dir(experiment_dir, tier_id.value, completed=True)
                tier_ctx.selection = load_tier_selection(completed_tier_dir)

            if tier_ctx.selection is None:
                raise RuntimeError("selection must be set before aggregating subtest results")
            subtest_results = tier_ctx.subtest_results
            selection = tier_ctx.selection
            start_time = tier_ctx.start_time

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            token_stats = reduce(
                lambda a, b: a + b,
                [s.token_stats for s in subtest_results.values()],
                TokenStats(),
            )

            tier_result = TierResult(
                tier_id=tier_id,
                subtest_results=subtest_results,
                best_subtest=selection.winning_subtest,
                best_subtest_score=selection.winning_score,
                inherited_from=baseline,
                tiebreaker_needed=selection.tiebreaker_needed,
                total_cost=sum(s.total_cost for s in subtest_results.values()),
                total_duration=duration,
                token_stats=token_stats,
            )
            tier_ctx.tier_result = tier_result

        def action_best_selected() -> None:
            # BEST_SELECTED -> REPORTS_GENERATED: Save tier result and generate reports.
            if tier_ctx.tier_result is None:
                raise RuntimeError("tier_result must be set before saving reports")
            save_tier_result_fn(tier_id, tier_ctx.tier_result)

        def action_reports_generated() -> None:
            # REPORTS_GENERATED -> COMPLETE: No-op (state machine marks complete).
            pass

        return {
            TierState.PENDING: action_pending,
            TierState.CONFIG_LOADED: action_config_loaded,
            TierState.SUBTESTS_RUNNING: action_subtests_running,
            TierState.SUBTESTS_COMPLETE: action_subtests_complete,
            TierState.BEST_SELECTED: action_best_selected,
            TierState.REPORTS_GENERATED: action_reports_generated,
        }
