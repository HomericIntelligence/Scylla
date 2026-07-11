"""HTML report generator for evaluation results."""

from html import escape
from pathlib import Path

from scylla.reporting.markdown import ReportData, TierMetrics


def _esc(value: str) -> str:
    """Escape a string for safe HTML embedding."""
    return escape(str(value))


def _format_percentage(value: float) -> str:
    """Format a value as a percentage string."""
    return f"{value * 100:.1f}%"


def _format_cost(value: float) -> str:
    """Format a cost value for display."""
    if value == float("inf"):
        return "&infin;"
    return f"${value:.2f}"


class HtmlReportGenerator:
    """Generates self-contained HTML evaluation reports."""

    def __init__(self, base_dir: Path) -> None:
        """Initialize HTML report generator.

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

    def _generate_style(self) -> str:
        """Generate CSS styles for the report."""
        return """<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
         sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem;
         color: #333; background: #fafafa; }
  h1 { border-bottom: 2px solid #2563eb; padding-bottom: 0.5rem; }
  h2 { color: #1e40af; margin-top: 2rem; }
  h3 { color: #374151; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #d1d5db; padding: 0.5rem 0.75rem;
           text-align: left; }
  th { background: #2563eb; color: white; }
  tr:nth-child(even) { background: #f3f4f6; }
  .meta { color: #6b7280; font-size: 0.9rem; }
  .summary-card { background: white; border: 1px solid #e5e7eb;
                  border-radius: 0.5rem; padding: 1rem; margin: 0.5rem 0; }
  .footer { margin-top: 2rem; padding-top: 1rem;
            border-top: 1px solid #e5e7eb; color: #9ca3af;
            font-size: 0.85rem; }
  ol { padding-left: 1.5rem; }
</style>"""

    def _generate_header(self, data: ReportData) -> str:
        """Generate the HTML header section."""
        return f"""<h1>Evaluation Report: {_esc(data.test_name)}</h1>
<p class="meta">
  <strong>Generated:</strong> {_esc(data.timestamp)}<br>
  <strong>Test ID:</strong> {_esc(data.test_id)}<br>
  <strong>Runs per Tier:</strong> {data.runs_per_tier}<br>
  <strong>Judge Model:</strong> {_esc(data.judge_model)}
</p>
<hr>"""

    def _generate_executive_summary(self, data: ReportData) -> str:
        """Generate executive summary section."""
        best_quality = self._find_best_quality_tier(data.tiers)
        best_cost = self._find_best_cost_tier(data.tiers)
        most_consistent = self._find_most_consistent_tier(data.tiers)

        parts = ["<h2>Executive Summary</h2>"]

        if best_quality:
            parts.append(
                '<div class="summary-card">'
                "<h3>Winner by Quality</h3>"
                f"<p><strong>{_esc(best_quality.tier_name)}</strong> achieved the "
                f"highest median composite score of "
                f"<strong>{_esc(_format_percentage(best_quality.composite_median))}"
                "</strong>.</p></div>"
            )

        if best_cost:
            parts.append(
                '<div class="summary-card">'
                "<h3>Winner by Cost Efficiency</h3>"
                f"<p><strong>{_esc(best_cost.tier_name)}</strong> achieved the "
                f"lowest Cost-of-Pass at "
                f"<strong>{_format_cost(best_cost.cost_of_pass_median)}"
                "</strong> per successful run.</p></div>"
            )

        if most_consistent:
            parts.append(
                '<div class="summary-card">'
                "<h3>Winner by Consistency</h3>"
                f"<p><strong>{_esc(most_consistent.tier_name)}</strong> showed the "
                f"lowest variance with std_dev of "
                f"<strong>{most_consistent.consistency_std_dev:.3f}"
                "</strong>.</p></div>"
            )

        if data.key_finding:
            parts.append(
                '<div class="summary-card">'
                "<h3>Key Finding</h3>"
                f"<p>{_esc(data.key_finding)}</p></div>"
            )

        parts.append("<hr>")
        return "\n".join(parts)

    def _generate_tier_comparison(self, data: ReportData) -> str:
        """Generate tier comparison table."""
        if not data.tiers:
            return ""

        rows: list[str] = []
        for tier in data.tiers:
            uplift_str = "-" if tier.tier_id == "T0" else f"+{tier.uplift * 100:.1f}%"
            rows.append(
                "<tr>"
                f"<td>{_esc(tier.tier_name)}</td>"
                f"<td>{_esc(_format_percentage(tier.pass_rate_median))}</td>"
                f"<td>{_esc(_format_percentage(tier.impl_rate_median))}</td>"
                f"<td>{_esc(_format_percentage(tier.composite_median))}</td>"
                f"<td>{_format_cost(tier.cost_of_pass_median)}</td>"
                f"<td>{tier.consistency_std_dev:.3f}</td>"
                f"<td>{_esc(uplift_str)}</td>"
                "</tr>"
            )

        return (
            "<h2>Tier Comparison</h2>\n"
            "<h3>Overall Performance</h3>\n"
            "<table>\n"
            "<tr><th>Tier</th><th>Pass Rate</th><th>Impl Rate</th>"
            "<th>Composite</th><th>Cost/Pass</th><th>Consistency</th>"
            "<th>Uplift</th></tr>\n" + "\n".join(rows) + "\n</table>\n<hr>"
        )

    def _generate_sensitivity_analysis(self, data: ReportData) -> str:
        """Generate prompt sensitivity analysis section."""
        if not data.sensitivity:
            return ""

        s = data.sensitivity
        parts = [
            "<h2>Prompt Sensitivity Analysis</h2>",
            "<h3>Variance Metrics</h3>",
            "<table>",
            "<tr><th>Metric</th><th>Cross-Tier Variance</th><th>Interpretation</th></tr>",
            f"<tr><td>Pass Rate</td><td>{s.pass_rate_variance:.4f}</td>"
            f"<td>{_esc(s.get_sensitivity_level(s.pass_rate_variance))} "
            "sensitivity</td></tr>",
            f"<tr><td>Impl Rate</td><td>{s.impl_rate_variance:.4f}</td>"
            f"<td>{_esc(s.get_sensitivity_level(s.impl_rate_variance))} "
            "sensitivity</td></tr>",
            f"<tr><td>Cost</td><td>{s.cost_variance:.4f}</td>"
            f"<td>{_esc(s.get_sensitivity_level(s.cost_variance))} "
            "sensitivity</td></tr>",
            "</table>",
        ]

        if data.transitions:
            parts.extend(
                [
                    "<h3>Tier Uplift Analysis</h3>",
                    "<table>",
                    "<tr><th>Transition</th><th>Pass Rate &Delta;</th>"
                    "<th>Impl Rate &Delta;</th><th>Cost &Delta;</th>"
                    "<th>Assessment</th></tr>",
                ]
            )
            for t in data.transitions:
                assessment = "worth it" if t.worth_it else "not worth it"
                parts.append(
                    f"<tr><td>{_esc(t.from_tier)} &rarr; {_esc(t.to_tier)}</td>"
                    f"<td>{t.pass_rate_delta:+.1%}</td>"
                    f"<td>{t.impl_rate_delta:+.1%}</td>"
                    f"<td>{_format_cost(t.cost_delta)}</td>"
                    f"<td>{_esc(assessment)}</td></tr>"
                )
            parts.append("</table>")

        parts.append("<hr>")
        return "\n".join(parts)

    def _generate_recommendations(self, data: ReportData) -> str:
        """Generate recommendations section."""
        if not data.recommendations:
            return ""

        items = "".join(f"<li>{_esc(rec)}</li>" for rec in data.recommendations)
        return f"<h2>Recommendations</h2>\n<ol>{items}</ol>\n<hr>"

    def _generate_footer(self) -> str:
        """Generate report footer."""
        return '<p class="footer"><em>Generated by Scylla Agent Testing Framework</em></p>'

    def generate_report(self, data: ReportData) -> str:
        """Generate a complete self-contained HTML report.

        Args:
            data: Report data

        Returns:
            Complete HTML report string

        """
        body = "\n".join(
            [
                self._generate_header(data),
                self._generate_executive_summary(data),
                self._generate_tier_comparison(data),
                self._generate_sensitivity_analysis(data),
                self._generate_recommendations(data),
                self._generate_footer(),
            ]
        )

        return (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n<head>\n'
            '<meta charset="utf-8">\n'
            f"<title>Evaluation Report: {_esc(data.test_name)}</title>\n"
            f"{self._generate_style()}\n"
            "</head>\n<body>\n"
            f"{body}\n"
            "</body>\n</html>"
        )

    def write_report(self, data: ReportData, output_path: Path | None = None) -> Path:
        """Generate and write an HTML report to file.

        Args:
            data: Report data
            output_path: Explicit file path to write the report to. When
                provided, the report is written to this exact path instead of
                the convention-based ``{base_dir}/{test_id}/report.html``.

        Returns:
            Path to written report file.

        """
        if output_path is not None:
            report_path = output_path
        else:
            report_dir = self.get_report_dir(data.test_id)
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "report.html"

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_content = self.generate_report(data)
        report_path.write_text(report_content)

        return report_path
