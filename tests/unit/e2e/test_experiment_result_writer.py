"""Unit tests for ExperimentResultWriter.

Tests the extracted experiment result saving/reporting class,
which encapsulates _save_tier_result, _save_final_results,
_generate_report, _find_frontier, _aggregate_token_stats,
and _aggregate_results from E2ERunner.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scylla.e2e.experiment_result_writer import ExperimentResultWriter
from scylla.e2e.models import (
    ExperimentConfig,
    ExperimentResult,
    SubTestResult,
    TierID,
    TierResult,
    TokenStats,
)
from scylla.e2e.paths import RESULT_FILE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> ExperimentConfig:
    """Minimal ExperimentConfig."""
    return ExperimentConfig(
        experiment_id="test-exp",
        task_repo="https://github.com/test/repo",
        task_commit="abc123",
        task_prompt_file=Path("/tmp/prompt.md"),
        language="python",
        tiers_to_run=[TierID.T0],
    )


def _make_subtest_result(
    subtest_id: str = "00",
    tier_id: TierID = TierID.T0,
    pass_rate: float = 0.5,
    mean_cost: float = 1.0,
    total_cost: float = 1.0,
    token_stats: TokenStats | None = None,
) -> SubTestResult:
    """Create a minimal SubTestResult."""
    return SubTestResult(
        subtest_id=subtest_id,
        tier_id=tier_id,
        runs=[],
        pass_rate=pass_rate,
        mean_cost=mean_cost,
        total_cost=total_cost,
        token_stats=token_stats or TokenStats(),
    )


def _make_tier_result(
    tier_id: TierID = TierID.T0,
    best_subtest: str | None = "00",
    total_cost: float = 1.0,
    pass_rate: float = 0.5,
    token_stats: TokenStats | None = None,
) -> TierResult:
    """Create a minimal TierResult."""
    subtest_results: dict[str, SubTestResult] = {}
    if best_subtest:
        subtest_results[best_subtest] = _make_subtest_result(
            subtest_id=best_subtest,
            tier_id=tier_id,
            pass_rate=pass_rate,
            mean_cost=total_cost,
            total_cost=total_cost,
            token_stats=token_stats,
        )
    return TierResult(
        tier_id=tier_id,
        subtest_results=subtest_results,
        best_subtest=best_subtest,
        best_subtest_score=0.8,
        total_cost=total_cost,
        token_stats=token_stats or TokenStats(),
    )


def _make_writer(
    experiment_dir: Path | None = None,
    tier_manager: MagicMock | None = None,
) -> ExperimentResultWriter:
    """Create ExperimentResultWriter with sensible defaults."""
    if tier_manager is None:
        tier_manager = MagicMock()
    return ExperimentResultWriter(
        experiment_dir=experiment_dir,
        tier_manager=tier_manager,
    )


# ---------------------------------------------------------------------------
# TestExperimentResultWriterConstruct
# ---------------------------------------------------------------------------


class TestExperimentResultWriterConstruct:
    """Tests for ExperimentResultWriter constructor."""

    def test_stores_experiment_dir(self, tmp_path: Path) -> None:
        """Constructor stores experiment_dir."""
        writer = _make_writer(experiment_dir=tmp_path)
        assert writer.experiment_dir == tmp_path

    def test_stores_tier_manager(self) -> None:
        """Constructor stores tier_manager."""
        mgr = MagicMock()
        writer = _make_writer(tier_manager=mgr)
        assert writer.tier_manager is mgr

    def test_experiment_dir_can_be_none(self) -> None:
        """experiment_dir may be None."""
        writer = _make_writer(experiment_dir=None)
        assert writer.experiment_dir is None


# ---------------------------------------------------------------------------
# TestSaveTierResult
# ---------------------------------------------------------------------------


class TestSaveTierResult:
    """Tests for ExperimentResultWriter.save_tier_result()."""

    def test_writes_result_json(self, tmp_path: Path) -> None:
        """save_tier_result writes result.json to tier directory."""
        writer = _make_writer(experiment_dir=tmp_path)
        result = _make_tier_result(TierID.T0)

        with (
            patch("scylla.persistence.experiment_result_writer.save_tier_report"),
            patch("scylla.persistence.experiment_result_writer.save_subtest_report"),
            patch(
                "scylla.persistence.experiment_result_writer.generate_tier_summary_table",
                return_value="table",
            ),
        ):
            writer.save_tier_result(TierID.T0, result)

        result_file = tmp_path / "completed" / TierID.T0.value / RESULT_FILE
        assert result_file.exists()
        data = json.loads(result_file.read_text())
        assert data["tier_id"] == "T0"

    def test_creates_tier_dir_if_missing(self, tmp_path: Path) -> None:
        """save_tier_result creates the tier directory."""
        writer = _make_writer(experiment_dir=tmp_path)
        result = _make_tier_result(TierID.T0)

        with (
            patch("scylla.persistence.experiment_result_writer.save_tier_report"),
            patch("scylla.persistence.experiment_result_writer.save_subtest_report"),
            patch(
                "scylla.persistence.experiment_result_writer.generate_tier_summary_table",
                return_value="t",
            ),
        ):
            writer.save_tier_result(TierID.T0, result)

        assert (tmp_path / "completed" / TierID.T0.value).is_dir()

    def test_writes_summary_md(self, tmp_path: Path) -> None:
        """save_tier_result writes summary.md."""
        writer = _make_writer(experiment_dir=tmp_path)
        result = _make_tier_result(TierID.T0)

        with (
            patch("scylla.persistence.experiment_result_writer.save_tier_report"),
            patch("scylla.persistence.experiment_result_writer.save_subtest_report"),
            patch(
                "scylla.persistence.experiment_result_writer.generate_tier_summary_table",
                return_value="summary_content",
            ),
        ):
            writer.save_tier_result(TierID.T0, result)

        summary_file = tmp_path / "completed" / TierID.T0.value / "summary.md"
        assert summary_file.exists()
        assert summary_file.read_text() == "summary_content"

    def test_noop_when_experiment_dir_is_none(self) -> None:
        """save_tier_result is a no-op when experiment_dir is None."""
        writer = _make_writer(experiment_dir=None)
        result = _make_tier_result(TierID.T0)

        # Should not raise
        writer.save_tier_result(TierID.T0, result)


# ---------------------------------------------------------------------------
# TestSaveFinalResults
# ---------------------------------------------------------------------------


class TestSaveFinalResults:
    """Tests for ExperimentResultWriter.save_final_results()."""

    def _make_experiment_result(self, config: ExperimentConfig, tmp_path: Path) -> ExperimentResult:
        """Create a minimal ExperimentResult."""
        tier_results = {TierID.T0: _make_tier_result(TierID.T0)}
        return ExperimentResult(
            config=config,
            tier_results=tier_results,
            best_overall_tier=TierID.T0,
            best_overall_subtest="00",
            frontier_cop=1.0,
            frontier_cop_tier=TierID.T0,
            total_cost=1.0,
            total_duration_seconds=10.0,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            token_stats=TokenStats(),
        )

    def test_writes_result_json(self, tmp_path: Path) -> None:
        """save_final_results writes result.json to experiment root."""
        config = _make_config()
        writer = _make_writer(experiment_dir=tmp_path)
        result = self._make_experiment_result(config, tmp_path)

        writer.save_final_results(result)

        assert (tmp_path / "result.json").exists()

    def test_writes_tier_comparison_json(self, tmp_path: Path) -> None:
        """save_final_results writes tier_comparison.json."""
        config = _make_config()
        writer = _make_writer(experiment_dir=tmp_path)
        result = self._make_experiment_result(config, tmp_path)

        writer.save_final_results(result)

        comparison_file = tmp_path / "tier_comparison.json"
        assert comparison_file.exists()
        data = json.loads(comparison_file.read_text())
        assert "T0" in data

    def test_tier_comparison_has_correct_structure(self, tmp_path: Path) -> None:
        """tier_comparison.json contains expected keys per tier."""
        config = _make_config()
        writer = _make_writer(experiment_dir=tmp_path)
        result = self._make_experiment_result(config, tmp_path)

        writer.save_final_results(result)

        data = json.loads((tmp_path / "tier_comparison.json").read_text())
        assert "best_subtest" in data["T0"]
        assert "best_score" in data["T0"]
        assert "total_cost" in data["T0"]
        assert "tiebreaker_needed" in data["T0"]

    def test_noop_when_experiment_dir_is_none(self) -> None:
        """save_final_results is a no-op when experiment_dir is None."""
        config = _make_config()
        writer = _make_writer(experiment_dir=None)
        result = ExperimentResult(
            config=config,
            tier_results={},
            best_overall_tier=None,
            best_overall_subtest=None,
            frontier_cop=float("inf"),
            frontier_cop_tier=None,
            total_cost=0.0,
            total_duration_seconds=0.0,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            token_stats=TokenStats(),
        )

        # Should not raise
        writer.save_final_results(result)


# ---------------------------------------------------------------------------
# TestGenerateReport
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Tests for ExperimentResultWriter.generate_report()."""

    def test_writes_summary_md(self, tmp_path: Path) -> None:
        """generate_report writes summary.md to experiment root."""
        config = _make_config()
        writer = _make_writer(experiment_dir=tmp_path)
        result = ExperimentResult(
            config=config,
            tier_results={TierID.T0: _make_tier_result(TierID.T0)},
            best_overall_tier=TierID.T0,
            best_overall_subtest="00",
            frontier_cop=1.0,
            frontier_cop_tier=TierID.T0,
            total_cost=1.0,
            total_duration_seconds=10.0,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            token_stats=TokenStats(),
        )

        with (
            patch("scylla.persistence.experiment_result_writer.save_experiment_report"),
            patch(
                "scylla.persistence.experiment_result_writer.generate_experiment_summary_table",
                return_value="exp_summary",
            ),
        ):
            writer.generate_report(result)

        assert (tmp_path / "summary.md").read_text() == "exp_summary"

    def test_early_return_when_experiment_dir_is_none(self) -> None:
        """generate_report returns early when experiment_dir is None."""
        writer = _make_writer(experiment_dir=None)
        config = _make_config()
        result = ExperimentResult(
            config=config,
            tier_results={},
            best_overall_tier=None,
            best_overall_subtest=None,
            frontier_cop=float("inf"),
            frontier_cop_tier=None,
            total_cost=0.0,
            total_duration_seconds=0.0,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            token_stats=TokenStats(),
        )

        # Should not raise or attempt file writes
        writer.generate_report(result)


# ---------------------------------------------------------------------------
# TestFindFrontier
# ---------------------------------------------------------------------------


class TestFindFrontier:
    """Tests for ExperimentResultWriter.find_frontier()."""

    def test_returns_none_none_for_empty_dict(self) -> None:
        """Returns (None, inf) for empty tier_results."""
        writer = _make_writer()
        tier_id, cop = writer.find_frontier({})
        assert tier_id is None
        assert cop == float("inf")

    def test_returns_lowest_cop_tier(self) -> None:
        """Returns tier with lowest cost_of_pass."""
        writer = _make_writer()
        t0_result = _make_tier_result(TierID.T0, pass_rate=0.5, total_cost=2.0)
        t1_result = _make_tier_result(TierID.T1, pass_rate=0.5, total_cost=0.5)

        tier_id, _cop = writer.find_frontier({TierID.T0: t0_result, TierID.T1: t1_result})

        # T1 has CoP = mean_cost / pass_rate = 0.5 / 0.5 = 1.0
        # T0 has CoP = 2.0 / 0.5 = 4.0
        assert tier_id == TierID.T1

    def test_skips_zero_pass_rate(self) -> None:
        """Skips tiers with pass_rate=0."""
        writer = _make_writer()
        t0_result = _make_tier_result(TierID.T0, pass_rate=0.0, total_cost=1.0)
        t1_result = _make_tier_result(TierID.T1, pass_rate=0.5, total_cost=1.0)

        tier_id, _cop = writer.find_frontier({TierID.T0: t0_result, TierID.T1: t1_result})

        assert tier_id == TierID.T1

    def test_skips_empty_subtest_results(self) -> None:
        """Skips tiers with no subtest_results."""
        writer = _make_writer()
        empty_result = _make_tier_result(TierID.T0, best_subtest=None)
        good_result = _make_tier_result(TierID.T1, pass_rate=0.5, total_cost=1.0)

        tier_id, _cop = writer.find_frontier({TierID.T0: empty_result, TierID.T1: good_result})

        assert tier_id == TierID.T1


# ---------------------------------------------------------------------------
# TestAggregateTokenStats
# ---------------------------------------------------------------------------


class TestAggregateTokenStats:
    """Tests for ExperimentResultWriter.aggregate_token_stats()."""

    def test_returns_empty_stats_for_empty_dict(self) -> None:
        """Returns empty TokenStats for empty tier_results."""
        writer = _make_writer()
        stats = writer.aggregate_token_stats({})
        assert stats == TokenStats()

    def test_sums_stats_from_all_tiers(self) -> None:
        """Sums token_stats across all tier results."""
        writer = _make_writer()
        t0_result = _make_tier_result(
            TierID.T0, token_stats=TokenStats(input_tokens=100, output_tokens=50)
        )
        t1_result = _make_tier_result(
            TierID.T1, token_stats=TokenStats(input_tokens=200, output_tokens=75)
        )

        stats = writer.aggregate_token_stats({TierID.T0: t0_result, TierID.T1: t1_result})

        assert stats.input_tokens == 300
        assert stats.output_tokens == 125

    def test_single_tier(self) -> None:
        """Returns stats from single tier unchanged."""
        writer = _make_writer()
        t0_result = _make_tier_result(
            TierID.T0, token_stats=TokenStats(input_tokens=50, output_tokens=25)
        )

        stats = writer.aggregate_token_stats({TierID.T0: t0_result})

        assert stats.input_tokens == 50
        assert stats.output_tokens == 25


# ---------------------------------------------------------------------------
# TestAggregateResults
# ---------------------------------------------------------------------------


class TestAggregateResults:
    """Tests for ExperimentResultWriter.aggregate_results()."""

    def test_returns_experiment_result(self) -> None:
        """aggregate_results returns an ExperimentResult."""
        config = _make_config()
        writer = _make_writer()
        tier_results = {TierID.T0: _make_tier_result(TierID.T0)}
        start_time = datetime.now(timezone.utc)

        result = writer.aggregate_results(config, tier_results, start_time)

        assert isinstance(result, ExperimentResult)

    def test_includes_all_tier_results(self) -> None:
        """aggregate_results includes all tier results."""
        config = _make_config()
        writer = _make_writer()
        tier_results = {
            TierID.T0: _make_tier_result(TierID.T0),
            TierID.T1: _make_tier_result(TierID.T1),
        }
        start_time = datetime.now(timezone.utc)

        result = writer.aggregate_results(config, tier_results, start_time)

        assert TierID.T0 in result.tier_results
        assert TierID.T1 in result.tier_results

    def test_aggregates_total_cost(self) -> None:
        """aggregate_results sums total_cost from all tiers."""
        config = _make_config()
        writer = _make_writer()
        tier_results = {
            TierID.T0: _make_tier_result(TierID.T0, total_cost=1.5),
            TierID.T1: _make_tier_result(TierID.T1, total_cost=2.5),
        }
        start_time = datetime.now(timezone.utc)

        result = writer.aggregate_results(config, tier_results, start_time)

        assert result.total_cost == pytest.approx(4.0)
