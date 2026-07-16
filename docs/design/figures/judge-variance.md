# Figure 02: Judge Variance

## Overview

Figure 02 visualizes per-judge scoring variance through histograms showing the distribution of judge scores. This figure helps identify systematic biases, scoring patterns, and the reliability of individual judge evaluations across different testing tiers.

**Key Insight**: Reveals whether judges score consistently or exhibit high variance, which impacts the reliability of consensus scores and overall evaluation quality.

## Purpose

- **Primary Goal**: Analyze the distribution of individual judge scores to understand scoring behavior
- **Use Cases**:
  - Detect judge scoring biases (lenient vs. strict)
  - Identify outlier scoring patterns
  - Validate judge reliability across tiers
  - Inform judge selection and weighting strategies
- **Audience**: Researchers evaluating judge performance, experiment designers optimizing evaluation protocols

## Data Source

**DataFrame**: `judges_df`

**Columns Used**:

- `tier` (str): Testing tier (T0-T6)
- `judge_score` (float): Individual judge score [0.0, 1.0]

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/judge_analysis.py:18-61`

**Data Requirements**:

- One row per (run, judge) evaluation
- Typical dataset: ~6,216 rows (2,238 runs × 3 judges)
- Must contain at least one judge score per tier

## Implementation Details

### Function Signature

```python
def fig02_judge_variance(
    judges_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 2: Per-Judge Scoring Variance.

    Histogram showing judge score distribution with 0.05 bin width.
    Generates separate figures per tier to avoid Altair's 5,000-row limit.

    Args:
        judges_df: Judges DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Per-Tier Splitting**:

- Generates separate figure for each tier
- **Rationale**: Avoids Altair's 5,000-row visualization limit
- **Trade-off**: Multiple files vs. single comprehensive view
- **Benefit**: Enables detailed per-tier analysis without data truncation

**Histogram Binning**:

- Bin width: 0.05 (20 bins across [0.0, 1.0])
- **Rationale**: Provides fine-grained distribution while maintaining readability
- **Sensitivity**: Reveals subtle scoring patterns (e.g., tendency to score in 0.05 increments)

**Dynamic Tier Discovery**:

- Uses `derive_tier_order(data)` to automatically detect available tiers
- Skips tiers with zero data
- **Benefit**: Handles partial experiments gracefully

### Algorithm

1. **Data Preparation**:

   ```python
   data = judges_df[["tier", "judge_score"]].copy()
   tier_order = derive_tier_order(data)
   ```

2. **Per-Tier Iteration**:

   ```python
   for tier in tier_order:
       tier_data = data[data["tier"] == tier]
       if len(tier_data) == 0:
           continue
   ```

3. **Histogram Construction**:

   ```python
   histogram = (
       alt.Chart(tier_data)
       .mark_bar()
       .encode(
           x=alt.X("judge_score:Q", bin=alt.Bin(step=0.05), title="Judge Score"),
           y=alt.Y("count():Q", title="Count"),
       )
   )
   ```

4. **Chart Finalization**:

   ```python
   chart = histogram.properties(
       title=f"Judge Score Distribution - {tier}",
       width=400,
       height=300,
   )
   ```

5. **Save with Tier-Specific Filename**:

   ```python
   tier_suffix = tier.lower().replace(" ", "-")
   save_figure(chart, f"fig02_{tier_suffix}_judge_variance", output_dir, render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig02_{tier}_judge_variance.{ext}`

**Examples**:

- `fig02_t0_judge_variance.vl.json` - Vega-Lite specification
- `fig02_t0_judge_variance.csv` - Data slice
- `fig02_t0_judge_variance.png` - Rendered image (300 DPI, if render=True)
- `fig02_t0_judge_variance.pdf` - Vector format (if render=True)

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

**Chart Type**: Histogram (Bar chart with binned continuous variable)

**Dimensions**:

- Width: 400px
- Height: 300px

**Axes**:

- **X-axis**: Judge Score (continuous, 0.0-1.0)
  - Binned with step=0.05
  - Title: "Judge Score"
- **Y-axis**: Count (discrete, auto-scaled)
  - Represents number of judge evaluations in each bin
  - Title: "Count"

**Title**: "Judge Score Distribution - {tier}"

- Example: "Judge Score Distribution - T0"

**Color Scheme**: Default Altair bar color (no custom encoding)

### Expected Patterns

**Ideal Distribution**:

- Bell curve centered around 0.7-0.9 (passing range)
- Moderate spread (std dev ~0.15-0.25)
- Few scores below 0.5 (failing range)

**Problematic Patterns**:

- Bimodal distribution → Inconsistent judge behavior
- Heavy tail at 0.0 or 1.0 → Judge saturation at extremes
- Uniform distribution → Random or uncalibrated scoring
- Spike at specific values → Anchoring bias

## Interpretation Guide

### Reading the Histogram

**High Frequency Bins**:

- Most common score ranges
- Indicates judge's "default" scoring tendency

**Distribution Shape**:

- **Normal**: Reliable, consistent scoring
- **Skewed left**: Lenient judge (scores high)
- **Skewed right**: Strict judge (scores low)
- **Flat**: High variance, unreliable

**Outliers**:

- Isolated bars far from main cluster
- May indicate edge cases or scoring errors

### Comparative Analysis

**Across Tiers**:

- Compare mean and variance across T0-T6
- Expected: Variance decreases as tiers advance (more capable agents → more consistent quality)

**Across Judges** (use with Fig 14):

- Compare distributions from different judge models
- Identify systematic differences in scoring behavior

### Action Items

**If High Variance Detected**:

1. Review judge prompts for ambiguity
2. Check rubric clarity and grading scale
3. Consider judge model calibration
4. Increase number of judges per run

**If Systematic Bias Detected**:

1. Investigate judge model characteristics
2. Review edge cases in judge data
3. Consider outlier removal or down-weighting

## Related Figures

- **Fig 14** (`fig14_judge_agreement`): Inter-judge agreement scatter matrix
  - Complements variance analysis with pairwise correlations
  - Reveals systematic disagreements between specific judge pairs

- **Fig 17** (`fig17_judge_variance_overall`): Judge variance per tier
  - Two-panel figure: box plots + std dev bars
  - Provides aggregate view across all judge models

- **Fig 01** (`fig01_score_variance_by_tier`): Score variance by tier
  - Shows consensus score distribution (not individual judges)
  - Useful for comparing judge-level vs. consensus-level variance

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.judge_analysis import fig02_judge_variance
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
judges_df = experiments["judges_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig02_judge_variance(judges_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig02_judge_variance(judges_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig02_t0_judge_variance.vl.json
├── fig02_t0_judge_variance.csv
├── fig02_t0_judge_variance.png
├── fig02_t0_judge_variance.pdf
├── fig02_t1_judge_variance.vl.json
├── fig02_t1_judge_variance.csv
├── fig02_t1_judge_variance.png
├── fig02_t1_judge_variance.pdf
└── ... (T2-T6)
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig02_t0_judge_variance.vl.json
```

**CSV Data**:

```bash
# Inspect raw data
head docs/figures/fig02_t0_judge_variance.csv
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig02_t0_judge_variance.png

# Include in LaTeX
\includegraphics{docs/figures/fig02_t0_judge_variance.pdf}
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #447
