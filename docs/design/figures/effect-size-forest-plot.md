# Effect Size Forest Plot

## Overview

Effect Size Forest Plot visualizes Cliff's delta effect sizes with 95% confidence intervals for consecutive tier transitions. This figure reveals the magnitude and significance of performance improvements between tiers, helping identify which transitions provide meaningful capability gains.

**Key Insight**: Confidence intervals that exclude zero indicate statistically significant improvements, while the magnitude of Cliff's delta reveals practical significance of tier transitions.

## Purpose

- **Primary Goal**: Quantify the effect size of tier transitions to distinguish meaningful improvements from noise
- **Use Cases**:
  - Identify which tier transitions provide significant capability gains
  - Assess practical significance beyond statistical significance
  - Compare effect sizes across different agent models
  - Prioritize tier investments based on impact magnitude
- **Audience**: Researchers evaluating tier effectiveness, experiment designers optimizing agent architectures

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `tier` (str): Testing tier (T0-T6)
- `agent_model` (str): Agent model identifier
- `passed` (bool): Binary pass/fail outcome

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/effect_size.py:18-150`

**Data Requirements**:

- One row per experimental run
- At least two tiers with data for comparison
- Minimum sample size: 2 runs per tier per model (for CI calculation)
- Typical dataset: ~2,000+ runs across 7 tiers and multiple models

## Implementation Details

### Function Signature

```python
def fig19_effect_size_forest(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 19: Effect Size Forest Plot.

    Horizontal dot plot with error bars showing Cliff's delta + 95% CI
    for each tier transition. Vertical dashed line at delta=0.
    Color indicates significance.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Cliff's Delta Selection**:

- Non-parametric effect size measure
- **Rationale**: Binary pass/fail data violates normality assumptions for Cohen's d
- **Interpretation**: δ ∈ [-1, 1] where |δ| represents probability of superiority
- **Benefits**: Robust to outliers, no distributional assumptions, intuitive interpretation

**Bootstrap Confidence Intervals**:

- Method: BCa (bias-corrected and accelerated)
- Resamples: 10,000 by default
- Confidence level: 95%
- **Rationale**: BCa provides better coverage for binary data near boundaries
- **Trade-off**: Computational cost (~1-2 seconds per transition) vs. accuracy

**Consecutive Tier Transitions**:

- Only compares adjacent tiers (T0→T1, T1→T2, etc.)
- **Rationale**: Isolates incremental effects of each architectural change
- **Alternative**: All pairwise comparisons would conflate multiple changes
- **Benefit**: Clean attribution of effects to specific tier additions

**Significance Visualization**:

- Color coding: Gray (non-significant), Red (significant)
- **Criterion**: CI excludes zero (CI_low > 0 or CI_high < 0)
- **Rationale**: Visual distinction between statistical and non-statistical effects
- **Trade-off**: Emphasizes p-value threshold over effect magnitude

### Algorithm

1. **Tier Order Derivation**:

   ```python
   tier_order = derive_tier_order(runs_df)  # e.g., ["T0", "T1", "T2", ...]
   ```

2. **Model-Stratified Analysis**:

   ```python
   for model in sorted(runs_df["agent_model"].unique()):
       model_runs = runs_df[runs_df["agent_model"] == model]
   ```

3. **Consecutive Tier Comparisons**:

   ```python
   for i in range(len(tier_order) - 1):
       tier1, tier2 = tier_order[i], tier_order[i + 1]
       tier1_data = model_runs[model_runs["tier"] == tier1]
       tier2_data = model_runs[model_runs["tier"] == tier2]
   ```

4. **Effect Size Calculation**:

   ```python
   delta, ci_low, ci_high = cliffs_delta_ci(
       tier2_data["passed"].astype(int),
       tier1_data["passed"].astype(int),
       confidence=0.95,
       n_resamples=10000,
   )
   ```

   - **Note**: `tier2` is group1, `tier1` is group2
   - Positive delta → tier2 outperforms tier1
   - Uses vectorized numpy operations for performance

5. **Significance Determination**:

   ```python
   is_significant = not (ci_low <= 0 <= ci_high)
   ```

   - Significant if CI excludes zero
   - Two-tailed test (detects both improvements and regressions)

6. **Chart Construction**:
   - **Points**: Circle marks at delta value
   - **Error bars**: Horizontal bars from ci_low to ci_high
   - **Zero line**: Vertical dashed line at delta=0 (null effect)
   - **Faceting**: Separate rows for each agent model (if multiple models)

7. **Save Output**:

   ```python
   save_figure(chart, "fig19_effect_size_forest", output_dir, render)
   ```

### Statistical Foundation

**Cliff's Delta Formula**:

```
δ = (# pairs where x₂ > x₁) - (# pairs where x₂ < x₁) / (n₁ × n₂)
```

- Where x₁ ∈ tier1, x₂ ∈ tier2
- Vectorized implementation: `np.sign(g1[:, None] - g2[None, :]).sum() / (n1 * n2)`

**Interpretation Thresholds** (Romano et al., 2006):

- |δ| < 0.11: Negligible effect
- |δ| < 0.28: Small effect
- |δ| < 0.43: Medium effect
- |δ| ≥ 0.43: Large effect

**Bootstrap CI Algorithm**:

1. Resample tier1 and tier2 independently with replacement
2. Compute Cliff's delta for each resample
3. Apply BCa correction for bias and skewness
4. Extract 2.5th and 97.5th percentiles

## Output Files

### File Naming Convention

**Pattern**: `fig19_effect_size_forest.{ext}`

**Files**:

- `fig19_effect_size_forest.vl.json` - Vega-Lite specification
- `fig19_effect_size_forest.csv` - Effect size data
- `fig19_effect_size_forest.png` - Rendered image (300 DPI, if render=True)
- `fig19_effect_size_forest.pdf` - Vector format (if render=True)

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 4 files (single figure for all models)

## Visual Specification

### Chart Components

**Chart Type**: Forest plot (horizontal dot plot with error bars)

**Layout**:

- **Single model**: Layered chart (zero line + error bars + points)
- **Multiple models**: Faceted by row (one row per model)

**Axes**:

- **X-axis**: Cliff's Delta (continuous, -1.0 to 1.0)
  - Domain: [-1, 1] (fixed scale for cross-model comparison)
  - Title: "Cliff's Delta (Effect Size)"
- **Y-axis**: Tier Transition (ordinal, sorted by tier order)
  - Values: "T0→T1", "T1→T2", ..., "T5→T6"
  - Title: "Tier Transition"

**Marks**:

- **Points**: Circle marks (size=100)
  - Position: (delta, transition)
  - Color: Gray (non-significant) or Red (significant)
- **Error bars**: Horizontal bars
  - Extent: ci_low to ci_high
  - Color: Matches point color
- **Zero line**: Vertical dashed rule
  - Position: x=0
  - Style: Black, strokeDash=[5, 5]

**Color Scheme**:

- Non-significant: #999999 (gray)
- Significant: #d62728 (red)

**Title**: "Effect Size Forest Plot (Cliff's Delta with 95% CI)"

**Tooltip** (interactive):

- Model: {agent_model}
- Transition: {tier1}→{tier2}
- Cliff's δ: {delta} (formatted to 3 decimals)
- 95% CI Low: {ci_low}
- 95% CI High: {ci_high}
- Significant: Yes/No

### Expected Patterns

**Ideal Progression**:

- Positive deltas for all transitions (monotonic improvement)
- Larger effects for early tiers (T0→T1, T1→T2)
- Diminishing returns in later tiers (T4→T5, T5→T6)
- Most CIs exclude zero (significant improvements)

**Problematic Patterns**:

- Negative deltas → Tier regression (higher tier performs worse)
- CIs crossing zero → Unreliable or negligible improvements
- Inconsistent effects across models → Model-specific tier benefits
- Flat progression → Architectural changes provide no value

## Interpretation Guide

### Reading the Forest Plot

**Horizontal Position**:

- **Right of zero** (δ > 0): Tier2 outperforms Tier1
- **Left of zero** (δ < 0): Tier1 outperforms Tier2 (regression)
- **At zero** (δ ≈ 0): No meaningful difference

**Error Bar Width**:

- **Narrow CI**: Precise effect estimate, high confidence
- **Wide CI**: Uncertain effect, low sample size or high variance
- **CI excludes zero**: Statistically significant effect
- **CI includes zero**: Non-significant, cannot rule out null

**Color Coding**:

- **Red**: Significant improvement (CI excludes zero)
- **Gray**: Non-significant (CI includes zero)

### Effect Size Magnitude

**Negligible** (|δ| < 0.11):

- Minimal practical difference
- Tier investment may not be justified
- Example: T4→T5 with δ=0.08

**Small** (0.11 ≤ |δ| < 0.28):

- Noticeable but modest improvement
- Cost-benefit analysis needed
- Example: T2→T3 with δ=0.22

**Medium** (0.28 ≤ |δ| < 0.43):

- Substantial improvement
- Strong justification for tier
- Example: T1→T2 with δ=0.35

**Large** (|δ| ≥ 0.43):

- Transformative improvement
- High-priority tier investment
- Example: T0→T1 with δ=0.67

### Comparative Analysis

**Across Transitions**:

- Identify highest-impact transitions
- Expected: Early tiers (T0→T1) show largest effects
- Diminishing returns: Later tiers show smaller deltas

**Across Models**:

- Compare effect patterns when faceted
- Check if tier benefits are model-specific
- Identify models with consistent vs. inconsistent improvements

### Action Items

**If Large Effects Detected**:

1. Prioritize those tier transitions for deployment
2. Investigate what architectural features drive the effect
3. Consider skipping intermediate tiers with small effects

**If Non-Significant Effects Detected**:

1. Increase sample size to narrow CIs
2. Re-evaluate tier necessity
3. Check for implementation errors or data quality issues

**If Regression Detected** (negative deltas):

1. Urgent investigation required
2. Check for data collection errors
3. Review tier implementation for bugs
4. Consider removing problematic tier

## Related Figures

- **Fig 03** (`fig03_tier_comparison`): Pass rate by tier with confidence intervals
  - Complements effect sizes with absolute performance metrics
  - Shows raw pass rates, not relative differences

- **Fig 09** (`fig09_tier_pairwise_significance`): Pairwise significance heatmap
  - Shows all pairwise tier comparisons (not just consecutive)
  - Uses p-values instead of effect sizes
  - Useful for identifying non-adjacent tier differences

- **Fig 18** (`fig18_power_analysis`): Statistical power by tier comparison
  - Assesses whether sample sizes are adequate for detecting effects
  - Complements CI width interpretation

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.effect_size import fig19_effect_size_forest
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig19_effect_size_forest(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig19_effect_size_forest(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig19_effect_size_forest.vl.json
├── fig19_effect_size_forest.csv
├── fig19_effect_size_forest.png
└── fig19_effect_size_forest.pdf
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig19_effect_size_forest.vl.json
```

**CSV Data**:

```bash
# Inspect effect sizes
head docs/figures/fig19_effect_size_forest.csv
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig19_effect_size_forest.png

# Include in LaTeX
\includegraphics{docs/figures/fig19_effect_size_forest.pdf}
```

### Sample CSV Output

```csv
agent_model,transition,tier1,tier2,delta,ci_low,ci_high,significant
claude-opus-4,T0→T1,T0,T1,0.657,0.548,0.752,Yes
claude-opus-4,T1→T2,T1,T2,0.312,0.198,0.425,Yes
claude-opus-4,T2→T3,T2,T3,0.185,0.067,0.301,Yes
claude-opus-4,T3→T4,T3,T4,0.092,-0.024,0.207,No
claude-opus-4,T4→T5,T4,T5,0.048,-0.068,0.164,No
claude-opus-4,T5→T6,T5,T6,0.023,-0.093,0.138,No
```

**Interpretation**:

- T0→T1: Large significant effect (δ=0.657, CI=[0.548, 0.752])
- T1→T2: Medium significant effect (δ=0.312, CI=[0.198, 0.425])
- T2→T3: Small significant effect (δ=0.185, CI=[0.067, 0.301])
- T3→T4: Negligible non-significant effect (δ=0.092, CI includes zero)
- T4→T5: Negligible non-significant effect (δ=0.048, CI includes zero)
- T5→T6: Negligible non-significant effect (δ=0.023, CI includes zero)

**Conclusion**: Major improvements occur in early tiers (T0→T3), while later tiers (T3→T6) provide minimal additional benefit for this model.

## Changelog

- **2026-02-12**: Initial documentation created for issue #463
