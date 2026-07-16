"""Hierarchical report generation for E2E experiments.

This module generates detailed reports at every level of the experiment:
- Run level: Individual run results
- Subtest level: Aggregated across runs
- Tier level: Aggregated across subtests
- Experiment level: Overall summary

Each level has both JSON and markdown reports with relative links.

Implementation is split across focused submodules:
- run_report_sections: private markdown section generators
- run_report_hierarchy: hierarchical save functions (subtest/tier/experiment)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scylla.e2e.run_report_hierarchy import (
    generate_experiment_summary_table as generate_experiment_summary_table,
)
from scylla.e2e.run_report_hierarchy import (
    generate_tier_summary_table as generate_tier_summary_table,
)
from scylla.e2e.run_report_hierarchy import (
    save_experiment_report as save_experiment_report,
)
from scylla.e2e.run_report_hierarchy import (
    save_run_report_json as save_run_report_json,
)
from scylla.e2e.run_report_hierarchy import (
    save_subtest_report as save_subtest_report,
)
from scylla.e2e.run_report_hierarchy import (
    save_tier_report as save_tier_report,
)
from scylla.e2e.run_report_sections import (
    _format_process_metric_value as _format_process_metric_value,
)
from scylla.e2e.run_report_sections import (
    _format_token_display as _format_token_display,
)
from scylla.e2e.run_report_sections import (
    _generate_best_subtest_table as _generate_best_subtest_table,
)
from scylla.e2e.run_report_sections import (
    _generate_criteria_comparison_table as _generate_criteria_comparison_table,
)
from scylla.e2e.run_report_sections import (
    _generate_criteria_scores_section as _generate_criteria_scores_section,
)
from scylla.e2e.run_report_sections import (
    _generate_grade_statistics_section as _generate_grade_statistics_section,
)
from scylla.e2e.run_report_sections import (
    _generate_judge_section as _generate_judge_section,
)
from scylla.e2e.run_report_sections import (
    _generate_process_metrics_section as _generate_process_metrics_section,
)
from scylla.e2e.run_report_sections import (
    _generate_tier_summary_table as _generate_tier_summary_table,
)
from scylla.e2e.run_report_sections import (
    _generate_token_breakdown_section as _generate_token_breakdown_section,
)
from scylla.e2e.run_report_sections import (
    _generate_token_stats_section as _generate_token_stats_section,
)
from scylla.e2e.run_report_sections import (
    _generate_workspace_state_section as _generate_workspace_state_section,
)
from scylla.e2e.run_report_sections import (
    _get_workspace_files as _get_workspace_files,
)


def generate_run_report(
    tier_id: str,
    subtest_id: str,
    run_number: int,
    score: float,
    grade: str,
    passed: bool,
    reasoning: str,
    cost_usd: float,
    duration_seconds: float,
    tokens_input: int,
    tokens_output: int,
    exit_code: int,
    task_prompt: str,
    workspace_path: Path,
    judges: list[Any] | None = None,
    criteria_scores: dict[str, dict[str, Any]] | None = None,
    agent_output: str | None = None,
    token_stats: dict[str, int] | None = None,
    agent_duration_seconds: float | None = None,
    judge_duration_seconds: float | None = None,
    process_metrics: dict[str, Any] | None = None,
) -> str:
    """Generate markdown report content for a single run.

    Args:
        tier_id: Tier identifier (e.g., "T0", "T1")
        subtest_id: Sub-test identifier (e.g., "baseline", "01")
        run_number: Run number (1-indexed)
        score: Overall judge score (0.0-1.0)
        grade: Letter grade (S-F)
        passed: Whether the run passed
        reasoning: Judge's overall reasoning
        cost_usd: Total cost in USD
        duration_seconds: Total execution duration (agent + judge)
        tokens_input: Number of input tokens (legacy, use token_stats if available)
        tokens_output: Number of output tokens (legacy, use token_stats if available)
        exit_code: Process exit code
        task_prompt: The task prompt given to the agent
        workspace_path: Path to the workspace directory
        criteria_scores: Optional detailed criteria evaluations
        agent_output: Optional truncated agent output
        token_stats: Optional detailed token statistics dict with keys:
            input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
        agent_duration_seconds: Agent execution time (optional)
        judge_duration_seconds: Judge evaluation time (optional)
        process_metrics: Optional process metrics dict with keys:
            r_prog, strategic_drift, cfp, pr_revert_rate

    Returns:
        Formatted markdown report string.

    """
    timestamp = datetime.now(timezone.utc).isoformat()
    pass_status = "\u2713 PASS" if passed else "\u2717 FAIL"

    # Format token display
    token_display = _format_token_display(token_stats, tokens_input, tokens_output)

    lines = [
        f"# Run Report: {tier_id}/{subtest_id}/run_{run_number:02d}",
        "",
        f"**Generated**: {timestamp}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Score | {score:.3f} |",
        f"| Grade | {grade} |",
        f"| Status | {pass_status} |",
        f"| Cost | ${cost_usd:.4f} |",
        f"| Duration (Total) | {duration_seconds:.2f}s |",
    ]

    # Add duration breakdown if available
    if agent_duration_seconds is not None and judge_duration_seconds is not None:
        lines.extend(
            [
                f"| - Agent | {agent_duration_seconds:.2f}s |",
                f"| - Judge | {judge_duration_seconds:.2f}s |",
            ]
        )

    lines.extend(
        [
            f"| Tokens | {token_display} |",
            f"| Exit Code | {exit_code} |",
            "",
        ]
    )

    # Add detailed token statistics table if available
    if token_stats:
        lines.extend(_generate_token_breakdown_section(token_stats))

    lines.extend(
        [
            "---",
            "",
            "## Task",
            "",
            "[View task prompt](./task_prompt.md)",
            "",
            "---",
            "",
        ]
    )

    # Add judge evaluation section
    judge_lines = _generate_judge_section(judges, score, grade, passed, reasoning)
    lines.extend(judge_lines)
    lines.extend([""])

    # Add criteria scores if available
    if criteria_scores:
        lines.extend(_generate_criteria_scores_section(criteria_scores))

    # Add workspace state
    lines.extend(_generate_workspace_state_section(workspace_path))

    # Add process metrics section if available
    if process_metrics and isinstance(process_metrics, dict):
        lines.extend(_generate_process_metrics_section(process_metrics))

    # Add agent output link
    lines.extend(
        [
            "---",
            "",
            "## Agent Output",
            "",
            "- [View agent output](./agent/output.txt)",
            "- [View agent result JSON](./agent/result.json)",
            "",
        ]
    )

    lines.extend(
        [
            "---",
            "",
            "*Generated by Scylla E2E Framework*",
        ]
    )

    return "\n".join(lines)


def save_run_report(
    output_path: Path,
    tier_id: str,
    subtest_id: str,
    run_number: int,
    score: float,
    grade: str,
    passed: bool,
    reasoning: str,
    cost_usd: float,
    duration_seconds: float,
    tokens_input: int,
    tokens_output: int,
    exit_code: int,
    task_prompt: str,
    workspace_path: Path,
    judges: list[Any] | None = None,
    criteria_scores: dict[str, dict[str, Any]] | None = None,
    agent_output: str | None = None,
    token_stats: dict[str, int] | None = None,
    agent_duration_seconds: float | None = None,
    judge_duration_seconds: float | None = None,
    process_metrics: dict[str, Any] | None = None,
) -> None:
    """Generate and save markdown report for a single run.

    Args:
        output_path: Path to save the report (e.g., logs/report.md)
        ... (same as generate_run_report)

    """
    report = generate_run_report(
        tier_id=tier_id,
        subtest_id=subtest_id,
        run_number=run_number,
        score=score,
        grade=grade,
        passed=passed,
        reasoning=reasoning,
        cost_usd=cost_usd,
        duration_seconds=duration_seconds,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        exit_code=exit_code,
        task_prompt=task_prompt,
        workspace_path=workspace_path,
        judges=judges,
        criteria_scores=criteria_scores,
        agent_output=agent_output,
        token_stats=token_stats,
        agent_duration_seconds=agent_duration_seconds,
        judge_duration_seconds=judge_duration_seconds,
        process_metrics=process_metrics,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
