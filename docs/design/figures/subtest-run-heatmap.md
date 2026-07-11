# Subtest Run Heatmap

## Overview

The Subtest Run Heatmap (fig15a) is a comprehensive visualization showing performance scores for all subtests across all experimental runs, faceted by tier and agent model. This heatmap provides maximum granularity, displaying the complete matrix of (subtest × run) combinations to reveal performance variation and consistency patterns within each tier.

Key characteristics:

- **Axes**: Y-axis shows subtests (sorted numerically), X-axis shows run numbers
- **Faceting**: Organized by tier (rows) and agent model (columns)
- **Color**: Score values from 0 (red) to 1 (green) using red-yellow-green gradient
- **Granularity**: Maximum - shows every individual run for every subtest

## Purpose

This figure serves multiple analytical purposes:

1. **Variability Analysis**: Identifies which subtests exhibit high run-to-run variance vs. consistent performance
2. **Outlier Detection**: Reveals exceptional runs (both high and low performers) that may warrant investigation
3. **Consistency Assessment**: Shows whether agent performance is stable or erratic across repeated attempts
4. **Pattern Recognition**: Exposes systematic patterns such as improving/degrading performance over sequential runs
5. **Tier Comparison**: Enables cross-tier comparison of consistency characteristics

The all-runs view is essential for understanding the reliability and reproducibility of agent performance, complementing aggregate metrics with full distributional information.

## Data Source

**Input**: `runs_df` DataFrame from `/home/mvillmow/Scylla/scylla/e2e/aggregate_runs.py`

**Required Columns**:

- `agent_model`: Agent/model identifier (e.g., "opus-4.6", "sonnet-4.5")
- `tier`: Testing tier (T0-T6)
- `subtest`: Numeric subtest identifier within tier
- `run_number`: Sequential run identifier (1, 2, 3, ...)
- `score`: Normalized score [0, 1] for the subtest in that run

**Data Preparation**:

```python
# Extract relevant columns
heatmap_data = runs_df[["agent_model", "tier", "subtest", "run_number", "score"]].copy()

# Sort subtests numerically within each tier
heatmap_data["subtest_num"] = heatmap_data["subtest"].astype(int)
subtest_order = sorted(heatmap_data["subtest"].unique(), key=lambda x: int(x))
```

Each cell in the heatmap represents a single (tier, subtest, run) tuple with its associated score.

## Mathematical Formulas

**Score Representation**:

For each cell at position (subtest `s`, run `r`) within tier `t`:

$$
\text{Cell}_{s,r,t} = \text{score}(t, s, r)
$$

where `score(t, s, r)` ∈ [0, 1] is the normalized performance score.

**Variance Calculation** (for interpretation):

To quantify run-to-run variability for a specific subtest:

$$
\sigma^2_s = \frac{1}{N_r} \sum_{r=1}^{N_r} \left( \text{score}(t, s, r) - \bar{s} \right)^2
$$

where:

- $\sigma^2_s$ = variance for subtest `s`
- $N_r$ = total number of runs
- $\bar{s}$ = mean score across all runs for subtest `s`

High variance indicates inconsistent performance; low variance indicates reliable behavior.

## Theoretical Foundation

### Run Variability

Agent systems may exhibit run-to-run variability due to:

1. **Non-deterministic Sampling**: Temperature > 0 in LLM inference introduces stochastic variation
2. **Search Space Exploration**: Different solution paths may be explored across runs
3. **External Dependencies**: Network conditions, API latency, resource availability
4. **State Dependencies**: Subtle differences in context or memory state

### Consistency as a Quality Metric

Consistency (low variance) is valuable because:

- **Reliability**: Predictable performance enables confident deployment
- **Robustness**: Low sensitivity to random factors indicates stable capability
- **True Capability**: High variance may indicate lucky/unlucky outcomes rather than genuine skill

However, some variability is expected and even beneficial:

- **Exploration**: Multiple runs can discover diverse solution strategies
- **Best-Case Performance**: Maximum capability may only emerge probabilistically
- **Failure Modes**: Variance reveals edge cases and failure conditions

### Interpretation Framework

**High Score + Low Variance**: Robust capability - agent reliably solves the subtest
**High Score + High Variance**: Inconsistent capability - success depends on run conditions
**Low Score + Low Variance**: Consistent limitation - subtest exceeds agent capabilities
**Low Score + High Variance**: Erratic performance - unstable or brittle behavior

## Visualization Details

### Implementation

The heatmap uses Altair's declarative grammar:

```python
heatmap = (
    alt.Chart(heatmap_data)
    .mark_rect()
    .encode(
        x=alt.X("run_number:O", title="Run Number", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("subtest:O", title="Subtest", sort=subtest_order),
        color=alt.Color(
            "score:Q",
            title="Score",
            scale=alt.Scale(scheme="redyellowgreen", domain=[0, 1]),
        ),
        tooltip=[
            alt.Tooltip("tier:O", title="Tier"),
            alt.Tooltip("subtest:O", title="Subtest"),
            alt.Tooltip("run_number:O", title="Run"),
            alt.Tooltip("score:Q", title="Score", format=".3f"),
        ],
    )
    .properties(width=300, height=200)
)

# Facet by tier (rows) and agent_model (columns)
chart = (
    heatmap.facet(
        row=alt.Row("tier:O", title="Tier", sort=tier_order),
        column=alt.Column("agent_model:N", title=None),
    )
    .properties(title="Subtest/Run Scores by Tier (All Runs)")
    .resolve_scale(y="independent")
)
```

### Visual Design Choices

**Color Scale**: Red-Yellow-Green gradient

- Red (0.0): Complete failure
- Yellow (0.5): Partial success
- Green (1.0): Complete success
- Continuous gradient reveals fine-grained score differences

**Faceting Strategy**:

- **Rows = Tiers**: Enables vertical comparison across capability levels
- **Columns = Models**: Enables horizontal comparison across agent variants
- **Independent Y-scales**: Each tier's subtests are independently ordered (numerically)

**Dimensions**:

- Width: 300px per facet (accommodates typical run counts)
- Height: 200px per facet (balances subtest visibility with screen real estate)

**Interactive Elements**:

- Tooltip displays tier, subtest, run number, and exact score on hover
- Enables precise inspection of individual cells

## Interpretation Guidelines

### Identifying Patterns

**Horizontal Bands** (same color across runs):

- Consistent performance across multiple runs
- Indicates stable behavior for that subtest
- Confidence in capability assessment

**Vertical Stripes** (same color down subtests):

- Systematic run-level effects
- May indicate warm-up, fatigue, or resource conditions
- Consider environmental factors

**Checkerboard Patterns** (alternating colors):

- High variability across both dimensions
- Suggests unreliable or borderline performance
- May require more runs for statistical confidence

**Color Gradients** (smooth transitions):

- Progressive learning or degradation across runs
- Could indicate adaptation or resource depletion
- Examine temporal sequence

### Actionable Insights

**For High Variance Subtests**:

1. Increase run count to better estimate true capability
2. Investigate environmental factors (API limits, timeouts, rate limiting)
3. Examine logs to understand divergent execution paths
4. Consider whether task has multiple valid solutions

**For Consistent Low Performers**:

1. Analyze failure modes - is this a fundamental limitation?
2. Check if subtest requires capabilities not present in this tier
3. Use as candidate for capability enhancement experiments

**For Outlier Runs**:

1. Inspect logs for unusual conditions
2. Determine if outlier represents rare success or failure mode
3. Consider using best-run metrics (see fig15b) for capability ceiling

### Statistical Considerations

**Sample Size**: More runs increase confidence in mean and variance estimates
**Independence**: Ensure runs are truly independent (fresh state, no carryover)
**Normality**: Score distributions may be skewed; consider non-parametric tests

## Related Figures

### Fig 15b: Subtest Best Heatmap

**Filename**: `fig15b_subtest_best_heatmap`
**Relationship**: Shows only the best-performing run for each subtest
**Granularity**: Mid-level - removes run variance, focuses on capability ceiling
**Use Case**: Understanding maximum achievable performance without run variation noise

**Comparison**:

- Fig15a shows distribution; Fig15b shows maximum
- Fig15a reveals consistency; Fig15b reveals potential
- Use Fig15a to assess reliability; Fig15b to assess capability

### Fig 15c: Tier Summary Heatmap

**Filename**: `fig15c_tier_summary_heatmap`
**Relationship**: Aggregates all subtests within each tier into mean score
**Granularity**: Minimum - tier-level summary across runs
**Use Case**: High-level comparison of tier performance without subtest detail

**Comparison**:

- Fig15a shows per-subtest detail; Fig15c shows tier averages
- Fig15a has N_subtests rows; Fig15c has N_tiers rows
- Use Fig15a for drill-down; Fig15c for overview

### Figure Progression

The three figures form a granularity hierarchy:

1. **Fig15a** (this figure): Maximum detail - all runs, all subtests
2. **Fig15b**: Mid detail - best run per subtest, all subtests
3. **Fig15c**: Minimum detail - aggregated across subtests, all runs

This progression supports top-down analysis (start with Fig15c overview, drill into Fig15a details) or bottom-up synthesis (understand Fig15a patterns, summarize with Fig15c).

## Code Reference

**Implementation**: `/home/mvillmow/Scylla/scylla/analysis/figures/subtest_detail.py:87-150`

**Function Signature**:

```python
def fig15a_subtest_run_heatmap(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None
```

**Dependencies**:

- `pandas`: DataFrame manipulation
- `altair`: Declarative visualization
- `derive_tier_order()`: Helper to extract and sort tier labels from data
- `save_figure()`: Utility to export chart as PNG/PDF/JSON

**Output Files**:

- `fig15a_subtest_run_heatmap.png`: Raster image
- `fig15a_subtest_run_heatmap.pdf`: Vector PDF
- `fig15a_subtest_run_heatmap.json`: Vega-Lite JSON specification

**Integration**: Called from analysis pipeline in `/home/mvillmow/Scylla/scylla/e2e/run_report.py` as part of comprehensive report generation.
