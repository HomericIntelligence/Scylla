# Latency Analysis

## Overview

Figure 13 visualizes the latency breakdown of evaluation runs across tiers and agent models. The figure displays mean execution time split into two distinct phases: agent execution and judge evaluation. This stacked bar chart provides insight into where computational time is spent during the evaluation process, enabling identification of performance bottlenecks and optimization opportunities.

## Purpose

The latency analysis figure serves multiple purposes:

1. **Performance Bottleneck Identification**: Reveals which phase (agent execution vs judge evaluation) dominates the total latency
2. **Tier Comparison**: Shows how execution time scales across testing tiers (T0-T6)
3. **Model Performance**: Compares latency characteristics across different agent models
4. **Resource Planning**: Informs infrastructure decisions by quantifying time requirements
5. **Cost-Time Tradeoffs**: Enables analysis of the relationship between latency and other metrics like cost or quality

## Data Source

**Primary DataFrame**: `runs_df` (Runs DataFrame)

**Required Columns**:

- `agent_model`: Model identifier (e.g., "claude-opus-4", "claude-sonnet-4")
- `tier`: Testing tier (T0, T1, T2, T3, T4, T5, T6)
- `agent_duration_seconds`: Time spent in agent execution phase (float, seconds)
- `judge_duration_seconds`: Time spent in judge evaluation phase (float, seconds)

**Aggregation Method**: Mean duration calculated per (agent_model, tier) combination

## Mathematical Formulas

### Mean Duration Calculation

For each combination of agent model and tier:

```
agent_duration_mean = mean(agent_duration_seconds)
judge_duration_mean = mean(judge_duration_seconds)
total_duration_mean = agent_duration_mean + judge_duration_mean
```

### Phase Proportion

The relative contribution of each phase to total latency:

```
agent_proportion = agent_duration_mean / total_duration_mean
judge_proportion = judge_duration_mean / total_duration_mean
```

Where:

- `agent_proportion + judge_proportion = 1.0`
- Values range from 0.0 to 1.0

### Latency Budget Analysis

For capacity planning and SLA definition:

```
p95_latency = percentile(total_duration, 95)
max_concurrent_runs = budget_hours * 3600 / p95_latency
```

## Theoretical Foundation

### Performance Analysis Concepts

**Amdahl's Law Application**: The stacked visualization helps identify which phase limits parallelization opportunities. If judge evaluation dominates, parallel judging can reduce total time.

**Critical Path Analysis**: The total stacked height represents the critical path duration for a single evaluation run, essential for pipeline scheduling.

**Resource Utilization**: Phase breakdown indicates whether optimization efforts should focus on:

- Agent execution (model inference, tool calls, reasoning)
- Judge evaluation (LLM-based assessment, criteria checking)

### Latency Budget Framework

Latency budgets define acceptable performance thresholds:

| Tier | Expected Agent (s) | Expected Judge (s) | Total Budget (s) |
|------|-------------------|-------------------|------------------|
| T0   | 10-30             | 5-15              | 15-45            |
| T1   | 20-60             | 10-30             | 30-90            |
| T2   | 40-120            | 15-45             | 55-165           |
| T3   | 60-180            | 20-60             | 80-240           |
| T4   | 90-270            | 25-75             | 115-345          |
| T5   | 120-360           | 30-90             | 150-450          |
| T6   | 150-600           | 40-120            | 190-720          |

These budgets inform SLA definitions and timeout configurations.

## Visualization Details

### Chart Type

**Stacked Bar Chart** with faceting:

- X-axis: Tier (T0, T1, T2, T3, T4, T5, T6)
- Y-axis: Mean Duration (seconds)
- Stack: Two phases (Agent Execution, Judge Evaluation)
- Facets: Separate panels per agent_model

### Visual Encoding

**Colors**:

- Agent Execution: Retrieved from centralized color palette (`get_color_scale("phases", ...)`)
- Judge Evaluation: Retrieved from centralized color palette (`get_color_scale("phases", ...)`)
- Colors are consistent across all figures using the phase category

**Dimensions**:

- Chart width: 350 pixels per facet
- Chart height: 250 pixels
- Title: "Latency Breakdown by Tier"

### Interactive Elements

**Tooltips** display on hover:

- Tier: Testing tier identifier
- Phase: "Agent Execution" or "Judge Evaluation"
- Duration (s): Mean duration formatted to 2 decimal places

**Sort Order**:

- Tiers: Natural order (T0, T1, ..., T6) derived from data
- Phases: Ascending order (Agent before Judge in stack)

### Data Transformation Pipeline

1. **Aggregation**: Group by (agent_model, tier), compute mean of duration columns
2. **Tier Ordering**: Derive natural tier order from data using `derive_tier_order()`
3. **Reshape**: Melt to long format with columns: agent_model, tier, phase, duration
4. **Labeling**: Map phase variable names to human-readable labels
5. **Color Assignment**: Get color scale from centralized palette
6. **Chart Generation**: Create Altair specification with stacking and faceting
7. **Export**: Save as Vega-Lite JSON, PNG, and PDF via `save_figure()`

## Interpretation Guidelines

### Acceptable Latency Ranges

**Good Performance** (within budget):

- Total latency ≤ upper bound of tier budget
- Agent phase dominates (>60% of total)
- Minimal variance across runs

**Acceptable Performance** (near budget):

- Total latency within 20% of budget
- Balanced phase distribution (40-60% each)
- Moderate variance

**Poor Performance** (exceeds budget):

- Total latency >120% of budget
- Judge phase dominates (>60% of total, indicating evaluation bottleneck)
- High variance (unreliable performance)

### Pattern Analysis

**Tier Scaling Patterns**:

- Linear scaling: Latency increases proportionally with tier complexity (expected)
- Sublinear scaling: Efficiency gains at higher tiers (good optimization)
- Superlinear scaling: Performance degradation at higher tiers (investigate bottlenecks)

**Phase Distribution Patterns**:

- Agent-heavy: Complex reasoning, many tool calls, extended thinking
- Judge-heavy: Complex criteria, multi-dimensional evaluation, slow judge model
- Balanced: Well-optimized evaluation pipeline

### Optimization Strategies

Based on observed patterns:

1. **If Agent Execution Dominates**:
   - Use faster models for simpler tiers
   - Optimize prompts to reduce reasoning steps
   - Cache common tool call results
   - Reduce extended thinking budget

2. **If Judge Evaluation Dominates**:
   - Use faster judge models
   - Simplify evaluation criteria
   - Implement parallel judging
   - Cache judgment patterns

3. **If Both Phases Are Slow**:
   - Re-evaluate tier complexity
   - Consider tier merging
   - Review timeout configurations
   - Investigate infrastructure bottlenecks

## Related Figures

### Complementary Analyses

- **Figure 22**: Cumulative cost via time - Shows how cost accumulates over evaluation duration
- **Figure 15a/15b/15c**: Subtest heatmaps - Detailed pass/fail patterns that may correlate with latency
- **Figure 8**: Token usage by tier - Token counts often correlate with latency

### Cross-Metric Insights

**Latency vs Cost**:

- Higher latency often correlates with higher token usage and cost
- Judge latency may be disproportionate to judge cost if using faster, cheaper models

**Latency vs Quality**:

- Longer agent latency may indicate more thorough reasoning (higher quality)
- Optimal tier balances latency, cost, and quality

**Latency vs Variance**:

- High latency variance indicates unstable performance
- Compare with variance figures to identify consistency issues

## Code Reference

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/subtest_detail.py`

**Function**: `fig13_latency(runs_df: pd.DataFrame, output_dir: Path, render: bool = True)`

**Line Range**: 17-84

**Key Dependencies**:

- `altair`: Chart generation and Vega-Lite specification
- `pandas`: Data aggregation and transformation
- `scylla.analysis.figures.derive_tier_order`: Natural tier sorting
- `scylla.analysis.figures.get_color_scale`: Centralized color palette
- `scylla.analysis.figures.spec_builder.save_figure`: Multi-format export

**Output Files**:

- `fig13_latency.json`: Vega-Lite specification
- `fig13_latency.png`: Raster image (if render=True)
- `fig13_latency.pdf`: Vector graphic (if render=True)
- `fig13_latency.csv`: Source data for chart

**Configuration**: Color palette loaded from `scylla/analysis/config.yaml` under `colors.phases` category.
