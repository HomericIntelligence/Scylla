"""Dataclasses and rubric conflict types used by the analysis loader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scylla.e2e.models import TokenStats

# Rubric conflict resolution policy.
# 'error'  – raise RubricConflictError (default; safest for research pipelines)
# 'warn'   – emit UserWarning and keep the *first* value
# 'first'  – silently keep the first value encountered
# 'last'   – silently overwrite with the last value encountered
RubricConflict = Literal["error", "warn", "first", "last"]


class RubricConflictError(ValueError):
    """Raised when two experiments define conflicting rubric weights for the same category.

    Attributes:
        category: Category name where the conflict was detected.
        exp_first: Experiment name that first defined this category.
        weight_first: Weight from the first experiment.
        exp_second: Experiment name that introduced the conflict.
        weight_second: Conflicting weight from the second experiment.

    """

    def __init__(
        self,
        category: str,
        exp_first: str,
        weight_first: float,
        exp_second: str,
        weight_second: float,
    ) -> None:
        """Initialize RubricConflictError with conflict details."""
        self.category = category
        self.exp_first = exp_first
        self.weight_first = weight_first
        self.exp_second = exp_second
        self.weight_second = weight_second
        super().__init__(
            f"Rubric conflict for category '{category}': "
            f"experiment '{exp_first}' defines weight={weight_first}, "
            f"but experiment '{exp_second}' defines weight={weight_second}. "
            "Use the rubric_conflict parameter to control resolution."
        )


@dataclass
class CriterionScore:
    """Detailed score for a single rubric criterion.

    Attributes:
        name: Criterion name (functional, code_quality, etc.)
        achieved: Points achieved
        max_points: Maximum possible points
        score: Normalized score (0.0-1.0)
        items: Individual check items within this criterion

    """

    name: str
    achieved: float
    max_points: float
    score: float
    items: dict[str, ItemScore]


@dataclass
class ItemScore:
    """Score for an individual rubric check item.

    Attributes:
        item_id: Item identifier (e.g., "F1", "Q2")
        achieved: Points achieved (or "N/A")
        max_points: Maximum possible points (or "N/A")
        reason: Judge's reasoning for the score

    """

    item_id: str
    achieved: float | str
    max_points: float | str
    reason: str


@dataclass
class JudgeEvaluation:
    """A single judge's evaluation of a run.

    Attributes:
        judge_model: Model ID of the judge (e.g., "claude-opus-4-6")
        judge_number: Judge number (1, 2, or 3)
        score: Overall score (0.0-1.0)
        passed: Whether the run passed
        grade: Letter grade (S/A/B/C/D/F)
        is_valid: Whether the judgment was valid
        reasoning: Judge's overall reasoning
        criteria: Detailed scores by criterion

    """

    judge_model: str
    judge_number: int
    score: float
    passed: bool
    grade: str
    is_valid: bool
    reasoning: str
    criteria: dict[str, CriterionScore]


@dataclass
class ModelUsage:
    """Per-model token usage from agent execution.

    Tracks individual model usage when multiple models are involved
    (relevant for T3-T5 delegation tiers).

    Attributes:
        model: Model identifier
        input_tokens: Input tokens consumed
        output_tokens: Output tokens generated
        cache_creation_tokens: Cache creation tokens
        cache_read_tokens: Cache read tokens
        cost_usd: Cost for this model's usage

    """

    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class RunData:
    """Complete data for a single run.

    Attributes:
        experiment: Experiment identifier
        agent_model: Model used for agent (claude-sonnet-4-6, claude-haiku-4-5)
        tier: Tier ID (T0-T6)
        subtest: Subtest ID
        run_number: Run number (1-10)
        score: Consensus judge score (arithmetic mean of judges)
        passed: Consensus pass decision (majority vote)
        grade: Consensus grade
        cost_usd: Total cost in USD
        duration_seconds: Total duration
        agent_duration_seconds: Agent execution time
        judge_duration_seconds: Judge evaluation time
        token_stats: Detailed token usage
        exit_code: Agent exit code
        judges: Per-judge evaluations
        api_calls: Number of API calls (optional, for delegation tiers)
        num_turns: Number of agentic turns (optional, for delegation tiers)
        model_usage: Per-model token usage (optional, for delegation tiers)
        r_prog: Fine-Grained Progress Rate, 0.0-1.0 (optional, from process_metrics)
        strategic_drift: Strategic Drift score, 0.0-1.0 (optional, from process_metrics)
        cfp: Change Fail Percentage, 0.0-1.0 (optional, from process_metrics)
        pr_revert_rate: PR Revert Rate, 0.0-1.0 (optional, from process_metrics)

    """

    experiment: str
    agent_model: str
    tier: str
    subtest: str
    run_number: int
    score: float
    passed: bool
    grade: str
    cost_usd: float
    duration_seconds: float
    agent_duration_seconds: float
    judge_duration_seconds: float
    token_stats: TokenStats
    exit_code: int
    judges: list[JudgeEvaluation]
    # Optional agent result fields (from agent/result.json)
    api_calls: int | None = None
    num_turns: int | None = None
    model_usage: list[ModelUsage] | None = None
    # Optional process metrics (from run_result.json process_metrics block)
    r_prog: float | None = None
    strategic_drift: float | None = None
    cfp: float | None = None
    pr_revert_rate: float | None = None
