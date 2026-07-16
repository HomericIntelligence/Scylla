# Fig 16a: Success Variance Per Subtest

## Overview

Two-panel heatmap showing per-subtest variance metrics, grouped by tier and faceted by agent model. This figure reveals which subtests exhibit high variability in outcomes, helping identify unstable evaluation points.

## Purpose

- **Identify high-variance subtests** where outcomes are inconsistent across runs
- **Compare variance patterns** between binary pass/fail and continuous scoring
- **Detect stability differences** across tiers and agent models
- **Guide evaluation protocol refinement** by highlighting unreliable subtests

## Visual Design

### Panel A: Pass/Fail Variance (Bernoulli)

- **Chart Type**: Heatmap with faceting by agent model (rows)
- **X-axis**: Tier (categorical, ordered: T0, T1, T2, T3, T4, T5, T6)
- **Y-axis**: Subtest (categorical, ascending sort)
- **Color**: Pass variance using viridis scheme
  - **Domain**: [0, 0.25]
  - **Formula**: `p * (1 - p)` where p = pass_rate
  - **Interpretation**: Maximum variance (0.25) occurs at p=0.5 (50% pass rate)
- **Dimensions**: 400px width × 600px height per facet

### Panel B: Score Standard Deviation

- **Chart Type**: Heatmap with faceting by agent model (rows)
- **X-axis**: Tier (categorical, ordered: T0, T1, T2, T3, T4, T5, T6)
- **Y-axis**: Subtest (categorical, ascending sort)
- **Color**: Score standard deviation using plasma scheme
  - **Domain**: [0, dynamic max] where max = max(0.3, data_max * 1.1) rounded to 0.05
  - **Formula**: Standard deviation of continuous scores across runs
- **Dimensions**: 400px width × 600px height per facet

### Layout

- **Arrangement**: Horizontal concatenation (Panel A | Panel B)
- **Faceting**: Each panel faceted by `agent_model` (rows)
- **Scale Resolution**: Independent Y-axis per facet (`resolve_scale(y="independent")`)

## Data Requirements

### Input Schema

Requires `runs_df` DataFrame with columns:

- `agent_model` (str): Model identifier (e.g., "opus-4", "sonnet-3.5")
- `tier` (str): Tier identifier (e.g., "T0", "T1", "T2")
- `subtest` (str): Subtest identifier
- `passed` (bool): Binary pass/fail outcome
- `score` (float): Continuous score value

### Aggregations

Per (`agent_model`, `tier`, `subtest`) group:

1. **Pass Rate**: `mean(passed)`
2. **Pass Variance**: `pass_rate * (1 - pass_rate)` (Bernoulli variance)
3. **Score Std Dev**: `std(score)` (standard deviation)
4. **Run Count**: `count(*)` (for tooltip)

## Metrics Displayed

### Pass Variance (Bernoulli)

- **Definition**: Variance of binary pass/fail outcomes
- **Formula**: `p * (1 - p)` where p = pass_rate
- **Range**: [0, 0.25]
- **Interpretation**:
  - **0.00**: All pass or all fail (100% consistent)
  - **0.25**: Maximum variance (50% pass rate, most unstable)
  - **0.10-0.24**: High variance (inconsistent outcomes)

### Score Standard Deviation

- **Definition**: Standard deviation of continuous scores
- **Formula**: `sqrt(mean((x - mean(x))^2))`
- **Range**: [0, ∞)
- **Interpretation**:
  - **Low std dev**: Consistent scoring across runs
  - **High std dev**: Variable performance on same subtest

## Interpretation Guidelines

### High Variance Subtests

Subtests with high variance (bright colors) indicate:

- **Flaky tests**: Outcomes sensitive to non-deterministic factors
- **Borderline difficulty**: Tasks at the edge of agent capability
- **Environment sensitivity**: Performance affected by external factors

### Variance Patterns

- **Tier progression**: Expect higher variance in mid-capability tiers (T2-T3)
- **Model differences**: Compare facets to identify model-specific stability
- **Panel comparison**: Divergence between panels suggests scoring granularity issues

## Use Cases

### Evaluation Protocol Refinement

- **Flag unreliable subtests**: High variance candidates for removal or revision
- **Adjust scoring rubrics**: High score std dev may indicate unclear criteria
- **Increase run counts**: Target high-variance subtests with more replications

### Capability Analysis

- **Identify capability boundaries**: High variance marks transition points
- **Validate tier design**: Excessive variance suggests tier miscalibration
- **Compare agent stability**: Faceted view reveals model-specific consistency

### Statistical Planning

- **Power analysis**: High variance subtests require more samples
- **Confidence interval sizing**: Adjust CI width based on observed variance
- **Hypothesis testing**: Account for heterogeneous variance across subtests

## Implementation Notes

### Source Code

- **Function**: `fig16a_success_variance_per_subtest()`
- **Location**: `/home/mvillmow/Scylla/scylla/analysis/figures/variance.py:122-217`
- **Output**: `fig16a_success_variance_per_subtest.{png,pdf,json}`

### Key Parameters

- **Color schemes**:
  - Panel A: `viridis` (perceptually uniform, good for variance)
  - Panel B: `plasma` (high contrast, good for detecting outliers)
- **Domain handling**:
  - Panel A: Fixed [0, 0.25] (theoretical Bernoulli max)
  - Panel B: Dynamic max with 10% headroom, rounded to 0.05
- **Faceting**: Row-wise by `agent_model`, independent Y-axis per facet

### Dependencies

- `pandas` for data aggregation
- `altair` for visualization
- `derive_tier_order()` for consistent tier ordering
- `save_figure()` for multi-format export

## Related Figures

- **Fig 16b**: Success variance per tier (aggregated view)
- **Fig 16c**: Variance decomposition by source (total vs. between-tier)
- **Fig 15**: Score distributions per subtest (complementary detail)
- **Fig 17**: Consistency metrics (pass-rate stability over time)
