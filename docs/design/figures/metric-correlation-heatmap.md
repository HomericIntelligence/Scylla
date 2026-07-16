# Metric Correlation Heatmap

## Overview

The Metric Correlation Heatmap visualizes pairwise Spearman rank correlations between key performance metrics across agent runs. This figure reveals relationships between quality (score), economic (cost), and process (tokens, duration) dimensions, helping identify trade-offs and dependencies in agent performance.

**Key Insight**: Exposes whether quality improvements come at the cost of higher expenses, or if certain metrics move together (e.g., tokens and duration), informing optimization strategies and resource allocation decisions.

## Purpose

- **Primary Goal**: Quantify and visualize correlation strength between score, cost, tokens, and duration metrics
- **Use Cases**:
  - Identify quality-cost trade-offs across different agent architectures
  - Detect collinearity between metrics (e.g., tokens vs. duration)
  - Validate metric independence for multi-objective optimization
  - Inform metric selection for pareto frontier analysis
  - Support cost-benefit analysis for tier comparisons
- **Audience**: Researchers analyzing agent performance trade-offs, experiment designers optimizing evaluation metrics, stakeholders evaluating cost-effectiveness

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `agent_model` (str): Agent model name (e.g., "Sonnet 4.5", "Haiku 4.5")
- `score` (float): Consensus score from judge evaluations [0.0, 1.0]
- `cost_usd` (float): Total cost in USD for the run
- `total_tokens` (int): Total tokens consumed (input + output + cached)
- `duration_seconds` (float): Total execution time in seconds

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/correlation.py:19-134`

**Data Requirements**:

- One row per agent run
- Typical dataset: ~2,238 runs across multiple tiers and models
- Minimum 3 runs per model required for correlation analysis (enforced by `config.min_sample_correlation`)
- Missing values automatically excluded via pairwise deletion

## Implementation Details

### Function Signature

```python
def fig20_metric_correlation_heatmap(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 20: Metric Correlation Heatmap.

    Spearman correlation heatmap of score, cost, tokens, duration.
    Annotated with coefficients. Faceted by model.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Spearman vs. Pearson Correlation**:

- Uses Spearman rank correlation (`spearman_correlation()` from `scylla.analysis.stats`)
- **Rationale**: Robust to non-linear monotonic relationships and outliers
- **Trade-off**: Captures rank-order relationships, not linear relationships
- **Benefit**: More appropriate for skewed distributions (e.g., cost data)

**Holm-Bonferroni Correction**:

- Applies `holm_bonferroni_correction()` to control family-wise error rate (FWER)
- **Rationale**: Multiple pairwise tests increase Type I error risk
- **Correction Method**: Step-down procedure, less conservative than standard Bonferroni
- **Significance Threshold**: Corrected p-value < 0.05
- **Benefit**: Valid statistical inference across all metric pairs

**Per-Model Analysis**:

- Computes separate correlation matrices for each agent model
- **Rationale**: Different models may exhibit different trade-off profiles
- **Implementation**: Faceted visualization with shared scales
- **Benefit**: Enables model-specific correlation pattern comparison

**Pairwise Deletion for Missing Data**:

- Uses index alignment to handle missing values
- **Implementation**: `common_idx = data1.index.intersection(data2.index)`
- **Benefit**: Maximizes sample size for each correlation pair

**Centralized Metric Configuration**:

- Metrics sourced from `config.correlation_metrics` (defined in `scylla/analysis/config.yaml`)
- Default metrics: `score`, `cost_usd`, `total_tokens`, `duration_seconds`
- **Benefit**: Consistent metric selection across analyses, easy to extend

### Algorithm

1. **Load Metric Configuration**:

   ```python
   metrics = config.correlation_metrics
   # metrics = {"score": "Score", "cost_usd": "Cost (USD)", ...}
   ```

2. **Per-Model Iteration**:

   ```python
   for model in sorted(runs_df["agent_model"].unique()):
       model_data = runs_df[runs_df["agent_model"] == model]
   ```

3. **Pairwise Correlation Computation**:

   ```python
   for metric1_col, metric1_name in metrics.items():
       for metric2_col, metric2_name in metrics.items():
           # Align on common indices (pairwise deletion)
           common_idx = data1.index.intersection(data2.index)
           if len(common_idx) < 3:
               continue

           # Compute Spearman correlation
           rho, p_value = spearman_correlation(
               model_data.loc[common_idx, metric1_col],
               model_data.loc[common_idx, metric2_col],
           )
   ```

4. **Multiple Comparison Correction**:

   ```python
   raw_p_values = corr_df["p_value"].tolist()
   corrected_p_values = holm_bonferroni_correction(raw_p_values)
   corr_df["p_value_corrected"] = corrected_p_values
   corr_df["significant"] = corr_df["p_value_corrected"] < 0.05
   ```

5. **Heatmap Construction**:

   ```python
   heatmap = (
       alt.Chart(corr_df)
       .mark_rect()
       .encode(
           x=alt.X("metric1:O", title="", sort=list(metrics.values())),
           y=alt.Y("metric2:O", title="", sort=list(metrics.values())),
           color=alt.Color(
               "rho:Q",
               title="Spearman ρ",
               scale=alt.Scale(domain=[-1, 1], scheme="blueorange"),
           ),
       )
   )
   ```

6. **Text Annotation Overlay**:

   ```python
   text = (
       alt.Chart(corr_df)
       .mark_text(baseline="middle", fontSize=7)
       .encode(
           x=alt.X("metric1:O", sort=list(metrics.values())),
           y=alt.Y("metric2:O", sort=list(metrics.values())),
           text="label:N",  # Formatted as "{rho:.2f}"
           color=alt.value("black"),
       )
   )
   ```

7. **Faceting and Finalization**:

   ```python
   if corr_df["agent_model"].nunique() > 1:
       chart = (
           alt.layer(heatmap, text)
           .facet(column=alt.Column("agent_model:N", title="Agent Model"))
           .properties(title="Metric Correlation Heatmap (Spearman ρ)")
           .configure_view(strokeWidth=0)
       )
   ```

8. **Save Output**:

   ```python
   save_figure(chart, "fig20_metric_correlation_heatmap", output_dir, render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig20_metric_correlation_heatmap.{ext}`

**Generated Files**:

- `fig20_metric_correlation_heatmap.vl.json` - Vega-Lite specification (version control)
- `fig20_metric_correlation_heatmap.csv` - Correlation data (all metric pairs, all models)
- `fig20_metric_correlation_heatmap.png` - Rendered image (300 DPI, if render=True)
- `fig20_metric_correlation_heatmap.pdf` - Vector format (if render=True)

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 4 files (single multi-faceted figure)

### CSV Data Structure

**Columns**:

- `agent_model`: Model name
- `metric1`: First metric display name
- `metric2`: Second metric display name
- `rho`: Spearman correlation coefficient [-1.0, 1.0]
- `p_value`: Raw p-value from Spearman test
- `p_value_corrected`: Holm-Bonferroni corrected p-value
- `significant`: Boolean (corrected p-value < 0.05)
- `label`: Formatted string for display (e.g., "0.45")

## Visual Specification

### Chart Components

**Chart Type**: Heatmap with text annotations (layered composition)

**Dimensions**:

- Width: Auto-sized based on metric count and facet columns
- Height: Auto-sized to maintain square cells

**Faceting**:

- **Column**: Agent model (if multiple models present)
- **Shared Scales**: Color scale consistent across facets
- **Title**: "Metric Correlation Heatmap (Spearman ρ)"

**Axes**:

- **X-axis**: Metric 1 (ordinal, sorted by config order)
  - No axis title (labels are self-explanatory)
  - Labels: "Score", "Cost (USD)", "Total Tokens", "Duration (s)"
- **Y-axis**: Metric 2 (ordinal, same sort order as X)
  - No axis title
  - Labels: Same as X-axis

**Color Encoding**:

- **Variable**: Spearman ρ (rho)
- **Scale**: Diverging color scheme (`blueorange`)
  - Blue: Negative correlation (-1)
  - White/neutral: No correlation (0)
  - Orange: Positive correlation (+1)
- **Domain**: [-1.0, 1.0] (fixed for cross-model comparison)

**Text Annotations**:

- **Content**: Correlation coefficient formatted as "{rho:.2f}"
- **Font Size**: 7pt (30% reduction from default for readability)
- **Color**: Black (constant, not data-driven)
- **Alignment**: Center-middle within each cell

**Tooltip** (interactive in browser):

- Metric 1: First metric name
- Metric 2: Second metric name
- Spearman ρ: Correlation coefficient (3 decimal places)
- p-value: Raw p-value (4 decimal places)

### Expected Patterns

**Diagonal Cells** (metric vs. itself):

- **Value**: ρ = 1.00 (perfect correlation)
- **Color**: Deep orange
- **Interpretation**: Self-correlation baseline

**Cost vs. Tokens**:

- **Expected**: Strong positive correlation (ρ > 0.7)
- **Interpretation**: More tokens → higher cost (API pricing model)

**Tokens vs. Duration**:

- **Expected**: Moderate to strong positive (ρ > 0.5)
- **Interpretation**: More tokens → longer processing time

**Score vs. Cost**:

- **Expected**: Weak to moderate positive (ρ = 0.2 to 0.5)
- **Interpretation**: Quality gains may require more expensive architectures
- **Alternative**: Negative correlation suggests inefficiency

**Score vs. Duration**:

- **Expected**: Weak correlation (ρ < 0.3)
- **Interpretation**: Quality improvements don't necessarily require longer runs

**Symmetric Matrix**:

- Correlation matrix is symmetric: `corr(A, B) = corr(B, A)`
- Heatmap displays full matrix (not just upper/lower triangle)

## Interpretation Guide

### Reading the Heatmap

**Color Intensity**:

- **Deep blue/orange**: Strong correlation (|ρ| > 0.7)
- **Light blue/orange**: Moderate correlation (0.3 < |ρ| < 0.7)
- **White/pale**: Weak correlation (|ρ| < 0.3)

**Sign Interpretation**:

- **Positive (orange)**: Metrics increase together
- **Negative (blue)**: Metrics move in opposite directions

**Statistical Significance**:

- Check `significant` column in CSV for Holm-Bonferroni corrected significance
- Non-significant correlations may be spurious (sampling noise)

### Key Trade-Off Patterns

**Quality-Cost Trade-Off** (Score vs. Cost):

- **Positive ρ**: Higher quality requires higher investment
  - Supports tier progression hypothesis (T0 → T6)
  - Justifies cost-benefit analysis for tier selection
- **Negative ρ**: Inefficiencies present (higher cost, lower quality)
  - Investigate poorly performing configurations
  - Candidate for ablation or removal

**Efficiency Frontier** (Score vs. Duration):

- **Weak ρ**: Quality gains possible without latency increase
  - Opportunity for optimization
  - Parallel processing or caching may help
- **Strong positive ρ**: Quality requires compute time
  - Trade-off inherent to architecture
  - Consider latency constraints for deployment

**Resource Utilization** (Tokens vs. Cost, Tokens vs. Duration):

- **Expected strong positive**: Validates token-based cost model
- **Deviation**: Investigate caching effects or pricing anomalies

### Comparative Analysis

**Across Models** (faceted panels):

- Compare correlation structures between models
- **Divergence**: Different models have different trade-off profiles
  - Example: Haiku may show weaker Score-Cost correlation (better efficiency)
- **Convergence**: Universal constraints (tokens always correlate with cost)

**Validation Checks**:

- Diagonal should be all 1.00 (self-correlation)
- Matrix should be symmetric
- Token-Cost correlation should be strong (validates pricing model)

### Action Items

**If Strong Score-Cost Correlation (ρ > 0.7)**:

1. Confirm tier progression justifies cost increases
2. Compute cost-effectiveness (CoP) for pareto analysis
3. Identify diminishing returns threshold

**If Weak Score-Cost Correlation (ρ < 0.3)**:

1. Investigate inefficiencies in higher tiers
2. Check for confounding variables (task difficulty)
3. Consider tier re-design or skill optimization

**If Tokens-Duration Weak (ρ < 0.5)**:

1. Check for I/O bottlenecks or network latency
2. Investigate batching or parallelization opportunities
3. Validate timestamp accuracy in duration measurements

**If Unexpected Negative Correlations**:

1. Investigate data quality issues
2. Check for tier-specific anomalies
3. Validate metric calculation logic

## Related Figures

- **Fig 21** (`fig21_cost_quality_regression`): OLS regression of cost vs. quality
  - Quantifies Score-Cost relationship with R² and trend line
  - Provides predictive model for cost given quality target
  - Complements heatmap with directional relationship

- **Fig 09** (`fig09_cost_distribution`): Per-tier cost distribution box plots
  - Shows cost variability within tiers
  - Complements correlation analysis with distributional context

- **Fig 15** (`fig15_token_distribution_by_tier`): Token distribution by tier
  - Visualizes token consumption patterns
  - Helps interpret Tokens-Cost correlation

- **Fig 12** (`fig12_pass_rate_vs_cost`): Pass-rate vs. cost scatter plot
  - Related quality-cost analysis at pass/fail threshold
  - Alternative view using binary quality metric

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.correlation import fig20_metric_correlation_heatmap
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig20_metric_correlation_heatmap(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig20_metric_correlation_heatmap(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig20_metric_correlation_heatmap.vl.json
├── fig20_metric_correlation_heatmap.csv
├── fig20_metric_correlation_heatmap.png
└── fig20_metric_correlation_heatmap.pdf
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig20_metric_correlation_heatmap.vl.json
```

**CSV Data**:

```bash
# Inspect correlation coefficients
head docs/figures/fig20_metric_correlation_heatmap.csv

# Filter significant correlations
awk -F',' '$7 == "True"' docs/figures/fig20_metric_correlation_heatmap.csv
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig20_metric_correlation_heatmap.png

# Include in LaTeX
\includegraphics{docs/figures/fig20_metric_correlation_heatmap.pdf}
```

### Customizing Metrics

**Edit Configuration** (`scylla/analysis/config.yaml`):

```yaml
figures:
  correlation_metrics:
    score: "Score"
    cost_usd: "Cost (USD)"
    total_tokens: "Total Tokens"
    duration_seconds: "Duration (s)"
    # Add custom metrics:
    cache_hit_rate: "Cache Hit Rate"
```

**Benefits**:

- No code changes required
- Automatic propagation to heatmap
- Centralized metric definitions

## Changelog

- **2026-02-12**: Initial documentation created for issue #464
