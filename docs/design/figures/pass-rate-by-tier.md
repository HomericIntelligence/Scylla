# Figure 04: Pass Rate by Tier

## 1. Overview

Figure 04 visualizes the distribution of task scores across all testing tiers (T0-T6), showing how agent capability progresses as architectural components are added. The figure displays histograms of score distributions with a reference line marking the pass threshold, enabling quick visual assessment of tier effectiveness and the proportion of runs that achieve passing scores.

The visualization supports the core research question: **Does adding architectural complexity (prompts, skills, tooling, delegation, hierarchy) improve agent task performance?**

## 2. Purpose

This figure serves multiple analytical purposes:

1. **Validate Tier Effectiveness**: Confirm that higher tiers (with more architectural components) produce higher pass rates than lower tiers
2. **Identify Optimal Tiers**: Determine which tier provides the best balance of capability and complexity
3. **Detect Non-Monotonic Patterns**: Identify cases where adding components decreases performance (e.g., T3 < T2), indicating architectural anti-patterns
4. **Support Ablation Analysis**: Provide visual evidence for the contribution of each architectural component to overall success
5. **Guide Architecture Decisions**: Inform practitioners about which components provide the most value

## 3. Data Source

The figure uses data from `runs_df`, the comprehensive DataFrame containing one row per experimental run.

### Required Columns

| Column | Type | Description |
|--------|------|-------------|
| `tier` | str | Testing tier identifier (T0, T1, T2, T3, T4, T5, T6) |
| `score` | float | Composite score combining pass_rate and implementation_rate (range: 0.0-1.0) |

### Data Characteristics

- **Sample Size**: 10 runs per tier per model per subtest
- **Score Range**: [0.0, 1.0] continuous values
- **Tier Coverage**: All 7 tiers (T0-T6) included
- **Filtering**: No filtering applied - all runs included

## 4. Mathematical Formulas

### Score Calculation

The score displayed in the histogram is the composite score:

```
score = (pass_rate + impl_rate) / 2
```

Where:

- `pass_rate`: Binary indicator (1.0 if passed, 0.0 if failed)
- `impl_rate`: Judge's weighted implementation score (0.0-1.0)

### Pass Rate Aggregation

For a given tier, the overall pass rate is:

```
tier_pass_rate = (number of runs with score >= pass_threshold) / (total runs in tier)
```

### Histogram Binning

The histogram uses fixed-width bins:

```
bin_width = 0.05
bin_edges = [0.00, 0.05, 0.10, 0.15, ..., 0.95, 1.00]
number_of_bins = 20
```

Each bar represents the count of runs with scores falling within the bin range.

## 5. Theoretical Foundation

### Ablation Study Methodology

Figure 04 implements a visual ablation study, where each tier represents a cumulative addition of architectural components:

| Tier | Components | Expected Impact |
|------|-----------|-----------------|
| T0 | Empty prompt | Baseline (lowest performance) |
| T1 | + Full CLAUDE.md | Improved task understanding |
| T2 | + Skills | Domain expertise boost |
| T3 | + External tools | Expanded capabilities |
| T4 | + Multi-agent delegation | Specialist coordination |
| T5 | + Hierarchical orchestration | Complex task decomposition |
| T6 | + All optimizations | Maximum capability |

### Expected Progression

Under the hypothesis that architectural components improve performance, we expect:

```
Pass Rate (T0) < Pass Rate (T1) < Pass Rate (T2) < ... < Pass Rate (T6)
```

### Non-Monotonic Patterns

When a tier performs worse than its predecessor (e.g., T3 < T2), this suggests:

1. **Overhead Dominance**: The added component introduces more overhead (cost, latency, complexity) than benefit
2. **Integration Issues**: Components conflict or interfere with each other
3. **Task Mismatch**: The component is not well-suited to the specific task type
4. **Prompt Incompatibility**: Instructions don't effectively leverage the new capability

These patterns are valuable for identifying architectural anti-patterns and guiding refinement.

## 6. Visualization Details

### Chart Type

**Layered Chart**: Combination of histogram (score distribution) + rule mark (threshold reference line)

### Faceting

- **Facet Type**: Column facets (horizontal arrangement)
- **Facet Variable**: `tier`
- **Facet Order**: Derived from data using `derive_tier_order()` function (typically T0, T1, T2, T3, T4, T5, T6)

### Histogram Layer

| Property | Value | Description |
|----------|-------|-------------|
| Mark | `bar` | Vertical bars for counts |
| X-axis | `score:Q` | Quantitative score values |
| Y-axis | `count():Q` | Aggregated count of runs in each bin |
| Bin Width | `0.05` | Fixed-width bins (20 bins total) |
| X-axis Title | "Score" | Clear label |
| Y-axis Title | "Count" | Number of runs |

### Threshold Line Layer

| Property | Value | Description |
|----------|-------|-------------|
| Mark | `rule` | Vertical reference line |
| X-position | `pass_threshold` | Default: 0.60 (from `config.yaml`) |
| Color | Red | High-contrast alert color |
| Stroke Dash | `[5, 5]` | Dashed pattern for reference line |

### Layout Properties

- **Title**: "Score Distribution per Tier (Pass Threshold Marked)"
- **Multi-panel**: One panel per tier (7 panels total)
- **Alignment**: Shared Y-axis scale across all panels for direct comparison

## 7. Interpretation Guidelines

### Reading the Visualization

1. **Distribution Shape**:
   - **Bimodal**: Clear separation between passing and failing runs
   - **Unimodal (low)**: Consistently failing tier
   - **Unimodal (high)**: Consistently passing tier
   - **Uniform**: High variance, unpredictable performance

2. **Position Relative to Threshold**:
   - **Most mass left of red line**: Tier performs below acceptable level
   - **Most mass right of red line**: Tier performs above acceptable level
   - **Mass split evenly**: Tier is marginal (50% pass rate)

3. **Tier Progression**:
   - **Expected**: Distribution shifts rightward (higher scores) as tier increases
   - **Anomalous**: Distribution shifts leftward, indicating performance degradation

### Example Interpretations

**Scenario 1: Monotonic Improvement**

```
T0: Most scores < 0.40 (left of threshold)
T1: Scores spread 0.30-0.70 (centered on threshold)
T2: Most scores > 0.60 (right of threshold)
...
T6: All scores > 0.80 (far right of threshold)
```

**Interpretation**: Architecture components provide cumulative benefit. Each tier adds value.

**Scenario 2: Non-Monotonic Pattern**

```
T2: Most scores > 0.70 (strong performance)
T3: Most scores < 0.60 (weak performance)
T4: Most scores > 0.75 (strong performance)
```

**Interpretation**: T3 (Delegation) degrades performance compared to T2 (Tooling). Possible causes:

- Tool selection overhead dominates benefit
- Prompts don't effectively guide tool usage
- Tools conflict with existing skills

**Scenario 3: Plateau Effect**

```
T4: Scores distributed 0.60-0.90
T5: Scores distributed 0.60-0.90 (identical to T4)
T6: Scores distributed 0.60-0.90 (identical to T4)
```

**Interpretation**: Hierarchical orchestration (T5) and optimization (T6) provide no additional benefit. Architecture has reached capability ceiling for this task set.

### Statistical Considerations

- **Small Sample Size**: With 10 runs per tier, distributions may appear noisy
- **Bin Artifacts**: 0.05 bin width may create visual discontinuities; consider smoothing for presentation
- **Threshold Sensitivity**: Different tasks may require different thresholds (see per-task rubrics)

## 8. Related Figures

This figure should be analyzed in conjunction with:

### Fig 11: Tier Uplift

- **Purpose**: Quantifies the improvement from tier N to tier N+1
- **Connection**: Fig04 shows distributions, Fig11 shows pairwise differences
- **Analysis**: Use Fig11 to identify which tier transitions provide the largest gains

### Fig 01: Score Variance by Tier

- **Purpose**: Box plots showing score distribution with quartiles
- **Connection**: Fig01 shows statistical summaries, Fig04 shows full distributions
- **Analysis**: Use Fig04 to see bimodal patterns that box plots might obscure

### Fig 03: Failure Rate by Tier

- **Purpose**: Stacked bar chart of grade distributions
- **Connection**: Fig03 shows categorical grades, Fig04 shows continuous scores
- **Analysis**: Use Fig04 to see fine-grained score patterns within each grade category

### Fig 06: Cost-of-Pass by Tier

- **Purpose**: Economic analysis of tier efficiency
- **Connection**: Combines pass rate (from Fig04) with cost data
- **Analysis**: High pass rate (Fig04) + low cost (Fig06) = optimal tier

## 9. Code Reference

### Source Location

File: `/home/mvillmow/Scylla/scylla/analysis/figures/tier_performance.py`

Function: `fig04_pass_rate_by_tier()` (lines 18-71)

### Function Signature

```python
def fig04_pass_rate_by_tier(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True,
    pass_threshold: float | None = None,
) -> None:
```

### Key Implementation Details

1. **Threshold Configuration**:
   - Default: Loaded from `scylla/analysis/config.yaml` (`pass_threshold: 0.60`)
   - Override: Pass `pass_threshold` parameter to use custom value

2. **Data Preparation**:

   ```python
   data = runs_df[["tier", "score"]].copy()
   ```

3. **Tier Ordering**:
   - Uses `derive_tier_order(data)` to extract tier labels from data
   - Ensures consistent ordering across all figures

4. **Reference Line Data**:
   - Creates one row per tier with threshold value
   - Enables facet-aware threshold line rendering

5. **Layering**:

   ```python
   chart = alt.layer(histogram, threshold_line).facet(...)
   ```

6. **Output**:
   - Saves to `output_dir/fig04_pass_rate_by_tier.vl.json` (Vega-Lite spec)
   - Optionally renders to PNG/PDF if `render=True`

### Configuration Dependencies

File: `/home/mvillmow/Scylla/scylla/analysis/config.yaml`

```yaml
figures:
  pass_threshold: 0.60  # Reference line for acceptable pass-rate
```

### Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.tier_performance import fig04_pass_rate_by_tier

# Load experiment data
runs_df = pd.read_csv("docs/data/runs.csv")

# Generate figure
output_dir = Path("docs/figures")
fig04_pass_rate_by_tier(
    runs_df=runs_df,
    output_dir=output_dir,
    render=True,  # Generate PNG/PDF
    pass_threshold=0.60  # Default from config
)

# Output files:
#   docs/figures/fig04_pass_rate_by_tier.vl.json
#   docs/figures/fig04_pass_rate_by_tier.png (if render=True)
#   docs/figures/fig04_pass_rate_by_tier.pdf (if render=True)
```

### Testing

Tests for this figure are located in:

- `/home/mvillmow/Scylla/tests/analysis/test_figures.py`

Verify figure generation with:

```bash
pixi run pytest tests/analysis/test_figures.py::test_fig04_pass_rate_by_tier -v
```
