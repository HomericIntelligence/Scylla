"""Regenerate results.json and reports from existing run_result.json files.

This module provides functionality to rebuild experiment results without re-running
agents or judges. It can also selectively re-run judges for runs that are missing
judge results.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel

from scylla.config.constants import DEFAULT_JUDGE_MODEL
from scylla.e2e.agent_runner import _has_valid_agent_result
from scylla.e2e.judge_runner import _has_valid_judge_result
from scylla.e2e.judge_selection import select_best_subtest
from scylla.e2e.llm_judge import run_llm_judge
from scylla.e2e.models import (
    E2ERunResult,
    ExperimentConfig,
    ExperimentResult,
    SubTestResult,
    TierID,
    TierResult,
    TokenStats,
)
from scylla.e2e.run_report import (
    generate_experiment_summary_table,
    generate_tier_summary_table,
    save_experiment_report,
    save_subtest_report,
    save_tier_report,
)
from scylla.e2e.subtest_executor import aggregate_run_results

logger = logging.getLogger(__name__)


class RegenerateStats(BaseModel):
    """Statistics from regeneration process."""

    runs_found: int = 0
    runs_valid: int = 0
    runs_rejudged: int = 0
    runs_skipped: int = 0
    tiers_processed: int = 0
    subtests_processed: int = 0


def regenerate_experiment(
    experiment_dir: Path,
    rejudge: bool = False,
    judge_model: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> RegenerateStats:
    """Regenerate experiment results from existing run_result.json files.

    Args:
        experiment_dir: Path to experiment directory
        rejudge: Whether to re-run judges for missing judge results
        judge_model: Override judge model (default: from config)
        dry_run: Show what would be done without modifying files
        verbose: Enable verbose logging

    Returns:
        Statistics about the regeneration process.

    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.info(f"🔍 Scanning experiment directory: {experiment_dir}")

    # Load experiment config
    config_file = experiment_dir / "config" / "experiment.json"
    if not config_file.exists():
        raise FileNotFoundError(f"Experiment config not found: {config_file}")

    config = ExperimentConfig.load(config_file)
    logger.info(f"✅ Loaded config for experiment: {config.experiment_id}")

    # Determine judge model
    effective_judge_model = judge_model
    if effective_judge_model is None:
        # Use first judge model from config (primary judge)
        effective_judge_model = (
            config.judge_models[0] if config.judge_models else DEFAULT_JUDGE_MODEL
        )
    logger.info(f"📊 Using judge model: {effective_judge_model}")

    # Scan for run results
    stats = RegenerateStats()
    run_results = scan_run_results(experiment_dir, stats)

    if not run_results:
        logger.warning("⚠️  No run results found in experiment directory")
        return stats

    logger.info(
        f"📦 Found {stats.runs_found} run_result.json files "
        f"({stats.runs_valid} valid, {stats.runs_found - stats.runs_valid} invalid)"
    )

    # Re-judge if requested
    if rejudge:
        logger.info("⚖️  Re-judging runs with missing judge results...")
        rejudge_missing_runs(
            experiment_dir, config, run_results, effective_judge_model, dry_run, stats
        )
        logger.info(f"✅ Re-judged {stats.runs_rejudged} runs")

    # Rebuild tier results
    logger.info("🔨 Rebuilding tier results...")
    tier_results = rebuild_tier_results(run_results, config, stats)
    logger.info(f"✅ Processed {stats.tiers_processed} tiers, {stats.subtests_processed} subtests")

    # Rebuild experiment result
    logger.info("🔨 Rebuilding experiment result...")
    experiment_result = rebuild_experiment_result(tier_results, config)

    # Save all results
    if not dry_run:
        logger.info("💾 Saving results and reports...")
        save_all_results(experiment_dir, experiment_result, config)
        logger.info("✅ Results and reports saved successfully")
    else:
        logger.info("🔍 DRY RUN: Would save results and reports")

    logger.info(
        f"\n📊 Regeneration complete:\n"
        f"  Runs found: {stats.runs_found}\n"
        f"  Runs valid: {stats.runs_valid}\n"
        f"  Runs re-judged: {stats.runs_rejudged}\n"
        f"  Tiers processed: {stats.tiers_processed}\n"
        f"  Subtests processed: {stats.subtests_processed}"
    )

    return stats


def scan_run_results(
    experiment_dir: Path,
    stats: RegenerateStats,
) -> dict[str, dict[str, list[E2ERunResult]]]:
    """Scan for run_result.json files and reconstruct E2ERunResult objects.

    Args:
        experiment_dir: Path to experiment directory
        stats: Statistics object to update

    Returns:
        Dict mapping tier_id -> subtest_id -> list[E2ERunResult].

    """
    results: dict[str, dict[str, list[E2ERunResult]]] = {}

    # Find all run_result.json files — only scan completed/ to exclude in-progress runs
    from scylla.e2e.paths import COMPLETED_DIR

    scan_root = experiment_dir / COMPLETED_DIR
    for run_result_file in scan_root.rglob("run_result.json"):
        stats.runs_found += 1

        # Skip .failed directories
        if ".failed" in run_result_file.parts:
            logger.debug(f"Skipping failed run: {run_result_file}")
            stats.runs_skipped += 1
            continue

        # Parse directory structure: T0/00-subtest/run_01/run_result.json
        try:
            run_dir = run_result_file.parent
            subtest_dir = run_dir.parent
            tier_dir = subtest_dir.parent

            # Extract IDs
            tier_id = tier_dir.name
            if not tier_id.startswith("T"):
                logger.debug(f"Skipping non-tier directory: {tier_id}")
                stats.runs_skipped += 1
                continue

            subtest_id = subtest_dir.name

            # Load and validate run result
            try:
                with open(run_result_file) as f:
                    data = json.load(f)

                # Reconstruct E2ERunResult (same logic as subtest_executor.py:659-681)
                run_result = E2ERunResult(
                    run_number=data["run_number"],
                    exit_code=data["exit_code"],
                    token_stats=TokenStats.from_dict(data["token_stats"]),
                    cost_usd=data["cost_usd"],
                    duration_seconds=data["duration_seconds"],
                    agent_duration_seconds=data.get("agent_duration_seconds", 0.0),
                    judge_duration_seconds=data.get("judge_duration_seconds", 0.0),
                    judge_score=data["judge_score"],
                    judge_passed=data["judge_passed"],
                    judge_grade=data["judge_grade"],
                    judge_reasoning=data["judge_reasoning"],
                    workspace_path=Path(data["workspace_path"]),
                    logs_path=Path(data["logs_path"]),
                    command_log_path=(
                        Path(data["command_log_path"]) if data.get("command_log_path") else None
                    ),
                    criteria_scores=data.get("criteria_scores") or {},
                )

                # Add to results
                if tier_id not in results:
                    results[tier_id] = {}
                if subtest_id not in results[tier_id]:
                    results[tier_id][subtest_id] = []

                results[tier_id][subtest_id].append(run_result)
                stats.runs_valid += 1

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"⚠️  Invalid run_result.json: {run_result_file}: {e}")
                stats.runs_skipped += 1
                continue

        except (IndexError, ValueError) as e:
            logger.warning(f"⚠️  Invalid directory structure: {run_result_file}: {e}")
            stats.runs_skipped += 1
            continue

    return results


def _rejudge_single_run(
    experiment_dir: Path,
    config: ExperimentConfig,
    run: E2ERunResult,
    run_dir: Path,
    judge_model: str,
    stats: RegenerateStats,
) -> None:
    """Perform judge re-execution for a single run.

    Args:
        experiment_dir: Path to experiment directory
        config: Experiment configuration
        run: The run result to rejudge
        run_dir: Path to the run directory
        judge_model: Judge model to use
        stats: Statistics object to update

    """
    import time
    from datetime import datetime, timezone

    workspace = run_dir / "workspace"

    # Load agent output
    agent_output_file = run_dir / "agent" / "output.txt"
    if not agent_output_file.exists():
        logger.warning(f"⚠️  Agent output not found: {agent_output_file}")
        return
    agent_output = agent_output_file.read_text()

    # Load task prompt
    task_prompt_file = experiment_dir / "prompt.md"
    if not task_prompt_file.exists():
        task_prompt_file = run_dir / "task_prompt.md"
    if not task_prompt_file.exists():
        logger.warning(f"⚠️  Task prompt not found for {run_dir}")
        return
    task_prompt = task_prompt_file.read_text()

    # Backup old run_result.json
    run_result_file = run_dir / "run_result.json"
    if run_result_file.exists():
        backup_file = run_dir / "run_result.json.pre-rejudge"
        shutil.copy2(run_result_file, backup_file)

    judge_dir = run_dir / "judge"
    judge_dir.mkdir(exist_ok=True)
    saved_judge_prompt_path = run_dir / "judge_prompt.md"

    try:
        if saved_judge_prompt_path.exists():
            # Reuse the original judge prompt to avoid rebuilding
            # from potentially corrupted workspace
            logger.info(f"Re-judging {run_dir} with model {judge_model} (using saved prompt)")

            from scylla.e2e.llm_judge import _call_claude_judge, _parse_judge_response
            from scylla.e2e.pipeline_scripts import _save_judge_logs

            judge_prompt = saved_judge_prompt_path.read_text()
            judge_start = time.time()

            stdout, stderr, result = _call_claude_judge(judge_prompt, judge_model, workspace)
            judge_result = _parse_judge_response(result)

            _save_judge_logs(
                judge_dir,
                judge_prompt,
                result,
                judge_result,
                judge_model,
                workspace,
                raw_stdout=stdout,
                raw_stderr=stderr,
                language=config.language,
            )

            judge_duration = time.time() - judge_start
            timing_file = judge_dir / "timing.json"
            with open(timing_file, "w") as f:
                json.dump(
                    {
                        "judge_duration_seconds": judge_duration,
                        "measured_at": datetime.now(timezone.utc).isoformat(),
                        "rejudge": True,
                        "used_saved_prompt": True,
                    },
                    f,
                    indent=2,
                )
        else:
            # Fallback: rebuild from workspace (old behavior, but log warning)
            logger.warning(
                f"Saved judge_prompt.md not found at {saved_judge_prompt_path}, "
                f"rebuilding from workspace (may be inaccurate)"
            )
            judge_result = run_llm_judge(
                workspace=workspace,
                task_prompt=task_prompt,
                agent_output=agent_output,
                model=judge_model,
                judge_dir=judge_dir,
                reference_patch_path=(
                    experiment_dir / "reference.patch"
                    if (experiment_dir / "reference.patch").exists()
                    else None
                ),
                rubric_path=(
                    experiment_dir / "rubric.yaml"
                    if (experiment_dir / "rubric.yaml").exists()
                    else None
                ),
            )

        # Update run result with new judge scores
        run.judge_score = judge_result.score
        run.judge_passed = judge_result.passed
        run.judge_grade = judge_result.grade
        run.judge_reasoning = judge_result.reasoning
        run.criteria_scores = judge_result.criteria_scores or {}

        # Save updated run_result.json
        with open(run_result_file, "w") as f:
            json.dump(
                {
                    "run_number": run.run_number,
                    "exit_code": run.exit_code,
                    "token_stats": run.token_stats.to_dict(),
                    "cost_usd": run.cost_usd,
                    "duration_seconds": run.duration_seconds,
                    "agent_duration_seconds": run.agent_duration_seconds,
                    "judge_duration_seconds": run.judge_duration_seconds,
                    "judge_score": run.judge_score,
                    "judge_passed": run.judge_passed,
                    "judge_grade": run.judge_grade,
                    "judge_reasoning": run.judge_reasoning,
                    "workspace_path": str(run.workspace_path),
                    "logs_path": str(run.logs_path),
                    "command_log_path": (
                        str(run.command_log_path) if run.command_log_path else None
                    ),
                    "criteria_scores": run.criteria_scores,
                },
                f,
                indent=2,
            )

        stats.runs_rejudged += 1
        logger.info(f"✅ Re-judged {run_dir}: score={judge_result.score:.2f}")

    except Exception as judge_error:
        # Log error with context
        logger.error(
            f"❌ Judge failed for {run_dir} with model {judge_model}: {judge_error}",
            exc_info=True,
        )

        # Save error artifacts
        timing_file = judge_dir / "timing.json"
        with open(timing_file, "w") as f:
            json.dump(
                {
                    "judge_duration_seconds": 0.0,
                    "measured_at": datetime.now(timezone.utc).isoformat(),
                    "failed": True,
                    "error": str(judge_error),
                },
                f,
                indent=2,
            )

        error_file = judge_dir / "error.log"
        error_file.write_text(f"Judge failed: {judge_error}\n")


def rejudge_missing_runs(
    experiment_dir: Path,
    config: ExperimentConfig,
    run_results: dict[str, dict[str, list[E2ERunResult]]],
    judge_model: str,
    dry_run: bool,
    stats: RegenerateStats,
) -> None:
    """Re-run judges for runs with missing judge results.

    Args:
        experiment_dir: Path to experiment directory
        config: Experiment configuration
        run_results: Dict of tier -> subtest -> runs
        judge_model: Judge model to use
        dry_run: If True, only show what would be done
        stats: Statistics object to update

    """
    for tier_id, subtests in run_results.items():
        for subtest_id, runs in subtests.items():
            for run in runs:
                from scylla.e2e.paths import get_run_dir

                run_dir = get_run_dir(
                    experiment_dir, tier_id, subtest_id, run.run_number, completed=True
                )

                # Check if judge result exists and is valid
                if _has_valid_judge_result(run_dir):
                    logger.debug(f"Judge result exists for {run_dir}")
                    continue

                # Check if agent result exists
                if not _has_valid_agent_result(run_dir):
                    logger.warning(f"⚠️  No valid agent result for {run_dir}, cannot re-judge")
                    continue

                # Check if workspace exists
                workspace = run_dir / "workspace"
                if not workspace.exists():
                    logger.warning(f"⚠️  Workspace not found for {run_dir}, cannot re-judge")
                    continue

                logger.info(f"⚖️  Re-judging: {run_dir}")

                if dry_run:
                    stats.runs_rejudged += 1
                    continue

                try:
                    _rejudge_single_run(experiment_dir, config, run, run_dir, judge_model, stats)
                except Exception as e:
                    logger.error(f"❌ Failed to re-judge {run_dir}: {e}")
                    continue


def rebuild_tier_results(
    run_results: dict[str, dict[str, list[E2ERunResult]]],
    config: ExperimentConfig,
    stats: RegenerateStats,
) -> dict[TierID, TierResult]:
    """Rebuild tier results from run results.

    Args:
        run_results: Dict of tier -> subtest -> runs
        config: Experiment configuration
        stats: Statistics object to update

    Returns:
        Dict mapping TierID to TierResult.

    """
    tier_results: dict[TierID, TierResult] = {}

    for tier_id_str, subtests in run_results.items():
        try:
            tier_id = TierID(tier_id_str)
        except ValueError:
            logger.warning(f"⚠️  Invalid tier ID: {tier_id_str}, skipping")
            continue

        stats.tiers_processed += 1

        # Build subtest results
        subtest_results: dict[str, SubTestResult] = {}
        for subtest_id, runs in subtests.items():
            stats.subtests_processed += 1

            # Sort runs by run_number
            runs.sort(key=lambda r: r.run_number)

            # Aggregate results (shared implementation from subtest_executor.py)
            subtest_result = aggregate_run_results(tier_id, subtest_id, runs)
            subtest_results[subtest_id] = subtest_result

        # Select best subtest
        if subtest_results:
            selection = select_best_subtest(
                subtest_results, config.judge_models, tie_threshold=0.05
            )
            best_subtest_id = selection.winning_subtest

            # Mark best subtest
            for subtest_id in subtest_results:
                subtest_results[subtest_id].selected_as_best = subtest_id == best_subtest_id

            best_subtest = subtest_results[best_subtest_id]

            # Build tier result
            tier_result = TierResult(
                tier_id=tier_id,
                subtest_results=subtest_results,
                best_subtest=best_subtest_id,
                best_subtest_score=best_subtest.median_score,
                total_cost=sum(s.total_cost for s in subtest_results.values()),
            )

            tier_results[tier_id] = tier_result

    return tier_results


def rebuild_experiment_result(
    tier_results: dict[TierID, TierResult],
    config: ExperimentConfig,
) -> ExperimentResult:
    """Rebuild experiment result from tier results.

    Args:
        tier_results: Dict of tier results
        config: Experiment configuration

    Returns:
        ExperimentResult with all tier results.

    """
    # Find frontier tier (from runner.py:755-787)
    best_tier, best_cop = _find_frontier(tier_results)

    return ExperimentResult(
        config=config,
        tier_results=tier_results,
        best_overall_tier=best_tier,
        frontier_cop=best_cop,
        frontier_cop_tier=best_tier,
    )


def _find_frontier(
    tier_results: dict[TierID, TierResult],
) -> tuple[TierID | None, float]:
    """Find the frontier tier (best cost-of-pass) (from runner.py:755-787)."""
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


def save_all_results(
    experiment_dir: Path,
    result: ExperimentResult,
    config: ExperimentConfig,
) -> None:
    """Save all results and reports at every level.

    Args:
        experiment_dir: Path to experiment directory
        result: ExperimentResult to save
        config: Experiment configuration

    """
    # Backup existing result.json
    result_file = experiment_dir / "result.json"
    if result_file.exists():
        backup_file = experiment_dir / "result.json.backup"
        shutil.copy2(result_file, backup_file)
        logger.info(f"📦 Backed up existing result.json to {backup_file.name}")

    # Save experiment-level result
    result.save(experiment_dir / "result.json")

    # Save experiment-level reports
    save_experiment_report(experiment_dir, result)

    # Generate and save summary table
    summary_md = generate_experiment_summary_table(result.tier_results)
    (experiment_dir / "summary.md").write_text(summary_md)

    # Save tier-level reports to completed/ phase directory
    from scylla.e2e.paths import get_subtest_dir, get_tier_dir

    for tier_id, tier_result in result.tier_results.items():
        tier_dir = get_tier_dir(experiment_dir, tier_id.value, completed=True)
        tier_dir.mkdir(parents=True, exist_ok=True)
        save_tier_report(tier_dir, tier_id.value, tier_result)

        # Generate and save tier summary
        tier_summary_md = generate_tier_summary_table(tier_id.value, tier_result.subtest_results)
        (tier_dir / "summary.md").write_text(tier_summary_md)

        # Save subtest-level reports
        for subtest_id, subtest_result in tier_result.subtest_results.items():
            subtest_dir = get_subtest_dir(experiment_dir, tier_id.value, subtest_id, completed=True)
            subtest_dir.mkdir(parents=True, exist_ok=True)
            save_subtest_report(subtest_dir, subtest_id, subtest_result)
