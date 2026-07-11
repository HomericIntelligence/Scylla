"""Tests for Markdown report generator."""

import tempfile
from pathlib import Path

import pytest

from scylla.reporting.markdown import (
    MarkdownReportGenerator,
    ReportData,
    SensitivityAnalysis,
    TierMetrics,
    TransitionAssessment,
    create_report_data,
    create_tier_metrics,
)


def make_tier_metrics(
    tier_id: str = "T0",
    tier_name: str = "T0 (Vanilla)",
    pass_rate_median: float = 0.8,
    impl_rate_median: float = 0.75,
    composite_median: float = 0.775,
    cost_of_pass_median: float = 1.0,
    consistency_std_dev: float = 0.1,
    uplift: float = 0.0,
) -> TierMetrics:
    """Create test TierMetrics."""
    return TierMetrics(
        tier_id=tier_id,
        tier_name=tier_name,
        pass_rate_median=pass_rate_median,
        impl_rate_median=impl_rate_median,
        composite_median=composite_median,
        cost_of_pass_median=cost_of_pass_median,
        consistency_std_dev=consistency_std_dev,
        uplift=uplift,
    )


class TestTierMetrics:
    """Tests for TierMetrics dataclass."""

    def test_create(self) -> None:
        """Test Create."""
        metrics = TierMetrics(
            tier_id="T1",
            tier_name="T1 (Prompted)",
            pass_rate_median=0.9,
            impl_rate_median=0.85,
            composite_median=0.875,
            cost_of_pass_median=1.5,
            consistency_std_dev=0.08,
            uplift=0.13,
        )
        assert metrics.tier_id == "T1"
        assert metrics.pass_rate_median == pytest.approx(0.9)

    def test_default_uplift(self) -> None:
        """Test Default uplift."""
        metrics = make_tier_metrics()
        assert metrics.uplift == pytest.approx(0.0)


class TestSensitivityAnalysis:
    """Tests for SensitivityAnalysis dataclass."""

    def test_create(self) -> None:
        """Test Create."""
        analysis = SensitivityAnalysis(
            pass_rate_variance=0.05,
            impl_rate_variance=0.03,
            cost_variance=0.10,
        )
        assert analysis.pass_rate_variance == pytest.approx(0.05)

    def test_get_sensitivity_level_low(self) -> None:
        """Test Get sensitivity level low."""
        analysis = SensitivityAnalysis(0.02, 0.02, 0.02)
        assert analysis.get_sensitivity_level(0.02) == "low"

    def test_get_sensitivity_level_medium(self) -> None:
        """Test Get sensitivity level medium."""
        analysis = SensitivityAnalysis(0.10, 0.10, 0.10)
        assert analysis.get_sensitivity_level(0.10) == "medium"

    def test_get_sensitivity_level_high(self) -> None:
        """Test Get sensitivity level high."""
        analysis = SensitivityAnalysis(0.20, 0.20, 0.20)
        assert analysis.get_sensitivity_level(0.20) == "high"


class TestTransitionAssessment:
    """Tests for TransitionAssessment dataclass."""

    def test_create(self) -> None:
        """Test Create."""
        assessment = TransitionAssessment(
            from_tier="T0",
            to_tier="T1",
            pass_rate_delta=0.1,
            impl_rate_delta=0.15,
            cost_delta=0.50,
            worth_it=True,
        )
        assert assessment.from_tier == "T0"
        assert assessment.worth_it is True


class TestReportData:
    """Tests for ReportData dataclass."""

    def test_create_minimal(self) -> None:
        """Test Create minimal."""
        data = ReportData(
            test_id="001-test",
            test_name="Test Name",
            timestamp="2024-01-15T14:30:00Z",
            runs_per_tier=10,
            judge_model="claude-opus-4-6",
        )
        assert data.test_id == "001-test"
        assert data.tiers == []
        assert data.recommendations == []

    def test_create_with_tiers(self) -> None:
        """Test Create with tiers."""
        data = ReportData(
            test_id="001-test",
            test_name="Test Name",
            timestamp="2024-01-15T14:30:00Z",
            runs_per_tier=10,
            judge_model="claude-opus-4-6",
            tiers=[make_tier_metrics()],
        )
        assert len(data.tiers) == 1

    def test_create_with_sensitivity(self) -> None:
        """Test Create with sensitivity."""
        data = ReportData(
            test_id="001-test",
            test_name="Test Name",
            timestamp="2024-01-15T14:30:00Z",
            runs_per_tier=10,
            judge_model="claude-opus-4-6",
            sensitivity=SensitivityAnalysis(0.05, 0.03, 0.10),
        )
        assert data.sensitivity is not None


class TestMarkdownReportGeneratorHelpers:
    """Tests for MarkdownReportGenerator helper methods."""

    def test_find_best_quality_tier(self) -> None:
        """Test Find best quality tier."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        tiers = [
            make_tier_metrics(tier_id="T0", composite_median=0.7),
            make_tier_metrics(tier_id="T1", composite_median=0.9),
            make_tier_metrics(tier_id="T2", composite_median=0.8),
        ]
        best = generator._find_best_quality_tier(tiers)

        assert best is not None
        assert best.tier_id == "T1"

    def test_find_best_quality_tier_empty(self) -> None:
        """Test Find best quality tier empty."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        best = generator._find_best_quality_tier([])
        assert best is None

    def test_find_best_cost_tier(self) -> None:
        """Test Find best cost tier."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        tiers = [
            make_tier_metrics(tier_id="T0", cost_of_pass_median=2.0),
            make_tier_metrics(tier_id="T1", cost_of_pass_median=1.0),
            make_tier_metrics(tier_id="T2", cost_of_pass_median=3.0),
        ]
        best = generator._find_best_cost_tier(tiers)

        assert best is not None
        assert best.tier_id == "T1"

    def test_find_best_cost_tier_ignores_infinity(self) -> None:
        """Test Find best cost tier ignores infinity."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        tiers = [
            make_tier_metrics(tier_id="T0", cost_of_pass_median=float("inf")),
            make_tier_metrics(tier_id="T1", cost_of_pass_median=1.0),
        ]
        best = generator._find_best_cost_tier(tiers)

        assert best is not None
        assert best.tier_id == "T1"

    def test_find_most_consistent_tier(self) -> None:
        """Test Find most consistent tier."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        tiers = [
            make_tier_metrics(tier_id="T0", consistency_std_dev=0.15),
            make_tier_metrics(tier_id="T1", consistency_std_dev=0.05),
            make_tier_metrics(tier_id="T2", consistency_std_dev=0.10),
        ]
        best = generator._find_most_consistent_tier(tiers)

        assert best is not None
        assert best.tier_id == "T1"

    def test_format_percentage(self) -> None:
        """Test Format percentage."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        assert generator._format_percentage(0.85) == "85.0%"
        assert generator._format_percentage(1.0) == "100.0%"
        assert generator._format_percentage(0.0) == "0.0%"

    def test_format_cost(self) -> None:
        """Test Format cost."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        assert generator._format_cost(1.50) == "$1.50"
        assert generator._format_cost(0.0) == "$0.00"
        assert generator._format_cost(float("inf")) == "∞"


class TestMarkdownReportGeneratorSections:
    """Tests for individual report sections."""

    def test_generate_header(self) -> None:
        """Test Generate header."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        data = create_report_data(
            test_id="001-test",
            test_name="Test Name",
            timestamp="2024-01-15T14:30:00Z",
        )
        header = generator._generate_header(data)

        assert "# Evaluation Report: Test Name" in header
        assert "**Test ID**: 001-test" in header
        assert "2024-01-15T14:30:00Z" in header

    def test_generate_executive_summary(self) -> None:
        """Test Generate executive summary."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        data = create_report_data(
            test_id="001-test",
            test_name="Test Name",
        )
        data.tiers = [
            make_tier_metrics(tier_id="T0", tier_name="T0 (Vanilla)"),
            make_tier_metrics(
                tier_id="T1",
                tier_name="T1 (Prompted)",
                composite_median=0.9,
            ),
        ]
        data.key_finding = "T1 provides significant improvement."

        summary = generator._generate_executive_summary(data)

        assert "## Executive Summary" in summary
        assert "Winner by Quality" in summary
        assert "T1 (Prompted)" in summary
        assert "T1 provides significant improvement." in summary

    def test_generate_tier_comparison(self) -> None:
        """Test Generate tier comparison."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        data = create_report_data(
            test_id="001-test",
            test_name="Test Name",
        )
        data.tiers = [
            make_tier_metrics(tier_id="T0", tier_name="T0 (Vanilla)"),
            make_tier_metrics(
                tier_id="T1",
                tier_name="T1 (Prompted)",
                uplift=0.15,
            ),
        ]

        comparison = generator._generate_tier_comparison(data)

        assert "## Tier Comparison" in comparison
        assert "| Tier | Pass Rate |" in comparison
        assert "T0 (Vanilla)" in comparison
        assert "T1 (Prompted)" in comparison
        assert "+15.0%" in comparison

    def test_generate_tier_comparison_empty(self) -> None:
        """Test Generate tier comparison empty."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        data = create_report_data(test_id="001-test", test_name="Test Name")

        comparison = generator._generate_tier_comparison(data)
        assert comparison == ""

    def test_generate_sensitivity_analysis(self) -> None:
        """Test Generate sensitivity analysis."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        data = create_report_data(test_id="001-test", test_name="Test Name")
        data.sensitivity = SensitivityAnalysis(0.05, 0.03, 0.10)
        data.transitions = [
            TransitionAssessment("T0", "T1", 0.1, 0.15, 0.5, True),
        ]

        analysis = generator._generate_sensitivity_analysis(data)

        assert "## Prompt Sensitivity Analysis" in analysis
        assert "Variance Metrics" in analysis
        assert "low sensitivity" in analysis
        assert "T0 → T1" in analysis
        assert "worth it" in analysis

    def test_generate_recommendations(self) -> None:
        """Test Generate recommendations."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        data = create_report_data(test_id="001-test", test_name="Test Name")
        data.recommendations = [
            "Use T1 for this task type.",
            "Consider cost constraints for high-volume use.",
        ]

        recommendations = generator._generate_recommendations(data)

        assert "## Recommendations" in recommendations
        assert "1. Use T1 for this task type." in recommendations
        assert "2. Consider cost constraints" in recommendations


class TestMarkdownReportGeneratorFullReport:
    """Tests for full report generation."""

    def test_generate_report(self) -> None:
        """Test Generate report."""
        generator = MarkdownReportGenerator(Path("/tmp"))
        data = create_report_data(
            test_id="001-test",
            test_name="Convert Justfile to Makefile",
            timestamp="2024-01-15T14:30:00Z",
        )
        data.tiers = [
            make_tier_metrics(tier_id="T0", tier_name="T0 (Vanilla)"),
            make_tier_metrics(
                tier_id="T1",
                tier_name="T1 (Prompted)",
                composite_median=0.85,
                uplift=0.10,
            ),
        ]
        data.key_finding = "Prompting improves quality by 10%."
        data.recommendations = ["Use T1 for production."]

        report = generator.generate_report(data)

        # Verify all major sections are present
        assert "# Evaluation Report:" in report
        assert "## Executive Summary" in report
        assert "## Tier Comparison" in report
        assert "## Recommendations" in report
        assert "*Generated by Scylla Agent Testing Framework*" in report

    def test_write_report(self) -> None:
        """Test Write report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MarkdownReportGenerator(Path(tmpdir))
            data = create_report_data(
                test_id="001-test",
                test_name="Test Name",
            )
            data.tiers = [make_tier_metrics()]

            output_path = generator.write_report(data)

            assert output_path.exists()
            assert output_path.name == "report.md"
            expected_path = Path(tmpdir) / "001-test" / "report.md"
            assert output_path == expected_path

            # Verify content
            content = output_path.read_text()
            assert "# Evaluation Report:" in content


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_tier_metrics(self) -> None:
        """Test Create tier metrics."""
        metrics = create_tier_metrics(
            tier_id="T1",
            tier_name="T1 (Prompted)",
            pass_rate_median=0.9,
            impl_rate_median=0.85,
            composite_median=0.875,
            cost_of_pass_median=1.5,
            consistency_std_dev=0.08,
            uplift=0.13,
        )
        assert metrics.tier_id == "T1"
        assert metrics.uplift == 0.13

    def test_create_report_data(self) -> None:
        """Test Create report data."""
        data = create_report_data(
            test_id="001-test",
            test_name="Test Name",
            runs_per_tier=10,
            timestamp="2024-01-15T14:30:00Z",
        )
        assert data.test_id == "001-test"
        assert data.runs_per_tier == 10

    def test_create_report_data_auto_timestamp(self) -> None:
        """Test Create report data auto timestamp."""
        data = create_report_data(
            test_id="001-test",
            test_name="Test Name",
        )
        assert data.timestamp is not None
        assert data.timestamp.endswith("Z")
