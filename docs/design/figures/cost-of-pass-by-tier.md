# Cost Distribution by Tier (Fig 06)

## Overview

Figure 06 presents the distribution of run-level costs across evaluation tiers using histogram visualizations. Each tier is displayed in a separate subfigure, showing the frequency distribution of `cost_usd` values with logarithmic scale binning. This figure reveals the spread and central tendency of costs within each tier, enabling identification of cost variance and outliers.

## Purpose

The primary objectives of this figure are:

1. **Cost Variance Analysis**: Quantify the spread of costs within each tier to assess consistency and predictability of economic performance
2. **Outlier Detection**: Identify runs with anomalously high or low costs that may indicate edge cases or optimization opportunities
3. **Distribution Shape**: Understand whether cost distributions are normal, skewed, or multimodal within each tier
4. **Tier Comparison**: Compare cost distribution characteristics across tiers to evaluate which configurations produce more stable economic outcomes

This analysis supports economic efficiency evaluation by revealing not just mean costs (captured in Cost-of-Pass metrics) but the full distribution of cost outcomes.

## Data Source

**Input DataFrame**: `runs_df` (runs-level aggregation)

**Required Columns**:

- `tier` (string): Tier identifier (T0-T6)
- `cost_usd` (float): Total cost per run in USD (sum of input, output, tool tokens)

**Filtering**:

- Only rows where `cost_usd > 0` are included
- Log-scale visualization requires positive values, so zero-cost runs are excluded

**Aggregation**: None (raw per-run costs)

## Mathematical Formulas

**Cost per Run** (computed upstream in metrics pipeline):

```
cost_usd = (input_tokens × price_per_input_token) +
           (output_tokens × price_per_output_token) +
           (tool_input_tokens × price_per_tool_input_token) +
           (tool_output_tokens × price_per_tool_output_token)
```

**Histogram Binning**:

- Auto-binning with max 20 bins per tier subfigure
- Bin edges determined by Altair's auto-binning algorithm on log-transformed data
- Each bin represents a range of cost values: `[bin_start, bin_end)`

**Distribution Statistics** (for interpretation, not visualized directly):

```
Mean Cost: μ = Σ(cost_usd) / n
Std Dev: σ = sqrt(Σ(cost_usd - μ)² / (n-1))
Coefficient of Variation: CV = σ / μ  (relative spread)
```

## Theoretical Foundation

### Economic Distribution Analysis

Cost distributions in AI agent systems are typically **right-skewed** (log-normal or gamma-distributed) because:

1. **Lower Bound**: Costs cannot be negative (bounded at zero)
2. **Heavy Tail**: Some runs may trigger expensive retry loops, tool-heavy workflows, or extended thinking, creating high-cost outliers
3. **Multiplicative Factors**: Token usage is the product of multiple factors (task complexity × agent efficiency × model size), leading to log-normal distributions

### Log-Scale Justification

Using logarithmic binning (base 10) serves several purposes:

1. **Range Compression**: Costs may span multiple orders of magnitude (e.g., $0.01 to $10.00), making linear binning ineffective
2. **Outlier Visibility**: Log-scale prevents high-cost outliers from compressing the bulk of the distribution
3. **Multiplicative Patterns**: Log-scale reveals multiplicative relationships (e.g., "Tier X costs 2× more than Tier Y")
4. **Geometric Interpretation**: Equal distances on the log axis represent equal multiplicative ratios

### Cost Stability and Predictability

Low-variance cost distributions indicate:

- Consistent agent behavior across runs
- Predictable economic performance
- Lower financial risk for production deployment

High-variance distributions suggest:

- Sensitivity to task complexity or randomness
- Potential optimization opportunities
- Need for cost guardrails or budgeting mechanisms

## Visualization Details

**Chart Type**: Histogram (bar chart with binned continuous variable)

**Axes**:

- **X-axis**: `cost_usd` (quantitative)
  - Title: "Cost (USD)"
  - Scale: Logarithmic (base 10)
  - Binning: Auto-binning with `maxbins=20`
- **Y-axis**: `count()` (quantitative)
  - Title: "Count"
  - Scale: Linear
  - Represents the number of runs in each cost bin

**Faceting**:

- **Column facet**: `tier` (nominal)
  - Each tier displayed as a separate subfigure
  - Tier order derived from data using natural sort (T0 < T1 < ... < T6)
  - Enables side-by-side comparison of cost distributions

**Visual Encoding**:

- Bar height encodes the count of runs in each cost bin
- Bar width represents the cost bin range (varies due to log-scale binning)
- No color encoding (uniform bar color across all tiers)

**Implementation Details** (from `scylla/analysis/figures/cost_analysis.py:18-57`):

- Data filtered to exclude `cost_usd <= 0` before visualization
- Altair's `alt.Bin(maxbins=20)` used for automatic bin edge calculation
- Tier order derived dynamically from data (no hardcoded tier list)
- Saved as Vega-Lite JSON specification + PNG/PDF renders

## Interpretation Guidelines

### Reading the Figure

1. **Identify Central Tendency**: The peak of each histogram indicates the most common cost range for that tier
2. **Assess Spread**: Wider distributions indicate higher cost variance; narrow distributions suggest consistency
3. **Detect Skew**: Right-skewed distributions (long tail toward higher costs) indicate outlier runs
4. **Compare Across Tiers**: Higher-tier histograms should generally shift rightward (higher costs) if additional capabilities increase token usage

### Key Patterns to Look For

**Normal Distribution** (symmetric bell curve on log scale):

- Indicates consistent, predictable costs
- Most runs cluster around the mean
- Rare outliers on both ends

**Right-Skewed Distribution** (long tail toward high costs):

- Common in AI agent systems
- Indicates occasional expensive runs (retries, complex tasks)
- May signal optimization opportunities

**Bimodal Distribution** (two distinct peaks):

- Suggests two distinct cost regimes (e.g., simple vs. complex tasks)
- May indicate task heterogeneity within tier
- Could reveal subgroups requiring separate analysis

**Uniform Distribution** (flat histogram):

- Indicates high cost unpredictability
- Rare in practice; may signal data quality issues

### Actionable Insights

- **High CV (σ/μ > 0.5)**: Investigate outlier runs to identify cost drivers; consider cost capping mechanisms
- **Tier X costs overlap Tier Y**: Question whether Tier X's added capabilities justify the cost; evaluate Frontier CoP
- **Outliers beyond 2σ**: Drill down into specific runs to understand edge cases (complex tasks, retry loops, tool failures)

## Related Figures

### Primary Relationships

- **Fig 08: Cost-Quality Pareto Frontier** - Combines cost distributions with quality metrics to identify optimal tiers on the cost-quality tradeoff curve. Fig 06 provides the underlying cost distribution that informs Pareto efficiency analysis.

- **Fig 22: Cumulative Cost** - Shows how total experiment costs accumulate over time. Fig 06 reveals the per-run cost variability that drives cumulative cost growth rates.

### Secondary Relationships

- **Fig 07: Token Distribution** - Breaks down costs by component (input/output/tool tokens). Use Fig 06 to identify high-cost outliers, then consult Fig 07 to diagnose which token type is driving the cost.

- **Fig 20: Metric Correlation Heatmap** - Explores correlations between cost and quality metrics. Fig 06 distributions inform the interpretation of cost-quality correlations.

### Analysis Workflow

1. **Fig 06**: Identify tiers with high cost variance or outliers
2. **Fig 08**: Evaluate whether those tiers are Pareto-efficient (justify cost with quality gains)
3. **Fig 07**: Diagnose cost drivers (which token types contribute most)
4. **Fig 22**: Assess cumulative cost impact of high-variance tiers

## Code Reference

**Source**: `/home/mvillmow/Scylla/scylla/analysis/figures/cost_analysis.py:18-57`

**Function**: `fig06_cop_by_tier(runs_df: pd.DataFrame, output_dir: Path, render: bool = True)`

**Key Implementation Details**:

```python
# Data preparation
data = runs_df[["tier", "cost_usd"]].copy()
data = data[data["cost_usd"] > 0]  # Filter for log-scale compatibility

# Tier ordering
tier_order = derive_tier_order(data)  # Natural sort: T0 < T1 < ... < T6

# Histogram with log-binning
histogram = (
    alt.Chart(data)
    .mark_bar()
    .encode(
        x=alt.X(
            "cost_usd:Q",
            bin=alt.Bin(maxbins=20),  # Auto-binning
            title="Cost (USD)",
            scale=alt.Scale(type="log", base=10),  # Log scale
        ),
        y=alt.Y("count():Q", title="Count"),
    )
)

# Facet by tier
chart = histogram.facet(
    column=alt.Column("tier:N", title="Tier", sort=tier_order)
).properties(title="Cost Distribution per Tier (Log Scale)")

# Save as Vega-Lite JSON + rendered PNG/PDF
save_figure(chart, "fig06_cop_by_tier", output_dir, render)
```

**Dependencies**:

- `derive_tier_order()` - Natural sort for tier labels (from `scylla/analysis/figures/__init__.py`)
- `save_figure()` - Saves Vega-Lite spec and renders to PNG/PDF (from `scylla/analysis/figures/spec_builder.py`)

**Output Files**:

- `fig06_cop_by_tier.json` - Vega-Lite specification
- `fig06_cop_by_tier.png` - Rasterized figure (if `render=True`)
- `fig06_cop_by_tier.pdf` - Vector figure (if `render=True`)

**Reproducibility**:

```bash
# Regenerate figure from analysis pipeline
scylla analyze --runs runs.csv --output-dir ./figures/
```
