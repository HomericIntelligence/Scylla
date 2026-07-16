# Tier Uplift Analysis

## Overview

Tier Uplift measures the cumulative improvement in pass rate relative to the T0-Subtest0 baseline (no enhancements) as agents progress through testing tiers. This analysis quantifies the incremental value of each tier's capabilities by comparing performance against a common baseline, enabling direct comparison of tier effectiveness across different agent models.

## Purpose

This figure addresses the core research question: **How much does each tier improve agent performance compared to the baseline?** By measuring uplift from a fixed baseline (T0-Subtest0), we can:

- Quantify the cumulative benefit of adding capabilities (prompts, skills, tools, delegation, hierarchy)
- Compare tier effectiveness across different agent models
- Identify diminishing returns or acceleration points in capability progression
- Validate statistical significance of tier transitions using Mann-Whitney U tests with Bonferroni correction

## Metrics Calculated

### Pass Rate Uplift

**Formula:**

```
uplift = pass_rate_tier - pass_rate_T0_Subtest0
```

- **pass_rate_tier**: Mean pass rate for the tier (averaged across all subtests)
- **pass_rate_T0_Subtest0**: Baseline pass rate from T0-Subtest0 (no enhancements)

**Interpretation:**

- Positive uplift indicates improvement over baseline
- Negative uplift indicates degradation from baseline
- Zero uplift indicates no change

### Uplift Percentage

**Formula:**

```
uplift_pct = (uplift / pass_rate_T0_Subtest0) × 100
```

**Interpretation:**

- Shows relative improvement as percentage of baseline
- Example: 50% uplift_pct means tier performance is 1.5× baseline

### Statistical Significance

**Method:** Mann-Whitney U test with Bonferroni correction

**Process:**

1. Compare consecutive tiers (T0→T1, T1→T2, etc.) using Mann-Whitney U test
2. Apply Bonferroni correction: `p_corrected = p_raw × n_tests` where `n_tests = len(tier_order) - 1`
3. Mark transitions as significant if `p_corrected < 0.05`

**Visualization:** Asterisks (*) placed above significant tier points

## Data Requirements

### Input DataFrame Schema

**Required Columns:**

- `agent_model` (str): Agent model identifier
- `tier` (str): Tier identifier (T0, T1, T2, etc.)
- `subtest` (str): Subtest identifier (00, 01, 02, etc.)
- `passed` (bool): Whether the run passed

### Baseline Requirements

**Critical:** Each agent model MUST have T0-Subtest0 data. Models without this baseline are skipped with no error.

**Rationale:** T0-Subtest0 represents the "zero enhancement" baseline (empty prompt, no skills, no tools, no delegation).

## Implementation Details

### Data Processing Pipeline

1. **Compute Tier Pass Rates:**

   ```python
   tier_stats = (
       runs_df.groupby(["agent_model", "tier"])["passed"]
       .mean()
       .reset_index()
       .rename(columns={"passed": "pass_rate"})
   )
   ```

2. **Extract T0-Subtest0 Baseline:**

   ```python
   t0_subtest0_data = runs_df[
       (runs_df["agent_model"] == model)
       & (runs_df["tier"] == "T0")
       & (runs_df["subtest"] == "00")
   ]["passed"]
   ```

3. **Compute Uplift Per Tier:**

   ```python
   uplift = pass_rate - t0_pass_rate
   uplift_pct = (uplift / t0_pass_rate) * 100 if t0_pass_rate > 0 else 0
   ```

4. **Statistical Testing:**

   ```python
   _, pvalue_raw = mann_whitney_u(tier1_data, tier2_data)
   pvalue = bonferroni_correction(pvalue_raw, n_tests)
   ```

### Visualization Specifications

**Chart Type:** Line chart with points and optional significance markers

**Axes:**

- X-axis: Tier (ordinal, sorted by tier order)
- Y-axis: Pass Rate Uplift vs T0-Subtest0 (quantitative, dynamic domain with floor=-1.0, ceiling=1.0)

**Color Encoding:** Agent model (categorical, dynamic color scale)

**Tooltip Fields:**

- Tier (ordinal)
- Model (nominal)
- Pass Rate (quantitative, formatted as percentage)
- Uplift (quantitative, formatted as percentage)
- Uplift % (quantitative, formatted as decimal)

**Significance Markers:**

- Text: "*" (asterisk)
- Position: dy=-15 (15 pixels above point)
- Style: fontSize=12, fontWeight="bold", color="black"
- Condition: Only shown when `significant == True`

## Output Files

### Primary Visualization

**File:** `fig11_tier_uplift.json` (Vega-Lite specification)

**Optional:** `fig11_tier_uplift.png` and `fig11_tier_uplift.pdf` (if `render=True`)

### Statistical Significance Data

**File:** `fig11_tier_uplift_significance.csv`

**Schema:**

- `agent_model` (str): Agent model identifier
- `tier` (str): Destination tier of transition
- `transition` (str): Transition label (e.g., "T0→T1")
- `pvalue` (float): Bonferroni-corrected p-value
- `significant` (bool): Whether p < 0.05

## Interpretation Guidelines

### Reading the Chart

1. **Baseline Reference:** All lines start from the same conceptual baseline (T0-Subtest0), though the chart shows uplift values
2. **Positive Slopes:** Indicate tier is improving performance (capabilities are helping)
3. **Negative Slopes:** Indicate tier is degrading performance (capabilities are hurting)
4. **Flat Regions:** Indicate tier provides no improvement over baseline
5. **Asterisks:** Mark statistically significant transitions (p < 0.05 after Bonferroni correction)

### Expected Patterns

**Ideal Case:** Monotonically increasing uplift across tiers

- T0 < T1 < T2 < T3 < T4 < T5 < T6
- All transitions marked as significant

**Diminishing Returns:** Uplift increases but at decreasing rates

- Large jumps early (T0→T1, T1→T2)
- Smaller gains later (T4→T5, T5→T6)

**Capability Interference:** Negative uplift in mid-tiers

- Could indicate poor prompt engineering, skill conflicts, or delegation overhead
- Requires deeper investigation into tier configuration

**Model Divergence:** Different models show different uplift patterns

- Some models may benefit more from certain capabilities
- Helps identify model-specific optimization strategies

## Related Figures

- **Fig 1 (Tier Performance):** Shows absolute pass rates per tier (not relative to baseline)
- **Fig 12 (Consistency):** Measures determinism across tiers (orthogonal to uplift)
- **Fig 6 (Tier Cost-of-Pass):** Economic complement to quality uplift

## Source Reference

**Implementation:** `/home/mvillmow/Scylla/scylla/analysis/figures/model_comparison.py:27-175`

**Function:** `fig11_tier_uplift(runs_df: pd.DataFrame, output_dir: Path, render: bool = True)`

**Dependencies:**

- `scylla.analysis.figures.derive_tier_order()`: Derives tier ordering from data
- `scylla.analysis.figures.get_color_scale()`: Generates dynamic color scales
- `scylla.analysis.figures.spec_builder.compute_dynamic_domain()`: Computes axis domains
- `scylla.analysis.figures.spec_builder.save_figure()`: Saves Vega-Lite specification
- `scylla.analysis.stats.mann_whitney_u()`: Performs non-parametric statistical test
- `scylla.analysis.stats.bonferroni_correction()`: Adjusts p-values for multiple comparisons
