"""RunnerExecution collaborator — experiment-execution loop and tier dispatch.

Owns: tier dependency grouping, parallel tier execution, single-tier
state-machine orchestration, and tier-action builder wiring.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from functools import reduce
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.persistence.checkpoint import E2ECheckpoint
from scylla.e2e.models import (
    TIER_DEPENDENCIES,
    TierBaseline,
    TierID,
    TierResult,
    TierState,
    TokenStats,
)
from scylla.e2e.parallel_tier_runner import ParallelTierRunner
from scylla.e2e.runner_internals.constants import _STATUS_RUNNING
from scylla.e2e.runner_internals.tier_context import TierContext
from scylla.e2e.tier_action_builder import TierActionBuilder
from scylla.utils.tracing import get_tracer

if TYPE_CHECKING:
    from scylla.e2e.runner_internals.runner_core import E2ERunner

logger = logging.getLogger(__name__)
_tracer = get_tracer(__name__)


class RunnerExecution:
    """Experiment-execution loop, tier dispatch, subtest fan-out."""

    def __init__(self, runner: E2ERunner) -> None:
        """Bind this collaborator to the owning :class:`E2ERunner`."""
        self._runner = runner

    @staticmethod
    def get_tier_groups(tiers_to_run: list[TierID]) -> list[list[TierID]]:
        """Group tiers by dependencies for parallel execution."""
        if not tiers_to_run:
            return []

        groups: list[list[TierID]] = []
        remaining = set(tiers_to_run)
        completed: set[TierID] = set()

        while remaining:
            ready = [
                tier
                for tier in remaining
                if all(
                    dep in completed or dep not in tiers_to_run for dep in TIER_DEPENDENCIES[tier]
                )
            ]

            if not ready:
                raise ValueError(
                    f"Unable to resolve tier dependencies. "
                    f"Remaining: {remaining}, Completed: {completed}"
                )

            groups.append(sorted(ready))
            completed.update(ready)
            remaining -= set(ready)

        return groups

    def _parallel_runner(self) -> ParallelTierRunner:
        runner = self._runner
        return ParallelTierRunner(
            config=runner.config,
            tier_manager=runner.tier_manager,
            experiment_dir=runner.experiment_dir,
            run_tier_fn=runner._run_tier,
            save_tier_result_fn=runner._save_tier_result,
        )

    def execute_tier_groups(
        self,
        tier_groups: list[list[TierID]],
        previous_baseline: TierBaseline | None = None,
    ) -> dict[TierID, TierResult]:
        """Execute all tier groups sequentially (each group runs in parallel)."""
        return self._parallel_runner().execute_tier_groups(tier_groups, previous_baseline)

    def create_baseline_from_tier_result(
        self,
        tier_id: TierID,
        tier_result: TierResult,
    ) -> TierBaseline | None:
        """Create a baseline from a tier result's best subtest."""
        return self._parallel_runner().create_baseline_from_tier_result(tier_id, tier_result)

    def build_tier_actions(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
        tier_ctx: TierContext,
    ) -> dict[TierState, Callable[[], None]]:
        """Build the TierState -> Callable action map for TierStateMachine."""
        runner = self._runner
        return TierActionBuilder(
            tier_id=tier_id,
            baseline=baseline,
            tier_ctx=tier_ctx,
            config=runner.config,
            tier_manager=runner.tier_manager,
            workspace_manager=runner.workspace_manager,
            checkpoint=runner.checkpoint,
            experiment_dir=runner.experiment_dir,
            save_tier_result_fn=runner._save_tier_result,
            resource_manager=runner._resource_manager,
        ).build()

    def run_tier(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
    ) -> TierResult:
        """Run a single tier's evaluation, wrapped in a tracing span."""
        runner = self._runner
        with _tracer.start_as_current_span(
            "scylla.tier",
            attributes={
                "scylla.tier_id": tier_id.value,
                "scylla.experiment_id": runner.config.experiment_id,
            },
        ) as _tier_span:
            try:
                return self.run_tier_body(tier_id, baseline)
            except Exception as e:
                _tier_span.record_exception(e)
                raise

    def run_tier_body(
        self,
        tier_id: TierID,
        baseline: TierBaseline | None,
    ) -> TierResult:
        """Body of :meth:`run_tier`, wrapped in a tracing span by the caller."""
        from scylla.e2e.tier_state_machine import TierStateMachine

        runner = self._runner
        tier_ctx = TierContext()

        checkpoint_path = (
            runner.experiment_dir / "checkpoint.json"
            if runner.checkpoint and runner.experiment_dir
            else Path("/dev/null")
        )

        checkpoint = runner.checkpoint
        if checkpoint is None:
            checkpoint = E2ECheckpoint(
                experiment_id=runner.config.experiment_id,
                experiment_dir=str(runner.experiment_dir or tempfile.gettempdir()),
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

        _tier_resume_state = tsm.get_state(tier_id.value)
        if _tier_resume_state not in (TierState.PENDING, TierState.COMPLETE, TierState.FAILED):
            logger.info(
                f"Resuming {tier_id.value} from {_tier_resume_state.value} — "
                "pre-loading tier config for resume"
            )
            _resume_tier_config = runner.tier_manager.load_tier_config(
                tier_id, runner.config.skip_agent_teams
            )
            if runner.config.max_subtests is not None:
                _resume_tier_config.subtests = _resume_tier_config.subtests[
                    : runner.config.max_subtests
                ]
            tier_ctx.tier_config = _resume_tier_config
            if runner.experiment_dir:
                from scylla.e2e.paths import get_tier_dir

                tier_ctx.tier_dir = get_tier_dir(
                    runner.experiment_dir, tier_id.value, completed=False
                )

        actions = self.build_tier_actions(
            tier_id=tier_id,
            baseline=baseline,
            tier_ctx=tier_ctx,
        )

        _tier_current = tsm.get_state(tier_id.value)
        if _tier_current == TierState.SUBTESTS_COMPLETE and runner.experiment_dir:
            from scylla.e2e.paths import get_tier_dir

            tier_dir = get_tier_dir(runner.experiment_dir, tier_id.value, completed=True)
            run_results = list(tier_dir.rglob("run_result.json")) if tier_dir.exists() else []
            if not run_results:
                logger.warning(
                    f"⚠️  Resuming {tier_id.value} from SUBTESTS_COMPLETE but no "
                    f"run_result.json found under {tier_dir}"
                )

        tsm.advance_to_completion(
            tier_id.value,
            actions,
            until_state=runner.config.until_tier_state,
        )

        if tier_ctx.tier_result is not None:
            return tier_ctx.tier_result

        subtest_results = tier_ctx.subtest_results
        if not subtest_results and runner.experiment_dir:
            from scylla.e2e.paths import get_tier_dir
            from scylla.persistence.rehydrate import load_tier_subtest_results

            tier_dir = get_tier_dir(runner.experiment_dir, tier_id.value, completed=True)
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
