"""Re-run judges for failed, never-run, or incomplete judge evaluations.

This module scans an experiment directory and identifies individual judge slots
(judge_01, judge_02, judge_03) that need re-execution. It handles per-slot granularity:
1. Complete - judgment.json exists and is valid
2. Missing - judge_NN/ dir doesn't exist
3. Failed - judge_NN/ exists but judgment.json is invalid/missing
4. Agent failed - Agent failed, cannot judge (skip)

After re-running missing judge slots, regenerates judge/result.json consensus.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from scylla.e2e.agent_runner import _has_valid_agent_result
from scylla.e2e.models import ExperimentConfig
from scylla.e2e.rerun_base import load_rerun_context, print_dry_run_summary
from scylla.e2e.tier_manager import TierManager
from scylla.metrics.grading import assign_letter_grade

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class JudgeSlotStatus(Enum):
    """Status of a single judge slot (judge_01, judge_02, etc.)."""

    COMPLETE = "complete"  # judgment.json exists and is valid
    MISSING = "missing"  # judge_NN/ dir doesn't exist
    FAILED = "failed"  # judge_NN/ exists but judgment.json is invalid/missing
    AGENT_FAILED = "agent_failed"  # Agent failed, cannot judge


class RerunJudgeStats(BaseModel):
    """Statistics from judge rerun process."""

    total_expected_slots: int = 0  # Total judge slots expected (runs x judges)
    per_slot_stats: dict[int, dict[str, int]] = Field(
        default_factory=dict
    )  # Stats per judge slot number

    # Overall stats
    complete: int = 0
    missing: int = 0
    failed: int = 0
    agent_failed: int = 0
    slots_rerun_success: int = 0
    slots_rerun_failed: int = 0
    consensus_regenerated: int = 0  # Number of run_dirs where consensus was regenerated
    runs_skipped_by_filter: int = 0

    def print_summary(self, judge_models: list[str]) -> None:
        """Log a summary of rerun statistics."""
        logger.info("=" * 70)
        logger.info("JUDGE SLOT CLASSIFICATION")
        logger.info("=" * 70)
        logger.info(f"Total expected judge slots: {self.total_expected_slots}")
        logger.info("  Per-slot breakdown:")

        for judge_num in sorted(self.per_slot_stats.keys()):
            stats = self.per_slot_stats[judge_num]
            model = judge_models[judge_num - 1] if judge_num <= len(judge_models) else "unknown"
            logger.info(f"    judge_{judge_num:02d} ({model}):")
            logger.info(
                f"      complete: {stats.get('complete', 0):4d}    "
                f"missing: {stats.get('missing', 0):4d}     "
                f"failed: {stats.get('failed', 0):4d}"
            )

        logger.info("RERUN RESULTS")
        logger.info("=" * 70)
        logger.info(f"Judge slots rerun successfully:  {self.slots_rerun_success}")
        logger.info(f"Judge slots failed to rerun:     {self.slots_rerun_failed}")
        logger.info(f"Consensus regenerated (runs):    {self.consensus_regenerated}")
        logger.info("=" * 70)


class JudgeSlotToRerun(BaseModel):
    """A single judge slot that needs re-running."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tier_id: str  # e.g., "T0"
    subtest_id: str  # e.g., "00"
    run_number: int  # 1-based
    run_dir: Path  # Full path to run_NN/ directory
    judge_number: int  # 1, 2, or 3
    judge_model: str  # Model to use for this slot
    status: JudgeSlotStatus  # Current status
    reason: str  # Human-readable description


def _is_valid_judgment(judgment_file: Path) -> bool:
    """Check if judgment.json is valid.

    Args:
        judgment_file: Path to judgment.json

    Returns:
        True if judgment file exists and is valid JSON with required fields
        and is_valid flag is not False

    """
    if not judgment_file.exists():
        return False

    try:
        with open(judgment_file) as f:
            data = json.load(f)
            # Must have score field and is_valid must not be False
            # (missing is_valid defaults to True for backward compatibility)
            is_valid = data.get("is_valid", True) is not False
            return "score" in data and is_valid
    except (json.JSONDecodeError, OSError):
        return False


def _classify_judge_slots(
    run_dir: Path,
    judge_models: list[str],
) -> list[tuple[int, str, JudgeSlotStatus]]:
    """Classify each judge slot (judge_01, judge_02, etc.) individually.

    Args:
        run_dir: Path to run directory
        judge_models: List of judge models (used to map judge_num -> model)

    Returns:
        List of (judge_number, judge_model, status) tuples

    """
    # First check agent validity
    if not _has_valid_agent_result(run_dir):
        return [(i + 1, m, JudgeSlotStatus.AGENT_FAILED) for i, m in enumerate(judge_models)]

    results = []
    for judge_num, model in enumerate(judge_models, start=1):
        judge_slot_dir = run_dir / "judge" / f"judge_{judge_num:02d}"
        judgment_file = judge_slot_dir / "judgment.json"

        if not judge_slot_dir.exists():
            results.append((judge_num, model, JudgeSlotStatus.MISSING))
        elif not judgment_file.exists():
            results.append((judge_num, model, JudgeSlotStatus.FAILED))
        elif _is_valid_judgment(judgment_file):
            results.append((judge_num, model, JudgeSlotStatus.COMPLETE))
        else:
            results.append((judge_num, model, JudgeSlotStatus.FAILED))

    return results


def scan_judges_needing_rerun(  # noqa: C901  # judge scan with many filter conditions
    experiment_dir: Path,
    config: ExperimentConfig,
    tier_manager: TierManager,
    tier_filter: list[str] | None = None,
    subtest_filter: list[str] | None = None,
    run_filter: list[int] | None = None,
    judge_slot_filter: list[int] | None = None,
    status_filter: list[JudgeSlotStatus] | None = None,
    stats: RerunJudgeStats | None = None,
) -> dict[JudgeSlotStatus, list[JudgeSlotToRerun]]:
    """Scan experiment directory and classify judge slots by status.

    Args:
        experiment_dir: Path to experiment directory
        config: Experiment configuration
        tier_manager: TierManager instance
        tier_filter: Only process these tiers (e.g., ["T0", "T1"])
        subtest_filter: Only process these subtests (e.g., ["00", "01"])
        run_filter: Only process these run numbers (e.g., [1, 3, 5])
        judge_slot_filter: Only process these judge slots (e.g., [1, 3])
        status_filter: Only include judge slots with these statuses
        stats: RerunJudgeStats instance to update (optional)

    Returns:
        Dictionary mapping JudgeSlotStatus to list of JudgeSlotToRerun instances

    """
    if stats is None:
        stats = RerunJudgeStats()

    slots_by_status: dict[JudgeSlotStatus, list[JudgeSlotToRerun]] = {
        status: [] for status in JudgeSlotStatus
    }

    # Iterate over all tiers to run
    for tier_id in config.tiers_to_run:
        tier_str = tier_id.value

        # Apply tier filter
        if tier_filter and tier_str not in tier_filter:
            continue

        # Load tier config to get subtests
        tier_config = tier_manager.load_tier_config(tier_id)

        # Limit subtests if max_subtests is set
        subtests = tier_config.subtests
        if config.max_subtests is not None:
            subtests = subtests[: config.max_subtests]

        # Iterate over all subtests
        for subtest in subtests:
            subtest_id = subtest.id

            # Apply subtest filter
            if subtest_filter and subtest_id not in subtest_filter:
                continue

            subtest_dir = experiment_dir / tier_str / subtest_id

            # Iterate over all expected runs
            for run_number in range(1, config.runs_per_subtest + 1):
                # Apply run filter
                if run_filter and run_number not in run_filter:
                    stats.runs_skipped_by_filter += 1
                    continue

                run_dir = subtest_dir / f"run_{run_number:02d}"

                # Classify each judge slot
                slot_statuses = _classify_judge_slots(run_dir, config.judge_models)

                for judge_num, judge_model, status in slot_statuses:
                    # Apply judge slot filter
                    if judge_slot_filter and judge_num not in judge_slot_filter:
                        continue

                    # Update stats
                    stats.total_expected_slots += 1

                    # Update per-slot stats
                    if judge_num not in stats.per_slot_stats:
                        stats.per_slot_stats[judge_num] = {
                            "complete": 0,
                            "missing": 0,
                            "failed": 0,
                            "agent_failed": 0,
                        }

                    if status == JudgeSlotStatus.COMPLETE:
                        stats.complete += 1
                        stats.per_slot_stats[judge_num]["complete"] += 1
                    elif status == JudgeSlotStatus.MISSING:
                        stats.missing += 1
                        stats.per_slot_stats[judge_num]["missing"] += 1
                    elif status == JudgeSlotStatus.FAILED:
                        stats.failed += 1
                        stats.per_slot_stats[judge_num]["failed"] += 1
                    elif status == JudgeSlotStatus.AGENT_FAILED:
                        stats.agent_failed += 1
                        stats.per_slot_stats[judge_num]["agent_failed"] += 1

                    # Apply status filter
                    if status_filter and status not in status_filter:
                        continue

                    # Create human-readable reason
                    reason_map = {
                        JudgeSlotStatus.COMPLETE: (
                            f"Judge {judge_num} complete (no action needed)"
                        ),
                        JudgeSlotStatus.MISSING: (
                            f"Judge {judge_num} never ran (judge_{judge_num:02d}/ missing)"
                        ),
                        JudgeSlotStatus.FAILED: (
                            f"Judge {judge_num} ran but failed (no valid judgment.json)"
                        ),
                        JudgeSlotStatus.AGENT_FAILED: "Agent failed, cannot judge",
                    }

                    slots_by_status[status].append(
                        JudgeSlotToRerun(
                            tier_id=tier_str,
                            subtest_id=subtest_id,
                            run_number=run_number,
                            run_dir=run_dir,
                            judge_number=judge_num,
                            judge_model=judge_model,
                            status=status,
                            reason=reason_map[status],
                        )
                    )

    return slots_by_status


def _rerun_single_judge_slot(
    slot: JudgeSlotToRerun, experiment_dir: Path, config: ExperimentConfig
) -> bool:
    """Re-run a single judge slot.

    Args:
        slot: JudgeSlotToRerun instance
        experiment_dir: Path to experiment directory
        config: Experiment configuration

    Returns:
        True if judge slot was successfully re-run

    """
    from scylla.e2e.llm_judge import run_llm_judge

    run_dir = slot.run_dir
    judge_dir = run_dir / "judge"
    judge_dir.mkdir(exist_ok=True)

    # Check if saved judge_prompt.md exists (from original run)
    saved_judge_prompt_path = run_dir / "judge_prompt.md"

    if saved_judge_prompt_path.exists():
        # Reuse the original judge prompt to avoid rebuilding from potentially corrupted workspace
        logger.info(
            f"Re-running judge slot {slot.judge_number} for "
            f"{slot.tier_id}/{slot.subtest_id}/run_{slot.run_number:02d} "
            f"with model {slot.judge_model} (using saved prompt)"
        )

        judge_prompt = saved_judge_prompt_path.read_text()
        workspace = run_dir / "workspace"

        # Run judge using the saved prompt directly
        # (bypass run_llm_judge which would rebuild prompt)
        import json
        import time
        from datetime import datetime, timezone

        from scylla.e2e.llm_judge import _call_claude_judge, _parse_judge_response
        from scylla.e2e.pipeline_scripts import _save_judge_logs

        try:
            judge_start = time.time()

            # Create judge-specific directory
            actual_judge_dir = judge_dir / f"judge_{slot.judge_number:02d}"
            actual_judge_dir.mkdir(parents=True, exist_ok=True)

            # Call Claude with saved prompt
            stdout, stderr, result = _call_claude_judge(judge_prompt, slot.judge_model, workspace)
            judge_result = _parse_judge_response(result)

            # Save logs
            _save_judge_logs(
                actual_judge_dir,
                judge_prompt,
                result,
                judge_result,
                slot.judge_model,
                workspace,
                raw_stdout=stdout,
                raw_stderr=stderr,
                language=config.language,
            )

            # Save timing
            judge_duration = time.time() - judge_start
            timing_file = actual_judge_dir / "timing.json"
            with open(timing_file, "w") as f:
                json.dump(
                    {
                        "judge_duration_seconds": judge_duration,
                        "measured_at": datetime.now(timezone.utc).isoformat(),
                        "rerun": True,
                        "used_saved_prompt": True,
                    },
                    f,
                    indent=2,
                )

            return judge_result.is_valid

        except Exception as e:
            logger.error(
                f"Failed to re-run judge slot {slot.judge_number} for "
                f"{slot.tier_id}/{slot.subtest_id}/run_{slot.run_number:02d}: {e}"
            )
            return False

    else:
        # Fallback: rebuild from workspace (old behavior, but log warning)
        logger.warning(
            f"Saved judge_prompt.md not found at {saved_judge_prompt_path}, "
            f"rebuilding from workspace (may be inaccurate if workspace was recreated)"
        )

        # Load agent output
        agent_output_file = run_dir / "agent" / "output.txt"
        if not agent_output_file.exists():
            logger.error(f"Agent output not found: {agent_output_file}")
            return False

        agent_output = agent_output_file.read_text()

        # Load task prompt
        task_prompt_file = experiment_dir / "prompt.md"
        if not task_prompt_file.exists():
            logger.error(f"Task prompt not found: {task_prompt_file}")
            return False

        task_prompt = task_prompt_file.read_text()

        # Find rubric
        rubric_candidate = experiment_dir / "rubric.yaml"
        rubric_path: Path | None = rubric_candidate if rubric_candidate.exists() else None

        workspace = run_dir / "workspace"

        logger.info(
            f"Re-running judge slot {slot.judge_number} for "
            f"{slot.tier_id}/{slot.subtest_id}/run_{slot.run_number:02d} "
            f"with model {slot.judge_model}"
        )

        # Run judge for this specific slot
        try:
            judge_result = run_llm_judge(
                workspace=workspace,
                task_prompt=task_prompt,
                agent_output=agent_output,
                model=slot.judge_model,
                judge_dir=judge_dir,
                judge_run_number=slot.judge_number,
                language=config.language,
                rubric_path=rubric_path,
            )

            return judge_result.is_valid

        except Exception as e:
            logger.error(
                f"Failed to re-run judge slot {slot.judge_number} for "
                f"{slot.tier_id}/{slot.subtest_id}/run_{slot.run_number:02d}: {e}"
            )
            return False


class _JudgeSlotResult(BaseModel):
    """Result from a parallel judge slot execution."""

    slot: JudgeSlotToRerun
    success: bool
    error: str | None = None


def _rerun_single_judge_slot_safe(
    slot: JudgeSlotToRerun,
    experiment_dir: Path,
    config: ExperimentConfig,
) -> _JudgeSlotResult:
    """Safe wrapper that never raises — prevents one failure from poisoning the pool."""
    try:
        success = _rerun_single_judge_slot(slot, experiment_dir, config)
        return _JudgeSlotResult(slot=slot, success=success)
    except Exception as e:
        logger.error(
            f"Unexpected exception in judge worker for "
            f"{slot.tier_id}/{slot.subtest_id}/run_{slot.run_number:02d} "
            f"judge_{slot.judge_number:02d}: {type(e).__name__}: {e}"
        )
        return _JudgeSlotResult(slot=slot, success=False, error=str(e))


def _load_judgments_from_dir(run_dir: Path, judge_models: list[str]) -> list[dict[str, Any]]:
    """Load all per-judge judgment.json files from a run directory.

    Args:
        run_dir: Path to run directory.
        judge_models: List of judge model names (determines expected judge count).

    Returns:
        List of judgment dicts (valid and invalid, for tracking purposes).

    """
    judges = []
    for judge_num, model in enumerate(judge_models, start=1):
        judgment_file = run_dir / "judge" / f"judge_{judge_num:02d}" / "judgment.json"
        if not judgment_file.exists():
            continue
        try:
            data = json.loads(judgment_file.read_text())
            if "score" not in data:
                continue
            is_valid = data.get("is_valid", True) is not False
            judges.append(
                {
                    "model": model,
                    "score": data.get("score"),
                    "passed": data.get("passed"),
                    "grade": data.get("grade"),
                    "reasoning": data.get("reasoning", ""),
                    "judge_number": judge_num,
                    "is_valid": is_valid,
                    "criteria_scores": data.get("criteria_scores"),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to load judgment from {judgment_file}: {e}")
    return judges


def _regenerate_consensus(run_dir: Path, judge_models: list[str]) -> bool:
    """Regenerate judge/result.json consensus from per-judge judgment files.

    Also updates run_result.json with the new consensus scores.

    Args:
        run_dir: Path to run directory
        judge_models: List of judge models (for metadata)

    Returns:
        True if consensus was successfully regenerated

    """
    judges = _load_judgments_from_dir(run_dir, judge_models)

    if not judges:
        logger.warning(f"No valid judge results found for {run_dir}, skipping consensus")
        return False

    # Compute consensus (same logic as subtest_executor._compute_judge_consensus)
    # Only include judgments with is_valid=True for score averaging
    valid = [j for j in judges if j["score"] is not None and j.get("is_valid", True)]
    if not valid:
        logger.warning(f"No valid scores for {run_dir}, skipping consensus")
        return False

    consensus_score = sum(j["score"] for j in valid) / len(valid)
    passed_votes = sum(1 for j in valid if j.get("passed", False))
    passed = passed_votes > len(valid) / 2
    grade = assign_letter_grade(consensus_score)

    # All judges must be valid for consensus to be valid
    consensus_is_valid = all(j.get("is_valid", True) for j in judges)

    # Use representative reasoning from judge closest to consensus score
    if valid:
        closest = min(valid, key=lambda j: abs(j["score"] - consensus_score))
        representative_reasoning = closest["reasoning"]
        representative_criteria = closest.get("criteria_scores")
    else:
        representative_reasoning = ""
        representative_criteria = None

    # Save judge/result.json
    result_data = {
        "score": consensus_score,
        "passed": passed,
        "grade": grade,
        "reasoning": representative_reasoning,
        "is_valid": consensus_is_valid,
        "criteria_scores": representative_criteria,
    }

    judge_result_file = run_dir / "judge" / "result.json"
    try:
        with open(judge_result_file, "w") as f:
            json.dump(result_data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write judge/result.json for {run_dir}: {e}")
        return False

    # Update run_result.json judge fields
    run_result_file = run_dir / "run_result.json"
    if run_result_file.exists():
        try:
            run_data = json.loads(run_result_file.read_text())
            run_data["judge_score"] = consensus_score
            run_data["judge_passed"] = passed
            run_data["judge_grade"] = grade
            run_data["judge_reasoning"] = representative_reasoning
            run_data["criteria_scores"] = representative_criteria or {}
            with open(run_result_file, "w") as f:
                json.dump(run_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to update run_result.json for {run_dir}: {e}")

    logger.info(
        f"Regenerated consensus for {run_dir.name}: "
        f"score={consensus_score:.2f}, passed={passed}, grade={grade}"
    )
    return True


def rerun_judges_experiment(  # noqa: C901  # judge rerun with many retry/skip paths
    experiment_dir: Path,
    dry_run: bool = False,
    verbose: bool = False,
    tier_filter: list[str] | None = None,
    subtest_filter: list[str] | None = None,
    run_filter: list[int] | None = None,
    judge_slot_filter: list[int] | None = None,
    status_filter: list[JudgeSlotStatus] | None = None,
    judge_model: str | None = None,
    regenerate_only: bool = False,
    parallel: int = 1,
) -> RerunJudgeStats:
    """Re-run judges for failed/missing judge evaluations in an experiment.

    Args:
        experiment_dir: Path to experiment directory
        dry_run: Show what would be done without executing
        verbose: Enable verbose logging
        tier_filter: Only process these tiers (e.g., ["T0", "T1"])
        subtest_filter: Only process these subtests (e.g., ["00", "01"])
        run_filter: Only process these run numbers (e.g., [1, 3, 5])
        judge_slot_filter: Only process these judge slots (e.g., [1, 3])
        status_filter: Only rerun judge slots with these statuses
        judge_model: Judge model to use (default: from config) - IGNORED, uses config.judge_models
        regenerate_only: Only regenerate consensus, don't re-run judges
        parallel: Number of judge slots to run in parallel (default: 1, sequential)

    Returns:
        RerunJudgeStats with summary of what was done

    """
    # Configure logging
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load experiment config and auto-detect tiers directory
    ctx = load_rerun_context(experiment_dir)
    config = ctx.config
    tier_manager = ctx.tier_manager
    logger.info(f"Judge models: {config.judge_models}")

    # Scan for judge slots by status
    stats = RerunJudgeStats()
    slots_by_status = scan_judges_needing_rerun(
        experiment_dir=experiment_dir,
        config=config,
        tier_manager=tier_manager,
        tier_filter=tier_filter,
        subtest_filter=subtest_filter,
        run_filter=run_filter,
        judge_slot_filter=judge_slot_filter,
        status_filter=status_filter,
        stats=stats,
    )

    # Print classification summary
    logger.info("Classification complete:")
    logger.info(f"  total slots:   {stats.total_expected_slots}")
    logger.info(f"  complete:      {stats.complete}")
    logger.info(f"  missing:       {stats.missing}")
    logger.info(f"  failed:        {stats.failed}")
    logger.info(f"  agent_failed:  {stats.agent_failed}")

    # Regenerate-only mode: just rebuild consensus files
    if regenerate_only:
        logger.info("Regenerate-only mode: rebuilding consensus files")

        # Find all runs where all judge slots are complete but result.json is missing
        runs_to_regenerate = set()
        for slot in slots_by_status[JudgeSlotStatus.COMPLETE]:
            result_file = slot.run_dir / "judge" / "result.json"
            if not result_file.exists():
                runs_to_regenerate.add(slot.run_dir)

        logger.info(f"Found {len(runs_to_regenerate)} runs needing consensus regeneration")

        if dry_run:
            logger.info("=" * 70)
            logger.info("DRY RUN MODE - No changes will be made")
            logger.info("=" * 70)
            logger.info(f"Would regenerate consensus for {len(runs_to_regenerate)} runs")
            logger.info("(All runs have complete judge slots but missing judge/result.json)")
            stats.print_summary(config.judge_models)
            return stats

        for run_dir in sorted(runs_to_regenerate):
            if _regenerate_consensus(run_dir, config.judge_models):
                stats.consensus_regenerated += 1

        stats.print_summary(config.judge_models)
        return stats

    # Standard dry-run mode (not regenerate-only)
    if dry_run:
        # Use shared dry-run summary formatter
        status_names = {
            status: status.value.upper().replace("_", " ") for status in JudgeSlotStatus
        }
        print_dry_run_summary(slots_by_status, status_names)

        stats.print_summary(config.judge_models)
        return stats

    # Determine which judge slots to rerun (exclude complete and agent_failed)
    needs_judge_rerun = []
    for status in [JudgeSlotStatus.MISSING, JudgeSlotStatus.FAILED]:
        needs_judge_rerun.extend(slots_by_status[status])

    logger.info(f"Judge slots needing re-execution: {len(needs_judge_rerun)}")

    # Re-run judges slot by slot
    if needs_judge_rerun:
        logger.info(f"Re-running {len(needs_judge_rerun)} judge slots (parallel={parallel})...")
        runs_with_reruns: set[Path] = set()

        if parallel <= 1 or len(needs_judge_rerun) <= 1:
            # === FAST PATH: Sequential (no pool overhead) ===
            for slot in needs_judge_rerun:
                if _rerun_single_judge_slot(slot, experiment_dir, config):
                    stats.slots_rerun_success += 1
                    runs_with_reruns.add(slot.run_dir)
                else:
                    stats.slots_rerun_failed += 1
        else:
            # === PARALLEL PATH: ThreadPoolExecutor ===
            lock = threading.Lock()
            total = len(needs_judge_rerun)
            completed_count = 0
            start_time = time.time()

            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(_rerun_single_judge_slot_safe, slot, experiment_dir, config): slot
                    for slot in needs_judge_rerun
                }

                for future in as_completed(futures):
                    result = future.result()  # Never raises (safe wrapper)
                    completed_count += 1

                    with lock:
                        if result.success:
                            stats.slots_rerun_success += 1
                            runs_with_reruns.add(result.slot.run_dir)
                        else:
                            stats.slots_rerun_failed += 1

                    # Progress logging
                    elapsed = time.time() - start_time
                    remaining = total - completed_count
                    slot = result.slot
                    status_str = "OK" if result.success else "FAIL"
                    logger.info(
                        f"[{completed_count}/{total}] "
                        f"{slot.tier_id}/{slot.subtest_id}/"
                        f"run_{slot.run_number:02d} "
                        f"judge_{slot.judge_number:02d} -> {status_str} "
                        f"({remaining} remaining, {elapsed:.0f}s elapsed)"
                    )

        logger.info(f"Re-ran {stats.slots_rerun_success} judge slots successfully")
        logger.info(f"Failed to re-run {stats.slots_rerun_failed} judge slots")

        # Consensus AFTER all slots complete (guaranteed by ThreadPoolExecutor context)
        logger.info(f"Regenerating consensus for {len(runs_with_reruns)} runs")
        for run_dir in sorted(runs_with_reruns):
            if _regenerate_consensus(run_dir, config.judge_models):
                stats.consensus_regenerated += 1

    stats.print_summary(config.judge_models)
    return stats
