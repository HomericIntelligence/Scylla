# Figure 14: Inter-Judge Agreement

## Overview

Figure 14 visualizes inter-judge agreement through pairwise scatter plots comparing judge scores across all evaluation runs. This figure is generated separately for each tier, producing a 3x3 scatter matrix that displays all pairwise judge comparisons.

**Key Characteristics**:

- Separate figure per tier (T0-T6)
- 3x3 scatter matrix layout
- Pairwise comparisons: Judge 1 vs 2, Judge 2 vs 3, Judge 1 vs 3
- Faceted by comparison pair (columns) and agent model (rows)
- Shared x/y scales for direct comparison

## Purpose

The primary purposes of Figure 14 are to:

1. **Validate Judge Consistency**: Assess whether multiple independent judge runs produce similar scores for the same evaluation
2. **Identify Systematic Disagreements**: Detect patterns where specific judge pairs consistently disagree
3. **Evaluate Multi-Judge Protocol**: Verify that the 3-run consensus approach produces reliable results
4. **Diagnose Evaluation Quality**: Low agreement may indicate ambiguous rubrics, unclear criteria, or borderline cases

**What Good Agreement Looks Like**:

- Points cluster tightly around the diagonal (y = x line)
- High correlation across all three pairwise comparisons
- Minimal scatter perpendicular to the diagonal

**What Poor Agreement Looks Like**:

- Wide scatter away from the diagonal
- Different patterns in different pairwise comparisons
- Systematic bias (points consistently above or below diagonal)

## Data Source

**Input**: `judges_df` - Judge scores DataFrame from `scylla.analysis.loader.load_judges_results()`

**Required Columns**:

- `agent_model` - Agent model being evaluated (e.g., "claude-opus-4-5")
- `tier` - Testing tier (T0-T6)
- `subtest` - Subtest identifier within the tier
- `run_number` - Run number (1-10)
- `judge_number` - Judge run number (1-3)
- `judge_score` - Judge weighted score [0.0, 1.0]

**Data Transformation**:

1. Pivot judges_df from long to wide format using `judge_number` as columns
2. Creates columns: `judge_1`, `judge_2`, `judge_3`
3. Drop rows with missing judge scores (incomplete consensus)
4. Generate pairwise comparison records for all three judge pairs

## Mathematical Formulas

### Pairwise Agreement

For each pair of judges (i, j), agreement can be quantified using:

**Pearson Correlation Coefficient**:

```
r = Σ[(x_i - x̄)(y_i - ȳ)] / √[Σ(x_i - x̄)² · Σ(y_i - ȳ)²]

where:
  x_i = score from judge i
  y_i = score from judge j
  x̄ = mean score from judge i
  ȳ = mean score from judge j
```

**Interpretation**:

- r = 1.0: Perfect positive correlation (identical scores)
- r = 0.0: No correlation (random agreement)
- r = -1.0: Perfect negative correlation (inverse scores)

**Good agreement**: r > 0.70 (strong positive correlation)

### Cohen's Kappa (for binary pass/fail)

While this figure shows continuous scores, agreement can also be measured using Cohen's Kappa for binary pass/fail decisions:

```
κ = (p_o - p_e) / (1 - p_e)

where:
  p_o = observed agreement proportion
  p_e = expected agreement by chance
```

**Interpretation Thresholds** (Landis & Koch, 1977):

| Kappa | Agreement Level |
|-------|----------------|
| < 0.00 | Poor |
| 0.00 - 0.20 | Slight |
| 0.21 - 0.40 | Fair |
| 0.41 - 0.60 | Moderate |
| 0.61 - 0.80 | Substantial |
| 0.81 - 1.00 | Almost Perfect |

### Mean Absolute Difference

Simple measure of average disagreement:

```
MAD = (1/n) · Σ|score_i - score_j|

where:
  n = number of evaluation runs
```

**Interpretation**:

- MAD = 0.00: Perfect agreement (identical scores)
- MAD = 0.05: Excellent agreement (±5% variation)
- MAD = 0.10: Good agreement (±10% variation)
- MAD > 0.20: Concerning disagreement (>20% variation)

## Theoretical Foundation

### Inter-Rater Reliability (IRR)

Inter-rater reliability measures the degree of agreement among independent raters evaluating the same phenomena. In Scylla, this applies to:

- **Raters**: 3 independent judge runs (same model, different executions)
- **Subjects**: AI agent evaluation runs (tier + subtest + run_number)
- **Scale**: Continuous scores [0.0, 1.0] representing weighted rubric scores

**Key Assumptions**:

1. **Independence**: Each judge run operates independently without knowledge of other judge scores
2. **Common Rubric**: All judges use the same evaluation criteria and rubric
3. **Stochastic Variance**: Disagreements arise from inherent non-determinism in LLM evaluation

### Sources of Disagreement

Systematic disagreement can arise from:

1. **Ambiguous Criteria**: Rubric requirements lack clear pass/fail boundaries
2. **Subjective Categories**: Evaluation dimensions require qualitative judgment
3. **Borderline Cases**: Agent output falls near threshold boundaries
4. **Model Non-Determinism**: LLM judges exhibit inherent stochastic behavior
5. **Tool Execution Variance**: Different judge runs may observe different artifacts

### Consensus Mechanisms

Scylla uses **confidence-weighted averaging** to resolve disagreements:

```
consensus_score = Σ(score_i × confidence_i) / Σ(confidence_i)

where:
  score_i = judge i's score
  confidence_i = judge i's self-reported confidence [0.0, 1.0]
```

This mechanism:

- Weights high-confidence judgments more heavily
- Reduces impact of uncertain scores
- Provides single consensus score for downstream metrics

## Visualization Details

### Chart Structure

**Type**: Scatter plot matrix (faceted)

**Layout**:

- **Columns**: Comparison pairs ("Judge 1 vs 2", "Judge 2 vs 3", "Judge 1 vs 3")
- **Rows**: Agent models (e.g., "claude-opus-4-5", "claude-sonnet-4")
- **Cell**: Scatter plot with 60px circles, 0.6 opacity

**Axes**:

- **X-axis**: First judge score [0.0, 1.0]
- **Y-axis**: Second judge score [0.0, 1.0]
- **Scales**: Shared across all panels for direct comparison
- **Domain**: Dynamically computed with 10% padding, rounded to nearest 0.05

**Visual Encoding**:

- **Position X**: Score from first judge in pair
- **Position Y**: Score from second judge in pair
- **Tooltip**: Comparison pair, judge identifiers, both scores (3 decimal places)

### Dynamic Domain Calculation

The figure uses `compute_dynamic_domain()` to calculate tight axis bounds:

```python
# Compute tight domain from data
score_x_domain = compute_dynamic_domain(tier_pairs_df["score_x"])
score_y_domain = compute_dynamic_domain(tier_pairs_df["score_y"])

# Applied to both axes
x=alt.X("score_x:Q", scale=alt.Scale(domain=score_x_domain))
y=alt.Y("score_y:Q", scale=alt.Scale(domain=score_y_domain))
```

**Algorithm**:

1. Compute data min/max
2. Add 10% padding on both sides
3. Enforce minimum range of 0.1
4. Round to nearest 0.05 for clean labels
5. Clamp to [0.0, 1.0]

### Per-Tier Figures

Unlike most figures that aggregate all tiers, Figure 14 generates **separate figures for each tier**:

```python
# Loop over tiers and generate separate figure
for tier in tier_order:
    tier_pairs_df = pairs_df[pairs_df["tier"] == tier]
    # ... create scatter plot ...
    save_figure(scatter, f"fig14_{tier_suffix}_judge_agreement", output_dir, render)
```

**Output Files** (per tier):

- `fig14_t0_judge_agreement.vl.json` - Vega-Lite spec for T0
- `fig14_t0_judge_agreement.png` - Rendered PNG (300 DPI)
- `fig14_t1_judge_agreement.vl.json` - Vega-Lite spec for T1
- ... (repeated for T1-T6)

**Rationale**: Separate figures allow tier-specific agreement analysis without visual clutter from combining all tiers.

## Interpretation Guidelines

### Agreement Thresholds

Visual assessment of scatter plot agreement:

| Visual Pattern | Agreement Level | Action |
|----------------|----------------|--------|
| Tight cluster on diagonal | Excellent (r > 0.90) | High confidence in judge scores |
| Moderate scatter on diagonal | Good (r = 0.70-0.90) | Acceptable agreement |
| Wide scatter perpendicular | Fair (r = 0.50-0.70) | Review rubric clarity |
| Random scatter | Poor (r < 0.50) | Re-evaluate criteria |
| Systematic bias (off-diagonal) | Concerning | Investigate judge bias |

### Diagnostic Patterns

**Pattern 1: High Agreement (Good)**

```
Score Judge 2
1.0  │              ●
     │            ● ●
     │          ●
     │        ●
0.0  └─────────────────
     0.0          1.0
         Score Judge 1
```

Points cluster tightly on diagonal → Reliable consensus

**Pattern 2: Systematic Bias (Concerning)**

```
Score Judge 2
1.0  │          ●●●●●
     │      ●●●●
     │  ●●●●
     │●●●
0.0  └─────────────────
     0.0          1.0
         Score Judge 1
```

Points consistently above diagonal → Judge 2 systematically scores higher

**Pattern 3: Random Scatter (Poor)**

```
Score Judge 2
1.0  │  ●   ●     ●
     │    ●   ●
     │  ●       ●
     │●     ●
0.0  └─────────────────
     0.0          1.0
         Score Judge 1
```

No correlation → Unreliable evaluation

### Implications of Low Agreement

**Low agreement (r < 0.50)** indicates:

1. **Rubric Issues**:
   - Criteria too ambiguous
   - Unclear pass/fail boundaries
   - Missing objective validation steps

2. **Task Characteristics**:
   - Borderline agent performance
   - Multiple valid interpretations
   - Subjective quality dimensions

3. **Judge Limitations**:
   - High model non-determinism
   - Tool execution variance
   - Insufficient context

**Recommended Actions**:

1. Review and refine rubric definitions
2. Add objective validation commands to rubric
3. Increase judge runs (3 → 5) for high-variance tasks
4. Consider using higher-capability judge model
5. Analyze individual judge outputs for patterns

## Related Figures

### Figure 2: Judge Score Variance

- Shows distribution of judge scores across all runs
- Complements pairwise agreement with overall variance metrics
- Helps identify high-variance tiers/subtests

### Figure 17: Overall Judge Agreement

- Aggregate agreement metrics across all tiers
- Provides single summary statistic per tier
- Useful for comparing agreement levels between tiers

**Relationship**:

- Fig 14 (this): Detailed pairwise scatter plots per tier
- Fig 2: Variance distributions
- Fig 17: Aggregate agreement metrics

Together, these figures provide complete picture of judge reliability.

## Code Reference

**Source**: `/home/mvillmow/Scylla/scylla/analysis/figures/judge_analysis.py:64-170`

**Function**: `fig14_judge_agreement(judges_df, output_dir, render=True)`

**Dependencies**:

- `scylla.analysis.figures.derive_tier_order()` - Extract tier ordering from data
- `scylla.analysis.figures.spec_builder.compute_dynamic_domain()` - Calculate axis domains
- `scylla.analysis.figures.spec_builder.save_figure()` - Save Vega-Lite spec and renders

**Key Implementation Details**:

1. **Pivot to Wide Format**:

```python
judge_pivot = judges_df.pivot_table(
    index=["agent_model", "tier", "subtest", "run_number"],
    columns="judge_number",
    values="judge_score",
).reset_index()
```

1. **Generate Pairwise Comparisons**:

```python
pair_indices = [(0, 1), (1, 2), (0, 2)]  # (1v2), (2v3), (1v3)
for i, j in pair_indices:
    pairs.append({
        "pair_label": f"Judge {i + 1} vs {j + 1}",
        "score_x": row[f"judge_{i+1}"],
        "score_y": row[f"judge_{j+1}"],
    })
```

1. **Per-Tier Figure Generation**:

```python
for tier in tier_order:
    tier_pairs_df = pairs_df[pairs_df["tier"] == tier]
    scatter = alt.Chart(tier_pairs_df).mark_circle()
    save_figure(scatter, f"fig14_{tier_suffix}_judge_agreement", output_dir, render)
```

**Testing**: See `/home/mvillmow/Scylla/tests/analysis/figures/test_judge_analysis.py` for unit tests.
