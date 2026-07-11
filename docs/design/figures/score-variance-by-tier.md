# Figure 01: Score Variance by Tier

## 1. Overview

Figure 01 visualizes the distribution of evaluation scores across all testing tiers (T0-T6) using histograms with 0.05 bin width. Each tier is displayed as a separate column facet, showing how score variance manifests differently as architectural complexity increases. This figure serves as the primary diagnostic for understanding score stability and performance consistency across the seven-tier ablation study framework.

## 2. Purpose

**Primary Question**: How does score variance evolve as we add architectural complexity (prompts → skills → tooling → delegation → hierarchy)?

**Secondary Questions**:

- Which tiers exhibit high variance (indicating inconsistent performance)?
- Do higher tiers (T4-T6) show tighter score distributions due to iterative refinement?
- Are there multi-modal distributions suggesting distinct performance clusters?
- Does any tier show ceiling effects (scores clustered near 1.0) or floor effects (scores clustered near 0.0)?

This figure enables researchers to identify whether architectural investments yield not just higher mean scores, but also more reliable and predictable performance.

## 3. Data Source

**Primary DataFrame**: `runs_df`

**Required Columns**:

- `tier` (categorical): Testing tier identifier (T0, T1, T2, T3, T4, T5, T6)
- `score` (float): Normalized evaluation score on [0, 1] scale

**Data Preparation**:

```python
data = runs_df[["tier", "score"]].copy()
```

**Tier Ordering**: Dynamically derived from data using natural sort (T0 < T1 < ... < T99) via `derive_tier_order(data)` function, ensuring correct left-to-right progression even with non-sequential tier sets.

**Sample Size**: Varies by tier and experimental configuration. Typical experiments include 10-50 runs per tier per subtest, resulting in hundreds to thousands of data points per tier histogram.

## 4. Mathematical Formulas

### Score Distribution

For each tier $T_i$, we observe a set of scores $S_i = \{s_1, s_2, \ldots, s_n\}$ where $s_j \in [0, 1]$.

**Histogram Binning**:

- Bin width: $\Delta = 0.05$
- Bin edges: $[0.00, 0.05), [0.05, 0.10), \ldots, [0.95, 1.00]$
- Number of bins: $k = \lceil 1.0 / 0.05 \rceil = 20$

**Bin Count**:
$$
\text{count}(\text{bin}_j) = \sum_{i=1}^{n} \mathbb{1}[s_i \in \text{bin}_j]
$$

where $\mathbb{1}[\cdot]$ is the indicator function.

### Variance and Standard Deviation

**Sample Variance**:
$$
\sigma^2 = \frac{1}{n-1} \sum_{i=1}^{n} (s_i - \bar{s})^2
$$

where $\bar{s} = \frac{1}{n} \sum_{i=1}^{n} s_i$ is the sample mean.

**Sample Standard Deviation**:
$$
\sigma = \sqrt{\sigma^2}
$$

**Coefficient of Variation** (CV):
$$
\text{CV} = \frac{\sigma}{\bar{s}}
$$

The CV is useful for comparing variability across tiers with different mean scores.

**Consistency Metric** (see `.claude/shared/metrics-definitions.md`):
$$
\text{Consistency} = 1 - \text{CV} = 1 - \frac{\sigma}{\bar{s}}
$$

Higher consistency values (closer to 1) indicate more stable performance.

## 5. Theoretical Foundation

### Variance as a Quality Signal

Score variance reveals critical information about agent architecture reliability:

1. **High Variance (σ² > 0.15)**: Indicates inconsistent performance across runs, suggesting:
   - Architectural non-determinism (e.g., stochastic tool selection in T3)
   - Task sensitivity to prompt variations (common in T0-T1)
   - Multi-modal failure patterns (some runs succeed, others fail catastrophically)

2. **Low Variance (σ² < 0.05)**: Indicates consistent performance, suggesting:
   - Robust architecture with deterministic execution paths (expected in T4-T5 with structured delegation)
   - Task ceiling/floor effects (all runs converge to similar outcomes)
   - Effective error handling and self-correction (T5 iterative refinement)

3. **Bimodal Distributions**: Two distinct score clusters (e.g., peaks near 0.0 and 1.0) indicate:
   - Binary success/failure mode (agent either completes task or fails completely)
   - Threshold effects in architectural capabilities
   - Potential for optimization through targeted interventions

### Expected Patterns

Based on the research methodology (see `/docs/research.md`), we expect:

**T0 (Vanilla LLM)**: High variance, often bimodal (success or total failure), low mean.

**T1 (Prompt Optimization)**: Reduced variance compared to T0, improved mean, but still sensitive to prompt engineering quality.

**T2 (Tooling)**: Moderate variance, multi-modal distributions if some tools are highly effective while others are not.

**T3 (Delegation)**: Potentially increased variance due to tool call failures and token budget explosions (see "Token Efficiency Chasm" in research.md).

**T4 (Hierarchy)**: Reduced variance through atomic task design and specialist agents, more consistent execution.

**T5 (Hybrid)**: Lowest variance expected due to iterative refinement and error correction loops, but at high cost.

**T6 (Super)**: Variance depends on synergy effects; ideally combines T5's consistency with optimized configurations.

### Statistical Significance

When comparing variance across tiers, use:

**Levene's Test** (for equality of variances):
$$
H_0: \sigma^2_{T_i} = \sigma^2_{T_j} \text{ for all } i, j
$$

**F-Test** (for pairwise variance comparison):
$$
F = \frac{\sigma^2_{\text{T}_i}}{\sigma^2_{\text{T}_j}}
$$

with $F \sim F(n_i-1, n_j-1)$ under $H_0$.

Report p-values with α = 0.05 threshold for significance.

## 6. Visualization Details

### Chart Type

**Histogram** with vertical bars (`alt.Chart.mark_bar()`)

### Axes

- **X-axis**: `score:Q` (quantitative)
  - Title: "Score"
  - Domain: [0, 1]
  - Binning: `alt.Bin(step=0.05)` creates 20 equal-width bins
  - Axis labels appear at: 0.0, 0.2, 0.4, 0.6, 0.8, 1.0

- **Y-axis**: `count():Q` (quantitative)
  - Title: "Count"
  - Domain: Dynamic based on bin counts
  - Shows frequency (number of runs) in each score bin

### Faceting

- **Column Facets**: `alt.Column("tier:N", title="Tier", sort=tier_order)`
  - Each tier displayed as separate histogram panel
  - Left-to-right progression: T0 → T1 → T2 → T3 → T4 → T5 → T6
  - Natural sorting ensures correct tier order even with gaps (e.g., if T2 is missing)

### Color Scheme

- **Single Color**: Default blue (`#4C78A8` from publication theme)
- No color encoding by tier (tiers are separated spatially via facets)

### Title

"Score Distribution per Tier"

### Theme

Publication-quality theme (see `scylla/analysis/figures/spec_builder.py`):

- Font: Serif
- Axis label size: 11pt
- Axis title size: 13pt
- Grid color: `#e0e0e0`
- Domain color: `#333333`

### Interactive Features (if rendered in browser)

- **Tooltip**: Hovering over bars shows:
  - Score bin range (e.g., "[0.45, 0.50)")
  - Count (number of runs in bin)

## 7. Interpretation Guidelines

### How to Read the Figure

1. **Identify the Tier**: Each column represents one testing tier (T0-T6).

2. **Observe the Shape**:
   - **Left-skewed (peak near 1.0)**: Most runs achieve high scores (good performance)
   - **Right-skewed (peak near 0.0)**: Most runs achieve low scores (poor performance)
   - **Uniform/flat**: Scores spread evenly across range (high variance, unpredictable)
   - **Bimodal**: Two peaks suggest binary success/failure pattern

3. **Assess the Spread**:
   - **Narrow distribution**: Low variance, consistent performance
   - **Wide distribution**: High variance, inconsistent performance

4. **Compare Across Tiers**:
   - Does variance decrease as tier increases? (Expected for T4-T5)
   - Do mean scores shift rightward (toward 1.0) with higher tiers?
   - Are there unexpected variance increases (red flags for architectural issues)?

### What "Good" Looks Like

**Ideal Pattern (T4-T5)**:

- Tight distribution (narrow histogram)
- Peak near 1.0 (high mean score)
- Minimal left tail (few catastrophic failures)

**Example**: T5 shows histogram concentrated in [0.85, 1.00] range with peak at [0.95, 1.00].

### What "Bad" Looks Like

**Problematic Pattern (T3)**:

- Wide distribution (σ > 0.25)
- Bimodal with peaks at extremes (0.0 and 1.0)
- Suggests tool failures causing catastrophic collapses

**Example**: T3 shows two peaks: one at [0.00, 0.05] (tool errors) and one at [0.90, 0.95] (successful runs).

### Common Patterns to Watch For

1. **Ceiling Effect**: All scores cluster at 1.0 → task is too easy for this tier
2. **Floor Effect**: All scores cluster at 0.0 → task is too hard for this tier
3. **Regression**: Higher tier shows worse variance than lower tier → architectural overhead outweighs benefits
4. **Mode Shift**: Distribution shifts from bimodal (T0-T2) to unimodal (T4-T5) → increased reliability

### Example Interpretations

**Scenario 1: T0 bimodal [0.0-0.1, 0.8-1.0], T5 unimodal [0.85-1.0]**

- Interpretation: Baseline (T0) has binary outcomes (either solves or fails). Advanced architecture (T5) consistently achieves high scores through iterative refinement.
- Conclusion: T5 justifies its cost through reduced failure rate.

**Scenario 2: T2 σ=0.15, T3 σ=0.28**

- Interpretation: Adding tools (T3) increased variance compared to skills (T2), likely due to tool call failures and token budget issues.
- Conclusion: Investigate tool reliability and schema optimization (see "Token Efficiency Chasm" in research.md).

**Scenario 3: T4 peak at [0.60-0.70], T5 peak at [0.90-1.0]**

- Interpretation: Flat delegation (T4) improves over baseline but hierarchical orchestration (T5) provides substantial quality gains.
- Conclusion: Iterative refinement in T5 is effective; measure Cost-of-Pass to assess economic viability.

## 8. Related Figures

### Direct Variance Analysis

- **Figure 16a**: Success Variance Per Subtest (heatmap)
  - Shows per-subtest variance grouped by tier
  - Complements Fig 01 by breaking down tier-level variance into subtest components
  - Reveals which subtests drive overall tier variance

- **Figure 16b**: Success Variance Aggregate (bar chart)
  - Shows aggregate variance metrics across all subtests per tier
  - Provides quantitative comparison (σ², CV) where Fig 01 shows distributions

### Related Failure Analysis

- **Figure 03**: Failure Rate by Tier (stacked bar chart)
  - Shows grade distribution (A/B/C/D/F) per tier
  - Complements Fig 01 by categorizing scores into discrete grades
  - Reveals proportion of passing vs. failing runs

- **Figure 18a**: Failure Rate per Subtest (horizontal bar chart)
  - Shows per-subtest failure rates color-coded by tier
  - Identifies which subtests contribute to variance in Fig 01

- **Figure 18b**: Aggregate Failure Rate by Tier (horizontal bar chart)
  - Shows overall failure rate per tier
  - Summarizes binary pass/fail trends that manifest as bimodal distributions in Fig 01

### Cross-Reference to Tables

- **Table 2.1** (in `/docs/research.md`): Tier definitions and hypothesized variance patterns
- **Metrics Definitions** (in `.claude/shared/metrics-definitions.md`): Consistency formula (1 - CV)

## 9. Code Reference

### Implementation

**File**: `/home/mvillmow/Scylla/scylla/analysis/figures/variance.py`

**Function**: `fig01_score_variance_by_tier(runs_df: pd.DataFrame, output_dir: Path, render: bool = True)`

**Lines**: 18-52

### Key Code Sections

**Data Preparation** (lines 31-32):

```python
data = runs_df[["tier", "score"]].copy()
```

**Tier Ordering** (lines 34-35):

```python
tier_order = derive_tier_order(data)
```

**Histogram Specification** (lines 37-45):

```python
histogram = (
    alt.Chart(data)
    .mark_bar()
    .encode(
        x=alt.X("score:Q", bin=alt.Bin(step=0.05), title="Score"),
        y=alt.Y("count():Q", title="Count"),
    )
)
```

**Faceting by Tier** (lines 47-50):

```python
chart = histogram.facet(
    column=alt.Column("tier:N", title="Tier", sort=tier_order)
).properties(title="Score Distribution per Tier")
```

**Output** (line 52):

```python
save_figure(chart, "fig01_score_variance_by_tier", output_dir, render)
```

### Output Files

When `render=True`, generates:

- `fig01_score_variance_by_tier.vl.json` - Vega-Lite JSON specification
- `fig01_score_variance_by_tier.png` - Rasterized image (300 DPI for publication)
- `fig01_score_variance_by_tier.pdf` - Vector PDF (if enabled)
- `fig01_score_variance_by_tier_include.tex` - LaTeX inclusion snippet (if PDF enabled)

### Dependencies

- `altair` - Declarative visualization library for Vega-Lite specs
- `pandas` - Data manipulation
- `scylla.analysis.config` - Configuration loading
- `scylla.analysis.figures` - Tier ordering and color utilities
- `scylla.analysis.figures.spec_builder` - Figure saving utilities

### Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.variance import fig01_score_variance_by_tier

# Load evaluation results
runs_df = pd.read_csv("results/runs.csv")

# Generate figure
output_dir = Path("results/figures")
fig01_score_variance_by_tier(runs_df, output_dir, render=True)
```

### Testing

Tested via end-to-end analysis pipeline in `scylla/analysis/generate_all_figures.py`, which:

1. Loads experiment results from `runs_df` aggregation
2. Calls all figure generation functions including `fig01_score_variance_by_tier`
3. Outputs figures to `results/figures/` directory
4. Validates Vega-Lite JSON spec structure

### Configuration

- **Bin width**: Hardcoded as `0.05` in line 42
- **Tier order**: Dynamically derived from data (no hardcoded tier list)
- **Color scheme**: Uses default publication theme (no tier-specific colors)
- **Title**: "Score Distribution per Tier" (line 49)

### Related Functions

- `fig03_failure_rate_by_tier()` (lines 55-119) - Grade distribution analysis
- `fig16a_success_variance_per_subtest()` (lines 122-217) - Per-subtest variance heatmap
- `fig16b_success_variance_aggregate()` (lines 220-321) - Aggregate variance bar charts
- `derive_tier_order()` in `scylla/analysis/figures/__init__.py` (lines 16-31) - Natural tier sorting
- `save_figure()` in `scylla/analysis/figures/spec_builder.py` (lines 160-207) - Figure output handling
