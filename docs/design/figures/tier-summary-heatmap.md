# Tier Summary Heatmap

## Overview

Figure 15c visualizes tier-level performance through an aggregated heatmap showing mean scores across all subtests within each tier. This figure provides the minimum granularity view, focusing on high-level performance patterns across testing tiers and model runs.

**Key Insight**: Reveals overall tier performance trends by aggregating away subtest-level detail, making it easier to identify which tiers show consistent success or failure across different agent models.

## Purpose

- **Primary Goal**: Visualize aggregated tier performance across runs to identify tier-level patterns
- **Use Cases**:
  - Compare tier difficulty across models (which tiers are universally hard/easy)
  - Identify run-to-run consistency at the tier level
  - Detect tier-level performance patterns across agent models
  - Provide executive summary view of performance without subtest detail
- **Audience**: Researchers conducting tier-level analysis, stakeholders needing high-level performance summaries

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `agent_model` (str): Agent model identifier
- `tier` (str): Testing tier (T0-T6)
- `run_number` (int): Run identifier
- `score` (float): Consensus score [0.0, 1.0]

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/subtest_detail.py:231-290`

**Data Requirements**:

- One row per (agent_model, tier, subtest, run_number) combination
- Scores are aggregated by taking the mean across all subtests within each (agent_model, tier, run_number) group
- Must contain at least one score per tier for meaningful visualization

## Implementation Details

### Function Signature

```python
def fig15c_tier_summary_heatmap(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 15c: Per-Tier Summary Heatmap (Aggregated).

    Aggregates scores across all subtests within each tier.
    Minimum granularity - focuses on tier-level performance patterns.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Score Aggregation**:

- Aggregates by (agent_model, tier, run_number) using mean
- **Rationale**: Reduces noise from individual subtest variations, highlights tier-level trends
- **Trade-off**: Loses subtest-level detail, but gains clarity for high-level patterns
- **Benefit**: Simplifies interpretation for executive summaries and tier-level comparisons

**Faceting by Model**:

- Creates separate heatmap panels for each agent model
- **Rationale**: Enables side-by-side model comparison while maintaining readability
- **Width**: 300px per panel (compact for multi-panel layouts)
- **Height**: 200px (sufficient for 7 tiers)

**Color Scale**:

- Scheme: "redyellowgreen" (diverging scale)
- Domain: [0, 1] (full score range)
- Shared across all facets
- **Rationale**: Intuitive color coding (red=poor, yellow=medium, green=good)
- **Benefit**: Enables cross-model comparison using consistent color mapping

**Natural Tier Ordering**:

- Uses `derive_tier_order()` to sort tiers naturally (T0, T1, ..., T6)
- **Benefit**: Prevents alphabetical sorting issues (e.g., T10 before T2)

### Algorithm

1. **Data Aggregation**:

   ```python
   tier_summary = (
       runs_df.groupby(["agent_model", "tier", "run_number"])["score"]
       .mean()
       .reset_index()
   )
   ```

2. **Derive Tier Order**:

   ```python
   tier_order = derive_tier_order(tier_summary)
   ```

3. **Create Base Heatmap**:

   ```python
   heatmap = (
       alt.Chart(tier_summary)
       .mark_rect()
       .encode(
           x=alt.X("run_number:O", title="Run Number", axis=alt.Axis(labelAngle=0)),
           y=alt.Y("tier:O", title="Tier", sort=tier_order),
           color=alt.Color(
               "score:Q",
               title="Mean Score",
               scale=alt.Scale(scheme="redyellowgreen", domain=[0, 1]),
           ),
           tooltip=[
               alt.Tooltip("agent_model:N", title="Model"),
               alt.Tooltip("tier:O", title="Tier"),
               alt.Tooltip("run_number:O", title="Run"),
               alt.Tooltip("score:Q", title="Mean Score", format=".3f"),
           ],
       )
       .properties(width=300, height=200)
   )
   ```

4. **Facet by Agent Model**:

   ```python
   chart = (
       heatmap.facet(column=alt.Column("agent_model:N", title=None))
       .properties(title="Tier Summary (Mean Across Subtests)")
       .resolve_scale(color="shared")
   )
   ```

5. **Save Figure**:

   ```python
   save_figure(chart, "fig15c_tier_summary_heatmap", output_dir, render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig15c_tier_summary_heatmap.{ext}`

**Examples**:

- `fig15c_tier_summary_heatmap.vl.json` - Vega-Lite specification
- `fig15c_tier_summary_heatmap.csv` - Aggregated data
- `fig15c_tier_summary_heatmap.png` - Rendered image (300 DPI, if render=True)
- `fig15c_tier_summary_heatmap.pdf` - Vector format (if render=True)

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 4 files (with rendering enabled)

## Visual Specification

### Chart Components

**Chart Type**: Faceted heatmap (rectangular marks with color encoding)

**Faceting**:

- Column facets: One panel per agent model
- Shared color scale across all panels

**Dimensions (Per Panel)**:

- Width: 300px
- Height: 200px

**Axes**:

- **X-axis**: Run Number (ordinal)
  - Label angle: 0° (horizontal)
  - Title: "Run Number"
- **Y-axis**: Tier (ordinal, sorted naturally)
  - Title: "Tier"
  - Sort order: T0, T1, T2, ..., T6

**Title**: "Tier Summary (Mean Across Subtests)"

**Color Encoding**:

- Variable: Mean score (aggregated across subtests)
- Scale: "redyellowgreen" (diverging)
- Domain: [0.0, 1.0]
- Interpretation:
  - Red (0.0-0.4): Poor performance
  - Yellow (0.4-0.6): Medium performance
  - Green (0.6-1.0): Good performance

**Tooltip**:

- Model: Agent model identifier
- Tier: Testing tier
- Run: Run number
- Mean Score: Aggregated score (3 decimal places)

### Expected Patterns

**Ideal Pattern**:

- Gradient from red (T0) to green (T6) → Performance improves with tier advancement
- Consistent color within columns → Run-to-run consistency
- Similar patterns across models → Tier difficulty is model-independent

**Problematic Patterns**:

- Vertical red stripes → Specific runs failed across all tiers
- Horizontal red bands → Specific tiers universally difficult
- Checkerboard pattern → High run-to-run variance
- Inverted gradient (green → red) → Performance degrades with tier advancement (unexpected)

## Interpretation Guide

### Reading the Heatmap

**Color Intensity**:

- **Dark red cells**: Mean score near 0.0 (tier failed on average)
- **Yellow cells**: Mean score around 0.5 (mixed success)
- **Dark green cells**: Mean score near 1.0 (tier succeeded on average)

**Horizontal Patterns (Across Runs)**:

- **Consistent color**: Stable tier performance across runs
- **Color variation**: Run-to-run variance in tier performance

**Vertical Patterns (Across Tiers)**:

- **Red → Green gradient**: Performance improves with tier advancement
- **Consistent color**: All tiers perform similarly (unexpected)
- **Green → Red gradient**: Performance degrades (potential issue)

### Comparative Analysis

**Across Models** (Horizontal Comparison):

- Compare corresponding cells across facet panels
- Identify model-specific strengths/weaknesses at tier level
- Example: Model A consistently green in T5, Model B consistently red → Model A better at T5

**Across Tiers** (Vertical Comparison):

- Compare rows within a single panel
- Identify which tiers are universally hard/easy
- Example: T3 consistently red across all models → T3 is universally difficult

**Across Runs** (Column Comparison):

- Compare columns within a single panel
- Identify run-to-run consistency
- Example: Run 1 all green, Run 2 all red → High variance between runs

### Action Items

**If Horizontal Red Bands Detected**:

1. Investigate tier definition for universal difficulty
2. Review subtest composition within that tier
3. Check for common failure modes across models
4. Consider tier redesign or recalibration

**If Vertical Red Stripes Detected**:

1. Investigate run-specific issues (environment, randomness)
2. Check for outlier runs in raw data
3. Consider increasing run count for robustness
4. Review run initialization and setup procedures

**If Checkerboard Pattern Detected**:

1. Analyze score variance at subtest level
2. Investigate sources of run-to-run variance
3. Consider increasing run count or adding warmup runs
4. Review metric stability and reliability

## Related Figures

- **Fig 15a** (`fig15a_subtest_duration_heatmap`): Subtest-level duration heatmap
  - Provides maximum granularity with per-subtest timing
  - Useful for identifying performance bottlenecks at subtest level

- **Fig 15b** (`fig15b_subtest_score_heatmap`): Subtest-level score heatmap
  - Shows scores at subtest granularity (before aggregation)
  - Reveals which specific subtests drive tier-level patterns

- **Fig 01** (`fig01_score_variance_by_tier`): Score variance by tier
  - Complementary statistical view of tier performance
  - Shows distribution and variance, not just mean scores

- **Fig 03** (`fig03_tier_performance_heatmap`): Per-tier grade distribution
  - Shows grade counts (A/B/C/D/F) instead of raw scores
  - Alternative categorical view of tier performance

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.subtest_detail import fig15c_tier_summary_heatmap
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig15c_tier_summary_heatmap(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig15c_tier_summary_heatmap(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig15c_tier_summary_heatmap.vl.json
├── fig15c_tier_summary_heatmap.csv
├── fig15c_tier_summary_heatmap.png
└── fig15c_tier_summary_heatmap.pdf
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig15c_tier_summary_heatmap.vl.json
```

**CSV Data**:

```bash
# Inspect aggregated data
head docs/figures/fig15c_tier_summary_heatmap.csv
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig15c_tier_summary_heatmap.png

# Include in LaTeX
\includegraphics{docs/figures/fig15c_tier_summary_heatmap.pdf}
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #462
