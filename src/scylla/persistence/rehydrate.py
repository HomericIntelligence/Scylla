"""Re-hydrate in-memory data structures from on-disk run_result.json files.

Used when the checkpoint state machine resumes past the actions that originally
populated these structures (e.g., subtest AGGREGATED, tier SUBTESTS_RUNNING+,
experiment TIERS_COMPLETE+).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scylla.e2e.judge_selection import JudgeSelection
    from scylla.e2e.models import (
        E2ERunResult,
        ExperimentConfig,
        SubTestResult,
        TierID,
        TierResult,
    )

logger = logging.getLogger(__name__)


def load_subtest_run_results(results_dir: Path) -> list[E2ERunResult]:
    """Load E2ERunResult objects from results_dir/run_*/run_result.json.

    Scans one level deep for run_NN subdirectories, skips .failed directories,
    and returns a list sorted by run_number.

    Args:
        results_dir: Subtest results directory (e.g., experiment/T0/00/).

    Returns:
        Sorted list of E2ERunResult objects. Empty list if dir does not exist
        or contains no valid run_result.json files.

    """
    from scylla.e2e.subtest_executor import _load_run_result

    if not results_dir.exists():
        return []

    run_results: list[E2ERunResult] = []
    for run_result_path in results_dir.glob("run_*/run_result.json"):
        # Skip .failed directories
        if ".failed" in run_result_path.parts:
            continue
        try:
            run_result = _load_run_result(run_result_path)
            run_results.append(run_result)
        except Exception as e:
            logger.warning(f"Skipping invalid run_result.json at {run_result_path}: {e}")

    run_results.sort(key=lambda r: r.run_number)
    return run_results


def load_tier_subtest_results(tier_dir: Path, tier_id: TierID) -> dict[str, SubTestResult]:
    """Load SubTestResult objects for a tier by scanning its subdirectories.

    Walks tier_dir/<subtest_id>/ subdirectories, calls load_subtest_run_results()
    for each, and aggregates via aggregate_run_results().

    Args:
        tier_dir: Tier results directory (e.g., experiment/T0/).
        tier_id: TierID enum value for aggregation.

    Returns:
        Dict mapping subtest_id -> SubTestResult. Empty dict if tier_dir does
        not exist or contains no valid run data.

    """
    from scylla.e2e.subtest_executor import aggregate_run_results

    if not tier_dir.exists():
        return {}

    subtest_results: dict[str, SubTestResult] = {}
    for subtest_dir in sorted(tier_dir.iterdir()):
        if not subtest_dir.is_dir():
            continue
        # Skip hidden/special directories
        if subtest_dir.name.startswith("."):
            continue

        subtest_id = subtest_dir.name
        runs = load_subtest_run_results(subtest_dir)
        if not runs:
            continue

        subtest_result = aggregate_run_results(tier_id, subtest_id, runs)
        subtest_results[subtest_id] = subtest_result
        logger.debug(f"Re-hydrated {len(runs)} runs for {tier_id.value}/{subtest_id}")

    return subtest_results


def load_tier_selection(tier_dir: Path) -> JudgeSelection | None:
    """Load JudgeSelection from tier_dir/best_subtest.json.

    Args:
        tier_dir: Tier results directory containing best_subtest.json.

    Returns:
        JudgeSelection if file exists and is valid, None otherwise.

    """
    from scylla.e2e.judge_selection import JudgeSelection

    best_subtest_path = tier_dir / "best_subtest.json"
    if not best_subtest_path.exists():
        return None

    try:
        data = json.loads(best_subtest_path.read_text())
        return JudgeSelection.model_validate(data)
    except Exception as e:
        logger.warning(f"Could not load best_subtest.json from {tier_dir}: {e}")
        return None


def load_experiment_tier_results(
    experiment_dir: Path, config: ExperimentConfig
) -> dict[TierID, TierResult]:
    """Load TierResult objects for an experiment by scanning all run_result.json files.

    Delegates to regenerate.scan_run_results() and regenerate.rebuild_tier_results().

    Args:
        experiment_dir: Experiment results directory.
        config: ExperimentConfig with judge_models and other settings.

    Returns:
        Dict mapping TierID -> TierResult. Empty dict if no valid data found.

    """
    from scylla.e2e.regenerate import RegenerateStats, rebuild_tier_results, scan_run_results

    stats = RegenerateStats()
    run_results = scan_run_results(experiment_dir, stats)
    if not run_results:
        return {}

    tier_results = rebuild_tier_results(run_results, config, stats)
    logger.debug(
        f"Re-hydrated {len(tier_results)} tiers, "
        f"{stats.subtests_processed} subtests, {stats.runs_valid} runs "
        f"from {experiment_dir}"
    )
    return tier_results
