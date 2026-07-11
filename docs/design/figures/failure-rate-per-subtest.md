# Figure 18a: Failure Rate per Subtest (Detailed)

## Overview

Figure 18a is a horizontal bar chart that visualizes the failure rate (1 - pass_rate) for each individual subtest across all tiers and agent models. This detailed view provides granular insight into which specific subtests are most challenging for agents, enabling identification of failure-prone test cases and analysis of difficulty patterns across the testing hierarchy.

The figure complements Figure 18b (aggregate failure rates) by showing the complete breakdown of failures at the subtest level, while Figure 03 provides tier-level failure rate aggregation.

## Purpose

The primary purposes of Figure 18a are to:

1. **Identify Problematic Subtests**: Pinpoint specific subtests with high failure rates that may require test design improvements or agent capability enhancements
2. **Analyze Difficulty Patterns**: Reveal systematic patterns in subtest difficulty across tiers and models
3. **Support Test Refinement**: Guide decisions about which subtests to adjust, remove, or investigate further
4. **Enable Targeted Optimization**: Focus agent improvement efforts on specific failure-prone subtests rather than broad tier-level optimizations
5. **Validate Test Coverage**: Ensure subtests provide appropriate difficulty distribution and coverage of agent capabilities

## Data Source

The figure aggregates data from individual agent runs, computing failure rates per subtest:

**Input**: `runs_df` DataFrame with columns:

- `agent_model`: Model identifier (e.g., "opus-4-6", "sonnet-4-5")
- `tier`: Tier identifier (T0-T6)
- `subtest`: Subtest identifier within tier
- `passed`: Boolean indicating test pass/fail

**Aggregation**: Group by `(agent_model, tier, subtest)` and compute:

- `pass_rate = mean(passed)` for each subtest
- `failure_rate = 1 - pass_rate`
- `n_runs`: Number of runs for each subtest

**Output**: Failure rate per subtest with metadata for visualization.

## Mathematical Formulas

### Failure Rate per Subtest

For each combination of agent model, tier, and subtest:

```
failure_rate(m, t, s) = 1 - pass_rate(m, t, s)
```

Where:

```
pass_rate(m, t, s) = (Σ passed_i) / n_runs
```

- `m`: Agent model
- `t`: Tier
- `s`: Subtest
- `passed_i`: Binary indicator (1 if run i passed, 0 if failed)
- `n_runs`: Total number of runs for subtest s in tier t using model m

### Relationship to Success Variance

While success variance (Figure 16a) measures **consistency** in pass rates:

```
variance = p(1 - p)
```

Failure rate measures the **absolute difficulty** of a subtest:

```
failure_rate = 1 - p
```

**Key Difference**:

- **High variance** (variance ≈ 0.25 at p = 0.5): Inconsistent results, sometimes passes, sometimes fails
- **High failure rate** (failure_rate ≈ 1.0): Consistently fails, regardless of consistency

A subtest can have:

- **High failure rate, low variance**: Consistently fails (e.g., p = 0.05, variance = 0.0475)
- **Medium failure rate, high variance**: Inconsistent (e.g., p = 0.5, variance = 0.25)
- **Low failure rate, low variance**: Consistently passes (e.g., p = 0.95, variance = 0.0475)

## Theoretical Foundation

### Subtest Difficulty Analysis

Failure rates provide a direct measure of subtest difficulty for each agent model. The theoretical interpretation:

1. **Capability Gaps**: High failure rates indicate subtests that exceed current agent capabilities
2. **Test Validity**: Extremely high failure rates (>0.95) may indicate overly difficult or poorly designed tests
3. **Tier Progression**: Expected pattern shows increasing failure rates in higher tiers (T5, T6) as complexity increases
4. **Model Differences**: Comparative failure rates across models reveal model-specific strengths and weaknesses

### Expected Patterns

**Well-Designed Test Suite**:

- **T0-T2**: Failure rates 0.1-0.3 (baseline capabilities)
- **T3-T4**: Failure rates 0.3-0.6 (intermediate difficulty)
- **T5-T6**: Failure rates 0.5-0.8 (challenging capabilities)

**Anomalous Patterns**:

- **Uniform failure rates across tiers**: Insufficient difficulty progression
- **Extremely high failure rates in T0-T1**: Test design issues or fundamental agent limitations
- **Large variance between models in same tier**: Model-specific capability gaps

### Statistical Interpretation

Each failure rate is based on `n_runs` samples. For statistical significance:

```
standard_error = sqrt(p(1-p) / n_runs)
```

With typical n_runs ≥ 10, failure rates are reasonably stable estimates of true subtest difficulty.

## Visualization Details

### Chart Type

**Horizontal Bar Chart** with faceting by agent model.

### Visual Encoding

**Axes**:

- **Y-axis**: `subtest_label` (format: "tier-subtest", e.g., "T0-baseline")
  - Ordered by tier (ascending), then by subtest within tier
  - Independent y-scale per model facet to accommodate different subtest sets
- **X-axis**: `failure_rate` (quantitative)
  - Domain: [0, 1] (0% to 100% failure rate)
  - Title: "Failure Rate"

**Color**:

- **Encoding**: `tier` (nominal)
- **Scale**: Dynamic tier color scale (derived from data)
- **Purpose**: Visually group subtests by tier for quick tier-level pattern recognition

**Faceting**:

- **Column**: `agent_model` (nominal)
- **Purpose**: Enable direct comparison of failure rates across models for same subtests

**Tooltips**:

- **Tier**: Tier identifier (e.g., "T0", "T1")
- **Subtest**: Subtest identifier
- **Failure Rate**: Formatted as percentage (e.g., "45.23%")
- **Runs**: Number of runs (sample size for statistical confidence)

### Layout

- **Title**: "Failure Rate per Subtest (Detailed)"
- **Resolution**: Independent y-scales per model facet
- **Sorting**: Subtests ordered by tier (ascending), maintaining consistent tier grouping

## Interpretation Guidelines

### Identifying Problematic Subtests

**High-Priority Failures** (failure_rate > 0.8):

1. Review test design for excessive difficulty or ambiguity
2. Verify test requirements are achievable with available tools/skills
3. Consider if test represents genuine capability gap vs. test design issue

**Medium-Priority Failures** (0.5 < failure_rate ≤ 0.8):

1. Expected for higher tiers (T5-T6)
2. Investigate if in lower tiers (T0-T2) - may indicate capability gaps
3. Analyze patterns across models - model-specific or universal difficulty?

**Low Failure Rates** (failure_rate < 0.3):

1. Expected for baseline tiers (T0-T2)
2. In higher tiers, may indicate test is too easy or not sufficiently challenging

### Tier Progression Analysis

**Expected Pattern**: Failure rates should increase with tier level:

```
T0 < T1 < T2 < T3 < T4 < T5 < T6
```

**Deviations to Investigate**:

- **Lower tier harder than higher tier**: May indicate test design inconsistency
- **Flat failure rates across tiers**: Insufficient difficulty progression
- **Sudden spikes**: Investigate specific subtests causing anomalies

### Cross-Model Comparison

**Consistent Failures Across Models**:

- Indicates genuine test difficulty or capability limitation shared by all models
- May suggest test requires capabilities beyond current model generations

**Model-Specific Failures**:

- One model fails significantly more than others on specific subtests
- Indicates model-specific weaknesses or strengths
- Guide model selection for specific task types

### Statistical Considerations

**Sample Size**: Check `n_runs` in tooltip

- `n_runs < 5`: Unreliable estimates, high variance
- `n_runs ≥ 10`: Reasonable confidence in failure rate
- `n_runs ≥ 30`: High confidence in failure rate

**Confidence Intervals**: For failure_rate `p` with `n_runs` samples:

```
95% CI ≈ p ± 1.96 * sqrt(p(1-p) / n_runs)
```

Example: `p = 0.5, n_runs = 20`

```
CI ≈ 0.5 ± 0.22 → [0.28, 0.72]
```

Wide confidence intervals suggest need for more runs before drawing conclusions.

## Related Figures

### Direct Relationships

**Figure 18b: Failure Rate Aggregate**

- Shows tier-level aggregated failure rates
- Complements this figure by providing tier-level summary
- Use 18a for detailed subtest analysis, 18b for tier-level overview

**Figure 03: Failure Rate by Tier**

- Provides tier-level failure rate visualization
- Alternative view of aggregated failure patterns
- Use for tier-level comparisons, 18a for subtest-level detail

**Figure 16a: Success Variance per Subtest**

- Analyzes **consistency** of subtest results (variance)
- Complements failure rate (absolute difficulty) with reliability metrics
- High variance + high failure rate = difficult and inconsistent test
- Low variance + high failure rate = consistently difficult test

### Analysis Workflow

1. **Start with Figure 18b**: Identify tiers with high aggregate failure rates
2. **Use Figure 18a**: Drill down to specific problematic subtests within those tiers
3. **Cross-reference Figure 16a**: Check if high failure rates coincide with high variance (inconsistency)
4. **Review Figure 03**: Validate tier-level patterns across different aggregation methods

## Code Reference

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/variance.py`

**Function**: `fig18a_failure_rate_per_subtest(runs_df, output_dir, render=True)`

**Lines**: 324-396

**Key Implementation Details**:

1. **Data Aggregation**:

   ```python
   for (model, tier, subtest), group in runs_df.groupby(["agent_model", "tier", "subtest"]):
       pass_rate = group["passed"].mean()
       failure_rate = 1 - pass_rate
   ```

2. **Subtest Label Construction**:

   ```python
   "subtest_label": f"{tier}-{subtest}"
   ```

3. **Sorting**:

   ```python
   failure_df = failure_df.sort_values(["tier", "subtest"])
   ```

4. **Color Scale**:

   ```python
   domain, range_ = get_color_scale("tiers", tier_order)
   ```

5. **Faceting**:

   ```python
   .facet(column=alt.Column("agent_model:N", title=None))
   .resolve_scale(y="independent")
   ```

**Output Files**:

- `fig18a_failure_rate_per_subtest.png` (raster)
- `fig18a_failure_rate_per_subtest.pdf` (vector)
- `fig18a_failure_rate_per_subtest.json` (Vega-Lite spec)

**Dependencies**:

- `derive_tier_order()`: Determines tier ordering from data
- `get_color_scale()`: Provides consistent tier color encoding
- `save_figure()`: Exports chart in multiple formats
