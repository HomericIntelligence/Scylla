# Figure 25: Implementation Rate by Tier

## Overview

Figure 25 visualizes Implementation Rate (Impl-Rate) across testing tiers through a grouped bar chart with 95% bootstrap confidence intervals. This figure reveals how effectively agents implement functionality, independent of test outcomes, providing insight into execution capability vs. correctness.

**Key Insight**: Distinguishes between "agent tried but failed tests" (high Impl-Rate, low Pass-Rate) and "agent didn't implement" (low Impl-Rate), enabling diagnosis of capability vs. execution issues.

## Purpose

- **Primary Goal**: Compare implementation capability across tiers and agent models using statistical rigor
- **Use Cases**:
  - Identify tiers where agents struggle to implement vs. tiers where implementations fail tests
  - Compare model implementation capabilities independent of test correctness
  - Detect strategic drift (agent abandons implementation attempts)
  - Validate that tier progression doesn't reduce implementation attempts
  - Inform resource allocation by distinguishing capability gaps from execution bugs
- **Audience**: Researchers analyzing agent execution patterns, experiment designers optimizing evaluation protocols, model developers diagnosing failure modes

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `tier` (str): Testing tier (T0-T6)
- `agent_model` (str): Agent model name
- `impl_rate` (float): Implementation Rate [0.0, 1.0]
- `subtest` (str, optional): Subtest identifier for counting n per tier

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/impl_rate_analysis.py:25-153`

**Data Requirements**:

- One row per run (task attempt)
- `impl_rate` column must exist (gracefully skips if missing)
- At least one run per (agent_model, tier) combination
- Typical dataset: ~2,238 runs across 7 tiers and multiple models

## Implementation Details

### Function Signature

```python
def fig25_impl_rate_by_tier(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 25: Implementation Rate by Tier.

    Grouped bar chart with 95% bootstrap confidence intervals.
    Analogous to fig04 but for Impl-Rate instead of Pass-Rate.

    Args:
        runs_df: Runs DataFrame (must include impl_rate column)
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Bootstrap Confidence Intervals**:

- Uses 95% bootstrap CI via `bootstrap_ci(impl_rate)`
- **Rationale**: Provides robust uncertainty quantification without normality assumptions
- **Trade-off**: Computationally expensive vs. parametric CI, but more accurate for skewed distributions
- **Benefit**: Enables rigorous statistical comparison across tiers and models

**Subtest Count Annotations**:

- Tier labels show `{tier} (n={count})` format (e.g., "T0 (n=24)")
- **Rationale**: Provides context for statistical power and sample size
- **Benefit**: Readers can assess confidence interval reliability at a glance

**Dynamic Domain Computation**:

- Uses `compute_dynamic_domain_with_ci()` to include CI bounds in axis range
- **Rationale**: Prevents error bars from being clipped at plot boundaries
- **Sensitivity**: Adds padding to ensure full visibility of uncertainty

**Grouped Encoding with xOffset**:

- Groups bars by model using `xOffset="agent_model:N"`
- **Rationale**: Enables direct within-tier comparisons across models
- **Alternative Considered**: Faceted charts (rejected due to reduced comparability)

### Algorithm

1. **Data Validation**:

   ```python
   if "impl_rate" not in runs_df.columns:
       print("Warning: impl_rate column not found, skipping fig25")
       return
   ```

2. **Tier Discovery and Subtest Counting**:

   ```python
   tier_order = derive_tier_order(runs_df)

   subtest_counts = {}
   for tier in tier_order:
       tier_data = runs_df[runs_df["tier"] == tier]
       if "subtest" in tier_data.columns:
           subtest_counts[tier] = tier_data["subtest"].nunique()
       else:
           subtest_counts[tier] = 0
   ```

3. **Bootstrap Statistics Calculation**:

   ```python
   stats = []
   for model in runs_df["agent_model"].unique():
       for tier in tier_order:
           subset = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)]
           impl_rate = subset["impl_rate"].dropna()

           if len(impl_rate) > 0:
               mean, ci_low, ci_high = bootstrap_ci(impl_rate)
               tier_label = f"{tier} (n={subtest_counts[tier]})"

               stats.append({
                   "agent_model": model,
                   "tier": tier,
                   "tier_label": tier_label,
                   "impl_rate": mean,
                   "ci_low": ci_low,
                   "ci_high": ci_high,
                   "n": len(impl_rate)
               })
   ```

4. **Color Scale Assignment**:

   ```python
   models = sorted(df["agent_model"].unique())
   domain, range_ = get_color_scale("models", models)
   ```

5. **Dynamic Domain Computation**:

   ```python
   impl_rate_domain = compute_dynamic_domain_with_ci(
       df["impl_rate"], df["ci_low"], df["ci_high"]
   )
   ```

6. **Vega-Lite Spec Construction**:

   ```python
   bars = alt.Chart(df).mark_bar().encode(
       x=alt.X("tier_label:N", title="Tier (Subtest Count)", sort=tier_label_order),
       y=alt.Y("impl_rate:Q", title="Implementation Rate",
               scale=alt.Scale(domain=impl_rate_domain)),
       color=alt.Color("agent_model:N", title="Model"),
       xOffset="agent_model:N"
   )

   error_bars = alt.Chart(df).mark_errorbar().encode(
       x=alt.X("tier_label:N", sort=tier_label_order),
       y="ci_low:Q", y2="ci_high:Q",
       xOffset="agent_model:N"
   )

   chart = (bars + error_bars).properties(
       title="Implementation Rate by Tier (95% Bootstrap CI)",
       width=400, height=300
   )
   ```

7. **Save to Disk**:

   ```python
   save_figure(chart, "fig25_impl_rate_by_tier", output_dir, render=render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig25_impl_rate_by_tier.{ext}`

**Extensions**:

- `.vl.json` - Vega-Lite specification (always generated)
- `.csv` - Aggregated statistics with bootstrap CIs (always generated)
- `.png` - Rendered image at 300 DPI (if `render=True`)
- `.pdf` - Vector format (if `render=True`)

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 4 files (with rendering), 2 files (spec-only)

## Visual Specification

### Chart Components

**Chart Type**: Grouped bar chart with error bars

**Dimensions**:

- Width: 400px
- Height: 300px

**Axes**:

- **X-axis**: Tier (Subtest Count) (nominal, ordered)
  - Format: "T0 (n=24)", "T1 (n=10)", etc.
  - Title: "Tier (Subtest Count)"
  - Labels: Horizontal (labelAngle=0)
  - Order: T0, T1, T2, T3, T4, T5, T6
- **Y-axis**: Implementation Rate (quantitative, [0.0, 1.0])
  - Title: "Implementation Rate"
  - Domain: Dynamically computed with CI padding
  - Format: Decimal (e.g., 0.850)

**Title**: "Implementation Rate by Tier (95% Bootstrap CI)"

**Color Encoding**:

- Maps `agent_model` to distinct colors via `get_color_scale("models", models)`
- Legend title: "Model"
- Colors are consistent across all analysis figures

**Error Bars**:

- Represent 95% bootstrap confidence intervals
- Vertical bars spanning `ci_low` to `ci_high`
- Aligned with corresponding bars via `xOffset`

**Tooltip**:

- Model: Agent model name
- Tier: Testing tier
- Impl-Rate: Mean implementation rate (3 decimal places)
- 95% CI Low: Lower confidence bound (3 decimal places)
- 95% CI High: Upper confidence bound (3 decimal places)
- N: Sample size (number of runs)

### Expected Patterns

**High Implementation Rate (>0.8)**:

- Agent consistently attempts implementation
- Indicates strong execution capability
- If Pass-Rate is low, suggests bugs in implementation rather than strategic failures

**Medium Implementation Rate (0.4-0.8)**:

- Partial implementation attempts
- May indicate complexity-driven abandonment
- Compare with Pass-Rate to diagnose issue

**Low Implementation Rate (<0.4)**:

- Frequent implementation abandonment
- Possible strategic drift or capability ceiling
- Critical issue requiring investigation

**Wide Confidence Intervals**:

- High variance in implementation behavior
- May indicate inconsistent agent behavior or small sample size
- Check `n` in tooltip for sample size

**Narrow Confidence Intervals**:

- Consistent implementation behavior
- Reliable estimates (especially with larger `n`)

## Interpretation Guide

### Reading the Chart

**Bar Heights**:

- Represent mean implementation rate across all runs for (model, tier)
- Higher bars = more consistent implementation attempts

**Error Bar Overlap**:

- Overlapping CIs suggest no statistically significant difference
- Non-overlapping CIs indicate likely significant difference (approximate test)

**Subtest Counts (n)**:

- Displayed in tier labels: "T0 (n=24)"
- Higher `n` = more statistical power
- Low `n` (e.g., n=1 for T6-Super) may have unreliable CIs

### Comparative Analysis

**Across Tiers**:

- Expected: Implementation rate should remain stable or increase with tier
- **If decreasing**: Strategic drift (agent gives up on harder tasks)
- **If stable with low Pass-Rate**: Execution bugs, not capability issues

**Across Models**:

- Compare bars within each tier group
- Identifies which models maintain implementation efforts
- Useful for model selection based on persistence

**Impl-Rate vs. Pass-Rate (use with Fig 04)**:

- High Impl-Rate, High Pass-Rate: Ideal performance
- High Impl-Rate, Low Pass-Rate: Bugs in implementation
- Low Impl-Rate, Low Pass-Rate: Strategic failure or capability ceiling
- Low Impl-Rate, High Pass-Rate: Impossible (can't pass without implementing)

### Action Items

**If Impl-Rate Declines with Tier**:

1. Investigate agent prompts for task abandonment triggers
2. Check timeout settings (premature termination)
3. Review task complexity scaling
4. Consider agent capability ceiling reached

**If Impl-Rate High but Pass-Rate Low**:

1. Focus on debugging implementation quality
2. Check test harness for edge cases
3. Review judge scoring criteria
4. Investigate common failure patterns

**If Impl-Rate Varies Widely Across Models**:

1. Analyze prompt engineering differences
2. Compare model architectures for persistence mechanisms
3. Consider ensemble approaches using high-Impl-Rate models

## Related Figures

- **Fig 04** (`fig04_pass_rate_by_tier`): Pass-Rate by tier
  - Direct comparison metric for Impl-Rate
  - Combined analysis reveals capability vs. correctness gaps

- **Fig 26** (`fig26_impl_rate_vs_pass_rate`): Implementation Rate vs Pass-Rate comparison
  - Side-by-side comparison with per-tier subfigures
  - Enables direct visual correlation analysis

- **Fig 27** (`fig27_impl_rate_distribution`): Implementation Rate distribution by tier
  - Violin plots showing full distribution shape
  - Complements aggregate statistics with distributional insights

- **Fig 08** (`fig08_cost_by_tier`): Cost by tier
  - Economic context for implementation attempts
  - Helps assess cost-effectiveness of implementation efforts

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.impl_rate_analysis import fig25_impl_rate_by_tier
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig25_impl_rate_by_tier(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig25_impl_rate_by_tier(runs_df, output_dir, render=True)

# Check if impl_rate column exists before calling
if "impl_rate" in runs_df.columns:
    fig25_impl_rate_by_tier(runs_df, output_dir, render=True)
else:
    print("Impl-Rate not computed, skipping fig25")
```

### Expected Output

```
docs/figures/
├── fig25_impl_rate_by_tier.vl.json  # Vega-Lite specification
├── fig25_impl_rate_by_tier.csv      # Aggregated data with bootstrap CIs
├── fig25_impl_rate_by_tier.png      # Rendered image (300 DPI, if render=True)
└── fig25_impl_rate_by_tier.pdf      # Vector format (if render=True)
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig25_impl_rate_by_tier.vl.json
```

**CSV Data**:

```bash
# Inspect aggregated statistics
head docs/figures/fig25_impl_rate_by_tier.csv

# Example output:
# agent_model,tier,tier_label,impl_rate,ci_low,ci_high,n
# claude-opus-4,T0,T0 (n=24),0.923,0.875,0.958,240
# claude-opus-4,T1,T1 (n=10),0.887,0.812,0.941,100
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig25_impl_rate_by_tier.png

# Include in LaTeX
\includegraphics{docs/figures/fig25_impl_rate_by_tier.pdf}
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #468
