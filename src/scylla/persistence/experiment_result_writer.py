"""Experiment result saving and report generation.

Encapsulates _save_tier_result, _save_final_results, _generate_report,
_find_frontier, _aggregate_token_stats, and _aggregate_results from E2ERunner.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import reduce
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.models import (
    ExperimentConfig,
    ExperimentResult,
    TierID,
    TierResult,
    TokenStats,
)
from scylla.e2e.paths import RESULT_FILE
from scylla.e2e.run_report import (
    generate_experiment_summary_table,
    generate_tier_summary_table,
    save_experiment_report,
    save_subtest_report,
    save_tier_report,
)

if TYPE_CHECKING:
    from scylla.e2e.tier_manager import TierManager

logger = logging.getLogger(__name__)


class ExperimentResultWriter:
    """Saves experiment results and generates hierarchical reports.

    Encapsulates all file-writing and report-generation concerns for
    both per-tier and experiment-level results. Stateless beyond the
    two constructor arguments; safe to instantiate per call if desired.
    """

    def __init__(
        self,
        experiment_dir: Path | None,
        tier_manager: TierManager,
    ) -> None:
        """Initialize ExperimentResultWriter.

        Args:
            experiment_dir: Root directory for this experiment's outputs (may be None).
            tier_manager: Provides tier-level operations (currently unused but kept for
                future extensibility and consistency with other collaborators).

        """
        self.experiment_dir = experiment_dir
        self.tier_manager = tier_manager

    def save_tier_result(self, tier_id: TierID, result: TierResult) -> None:
        """Save tier results to file and generate hierarchical reports.

        Generates:
        - result.json (detailed data)
        - report.json (summary with links)
        - report.md (human-readable)
        - Per-subtest reports
        - summary.md

        Args:
            tier_id: The tier identifier.
            result: The tier result.

        """
        if self.experiment_dir:
            from scylla.e2e.paths import get_tier_dir

            tier_dir = get_tier_dir(self.experiment_dir, tier_id.value, completed=True)
            tier_dir.mkdir(parents=True, exist_ok=True)

            # Save detailed result
            with open(tier_dir / RESULT_FILE, "w") as f:
                json.dump(result.to_dict(), f, indent=2)

            # Generate subtest reports
            for subtest_id, subtest_result in result.subtest_results.items():
                subtest_dir = tier_dir / subtest_id
                save_subtest_report(subtest_dir, subtest_id, subtest_result)

            # Generate tier report
            save_tier_report(tier_dir, tier_id.value, result)

            # Generate tier summary table
            tier_summary = generate_tier_summary_table(
                tier_id=tier_id.value,
                subtest_results=result.subtest_results,
            )
            (tier_dir / "summary.md").write_text(tier_summary)

    def save_final_results(self, result: ExperimentResult) -> None:
        """Save final experiment results.

        Saves result.json and tier_comparison.json to experiment root.

        Args:
            result: The complete experiment result.

        """
        if self.experiment_dir:
            # Save to root (not summary/ subdir)
            result.save(self.experiment_dir / "result.json")

            # Save tier comparison
            comparison = {
                tier_id.value: {
                    "best_subtest": tier_result.best_subtest,
                    "best_score": tier_result.best_subtest_score,
                    "total_cost": tier_result.total_cost,
                    "tiebreaker_needed": tier_result.tiebreaker_needed,
                }
                for tier_id, tier_result in result.tier_results.items()
            }

            with open(self.experiment_dir / "tier_comparison.json", "w") as f:
                json.dump(comparison, f, indent=2)

    def generate_report(self, result: ExperimentResult) -> None:
        """Generate hierarchical experiment reports.

        Generates:
        - report.json (summary with links to tier reports)
        - report.md (human-readable with links)
        - summary.md

        Args:
            result: The complete experiment result.

        """
        if not self.experiment_dir:
            return

        # Use the hierarchical report generator
        save_experiment_report(self.experiment_dir, result)

        # Generate experiment summary table
        experiment_summary = generate_experiment_summary_table(
            tier_results=result.tier_results,
        )
        (self.experiment_dir / "summary.md").write_text(experiment_summary)

        logger.info(f"Reports saved to {self.experiment_dir / 'report.md'}")

    def find_frontier(
        self,
        tier_results: dict[TierID, TierResult],
    ) -> tuple[TierID | None, float]:
        """Find the frontier tier (best cost-of-pass).

        Args:
            tier_results: All tier results.

        Returns:
            Tuple of (best tier ID, cost-of-pass). Returns (None, inf) for empty input.

        """
        best_tier: TierID | None = None
        best_cop = float("inf")

        for tier_id, result in tier_results.items():
            if not result.subtest_results:
                continue

            # Get best sub-test results
            best_subtest = result.subtest_results.get(result.best_subtest or "")
            if not best_subtest or best_subtest.pass_rate == 0:
                continue

            # Calculate cost-of-pass
            cop = best_subtest.mean_cost / best_subtest.pass_rate

            if cop < best_cop:
                best_cop = cop
                best_tier = tier_id

        return best_tier, best_cop

    def aggregate_token_stats(self, tier_results: dict[TierID, TierResult]) -> TokenStats:
        """Aggregate token statistics from all tier results.

        Args:
            tier_results: Dictionary mapping tier IDs to their results.

        Returns:
            Aggregated token statistics across all tiers. Returns empty
            TokenStats if tier_results is empty.

        """
        if not tier_results:
            return TokenStats()

        return reduce(
            lambda a, b: a + b,
            [t.token_stats for t in tier_results.values()],
            TokenStats(),
        )

    def aggregate_results(
        self,
        config: ExperimentConfig,
        tier_results: dict[TierID, TierResult],
        start_time: datetime,
    ) -> ExperimentResult:
        """Create experiment result from accumulated tier results.

        Used for both normal completion and interrupted (partial) results.

        Args:
            config: Experiment configuration.
            tier_results: Accumulated tier results.
            start_time: Experiment start timestamp.

        Returns:
            ExperimentResult with completed tiers.

        """
        end_time = datetime.now(timezone.utc)
        total_duration = (end_time - start_time).total_seconds()
        total_cost = sum(t.total_cost for t in tier_results.values())

        # Find frontier from completed tiers
        frontier_tier, frontier_cop = self.find_frontier(tier_results)

        # Aggregate token stats from completed tiers
        experiment_token_stats = self.aggregate_token_stats(tier_results)

        return ExperimentResult(
            config=config,
            tier_results=tier_results,
            best_overall_tier=frontier_tier,
            best_overall_subtest=(
                tier_results[frontier_tier].best_subtest if frontier_tier else None
            ),
            frontier_cop=frontier_cop,
            frontier_cop_tier=frontier_tier,
            total_cost=total_cost,
            total_duration_seconds=total_duration,
            started_at=start_time.isoformat(),
            completed_at=end_time.isoformat(),
            token_stats=experiment_token_stats,
        )
