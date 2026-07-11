# Implementation Rate vs Pass-Rate Comparison

## Overview

This figure visualizes the correlation between Implementation Rate (Impl-Rate) and Pass-Rate across different agent models and testing tiers through grouped bar charts. The side-by-side comparison reveals whether successful implementations correlate with successful task completion and highlights model-specific performance patterns.

**Key Insight**: Reveals the gap between completing implementation steps (Impl-Rate) and achieving passing outcomes (Pass-Rate), which identifies where agents execute code correctly but fail validation criteria.

## Purpose

- **Primary Goal**: Compare implementation success against final task success to identify quality vs. completion trade-offs
- **Use Cases**:
  - Detect implementation-quality gaps (high Impl-Rate, low Pass-Rate)
  - Identify over-implementation patterns (agents complete steps but miss requirements)
  - Validate tier progression assumptions (both metrics should increase together)
  - Inform model selection based on implementation vs. validation performance
- **Audience**: Researchers analyzing agent quality metrics, experiment designers optimizing evaluation protocols, model developers comparing architectures

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `agent_model` (str): Agent model identifier (e.g., "opus-4", "sonnet-3.5")
- `tier` (str): Testing tier (T0-T6)
- `impl_rate` (float): Implementation rate [0.0, 1.0] - fraction of implementation criteria completed
- `passed` (bool/int): Final pass/fail status (converted to mean for pass-rate)

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/impl_rate_analysis.py:156-235`

**Data Requirements**:

- One row per run
- `impl_rate` column must exist (function returns early if missing)
- Typical dataset: 2,238+ runs across multiple models and tiers
- Groups by (agent_model, tier) for aggregation

## Implementation Details

### Function Signature

```python
def fig26_impl_rate_vs_pass_rate(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 26: Implementation Rate vs Pass-Rate Comparison.

    Grouped bar chart showing Impl-Rate and Pass-Rate side-by-side per model,
    with per-tier subfigures for detailed comparison.

    Args:
        runs_df: Runs DataFrame (must include impl_rate and passed columns)
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Grouped Bar Chart Design**:

- Displays two metrics (Impl-Rate, Pass-Rate) side-by-side per model
- **Rationale**: Enables direct visual comparison of both metrics for each model
- **Trade-off**: More visual complexity vs. single-metric clarity
- **Benefit**: Immediate identification of implementation-quality gaps

**Per-Tier Faceting**:

- Separate column for each tier using Altair's facet functionality
- **Rationale**: Shows tier progression and enables tier-specific model comparison
- **Design**: Independent x-axis scales per tier allow different model sets per tier
- **Benefit**: Handles incomplete tier coverage gracefully

**Fixed Color Encoding**:

- Blue (#1f77b4) for Impl-Rate
- Orange (#ff7f0e) for Pass-Rate
- **Rationale**: Color consistency across all instances of these metrics
- **Benefit**: Immediate visual recognition of metric type

**Y-Axis Domain**:

- Fixed [0, 1] scale
- **Rationale**: Both metrics are rates (fractions)
- **Benefit**: Consistent scale enables cross-tier and cross-model comparison

### Algorithm

1. **Column Validation**:

   ```python
   if "impl_rate" not in runs_df.columns:
       print("Warning: impl_rate column not found in runs_df, skipping fig26")
       return
   ```

2. **Metric Aggregation**:

   ```python
   stats = []
   for (model, tier), group in runs_df.groupby(["agent_model", "tier"]):
       impl_rate_mean = group["impl_rate"].mean()
       pass_rate_mean = group["passed"].mean()

       stats.append({"agent_model": model, "tier": tier, "metric": "Impl-Rate", "value": impl_rate_mean})
       stats.append({"agent_model": model, "tier": tier, "metric": "Pass-Rate", "value": pass_rate_mean})
   ```

   - Computes mean for both metrics per (model, tier) group
   - Reshapes data to long format with separate rows per metric

3. **Tier Discovery**:

   ```python
   tier_order = derive_tier_order(runs_df)
   ```

   - Dynamic tier detection from data
   - Natural sorting (T0 < T1 < ... < T99)

4. **Color Scale Configuration**:

   ```python
   metric_domain = ["Impl-Rate", "Pass-Rate"]
   metric_colors = ["#1f77b4", "#ff7f0e"]  # Blue for impl, orange for pass
   ```

5. **Grouped Bar Chart Construction**:

   ```python
   bars = (
       alt.Chart(df)
       .mark_bar()
       .encode(
           x=alt.X("agent_model:N", title="Agent Model"),
           y=alt.Y("value:Q", title="Rate", scale=alt.Scale(domain=[0, 1])),
           color=alt.Color("metric:N", title="Metric",
                          scale=alt.Scale(domain=metric_domain, range=metric_colors)),
           xOffset="metric:N",  # Side-by-side positioning
           tooltip=[...]
       )
   )
   ```

   - `xOffset` creates grouped bars within each model category

6. **Faceting by Tier**:

   ```python
   chart = (
       bars.facet(column=alt.Column("tier:O", title="Tier", sort=tier_order))
       .properties(title="Implementation Rate vs Pass-Rate per Tier")
       .resolve_scale(x="independent")  # Allow different models per tier
   )
   ```

7. **Save Output**:

   ```python
   save_figure(chart, "fig26_impl_rate_vs_pass_rate", output_dir, render=render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig26_impl_rate_vs_pass_rate.{ext}`

**Files Generated**:

- `fig26_impl_rate_vs_pass_rate.vl.json` - Vega-Lite specification
- `fig26_impl_rate_vs_pass_rate.csv` - Aggregated data (reshaped to long format)
- `fig26_impl_rate_vs_pass_rate.png` - Rendered image (300 DPI, if render=True)
- `fig26_impl_rate_vs_pass_rate.pdf` - Vector format (if render=True)

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 4 files (1 set per figure, not per-tier since faceting is internal)

## Visual Specification

### Chart Components

**Chart Type**: Grouped bar chart with faceted columns

**Dimensions**:

- Width: Auto (determined by Altair based on number of facets)
- Height: Auto (determined by Altair)
- Subfigure width: ~150-200px per tier (auto-scaled)

**Axes**:

- **X-axis** (per tier): Agent Model (nominal)
  - Title: "Agent Model"
  - Independent scales per tier (different models may appear in different tiers)
- **Y-axis** (shared): Rate (quantitative, 0.0-1.0)
  - Title: "Rate"
  - Fixed domain: [0, 1]

**Color Encoding**:

- **Impl-Rate**: Blue (#1f77b4)
- **Pass-Rate**: Orange (#ff7f0e)
- Legend title: "Metric"

**Faceting**:

- **Column**: Tier (T0, T1, ..., T6)
- **Sort**: Natural tier order
- **Title**: "Tier"

**Chart Title**: "Implementation Rate vs Pass-Rate per Tier"

**Tooltips**:

- Model (agent_model)
- Tier
- Metric (Impl-Rate or Pass-Rate)
- Rate (formatted to 3 decimal places)

### Expected Patterns

**Ideal Correlation**:

- Impl-Rate and Pass-Rate bars roughly equal height
- Both metrics increase together across tiers
- Indicates implementations directly lead to passing outcomes

**Implementation-Quality Gap**:

- Impl-Rate > Pass-Rate (blue bar taller than orange)
- Agents complete steps but fail validation
- Common causes:
  - Missing edge case handling
  - Incorrect implementation of requirements
  - Partial feature completion counted as "implemented"

**Over-Specification**:

- Pass-Rate > Impl-Rate (orange bar taller than blue)
- Rare but possible if pass criteria are broader than implementation criteria
- May indicate measurement issue or overly strict implementation rubric

**Tier Progression**:

- Both metrics should increase from T0 to T6
- Flatter progression indicates diminishing returns from capability tiers

## Interpretation Guide

### Reading the Bars

**Bar Height**:

- Represents mean rate across all runs for that (model, tier) group
- Values range from 0.0 (never achieved) to 1.0 (always achieved)

**Bar Positioning**:

- Grouped by model (x-axis)
- Colored by metric (blue vs. orange)
- Side-by-side within each model category

**Gap Analysis**:

- **Large gap** (blue >> orange): Implementation without quality
- **Small gap** (blue ≈ orange): Quality implementations
- **Negative gap** (blue < orange): Possible measurement issue

### Comparative Analysis

**Across Models**:

- Compare bar heights within each tier
- Identify which models have better implementation vs. pass-rate performance
- Look for models with consistent gaps vs. aligned metrics

**Across Tiers**:

- Follow a single model across tier columns
- Expected pattern: Both bars rise together
- Problematic pattern: Impl-Rate rises but Pass-Rate stagnates

**Metric Correlation**:

- Visual correlation: Do bars rise/fall together?
- Strong correlation → Quality implementations
- Weak correlation → Execution without understanding

### Action Items

**If Large Implementation-Quality Gap Detected**:

1. Review evaluation rubric for implementation criteria clarity
2. Check if partial implementations are over-credited
3. Investigate common failure modes in passing criteria
4. Consider stricter implementation validation

**If Metrics Are Uncorrelated**:

1. Validate that implementation criteria align with pass criteria
2. Check for edge cases where implementation steps succeed but outcome fails
3. Review whether "implementation" measures activity vs. correctness

**If Pass-Rate Exceeds Impl-Rate**:

1. Investigate potential measurement error
2. Check if pass criteria are too lenient
3. Verify implementation criteria aren't overly strict

## Related Figures

- **Fig 25** (`fig25_impl_rate_by_tier`): Implementation Rate by tier with confidence intervals
  - Provides detailed statistical view of Impl-Rate metric
  - Complements this figure by showing uncertainty in Impl-Rate measurements

- **Fig 27** (`fig27_impl_rate_distribution`): Implementation Rate distribution by tier
  - Violin/box plots showing Impl-Rate variance
  - Reveals distribution shape and outliers not visible in mean comparisons

- **Fig 04** (`fig04_pass_rate_by_tier`): Pass-Rate by tier with confidence intervals
  - Analogous figure focused solely on Pass-Rate
  - Useful for detailed Pass-Rate analysis separate from implementation

- **Fig 01** (`fig01_score_variance_by_tier`): Score variance by tier
  - Shows consensus score distributions
  - Contextualizes Pass-Rate in terms of underlying score distributions

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.impl_rate_analysis import fig26_impl_rate_vs_pass_rate
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Verify impl_rate column exists
if "impl_rate" not in runs_df.columns:
    print("Error: impl_rate column missing - cannot generate fig26")
else:
    # Generate figure (specs only, no rendering)
    output_dir = Path("docs/figures")
    fig26_impl_rate_vs_pass_rate(runs_df, output_dir, render=False)

    # Generate with rendering (PNG + PDF)
    fig26_impl_rate_vs_pass_rate(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig26_impl_rate_vs_pass_rate.vl.json
├── fig26_impl_rate_vs_pass_rate.csv
├── fig26_impl_rate_vs_pass_rate.png
└── fig26_impl_rate_vs_pass_rate.pdf
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig26_impl_rate_vs_pass_rate.vl.json
```

**CSV Data**:

```bash
# Inspect aggregated data
head docs/figures/fig26_impl_rate_vs_pass_rate.csv

# Expected columns: agent_model, tier, metric, value
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig26_impl_rate_vs_pass_rate.png

# Include in LaTeX
\includegraphics{docs/figures/fig26_impl_rate_vs_pass_rate.pdf}
```

### Sample Data Format

CSV output contains aggregated statistics in long format:

```csv
agent_model,tier,metric,value
opus-4,T0,Impl-Rate,0.450
opus-4,T0,Pass-Rate,0.300
opus-4,T1,Impl-Rate,0.620
opus-4,T1,Pass-Rate,0.580
sonnet-3.5,T0,Impl-Rate,0.380
sonnet-3.5,T0,Pass-Rate,0.250
...
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #469
