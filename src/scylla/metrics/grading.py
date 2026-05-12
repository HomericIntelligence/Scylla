"""Grading calculations for evaluation metrics.

This module provides grading functions for calculating pass rate,
implementation rate, cost of pass, and composite scores.
"""

from __future__ import annotations

from dataclasses import dataclass

# Re-exported from scylla.core.thresholds to preserve the public symbol
# ``scylla.metrics.grading.DEFAULT_PASS_THRESHOLD`` for any external callers.
# The canonical home is now ``scylla.core.thresholds`` so that ``config``
# does not have to import from ``metrics`` (issue #1937, edge 1 of 3).
# See docs/design/grading-scale.md for specification.
from scylla.core.thresholds import DEFAULT_PASS_THRESHOLD as DEFAULT_PASS_THRESHOLD


@dataclass
class GradingResult:
    """Result of grading calculations.

    Attributes:
        pass_rate: Binary pass/fail as 1.0 or 0.0.
        impl_rate: Implementation rate from judgment.
        cost_of_pass: Cost per successful run.
        composite_score: Combined score from metrics.
        letter_grade: Letter grade (A/B/C/D/F).

    """

    pass_rate: float
    impl_rate: float
    cost_of_pass: float
    composite_score: float
    letter_grade: str


def calculate_pass_rate(passed: bool) -> float:
    """Calculate pass rate from boolean result.

    Args:
        passed: Whether the evaluation passed.

    Returns:
        1.0 if passed, 0.0 if failed.

    """
    return 1.0 if passed else 0.0


def calculate_impl_rate(weighted_score: float) -> float:
    """Calculate implementation rate from weighted score.

    Args:
        weighted_score: Weighted score from judgment (0.0 to 1.0).

    Returns:
        Implementation rate (clamped to 0.0-1.0).

    """
    return max(0.0, min(1.0, weighted_score))


def calculate_cost_of_pass(cost: float, pass_rate: float) -> float:
    """Calculate cost per successful run.

    If pass_rate is 0, returns infinity to indicate
    infinitely expensive failures.

    Args:
        cost: Total cost in USD.
        pass_rate: Pass rate (0.0 to 1.0).

    Returns:
        Cost per pass, or infinity if pass_rate is 0.

    """
    if pass_rate <= 0:
        return float("inf")

    return cost / pass_rate


def calculate_composite_score(
    pass_rate: float,
    impl_rate: float,
    pass_weight: float = 0.5,
    impl_weight: float = 0.5,
) -> float:
    """Calculate composite score from metrics.

    By default, uses simple average of pass_rate and impl_rate.
    Custom weights can adjust the relative importance.

    Args:
        pass_rate: Pass rate (0.0 to 1.0).
        impl_rate: Implementation rate (0.0 to 1.0).
        pass_weight: Weight for pass_rate (default 0.5).
        impl_weight: Weight for impl_rate (default 0.5).

    Returns:
        Weighted composite score (0.0 to 1.0).

    """
    total_weight = pass_weight + impl_weight
    if total_weight <= 0:
        return 0.0

    weighted_sum = (pass_rate * pass_weight) + (impl_rate * impl_weight)
    return weighted_sum / total_weight


def assign_letter_grade(score: float) -> str:
    """Assign letter grade based on score using industry-aligned scale.

    See docs/design/grading-scale.md for full specification.

    Grade thresholds:
        S: == 1.00 (Amazing - exceptional, above and beyond)
        A: >= 0.80 (Excellent - production ready)
        B: >= 0.60 (Good - minor improvements possible)
        C: >= 0.40 (Acceptable - functional with issues)
        D: >= 0.20 (Marginal - significant issues)
        F: < 0.20 (Failing - does not meet requirements)

    Args:
        score: Score (0.0 to 1.0).

    Returns:
        Letter grade (S/A/B/C/D/F).

    """
    if not (0.0 <= score <= 1.0):
        raise ValueError(f"score must be in [0.0, 1.0], got {score}")

    if score == 1.0:
        return "S"
    elif score >= 0.80:
        return "A"
    elif score >= 0.60:
        return "B"
    elif score >= 0.40:
        return "C"
    elif score >= 0.20:
        return "D"
    else:
        return "F"


def calculate_tier_uplift(
    tier_score: float,
    baseline_score: float,
) -> float:
    """Calculate tier uplift vs baseline (T0).

    Formula: (tier_score - baseline) / baseline

    Args:
        tier_score: Score for the tier being evaluated.
        baseline_score: Baseline score (typically T0).

    Returns:
        Percentage uplift (can be negative for regression).
        Returns 0.0 if baseline is 0.

    """
    if baseline_score <= 0:
        return 0.0

    return (tier_score - baseline_score) / baseline_score


def calculate_cost_delta(costs: list[float]) -> float:
    """Calculate cost delta between tiers.

    Formula: max(costs) - min(costs)

    Args:
        costs: List of costs across tiers.

    Returns:
        Cost delta, or 0.0 if empty.

    """
    if not costs:
        return 0.0

    return max(costs) - min(costs)


def grade_run(
    passed: bool,
    weighted_score: float,
    cost_usd: float,
) -> GradingResult:
    """Grade a single evaluation run.

    Args:
        passed: Whether the evaluation passed.
        weighted_score: Weighted score from judgment.
        cost_usd: Cost of the run in USD.

    Returns:
        GradingResult with all calculated metrics.

    """
    pass_rate = calculate_pass_rate(passed)
    impl_rate = calculate_impl_rate(weighted_score)
    cost_of_pass = calculate_cost_of_pass(cost_usd, pass_rate)
    composite = calculate_composite_score(pass_rate, impl_rate)
    grade = assign_letter_grade(composite)

    return GradingResult(
        pass_rate=pass_rate,
        impl_rate=impl_rate,
        cost_of_pass=cost_of_pass,
        composite_score=composite,
        letter_grade=grade,
    )
