# Score Histograms with KDE Overlay

## Overview

This figure visualizes the distribution of agent scores across testing tiers using histograms overlaid with Kernel Density Estimate (KDE) curves. The figure generates separate visualizations for each tier (T0-T6), showing how agent performance scores are distributed and enabling comparison across different agent models.

**Key Insight**: Reveals the shape of score distributions (normal, skewed, bimodal, multimodal) which indicates whether agents perform consistently or exhibit high variance, and helps identify tier-specific performance patterns.

## Purpose

- **Primary Goal**: Visualize the distribution of agent scores to understand performance patterns and variance
- **Use Cases**:
  - Identify distribution shapes (normal, skewed, bimodal) indicating performance consistency
  - Compare score distributions across agent models within each tier
  - Detect outlier performance patterns or unusual scoring clusters
  - Validate assumptions about score normality for statistical tests
  - Identify tier-specific performance characteristics (e.g., bimodal distributions in challenging tiers)
- **Audience**: Researchers analyzing agent performance patterns, experiment designers validating evaluation protocols, statisticians verifying distribution assumptions

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `tier` (str): Testing tier (T0-T6)
- `agent_model` (str): Agent model identifier (e.g., "opus-4.6", "sonnet-3.7")
- `score` (float): Agent score [0.0, 1.0]

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/diagnostics.py:161-284`

**Data Requirements**:

- One row per agent run
- Minimum 3 data points per (model, tier) combination for KDE computation
- Typical dataset: ~2,238 runs across all tiers and models
- Score values must be in range [0.0, 1.0]

## Mathematical Formulas

### Histogram Binning

**Bin Configuration**:

```
Number of bins: maxbins = 20
Bin width: Δx ≈ (max(score) - min(score)) / 20 ≈ 1.0 / 20 = 0.05
```

**Frequency Calculation**:

```
Frequency(bin_i) = count({score ∈ runs_df | bin_i.lower ≤ score < bin_i.upper})
```

### Kernel Density Estimation (KDE)

**Gaussian KDE**:

```
f̂(x) = (1/n) Σᵢ₌₁ⁿ K((x - xᵢ)/h)

where:
- f̂(x) = estimated probability density at point x
- n = number of data points
- K = Gaussian kernel function: K(u) = (1/√(2π)) exp(-u²/2)
- h = bandwidth (automatically selected via Scott's rule or Silverman's rule)
- xᵢ = individual score observations
```

**Scott's Bandwidth Rule** (default in scipy.stats.gaussian_kde):

```
h = n^(-1/(d+4)) * σ̂

where:
- d = 1 (dimensionality, since score is univariate)
- σ̂ = sample standard deviation of scores
```

**Evaluation Grid**:

```
x_range = linspace(0, 1, 100)  # 100 points uniformly spaced [0, 1]
density = kde(x_range)         # Evaluate KDE at each point
```

### KDE Scaling for Visualization

To align KDE curves with histogram frequencies:

```
scaled_density_model = density_model * (count_model / max(density_model))

where:
- count_model = total number of scores for the given model
- max(density_model) = maximum density value for the model's KDE
```

This ensures the KDE curve's peak height matches the histogram's maximum frequency for each model.

## Theoretical Foundation

### Distribution Shapes and Interpretation

**Normal (Gaussian) Distribution**:

- **Shape**: Symmetric bell curve centered around mean
- **Interpretation**: Agents perform consistently with predictable variance
- **Expected**: In tiers where agents have uniform capability (e.g., T0 baseline)
- **Statistical Properties**: Mean ≈ median ≈ mode

**Skewed Distributions**:

- **Right-skewed (positive skew)**: Long tail toward high scores
  - Interpretation: Most agents struggle, few excel
  - Expected: In very difficult tiers or with under-powered models
- **Left-skewed (negative skew)**: Long tail toward low scores
  - Interpretation: Most agents succeed, few fail
  - Expected: In easy tiers or with over-powered models

**Bimodal Distribution**:

- **Shape**: Two distinct peaks
- **Interpretation**: Two sub-populations with different performance levels
- **Possible Causes**:
  - Task difficulty variation (some runs much harder than others)
  - Model architecture differences creating capability gaps
  - Binary success/failure outcomes (score ≈ 0 or score ≈ 1)

**Multimodal Distribution**:

- **Shape**: Three or more distinct peaks
- **Interpretation**: Multiple performance clusters or scoring regimes
- **Possible Causes**:
  - Heterogeneous task set with distinct difficulty levels
  - Different agent strategies leading to clustered outcomes

**Uniform Distribution**:

- **Shape**: Flat, no clear peak
- **Interpretation**: High variance, no consistent performance pattern
- **Concern**: May indicate random behavior, poorly calibrated tasks, or measurement noise

### Central Tendency and Spread

**Central Tendency Metrics**:

- **Mean**: μ = (1/n) Σᵢ xᵢ
  - Sensitive to outliers
- **Median**: 50th percentile
  - Robust to outliers
- **Mode**: Peak of distribution (where KDE is maximum)
  - Most common score range

**Spread Metrics**:

- **Standard Deviation**: σ = sqrt((1/n) Σᵢ (xᵢ - μ)²)
  - Measure of overall variance
- **Interquartile Range (IQR)**: Q3 - Q1
  - Robust measure of spread
- **Range**: max(scores) - min(scores)
  - Sensitive to outliers

## Visualization Details

### Chart Components

**Chart Type**: Layered histogram with KDE overlay

**Histogram Layer**:

- Mark: Bar chart with binned continuous variable
- Opacity: 0.5 (semi-transparent for overlay visibility)
- Bin spacing: 0 (adjacent bars touch)
- Bin count: maxbins=20

**KDE Layer**:

- Mark: Line chart (strokeWidth=2)
- Computed over 100 evaluation points [0, 1]
- Scaled to match histogram frequency range
- Only rendered if ≥3 data points available per (model, tier)

**Dimensions**:

- Width: 600px
- Height: 400px

**Axes**:

- **X-axis**: Score (continuous, 0.0-1.0)
  - Title: "Score"
  - Binned with maxbins=20 for histogram
- **Y-axis**: Frequency (discrete, auto-scaled)
  - Title: "Frequency"
  - Represents count of runs in each bin (histogram) or scaled density (KDE)

**Color Encoding**:

- **Dimension**: Agent Model
- **Scale**: Dynamic color scale via `get_color_scale("models", models)`
- **Purpose**: Distinguish distributions across different agent models

**Tooltip** (Histogram bars only):

- Model name
- Count in bin

**Title**: "Score Distribution - {tier} (with KDE Overlay)"

- Example: "Score Distribution - T0 (with KDE Overlay)"

### Per-Tier Output Strategy

**Rationale for Separate Figures**:

- Avoids Altair's 5,000-row visualization limit
- Improves readability by focusing on one tier at a time
- Enables detailed per-tier analysis without data truncation
- Facilitates side-by-side tier comparisons

**Filename Pattern**: `fig24_{tier}_score_histogram.{ext}`

**Examples**:

- `fig24_t0_score_histogram.vl.json`
- `fig24_t1_score_histogram.vl.json`
- `fig24_t2_score_histogram.vl.json`

## Interpretation Guidelines

### Identifying Distribution Patterns

**Step 1: Assess Overall Shape**

- Look at KDE curve for smooth representation of distribution
- Identify number of modes (peaks):
  - Unimodal: Single peak (expected for most tiers)
  - Bimodal: Two peaks (investigate cause)
  - Multimodal: Multiple peaks (flag for review)

**Step 2: Check Symmetry**

- Compare left and right tails of distribution
- Determine skewness direction:
  - Symmetric: Balanced performance
  - Right-skewed: Many low scores, few high scores
  - Left-skewed: Many high scores, few low scores

**Step 3: Evaluate Spread**

- Examine histogram bar heights and KDE curve width
- Wide spread (σ > 0.3): High variance, inconsistent performance
- Narrow spread (σ < 0.15): Consistent performance

**Step 4: Identify Outliers**

- Look for isolated bars far from main distribution
- Check for extreme scores (near 0.0 or 1.0)
- Investigate causes of outlier runs

### Expected Patterns by Tier

**T0 (Baseline - Minimal Capabilities)**:

- Expected: Right-skewed or bimodal with peak near 0.0
- Agents struggle with limited tools/prompts
- High failure rate → concentration at low scores

**T1-T2 (Early Capabilities)**:

- Expected: Broad distribution, possibly bimodal
- Some tasks become solvable, others remain difficult
- Transition from failure to partial success

**T3-T4 (Mid-Range Capabilities)**:

- Expected: Normal or slight left-skew
- Most agents perform adequately
- Peak shifts toward higher scores (0.6-0.8)

**T5-T6 (Advanced Capabilities)**:

- Expected: Left-skewed with peak near 1.0
- Agents have sufficient capabilities for most tasks
- Concentration at high scores, few failures

### Anomaly Detection

**Red Flags**:

1. **Uniform distribution**: No clear performance pattern → review task calibration
2. **Spike at 0.0 or 1.0**: Binary outcomes → check scoring rubric for all-or-nothing criteria
3. **Bimodal in unexpected tiers**: Investigate task heterogeneity or model differences
4. **Gaps in distribution**: Missing score ranges → potential scoring bias or limited task coverage
5. **High variance across models**: Inconsistent model capabilities → review model selection

**Investigation Steps**:

1. Cross-reference with Fig 23 (QQ plots) to check normality assumptions
2. Review individual run logs for outlier scores
3. Check task characteristics for distribution-influencing factors
4. Validate judge scoring consistency (Fig 02)

## Related Figures

- **Fig 23** (`fig23_score_qq_plots`): Q-Q plots for normality testing
  - Complements histogram with formal normality assessment
  - Reveals deviations from theoretical normal distribution
  - Useful for validating statistical test assumptions

- **Fig 01** (`fig01_score_variance_by_tier`): Score variance by tier
  - Shows aggregate variance metrics across tiers
  - Provides quantitative complement to visual distribution analysis

- **Fig 25** (`fig25_score_boxplots`): Score box plots per tier
  - Alternative visualization showing quartiles and outliers
  - Easier to compare central tendency and spread across models

## Code Reference

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/diagnostics.py:161-284`

**Function Signature**:

```python
def fig24_score_histograms(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 24: Score Histograms with KDE Overlay.

    Histograms with kernel density estimate (KDE) overlay.
    Generates separate figures per tier for improved readability.

    Args:
        runs_df: Runs DataFrame with columns [tier, agent_model, score]
        output_dir: Output directory for saved figures
        render: Whether to render to PNG/PDF (default: True)
    """
```

**Key Implementation Steps**:

1. **Derive Tier Order**:

   ```python
   tier_order = derive_tier_order(runs_df)
   ```

2. **Compute KDE Per (Model, Tier)**:

   ```python
   for model in sorted(runs_df["agent_model"].unique()):
       for tier in tier_order:
           tier_data = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)]
           if len(tier_data) < 3:
               continue
           scores = tier_data["score"].dropna().values

           kde = stats.gaussian_kde(scores)
           x_range = np.linspace(0, 1, 100)
           kde_values = kde(x_range)
   ```

3. **Create Histogram**:

   ```python
   histogram = (
       alt.Chart(tier_runs_df)
       .mark_bar(opacity=0.5, binSpacing=0)
       .encode(
           x=alt.X("score:Q", title="Score", bin=alt.Bin(maxbins=20)),
           y=alt.Y("count():Q", title="Frequency"),
           color=alt.Color("agent_model:N", title="Agent Model"),
       )
   )
   ```

4. **Create KDE Overlay**:

   ```python
   kde_lines = (
       alt.Chart(tier_kde_df)
       .mark_line(strokeWidth=2)
       .encode(
           x=alt.X("score:Q"),
           y=alt.Y("scaled_density:Q"),
           color=alt.Color("agent_model:N"),
       )
   )
   ```

5. **Layer Charts**:

   ```python
   chart = alt.layer(histogram, kde_lines, data=tier_runs_df)
   ```

6. **Save Per-Tier**:

   ```python
   tier_suffix = tier.lower().replace(" ", "-")
   save_figure(chart, f"fig24_{tier_suffix}_score_histogram", output_dir, render)
   ```

**Error Handling**:

- Skips (model, tier) combinations with < 3 data points (insufficient for KDE)
- Catches KDE computation failures and logs warnings
- Gracefully handles tiers with zero data

**Dependencies**:

- `pandas`: DataFrame operations
- `numpy`: Numerical computations (linspace)
- `scipy.stats.gaussian_kde`: Kernel density estimation
- `altair`: Visualization library
- `scylla.analysis.figures.utils`: Helper functions (derive_tier_order, get_color_scale, save_figure)

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.diagnostics import fig24_score_histograms
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig24_score_histograms(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig24_score_histograms(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig24_t0_score_histogram.vl.json
├── fig24_t0_score_histogram.csv
├── fig24_t0_score_histogram.png
├── fig24_t0_score_histogram.pdf
├── fig24_t1_score_histogram.vl.json
├── fig24_t1_score_histogram.csv
├── fig24_t1_score_histogram.png
├── fig24_t1_score_histogram.pdf
└── ... (T2-T6)
```

**Total Files**: 4 files per tier × 7 tiers = 28 files (with render=True)

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig24_t0_score_histogram.vl.json
```

**CSV Data**:

```bash
# Inspect raw data
head docs/figures/fig24_t0_score_histogram.csv
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig24_t0_score_histogram.png

# Include in LaTeX
\includegraphics{docs/figures/fig24_t0_score_histogram.pdf}
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #467
