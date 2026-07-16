# Cost-Quality Pareto Frontier

## Overview

The Cost-Quality Pareto Frontier figure visualizes the trade-off between mean cost and mean quality (score) across different agent models and tiers. It identifies the Pareto-efficient configurations where no other configuration achieves both lower cost and higher quality simultaneously.

This scatter plot uses a logarithmic x-axis for mean cost (USD) and a linear y-axis for mean score, with each point representing a (agent_model, tier) combination. Points on the Pareto frontier are connected with dashed lines per model, highlighting the optimal configurations that represent different cost-quality trade-offs.

## Purpose

The primary purposes of this figure are to:

1. **Identify optimal configurations**: Determine which (agent_model, tier) combinations are Pareto-efficient
2. **Visualize trade-offs**: Show the relationship between cost and quality across the ablation tiers
3. **Guide tier selection**: Help users select the most cost-effective tier for their quality requirements
4. **Compare models**: Understand how different agent models perform on the cost-quality frontier
5. **Inform optimization decisions**: Provide data-driven insights for balancing cost and performance

By identifying the Pareto frontier, stakeholders can select configurations that maximize quality within budget constraints or minimize costs while meeting quality thresholds.

## Data Source

The figure uses the `runs_df` DataFrame, which contains individual run-level data with the following key columns:

- `agent_model` (str): The agent model identifier (e.g., "claude-opus-4", "claude-sonnet-4")
- `tier` (str): The ablation tier (e.g., "T0", "T1", "T2", ..., "T6")
- `cost_usd` (float): The cost in USD for a single run
- `score` (float): The quality score for a single run (range: 0.0 to 1.0)

**Data Transformation:**

The raw run-level data is aggregated to compute mean cost and mean score per (agent_model, tier) combination:

```python
tier_stats = (
    runs_df.groupby(["agent_model", "tier"])
    .agg({"cost_usd": "mean", "score": "mean"})
    .reset_index()
)
tier_stats.columns = ["agent_model", "tier", "mean_cost", "mean_score"]
```

Each point in the scatter plot represents these aggregated statistics for a specific configuration.

## Mathematical Formulas

### Pareto Dominance

A point (configuration) is on the Pareto frontier if it is not dominated by any other point. The dominance relationship is defined as:

**Definition**: Point A dominates Point B if and only if:

- `cost_A ≤ cost_B` AND `score_A ≥ score_B`
- At least one inequality is strict (i.e., `cost_A < cost_B` OR `score_A > score_B`)

In other words, A dominates B when A is at least as good as B in both dimensions and strictly better in at least one dimension.

### Pareto Frontier

The Pareto frontier is the set of all non-dominated points:

```
Pareto_Frontier = {P | ∄Q : Q dominates P}
```

Where:

- `P` = a point (mean_cost, mean_score)
- `Q` = any other point in the dataset
- `∄` = "there does not exist"

### Per-Model Pareto Frontiers

The implementation computes separate Pareto frontiers for each agent model, allowing direct comparison of optimal configurations within each model family:

```python
for model in tier_stats["agent_model"].unique():
    model_mask = tier_stats["agent_model"] == model
    model_data = tier_stats[model_mask]

    pareto_mask = is_pareto_efficient(
        model_data["mean_cost"].values,
        model_data["mean_score"].values,
    )

    tier_stats.loc[model_mask, "is_pareto"] = pareto_mask
```

## Theoretical Foundation

### Pareto Efficiency Theory

Pareto efficiency is a fundamental concept in multi-objective optimization, economics, and game theory. It describes a state where resources are allocated such that it is impossible to make any one individual better off without making at least one other individual worse off.

**Key Principles:**

1. **Non-Domination**: A Pareto-efficient solution cannot be improved in one objective without degrading another
2. **Multiple Optima**: Unlike single-objective optimization, Pareto optimization typically yields a set of optimal solutions (the Pareto frontier)
3. **Trade-off Representation**: The Pareto frontier represents all possible optimal trade-offs between competing objectives

### Multi-Objective Optimization

In the context of agent evaluation, we face a bi-objective optimization problem:

- **Minimize**: Cost per run (USD)
- **Maximize**: Quality score (0.0 to 1.0)

These objectives are typically conflicting: higher-tier configurations (T3-T6) often achieve better scores but at increased cost due to additional features like delegation, hierarchy, or tooling.

### Non-Dominated Solutions

The Pareto frontier consists of all non-dominated solutions. The implementation uses an efficient algorithm to identify these points:

```python
def is_pareto_efficient(costs, scores):
    """Return boolean array of Pareto efficient points.

    A point (c1, s1) dominates (c2, s2) if c1 <= c2 AND s1 >= s2
    with at least one strict inequality.
    """
    is_efficient = np.ones(len(costs), dtype=bool)
    for i in range(len(costs)):
        if is_efficient[i]:
            # Check if point i is dominated by any other point
            dominated_by_others = np.logical_and(costs <= costs[i], scores >= scores[i]) & (
                np.logical_or(costs < costs[i], scores > scores[i])
            )
            dominated_by_others[i] = False  # Exclude self-comparison

            if np.any(dominated_by_others):
                is_efficient[i] = False
            else:
                # Point i is not dominated, remove all points it dominates
                dominated_by_i = np.logical_and(costs >= costs[i], scores <= scores[i]) & (
                    np.logical_or(costs > costs[i], scores < scores[i])
                )
                dominated_by_i[i] = False
                is_efficient[dominated_by_i] = False

    return is_efficient
```

**Algorithm Complexity**: O(n²) where n is the number of points per model. This is acceptable for typical dataset sizes (7 tiers × k models).

## Visualization Details

### Scatter Plot Components

The visualization consists of four layered components:

1. **Scatter Points**: Circle markers showing all (agent_model, tier) combinations
   - X-axis: `mean_cost` (logarithmic scale, USD)
   - Y-axis: `mean_score` (linear scale, 0.0 to 1.0)
   - Size: 100 (fixed)
   - Color: Dynamic color scale per agent model
   - Shape: Different marker shapes per model (circle, square, triangle-up, diamond, cross)

2. **Tier Labels**: Text annotations above each point
   - Text: Tier identifier (e.g., "T0", "T1", "T2")
   - Position: 15 pixels above point (`dy=-15`)
   - Font size: 10pt
   - Color: Black

3. **Pareto Frontier Lines**: Dashed lines connecting Pareto points
   - Style: Dashed (`strokeDash=[5, 5]`)
   - Color: Matches agent model color
   - Connects points sorted by cost (left to right)
   - Only drawn if model has 2+ Pareto points

4. **Tooltip**: Interactive hover information
   - Tier
   - Agent Model
   - Mean Cost (formatted as `$.4f`)
   - Mean Score (formatted as `.3f`)
   - Pareto Efficient (boolean)

### Axis Scales

- **X-axis (Mean Cost)**: Logarithmic scale to handle wide cost ranges (e.g., T0 at $0.01 vs T6 at $10.00)
- **Y-axis (Mean Score)**: Linear scale with dynamic domain computed from data with 15% padding for text labels

### Color and Shape Encoding

- **Color**: Agent models are assigned colors from a dynamic color scale
- **Shape**: Models cycle through available shapes: `["circle", "square", "triangle-up", "diamond", "cross"]`

This dual encoding (color + shape) improves accessibility and distinguishes models even in grayscale or for colorblind viewers.

### Output Files

The figure is saved in multiple formats:

1. **Vega-Lite JSON**: `fig08_cost_quality_pareto.json` (chart specification)
2. **PNG**: `fig08_cost_quality_pareto.png` (raster image, if `render=True`)
3. **PDF**: `fig08_cost_quality_pareto.pdf` (vector image, if `render=True`)
4. **CSV**: `fig08_cost_quality_pareto.csv` (data table with Pareto classification)

The CSV file includes all tier statistics with the `is_pareto` boolean column, enabling downstream analysis.

## Interpretation Guidelines

### Reading the Frontier

1. **Pareto Points**: Points on the frontier (connected by dashed lines) represent optimal configurations
2. **Dominated Points**: Points below/right of the frontier are suboptimal (lower quality for the cost or higher cost for the quality)
3. **Model Comparison**: Compare frontier lines across models to identify which model offers the best cost-quality trade-offs
4. **Tier Progression**: Observe how tiers advance along the frontier (generally left-to-right as tiers increase)

### Decision-Making Scenarios

**Scenario 1: Budget-Constrained Selection**

- Identify maximum acceptable cost on x-axis
- Select the Pareto point with highest score below that cost threshold
- This maximizes quality within budget

**Scenario 2: Quality-Threshold Selection**

- Identify minimum acceptable score on y-axis
- Select the Pareto point with lowest cost above that quality threshold
- This minimizes cost while meeting quality requirements

**Scenario 3: Model Selection**

- Compare Pareto frontiers across models
- Select the model whose frontier dominates others in the region of interest
- Consider shape differences: some models may excel at low-cost tiers, others at high-quality tiers

### Implications for Tier Selection

The Pareto frontier reveals several key insights:

1. **Diminishing Returns**: The frontier typically shows diminishing returns - each additional dollar yields smaller quality improvements
2. **Tier Gaps**: Large vertical gaps between adjacent Pareto points indicate tiers with significant quality jumps
3. **Cost Efficiency**: Steep frontier regions indicate high cost efficiency (large quality gains for small cost increases)
4. **Plateau Regions**: Flat frontier regions suggest tiers with minimal quality improvement despite cost increases

### Statistical Considerations

- **Mean vs Median**: The figure uses mean cost and mean score, which can be affected by outliers. Consider reviewing histograms (Fig 6) for distribution details.
- **Variance**: Points on the frontier may have different variance in cost or score. High-variance points represent less consistent performance.
- **Sample Size**: Ensure adequate sample sizes per (agent_model, tier) combination for reliable mean estimates.

### Limitations

1. **Aggregation**: Mean statistics hide within-tier variance
2. **Independence Assumption**: Assumes cost and score are the only relevant objectives (ignores latency, memory, etc.)
3. **Per-Model Frontiers**: Computing separate frontiers per model prevents cross-model dominance detection
4. **Static Analysis**: Does not account for dynamic factors like caching, learning effects, or temporal changes

## Related Figures

### Fig 6: Cost Distribution by Tier

**File**: `scylla/analysis/figures/cost_analysis.py:18-58`

**Relationship**: Fig 6 provides detailed cost distributions per tier using histograms with log-scale bins. While the Pareto frontier shows mean cost, Fig 6 reveals the underlying distribution, helping assess cost variability and outliers.

**Use Together**: Review Fig 6 to understand cost variance before selecting a tier from the Pareto frontier. High variance indicates less predictable costs.

### Fig 21: Cost-Quality Regression (if exists)

**Hypothetical Reference** (verify existence)

**Relationship**: A cost-quality regression figure would fit a continuous model to the cost-score relationship, while the Pareto frontier identifies discrete optimal points. Regression provides interpolation and confidence intervals.

**Use Together**: Use regression for predictive modeling and the Pareto frontier for decision-making on specific tier configurations.

### Additional Related Analyses

- **Token Distribution Figures**: Understanding token usage patterns helps explain cost differences between tiers
- **Pass Rate Figures**: Quality scores may be derived from pass rates; reviewing pass rate distributions provides context
- **Latency Figures**: Cost and latency often correlate; consider latency when selecting Pareto-optimal tiers

## Code Reference

**Primary Function**: `fig08_cost_quality_pareto`

**Location**: `/home/mvillmow/Scylla/scylla/analysis/figures/cost_analysis.py:60-207`

**Function Signature**:

```python
def fig08_cost_quality_pareto(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None:
    """Generate Fig 8: Cost vs Quality Pareto Frontier.

    Scatter plot showing mean cost vs mean score, with Pareto frontier line.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

**Dependencies**:

- `scylla.analysis.figures.get_color_scale`: Dynamic color scale generation
- `scylla.analysis.figures.spec_builder.compute_dynamic_domain`: Y-axis domain calculation with padding
- `scylla.analysis.figures.spec_builder.save_figure`: Multi-format figure saving (JSON, PNG, PDF)

**Key Implementation Details**:

1. **Aggregation** (lines 72-77): Groups runs by (agent_model, tier) and computes mean cost and mean score
2. **Pareto Computation** (lines 81-122): Implements `is_pareto_efficient` function and applies per-model
3. **Visualization** (lines 124-200): Constructs Altair chart with scatter, labels, and frontier lines
4. **Export** (lines 202-206): Saves figure in multiple formats plus CSV data table

**Algorithm**:

```python
# Simplified Pareto detection logic
for model in models:
    for point_i in model_points:
        is_dominated = any(
            (cost_j <= cost_i and score_j >= score_i) and
            (cost_j < cost_i or score_j > score_i)
            for point_j in model_points if j != i
        )
        if not is_dominated:
            mark_as_pareto(point_i)
```

**Testing**: Verify using unit tests that check:

- Pareto detection correctness on synthetic data with known frontiers
- Handling of edge cases (single point, all points on frontier, no points on frontier)
- CSV output contains correct `is_pareto` classifications
- Visual output matches expected layout

**Example Usage**:

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.cost_analysis import fig08_cost_quality_pareto

# Load runs data
runs_df = pd.read_csv("runs.csv")

# Generate figure
output_dir = Path("output/figures")
output_dir.mkdir(parents=True, exist_ok=True)
fig08_cost_quality_pareto(runs_df, output_dir, render=True)

# Outputs:
# - output/figures/fig08_cost_quality_pareto.json
# - output/figures/fig08_cost_quality_pareto.png
# - output/figures/fig08_cost_quality_pareto.pdf
# - output/figures/fig08_cost_quality_pareto.csv
```
