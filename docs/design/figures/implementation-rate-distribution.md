# Implementation Rate Distribution

## Overview

This figure visualizes the distribution of Implementation Rate (Impl-Rate) across testing tiers using violin plots overlaid with box plots. It reveals how completely agents satisfy semantic requirements, showing both the central tendencies and the full distribution shape to identify performance patterns and variability across different agent models and testing tiers.

**Key Insight**: Reveals whether agents consistently achieve high implementation completeness or show significant variation in requirement satisfaction, which impacts the reliability of partial-credit evaluation metrics.

## Purpose

- **Primary Goal**: Analyze the distribution of Implementation Rate scores to understand agent completeness patterns
- **Use Cases**:
  - Detect implementation completeness patterns across tiers
  - Identify variability in requirement satisfaction
  - Compare distribution shapes between agent models
  - Validate implementation rate consistency across testing conditions
  - Inform tier difficulty assessment and ablation study insights
- **Audience**: Researchers evaluating agent implementation completeness, experiment designers analyzing quality metrics, stakeholders comparing agent capabilities

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `tier` (str): Testing tier (T0-T6)
- `agent_model` (str): Model identifier (e.g., "opus", "sonnet", "haiku")
- `impl_rate` (float): Implementation Rate [0.0, 1.0]

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/impl_rate_analysis.py:237-340`

**Data Requirements**:

- One row per run
- Must contain valid impl_rate values (NaN values are filtered out)
- Typical dataset: ~746 runs across 7 tiers × 3 models
- Requires sufficient data points per tier for density estimation

## Implementation Details

### Function Signature

```python
def fig27_impl_rate_distribution(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 27: Implementation Rate Distribution by Tier.

    Violin plot showing distribution of Impl-Rate across tiers.

    Args:
        runs_df: Runs DataFrame (must include impl_rate column)
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Violin + Box Plot Overlay**:

- Combines density estimation (violin) with statistical summary (box plot)
- **Rationale**: Violin shows full distribution shape, box plot highlights quartiles and outliers
- **Trade-off**: More complex visualization vs. richer information content
- **Benefit**: Reveals both shape characteristics (bimodality, skewness) and statistical summaries

**Horizontal Orientation**:

- Density extends horizontally from y-axis
- **Rationale**: Maximizes vertical space for tier faceting
- **Benefit**: Enables clear per-tier comparison across many tiers

**Dynamic Domain Calculation**:

- Uses `compute_dynamic_domain()` with 15% padding
- **Rationale**: Focuses on actual data range with extra padding for box plot whiskers
- **Sensitivity**: Reveals subtle variations without wasting visual space on empty ranges
- **Example**: If data ranges [0.60, 0.95], domain becomes [0.55, 1.00] after padding and rounding

**Density Transform**:

- Altair's `transform_density()` for automatic kernel density estimation
- Grouped by tier and agent_model
- **Benefit**: Smooth distribution curves without manual binning

**Faceting Strategy**:

- Row faceting by tier with derived natural ordering
- **Rationale**: Enables vertical stacking for easy tier-to-tier comparison
- **Alternative**: Could use color/column faceting, but vertical stacking is clearer for progression

### Algorithm

1. **Data Validation**:

   ```python
   if "impl_rate" not in runs_df.columns:
       print("Warning: impl_rate column not found, skipping fig27")
       return

   df = runs_df[["agent_model", "tier", "impl_rate"]].dropna()
   ```

2. **Tier Ordering**:

   ```python
   tier_order = derive_tier_order(runs_df)
   ```

3. **Color Scale Setup**:

   ```python
   models = sorted(df["agent_model"].unique())
   domain, range_ = get_color_scale("models", models)
   ```

4. **Dynamic Domain Calculation**:

   ```python
   impl_rate_domain = compute_dynamic_domain(
       df["impl_rate"],
       padding_fraction=0.15
   )
   ```

5. **Violin Plot Construction**:

   ```python
   base_violin = (
       alt.Chart(df)
       .transform_density(
           density="impl_rate",
           groupby=["tier", "agent_model"],
           as_=["impl_rate", "density"],
       )
       .mark_area(orient="horizontal", opacity=0.5)
       .encode(
           x=alt.X("density:Q", title=None, axis=alt.Axis(labels=False)),
           y=alt.Y("impl_rate:Q", title="Implementation Rate",
                   scale=alt.Scale(domain=impl_rate_domain)),
           color=alt.Color("agent_model:N", title="Model",
                          scale=alt.Scale(domain=domain, range=range_)),
       )
   )
   ```

6. **Box Plot Construction**:

   ```python
   base_box = (
       alt.Chart(df)
       .mark_boxplot(size=20, opacity=0.7)
       .encode(
           x=alt.X("agent_model:N", title="Model", axis=alt.Axis(labels=False)),
           y=alt.Y("impl_rate:Q", scale=alt.Scale(domain=impl_rate_domain)),
           color=alt.Color("agent_model:N",
                          scale=alt.Scale(domain=domain, range=range_)),
       )
   )
   ```

7. **Layering and Faceting**:

   ```python
   chart = (
       (base_violin + base_box)
       .properties(title="Implementation Rate Distribution by Tier",
                  width=300, height=100)
       .facet(row=alt.Row("tier:N", title="Tier", sort=tier_order))
   )
   ```

8. **Save Figure**:

   ```python
   save_figure(chart, "fig27_impl_rate_distribution", output_dir, render=render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig27_impl_rate_distribution.{ext}`

**Examples**:

- `fig27_impl_rate_distribution.vl.json` - Vega-Lite specification
- `fig27_impl_rate_distribution.png` - Rendered image (300 DPI, if render=True)
- `fig27_impl_rate_distribution.pdf` - Vector format (if render=True)

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 3 files (with rendering enabled)

## Visual Specification

### Chart Components

**Chart Type**: Layered violin plot + box plot, faceted by tier

**Dimensions**:

- Width: 300px per facet
- Height: 100px per facet
- Total height: ~700px (7 tiers × 100px)

**Faceting**:

- **Rows**: One per tier (T0-T6)
- **Ordering**: Natural tier order (T0 → T1 → ... → T6)

**Axes**:

- **X-axis (Violin)**: Density (hidden - no labels, ticks, or grid)
  - Horizontal orientation for violin shapes
- **X-axis (Box)**: Agent Model (categorical, labels hidden)
  - Used for box plot positioning only
- **Y-axis**: Implementation Rate (continuous, [dynamic domain])
  - Title: "Implementation Rate"
  - Shared across all facets

**Color Encoding**:

- Maps to `agent_model`
- Uses consistent color scheme from config
- Applied to both violin and box plot layers

**Opacity**:

- Violin: 0.5 (semi-transparent for overlapping visibility)
- Box plot: 0.7 (slightly more opaque for quartile emphasis)

**Title**: "Implementation Rate Distribution by Tier"

### Expected Patterns

**Ideal Distribution**:

- Narrow violins centered near 1.0 (complete implementation)
- Low variance (most runs achieve high Impl-Rate)
- Few outliers below 0.7

**Progression Patterns**:

- **T0 (baseline)**: High variance, bimodal (partial vs. full implementation)
- **T1 (Skills) and T2 (Tooling)**: Narrowing distribution, shifting toward higher Impl-Rate
- **T3 (Delegation) and T4 (Hierarchy)**: Continued improvement in completeness
- **T5 (Hybrid) and T6 (Super)**: Tight distribution near 1.0

**Problematic Patterns**:

- Wide violins → Inconsistent implementation quality
- Bimodal distribution → All-or-nothing implementation (no partial credit)
- Low ceiling (< 0.8) → Systematic implementation gaps
- High outliers only → Cherry-picking (most runs fail to implement fully)

## Interpretation Guide

### Reading the Violin Plot

**Violin Width**:

- Wide sections → High density of runs at that Impl-Rate
- Narrow sections → Few runs with that score
- Multiple bulges → Multimodal distribution (distinct performance clusters)

**Box Plot Elements**:

- **Center line**: Median Impl-Rate
- **Box edges**: 25th and 75th percentiles (IQR)
- **Whiskers**: 1.5 × IQR or min/max
- **Points**: Outliers beyond whiskers

**Color Groups**:

- Each color represents a different agent model
- Compare shapes across colors within same tier
- Compare same color across tiers for model progression

### Comparative Analysis

**Across Tiers**:

- Expected: Distribution shifts right and narrows as tiers advance
- Variance reduction → More consistent implementation
- Median increase → Better average completeness

**Across Models**:

- Compare violin shapes within same tier
- Identify which models achieve more complete implementations
- Detect model-specific patterns (e.g., one model bimodal, another unimodal)

**Violin vs. Box Plot**:

- Violin reveals shape (skewness, multimodality)
- Box plot highlights statistical summary (median, quartiles)
- Discrepancies reveal distribution characteristics (e.g., long tail vs. symmetric)

### Action Items

**If High Variance Detected**:

1. Review task specification clarity
2. Check for ambiguous requirements
3. Investigate partial implementation patterns
4. Consider requirement decomposition granularity

**If Bimodal Distribution Detected**:

1. Identify which requirements separate the modes
2. Check for task-specific difficulty spikes
3. Investigate agent failure patterns (e.g., planning vs. execution)
4. Consider splitting task into subtasks

**If Low Ceiling Detected**:

1. Review requirement definitions for completeness
2. Check for missing or unmeasurable requirements
3. Investigate systematic gaps in agent capabilities
4. Validate Impl-Rate calculation correctness

## Related Figures

- **Fig 25** (`fig25_impl_rate_by_tier`): Implementation Rate by tier
  - Bar chart with confidence intervals
  - Provides aggregate view with statistical summaries
  - Complements distribution view with point estimates

- **Fig 26** (`fig26_impl_rate_vs_pass_rate`): Impl-Rate vs Pass-Rate scatter
  - Reveals correlation between implementation completeness and test passing
  - Identifies runs with partial implementation that still pass tests
  - Complements distribution with outcome relationships

- **Fig 04** (`fig04_pass_rate_by_tier`): Pass-Rate by tier
  - Analogous metric for test passing (vs. requirement satisfaction)
  - Useful for comparing Impl-Rate patterns with Pass-Rate patterns
  - Reveals partial-credit insights (high Impl-Rate, low Pass-Rate or vice versa)

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.impl_rate_analysis import fig27_impl_rate_distribution
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig27_impl_rate_distribution(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig27_impl_rate_distribution(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig27_impl_rate_distribution.vl.json
├── fig27_impl_rate_distribution.png
└── fig27_impl_rate_distribution.pdf
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig27_impl_rate_distribution.vl.json
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig27_impl_rate_distribution.png

# Include in LaTeX
\includegraphics[width=\textwidth]{docs/figures/fig27_impl_rate_distribution.pdf}
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #470
