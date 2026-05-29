"""Private section-generation helpers extracted from run_report.py.

Contains markdown generation helpers for individual sections of run reports:
- Token breakdown and display formatting
- Tier and subtest summary tables
- Grade statistics, workspace state, criteria scores
- Judge evaluation section
- Process metrics section
- Workspace file listing helper
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scylla.e2e.filters import is_test_config_file

if TYPE_CHECKING:
    from scylla.e2e.models import ExperimentResult, SubTestResult


def _generate_token_breakdown_section(token_stats: dict[str, int]) -> list[str]:
    """Generate detailed token breakdown section markdown.

    Args:
        token_stats: Token statistics dictionary

    Returns:
        List of markdown lines for token breakdown section

    """
    input_tok = token_stats.get("input_tokens", 0)
    output_tok = token_stats.get("output_tokens", 0)
    cache_read = token_stats.get("cache_read_tokens", 0)
    cache_create = token_stats.get("cache_creation_tokens", 0)
    total = input_tok + output_tok + cache_read + cache_create

    return [
        "### Token Breakdown",
        "",
        "| Type | Count |",
        "|------|-------|",
        f"| Input (fresh) | {input_tok:,} |",
        f"| Output | {output_tok:,} |",
        f"| Cache Read | {cache_read:,} |",
        f"| Cache Created | {cache_create:,} |",
        f"| **Total** | **{total:,}** |",
        "",
    ]


def _format_token_display(
    token_stats: dict[str, int] | None,
    tokens_input: int,
    tokens_output: int,
) -> str:
    """Format token display string with cache information.

    Args:
        token_stats: Optional detailed token statistics dict
        tokens_input: Legacy input token count (fallback)
        tokens_output: Legacy output token count (fallback)

    Returns:
        Formatted token display string

    """
    if token_stats:
        input_tok = token_stats.get("input_tokens", 0)
        output_tok = token_stats.get("output_tokens", 0)
        cache_read = token_stats.get("cache_read_tokens", 0)
        cache_create = token_stats.get("cache_creation_tokens", 0)
        total_input = input_tok + cache_read
        # Format token display with cache info
        if cache_read > 0 or cache_create > 0:
            token_display = f"{total_input:,} in ({cache_read:,} cached) / {output_tok:,} out"
            if cache_create > 0:
                token_display += f" / {cache_create:,} cache created"
        else:
            token_display = f"{total_input:,} in / {output_tok:,} out"
    else:
        token_display = f"{tokens_input:,} in / {tokens_output:,} out"
    return token_display


def _generate_tier_summary_table(result: ExperimentResult) -> list[str]:
    """Generate tier summary table markdown.

    Args:
        result: ExperimentResult with tier data

    Returns:
        List of markdown lines for tier summary table

    """
    lines = [
        "## Tier Summary",
        "",
        "| Tier | Subtests | Duration | Cost | In | Out | Cache R | Cache W | CoP |",
        "|------|----------|----------|------|-----|-----|---------|---------|-----|",
    ]

    for tier_id in result.config.tiers_to_run:
        tier_result = result.tier_results.get(tier_id)
        if tier_result:
            ts = tier_result.token_stats
            # Calculate cost-of-pass for this tier
            best_subtest = result.tier_results[tier_id].subtest_results.get(
                tier_result.best_subtest or ""
            )
            if best_subtest and best_subtest.pass_rate > 0:
                cop = tier_result.total_cost / best_subtest.pass_rate
                cop_str = f"${cop:.2f}"
            else:
                cop_str = "N/A"

            num_subtests = len(tier_result.subtest_results)
            lines.append(
                f"| {tier_id.value} | {num_subtests} | "
                f"{tier_result.total_duration:.1f}s | "
                f"${tier_result.total_cost:.2f} | "
                f"{ts.input_tokens:,} | {ts.output_tokens:,} | "
                f"{ts.cache_read_tokens:,} | {ts.cache_creation_tokens:,} | {cop_str} |"
            )

    lines.append("")
    return lines


def _generate_best_subtest_table(result: ExperimentResult) -> list[str]:
    """Generate best subtest per tier table markdown.

    Args:
        result: ExperimentResult with tier and subtest data

    Returns:
        List of markdown lines for best subtest table

    """
    lines = [
        "## Best Subtest per Tier",
        "",
        "| Tier | Best | Score | Pass | Cost | Duration |",
        "|------|------|-------|------|------|----------|",
    ]

    for tier_id in result.config.tiers_to_run:
        tier_result = result.tier_results.get(tier_id)
        if tier_result and tier_result.best_subtest:
            best_subtest = tier_result.subtest_results.get(tier_result.best_subtest)
            if best_subtest:
                # Calculate subtest-level duration (sum of all runs in this subtest)
                subtest_duration = sum(r.duration_seconds for r in best_subtest.runs)
                lines.append(
                    f"| {tier_id.value} | {tier_result.best_subtest} | "
                    f"{tier_result.best_subtest_score:.2f} | "
                    f"{best_subtest.pass_rate:.0%} | "
                    f"${best_subtest.total_cost:.2f} | "
                    f"{subtest_duration:.1f}s |"
                )

    lines.append("")
    return lines


def _generate_grade_statistics_section(result: SubTestResult) -> list[str]:
    """Generate grade statistics section markdown.

    Args:
        result: SubTestResult with grade distribution data

    Returns:
        List of markdown lines for grade statistics section

    """
    if not result.grade_distribution:
        return []

    lines = ["", "## Grade Statistics", ""]
    # Sort grades from best to worst (S to F)
    grade_order = ["S", "A", "B", "C", "D", "F"]
    sorted_dist = sorted(
        result.grade_distribution.items(),
        key=lambda x: grade_order.index(x[0]) if x[0] in grade_order else 99,
    )
    dist_str = ", ".join(f"{g}={c}" for g, c in sorted_dist)
    lines.append(f"**Distribution**: {dist_str}")
    lines.append(f"**Modal Grade**: {result.modal_grade}")
    if result.min_grade and result.max_grade:
        lines.append(f"**Grade Range**: {result.min_grade} - {result.max_grade}")
    return lines


def _generate_workspace_state_section(workspace_path: Path) -> list[str]:
    """Generate workspace state section markdown.

    Args:
        workspace_path: Path to workspace directory

    Returns:
        List of markdown lines for workspace state section

    """
    lines = [
        "---",
        "",
        "## Workspace State",
        "",
    ]

    workspace_files = _get_workspace_files(workspace_path)
    if workspace_files:
        lines.append("Files created/modified:")
        lines.append("")
        for file_path, status in workspace_files:
            # Create markdown link to file in workspace with status indicator
            status_indicator = "✓" if status == "committed" else "⚠"
            lines.append(f"- [{file_path}](./workspace/{file_path}) {status_indicator} {status}")
        lines.append("")
    else:
        lines.append("No files created in workspace.")
        lines.append("")

    return lines


def _generate_criteria_scores_section(criteria_scores: dict[str, dict[str, Any]]) -> list[str]:
    """Generate criteria scores section markdown.

    Args:
        criteria_scores: Dictionary of criterion -> score data

    Returns:
        List of markdown lines for criteria scores section

    """
    lines = [
        "### Criteria Scores",
        "",
        "| Criterion | Score | Explanation |",
        "|-----------|-------|-------------|",
    ]

    for criterion, data in criteria_scores.items():
        if isinstance(data, dict):
            crit_score = data.get("score", "N/A")
            explanation = data.get("explanation", "No explanation provided")
            # Truncate long explanations for table, escape pipes
            explanation_short = explanation[:100].replace("|", "\\|")
            if len(explanation) > 100:
                explanation_short += "..."
            if isinstance(crit_score, int | float):
                lines.append(f"| {criterion} | {crit_score:.2f} | {explanation_short} |")
            else:
                lines.append(f"| {criterion} | {crit_score} | {explanation_short} |")
        else:
            # Legacy format: just a number
            lines.append(f"| {criterion} | {data:.2f} | - |")

    lines.append("")

    # Add full explanations section
    lines.extend(
        [
            "### Detailed Explanations",
            "",
        ]
    )

    for criterion, data in criteria_scores.items():
        if isinstance(data, dict):
            crit_score = data.get("score", "N/A")
            explanation = data.get("explanation", "No explanation provided")
            score_str = (
                f"{crit_score:.2f}" if isinstance(crit_score, int | float) else str(crit_score)
            )
            lines.extend(
                [
                    f"#### {criterion.replace('_', ' ').title()} ({score_str})",
                    "",
                    explanation,
                    "",
                ]
            )

    return lines


def _generate_judge_section(
    judges: list[Any] | None,
    score: float,
    grade: str,
    passed: bool,
    reasoning: str,
) -> list[str]:
    """Generate judge evaluation section lines.

    Args:
        judges: Optional list of judge results
        score: Overall judge score
        grade: Letter grade
        passed: Whether the run passed
        reasoning: Judge's overall reasoning

    Returns:
        List of markdown lines for judge section

    """
    lines = []
    # Judge Evaluation section - handle single or multiple judges
    if judges and len(judges) > 1:
        # Multiple judges - show consensus summary and individual results
        lines.extend(
            [
                "## Judge Evaluation (Consensus)",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Score | {score:.3f} |",
                f"| Grade | {grade} |",
                f"| Passed | {'✅' if passed else '❌'} |",
                "",
                "### Individual Judges",
                "",
            ]
        )

        for judge in judges:
            judge_score_str = f"{judge.score:.3f}" if judge.score is not None else "N/A"
            judge_grade_str = judge.grade or "N/A"
            lines.extend(
                [
                    f"#### Judge {judge.judge_number}: {judge.model}",
                    "",
                    "| Metric | Value |",
                    "|--------|-------|",
                    f"| Score | {judge_score_str} |",
                    f"| Passed | {'✅' if judge.passed else '❌'} |",
                    f"| Grade | {judge_grade_str} |",
                    "",
                    f"**Reasoning:** {judge.reasoning or 'No reasoning provided'}",
                    "",
                    f"- [View judgment](./judge/judge_{judge.judge_number:02d}/judgment.json)",
                    "",
                ]
            )
    else:
        # Single judge - use existing format
        lines.extend(
            [
                "## Judge Evaluation",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Score | {score:.3f} |",
                f"| Grade | {grade} |",
                f"| Passed | {'✅' if passed else '❌'} |",
                "",
                f"**Reasoning:** {reasoning}",
                "",
                "- [View full judgment](./judge/judge_01/judgment.json)",
                "",
            ]
        )
    return lines


def _format_process_metric_value(val: Any) -> str:
    """Format a process metric value for display.

    Args:
        val: Metric value (float, int, or None)

    Returns:
        Formatted string: 4 decimal places for floats, 'N/A' for None/NaN.

    """
    if val is None:
        return "N/A"
    try:
        f = float(val)
        if math.isnan(f):
            return "N/A"
        return f"{f:.4f}"
    except (TypeError, ValueError):
        return "N/A"


def _generate_process_metrics_section(process_metrics: dict[str, Any]) -> list[str]:
    """Generate process metrics section markdown.

    Args:
        process_metrics: Dict with keys r_prog, strategic_drift, cfp, pr_revert_rate

    Returns:
        List of markdown lines for process metrics section.

    """
    r_prog = _format_process_metric_value(process_metrics.get("r_prog"))
    strategic_drift = _format_process_metric_value(process_metrics.get("strategic_drift"))
    cfp = _format_process_metric_value(process_metrics.get("cfp"))
    pr_revert_rate = _format_process_metric_value(process_metrics.get("pr_revert_rate"))

    return [
        "---",
        "",
        "## Process Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| R_Prog (Fine-Grained Progress) | {r_prog} |",
        f"| Strategic Drift | {strategic_drift} |",
        f"| CFP (Change Fail %) | {cfp} |",
        f"| PR Revert Rate | {pr_revert_rate} |",
        "",
    ]


def _generate_token_stats_section(token_stats: Any) -> list[str]:
    """Generate token statistics section markdown.

    Args:
        token_stats: Token statistics object with attributes

    Returns:
        List of markdown lines for token statistics section

    """
    return [
        "",
        "## Token Statistics (Total)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Input (fresh) | {token_stats.input_tokens:,} |",
        f"| Output | {token_stats.output_tokens:,} |",
        f"| Cache Read | {token_stats.cache_read_tokens:,} |",
        f"| Cache Created | {token_stats.cache_creation_tokens:,} |",
        f"| **Total** | **{token_stats.total_tokens:,}** |",
        "",
    ]


def _build_criterion_row(criterion: str, sorted_items: list[Any]) -> str:
    """Build a markdown table row for one criterion across all items.

    Args:
        criterion: Criterion name.
        sorted_items: Items ordered by key (each has .criteria_scores).

    Returns:
        Markdown row string.

    """
    row = f"| {criterion} |"
    scores: list[tuple[float, int]] = []
    score_cells: list[str] = []

    for item in sorted_items:
        if (
            hasattr(item, "criteria_scores")
            and item.criteria_scores
            and criterion in item.criteria_scores
        ):
            score_data = item.criteria_scores[criterion]
            score = score_data.get("score") if isinstance(score_data, dict) else score_data
            if isinstance(score, int | float):
                scores.append((score, len(score_cells)))
                score_cells.append(f"{score:.2f}")
            else:
                score_cells.append(f"{score}" if score else "-")
        else:
            score_cells.append("-")

    if scores:
        max_score = max(s[0] for s in scores)
        best_indices = {s[1] for s in scores if s[0] == max_score}
        should_highlight = len(score_cells) > 1
        for idx, cell in enumerate(score_cells):
            if should_highlight and idx in best_indices and cell != "-":
                row += f" ***{cell}*** |"
            else:
                row += f" {cell} |"
    else:
        row += "".join(f" {cell} |" for cell in score_cells)

    return row


def _generate_criteria_comparison_table(
    all_criteria: set[str],
    items: dict[Any, Any],
    column_header_fn: Callable[[Any], str],
) -> list[str]:
    """Generate per-criteria comparison table markdown.

    This is shared across subtest, tier, and experiment reports.

    Args:
        all_criteria: Set of all criterion names
        items: Dict mapping item_id -> item (with .criteria_scores and .judge_score)
        column_header_fn: Function to format column header (e.g., lambda k: f"Run {k:02d}")

    Returns:
        List of markdown lines for the criteria comparison table

    """
    lines = []
    sorted_item_ids = sorted(items.keys())
    sorted_items = [items[k] for k in sorted_item_ids]

    # Build header
    header = "| Criterion |"
    separator = "|-----------|"
    for item_id in sorted_item_ids:
        header += f" {column_header_fn(item_id)} |"
        separator += "--------|"
    lines.extend([header, separator])

    # Add rows with best values bolded/italicized
    for criterion in sorted(all_criteria):
        lines.append(_build_criterion_row(criterion, sorted_items))

    # Add Total row with judge's final scores
    total_row = "| **Total** |"
    for item in sorted_items:
        if hasattr(item, "judge_score"):
            total_row += f" **{item.judge_score:.2f}** |"
        else:
            total_row += " **—** |"
    lines.append(total_row)

    return lines


def _parse_porcelain_file_path(line: str) -> str:
    """Extract file path from a git status --porcelain output line.

    Args:
        line: A single git status porcelain output line

    Returns:
        Extracted file path string, or empty string on parse failure.

    """
    if len(line) > 3 and line[2] == " ":
        return line[3:].strip()
    if " " in line:
        return line.split(" ", 1)[1].strip() if " " in line[1:] else ""
    return ""


def _collect_committed_files(workspace_path: Path) -> list[tuple[str, str]]:
    """Return (path, 'committed') pairs from HEAD~1..HEAD diff.

    Args:
        workspace_path: Git repository root to inspect

    Returns:
        List of (file_path, "committed") tuples for non-config files.

    """
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        cwd=workspace_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [
        (line.strip(), "committed")
        for line in result.stdout.strip().split("\n")
        if line.strip() and not is_test_config_file(line.strip())
    ]


def _collect_uncommitted_files(
    workspace_path: Path, committed_paths: set[str]
) -> list[tuple[str, str]]:
    """Return (path, 'uncommitted') pairs from git status --porcelain.

    Args:
        workspace_path: Git repository root to inspect
        committed_paths: Paths already captured as committed (excluded)

    Returns:
        List of (file_path, "uncommitted") tuples for non-config, non-committed files.

    """
    import subprocess

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return []
    entries: list[tuple[str, str]] = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        file_path = _parse_porcelain_file_path(line)
        if file_path and not is_test_config_file(file_path) and file_path not in committed_paths:
            entries.append((file_path, "uncommitted"))
    return entries


def _get_workspace_files(workspace_path: Path) -> list[tuple[str, str]]:
    """Get files created/modified by agent, with their status.

    Returns both committed and uncommitted files created by the agent.

    Args:
        workspace_path: Path to workspace directory

    Returns:
        List of (file_path, status) tuples where status is "committed" or "uncommitted".

    """
    if not workspace_path.exists():
        return []

    try:
        committed = _collect_committed_files(workspace_path)
        committed_paths = {f[0] for f in committed}
        uncommitted = _collect_uncommitted_files(workspace_path, committed_paths)
        return sorted(committed + uncommitted, key=lambda x: x[0])
    except Exception:
        return []
