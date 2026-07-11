# Cost vs Quality Regression Analysis

## Overview

Figure 21 visualizes the regression analysis of cost vs quality trade-offs at the subtest level. It presents scatter plots with OLS (Ordinary Least Squares) regression lines, R² values, and p-values to quantify the relationship between mean cost per subtest and mean score per subtest. The visualization reveals whether increasing investment (cost) yields proportional quality improvements and identifies the efficiency of cost-quality conversion.

## Purpose

This figure answers critical economic questions:

- **Is there a linear relationship between cost and quality?** Strong positive correlation (high R²) indicates that spending more reliably improves outcomes.
- **What is the marginal return on investment?** The regression slope quantifies how much quality improvement (Δscore) is gained per dollar spent.
- **How efficient is cost-quality conversion?** Models with steeper slopes and higher R² values provide better return on investment.
- **Are there diminishing returns?** Nonlinear patterns or low R² suggest that simply increasing cost does not guarantee proportional quality gains.

## Source Code

**Location**: `/home/mvillmow/Scylla/scylla/analysis/figures/correlation.py:136-271`

**Function**: `fig21_cost_quality_regression(runs_df: pd.DataFrame, output_dir: Path, render: bool = True)`

## Data Processing

### Input Data

**Source**: `runs_df` (Runs DataFrame)

**Schema**:

- `agent_model` (str): Agent model identifier (e.g., "claude-opus-4", "gpt-4-turbo")
- `tier` (str): Testing tier (T0-T6)
- `subtest` (str): Subtest identifier
- `cost_usd` (float): Cost per run in USD
- `score` (float): Score per run (0.0-1.0)

### Aggregation Pipeline

1. **Subtest-Level Aggregation**:

   ```python
   subtest_stats = (
       runs_df.groupby(["agent_model", "tier", "subtest"])
       .agg({"cost_usd": "mean", "score": "mean"})
       .reset_index()
   )
   ```

   - Groups by model, tier, and subtest
   - Computes mean cost and mean score for each subtest across all runs
   - Reduces run-level variance to focus on subtest-level trends

2. **Regression Analysis** (per model):

   ```python
   result = ols_regression(model_data["mean_cost"], model_data["mean_score"])
   ```

   - Fits `score = slope × cost + intercept` using OLS
   - Returns:
     - `slope`: Marginal quality improvement per dollar
     - `intercept`: Baseline quality at zero cost (theoretical)
     - `r_squared`: Proportion of variance explained by cost
     - `p_value`: Statistical significance of the slope
     - `std_err`: Standard error of slope estimate

3. **Regression Line Generation**:
   - Generates two points (min_cost, max_cost) per model
   - Computes predicted scores using fitted parameters
   - Creates line segments for overlay visualization

## Statistical Methods

### OLS Regression

**Implementation**: `scylla/analysis/stats.py:685-718` (`ols_regression`)

**Formula**:

```
y = β₁x + β₀

where:
  y = mean_score (dependent variable)
  x = mean_cost (independent variable)
  β₁ = slope (marginal return per dollar)
  β₀ = intercept (baseline quality)
```

**Diagnostics**:

- **R²** (Coefficient of Determination): Measures goodness-of-fit
  - R² ∈ [0, 1]
  - R² = 1: Perfect linear relationship
  - R² = 0: No linear relationship
  - R² < 0.3: Weak relationship (cost is not a strong predictor)
  - R² > 0.7: Strong relationship (cost explains most variance)

- **p-value**: Tests H₀: β₁ = 0 (slope is zero, no relationship)
  - p < 0.05: Reject H₀, slope is statistically significant
  - p ≥ 0.05: Fail to reject H₀, relationship may be spurious

- **Standard Error**: Quantifies uncertainty in slope estimate

### Dynamic Domain Calculation

**Implementation**: `scylla/analysis/figures/spec_builder.py:18-79` (`compute_dynamic_domain`)

Computes tight axis ranges by:

1. Finding min/max values across scatter points and regression line endpoints
2. Adding 10% padding for visual breathing room
3. Rounding to nearest 0.05 for clean axis labels
4. Clamping to [0.0, 1.0] for score axis

## Visualization Components

### 1. Scatter Plot (Subtest-Level Data Points)

**Mark**: `mark_circle(size=60, opacity=0.6)`

**Encodings**:

- **x-axis**: `mean_cost` (Mean Cost per Subtest, USD)
- **y-axis**: `mean_score` (Mean Score per Subtest, 0.0-1.0)
  - Uses dynamic domain to focus on actual data range
- **color**: `agent_model` (Model-specific colors from config)
- **tooltip**: Shows model, tier, subtest, formatted cost ($0.0000), formatted score (0.000)

**Visual Design**:

- Semi-transparent circles allow overlapping points to be visible
- Size 60 balances visibility with clutter avoidance

### 2. Regression Lines

**Mark**: `mark_line(strokeWidth=2)`

**Encodings**:

- **x**: Cost range (min_cost → max_cost for each model)
- **y**: Predicted score from OLS equation
- **color**: Matches model colors for visual consistency

**Purpose**: Shows the best-fit linear trend for each model's cost-quality relationship

### 3. R² and p-value Annotations

**Mark**: `mark_text(align="left", dx=10, dy=10, fontSize=11)`

**Format**: `"R² = {r_squared:.3f}, p = {p_value:.4f}"`

**Position**: Top-left corner of each facet (absolute positioning)

**Purpose**: Displays regression diagnostics directly on the chart for immediate interpretation

### 4. Faceting (Multi-Model Layout)

**Facet**: `row=alt.Row("agent_model:N")` (if multiple models present)

**Layout**: Vertical stacking of model-specific subplots

**Purpose**: Enables direct comparison of cost-quality efficiency across models

## Output Files

**Generated by**: `save_figure(chart, "fig21_cost_quality_regression", output_dir, render)`

**Outputs**:

1. **Vega-Lite Spec**: `fig21_cost_quality_regression.vl.json`
   - JSON specification for web rendering
   - Enables interactive tooltips and pan/zoom

2. **PNG Image**: `fig21_cost_quality_regression.png` (if `render=True`)
   - High-DPI raster format (3x scale = 300 DPI)
   - Suitable for presentations and web embedding

3. **PDF Vector**: `fig21_cost_quality_regression.pdf` (if requested)
   - Publication-quality vector format
   - Scales without loss of quality

4. **LaTeX Snippet**: `fig21_cost_quality_regression_include.tex` (if PDF rendered)
   - Ready-to-include LaTeX code for papers

## Interpretation Guidelines

### Strong Cost-Quality Relationship

- **High R²** (> 0.7) + **Low p-value** (< 0.05)
- **Interpretation**: Cost is a reliable predictor of quality
- **Implication**: Increasing investment yields predictable improvements
- **Action**: Focus on cost optimization to maximize quality within budget

### Weak or No Relationship

- **Low R²** (< 0.3) or **High p-value** (> 0.05)
- **Interpretation**: Cost does not explain quality variance
- **Implication**: Other factors (e.g., tier design, task difficulty) dominate quality
- **Action**: Investigate non-cost drivers of performance

### Slope Analysis

- **Steep slope**: High marginal return (e.g., +0.1 score per $0.01)
- **Shallow slope**: Low marginal return (e.g., +0.01 score per $0.01)
- **Negative slope**: Spending more reduces quality (likely spurious or confounded)

### Outlier Detection

- **Points far from regression line**: Unusually efficient or inefficient subtests
- **High residuals**: Investigate why cost did not predict quality for these cases
- **Clustering**: Groups of subtests with similar cost-quality profiles

## Related Figures

- **Fig 19 (Correlation Heatmap)**: Shows all pairwise correlations including cost-quality
- **Fig 20 (Cost vs Score Scatter)**: Run-level scatter without regression analysis
- **Fig 22 (Strategic Drift)**: Examines non-cost factors affecting consistency

## Dependencies

### Python Packages

- `pandas`: Data aggregation and manipulation
- `altair`: Declarative visualization (Vega-Lite wrapper)
- `statsmodels`: OLS regression (`OLS`, `add_constant`)

### Internal Modules

- `scylla.analysis.stats.ols_regression`: Regression fitting and diagnostics
- `scylla.analysis.figures.spec_builder.compute_dynamic_domain`: Axis range calculation
- `scylla.analysis.figures.spec_builder.save_figure`: Multi-format export
- `scylla.analysis.figures.get_color_scale`: Consistent color mapping

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.correlation import fig21_cost_quality_regression

# Load runs data
runs_df = pd.read_csv("data/runs.csv")

# Generate figure
output_dir = Path("output/figures")
fig21_cost_quality_regression(
    runs_df=runs_df,
    output_dir=output_dir,
    render=True  # Generate PNG images
)

# Outputs:
# - output/figures/fig21_cost_quality_regression.vl.json
# - output/figures/fig21_cost_quality_regression.png
```

## Design Rationale

### Why OLS Regression?

- **Simplicity**: Linear models are interpretable and widely understood
- **Diagnostics**: R² and p-values provide clear goodness-of-fit metrics
- **Baseline**: Establishes linear baseline before exploring nonlinear relationships

### Why Subtest-Level Aggregation?

- **Reduces noise**: Averaging across runs smooths out run-to-run variance
- **Focus on structure**: Emphasizes systematic cost-quality patterns
- **Balances granularity**: Finer than tier-level, coarser than run-level

### Why Facet by Model?

- **Avoids clutter**: Prevents overlapping regression lines in single plot
- **Enables comparison**: Easy to visually compare slopes and R² across models
- **Consistent scales**: Same x/y axes across facets ensure fair comparison

### Why Include Regression Diagnostics as Annotations?

- **Immediate context**: Viewers see statistical significance without consulting tables
- **Publication-ready**: No need for separate legend or footnote explaining significance
- **Transparency**: Shows both point estimates (slope) and uncertainty (R², p-value)
