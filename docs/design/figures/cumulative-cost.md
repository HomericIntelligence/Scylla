# Cumulative Cost Analysis

## Overview

Figure 22 visualizes the cumulative cost accumulation across all experimental runs in chronological order. This line chart tracks how total expenditure grows as the evaluation progresses, providing visibility into cost trajectory and enabling budget monitoring throughout the experiment lifecycle.

The visualization displays cumulative cost curves for different agent models on a single graph, using distinct line styles (strokeDash patterns) to differentiate between models while maintaining color consistency with the model color scheme used throughout other visualizations.

## Purpose

This figure serves several critical functions in cost analysis and budget management:

1. **Cost Trajectory Monitoring**: Track how quickly costs accumulate during evaluation runs
2. **Budget Planning**: Project total experiment costs based on observed accumulation rates
3. **Model Comparison**: Compare cost efficiency between different agent models over time
4. **Anomaly Detection**: Identify unexpectedly high-cost runs that create steep jumps in the curve
5. **Resource Allocation**: Inform decisions about continuing, pausing, or modifying experiments based on cost burn rate

Unlike static cost metrics (CoP, total cost), cumulative cost reveals the temporal dynamics of expenditure, making it invaluable for operational cost management during long-running evaluations.

## Data Source

**Primary DataFrame**: `runs_df` (per-run execution records)

**Required Columns**:

- `agent_model`: Model identifier (e.g., "opus-4", "sonnet-3.5")
- `tier`: Testing tier (T0-T6)
- `subtest`: Specific subtest identifier
- `cost_usd`: Per-run cost in USD
- `run_number` (optional): Explicit execution sequence number

**Data Preparation**:

1. Sort runs by execution order:
   - If `run_number` exists: Sort by `[agent_model, tier, subtest, run_number]`
   - Otherwise: Sort by `[agent_model, tier, subtest]` (assumes insertion order = execution order)
2. Compute cumulative sum per model group independently
3. Assign sequential run indices (0, 1, 2, ...) within each model group

**Data Quality Requirements**:

- All `cost_usd` values must be non-negative
- Chronological ordering must reflect actual execution sequence
- No missing cost data (null/NaN values will break cumulative calculation)

## Mathematical Formulas

### Cumulative Cost

For each model group, cumulative cost at run index $i$ is:

$$
\text{CumulativeCost}_i = \sum_{j=0}^{i} \text{cost\_usd}_j
$$

Where:

- $i$ = run index in chronological order (0-indexed)
- $j$ = index variable for summation
- $\text{cost\_usd}_j$ = individual run cost at index $j$

**Properties**:

- Monotonically non-decreasing (assuming non-negative costs)
- Final value equals total experiment cost for that model
- Slope between points $i$ and $i+1$ equals $\text{cost\_usd}_{i+1}$

### Rate of Cost Accumulation

The instantaneous cost accumulation rate (derivative approximation):

$$
\text{Rate}_i = \frac{\text{CumulativeCost}_{i+1} - \text{CumulativeCost}_i}{\Delta \text{run\_index}} = \text{cost\_usd}_{i+1}
$$

Where $\Delta \text{run\_index} = 1$ (unit spacing).

**Interpretation**:

- Steep sections = high per-run costs
- Flat sections = low per-run costs
- Sudden jumps = individual expensive runs

## Theoretical Foundation

### Cost Monitoring and Budget Tracking

Cumulative cost curves provide real-time visibility into experimental expenditure, enabling proactive budget management:

1. **Linear Accumulation**: If per-run costs are stable, cumulative cost grows linearly
2. **Sublinear Accumulation**: Decreasing per-run costs (learning/optimization) yield concave curves
3. **Superlinear Accumulation**: Increasing per-run costs (complexity growth) yield convex curves

### Budget Projection

Given observed cumulative cost $C_i$ at run index $i$ out of total planned runs $N$:

$$
\text{Projected Total Cost} = C_i + \frac{C_i}{i} \times (N - i)
$$

This assumes future runs have the same average cost as past runs. More sophisticated projections can fit trend lines (linear, polynomial) to the cumulative curve.

### Model Cost Efficiency

Comparing cumulative cost curves between models reveals:

- **Lower final value**: More cost-efficient model overall
- **Flatter slope**: Lower average per-run cost
- **Smoother curve**: More consistent per-run costs (lower variance)

### Connection to CoP Metric

Cost-of-Pass (CoP) represents average cost per successful solution:

$$
\text{CoP} = \frac{\text{Total Cost}}{\text{Pass Rate}}
$$

Cumulative cost provides the numerator (total cost), while pass-rate data from separate quality metrics provides the denominator. Together, they enable CoP calculation at any point during the experiment:

$$
\text{CoP}_i = \frac{\text{CumulativeCost}_i}{\text{Successful Runs}_{0:i}}
$$

## Visualization Details

### Chart Type

**Line chart** with continuous trajectories showing cumulative cost evolution.

### Axes

**X-axis**: `run_index:Q` (quantitative)

- **Title**: "Run Index (Chronological Order)"
- **Scale**: Linear, starting at 0
- **Interpretation**: Sequential position in execution timeline

**Y-axis**: `cumulative_cost:Q` (quantitative)

- **Title**: "Cumulative Cost (USD)"
- **Scale**: Linear, starting at 0
- **Interpretation**: Total expenditure up to and including this run

### Encodings

**Color**: `agent_model:N` (nominal)

- **Purpose**: Differentiate models
- **Scale**: Dynamic color scale derived from available models
- **Legend**: "Model"

**StrokeDash**: `agent_model:N` (nominal)

- **Purpose**: Provide secondary visual differentiation (accessibility)
- **Scale**:
  - 2 models: `[[1, 0], [5, 5]]` (solid, dashed)
  - 3+ models: `[[1, 0], [5, 5], [3, 3]]` (solid, dashed, dotted)
- **Legend**: "Model"

### Tooltip

Hover interactions display:

- `agent_model`: Model identifier
- `tier`: Testing tier
- `subtest`: Specific subtest
- `run_index`: Chronological position
- `cost_usd`: Individual run cost (formatted as `$.4f`)
- `cumulative_cost`: Total cost up to this point (formatted as `$.2f`)

### Chart Properties

- **Title**: "Cumulative Cost Over Runs"
- **Stroke Width**: Default line width
- **View**: No border (`strokeWidth=0`)

## Interpretation Guidelines

### Curve Shape Analysis

**Linear Trajectory**:

- Indicates stable, predictable per-run costs
- Easiest to budget and project
- Suggests consistent task complexity

**Concave Curve (Decreasing Slope)**:

- Per-run costs decreasing over time
- May indicate caching effects, learning, or optimization
- Favorable for long experiments

**Convex Curve (Increasing Slope)**:

- Per-run costs increasing over time
- May indicate growing task complexity or resource exhaustion
- Warning signal for budget overruns

**Step Function (Sudden Jumps)**:

- Individual high-cost runs creating discontinuities
- Investigate outlier runs causing jumps
- May indicate failure modes or expensive error recovery

### Model Comparison

**Lower Curve Dominance**:

- Model with consistently lower cumulative cost is more economical
- Check if quality metrics (pass-rate) are comparable before concluding superiority

**Parallel Curves**:

- Models have similar per-run costs but different starting points
- Investigate setup/initialization cost differences

**Converging Curves**:

- Initially different costs becoming similar over time
- May indicate adaptive behavior or caching equilibrium

**Diverging Curves**:

- Cost gap widening over time
- One model's costs growing faster than the other
- Critical for long-term deployment decisions

### Budget Management

**Actual vs. Projected Cost**:

1. Draw linear projection from current cumulative cost point
2. Compare to total budget allocation
3. If projection exceeds budget, consider:
   - Reducing remaining runs
   - Switching to lower-tier configurations
   - Pausing experiment for analysis

**Burn Rate Monitoring**:

- Calculate average cost per run: `cumulative_cost / run_index`
- Multiply by remaining runs to project final cost
- Alert if projected total exceeds budget threshold

### Anomaly Investigation

**Identifying Outliers**:

- Look for steep jumps (large vertical steps)
- Use tooltip to identify specific run causing jump
- Cross-reference with execution logs for that tier/subtest

**Root Cause Analysis**:

- Did the run fail and retry multiple times?
- Was the task unexpectedly complex?
- Did the agent enter an expensive reasoning loop?
- Were tool calls excessive?

## Related Figures

### Fig 6: Cost Distribution by Tier

- **Relationship**: Fig 6 shows cost distribution per tier; Fig 22 shows cumulative totals
- **Usage**: Fig 6 identifies which tiers are expensive; Fig 22 shows when costs accumulate
- **File**: `scylla/analysis/figures/cost_analysis.py:18`

### Fig 7: Token Distribution

- **Relationship**: Token usage drives cost; Fig 7 breaks down token types contributing to costs
- **Usage**: Investigate high-cost runs in Fig 22 by examining token distribution in Fig 7
- **File**: (would be in token analysis module if implemented)

### Fig 8: Cost-Quality Pareto

- **Relationship**: Fig 8 plots cost vs. quality trade-offs; Fig 22 focuses purely on cost accumulation
- **Usage**: Fig 22 identifies total cost; Fig 8 evaluates if that cost was worth it (quality)
- **File**: `scylla/analysis/figures/cost_analysis.py:60`

### CoP Metric Calculations

- **Relationship**: Cumulative cost provides the numerator for CoP calculation
- **Usage**: Final cumulative cost ÷ pass-rate = overall CoP for the experiment
- **Reference**: `.claude/shared/metrics-definitions.md:95`

## Code Reference

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/cost_analysis.py`

**Function**: `fig22_cumulative_cost(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None`

**Lines**: 209-284

**Key Implementation Details**:

1. **Data Sorting** (lines 221-226):

   ```python
   if "run_number" in runs_df.columns:
       runs_sorted = runs_df.sort_values(["agent_model", "tier", "subtest", "run_number"])
   else:
       runs_sorted = runs_df.sort_values(["agent_model", "tier", "subtest"])
   ```

   Ensures chronological ordering for accurate cumulative calculation.

2. **Cumulative Calculation** (lines 228-238):

   ```python
   for model in sorted(runs_sorted["agent_model"].unique()):
       model_runs = runs_sorted[runs_sorted["agent_model"] == model].copy()
       model_runs["cumulative_cost"] = model_runs["cost_usd"].cumsum()
       model_runs["run_index"] = range(len(model_runs))
       cumulative_data.append(model_runs)
   ```

   Computes cumulative sum independently per model group.

3. **Visualization Encoding** (lines 252-282):
   - Uses `mark_line()` for continuous trajectories
   - Encodes both color and strokeDash by `agent_model`
   - Includes rich tooltip with run-level and cumulative information

4. **Output** (line 284):

   ```python
   save_figure(chart, "fig22_cumulative_cost", output_dir, render)
   ```

   Saves as both interactive HTML and static PNG/PDF formats.

**Dependencies**:

- `pandas` for cumulative sum calculation (`cumsum()`)
- `altair` for declarative visualization
- `derive_tier_order()` for consistent tier ordering
- `get_color_scale()` for dynamic color/dash scales
- `save_figure()` for multi-format output

**Testing**: Unit tests should verify:

- Cumulative calculation correctness (sum matches expected totals)
- Proper handling of missing `run_number` column
- Multi-model grouping and independent cumsum per model
- Correct run_index assignment (0-indexed, sequential)
