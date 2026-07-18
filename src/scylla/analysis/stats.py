"""Statistical analysis functions.

Provides confidence intervals, significance tests, effect sizes,
and inter-rater reliability calculations.
"""

from __future__ import annotations

import logging

import krippendorff
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

from scylla.analysis.config import config

logger = logging.getLogger(__name__)

__all__ = [
    "benjamini_hochberg_correction",
    "bonferroni_correction",
    "bootstrap_ci",
    "cliffs_delta",
    "cliffs_delta_ci",
    "compute_consistency",
    "compute_cop",
    "compute_delegation_overhead",
    "compute_frontier_cop",
    "compute_impl_rate",
    "holm_bonferroni_correction",
    "kendall_tau",
    "krippendorff_alpha",
    "kruskal_wallis",
    "kruskal_wallis_power",
    "mann_whitney_power",
    "mann_whitney_u",
    "ols_regression",
    "pearson_correlation",
    "scheirer_ray_hare",
    "shapiro_wilk",
    "spearman_correlation",
]


def bootstrap_ci(
    data: pd.Series | np.ndarray,
    confidence: float | None = None,
    n_resamples: int | None = None,
) -> tuple[float, float, float]:
    """Compute bootstrap confidence interval.

    Uses BCa (bias-corrected and accelerated) method for better coverage
    on small samples and binary data near boundaries.

    Args:
        data: Data to bootstrap
        confidence: Confidence level (default from config: 0.95 for 95% CI)
        n_resamples: Number of bootstrap resamples (default from config: 10000)

    Returns:
        Tuple of (mean, lower_bound, upper_bound)

    """
    # Use config defaults if not specified
    if confidence is None:
        confidence = config.bootstrap_confidence
    if n_resamples is None:
        n_resamples = config.bootstrap_resamples

    data_array = np.array(data)
    mean = np.mean(data_array)

    # Guard against single-element arrays (BCa requires n >= 2)
    if len(data_array) < 2:
        logger.warning(
            f"Bootstrap CI called with sample size {len(data_array)} < 2. "
            "Returning point estimate only."
        )
        val = float(mean)
        return val, val, val

    # Guard against zero variance (BCa fails on degenerate distributions)
    if np.std(data_array) == 0:
        logger.debug(
            "Bootstrap CI called with zero variance data. Returning point estimate as CI bounds."
        )
        val = float(mean)
        return val, val, val

    # Use scipy's bootstrap with BCa method for better coverage
    res = stats.bootstrap(
        (data_array,),
        np.mean,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="BCa",
        random_state=config.bootstrap_random_state,
    )

    return mean, res.confidence_interval.low, res.confidence_interval.high


def mann_whitney_u(
    group1: pd.Series | np.ndarray, group2: pd.Series | np.ndarray
) -> tuple[float, float]:
    """Perform Mann-Whitney U test (non-parametric).

    Args:
        group1: First group
        group2: Second group

    Returns:
        Tuple of (U statistic, p-value)

    """
    g1 = np.array(group1)
    g2 = np.array(group2)

    # Guard against degenerate input (n < 2 per group)
    if len(g1) < 2 or len(g2) < 2:
        logger.warning(
            f"Mann-Whitney U test called with sample sizes {len(g1)}, {len(g2)}. "
            "Need at least 2 samples per group. Returning U=0, p=1.0."
        )
        return 0.0, 1.0

    # Guard against fully-tied input (every observation across both groups is
    # identical). The two samples are drawn from the same degenerate
    # distribution, so there is no location shift to detect. SciPy >= 1.18
    # returns p=nan here (undefined normal approximation with zero rank
    # variance); older versions returned a valid p. Treat identical
    # distributions as "not significant" (p=1.0), consistent with the n<2 and
    # ValueError guards below.
    combined = np.concatenate([g1, g2])
    if np.all(combined == combined[0]):
        logger.warning(
            "Mann-Whitney U test called with fully-tied input (all values "
            "identical across both groups). No location shift to test; "
            "returning U=0, p=1.0."
        )
        return 0.0, 1.0

    try:
        statistic, pvalue = stats.mannwhitneyu(g1, g2, alternative="two-sided")
        return float(statistic), float(pvalue)
    except ValueError as e:
        # Additional guard for unexpected scipy errors
        logger.error(
            f"Mann-Whitney U test failed with ValueError: {e}. "
            f"Sample sizes: {len(g1)}, {len(g2)}. Returning U=0, p=1.0."
        )
        return 0.0, 1.0


def mann_whitney_power(
    n1: int,
    n2: int,
    effect_size: float,
    alpha: float | None = None,
    n_simulations: int | None = None,
) -> float:
    """Compute post-hoc power for Mann-Whitney U test via simulation.

    Generates data under the alternative hypothesis using the observed
    Cliff's delta as effect size, then computes the proportion of
    significant test results.

    Args:
        n1: Sample size of group 1
        n2: Sample size of group 2
        effect_size: Cliff's delta (observed effect size in [-1, 1])
        alpha: Significance level (default from config: 0.05)
        n_simulations: Number of simulation iterations (default: 10000)

    Returns:
        Achieved power in [0, 1]

    """
    if alpha is None:
        alpha = config.alpha
    if n_simulations is None:
        n_simulations = config.power_n_simulations

    # Handle edge cases
    if n1 < 2 or n2 < 2:
        return np.nan
    if abs(effect_size) < 1e-10:  # Zero effect
        return alpha  # Power equals Type I error rate

    # Convert Cliff's delta to normal distribution shift
    # d = 2 * Phi(shift/sqrt(2)) - 1, so shift = sqrt(2) * Phi^(-1)((d + 1) / 2)
    from scipy.stats import norm

    shift = np.sqrt(2) * norm.ppf((effect_size + 1) / 2)

    # Run simulations
    rng = np.random.RandomState(config.power_random_state)
    significant_count = 0

    for _ in range(n_simulations):
        # Generate data under alternative hypothesis
        group1_sim = rng.normal(0, 1, n1)
        group2_sim = rng.normal(shift, 1, n2)

        # Run Mann-Whitney U test
        _, p_value = mann_whitney_u(group1_sim, group2_sim)

        if p_value < alpha:
            significant_count += 1

    return significant_count / n_simulations


def kruskal_wallis_power(
    group_sizes: list[int],
    effect_size: float,
    alpha: float | None = None,
    n_simulations: int | None = None,
) -> float:
    """Compute post-hoc power for Kruskal-Wallis H test via simulation.

    Generates data under the alternative hypothesis using the observed
    effect size (epsilon-squared), then computes the proportion of
    significant test results.

    Args:
        group_sizes: List of sample sizes for each group
        effect_size: Epsilon-squared effect size (H / (N-1))
        alpha: Significance level (default from config: 0.05)
        n_simulations: Number of simulation iterations (default: 10000)

    Returns:
        Achieved power in [0, 1]

    """
    if alpha is None:
        alpha = config.alpha
    if n_simulations is None:
        n_simulations = config.power_n_simulations

    # Handle edge cases
    if len(group_sizes) < 2 or any(n < 2 for n in group_sizes):
        return np.nan
    if abs(effect_size) < 1e-10:  # Zero effect
        return alpha  # Power equals Type I error rate

    # Distribute effect across groups using simple shift model
    # Each group gets a shift proportional to its expected rank deviation
    k = len(group_sizes)
    shifts = np.linspace(-1, 1, k) * np.sqrt(effect_size) * 2

    # Run simulations
    rng = np.random.RandomState(config.power_random_state)
    significant_count = 0

    for _ in range(n_simulations):
        # Generate data for each group with different shifts
        groups = [rng.normal(shift, 1, n) for shift, n in zip(shifts, group_sizes, strict=False)]

        # Run Kruskal-Wallis test
        _, p_value = kruskal_wallis(*groups)

        if p_value < alpha:
            significant_count += 1

    return significant_count / n_simulations


def cliffs_delta(group1: pd.Series | np.ndarray, group2: pd.Series | np.ndarray) -> float:
    """Compute Cliff's delta effect size (non-parametric).

    Uses vectorized numpy operations for performance (~50x faster than loops).

    Interpretation (Romano et al., 2006, FAIR conference thresholds):
        |δ| < 0.11: negligible
        |δ| < 0.28: small
        |δ| < 0.43: medium
        |δ| >= 0.43: large

    Note: These thresholds differ from the standard Romano et al. (2006) thresholds
    sometimes cited in the literature (0.147/0.33/0.474). The thresholds used here
    are from the original FAIR conference paper. Effects near the 0.43 boundary
    should be interpreted as borderline medium/large.

    Reference:
        Romano, J., Kromrey, J. D., Coraggio, J., & Skowronek, J. (2006).
        Appropriate statistics for ordinal level data: Should we really be using
        t-test and Cohen's d for evaluating group differences on the NSSE and
        other surveys? Annual meeting of the Florida Association of Institutional Research.

    Args:
        group1: First group
        group2: Second group

    Returns:
        Cliff's delta in range [-1, 1]

    """
    g1 = np.array(group1)
    g2 = np.array(group2)

    n1, n2 = len(g1), len(g2)
    if n1 == 0 or n2 == 0:
        return np.nan

    # Vectorized comparison: g1[:, None] broadcasts to (n1, n2)
    # g2[None, :] broadcasts to (n1, n2)
    # np.sign gives -1, 0, or 1 for each comparison
    delta = np.sign(g1[:, None] - g2[None, :]).sum() / (n1 * n2)
    return float(delta)


def spearman_correlation(
    x: pd.Series | np.ndarray, y: pd.Series | np.ndarray
) -> tuple[float, float]:
    """Compute Spearman rank correlation.

    Args:
        x: First variable
        y: Second variable

    Returns:
        Tuple of (correlation, p-value)

    """
    corr, pvalue = stats.spearmanr(x, y)
    return float(corr), float(pvalue)


def kendall_tau(x: pd.Series | np.ndarray, y: pd.Series | np.ndarray) -> tuple[float, float]:
    """Compute Kendall's tau rank correlation.

    Measures ordinal association between two rankings. Useful for assessing
    tier rank stability across experiments (e.g., do tier rankings agree?).

    Args:
        x: First ranking variable
        y: Second ranking variable

    Returns:
        Tuple of (tau, p-value)

    """
    x_arr = np.array(x)
    y_arr = np.array(y)

    if len(x_arr) < 2 or len(y_arr) < 2:
        logger.warning(
            f"Kendall's tau called with sample sizes {len(x_arr)}, {len(y_arr)}. "
            "Need at least 2 samples. Returning tau=0, p=1.0."
        )
        return 0.0, 1.0

    tau, pvalue = stats.kendalltau(x_arr, y_arr)
    return float(tau), float(pvalue)


def pearson_correlation(
    x: pd.Series | np.ndarray, y: pd.Series | np.ndarray
) -> tuple[float, float]:
    """Compute Pearson correlation.

    Args:
        x: First variable
        y: Second variable

    Returns:
        Tuple of (correlation, p-value)

    """
    corr, pvalue = stats.pearsonr(x, y)
    return float(corr), float(pvalue)


def krippendorff_alpha(ratings: np.ndarray, level: str = "ordinal") -> float:
    """Compute Krippendorff's alpha for inter-rater reliability.

    Wrapper around the krippendorff package for correct implementation.

    Args:
        ratings: 2D array of shape (n_judges, n_items)
        level: Measurement level ("nominal", "ordinal", "interval", "ratio")

    Returns:
        Krippendorff's alpha in range [-1, 1]

    """
    # Convert to numpy array
    ratings = np.array(ratings)

    # The krippendorff package expects (n_units, n_coders) format
    # Our input is already (n_judges, n_items) which matches (n_coders, n_units)
    # No transpose needed
    reliability_data = ratings

    # Call the krippendorff package
    return float(krippendorff.alpha(reliability_data=reliability_data, level_of_measurement=level))


def bonferroni_correction(p_value: float, n_tests: int) -> float:
    """Apply Bonferroni correction for multiple comparisons.

    Adjusts p-value by multiplying by the number of independent tests.
    This controls the family-wise error rate (FWER) at the significance level.

    Args:
        p_value: Original p-value from single test
        n_tests: Number of independent hypothesis tests performed

    Returns:
        Bonferroni-corrected p-value, clamped to [0, 1]

    Example:
        >>> # 6 independent tests at α=0.05 individual level
        >>> # FWER = 1 - (1-0.05)^6 ≈ 0.26 (26% chance of Type I error)
        >>> # Bonferroni corrects to α_adj = 0.05/6 ≈ 0.0083
        >>> bonferroni_correction(0.04, 6)  # Original p=0.04 < 0.05
        0.24  # Adjusted p=0.24 > 0.05, not significant after correction

    """
    return min(1.0, p_value * n_tests)


def compute_consistency(mean: float, std: float) -> float:
    """Compute consistency metric: 1 - coefficient of variation.

    Consistency measures how stable scores are relative to their mean.
    Higher values indicate more consistent (less variable) performance.

    Args:
        mean: Mean of the data
        std: Standard deviation of the data

    Returns:
        Consistency value in [0, 1], where 1 = perfect consistency

    """
    if mean == 0:
        return 0.0
    consistency = 1 - (std / mean)
    return max(0.0, min(1.0, consistency))  # Clamp to [0, 1]


def compute_cop(mean_cost: float, pass_rate: float) -> float:
    """Compute Cost-of-Pass (CoP) metric.

    CoP represents the expected cost to achieve one successful outcome.
    Lower values indicate better cost efficiency.

    Args:
        mean_cost: Mean cost per attempt (USD)
        pass_rate: Success rate in [0, 1]

    Returns:
        CoP in USD, or inf if pass_rate is 0

    """
    if pass_rate == 0:
        return float("inf")
    return mean_cost / pass_rate


def compute_delegation_overhead(delegated_cost: float, base_cost: float) -> float:
    """Compute delegation overhead as percentage increase over base cost.

    Measures the cost increase when using delegation (T3-T5) compared to
    non-delegation tiers (T0-T2).

    Args:
        delegated_cost: Total cost with delegation (T3-T5)
        base_cost: Baseline cost without delegation (T0-T2)

    Returns:
        Overhead as ratio (0.5 = 50% overhead), or inf if base_cost is 0

    """
    if base_cost == 0:
        return float("inf")
    return (delegated_cost - base_cost) / base_cost


def compute_frontier_cop(cop_values: list[float]) -> float:
    """Compute Frontier CoP - minimum CoP across all configurations.

    The Frontier CoP represents the most cost-efficient configuration,
    establishing the efficiency frontier. Configurations above this frontier
    are dominated (higher cost for same or worse performance).

    Args:
        cop_values: List of CoP values from different configurations/tiers

    Returns:
        Minimum CoP (best cost efficiency), or inf if all values are inf

    Example:
        >>> cops = [2.50, 1.75, 3.20, 2.10]
        >>> compute_frontier_cop(cops)
        1.75

    """
    # Filter out inf values for comparison
    finite_cops = [c for c in cop_values if c != float("inf")]

    if not finite_cops:
        return float("inf")

    return min(finite_cops)


def compute_impl_rate(achieved_points: float, max_points: float) -> float:
    """Compute Implementation Rate (Impl-Rate) metric.

    Impl-Rate measures the proportion of semantic requirements satisfied,
    providing more granular feedback than binary pass/fail. It aggregates
    points achieved across all rubric criteria.

    Args:
        achieved_points: Total points achieved across all criteria
        max_points: Total maximum possible points across all criteria

    Returns:
        Implementation rate in [0, 1], or NaN if max_points is 0

    Examples:
        >>> compute_impl_rate(8.5, 10.0)
        0.85
        >>> compute_impl_rate(0.0, 10.0)
        0.0
        >>> import numpy as np
        >>> np.isnan(compute_impl_rate(0.0, 0.0))
        True

    """
    if max_points == 0:
        return np.nan
    return achieved_points / max_points


def shapiro_wilk(data: pd.Series | np.ndarray) -> tuple[float, float]:
    """Perform Shapiro-Wilk normality test.

    Tests the null hypothesis that the data was drawn from a normal distribution.
    Used to justify choice of parametric vs non-parametric tests.

    Args:
        data: Sample data to test for normality

    Returns:
        Tuple of (W statistic, p-value)
        - W close to 1 suggests normality
        - p > 0.05 means cannot reject normality (at α=0.05)

    """
    data_array = np.array(data)

    # Guard against insufficient sample size
    if len(data_array) < config.min_sample_normality:
        logger.warning(
            f"Shapiro-Wilk test requires n >= {config.min_sample_normality}, "
            f"got n={len(data_array)}. Returning NaN."
        )
        return np.nan, np.nan

    statistic, pvalue = stats.shapiro(data_array)
    return float(statistic), float(pvalue)


def kruskal_wallis(*groups: pd.Series | np.ndarray) -> tuple[float, float]:
    """Perform Kruskal-Wallis H test (non-parametric one-way ANOVA).

    Omnibus test for whether samples originate from the same distribution.
    Should be performed before pairwise comparisons to control FWER.

    Args:
        *groups: Variable number of sample groups to compare

    Returns:
        Tuple of (H statistic, p-value)
        - H = 0 when all groups have identical rank sums
        - p < 0.05 indicates at least one group differs (justifies pairwise tests)
        - Returns (NaN, NaN) if any group has fewer than min_sample_kruskal_wallis samples

    """
    # Defensive guard: ensure minimum sample size
    groups_arrays = [np.array(g) for g in groups]
    min_samples = config.min_sample_kruskal_wallis

    if any(len(g) < min_samples for g in groups_arrays):
        return (np.nan, np.nan)

    statistic, pvalue = stats.kruskal(*groups_arrays)
    return float(statistic), float(pvalue)


def holm_bonferroni_correction(p_values: list[float]) -> list[float]:
    """Apply Holm-Bonferroni step-down correction for multiple comparisons.

    Less conservative than standard Bonferroni while still controlling FWER.
    Sorts p-values and applies decreasing correction factors.

    Args:
        p_values: List of p-values from multiple tests

    Returns:
        List of corrected p-values in original order

    Example:
        >>> p_vals = [0.01, 0.04, 0.03, 0.50]
        >>> holm_bonferroni_correction(p_vals)
        [0.04, 0.09, 0.09, 0.50]  # More power than Bonferroni

    """
    n = len(p_values)
    if n == 0:
        return []

    # Create (index, p_value) pairs and sort by p_value
    indexed = list(enumerate(p_values))
    indexed.sort(key=lambda x: x[1])

    # Apply step-down correction
    corrected = [0.0] * n
    for rank, (original_idx, p_val) in enumerate(indexed):
        # Correction factor decreases from n to 1
        corrected[original_idx] = min(1.0, p_val * (n - rank))

    # Enforce monotonicity: corrected p-values must be non-decreasing in sorted order
    for i in range(1, n):
        curr_idx = indexed[i][0]
        prev_idx = indexed[i - 1][0]
        corrected[curr_idx] = max(corrected[curr_idx], corrected[prev_idx])

    return corrected


def benjamini_hochberg_correction(p_values: list[float]) -> list[float]:
    """Apply Benjamini-Hochberg FDR correction for multiple comparisons.

    Controls False Discovery Rate instead of FWER. More powerful than
    Bonferroni/Holm when many tests are performed.

    Args:
        p_values: List of p-values from multiple tests

    Returns:
        List of corrected p-values (q-values) in original order

    Example:
        >>> p_vals = [0.01, 0.04, 0.03, 0.50]
        >>> benjamini_hochberg_correction(p_vals)
        [0.04, 0.053, 0.053, 0.50]  # FDR control, not FWER

    """
    n = len(p_values)
    if n == 0:
        return []

    # Create (index, p_value) pairs and sort by p_value
    indexed = list(enumerate(p_values))
    indexed.sort(key=lambda x: x[1])

    # Apply step-up correction (reverse order from Holm)
    corrected = [0.0] * n
    for rank, (original_idx, p_val) in enumerate(indexed):
        # Correction factor: (n / rank+1) where rank is 0-indexed
        corrected[original_idx] = min(1.0, p_val * n / (rank + 1))

    # Enforce monotonicity: corrected p-values in sorted order must be
    # non-decreasing. Work backwards to ensure each value is no larger
    # than the one after it in the sorted sequence.
    for i in range(n - 2, -1, -1):
        curr_idx = indexed[i][0]
        next_idx = indexed[i + 1][0]
        corrected[curr_idx] = min(corrected[curr_idx], corrected[next_idx])

    return corrected


def cliffs_delta_ci(
    group1: pd.Series | np.ndarray,
    group2: pd.Series | np.ndarray,
    confidence: float | None = None,
    n_resamples: int | None = None,
) -> tuple[float, float, float]:
    """Compute Cliff's delta with bootstrap confidence interval.

    Provides effect size estimate with uncertainty quantification via
    BCa bootstrap. Complements the point estimate from cliffs_delta().

    Args:
        group1: First group
        group2: Second group
        confidence: Confidence level (default from config: 0.95)
        n_resamples: Number of bootstrap resamples (default from config: 10000)

    Returns:
        Tuple of (delta, ci_low, ci_high)

    """
    # Use config defaults if not specified
    if confidence is None:
        confidence = config.bootstrap_confidence
    if n_resamples is None:
        n_resamples = config.bootstrap_resamples

    # Compute point estimate using existing function
    delta = cliffs_delta(group1, group2)

    g1 = np.array(group1)
    g2 = np.array(group2)

    # Guard against insufficient data
    if len(g1) < 2 or len(g2) < 2:
        logger.warning(
            f"Cliff's delta CI called with sample sizes {len(g1)}, {len(g2)}. "
            "Returning point estimate only."
        )
        return delta, delta, delta

    # Bootstrap the delta calculation
    def delta_statistic(g1_sample: np.ndarray, g2_sample: np.ndarray) -> float:
        n1, n2 = len(g1_sample), len(g2_sample)
        if n1 == 0 or n2 == 0:
            return 0.0
        return float(np.sign(g1_sample[:, None] - g2_sample[None, :]).sum() / (n1 * n2))

    # Use scipy's bootstrap
    res = stats.bootstrap(
        (g1, g2),
        delta_statistic,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="BCa",
        random_state=config.bootstrap_random_state,
    )

    return delta, res.confidence_interval.low, res.confidence_interval.high


def ols_regression(x: pd.Series | np.ndarray, y: pd.Series | np.ndarray) -> dict[str, float]:
    """Perform Ordinary Least Squares regression.

    Fits y = slope * x + intercept using OLS and returns diagnostics.

    Args:
        x: Independent variable
        y: Dependent variable

    Returns:
        Dictionary with keys:
            - slope: Regression coefficient
            - intercept: Y-intercept
            - r_squared: Coefficient of determination
            - p_value: P-value for slope significance
            - std_err: Standard error of slope estimate

    """
    x_array = np.array(x)
    y_array = np.array(y)

    # Add constant term for intercept
    x_with_const = add_constant(x_array)

    # Fit OLS model
    model = OLS(y_array, x_with_const).fit()

    return {
        "slope": float(model.params[1]),
        "intercept": float(model.params[0]),
        "r_squared": float(model.rsquared),
        "p_value": float(model.pvalues[1]),
        "std_err": float(model.bse[1]),
    }


def scheirer_ray_hare(
    data: pd.DataFrame,
    value_col: str,
    factor_a_col: str,
    factor_b_col: str,
) -> dict[str, dict[str, float]]:
    """Scheirer-Ray-Hare test (non-parametric two-way ANOVA).

    Tests for main effects and interaction between two factors using ranks.
    This is a non-parametric alternative to two-way ANOVA that does not assume
    normality or homoscedasticity.

    Algorithm:
        1. Rank all observations across the entire dataset
        2. Compute sum of squares for ranks using two-way ANOVA formulas
        3. Test each effect against chi-squared distribution

    Args:
        data: DataFrame containing the data
        value_col: Name of the dependent variable column
        factor_a_col: Name of the first factor column
        factor_b_col: Name of the second factor column

    Returns:
        Dictionary with keys 'factor_a', 'factor_b', and 'interaction', each containing:
            - h_statistic: H-statistic (similar to chi-squared)
            - df: Degrees of freedom
            - p_value: P-value from chi-squared distribution

    Example:
        >>> df = pd.DataFrame({
        ...     'score': [0.8, 0.9, 0.6, 0.7, 0.85, 0.95],
        ...     'model': ['A', 'A', 'B', 'B', 'A', 'B'],
        ...     'tier': ['T0', 'T1', 'T0', 'T1', 'T2', 'T2']
        ... })
        >>> results = scheirer_ray_hare(df, 'score', 'model', 'tier')
        >>> results['model']['p_value']  # Main effect of model
        >>> results['interaction']['p_value']  # Model x Tier interaction

    """
    # Rank all observations across entire dataset
    ranks = data[value_col].rank()

    # Get factor levels
    levels_a = data[factor_a_col].unique()
    levels_b = data[factor_b_col].unique()

    # Total number of observations
    n = len(data)

    # Degrees of freedom
    a = len(levels_a)  # Number of levels in factor A
    b = len(levels_b)  # Number of levels in factor B
    df_a = a - 1
    df_b = b - 1
    df_ab = (a - 1) * (b - 1)

    # Compute mean rank (for centering)
    mean_rank = ranks.mean()

    # Compute sum of squared deviations of ranks from mean (MS_total denominator)
    ss_total = ((ranks - mean_rank) ** 2).sum()

    # Compute SS for factor A (main effect)
    ss_a = 0.0
    for level in levels_a:
        mask = data[factor_a_col] == level
        n_i = mask.sum()
        mean_rank_i = ranks[mask].mean()
        ss_a += n_i * (mean_rank_i - mean_rank) ** 2

    # Compute SS for factor B (main effect)
    ss_b = 0.0
    for level in levels_b:
        mask = data[factor_b_col] == level
        n_j = mask.sum()
        mean_rank_j = ranks[mask].mean()
        ss_b += n_j * (mean_rank_j - mean_rank) ** 2

    # Compute SS for cells (A x B)
    ss_cells = 0.0
    for level_a in levels_a:
        for level_b in levels_b:
            mask = (data[factor_a_col] == level_a) & (data[factor_b_col] == level_b)
            n_ij = mask.sum()
            if n_ij > 0:
                mean_rank_ij = ranks[mask].mean()
                ss_cells += n_ij * (mean_rank_ij - mean_rank) ** 2

    # Compute SS for interaction (what's left after removing main effects)
    ss_ab = ss_cells - ss_a - ss_b

    # Compute MS_total (variance of ranks)
    ms_total = ss_total / (n - 1)

    # Compute H-statistics (analogous to F-statistics in parametric ANOVA)
    # H = SS / MS_total follows chi-squared distribution under null
    h_a = ss_a / ms_total
    h_b = ss_b / ms_total
    h_ab = ss_ab / ms_total

    # Compute p-values from chi-squared distribution
    p_a = 1 - stats.chi2.cdf(h_a, df_a)
    p_b = 1 - stats.chi2.cdf(h_b, df_b)
    p_ab = 1 - stats.chi2.cdf(h_ab, df_ab)

    return {
        factor_a_col: {
            "h_statistic": float(h_a),
            "df": int(df_a),
            "p_value": float(p_a),
        },
        factor_b_col: {
            "h_statistic": float(h_b),
            "df": int(df_b),
            "p_value": float(p_b),
        },
        "interaction": {
            "h_statistic": float(h_ab),
            "df": int(df_ab),
            "p_value": float(p_ab),
        },
    }
