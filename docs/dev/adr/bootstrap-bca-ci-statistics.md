# ADR: Bootstrap BCa Confidence Intervals for Statistical Reporting

**Date**: 2026-05-06
**Status**: Accepted
**Issue**: [#1882](https://github.com/HomericIntelligence/ProjectScylla/issues/1882)

## Context

Ablation results in ProjectScylla are reported with confidence intervals on
both summary statistics (e.g., mean pass-rate per tier) and effect sizes
(e.g., Cliff's delta between tiers). Two properties of the experimental
data make naive interval methods unsafe:

1. **Small samples.** Each subtest typically has on the order of 10 runs
   per model (`runs_per_subtest`, default in `ExperimentConfig`).
   Asymptotic / normal-theory CIs (mean ± 1.96·SE/√n) are unreliable at
   n ≈ 10.
2. **Boundary-bound binary metrics.** Pass-rate is a fraction in [0, 1].
   When the true value is near 0 or 1, symmetric Wald-style intervals
   produce nonsensical bounds (negative pass-rates or pass-rates above
   100%) and have systematic coverage error.
3. **Skewed effect-size distributions.** Cliff's delta is bounded in
   [-1, 1] and is typically skewed when one group dominates. Percentile
   bootstrap is biased on skewed estimators; basic bootstrap is biased
   in the opposite direction. Both have known coverage problems.

The published method that addresses all three concerns is the
bias-corrected and accelerated (BCa) bootstrap of Efron (1987). It
adjusts the percentile bootstrap for both bias and skewness using the
jackknife-estimated acceleration parameter, and produces transformation-
respecting intervals that stay inside the support of the statistic.

scipy ships `scipy.stats.bootstrap(..., method="BCa")` which makes this
trivially callable.

## Decision

All bootstrap confidence intervals reported by ProjectScylla use the BCa
method. There are exactly two call sites, both in
[`src/scylla/analysis/stats.py`](../../../src/scylla/analysis/stats.py):

1. `bootstrap_ci()` at line 48 — the general mean-CI used by the
   reporting pipeline. Calls `scipy.stats.bootstrap(..., method="BCa",
   random_state=config.bootstrap_random_state)` at line 94.
2. `cliffs_delta_ci()` at line 666 — effect-size CI for the Cliff's
   delta tier-pair comparisons. Same `method="BCa"` at line 720.

Defaults are centralised in
[`src/scylla/analysis/config.py:67-79`](../../../src/scylla/analysis/config.py):

- `bootstrap_resamples = 10000`
- `bootstrap_confidence = 0.95`
- `bootstrap_random_state = 42` (fixed seed for reproducibility)

Both functions degrade gracefully when BCa cannot be applied:

- n < 2 returns the point estimate as both bounds (`stats.py:77-83`,
  `stats.py:700-705`) with a warning. BCa requires at least two samples
  for the jackknife.
- Zero-variance samples return the point estimate as both bounds
  (`stats.py:86-91`). BCa fails on degenerate distributions because the
  acceleration computation divides by the standard deviation.

## Consequences

**Positive**:

- Reported CIs respect the natural support of the statistic. Pass-rate
  intervals stay in [0, 1]; Cliff's delta intervals stay in [-1, 1].
- Coverage is approximately nominal even at n ≈ 10 and even when the
  underlying statistic is skewed. This matters for the headline plots
  in the published paper, which compare tiers whose pass-rates are
  near 0 or 1 (e.g., T0 vs T6).
- Reproducibility is built in: the random state is config-driven and
  defaults to 42, so re-running `export_data.py` on the same data
  produces byte-identical CIs.
- Both call sites share a single configured implementation, so a future
  change (e.g., to studentized bootstrap or to a different `n_resamples`)
  is one PR, not two.

**Negative**:

- BCa is ~2× slower than percentile bootstrap because it requires a
  jackknife pass to estimate acceleration. At n_resamples=10000 and
  ~120 subtests this is still cheap (seconds, not minutes), but it is
  the dominant cost of `bootstrap_ci` for very small datasets.
- The graceful-degradation paths (n<2, zero variance) silently collapse
  the CI to a point. Downstream readers must understand that
  `(x, x, x)` is a sentinel for "BCa not applicable" rather than
  "estimate is exact." The functions log warnings, but the JSON
  output does not flag the case explicitly.
- BCa is implemented in scipy.stats; we depend on scipy's
  implementation correctness. The pinned scipy minimum version is
  enforced through `pyproject.toml`; downgrading is not safe.
- Reported CIs in `statistical_results.json` come from
  `bootstrap_ci`/`cliffs_delta_ci` invoked from `scripts/export_data.py`.
  CIs that appear in tables but not in `statistical_results.json` are
  the canonical confusion for paper reviewers — see MEMORY.md
  "Statistical Claim Verification Pattern."

## References

- [`src/scylla/analysis/stats.py:48-103`](../../../src/scylla/analysis/stats.py)
  — `bootstrap_ci()`.
- [`src/scylla/analysis/stats.py:666-724`](../../../src/scylla/analysis/stats.py)
  — `cliffs_delta_ci()`.
- [`src/scylla/analysis/config.py:67-79`](../../../src/scylla/analysis/config.py)
  — bootstrap defaults.
- Efron, B. (1987). "Better Bootstrap Confidence Intervals."
  *Journal of the American Statistical Association*, 82(397), 171–185.
- scipy docs: `scipy.stats.bootstrap`, `method="BCa"`.
- Related: MEMORY.md "Statistical Claim Verification Pattern" notes that
  BCa CIs in paper tables are generated from `scripts/export_data.py`
  via these two functions, not from a separate analysis path.
