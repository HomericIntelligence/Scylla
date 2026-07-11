# Figure 16b: Success Variance Aggregate

## Overview

Figure 16b provides a tier-level summary of success variance by aggregating all subtest runs within each tier. Unlike Figure 16a which shows variance at the per-subtest granularity, this figure pools all subtests together to answer the question: "How consistent is this tier overall, regardless of which specific subtest is being run?"

The figure consists of two vertically stacked bar chart panels showing aggregate variance metrics across testing tiers, with bars color-coded by agent model.

## Purpose

This figure serves to:

1. **Assess Overall Tier Consistency**: Identify which tiers exhibit stable vs. volatile performance when all subtests are considered collectively
2. **Compare Model Stability**: Evaluate how different agent models perform in terms of overall consistency at the tier level
3. **Complement Per-Subtest Analysis**: Provide the macro view that complements Figure 16a's micro view of individual subtest variance
4. **Guide Tier Selection**: Help practitioners choose tiers with appropriate stability characteristics for their use case

The aggregate view is particularly useful for:

- Identifying tiers with systematically high or low variance across all tasks
- Understanding whether variance patterns are tier-specific or model-specific
- Making architecture decisions based on overall tier stability rather than individual subtest behavior

## Data Source

The figure aggregates data from:

- **Input**: `runs_df` (Runs DataFrame containing all evaluation runs)
- **Grouping**: Data is grouped by `(agent_model, tier)`, pooling all subtests within each tier
- **Metrics Computed**:
  - Binary pass/fail variance (Bernoulli variance)
  - Continuous score standard deviation
  - Sample size (total number of runs across all subtests in the tier)

**Key Aggregation Logic**:

```python
for (model, tier), group in runs_df.groupby(["agent_model", "tier"]):
    pass_rate = group["passed"].mean()  # Aggregate pass rate across all subtests
    pass_variance = pass_rate * (1 - pass_rate)  # Bernoulli variance
    score_std = group["score"].std()  # Standard deviation of scores
```

All runs within a tier are treated as a single population, regardless of which subtest they belong to.

## Mathematical Formulas

### Panel A: Pass/Fail Variance (Bernoulli)

For each `(agent_model, tier)` combination:

```
pass_rate = mean(passed_i) for all runs i in tier
pass_variance = pass_rate × (1 - pass_rate)
```

**Bernoulli Variance Formula**:

```
Var(X) = p(1 - p)
```

Where:

- `p` = aggregate pass rate across all subtests in the tier
- Maximum variance occurs at `p = 0.5` (variance = 0.25)
- Variance approaches 0 as `p → 0` or `p → 1` (consistent failure or success)

**Interpretation**:

- **High variance (≈0.25)**: Tier passes ~50% of the time (highly unpredictable)
- **Low variance (≈0)**: Tier consistently passes or consistently fails (predictable)

### Panel B: Score Standard Deviation

For each `(agent_model, tier)` combination:

```
score_std = std(score_i) for all runs i in tier
```

**Standard Deviation Formula**:

```
σ = sqrt(Σ(x_i - μ)² / N)
```

Where:

- `x_i` = score for run i
- `μ` = mean score across all runs in the tier
- `N` = total number of runs in the tier

**Interpretation**:

- **High std dev**: Scores vary widely across runs (inconsistent quality)
- **Low std dev**: Scores are tightly clustered (consistent quality)

## Theoretical Foundation

### Why Aggregate Variance Matters

1. **System-Level Reliability**: While per-subtest variance (Figure 16a) reveals task-specific instability, aggregate variance reveals system-level reliability. A tier with low aggregate variance is predictable across diverse tasks.

2. **Portfolio Effect**: Aggregating across subtests can reveal whether variance is systematic (affects all subtests) or idiosyncratic (varies by subtest). High aggregate variance suggests systemic instability in the tier's architecture.

3. **Bernoulli vs. Gaussian Assumptions**:
   - **Panel A** uses Bernoulli variance because pass/fail is binary
   - **Panel B** uses standard deviation because scores are continuous
   - Together, they provide complementary views of stability

4. **Variance as Risk Metric**: In production systems, variance translates to risk. High variance means unpredictable behavior, which may be unacceptable even if average performance is good.

### Statistical Considerations

- **Aggregation reduces granularity**: By pooling subtests, we lose the ability to identify which specific subtests drive variance
- **Sample size increases**: Larger sample sizes (more runs per tier) make aggregate statistics more reliable
- **Heterogeneity**: If subtests are highly heterogeneous, aggregate variance may conflate task difficulty with tier stability

## Visualization Details

### Panel A: Pass/Fail Variance (Aggregated)

**Chart Type**: Grouped bar chart

- **X-axis**: Tier (categorical, ordered T0 → T6)
- **Y-axis**: Pass variance (quantitative, range 0-0.25)
- **Color**: Agent model (categorical, color-coded)
- **Dimensions**: 400×300 pixels
- **Tooltip**:
  - Model name
  - Tier
  - Pass variance (3 decimal places)
  - Total runs (across all subtests)

**Y-axis Scale**: Fixed domain `[0, 0.25]` to facilitate cross-tier comparison. The maximum theoretical variance is 0.25 (at p=0.5).

### Panel B: Score Standard Deviation (Aggregated)

**Chart Type**: Grouped bar chart

- **X-axis**: Tier (categorical, ordered T0 → T6)
- **Y-axis**: Score standard deviation (quantitative, dynamic range)
- **Color**: Agent model (categorical, color-coded, same as Panel A)
- **Dimensions**: 400×300 pixels
- **Tooltip**:
  - Model name
  - Tier
  - Score std dev (3 decimal places)
  - Total runs (across all subtests)

**Y-axis Scale**: Dynamic domain computed as:

```python
std_max = max(0.3, variance_df["score_std"].max() * 1.1)
domain = [0, round(std_max / 0.05) * 0.05]  # Round to nearest 0.05
```

This ensures the scale adapts to data while maintaining a minimum range of 0.3.

### Layout

Panels are **stacked vertically** (`bar_pass & bar_score`), creating a unified view:

```
+-----------------------------------+
| Panel A: Pass/Fail Variance       |
+-----------------------------------+
| Panel B: Score Std Dev            |
+-----------------------------------+
```

The vertical stacking emphasizes comparison across panels for the same tier, rather than across tiers within a panel.

### Color Encoding

Both panels use the same color scale for agent models to ensure visual consistency:

```python
models = sorted(variance_df["agent_model"].unique())
domain, range_ = get_color_scale("models", models)
```

This allows direct comparison of the same model's behavior across both metrics.

## Interpretation Guidelines

### Reading the Figure

1. **Compare Panels Vertically**: For a given tier and model, compare the bar height in Panel A vs. Panel B. High variance in both suggests overall instability; high in one but not the other suggests mode-specific issues.

2. **Compare Models Horizontally**: Within a tier, compare bars across models. Models with consistently lower bars are more stable.

3. **Compare Tiers Across X-axis**: Identify which tiers exhibit systemic variance issues across all models.

### Key Patterns to Look For

**High Aggregate Variance (Both Panels)**:

- **Interpretation**: The tier is fundamentally unstable, producing inconsistent results across all subtests
- **Implication**: Avoid this tier for production use unless variance can be reduced

**High Variance in Panel A, Low in Panel B**:

- **Interpretation**: Pass/fail outcomes are unpredictable (~50% success), but when it succeeds, quality is consistent
- **Implication**: Focus on improving pass rate reliability

**Low Variance in Panel A, High in Panel B**:

- **Interpretation**: Pass/fail is predictable, but quality varies widely across runs
- **Implication**: Focus on stabilizing implementation quality

**Low Aggregate Variance (Both Panels)**:

- **Interpretation**: The tier is highly consistent and reliable across all tasks
- **Implication**: Good candidate for production deployment

### When to Use Fig16b vs. Fig16a

| Use Figure 16b when... | Use Figure 16a when... |
|------------------------|------------------------|
| Evaluating overall tier reliability | Diagnosing subtest-specific variance issues |
| Comparing tier architectures at macro level | Identifying which subtests are unstable |
| Making tier selection decisions | Debugging specific task failures |
| Reporting tier-level stability to stakeholders | Analyzing variance patterns across task types |
| Assessing portfolio-level risk | Investigating outlier subtests |

**General Rule**: Start with Figure 16b for the big picture, then drill down to Figure 16a if specific tiers show concerning aggregate variance.

## Related Figures

### Figure 16a: Success Variance Per Subtest

- **Granularity**: Per-subtest variance (micro view)
- **Visualization**: Heatmaps faceted by model, with subtests on Y-axis
- **Use Case**: Identify which specific subtests drive variance
- **Relationship**: Figure 16a provides the detailed breakdown that Figure 16b summarizes

**Workflow**: Use Figure 16b to identify problematic tiers, then use Figure 16a to identify which subtests within those tiers are the primary contributors to variance.

### Other Variance-Related Figures

- **Figure 1: Score Variance by Tier**: Histogram showing score distributions (not variance metrics)
- **Figure 3: Failure Rate by Tier**: Stacked bar chart of grade proportions (categorical failure analysis)

## Code Reference

**Source**: `/home/mvillmow/Scylla/scylla/analysis/figures/variance.py:220-321`

**Function**: `fig16b_success_variance_aggregate(runs_df, output_dir, render=True)`

**Key Implementation Steps**:

1. **Aggregate data by tier**:

   ```python
   for (model, tier), group in runs_df.groupby(["agent_model", "tier"]):
       pass_rate = group["passed"].mean()
       pass_variance = pass_rate * (1 - pass_rate)
       score_std = group["score"].std()
   ```

2. **Create Panel A (pass variance)**:

   ```python
   bar_pass = alt.Chart(variance_df).mark_bar().encode(
       x=alt.X("tier:O", sort=tier_order),
       y=alt.Y("pass_variance:Q", scale=alt.Scale(domain=[0, 0.25])),
       color=alt.Color("agent_model:N", scale=alt.Scale(domain=domain, range=range_))
   )
   ```

3. **Create Panel B (score std dev)**:

   ```python
   bar_score = alt.Chart(variance_df).mark_bar().encode(
       x=alt.X("tier:O", sort=tier_order),
       y=alt.Y("score_std:Q", scale=alt.Scale(domain=[0, std_max])),
       color=alt.Color("agent_model:N", scale=alt.Scale(domain=domain, range=range_))
   )
   ```

4. **Stack panels vertically**:

   ```python
   chart = (bar_pass & bar_score).properties(
       title="Success Variance Aggregate (All Subtests Combined Per Tier)"
   )
   ```

5. **Save figure**:

   ```python
   save_figure(chart, "fig16b_success_variance_aggregate", output_dir, render)
   ```

**Output Files**:

- `fig16b_success_variance_aggregate.json` (Vega-Lite specification)
- `fig16b_success_variance_aggregate.png` (rasterized image, if `render=True`)
- `fig16b_success_variance_aggregate.pdf` (vector graphic, if `render=True`)

**Dependencies**:

- `derive_tier_order()`: Determines canonical tier ordering from data
- `get_color_scale()`: Provides consistent color mapping for agent models
- `save_figure()`: Handles file output in multiple formats
