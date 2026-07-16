"""Hierarchical report save functions extracted from run_report.py.

Contains save functions for each level of the experiment hierarchy:
- save_run_report_json: JSON report for a single run
- save_subtest_report: JSON and markdown reports for a subtest
- generate_tier_summary_table: markdown table for tier subtests
- generate_experiment_summary_table: markdown table for experiment tiers
- save_tier_report: JSON and markdown reports for a tier
- save_experiment_report: JSON and markdown reports for the whole experiment
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scylla.e2e.run_report_sections import (
    _generate_best_subtest_table,
    _generate_criteria_comparison_table,
    _generate_grade_statistics_section,
    _generate_tier_summary_table,
    _generate_token_stats_section,
)

if TYPE_CHECKING:
    from scylla.e2e.models import ExperimentResult, SubTestResult, TierID, TierResult


def save_run_report_json(
    run_dir: Path,
    run_number: int,
    score: float,
    grade: str,
    passed: bool,
    cost_usd: float,
    duration_seconds: float,
    process_metrics: dict[str, Any] | None = None,
) -> None:
    """Save JSON report for a single run.

    Args:
        run_dir: Directory for this run
        run_number: Run number (1-indexed)
        score: Judge score
        grade: Letter grade
        passed: Whether passed
        cost_usd: Cost in USD
        duration_seconds: Duration
        process_metrics: Optional process metrics dict with keys:
            r_prog, strategic_drift, cfp, pr_revert_rate

    """
    report: dict[str, Any] = {
        "run_number": run_number,
        "score": score,
        "grade": grade,
        "passed": passed,
        "cost_usd": cost_usd,
        "duration_seconds": duration_seconds,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if process_metrics and isinstance(process_metrics, dict):
        guarded: dict[str, float | None] = {}
        for key in ("r_prog", "strategic_drift", "cfp", "pr_revert_rate"):
            val = process_metrics.get(key)
            if val is None:
                guarded[key] = None
            else:
                try:
                    f = float(val)
                    guarded[key] = None if math.isnan(f) else f
                except (TypeError, ValueError):
                    guarded[key] = None
        report["process_metrics"] = guarded

    (run_dir / "report.json").write_text(json.dumps(report, indent=2))


def save_subtest_report(
    subtest_dir: Path,
    subtest_id: str,
    result: SubTestResult,
    output_path_json: Path | None = None,
    output_path_md: Path | None = None,
) -> None:
    """Save JSON and markdown reports for a subtest.

    Args:
        subtest_dir: Directory for this subtest
        subtest_id: Subtest identifier
        result: SubTestResult with aggregated data
        output_path_json: Optional custom path for JSON report (defaults to subtest_dir/report.json)
        output_path_md: Optional custom path for markdown report (defaults to subtest_dir/report.md)

    """
    # Build children list with relative paths
    children = []
    for run in result.runs:
        run_dir_name = f"run_{run.run_number:02d}"
        children.append(
            {
                "run_number": run.run_number,
                "score": run.judge_score,
                "passed": run.judge_passed,
                "report": f"./{run_dir_name}/report.json",
            }
        )

    # JSON report with token stats
    json_report = {
        "subtest_id": subtest_id,
        "tier_id": result.tier_id.value,
        "summary": {
            "total_runs": len(result.runs),
            "passed": sum(1 for r in result.runs if r.judge_passed),
            "pass_rate": result.pass_rate,
            "mean_score": result.mean_score,
            "median_score": result.median_score,
            "std_dev": result.std_dev_score,
            "total_cost": result.total_cost,
            "consistency": result.consistency,
            "grade_distribution": result.grade_distribution,
            "modal_grade": result.modal_grade,
            "min_grade": result.min_grade,
            "max_grade": result.max_grade,
        },
        "token_stats": result.token_stats.to_dict(),
        "children": children,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Ensure directory exists before writing
    subtest_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_path_json if output_path_json is not None else subtest_dir / "report.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_report, indent=2))

    # Markdown report
    md_lines = [
        f"# Subtest Report: {subtest_id}",
        "",
        f"**Tier**: {result.tier_id.value}",
        f"**Generated**: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Runs | {len(result.runs)} |",
        f"| Passed | {sum(1 for r in result.runs if r.judge_passed)} |",
        f"| Pass Rate | {result.pass_rate:.1%} |",
        f"| Mean Score | {result.mean_score:.3f} |",
        f"| Median Score | {result.median_score:.3f} |",
        f"| Std Dev | {result.std_dev_score:.3f} |",
        f"| Total Cost | ${result.total_cost:.4f} |",
        f"| Consistency | {result.consistency:.3f} |",
        "",
        "## Runs Overview",
        "",
        "| Run | Score | Grade | Pass | Duration | Cost | In | Out | Cache R | Cache W |",
        "|-----|-------|-------|------|----------|------|-----|-----|---------|---------|",
    ]

    # Find best run
    best_run = max(result.runs, key=lambda r: r.judge_score) if result.runs else None

    for run in result.runs:
        status = "✓" if run.judge_passed else "✗"
        is_best = "★" if best_run and run.run_number == best_run.run_number else ""
        ts = run.token_stats
        md_lines.append(
            f"| {run.run_number:02d}{is_best} | {run.judge_score:.2f} | {run.judge_grade} | "
            f"{status} | {run.duration_seconds:.2f}s | ${run.cost_usd:.4f} | "
            f"{ts.input_tokens:,} | {ts.output_tokens:,} | "
            f"{ts.cache_read_tokens:,} | {ts.cache_creation_tokens:,} |"
        )

    # Add grade statistics if available
    md_lines.extend(_generate_grade_statistics_section(result))

    # Collect all criteria across runs
    all_criteria: set[str] = set()
    for run in result.runs:
        if run.criteria_scores:
            all_criteria.update(run.criteria_scores.keys())

    # Add per-criteria comparison table if we have criteria
    if all_criteria:
        md_lines.extend(
            [
                "",
                "## Per-Criteria Scores (All Runs)",
                "",
            ]
        )

        # Build items dict for helper
        items_dict = {run.run_number: run for run in result.runs}
        criteria_table = _generate_criteria_comparison_table(
            all_criteria,
            items_dict,
            column_header_fn=lambda run_num: f"Run {run_num:02d}",
        )
        md_lines.extend(criteria_table)

    # Add aggregated token statistics
    md_lines.extend(_generate_token_stats_section(result.token_stats))

    # Add run links
    md_lines.extend(
        [
            "## Run Reports",
            "",
        ]
    )
    for run in result.runs:
        run_dir_name = f"run_{run.run_number:02d}"
        md_lines.append(f"- [Run {run.run_number:02d}](./{run_dir_name}/report.md)")

    md_lines.extend(
        [
            "",
            "---",
            "*Generated by Scylla E2E Framework*",
        ]
    )

    (subtest_dir / "report.md").write_text("\n".join(md_lines))


def generate_tier_summary_table(
    tier_id: str,
    subtest_results: dict[str, SubTestResult],
) -> str:
    """Generate markdown table summarizing all subtest scores for a tier.

    Args:
        tier_id: The tier identifier (e.g., "T0", "T1")
        subtest_results: Dictionary mapping subtest ID to SubTestResult

    Returns:
        Markdown formatted summary table with links to individual reports

    """
    lines = [
        f"# {tier_id} Subtest Summary",
        "",
        "| Subtest | Best Score | Pass Rate | Avg Cost | Report |",
        "|---------|------------|-----------|----------|--------|",
    ]

    for subtest_id, result in sorted(subtest_results.items()):
        # Find best score across all runs
        best_score = max(run.judge_score for run in result.runs) if result.runs else 0.0

        # Calculate pass rate
        pass_rate = result.pass_rate

        # Calculate average cost
        avg_cost = result.mean_cost

        # Create link to detailed report
        report_link = f"[View](./{subtest_id}/report.md)"

        lines.append(
            f"| {subtest_id} | {best_score:.2f} | {pass_rate:.1%} | "
            f"${avg_cost:.4f} | {report_link} |"
        )

    lines.extend(["", "*Generated by Scylla E2E Framework*"])

    return "\n".join(lines)


def generate_experiment_summary_table(
    tier_results: dict[TierID, TierResult],
) -> str:
    """Generate markdown table summarizing all tiers and subtests.

    Args:
        tier_results: Dictionary mapping TierID to TierResult

    Returns:
        Markdown formatted comprehensive summary table

    """
    lines = [
        "# Experiment Summary: All Subtests",
        "",
        "| Tier | Subtest | Best Score | Pass Rate | Avg Cost | Report |",
        "|------|---------|------------|-----------|----------|--------|",
    ]

    for tier_id, tier_result in sorted(tier_results.items()):
        for subtest_id, subtest_result in sorted(tier_result.subtest_results.items()):
            # Find best score across all runs
            best_score = (
                max(run.judge_score for run in subtest_result.runs) if subtest_result.runs else 0.0
            )

            # Calculate pass rate
            pass_rate = subtest_result.pass_rate

            # Calculate average cost
            avg_cost = subtest_result.mean_cost

            # Create link to detailed report
            report_link = f"[View](./tiers/{tier_id.value}/{subtest_id}/report.md)"

            lines.append(
                f"| {tier_id.value} | {subtest_id} | {best_score:.2f} | "
                f"{pass_rate:.1%} | ${avg_cost:.4f} | {report_link} |"
            )

    lines.extend(["", "*Generated by Scylla E2E Framework*"])

    return "\n".join(lines)


def save_tier_report(
    tier_dir: Path,
    tier_id: str,
    result: TierResult,
    output_path_json: Path | None = None,
    output_path_md: Path | None = None,
) -> None:
    """Save JSON and markdown reports for a tier.

    Args:
        tier_dir: Directory for this tier
        tier_id: Tier identifier (e.g., "T0")
        result: TierResult with aggregated data
        output_path_json: Optional custom path for JSON report (defaults to tier_dir/report.json)
        output_path_md: Optional custom path for markdown report (defaults to tier_dir/report.md)

    """
    # Build children list with relative paths
    children = []
    for subtest_id, subtest_result in result.subtest_results.items():
        children.append(
            {
                "id": subtest_id,
                "score": subtest_result.median_score,
                "pass_rate": subtest_result.pass_rate,
                "cost": subtest_result.total_cost,
                "selected": subtest_result.selected_as_best,
                "report": f"./{subtest_id}/report.json",
            }
        )

    # JSON report with token stats
    json_report = {
        "tier": tier_id,
        "summary": {
            "total_subtests": len(result.subtest_results),
            "best_subtest": result.best_subtest,
            "best_score": result.best_subtest_score,
            "total_cost": result.total_cost,
            "total_duration": result.total_duration,
            "tiebreaker_needed": result.tiebreaker_needed,
        },
        "token_stats": result.token_stats.to_dict(),
        "best": {
            "subtest": result.best_subtest,
            "score": result.best_subtest_score,
            "report": f"./{result.best_subtest}/report.json" if result.best_subtest else None,
        },
        "children": children,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    json_path = output_path_json if output_path_json is not None else tier_dir / "report.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_report, indent=2))

    # Markdown report
    md_lines = [
        f"# Tier Report: {tier_id}",
        "",
        f"**Generated**: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Subtests | {len(result.subtest_results)} |",
        f"| Best Subtest | {result.best_subtest or 'N/A'} |",
        f"| Best Score | {result.best_subtest_score:.3f} |",
        f"| Total Cost | ${result.total_cost:.4f} |",
        f"| Duration | {result.total_duration:.1f}s |",
        f"| Tiebreaker Needed | {'Yes' if result.tiebreaker_needed else 'No'} |",
        "",
        "## Subtests Overview",
        "",
        "| Subtest | Score | Pass | Duration | Cost | In | Out | Cache R | Cache W | Best |",
        "|---------|-------|------|----------|------|-----|-----|---------|---------|------|",
    ]

    for subtest_id, subtest_result in sorted(result.subtest_results.items()):
        selected = "★" if subtest_result.selected_as_best else ""
        ts = subtest_result.token_stats
        # Calculate total duration from runs
        total_duration = sum(run.duration_seconds for run in subtest_result.runs)
        md_lines.append(
            f"| {subtest_id} | {subtest_result.median_score:.2f} | "
            f"{subtest_result.pass_rate:.0%} | {total_duration:.2f}s | "
            f"${subtest_result.total_cost:.2f} | "
            f"{ts.input_tokens:,} | {ts.output_tokens:,} | "
            f"{ts.cache_read_tokens:,} | {ts.cache_creation_tokens:,} | {selected} |"
        )

    # Collect all criteria across best runs from each subtest
    all_criteria: set[str] = set()
    best_runs: dict[str, Any] = {}  # subtest_id -> best run
    for subtest_id, subtest_result in result.subtest_results.items():
        if subtest_result.runs:
            best_run = max(subtest_result.runs, key=lambda r: r.judge_score)
            best_runs[subtest_id] = best_run
            if best_run.criteria_scores:
                all_criteria.update(best_run.criteria_scores.keys())

    # Add per-criteria comparison table if we have criteria
    if all_criteria and best_runs:
        md_lines.extend(
            [
                "",
                "## Per-Criteria Scores (Best Run per Subtest)",
                "",
            ]
        )

        # Use helper to generate table
        criteria_table = _generate_criteria_comparison_table(
            all_criteria,
            best_runs,
            column_header_fn=lambda subtest_id: subtest_id,
        )
        md_lines.extend(criteria_table)

    # Add aggregated token statistics
    md_lines.extend(_generate_token_stats_section(result.token_stats))

    # Add subtest links
    md_lines.extend(
        [
            "## Subtest Reports",
            "",
        ]
    )
    for subtest_id in sorted(result.subtest_results.keys()):
        md_lines.append(f"- [{subtest_id}](./{subtest_id}/report.md)")

    md_lines.extend(
        [
            "",
            "---",
            "*Generated by Scylla E2E Framework*",
        ]
    )

    (tier_dir / "report.md").write_text("\n".join(md_lines))


def save_experiment_report(
    experiment_dir: Path,
    result: ExperimentResult,
    output_path_json: Path | None = None,
    output_path_md: Path | None = None,
) -> None:
    """Save JSON and markdown reports for the entire experiment.

    Args:
        experiment_dir: Root experiment directory
        result: ExperimentResult with all data
        output_path_json: Optional custom path for JSON report
            (defaults to experiment_dir/report.json)
        output_path_md: Optional custom path for markdown report
            (defaults to experiment_dir/report.md)

    """
    # Build children list with relative paths
    children = []
    for tier_id, tier_result in result.tier_results.items():
        children.append(
            {
                "tier": tier_id.value,
                "best_subtest": tier_result.best_subtest,
                "best_score": tier_result.best_subtest_score,
                "cost": tier_result.total_cost,
                "report": f"./{tier_id.value}/report.json",
            }
        )

    # JSON report with token stats
    json_report = {
        "experiment_id": result.config.experiment_id,
        "summary": {
            "total_tiers": len(result.tier_results),
            "best_tier": result.best_overall_tier.value if result.best_overall_tier else None,
            "best_subtest": result.best_overall_subtest,
            "frontier_cop": result.frontier_cop if result.frontier_cop != float("inf") else None,
            "total_cost": result.total_cost,
            "total_duration": result.total_duration_seconds,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
        },
        "token_stats": result.token_stats.to_dict(),
        "best": {
            "tier": result.best_overall_tier.value if result.best_overall_tier else None,
            "subtest": result.best_overall_subtest,
            "report": f"./{result.best_overall_tier.value}/report.json"
            if result.best_overall_tier
            else None,
        },
        "children": children,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    json_path = output_path_json if output_path_json is not None else experiment_dir / "report.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_report, indent=2))

    # Markdown report with enhanced tables
    md_lines = [
        f"# E2E Experiment Report: {result.config.experiment_id}",
        "",
        f"**Generated**: {datetime.now(timezone.utc).isoformat()}",
        f"**Duration**: {result.total_duration_seconds:.1f}s",
        f"**Total Cost**: ${result.total_cost:.4f}",
        "",
        "## Summary",
        "",
        f"- **Best Tier**: {result.best_overall_tier.value if result.best_overall_tier else 'N/A'}",
        f"- **Best Sub-test**: {result.best_overall_subtest or 'N/A'}",
        f"- **Frontier CoP**: ${result.frontier_cop:.4f}"
        if result.frontier_cop != float("inf")
        else "- **Frontier CoP**: N/A",
        "",
    ]

    # Add tier summary table
    md_lines.extend(_generate_tier_summary_table(result))

    # Add best subtest per tier table
    md_lines.extend(_generate_best_subtest_table(result))

    # Collect all criteria across best runs from each tier's best subtest
    all_criteria: set[str] = set()
    best_runs_by_tier: dict[str, Any] = {}  # tier_id.value -> best run
    for tier_id, tier_result in result.tier_results.items():
        if tier_result.best_subtest:
            best_subtest = tier_result.subtest_results.get(tier_result.best_subtest)
            if best_subtest and best_subtest.runs:
                best_run = max(best_subtest.runs, key=lambda r: r.judge_score)
                best_runs_by_tier[tier_id.value] = best_run
                if best_run.criteria_scores:
                    all_criteria.update(best_run.criteria_scores.keys())

    # Add per-criteria comparison table if we have criteria
    if all_criteria and best_runs_by_tier:
        md_lines.extend(
            [
                "",
                "## Per-Criteria Scores (Best Subtest per Tier)",
                "",
            ]
        )

        # Use helper to generate table
        criteria_table = _generate_criteria_comparison_table(
            all_criteria,
            best_runs_by_tier,
            column_header_fn=lambda tier_val: tier_val,
        )
        md_lines.extend(criteria_table)

    # Add aggregated token statistics
    md_lines.extend(_generate_token_stats_section(result.token_stats))

    md_lines.extend(
        [
            "## Configuration",
            "",
            f"- **Task Repo**: {result.config.task_repo}",
            f"- **Task Commit**: {result.config.task_commit}",
            f"- **Runs per Sub-test**: {result.config.runs_per_subtest}",
            f"- **Judge Models**: {', '.join(result.config.judge_models)}",
            "",
            "## Tier Reports",
            "",
        ]
    )

    for tier_id in result.config.tiers_to_run:
        if tier_id in result.tier_results:
            md_lines.append(f"- [{tier_id.value}](./{tier_id.value}/report.md)")

    md_lines.extend(
        [
            "",
            "## Files",
            "",
            "- [prompt.md](./prompt.md) - Task prompt",
            "- [criteria.md](./criteria.md) - Grading criteria (if available)",
            "- [rubric.yaml](./rubric.yaml) - Grading rubric (if available)",
            "- [judge_prompt.md](./judge_prompt.md) - Judge prompt template",
            "- [result.json](./result.json) - Full results data",
            "",
            "---",
            "",
            "*Generated by Scylla E2E Framework*",
        ]
    )

    (experiment_dir / "report.md").write_text("\n".join(md_lines))
