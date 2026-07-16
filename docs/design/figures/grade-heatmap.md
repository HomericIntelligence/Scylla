# Figure 05: Grade Distribution Heatmap

> **Figure ID**: fig05
> **Source**: `scylla/analysis/figures/tier_performance.py:74-150`
> **Category**: Tier Performance Analysis

## Overview

Figure 05 presents a heatmap visualization showing the distribution of letter grades (S, A, B, C, D, F) across evaluation tiers. The figure displays the proportion of runs receiving each grade within each tier, faceted by agent model. This visualization enables rapid identification of grading patterns, tier difficulty differences, and model-specific performance characteristics.

The heatmap uses a viridis color scale to represent proportions from 0 (no runs) to 1 (all runs), with text annotations showing actual run counts. Empty cells indicate grade-tier combinations with zero runs, making it easy to spot edge cases or rare outcomes.

## Purpose

The grade distribution heatmap serves three primary analytical purposes:

1. **Pattern Recognition**: Identify systematic grading trends across tiers (e.g., T0 predominantly F/D grades, T6 predominantly A/S grades)
2. **Tier Difficulty Assessment**: Compare grade distributions between tiers to validate difficulty progression
3. **Model Comparison**: Evaluate how different agent models perform across the same tier structure through faceted views

This figure is particularly valuable for:

- Validating that tier difficulty increases monotonically (higher tiers should show better grade distributions)
- Identifying anomalies where specific grade-tier combinations are over/under-represented
- Assessing whether grading criteria are appropriately calibrated across tiers

## Data Source

**Primary Input**: `runs_df` - Runs DataFrame containing evaluation results

**Required Columns**:

- `agent_model`: Model identifier for faceting (e.g., "claude-opus-4", "claude-sonnet-3.5")
- `tier`: Evaluation tier (T0, T1, T2, T3, T4, T5, T6)
- `grade`: Letter grade assigned (S, A, B, C, D, F)

**Data Processing Pipeline**:

1. Group runs by `(agent_model, tier, grade)` and count occurrences
2. Calculate total runs per `(agent_model, tier)` combination
3. Compute proportion: `count / total` for each grade within tier
4. Derive tier ordering from data using `derive_tier_order()`
5. Use canonical grade ordering from `config.grade_order`

**Example Data Structure**:

```
agent_model          tier  grade  count  total  proportion
claude-opus-4        T0    F      45     50     0.90
claude-opus-4        T0    D      5      50     0.10
claude-opus-4        T1    B      20     50     0.40
claude-opus-4        T1    A      30     50     0.60
```

## Mathematical Formulas

### Grade Proportion Calculation

For each `(agent_model, tier, grade)` combination:

$$
\text{proportion}_{m,t,g} = \frac{\text{count}_{m,t,g}}{\sum_{g'} \text{count}_{m,t,g'}}
$$

Where:

- $m$ = agent model
- $t$ = tier
- $g$ = grade
- $\text{count}_{m,t,g}$ = number of runs with model $m$, tier $t$, grade $g$
- $\sum_{g'} \text{count}_{m,t,g'}$ = total runs for model $m$ in tier $t$ (across all grades)

### Constraints

$$
\forall m,t: \sum_{g \in \{S,A,B,C,D,F\}} \text{proportion}_{m,t,g} = 1.0
$$

$$
\forall m,t,g: 0 \leq \text{proportion}_{m,t,g} \leq 1.0
$$

**Special Case - Empty Cells**: When $\text{count}_{m,t,g} = 0$, the cell is rendered as empty (no rectangle, no text) rather than showing 0 proportion.

## Theoretical Foundation

### Grading Scale

Scylla uses an industry-aligned grading scale focused on production readiness (see `docs/design/grading-scale.md`):

| Grade | Threshold | Label | Description |
|-------|-----------|-------|-------------|
| S | 1.00 | Amazing | Exceptional work that goes above and beyond requirements |
| A | 0.80 | Excellent | Production ready, no significant issues |
| B | 0.60 | Good | Minor improvements possible, meets requirements |
| C | 0.40 | Acceptable | Functional with some issues, partial credit |
| D | 0.20 | Marginal | Significant issues, barely functional |
| F | 0.00 | Failing | Does not meet requirements |

### Expected Distribution Characteristics

**Tier Difficulty Hypothesis**: As tier complexity increases (T0 → T6), the grade distribution should shift toward higher grades, assuming:

- Lower tiers (T0-T2) test basic capabilities → expect more F/D/C grades
- Mid tiers (T3-T4) test intermediate capabilities → expect more C/B/A grades
- Upper tiers (T5-T6) test advanced capabilities → expect more A/S grades (only advanced agents reach these tiers)

**Distribution Shape**:

- **Baseline tiers** (T0) should show right-skewed distributions (concentrated in F/D)
- **Skill-augmented tiers** (T1-T2) should show increased spread
- **Advanced tiers** (T5-T6) should show left-skewed distributions (concentrated in A/S)

### Viridis Color Scale Rationale

The viridis colormap was chosen for several reasons:

1. **Perceptually uniform**: Equal steps in proportion yield equal steps in perceived color
2. **Colorblind-safe**: Distinguishable under common color vision deficiencies
3. **Print-friendly**: Maintains contrast when converted to grayscale
4. **Intuitive**: Dark (purple) = low proportion, bright (yellow) = high proportion

## Visualization Details

### Heatmap Specification

**Chart Type**: `mark_rect()` (rectangular heatmap cells)

**Encodings**:

- **X-axis**: `grade:O` (ordinal) - ordered as `["S", "A", "B", "C", "D", "F"]`
- **Y-axis**: `tier:O` (ordinal) - ordered dynamically from data
- **Color**: `proportion:Q` (quantitative) - viridis scale, domain `[0, 1]`
- **Facet**: `agent_model:N` (nominal) - one column per model

**Text Annotations**:

- **Position**: Centered in each cell (`baseline="middle"`)
- **Content**: `count:Q` (actual number of runs)
- **Font**: 12pt
- **Color**: Dynamic contrast adjustment
  - White text when `proportion < 0.7` (dark purple/green backgrounds)
  - Black text when `proportion > 0.7` (light yellow backgrounds)

### Color Contrast Logic

The dynamic text color ensures readability across the viridis gradient:

```python
color=alt.condition(
    alt.datum.proportion > 0.7,  # Light yellow backgrounds
    alt.value("black"),          # Use black text
    alt.value("white"),          # Use white text on dark backgrounds
)
```

**Threshold Rationale**: The 0.7 threshold was empirically chosen based on viridis luminance:

- Proportion 0.0 → dark purple (viridis start) → needs white text
- Proportion 0.5 → green (viridis mid) → needs white text
- Proportion 1.0 → bright yellow (viridis end) → needs black text
- Transition occurs around 0.7 where yellow becomes sufficiently bright

### Empty Cells

When a grade-tier combination has zero runs, no rectangle or text is rendered. This design choice:

- Reduces visual clutter
- Makes rare grade-tier combinations immediately apparent
- Prevents confusion between "0 proportion" and "no data"

The subtitle clarifies this behavior: "Empty cells indicate no runs with that grade for the tier"

### Tooltip Information

Hovering over any cell displays:

- **Tier**: Tier identifier
- **Grade**: Letter grade
- **Count**: Number of runs (integer)
- **Proportion**: Percentage formatted to 2 decimal places (e.g., "45.23%")

## Interpretation Guidelines

### Reading the Heatmap

1. **Within a Column (Single Tier)**:
   - Brighter cells indicate more common grades for that tier
   - The brightest cell shows the mode (most frequent grade)
   - Multiple bright cells indicate multimodal distribution

2. **Across Rows (Single Grade)**:
   - Horizontal patterns show which tiers commonly receive a specific grade
   - For example, F grades should be bright in T0 and fade in higher tiers

3. **Across Facets (Between Models)**:
   - Compare patterns between agent models
   - Different patterns suggest models have different capability profiles

### Pattern Recognition

**Healthy Progression** (Expected Pattern):

```
Tier  S  A  B  C  D  F
T0    ·  ·  ·  ·  ·  ████  (mostly F/D - baseline low)
T1    ·  ·  ·  ██ ██ ██   (spread across C/D/F)
T2    ·  ·  ██ ██ ·  ·    (concentrated B/C)
T3    ·  ██ ██ ·  ·  ·    (concentrated A/B)
T4    ██ ██ ·  ·  ·  ·    (concentrated S/A)
T5    ██ ██ ·  ·  ·  ·    (high grades)
T6    ███ ██ ·  ·  ·  ·   (very high grades)
```

**Anomaly Indicators**:

- **Flat distributions**: Every grade has similar proportion (suggests evaluation criteria too lenient/harsh)
- **Inverted progression**: Higher tiers show worse grades than lower tiers (suggests tier ordering issue)
- **Isolated bright cells**: One grade dominates entirely (suggests rubric targets single outcome)
- **Empty columns**: No runs achieve certain grades across all tiers (suggests grading scale mismatch)

### Grade Distribution Analysis

**Interpreting Specific Patterns**:

1. **All F grades in T0**:
   - Normal for baseline evaluation (no prompts/skills/tools)
   - Validates that enhancements in higher tiers provide value

2. **Bimodal distribution** (e.g., bright cells in both A and F):
   - Suggests task has "all or nothing" characteristics
   - May indicate rubric needs more granular criteria

3. **Uniform distribution** (all cells same brightness):
   - Suggests tier difficulty not calibrated to expected capability
   - May need rubric adjustment or tier redefinition

4. **S grades only in T6**:
   - Expected if S requires perfect score (1.00 exactly)
   - Validates that maximum capabilities are needed for exceptional performance

### Comparative Analysis

**Between Models**:

- Models with similar patterns have similar capability profiles
- Models with shifted patterns (e.g., one tier ahead) have capability advantages
- Models with different pattern shapes may specialize in different task types

**Between Tiers**:

- Large jumps in distribution (e.g., T1→T2) indicate significant capability gain from enhancements
- Small changes suggest diminishing returns or redundant enhancements
- Reversals indicate negative interference between enhancements

## Related Figures

### Complementary Visualizations

**Figure 04 - Pass-Rate by Tier**:

- Shows score distributions with pass/fail threshold
- Provides finer granularity than letter grades
- Use Fig 04 for precise threshold analysis, Fig 05 for categorical patterns

**Figure 09 - Criteria Performance by Tier** (if exists):

- Shows which rubric criteria drive grade differences
- Use together to understand *why* certain grades dominate in specific tiers

**Figure 03 - Score vs Cost Scatter** (if exists):

- Maps grade distributions to economic costs
- Helps identify cost-optimal tiers for desired grade targets

### Analysis Workflows

**Workflow 1: Validate Tier Progression**

1. Start with Fig 05 to identify overall grade distribution trends
2. Use Fig 04 to verify pass-rate increases monotonically
3. Check Fig 09 to confirm specific criteria improve across tiers

**Workflow 2: Identify Optimal Tier**

1. Use Fig 05 to find first tier with acceptable grade distribution (e.g., 80% A/B grades)
2. Check Fig 03 for cost at that tier
3. Use Fig 04 to verify pass-rate exceeds target threshold

**Workflow 3: Debug Grading Issues**

1. Notice anomaly in Fig 05 (e.g., unexpected grade distribution)
2. Drill into Fig 09 to identify problematic criteria
3. Review rubric definitions and adjust thresholds

## Code Reference

### Function Location

**File**: `/home/mvillmow/Scylla/scylla/analysis/figures/tier_performance.py`
**Function**: `fig05_grade_heatmap(runs_df, output_dir, render=True)`
**Lines**: 74-150

### Implementation Details

**Key Dependencies**:

- `altair`: Declarative visualization library for heatmap rendering
- `pandas`: DataFrame operations for grouping and proportion calculation
- `scylla.analysis.config`: Grade ordering and color configuration
- `scylla.analysis.figures.derive_tier_order`: Dynamic tier ordering from data

**Configuration Sources**:

- `config.grade_order`: `["S", "A", "B", "C", "D", "F"]` from `scylla/analysis/config.yaml:119`
- Viridis color scale: Built-in Altair scheme, domain fixed at `[0, 1]`
- Text color threshold: Hardcoded at `0.7` in conditional logic

### Data Transformations

```python
# Step 1: Count runs per (agent_model, tier, grade)
grade_counts = runs_df.groupby(["agent_model", "tier", "grade"]).size().reset_index(name="count")

# Step 2: Calculate totals per (agent_model, tier)
grade_counts["total"] = grade_counts.groupby(["agent_model", "tier"])["count"].transform("sum")

# Step 3: Compute proportions
grade_counts["proportion"] = grade_counts["count"] / grade_counts["total"]
```

### Output Files

**Generated Files** (when `render=True`):

- `{output_dir}/fig05_grade_heatmap.png` - Raster image (300 DPI)
- `{output_dir}/fig05_grade_heatmap.pdf` - Vector PDF for publication
- `{output_dir}/fig05_grade_heatmap.json` - Vega-Lite specification for reproducibility

### Customization Points

**To Modify Grade Ordering**:
Edit `scylla/analysis/config.yaml:119-124` and update `grade_order` list.

**To Change Color Scale**:
Modify line 109: `scale=alt.Scale(scheme="viridis", domain=[0, 1])`
Alternative schemes: `"plasma"`, `"inferno"`, `"magma"`, `"cividis"`

**To Adjust Text Color Threshold**:
Modify line 131: `alt.datum.proportion > 0.7`
Lower values → more black text, Higher values → more white text

**To Change Text Size**:
Modify line 125: `mark_text(baseline="middle", fontSize=12)`

### Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.tier_performance import fig05_grade_heatmap

# Load runs data
runs_df = pd.read_parquet("data/runs.parquet")

# Generate figure
output_dir = Path("output/figures")
fig05_grade_heatmap(runs_df, output_dir, render=True)

# Files created:
# - output/figures/fig05_grade_heatmap.png
# - output/figures/fig05_grade_heatmap.pdf
# - output/figures/fig05_grade_heatmap.json
```

### Testing Considerations

**Edge Cases to Test**:

1. **Single grade dominates**: All runs in one tier receive same grade
2. **Empty tiers**: Some agent-tier combinations have zero runs
3. **Missing grades**: No runs achieve certain grades (e.g., no S grades)
4. **Single model**: Only one agent_model in dataset (faceting still works)

**Visual Validation**:

- Verify proportions sum to 1.0 for each tier (brightness distribution)
- Confirm empty cells render as blank (not 0)
- Check text readability on darkest and lightest cells
- Validate tooltip shows correct count and percentage
