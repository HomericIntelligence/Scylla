# Q-Q Plots for Normality

## Overview

Q-Q (Quantile-Quantile) plots visualize the normality of score distributions per (model, tier) by comparing theoretical quantiles from a standard normal distribution against observed quantiles from standardized scores. Points falling on the diagonal reference line indicate the data follows a normal distribution, while deviations reveal non-normality patterns.

**Key Insight**: Validates the assumption of normality required for parametric statistical tests, helping researchers choose appropriate analysis methods and identify distribution anomalies.

## Purpose

- **Primary Goal**: Assess whether score distributions approximate normal distributions for each (model, tier) combination
- **Use Cases**:
  - Validate normality assumptions before parametric tests (t-tests, ANOVA)
  - Identify skewness, heavy tails, or outliers in score distributions
  - Compare distribution shapes across models and tiers
  - Determine when non-parametric alternatives are needed
- **Audience**: Statisticians validating analysis assumptions, researchers interpreting significance tests

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `agent_model` (str): Model identifier (e.g., "claude-opus-4", "claude-sonnet-4")
- `tier` (str): Testing tier (T0-T6)
- `score` (float): Consensus score [0.0, 1.0]

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/diagnostics.py:20-159`

**Data Requirements**:

- Minimum 3 non-null scores per (model, tier) combination
- Typical dataset: 319 runs per (model, tier)
- Standardization requires mean and standard deviation (std > 0)

## Implementation Details

### Function Signature

```python
def fig23_qq_plots(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 23: Q-Q Plots (Quantile-Quantile).

    Q-Q plots per (model, tier) to assess normality.
    Compares theoretical quantiles (normal distribution) vs observed quantiles.
    Points should fall on diagonal line if data is normally distributed.

    Now generates separate figures per tier (fig23a-T0, fig23b-T1, etc.)
    for improved readability and analysis.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Per-Tier Splitting**:

- Generates separate figure for each tier
- **Rationale**: Enables focused per-tier normality assessment
- **Trade-off**: Multiple files vs. comprehensive cross-tier view
- **Benefit**: Avoids visual clutter from overlaying 7 tiers

**Standardization Method**:

- Observed scores standardized: `(score - mean) / std`
- **Rationale**: Makes observed quantiles comparable to standard normal theoretical quantiles
- **Edge Case**: If std = 0, uses raw scores (prevents division by zero)
- **Sensitivity**: Standardization removes location/scale, focuses on shape

**Theoretical Quantile Generation**:

- Uses `scipy.stats.norm.ppf()` with 99 evenly-spaced percentiles (0.01 to 0.99)
- **Rationale**: Avoids extreme quantiles (0.0, 1.0) which can be unstable
- **Benefit**: Matches number of theoretical quantiles to number of observed data points

**Reference Line Calculation**:

- Single diagonal line from `(q_min, q_min)` to `(q_max, q_max)`
- **Rationale**: Perfect normality = points lie on y = x line
- **Visual**: Red dashed line shared across both models for comparison

### Algorithm

1. **Data Collection**:

   ```python
   for model in sorted(runs_df["agent_model"].unique()):
       for tier in tier_order:
           tier_data = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)]
           scores = tier_data["score"].dropna().values
   ```

2. **Quantile Computation**:

   ```python
   # Theoretical quantiles (standard normal)
   theoretical_quantiles = stats.norm.ppf(np.linspace(0.01, 0.99, len(scores)))

   # Observed quantiles (sorted, standardized)
   observed_sorted = np.sort(scores)
   observed_mean = np.mean(scores)
   observed_std = np.std(scores)
   observed_quantiles = (observed_sorted - observed_mean) / observed_std
   ```

3. **Data Pairing**:

   ```python
   for theoretical_q, observed_q, original_score in zip(
       theoretical_quantiles, observed_quantiles, observed_sorted
   ):
       qq_data.append({
           "agent_model": model,
           "tier": tier,
           "theoretical_quantile": theoretical_q,
           "observed_quantile": observed_q,
           "original_score": original_score,
       })
   ```

4. **Per-Tier Chart Creation**:

   ```python
   for tier in tier_order:
       tier_qq_df = qq_df[qq_df["tier"] == tier]

       # Get extent for reference line
       q_min = min(tier_qq_df["theoretical_quantile"].min(),
                   tier_qq_df["observed_quantile"].min())
       q_max = max(tier_qq_df["theoretical_quantile"].max(),
                   tier_qq_df["observed_quantile"].max())
   ```

5. **Layered Visualization**:

   ```python
   chart = alt.layer(reference_line, scatter).properties(
       title=f"Q-Q Plots - {tier} (Normal Distribution Assessment)",
       width=400,
       height=350,
   )
   ```

6. **Save with Tier-Specific Filename**:

   ```python
   tier_suffix = tier.lower().replace(" ", "-")
   save_figure(chart, f"fig23_{tier_suffix}_qq_plots", output_dir, render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig23_{tier}_qq_plots.{ext}`

**Examples**:

- `fig23_t0_qq_plots.vl.json` - Vega-Lite specification
- `fig23_t0_qq_plots.csv` - Data slice (theoretical_quantile, observed_quantile pairs)
- `fig23_t0_qq_plots.png` - Rendered image (300 DPI, if render=True)
- `fig23_t0_qq_plots.pdf` - Vector format (if render=True)

**Tier Suffixes**:

- T0 → `t0`
- T1 → `t1`
- T2 → `t2`
- T3 → `t3`
- T4 → `t4`
- T5 → `t5`
- T6 → `t6`

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 4 files per tier × 7 tiers = 28 files (with rendering)

## Visual Specification

### Chart Components

**Chart Type**: Scatter plot with reference line

**Dimensions**:

- Width: 400px
- Height: 350px

**Layers**:

1. **Reference Line**: Red dashed diagonal (y = x)
   - `strokeDash=[5, 5]`, `strokeWidth=2`
   - Represents perfect normality
2. **Scatter Points**: Circular markers (size=60, opacity=0.7)
   - Color-coded by model
   - Each point = one (theoretical_q, observed_q) pair

**Axes**:

- **X-axis**: Theoretical Quantiles (Normal)
  - Standard normal quantiles
  - Scale: `zero=False` (auto-fit to data range)
- **Y-axis**: Observed Quantiles (Standardized Score)
  - Standardized observed scores
  - Scale: `zero=False` (auto-fit to data range)

**Color Encoding**:

- Domain: Model identifiers (sorted)
- Range: Dynamic color scale from `get_color_scale("models", models)`
- Legend: "Model"

**Tooltip**:

- Model (nominal)
- Tier (ordinal)
- Theoretical Q (quantitative, .2f)
- Observed Q (quantitative, .2f)
- Original Score (quantitative, .3f)

**Title**: "Q-Q Plots - {tier} (Normal Distribution Assessment)"

- Example: "Q-Q Plots - T0 (Normal Distribution Assessment)"

### Expected Patterns

**Perfect Normality**:

- All points fall exactly on red diagonal line
- No systematic deviations
- Rare in practice for real data

**Acceptable Normality**:

- Points cluster tightly around diagonal
- Minor scatter but no systematic pattern
- Deviations < 0.5 quantile units

**Problematic Patterns**:

- **S-curve**: Heavy tails (points curve away at extremes) → Leptokurtic distribution
- **Inverted S-curve**: Light tails (points curve inward at extremes) → Platykurtic distribution
- **Points above line**: Right skew (positive skew) → Long tail of high scores
- **Points below line**: Left skew (negative skew) → Long tail of low scores
- **Outliers**: Isolated points far from line → Extreme values or data errors

## Interpretation Guide

### Reading Q-Q Plots

**Diagonal Alignment**:

- Points on line → Data matches normal distribution
- Consistent offset → Location shift (mean difference)
- Steeper/shallower slope → Scale difference (std deviation)

**Systematic Deviations**:

- **Upper-right deviation**: Heavier right tail than normal
- **Lower-left deviation**: Heavier left tail than normal
- **S-curve**: Both tails heavier than normal (leptokurtic)
- **Inverted S**: Both tails lighter than normal (platykurtic)

**Quantile Interpretation**:

- **Theoretical Q = -2.0, Observed Q = -2.5**: Lower tail extends further than normal
- **Theoretical Q = 2.0, Observed Q = 1.5**: Upper tail less extreme than normal

### Statistical Implications

**When Points Follow Diagonal**:

- Parametric tests (t-test, ANOVA) valid
- Confidence intervals accurate
- Linear regression assumptions satisfied

**When Points Deviate Systematically**:

- Consider non-parametric alternatives (Mann-Whitney, Kruskal-Wallis)
- Apply transformations (log, square-root)
- Use robust statistical methods
- Increase sample size for central limit theorem

### Comparative Analysis

**Across Models**:

- Compare point patterns between models within same tier
- Identify which model produces more normal score distributions
- Expected: Both models show similar normality patterns if task difficulty is comparable

**Across Tiers**:

- Compare normality across T0-T6
- Expected: T0 may show more skew (low scores), T6 more normal (varied performance)
- Insight: Tier difficulty impacts distribution shape

### Action Items

**If Heavy Tails Detected**:

1. Investigate outlier runs (very high/low scores)
2. Check for data quality issues
3. Consider robust statistical methods (trimmed means, Winsorization)
4. Report median/IQR instead of mean/std

**If Skewness Detected**:

1. Apply transformation (e.g., logit for scores in [0,1])
2. Use non-parametric tests
3. Report skewness metric alongside analysis
4. Consider floor/ceiling effects in scoring

**If Non-Normality Confirmed**:

1. Explicitly document distribution shape
2. Justify choice of statistical methods
3. Consider bootstrap or permutation tests
4. Increase sample size if possible

## Related Figures

- **Fig 24** (`fig24_score_histograms`): Score histograms with KDE overlay
  - Complements Q-Q plots with visual distribution shape
  - Easier to spot bimodality and clustering
  - Shows raw frequency counts

- **Fig 01** (`fig01_score_variance_by_tier`): Score variance by tier
  - Provides variance metrics to contextualize Q-Q plot spread
  - Shows box plots for quartile comparison

- **Fig 17** (`fig17_judge_variance_overall`): Judge variance per tier
  - Related normality assessment for judge-level scores
  - Complements consensus-level Q-Q analysis

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.diagnostics import fig23_qq_plots
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig23_qq_plots(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig23_qq_plots(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig23_t0_qq_plots.vl.json
├── fig23_t0_qq_plots.csv
├── fig23_t0_qq_plots.png
├── fig23_t0_qq_plots.pdf
├── fig23_t1_qq_plots.vl.json
├── fig23_t1_qq_plots.csv
├── fig23_t1_qq_plots.png
├── fig23_t1_qq_plots.pdf
└── ... (T2-T6)
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig23_t0_qq_plots.vl.json
```

**CSV Data**:

```bash
# Inspect quantile pairs
head docs/figures/fig23_t0_qq_plots.csv
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig23_t0_qq_plots.png

# Include in LaTeX
\includegraphics{docs/figures/fig23_t0_qq_plots.pdf}
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #466
