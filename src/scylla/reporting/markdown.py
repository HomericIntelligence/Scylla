"""Markdown report generator for evaluation results."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TierMetrics:
    """Metrics for a single tier."""

    tier_id: str
    tier_name: str
    pass_rate_median: float
    impl_rate_median: float
    composite_median: float
    cost_of_pass_median: float
    consistency_std_dev: float
    uplift: float  # Percentage uplift vs T0


@dataclass
class SensitivityAnalysis:
    """Prompt sensitivity analysis results."""

    pass_rate_variance: float
    impl_rate_variance: float
    cost_variance: float

    def get_sensitivity_level(self, variance: float) -> str:
        """Determine sensitivity level from variance.

        Args:
            variance: Variance value

        Returns:
            Sensitivity level string

        """
        if variance < 0.05:
            return "low"
        elif variance < 0.15:
            return "medium"
        else:
            return "high"


@dataclass
class TransitionAssessment:
    """Assessment of transitioning between tiers."""

    from_tier: str
    to_tier: str
    pass_rate_delta: float
    impl_rate_delta: float
    cost_delta: float
    worth_it: bool


@dataclass
class ReportData:
    """All data needed to generate a report."""

    test_id: str
    test_name: str
    timestamp: str
    runs_per_tier: int
    judge_model: str
    tiers: list[TierMetrics] = field(default_factory=list)
    sensitivity: SensitivityAnalysis | None = None
    transitions: list[TransitionAssessment] = field(default_factory=list)
    key_finding: str = ""
    recommendations: list[str] = field(default_factory=list)


class MarkdownReportGenerator:
    """Generates Markdown evaluation reports."""

    def __init__(self, base_dir: Path) -> None:
        """Initialize report generator.

        Args:
            base_dir: Base directory for reports (e.g., 'reports/')

        """
        self.base_dir = base_dir

    def get_report_dir(self, test_id: str) -> Path:
        """Get the directory path for a test report.

        Args:
            test_id: Test identifier

        Returns:
            Path to report directory

        """
        return self.base_dir / test_id

    def _find_best_quality_tier(self, tiers: list[TierMetrics]) -> TierMetrics | None:
        """Find tier with highest composite score."""
        if not tiers:
            return None
        return max(tiers, key=lambda t: t.composite_median)

    def _find_best_cost_tier(self, tiers: list[TierMetrics]) -> TierMetrics | None:
        """Find tier with lowest cost-of-pass."""
        if not tiers:
            return None
        valid_tiers = [t for t in tiers if t.cost_of_pass_median != float("inf")]
        if not valid_tiers:
            return None
        return min(valid_tiers, key=lambda t: t.cost_of_pass_median)

    def _find_most_consistent_tier(self, tiers: list[TierMetrics]) -> TierMetrics | None:
        """Find tier with lowest variance (most consistent)."""
        if not tiers:
            return None
        return min(tiers, key=lambda t: t.consistency_std_dev)

    def _format_percentage(self, value: float) -> str:
        """Format a value as a percentage string."""
        return f"{value * 100:.1f}%"

    def _format_cost(self, value: float) -> str:
        """Format a cost value."""
        if value == float("inf"):
            return "∞"
        return f"${value:.2f}"

    def _generate_header(self, data: ReportData) -> str:
        """Generate report header."""
        return f"""# Evaluation Report: {data.test_name}

**Generated**: {data.timestamp}
**Test ID**: {data.test_id}
**Runs per Tier**: {data.runs_per_tier}
**Judge Model**: {data.judge_model}

---
"""

    def _generate_executive_summary(self, data: ReportData) -> str:
        """Generate executive summary section."""
        best_quality = self._find_best_quality_tier(data.tiers)
        best_cost = self._find_best_cost_tier(data.tiers)
        most_consistent = self._find_most_consistent_tier(data.tiers)

        sections = ["## Executive Summary\n"]

        if best_quality:
            sections.append(
                f"### Winner by Quality\n"
                f"**{best_quality.tier_name}** achieved the highest median composite score of "
                f"**{self._format_percentage(best_quality.composite_median)}**.\n"
            )

        if best_cost:
            sections.append(
                f"### Winner by Cost Efficiency\n"
                f"**{best_cost.tier_name}** achieved the lowest Cost-of-Pass at "
                f"**{self._format_cost(best_cost.cost_of_pass_median)}** per successful run.\n"
            )

        if most_consistent:
            sections.append(
                f"### Winner by Consistency\n"
                f"**{most_consistent.tier_name}** showed the lowest variance with "
                f"std_dev of **{most_consistent.consistency_std_dev:.3f}**.\n"
            )

        if data.key_finding:
            sections.append(f"""### Key Finding
{data.key_finding}
""")

        sections.append("---\n")
        return "\n".join(sections)

    def _generate_tier_comparison(self, data: ReportData) -> str:
        """Generate tier comparison table."""
        if not data.tiers:
            return ""

        lines = [
            "## Tier Comparison\n",
            "### Overall Performance\n",
            "| Tier | Pass Rate | Impl Rate | Composite | Cost/Pass | Consistency | Uplift |",
            "|------|-----------|-----------|-----------|-----------|-------------|--------|",
        ]

        for tier in data.tiers:
            uplift_str = "-" if tier.tier_id == "T0" else f"+{tier.uplift * 100:.1f}%"
            lines.append(
                f"| {tier.tier_name} | "
                f"{self._format_percentage(tier.pass_rate_median)} | "
                f"{self._format_percentage(tier.impl_rate_median)} | "
                f"{self._format_percentage(tier.composite_median)} | "
                f"{self._format_cost(tier.cost_of_pass_median)} | "
                f"{tier.consistency_std_dev:.3f} | "
                f"{uplift_str} |"
            )

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_sensitivity_analysis(self, data: ReportData) -> str:
        """Generate prompt sensitivity analysis section."""
        if not data.sensitivity:
            return ""

        s = data.sensitivity
        lines = [
            "## Prompt Sensitivity Analysis\n",
            "### Variance Metrics\n",
            "| Metric | Cross-Tier Variance | Interpretation |",
            "|--------|---------------------|----------------|",
            (
                f"| Pass Rate | {s.pass_rate_variance:.4f} | "
                f"{s.get_sensitivity_level(s.pass_rate_variance)} sensitivity |"
            ),
            (
                f"| Impl Rate | {s.impl_rate_variance:.4f} | "
                f"{s.get_sensitivity_level(s.impl_rate_variance)} sensitivity |"
            ),
            (
                f"| Cost | {s.cost_variance:.4f} | "
                f"{s.get_sensitivity_level(s.cost_variance)} sensitivity |"
            ),
        ]

        if data.transitions:
            lines.extend(
                [
                    "\n### Tier Uplift Analysis\n",
                    "| Transition | Pass Rate Δ | Impl Rate Δ | Cost Δ | Assessment |",
                    "|------------|-------------|-------------|--------|------------|",
                ]
            )

            for t in data.transitions:
                assessment = "worth it" if t.worth_it else "not worth it"
                lines.append(
                    f"| {t.from_tier} → {t.to_tier} | "
                    f"{t.pass_rate_delta:+.1%} | "
                    f"{t.impl_rate_delta:+.1%} | "
                    f"{self._format_cost(t.cost_delta)} | "
                    f"{assessment} |"
                )

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_recommendations(self, data: ReportData) -> str:
        """Generate recommendations section."""
        if not data.recommendations:
            return ""

        lines = ["## Recommendations\n"]

        for i, rec in enumerate(data.recommendations, 1):
            lines.append(f"{i}. {rec}")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_footer(self) -> str:
        """Generate report footer."""
        return """
*Generated by Scylla Agent Testing Framework*
"""

    def generate_report(self, data: ReportData) -> str:
        """Generate a complete Markdown report.

        Args:
            data: Report data

        Returns:
            Complete Markdown report string

        """
        sections = [
            self._generate_header(data),
            self._generate_executive_summary(data),
            self._generate_tier_comparison(data),
            self._generate_sensitivity_analysis(data),
            self._generate_recommendations(data),
            self._generate_footer(),
        ]

        return "".join(sections)

    def write_report(self, data: ReportData, output_path: Path | None = None) -> Path:
        """Generate and write a report to file.

        Args:
            data: Report data
            output_path: Explicit file path to write the report to. When
                provided, the report is written to this exact path instead of
                the convention-based ``{base_dir}/{test_id}/report.md``.

        Returns:
            Path to written report file.

        """
        if output_path is not None:
            report_path = output_path
        else:
            report_dir = self.get_report_dir(data.test_id)
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "report.md"

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_content = self.generate_report(data)
        report_path.write_text(report_content)

        return report_path


def create_tier_metrics(
    tier_id: str,
    tier_name: str,
    pass_rate_median: float,
    impl_rate_median: float,
    composite_median: float,
    cost_of_pass_median: float,
    consistency_std_dev: float,
    uplift: float = 0.0,
) -> TierMetrics:
    """Create TierMetrics from tier results.

    Args:
        tier_id: Tier identifier (T0, T1, etc.)
        tier_name: Human-readable tier name
        pass_rate_median: Median pass rate
        impl_rate_median: Median implementation rate
        composite_median: Median composite score
        cost_of_pass_median: Median cost of pass
        consistency_std_dev: Standard deviation for consistency
        uplift: Percentage uplift vs T0

    Returns:
        TierMetrics object

    """
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


def create_report_data(
    test_id: str,
    test_name: str,
    runs_per_tier: int = 10,
    judge_model: str = "claude-opus-4-6",
    timestamp: str | None = None,
) -> ReportData:
    """Create ReportData from experiment results.

    Args:
        test_id: Test identifier
        test_name: Human-readable test name
        runs_per_tier: Number of runs per tier
        judge_model: Judge model name
        timestamp: Optional timestamp (auto-generated if not provided)

    Returns:
        ReportData object

    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return ReportData(
        test_id=test_id,
        test_name=test_name,
        timestamp=timestamp,
        runs_per_tier=runs_per_tier,
        judge_model=judge_model,
    )
