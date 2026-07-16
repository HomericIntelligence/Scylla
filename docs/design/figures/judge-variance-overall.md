# Figure 17: Judge Variance Overall

## Overview

Figure 17 provides a comprehensive view of judge scoring variance across the entire evaluation system, measuring the consistency and reliability of judge behavior at an aggregate level. Unlike Figure 2 (which shows raw score distributions), this figure analyzes per-judge scoring patterns using two complementary panels: a boxplot showing the distribution of scores assigned by each judge, and a bar chart quantifying each judge's scoring standard deviation. This dual-panel approach enables system-level reliability assessment by revealing which judges exhibit stable scoring behavior versus those with high variability.

The figure is generated separately for each tier to avoid Altair's 5,000-row limit and to enable tier-specific judge reliability analysis.

## Purpose

This figure serves three critical purposes in evaluating judge system reliability:

1. **System-Level Reliability Assessment**: Quantifies overall judge consistency across all evaluations, identifying whether the judging system as a whole produces stable, reproducible scores
2. **Judge-Specific Variance Detection**: Identifies individual judges with high scoring variability that may indicate unreliable evaluation behavior or sensitivity to specific test characteristics
3. **Comparative Judge Analysis**: Enables direct comparison of scoring behavior across different judge models, revealing which models provide more consistent evaluations

This analysis is essential for validating the reliability of the entire evaluation framework, as high judge variance undermines the reproducibility and trustworthiness of all benchmark results.

## Data Source

**Primary Input**: `judges_df` - Aggregated judge scores across all tests and runs

**Required Columns**:

- `tier`: Testing tier (T0-T6)
- `judge_model`: Full model identifier (e.g., "claude-sonnet-4-5-20250929")
- `judge_score`: Individual judge score (0.0-1.0)

**Data Transformations**:

1. Convert judge model IDs to display names using `model_id_to_display()` (e.g., "claude-sonnet-4-5-20250929" → "Sonnet 4.5")
2. Filter data by tier to generate separate figures per tier
3. Aggregate all scores per judge across tests and runs to compute overall statistics

**Data Volume**: Aggregates all judge scores within a tier (typically thousands of evaluations per judge)

## Mathematical Formulas

### Panel A: Score Distribution (Boxplot)

For each judge *j*, the boxplot displays the distribution of all scores assigned:

**Five-number summary**:

- **Minimum**: min(scores_j)
- **Q1 (25th percentile)**: percentile(scores_j, 0.25)
- **Median (Q2)**: percentile(scores_j, 0.50)
- **Q3 (75th percentile)**: percentile(scores_j, 0.75)
- **Maximum**: max(scores_j)

**Interquartile Range (IQR)**:

```
IQR_j = Q3_j - Q1_j
```

**Outlier Detection** (standard boxplot whiskers extend to 1.5 × IQR):

```
Lower_whisker = max(min(scores_j), Q1_j - 1.5 × IQR_j)
Upper_whisker = min(max(scores_j), Q3_j + 1.5 × IQR_j)
```

### Panel B: Scoring Standard Deviation

For each judge *j* with *n* scores, the standard deviation quantifies scoring variability:

**Sample standard deviation**:

```
σ_j = sqrt(Σ(score_i - μ_j)² / (n - 1))
```

where:

- `score_i`: Individual score assigned by judge *j*
- `μ_j`: Mean score assigned by judge *j*
- `n`: Total number of scores assigned by judge *j*

**Coefficient of Variation** (normalized variability measure, not displayed but relevant):

```
CV_j = σ_j / μ_j
```

## Theoretical Foundation

### Judge Reliability Theory

Judge variance analysis is grounded in psychometric reliability theory and inter-rater reliability frameworks:

1. **Consistency as Reliability**: Low variance indicates a judge applies consistent scoring criteria across different tests, while high variance suggests inconsistent application or sensitivity to context
2. **System-Level Trust**: If any judge exhibits high variance, all results from that judge become questionable, potentially invalidating tier comparisons
3. **Variance Decomposition**: Total scoring variance can be decomposed into:
   - **True Score Variance**: Legitimate differences in agent performance (desired signal)
   - **Judge Variance**: Inconsistent scoring behavior (measurement error)

### Statistical Interpretation

**Standard Deviation Thresholds** (heuristic guidelines):

- **σ < 0.15**: Excellent consistency (judge applies stable criteria)
- **0.15 ≤ σ < 0.25**: Acceptable consistency (moderate variability within reasonable bounds)
- **0.25 ≤ σ < 0.35**: Concerning variability (requires investigation)
- **σ ≥ 0.35**: Poor reliability (judge may be unreliable or highly context-sensitive)

**Boxplot IQR Interpretation**:

- **Narrow IQR (< 0.20)**: Judge scores cluster tightly around median (consistent behavior)
- **Wide IQR (> 0.40)**: Judge scores spread across a broad range (high variability)
- **Outliers**: Indicate specific test cases where judge behavior deviates dramatically from typical scoring

## Visualization Details

### Panel A: Score Distribution per Judge (Boxplot)

**Chart Type**: Boxplot (box-and-whisker plot)

**Visual Encoding**:

- **X-axis**: Judge model (display name, categorical)
- **Y-axis**: Judge score (0.0-1.0, quantitative)
- **Color**: Judge model (categorical, same as x-axis for visual clarity)
- **Box elements**:
  - Box spans Q1 to Q3 (IQR)
  - Median line inside box
  - Whiskers extend to 1.5 × IQR or min/max (whichever is closer)
  - Outliers plotted as individual points beyond whiskers

**Chart Properties**:

- Title: "Panel A: Score Distribution per Judge"
- Width: 300px
- Boxplot size: 40px

**Dynamic Scaling**:

- Y-axis domain computed from data with 15% padding to accommodate boxplot whiskers
- Judge order sorted alphabetically by display name
- Color scale dynamically assigned from config or fallback palette

### Panel B: Scoring Standard Deviation (Bar Chart)

**Chart Type**: Vertical bar chart

**Visual Encoding**:

- **X-axis**: Judge model (display name, categorical)
- **Y-axis**: Score standard deviation (0.0 to max, quantitative)
- **Color**: Judge model (categorical, matching Panel A)
- **Tooltip**:
  - Judge name
  - Standard deviation (formatted to 3 decimal places)

**Chart Properties**:

- Title: "Panel B: Scoring Standard Deviation"
- Width: 300px

**Dynamic Scaling**:

- Y-axis domain: [0, max(0.3, max_std × 1.1)] rounded to nearest 0.05
- Minimum domain of 0.3 ensures readability even for low-variance judges
- Judge order matches Panel A (alphabetically by display name)

### Combined Layout

**Horizontal Concatenation**: Panel A | Panel B (side-by-side)

**Overall Title**: "Judge Variance - {Tier}" (e.g., "Judge Variance - T0")

**File Output**:

- Vega-Lite JSON: `fig17_{tier}_judge_variance_overall.vl.json`
- CSV data: `fig17_{tier}_judge_variance_overall.csv`
- PNG render (if enabled): `fig17_{tier}_judge_variance_overall.png`
- PDF render (if enabled): `fig17_{tier}_judge_variance_overall.pdf`

where `{tier}` is the lowercase, hyphenated tier name (e.g., "t0", "t1").

## Interpretation Guidelines

### Reading Panel A (Boxplot)

1. **Median Line Position**: Indicates typical score assigned by judge
   - High median (> 0.7): Judge tends to give favorable scores
   - Low median (< 0.3): Judge tends to give harsh scores
   - Mid-range median (0.4-0.6): Judge uses full scoring range

2. **Box Height (IQR)**: Indicates middle 50% of scores
   - Narrow box: Consistent scoring (most scores cluster near median)
   - Wide box: Variable scoring (scores spread across range)

3. **Whisker Length**: Indicates full range excluding outliers
   - Short whiskers: Judge rarely assigns extreme scores
   - Long whiskers: Judge occasionally uses extreme scores

4. **Outliers**: Individual scores far from typical behavior
   - Few outliers: Stable scoring with rare exceptions
   - Many outliers: Frequent deviations from typical behavior

### Reading Panel B (Standard Deviation Bars)

1. **Bar Height**: Direct measure of scoring variability
   - Short bar (σ < 0.15): Excellent consistency
   - Medium bar (0.15 ≤ σ < 0.25): Acceptable consistency
   - Tall bar (σ ≥ 0.25): Concerning variability

2. **Relative Comparison**: Compare bars across judges
   - Similar heights: Judges exhibit similar variability
   - One judge much taller: Specific judge has reliability issues
   - Gradual progression: Systematic differences in judge behavior

### System-Level Reliability Thresholds

**Green Zone (High Reliability)**:

- All judges have σ < 0.20
- Boxplots show tight IQRs (< 0.25)
- Few outliers across all judges
- **Interpretation**: Evaluation system is highly reliable and reproducible

**Yellow Zone (Acceptable Reliability)**:

- Most judges have σ < 0.25, some between 0.25-0.30
- Boxplots show moderate spread (IQR 0.25-0.40)
- Occasional outliers
- **Interpretation**: System is generally reliable, but monitor high-variance judges

**Red Zone (Unreliable System)**:

- Any judge has σ > 0.35
- Boxplots show wide spread (IQR > 0.40)
- Frequent outliers across multiple judges
- **Interpretation**: System reliability is compromised; investigate judge configuration, test design, or rubric clarity

### Difference from Figure 2

**Figure 2 (Per-Judge Scoring Variance)**:

- Shows raw histogram of all judge scores combined
- Focuses on overall score distribution across the entire judging system
- Does not distinguish between individual judges
- Purpose: Understand aggregate scoring behavior

**Figure 17 (Judge Variance Overall)**:

- Shows per-judge score distributions using boxplots
- Quantifies per-judge standard deviation
- Explicitly compares individual judge reliability
- Purpose: Identify which specific judges are consistent vs. variable

**Key Distinction**: Figure 2 answers "How are scores distributed overall?" while Figure 17 answers "Which judges are reliable and which are not?"

## Related Figures

### Figure 2: Per-Judge Scoring Variance

**Relationship**: Figure 2 shows aggregate score distribution; Figure 17 decomposes this by individual judge

**Complementary Insights**:

- If Figure 2 shows bimodal distribution, Figure 17 reveals which judges contribute to each mode
- If Figure 2 shows wide spread, Figure 17 identifies whether this is due to all judges being variable or specific judges being unreliable

### Figure 14: Inter-Judge Agreement

**Relationship**: Figure 14 shows pairwise correlations; Figure 17 shows per-judge consistency

**Complementary Insights**:

- High inter-judge agreement (Figure 14) with low variance (Figure 17) → System is reliable and judges agree
- High inter-judge agreement (Figure 14) with high variance (Figure 17) → Judges agree on relative rankings but use different scoring scales
- Low inter-judge agreement (Figure 14) with low variance (Figure 17) → Judges are individually consistent but disagree with each other
- Low inter-judge agreement (Figure 14) with high variance (Figure 17) → System has fundamental reliability issues

**Combined Interpretation**: Use both figures together to distinguish between systematic disagreement (different but consistent scoring) versus random noise (inconsistent scoring).

## Code Reference

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/judge_analysis.py`

**Function**: `fig17_judge_variance_overall()` (lines 173-268)

**Dependencies**:

- `model_id_to_display()` from `scylla/analysis/loader.py:274` - Converts model IDs to display names
- `derive_tier_order()` from `scylla/analysis/figures/__init__.py:16` - Derives tier ordering from data
- `get_color_scale()` from `scylla/analysis/figures/__init__.py:71` - Retrieves color palettes
- `compute_dynamic_domain()` from `scylla/analysis/figures/spec_builder.py:18` - Computes axis domains with padding
- `save_figure()` - Saves Vega-Lite JSON, CSV, and optional PNG/PDF renders

**Key Implementation Details**:

1. **Tier-Specific Generation**: Generates separate figure for each tier to avoid Altair's 5,000-row limit
2. **Model Name Conversion**: Applies `model_id_to_display()` to convert technical model IDs to human-readable names
3. **Dynamic Judge Ordering**: Sorts judges alphabetically by display name (not hardcoded)
4. **Dynamic Color Assignment**: Uses configured colors or fallback palette based on judge names
5. **Adaptive Y-Axis Scaling**: Panel A uses 15% padding for boxplot whiskers; Panel B uses max(0.3, max_std × 1.1) to ensure readability
6. **Horizontal Layout**: Uses Altair's `|` operator to concatenate panels side-by-side

**Invocation**:

```python
from scylla.analysis.figures.judge_analysis import fig17_judge_variance_overall
from pathlib import Path

fig17_judge_variance_overall(
    judges_df=judges_df,  # DataFrame with columns: tier, judge_model, judge_score
    output_dir=Path("output/figures"),
    render=True  # Generate PNG/PDF in addition to JSON/CSV
)
```

**Output Files** (per tier):

- `output/figures/fig17_t0_judge_variance_overall.vl.json`
- `output/figures/fig17_t0_judge_variance_overall.csv`
- `output/figures/fig17_t0_judge_variance_overall.png` (if render=True)
- `output/figures/fig17_t0_judge_variance_overall.pdf` (if render=True)
