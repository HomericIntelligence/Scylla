# Figure 12: Consistency Analysis

## Overview

Figure 12 visualizes consistency scores across testing tiers through a line chart with confidence bands. This figure measures output consistency by analyzing run-to-run variance for each tier, revealing how reliably different agent configurations produce similar results when executed multiple times.

**Key Insight**: High consistency (values near 1.0) indicates deterministic, reliable agent behavior, while low consistency suggests unstable performance that varies significantly across repeated runs.

## Purpose

- **Primary Goal**: Measure tier reliability and stability by quantifying run-to-run variance
- **Use Cases**:
  - Identify tiers with unstable performance requiring investigation
  - Compare consistency-performance tradeoffs across agent configurations
  - Validate that enhancements (skills, tools, hierarchy) improve determinism
  - Detect configurations that introduce non-deterministic behavior
- **Audience**: Researchers evaluating agent reliability, experiment designers optimizing for consistent outcomes

## Data Source

**DataFrame**: `runs_df`

**Columns Used**:

- `agent_model` (str): Model identifier (e.g., "opus-4-6", "sonnet-4")
- `tier` (str): Testing tier (T0-T6)
- `subtest` (str): Specific test within tier
- `score` (float): Individual run score [0.0, 1.0]

**Source File**: `/home/mvillmow/Scylla/scylla/analysis/figures/model_comparison.py:177-301`

**Data Requirements**:

- Multiple runs per subtest (minimum 2 runs for meaningful consistency)
- One row per run evaluation
- Typical dataset: Multiple repetitions of each (tier, subtest, model) combination
- Handles single-run subtests gracefully (returns point estimate with no CI)

## Mathematical Formulas

### Consistency Metric

**Formula**:

```
Consistency = 1 - CV
            = 1 - (σ / μ)
```

Where:

- `CV` = Coefficient of Variation
- `σ` (sigma) = Standard deviation of scores across runs
- `μ` (mu) = Mean score across runs

**Alternative Expression**:

```
CV = σ / μ
Consistency = 1 - CV
```

**Domain**: `[0, 1]`

- `1.0` = Perfect consistency (zero variance)
- `0.0` = Maximum inconsistency (σ ≥ μ)
- Values are clamped to `[0, 1]` range

**Special Cases**:

- If `μ = 0`: Consistency = 0.0 (undefined CV, conservative estimate)
- If `σ = 0`: Consistency = 1.0 (perfect determinism)
- If `CV > 1`: Consistency clamped to 0.0 (variance exceeds mean)

### Bootstrap Confidence Intervals

**Method**: BCa (Bias-Corrected and Accelerated) Bootstrap

**Configuration**:

- Confidence level: 95% (default from config)
- Resamples: 10,000 (default from config)
- Applied to: Mean consistency across subtests within each tier

**Formula**:

```
CI = Bootstrap_BCa(consistency_per_subtest, confidence=0.95, n=10000)
   → (mean_consistency, ci_low, ci_high)
```

**Constraints**:

- Requires ≥2 subtests for bootstrap
- Single-subtest tiers use point estimate: `ci_low = ci_high = mean`
- CI bounds clamped to `[0, 1]`

## Theoretical Foundation

### Reliability Theory

**Core Concept**: Consistency quantifies the inverse of relative variability, a key reliability metric in systems analysis.

**Coefficient of Variation (CV)**:

- Standard measure of dispersion normalized by mean
- Dimensionless metric allowing cross-scale comparison
- Used in reliability engineering to assess process stability

**Consistency as Inverse CV**:

- Transforms variance-based metric into reliability-based metric
- Higher values = more reliable (opposite of CV)
- Intuitive interpretation: "How much consistency exists?"

### Run-to-Run Variance Sources

**Stochastic Components**:

1. **Model Sampling**: LLM temperature and nucleus sampling
2. **Tool Execution**: Non-deterministic external tools (e.g., web search)
3. **Timing Dependencies**: Race conditions in async operations
4. **Environment State**: File system state, API availability

**Deterministic Factors**:

1. **Prompt Engineering**: Clear, unambiguous instructions reduce variance
2. **Structured Outputs**: JSON schemas enforce consistency
3. **Validation Loops**: Error checking and retry logic stabilize results
4. **Tool Reliability**: Deterministic tools (e.g., file I/O) improve consistency

### Acceptable Consistency Levels

**Interpretation Scale**:

| Range | Interpretation | Action |
|-------|----------------|--------|
| 0.90 - 1.00 | Excellent | Highly reliable, production-ready |
| 0.80 - 0.90 | Good | Acceptable for most use cases |
| 0.70 - 0.80 | Moderate | Review for instability sources |
| 0.60 - 0.70 | Fair | Investigate non-determinism |
| < 0.60 | Poor | Requires immediate attention |

**Context Matters**:

- **High-stakes applications**: Require ≥0.90 consistency
- **Research/exploration**: 0.70-0.80 may be acceptable
- **Stochastic tasks**: Lower consistency expected (e.g., creative generation)

## Visualization Details

### Chart Components

**Chart Type**: Line chart with confidence bands

**Layers**:

1. **Confidence Band** (bottom layer):
   - `mark_area` with 20% opacity
   - Fills region between `ci_low` and `ci_high`
   - Color: Matches model line color

2. **Line Chart** (top layer):
   - `mark_line` with point markers
   - Connects mean consistency across tiers
   - Color-coded by agent model

**Axes**:

- **X-axis**: Tier (ordinal, T0-T6)
  - Title: "Tier"
  - Sorted by tier order
- **Y-axis**: Consistency Score (quantitative, dynamic domain)
  - Title: "Consistency Score (1 - CV)"
  - Domain: Auto-scaled from data including CI bounds
  - Range: Typically [0.5, 1.0] for well-behaved agents

**Color Encoding**:

- Scale: Dynamic color palette per model
- Domain: Sorted list of unique agent models
- Range: Generated by `get_color_scale("models", models)`

**Title**: "Consistency Score by Tier (Higher = More Deterministic)"

**Tooltip**:

- Tier (ordinal)
- Agent Model (nominal)
- Mean Consistency (formatted to 3 decimals)
- CI Low (formatted to 3 decimals)
- CI High (formatted to 3 decimals)

### Dynamic Domain Calculation

**Function**: `compute_dynamic_domain_with_ci(mean, ci_low, ci_high)`

**Algorithm**:

1. Find global minimum across all `ci_low` values
2. Find global maximum across all `ci_high` values
3. Add padding for visual clarity
4. Ensure domain includes entire confidence band

**Benefit**: Prevents clipping of confidence bands while maintaining readable scale

## Interpretation Guidelines

### High Consistency (≥0.85)

**Characteristics**:

- Narrow confidence bands
- Scores tightly clustered across runs
- Low coefficient of variation (CV < 0.15)

**Interpretation**:

- Tier produces reliable, repeatable results
- Agent behavior is deterministic
- Configuration is production-ready

**Potential Causes**:

- Well-structured prompts and workflows
- Deterministic tool usage
- Effective validation and error handling
- Low LLM temperature settings

### Low Consistency (<0.70)

**Characteristics**:

- Wide confidence bands
- High run-to-run score variance
- High coefficient of variation (CV > 0.30)

**Interpretation**:

- Tier exhibits unstable performance
- Results are unpredictable
- Configuration needs debugging

**Potential Causes**:

- Ambiguous prompts or rubrics
- Non-deterministic tool dependencies (e.g., web search)
- Race conditions or timing issues
- Evaluation judge inconsistency

### Consistency vs. Performance Tradeoffs

**Trade-off Scenarios**:

1. **High Consistency, Low Performance**:
   - Agent reliably fails or underperforms
   - **Action**: Improve capability, not just reliability

2. **High Performance, Low Consistency**:
   - Agent sometimes succeeds, sometimes fails
   - **Action**: Reduce variance through better prompts/validation

3. **Optimal Balance**:
   - High consistency + high performance
   - **Goal**: Maximize both metrics simultaneously

**Analyzing Trade-offs**:

- Cross-reference with Fig 01 (score variance)
- Compare consistency across tiers as capabilities increase
- Expected pattern: Consistency should increase or remain stable as tiers advance

### Tier-to-Tier Trends

**Expected Patterns**:

**Scenario 1: Monotonic Improvement**:

- Consistency increases T0 → T6
- Interpretation: Enhancements (skills, tools) improve determinism
- Ideal outcome for capability additions

**Scenario 2: Plateau**:

- Consistency stable across tiers
- Interpretation: Variance sources are tier-independent (e.g., LLM sampling)
- Acceptable if absolute consistency is high

**Scenario 3: Degradation**:

- Consistency decreases at higher tiers
- Interpretation: Added complexity introduces instability
- **Action**: Investigate which enhancement caused degradation

**Scenario 4: U-Shape**:

- High at T0, drops at T2-T4, recovers at T6
- Interpretation: Mid-tier complexity introduces variance, resolved at higher tiers
- Common pattern during capability scaling

## Related Figures

- **Fig 01** (`fig01_score_variance_by_tier`): Score variance box plots
  - Shows raw score distributions (not normalized by mean)
  - Complements consistency analysis with absolute variance view
  - Useful for understanding variance magnitude alongside relative consistency

- **Fig 03** (`fig03_consensus_variance`): Consensus score variance
  - Analyzes variance in consensus scores across judges
  - Consistency measures run-to-run variance, consensus measures judge-to-judge variance
  - Both metrics inform overall evaluation reliability

- **Fig 10** (`fig10_model_comparison_bars`): Model comparison bar chart
  - Shows mean scores by tier and model
  - Cross-reference to assess performance-consistency correlation
  - Identifies high-performance + high-consistency configurations

## Code Reference

### Source Files

**Primary Implementation**: `/home/mvillmow/Scylla/scylla/analysis/figures/model_comparison.py:177-301`

**Consistency Calculation**: `/home/mvillmow/Scylla/scylla/analysis/stats.py:377-394`

**Bootstrap CI**: `/home/mvillmow/Scylla/scylla/analysis/stats.py:47-120`

### Function Signature

```python
def fig12_consistency(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True
) -> None:
    """Generate Fig 12: Consistency by Tier.

    Line plot with confidence bands showing consistency scores.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF
    """
```

### Key Technical Decisions

**Per-Subtest Calculation**:

- Computes consistency for each (model, tier, subtest) combination
- Aggregates subtest consistencies using bootstrap mean ± CI
- **Rationale**: Captures within-tier heterogeneity across different test types
- **Benefit**: More robust than tier-level aggregation alone

**Bootstrap Aggregation**:

- Uses bootstrap CI on subtest consistencies (not raw scores)
- **Rationale**: Accounts for uncertainty in tier-level consistency estimate
- **Trade-off**: More conservative bands vs. direct calculation

**Clamping Strategy**:

- Clamps CI bounds to `[0, 1]` after bootstrap
- **Rationale**: Bootstrap can produce out-of-range values for bounded metrics
- **Implementation**: `consistency_df["ci_low"].clip(lower=0)`, `consistency_df["ci_high"].clip(upper=1)`

### Algorithm

1. **Derive Tier Order**:

   ```python
   tier_order = derive_tier_order(runs_df)
   ```

2. **Compute Per-Subtest Consistency**:

   ```python
   for model in runs_df["agent_model"].unique():
       for tier in tier_order:
           tier_subtests = runs_df[
               (runs_df["agent_model"] == model) &
               (runs_df["tier"] == tier)
           ]["subtest"].unique()

           for subtest in tier_subtests:
               subtest_runs = runs_df[
                   (runs_df["agent_model"] == model) &
                   (runs_df["tier"] == tier) &
                   (runs_df["subtest"] == subtest)
               ]

               if len(subtest_runs) > 1:
                   mean_score = subtest_runs["score"].mean()
                   std_score = subtest_runs["score"].std()
                   consistency = compute_consistency(mean_score, std_score)
                   subtest_consistencies.append(consistency)
   ```

3. **Aggregate with Bootstrap CI**:

   ```python
   if len(subtest_consistencies) >= 2:
       mean_consistency, ci_low, ci_high = bootstrap_ci(
           pd.Series(subtest_consistencies)
       )
   else:
       mean_consistency = subtest_consistencies[0]
       ci_low = ci_high = mean_consistency
   ```

4. **Clamp CI Bounds**:

   ```python
   consistency_df["ci_low"] = consistency_df["ci_low"].clip(lower=0)
   consistency_df["ci_high"] = consistency_df["ci_high"].clip(upper=1)
   ```

5. **Build Visualization**:

   ```python
   line = alt.Chart(consistency_df).mark_line(point=True).encode(
       x=alt.X("tier:O", title="Tier", sort=tier_order),
       y=alt.Y("mean_consistency:Q", title="Consistency Score (1 - CV)"),
       color=alt.Color("agent_model:N", title="Agent Model"),
       tooltip=[...]
   )

   band = alt.Chart(consistency_df).mark_area(opacity=0.2).encode(
       x=alt.X("tier:O", sort=tier_order),
       y="ci_low:Q",
       y2="ci_high:Q",
       color=alt.Color("agent_model:N"),
   )

   chart = (band + line).properties(
       title="Consistency Score by Tier (Higher = More Deterministic)"
   )
   ```

6. **Save Figure**:

   ```python
   save_figure(chart, "fig12_consistency", output_dir, render)
   ```

## Output Files

### File Naming Convention

**Pattern**: `fig12_consistency.{ext}`

**Generated Files**:

- `fig12_consistency.vl.json` - Vega-Lite specification
- `fig12_consistency.csv` - Data slice (consistency per tier/model)
- `fig12_consistency.png` - Rendered image (300 DPI, if render=True)
- `fig12_consistency.pdf` - Vector format (if render=True)

### Output Directory

**Default**: `docs/figures/`

**Total Files Generated**: 4 files (with rendering enabled)

## Usage Example

```python
from pathlib import Path
import pandas as pd
from scylla.analysis.figures.model_comparison import fig12_consistency
from scylla.analysis.loader import load_experiment_data

# Load experiment data
experiments = load_experiment_data("~/fullruns/")
runs_df = experiments["runs_df"]

# Generate figure (specs only, no rendering)
output_dir = Path("docs/figures")
fig12_consistency(runs_df, output_dir, render=False)

# Generate with rendering (PNG + PDF)
fig12_consistency(runs_df, output_dir, render=True)
```

### Expected Output

```
docs/figures/
├── fig12_consistency.vl.json
├── fig12_consistency.csv
├── fig12_consistency.png
└── fig12_consistency.pdf
```

### Viewing the Figure

**Vega-Lite Spec (Recommended)**:

```bash
# Open in Vega Editor
open https://vega.github.io/editor/
# Upload fig12_consistency.vl.json
```

**CSV Data**:

```bash
# Inspect raw data
head docs/figures/fig12_consistency.csv
```

**Rendered Images**:

```bash
# View PNG
open docs/figures/fig12_consistency.png

# Include in LaTeX
\includegraphics{docs/figures/fig12_consistency.pdf}
```

## Changelog

- **2026-02-12**: Initial documentation created for issue #458
