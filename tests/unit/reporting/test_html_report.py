"""Tests for HTML report generator."""

import tempfile
from pathlib import Path

from scylla.reporting.html_report import HtmlReportGenerator
from scylla.reporting.markdown import (
    ReportData,
    SensitivityAnalysis,
    TierMetrics,
    TransitionAssessment,
)


def _make_report_data(test_id: str = "test-001") -> ReportData:
    """Create minimal ReportData for testing."""
    return ReportData(
        test_id=test_id,
        test_name="Test 001",
        timestamp="2025-01-01T00:00:00Z",
        runs_per_tier=10,
        judge_model="claude-opus-4-6",
    )


def _make_tier() -> TierMetrics:
    """Create a sample TierMetrics."""
    return TierMetrics(
        tier_id="T0",
        tier_name="Vanilla",
        pass_rate_median=0.5,
        impl_rate_median=0.6,
        composite_median=0.55,
        cost_of_pass_median=2.50,
        consistency_std_dev=0.1,
        uplift=0.0,
    )


class TestHtmlReportGenerator:
    """Tests for HtmlReportGenerator."""

    def test_get_report_dir(self) -> None:
        """Report dir is base_dir / test_id."""
        gen = HtmlReportGenerator(Path("/reports"))
        assert gen.get_report_dir("test-001") == Path("/reports/test-001")

    def test_generate_report_returns_html(self) -> None:
        """generate_report returns valid HTML document."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        result = gen.generate_report(data)
        assert result.startswith("<!DOCTYPE html>")
        assert "</html>" in result

    def test_generate_report_contains_metadata(self) -> None:
        """Report includes test metadata."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        result = gen.generate_report(data)
        assert "Test 001" in result
        assert "test-001" in result
        assert "2025-01-01T00:00:00Z" in result
        assert "claude-opus-4-6" in result

    def test_generate_report_contains_tier_table(self) -> None:
        """Report includes tier comparison table when tiers are present."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        data.tiers = [_make_tier()]
        result = gen.generate_report(data)
        assert "<table>" in result
        assert "Vanilla" in result
        assert "50.0%" in result

    def test_generate_report_no_tiers(self) -> None:
        """Report is valid even without tier data."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        result = gen.generate_report(data)
        assert "Tier Comparison" not in result

    def test_generate_report_inf_cost(self) -> None:
        """Infinity cost renders as the infinity symbol."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        tier = _make_tier()
        tier.cost_of_pass_median = float("inf")
        data.tiers = [tier]
        result = gen.generate_report(data)
        assert "&infin;" in result

    def test_generate_report_executive_summary(self) -> None:
        """Executive summary shows winners when tiers are present."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        data.tiers = [_make_tier()]
        result = gen.generate_report(data)
        assert "Winner by Quality" in result
        assert "Winner by Cost Efficiency" in result
        assert "Winner by Consistency" in result

    def test_generate_report_key_finding(self) -> None:
        """Key finding is rendered when present."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        data.key_finding = "T2 outperforms T0 significantly."
        result = gen.generate_report(data)
        assert "T2 outperforms T0 significantly." in result

    def test_generate_report_sensitivity_analysis(self) -> None:
        """Sensitivity analysis section is rendered when present."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        data.sensitivity = SensitivityAnalysis(
            pass_rate_variance=0.03,
            impl_rate_variance=0.10,
            cost_variance=0.20,
        )
        result = gen.generate_report(data)
        assert "Prompt Sensitivity Analysis" in result
        assert "low sensitivity" in result
        assert "medium sensitivity" in result
        assert "high sensitivity" in result

    def test_generate_report_transitions(self) -> None:
        """Transition assessments are rendered when present."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        data.sensitivity = SensitivityAnalysis(
            pass_rate_variance=0.05,
            impl_rate_variance=0.05,
            cost_variance=0.05,
        )
        data.transitions = [
            TransitionAssessment(
                from_tier="T0",
                to_tier="T1",
                pass_rate_delta=0.15,
                impl_rate_delta=0.10,
                cost_delta=1.50,
                worth_it=True,
            )
        ]
        result = gen.generate_report(data)
        assert "Tier Uplift Analysis" in result
        assert "worth it" in result

    def test_generate_report_recommendations(self) -> None:
        """Recommendations section is rendered when present."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        data.recommendations = ["Use T2 for production.", "Monitor costs closely."]
        result = gen.generate_report(data)
        assert "Recommendations" in result
        assert "Use T2 for production." in result
        assert "Monitor costs closely." in result

    def test_generate_report_escapes_html(self) -> None:
        """HTML special characters in data are escaped."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        data.test_name = "<script>alert('xss')</script>"
        result = gen.generate_report(data)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_generate_report_self_contained(self) -> None:
        """Report contains embedded CSS (self-contained)."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        result = gen.generate_report(data)
        assert "<style>" in result

    def test_generate_report_footer(self) -> None:
        """Report contains the Scylla footer."""
        gen = HtmlReportGenerator(Path("/tmp"))
        data = _make_report_data()
        result = gen.generate_report(data)
        assert "Scylla Agent Testing Framework" in result

    def test_write_report_creates_file(self) -> None:
        """write_report creates report.html in the correct directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = HtmlReportGenerator(Path(tmpdir))
            data = _make_report_data()
            path = gen.write_report(data)

            assert path.exists()
            assert path.name == "report.html"
            assert path.parent.name == "test-001"

            content = path.read_text()
            assert "<!DOCTYPE html>" in content

    def test_write_report_creates_directories(self) -> None:
        """write_report creates missing directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = HtmlReportGenerator(Path(tmpdir) / "nested" / "reports")
            data = _make_report_data()
            path = gen.write_report(data)
            assert path.exists()

    def test_write_report_with_explicit_output_path(self) -> None:
        """When output_path is provided, write to that exact path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = HtmlReportGenerator(Path(tmpdir))
            data = _make_report_data()
            target = Path(tmpdir) / "my-custom-report.html"

            path = gen.write_report(data, output_path=target)

            assert path == target
            assert target.exists()
            content = target.read_text()
            assert "test-001" in content

    def test_write_report_with_output_path_creates_parents(self) -> None:
        """Parent directories are created when output_path has non-existent parents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = HtmlReportGenerator(Path(tmpdir))
            data = _make_report_data()
            target = Path(tmpdir) / "deep" / "nested" / "report.html"

            path = gen.write_report(data, output_path=target)

            assert path == target
            assert target.exists()

    def test_write_report_without_output_path_uses_convention(self) -> None:
        """Default behavior writes to {base_dir}/{test_id}/report.html."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = HtmlReportGenerator(Path(tmpdir))
            data = _make_report_data()

            path = gen.write_report(data)

            expected = Path(tmpdir) / "test-001" / "report.html"
            assert path == expected
            assert path.exists()
