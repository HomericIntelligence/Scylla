# Figure 18b: Aggregate Failure Rate by Tier (Summary)

## Overview

Figure 18b visualizes aggregate failure rates across all subtests within each tier, providing a high-level summary view of tier-level effectiveness. Unlike Figure 18a which shows granular per-subtest failure rates, this figure aggregates all subtest results within a tier to show overall tier failure patterns.

The visualization uses a horizontal bar chart showing the aggregate failure rate for each tier, faceted by agent model. Each bar represents the combined failure rate across all subtests in that tier, making it easy to compare overall tier performance at a glance.

## Purpose

Figure 18b serves several analytical purposes:

1. **Tier-level comparison**: Quickly identify which tiers have the highest and lowest overall failure rates
2. **Model comparison**: Compare aggregate tier performance across different agent models
3. **Summary view**: Provide a high-level overview complementing the detailed per-subtest analysis in Figure 18a
4. **Trend identification**: Reveal overall patterns in tier effectiveness across the testing hierarchy

This figure is particularly useful for:

- Executive summaries showing overall tier success/failure trends
- Identifying tiers that need systematic improvement across all subtests
- Understanding which tier levels pose the most challenges for agents
- Making high-level decisions about tier complexity and agent capability

## Data Source

The figure uses aggregated failure counts from the runs DataFrame:

**Input**: `runs_df` - DataFrame containing evaluation run results with columns:

- `agent_model`: Model identifier (e.g., "opus", "sonnet", "haiku")
- `tier`: Tier identifier (e.g., "T0", "T1", "T2", etc.)
- `subtest`: Subtest identifier within the tier
- `passed`: Boolean indicating test pass/fail status

**Aggregation Process**:

1. Group runs by `(agent_model, tier)` - combining all subtests within each tier
2. Calculate mean pass rate across all subtests in the tier
3. Derive failure rate as `1 - pass_rate`
4. Count number of subtests and runs aggregated per tier

**Aggregated Data Structure**:

```python
{
    "agent_model": str,      # Model identifier
    "tier": str,             # Tier identifier
    "failure_rate": float,   # Aggregate failure rate (0.0 to 1.0)
    "n_runs": int,           # Total number of runs in tier
    "n_subtests": int        # Number of subtests aggregated
}
```

## Mathematical Formulas

### Aggregate Failure Rate

The aggregate failure rate for a tier is computed by first calculating the mean pass rate across all subtests and runs within that tier, then converting to a failure rate:

**Pass Rate (Tier-level)**:

```
pass_rate(tier) = mean(passed) for all runs in tier
                = (sum of all passed values) / (total number of runs)
```

**Failure Rate (Tier-level)**:

```
failure_rate(tier) = 1 - pass_rate(tier)
```

where:

- `tier` = specific tier identifier (T0, T1, T2, etc.)
- `passed` = boolean values (0 or 1) from all runs across all subtests in the tier
- `mean(passed)` = average of all passed values in the tier group

### Example Calculation

For tier T1 with 3 subtests and 4 runs per subtest:

**Individual subtest pass rates**:

- Subtest A: 3/4 = 0.75 (3 passes out of 4 runs)
- Subtest B: 2/4 = 0.50 (2 passes out of 4 runs)
- Subtest C: 4/4 = 1.00 (4 passes out of 4 runs)

**Aggregate calculation**:

- Total runs: 12 (3 subtests × 4 runs)
- Total passes: 3 + 2 + 4 = 9
- Aggregate pass rate: 9/12 = 0.75
- Aggregate failure rate: 1 - 0.75 = 0.25

## Theoretical Foundation

### Tier-Level Failure Analysis

Figure 18b implements tier-level aggregation theory from evaluation methodology:

**Aggregation Principle**: By combining all subtest results within a tier, we measure the overall effectiveness of the tier as a complete capability level. This differs from per-subtest analysis which focuses on granular capability assessment.

**Key Theoretical Concepts**:

1. **Tier as Unit of Analysis**: Treats each tier (T0-T6) as a cohesive testing unit representing a specific capability level in the ablation study hierarchy

2. **Uniform Weighting**: All subtests within a tier contribute equally to the aggregate failure rate, assuming each subtest represents an equivalent facet of tier capability

3. **Overall Effectiveness**: Aggregate failure rate measures the probability that a randomly selected run from the tier will fail, providing a single effectiveness metric per tier

4. **Comparative Baseline**: Enables direct comparison of tier difficulty by abstracting away subtest-level variation

### Relationship to Testing Tiers

The seven testing tiers (T0-T6) represent an ablation study of agent capabilities:

| Tier | Name | Description |
|------|------|-------------|
| T0 | Prompts | System prompt ablation (empty → full CLAUDE.md) |
| T1 | Skills | Domain expertise via installed skills |
| T2 | Tooling | External tools and MCP servers |
| T3 | Delegation | Flat multi-agent with specialists |
| T4 | Hierarchy | Nested orchestration with orchestrators |
| T5 | Hybrid | Best combinations and permutations |
| T6 | Super | Everything enabled at maximum capability |

Aggregate failure rates reveal which capability levels pose the most systematic challenges, independent of specific subtest implementation.

## Visualization Details

### Chart Type

**Horizontal Bar Chart** with the following specifications:

**Mark**: `mark_bar()`

- Horizontal orientation (bars extend left-to-right)
- Solid fill colored by tier

**Encodings**:

- **Y-axis** (`y`): Tier identifier (nominal/ordinal)
  - Sorted by tier order (T0, T1, T2, ...)
  - Label: "Tier"

- **X-axis** (`x`): Aggregate failure rate (quantitative)
  - Domain: [0, 1] (0% to 100% failure rate)
  - Label: "Failure Rate"

- **Color** (`color`): Tier identifier
  - Dynamic color scale from tier configuration
  - Consistent with other tier-level visualizations

- **Tooltip**: Interactive information display
  - Tier identifier
  - Failure rate (formatted as percentage)
  - Number of subtests aggregated
  - Total number of runs

**Faceting**:

- **Column** (`facet`): Agent model
  - Creates separate panel for each model
  - Enables direct model-to-model comparison
  - Independent Y-axis scale per facet

**Layout**:

- Title: "Aggregate Failure Rate by Tier (Summary)"
- Column facet headers show agent model names
- Bars sorted vertically by tier order

### Visual Design Principles

1. **Color Consistency**: Tier colors match those used in Figure 18a and other tier-level visualizations
2. **Scale Normalization**: X-axis fixed at [0, 1] for consistent cross-model comparison
3. **Information Density**: Tooltip provides comprehensive context without cluttering the visual
4. **Horizontal Layout**: Facilitates reading tier labels and comparing bar lengths
5. **Faceted Comparison**: Side-by-side model panels enable quick performance comparison

## Interpretation Guidelines

### Reading the Chart

**Tier Success/Failure Trends**:

- **Short bars** (near 0.0): High success rate, low failure rate - tier is performing well
- **Long bars** (near 1.0): High failure rate, low success rate - tier has systematic issues
- **Mid-length bars** (around 0.5): Mixed success - tier shows moderate difficulty

**Cross-Tier Patterns**:

- **Increasing trend** (T0 → T6): Difficulty increases with capability level
- **Decreasing trend** (T0 → T6): Effectiveness improves with more capabilities
- **U-shaped pattern**: Performance dips at middle tiers, recovers at higher tiers
- **Flat pattern**: Consistent performance across all tier levels

**Cross-Model Patterns**:

- **Consistent bars**: Similar failure rates across models - tier difficulty is model-independent
- **Divergent bars**: Different failure rates - some models handle specific tiers better
- **Model superiority**: One model shows consistently shorter bars - better overall performance

### Analytical Questions

1. **Which tiers have the highest aggregate failure rates?**
   - Identify longest bars across all models
   - These tiers may need redesign or additional training data

2. **Do failure rates increase with tier complexity?**
   - Compare T0 vs T6 bar lengths
   - Expected pattern: higher tiers (more capabilities) should have lower failure rates

3. **Which models handle tier complexity best?**
   - Compare bar lengths across facets for the same tier
   - Shorter bars indicate better tier handling

4. **Are there tier-specific model strengths?**
   - Look for tiers where one model significantly outperforms others
   - Indicates specialized capability advantages

### Comparison with Related Figures

**vs. Figure 18a (Per-Subtest Failure Rate)**:

- Fig 18a: Shows granular per-subtest failure rates within each tier
- Fig 18b: Shows aggregated tier-level failure rates across all subtests
- **Use Fig 18a**: When investigating specific subtest issues or variation within a tier
- **Use Fig 18b**: When comparing overall tier effectiveness or presenting summary results

**vs. Figure 03 (Failure Rate by Tier - Grade Proportions)**:

- Fig 03: Shows stacked bar chart with grade proportions (P/D/C/B/A/S)
- Fig 18b: Shows simple failure rate (pass/fail binary)
- **Use Fig 03**: When granular grade distribution matters (e.g., understanding partial success)
- **Use Fig 18b**: When binary pass/fail outcome is sufficient for tier comparison

**Complementary Analysis**:

- Fig 18b identifies *which* tiers have high failure rates
- Fig 18a reveals *which subtests* within those tiers contribute most to failures
- Fig 03 shows *how* failures manifest across the grading spectrum

## Related Figures

### Figure 18a: Failure Rate per Subtest (Detailed)

- **Purpose**: Per-subtest granular failure rate analysis
- **Relationship**: Provides detailed breakdown of the aggregated rates shown in Fig 18b
- **When to use**: Investigating specific subtest failures within a tier

### Figure 03: Failure Rate by Tier (Grade Proportions)

- **Purpose**: Stacked bar chart showing grade distribution (P/D/C/B/A/S)
- **Relationship**: Alternative tier-level view with grade-based categorization instead of binary pass/fail
- **When to use**: Understanding grade distribution and partial success rates

### Figure 01: Score Variance by Tier

- **Purpose**: Distribution of evaluation scores within each tier
- **Relationship**: Complements failure rate with score variance analysis
- **When to use**: Understanding score variability and consistency within tiers

## Code Reference

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/variance.py`

**Function**: `fig18b_failure_rate_aggregate()`

- **Lines**: 399-468
- **Signature**: `fig18b_failure_rate_aggregate(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None`

**Key Implementation Details**:

1. **Data Aggregation** (lines 417-430):
   - Groups by `(agent_model, tier)` to aggregate all subtests
   - Computes `pass_rate = group["passed"].mean()`
   - Derives `failure_rate = 1 - pass_rate`
   - Tracks `n_subtests` and `n_runs` for context

2. **Chart Construction** (lines 444-466):
   - Horizontal bar chart with tier on Y-axis
   - Failure rate on X-axis with domain [0, 1]
   - Color encoding by tier with dynamic color scale
   - Tooltip showing tier, failure_rate, n_subtests, n_runs

3. **Faceting** (line 463):
   - Column facet by `agent_model`
   - Independent Y-axis scale resolution

4. **Output** (line 468):
   - Saves to `fig18b_failure_rate_aggregate.{png,pdf,json}`
   - Uses `save_figure()` utility for consistent file handling

**Dependencies**:

- `derive_tier_order()`: Determines tier sort order from data
- `get_color_scale()`: Retrieves dynamic tier color scheme
- `save_figure()`: Handles multi-format output (PNG/PDF/JSON)

**Related Functions**:

- `fig18a_failure_rate_per_subtest()`: Per-subtest detailed view
- `fig03_failure_rate_by_tier()`: Grade-based tier failure rates
