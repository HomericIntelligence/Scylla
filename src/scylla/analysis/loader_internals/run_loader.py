"""Per-run loading: judge model resolution, judgments, and individual run records."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, cast

import jsonschema
import numpy as np

from scylla.e2e.models import TokenStats

from .models import CriterionScore, ItemScore, JudgeEvaluation, ModelUsage, RunData
from .validators import validate_bool, validate_int, validate_numeric

logger = logging.getLogger(__name__)

# Load JSON Schema for run_result.json validation
_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "run_result.schema.json"
with _SCHEMA_PATH.open() as _schema_file:
    _RUN_RESULT_SCHEMA = json.load(_schema_file)


def model_id_to_display(model_id: str) -> str:
    """Return model ID as its display name.

    Args:
        model_id: Model ID (e.g., "claude-sonnet-4-6")

    Returns:
        The model ID unchanged — display matches the identifier for clarity.

    Examples:
        >>> model_id_to_display("claude-sonnet-4-6")
        'claude-sonnet-4-6'
        >>> model_id_to_display("claude-haiku-4-5")
        'claude-haiku-4-5'
        >>> model_id_to_display("unknown-model")
        'unknown-model'

    """
    return model_id


def _find_model_md_in_experiment(experiment_dir: Path) -> str | None:
    """Scan tier/subtest/run directories for the first valid agent MODEL.md.

    Args:
        experiment_dir: Path to experiment directory.

    Returns:
        Model display string, or None if no MODEL.md found.

    """
    from scylla.e2e.paths import COMPLETED_DIR

    completed_dir = experiment_dir / COMPLETED_DIR
    scan_base = completed_dir if completed_dir.exists() else experiment_dir
    for tier_dir in sorted(scan_base.iterdir()):
        if not tier_dir.is_dir() or not tier_dir.name.startswith("T"):
            continue
        for subtest_dir in sorted(tier_dir.iterdir()):
            if not subtest_dir.is_dir() or not subtest_dir.name.isdigit():
                continue
            for run_dir in sorted(subtest_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue
                model_md = run_dir / "agent" / "MODEL.md"
                if model_md.exists():
                    try:
                        return model_id_to_display(parse_judge_model(model_md))
                    except Exception as e:
                        logger.warning("Failed to parse %s: %s", model_md, e)
    return None


def resolve_agent_model(experiment_dir: Path) -> str:
    """Resolve agent model from experiment configuration.

    Tries (in order):
    1. config/experiment.json -> models[0]
    2. First agent/MODEL.md file found

    Args:
        experiment_dir: Path to experiment directory (timestamped)

    Returns:
        Model ID string

    Raises:
        ValueError: If model cannot be determined

    """
    # Try experiment.json first
    config_path = experiment_dir / "config" / "experiment.json"
    if config_path.exists():
        try:
            with config_path.open() as f:
                config = json.load(f)
                models = config.get("models", [])
                if models:
                    return model_id_to_display(models[0])
        except Exception as e:
            logger.warning("Failed to read %s: %s", config_path, e)

    # Fallback: find first agent/MODEL.md
    model = _find_model_md_in_experiment(experiment_dir)
    if model is not None:
        return model

    raise ValueError(f"Could not determine agent model for {experiment_dir}")


def parse_judge_model(model_md_path: Path) -> str:
    """Parse judge model from MODEL.md file.

    Args:
        model_md_path: Path to MODEL.md file

    Returns:
        Judge model ID

    Raises:
        ValueError: If model pattern not found

    """
    content = model_md_path.read_text()
    match = re.search(r"\*\*Model\*\*:\s*(.+)", content)
    if not match:
        raise ValueError(f"Could not find model in {model_md_path}")
    return match.group(1).strip()


def load_agent_result(run_dir: Path) -> dict[str, Any]:
    """Load agent execution result from agent/result.json.

    Args:
        run_dir: Path to the run directory

    Returns:
        Dictionary with agent result data, or empty dict if not available

    """
    agent_result_path = run_dir / "agent" / "result.json"
    if not agent_result_path.exists():
        return {}

    try:
        with agent_result_path.open() as f:
            return cast(dict[str, Any], json.load(f))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load agent result %s: %s", agent_result_path, e)
        return {}


def load_judgment(judgment_path: Path, judge_number: int) -> JudgeEvaluation:
    """Load a single judge's evaluation.

    Args:
        judgment_path: Path to judgment.json file
        judge_number: Judge number (1, 2, or 3)

    Returns:
        Judge evaluation data

    """
    with judgment_path.open() as f:
        data = json.load(f)

    # Parse judge model from MODEL.md in same directory
    model_md_path = judgment_path.parent / "MODEL.md"
    judge_model = parse_judge_model(model_md_path)

    # Parse criteria scores (handle None case)
    criteria_scores_data = data.get("criteria_scores")
    if criteria_scores_data is None:
        criteria_scores_data = {}

    criteria = {}
    for criterion_name, criterion_data in criteria_scores_data.items():
        if criterion_data is None:
            continue

        items_data = criterion_data.get("items", {})
        if items_data is None:
            items_data = {}

        items = {}
        for item_id, item_data in items_data.items():
            if item_data is None:
                continue

            items[item_id] = ItemScore(
                item_id=item_id,
                achieved=item_data.get("achieved", "N/A"),
                max_points=item_data.get("max", "N/A"),
                reason=item_data.get("reason", ""),
            )

        criteria[criterion_name] = CriterionScore(
            name=criterion_name,
            achieved=criterion_data.get("achieved", np.nan),
            max_points=criterion_data.get("max", np.nan),
            score=criterion_data.get("score", np.nan),
            items=items,
        )

    # Check is_valid flag
    is_valid_raw = data.get("is_valid", True) is not False

    return JudgeEvaluation(
        judge_model=judge_model,
        judge_number=judge_number,
        score=data.get("score", np.nan),
        passed=data.get("passed", False),
        grade=data.get("grade", "F"),
        is_valid=is_valid_raw,
        reasoning=data.get("reasoning", ""),
        criteria=criteria,
    )


def load_run(  # noqa: C901  # data loading with many optional field paths
    run_dir: Path, experiment: str, tier: str, subtest: str, agent_model: str
) -> RunData:
    """Load data for a single run.

    Args:
        run_dir: Path to run directory
        experiment: Experiment name
        tier: Tier ID (T0-T6)
        subtest: Subtest ID
        agent_model: Agent model display name

    Returns:
        Complete run data

    """
    # Load run_result.json for consensus data
    run_result_path = run_dir / "run_result.json"
    with run_result_path.open() as f:
        result = json.load(f)

    # Validate against JSON Schema (graceful degradation - log warning only)
    try:
        jsonschema.validate(result, _RUN_RESULT_SCHEMA)
    except jsonschema.ValidationError as e:
        logger.warning(
            "Schema validation failed for %s: %s (path: %s)",
            run_result_path,
            e.message,
            " -> ".join(str(p) for p in e.path) if e.path else "root",
        )

    # Parse run number from directory name (e.g., "run_01" -> 1)
    try:
        run_number = int(run_dir.name.split("_")[1])
    except (IndexError, ValueError):
        # Fallback: try to extract any number from the directory name
        match = re.search(r"\d+", run_dir.name)
        run_number = int(match.group()) if match else 0

    # Load token stats
    token_stats = TokenStats.from_dict(result.get("token_stats", {}))

    # Load per-judge evaluations
    judges = []
    judge_dir = run_dir / "judge"
    if judge_dir.exists():
        # Dynamically discover all judge directories
        for judge_path in sorted(judge_dir.glob("judge_*/judgment.json")):
            # Extract judge number from directory name (e.g., "judge_01" -> 1)
            judge_num = int(judge_path.parent.name.replace("judge_", ""))
            judges.append(load_judgment(judge_path, judge_num))

    # Load optional agent result data
    agent_data = load_agent_result(run_dir)
    api_calls_val = None
    num_turns_val = None
    model_usage_val = None

    if agent_data:
        # Extract API calls and turns if present
        if "api_calls" in agent_data:
            api_calls_val = validate_int(agent_data["api_calls"], "api_calls", 0) or None
        if "num_turns" in agent_data:
            num_turns_val = validate_int(agent_data["num_turns"], "num_turns", 0) or None

        # Parse model_usage if present (for delegation tiers)
        raw_usage = agent_data.get("model_usage") or agent_data.get("modelUsage")
        if raw_usage and isinstance(raw_usage, list):
            model_usage_val = []
            for usage in raw_usage:
                if isinstance(usage, dict):
                    model_usage_val.append(
                        ModelUsage(
                            model=usage.get("model", "unknown"),
                            input_tokens=validate_int(
                                usage.get("input_tokens") or usage.get("inputTokens"),
                                "input_tokens",
                                0,
                            ),
                            output_tokens=validate_int(
                                usage.get("output_tokens") or usage.get("outputTokens"),
                                "output_tokens",
                                0,
                            ),
                            cache_creation_tokens=validate_int(
                                usage.get("cache_creation_tokens"), "cache_creation_tokens", 0
                            ),
                            cache_read_tokens=validate_int(
                                usage.get("cache_read_tokens"), "cache_read_tokens", 0
                            ),
                            cost_usd=validate_numeric(usage.get("cost_usd"), "cost_usd", 0.0),
                        )
                    )

    # Extract process metrics from run_result.json
    r_prog_val: float | None = None
    strategic_drift_val: float | None = None
    cfp_val: float | None = None
    pr_revert_rate_val: float | None = None

    process_metrics_data = result.get("process_metrics")
    if process_metrics_data and isinstance(process_metrics_data, dict):
        # Use pre-computed process_metrics block if available
        def _extract_process_float(key: str) -> float | None:
            raw = validate_numeric(process_metrics_data.get(key), key, np.nan)
            return None if (raw is None or np.isnan(raw)) else raw

        r_prog_val = _extract_process_float("r_prog")
        strategic_drift_val = _extract_process_float("strategic_drift")
        cfp_val = _extract_process_float("cfp")
        pr_revert_rate_val = _extract_process_float("pr_revert_rate")
    else:
        # Fallback: compute from raw tracking data if present
        progress_tracking = result.get("progress_tracking")
        changes = result.get("changes")
        if progress_tracking or changes:
            from scylla.metrics.process import (
                ChangeResult,
                ProgressStep,
                ProgressTracker,
                calculate_cfp,
                calculate_pr_revert_rate,
                calculate_r_prog,
                calculate_strategic_drift,
            )

            if progress_tracking and isinstance(progress_tracking, list):
                steps = []
                achieved = []
                for s in progress_tracking:
                    if isinstance(s, dict):
                        step = ProgressStep(
                            step_id=s.get("step_id", ""),
                            description=s.get("description", ""),
                            weight=float(s.get("weight", 1.0)),
                            completed=bool(s.get("completed", False)),
                            goal_alignment=float(s.get("goal_alignment", 1.0)),
                        )
                        steps.append(step)
                        if step.completed:
                            achieved.append(step)
                tracker = ProgressTracker(expected_steps=steps, achieved_steps=achieved)
                r_prog_val = calculate_r_prog(tracker)
                strategic_drift_val = calculate_strategic_drift(tracker)

            if changes and isinstance(changes, list):
                change_results = []
                for c in changes:
                    if isinstance(c, dict):
                        change_results.append(
                            ChangeResult(
                                change_id=c.get("change_id", ""),
                                description=c.get("description", ""),
                                succeeded=bool(c.get("succeeded", True)),
                                caused_failure=bool(c.get("caused_failure", False)),
                                reverted=bool(c.get("reverted", False)),
                            )
                        )
                cfp_val = calculate_cfp(change_results)
                pr_revert_rate_val = calculate_pr_revert_rate(change_results)

    # Validate and coerce all numeric/boolean fields with type checking
    return RunData(
        experiment=experiment,
        agent_model=agent_model,
        tier=tier,
        subtest=subtest,
        run_number=run_number,
        score=validate_numeric(result.get("judge_score"), "judge_score", np.nan),
        passed=validate_bool(result.get("judge_passed"), "judge_passed", False),
        grade=result.get("judge_grade", "F"),  # String, no validation needed
        cost_usd=validate_numeric(result.get("cost_usd"), "cost_usd", np.nan),
        duration_seconds=validate_numeric(
            result.get("duration_seconds"), "duration_seconds", np.nan
        ),
        agent_duration_seconds=validate_numeric(
            result.get("agent_duration_seconds"), "agent_duration_seconds", np.nan
        ),
        judge_duration_seconds=validate_numeric(
            result.get("judge_duration_seconds"), "judge_duration_seconds", np.nan
        ),
        token_stats=token_stats,
        exit_code=validate_int(result.get("exit_code"), "exit_code", -1),
        judges=judges,
        api_calls=api_calls_val,
        num_turns=num_turns_val,
        model_usage=model_usage_val,
        r_prog=r_prog_val,
        strategic_drift=strategic_drift_val,
        cfp=cfp_val,
        pr_revert_rate=pr_revert_rate_val,
    )
