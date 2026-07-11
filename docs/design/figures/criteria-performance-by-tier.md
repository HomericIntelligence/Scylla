# Criteria Performance by Tier

## Overview

This figure presents a multi-faceted analysis of criteria-level performance across testing tiers. Unlike aggregate metrics that combine all evaluation dimensions into a single score, this visualization breaks down performance into individual quality criteria (e.g., functional correctness, code quality, documentation, architecture) and shows how each criterion improves (or fails to improve) as agents gain access to more sophisticated capabilities.

The visualization uses a faceted bar chart layout with rows representing different criteria and columns representing different agent models. Each subplot shows the mean criterion score across tiers, allowing for direct comparison of tier effectiveness at improving specific aspects of code quality.

This granular view reveals that different tiers have varying impacts on different quality dimensions. For example, adding documentation skills (T1) may dramatically improve documentation scores but have minimal impact on functional correctness, while adding testing tools (T2) may improve test coverage without affecting architectural cleanliness.

## Purpose

The primary purpose of this figure is to identify which criteria benefit most from tier progression and which remain relatively static. This analysis serves several critical functions:

1. **Capability Attribution**: Determine which tier additions drive improvements in specific quality dimensions
2. **Tier ROI Analysis**: Evaluate whether expensive tier additions (e.g., multi-agent delegation) justify their costs for specific criteria
3. **Strategic Optimization**: Identify opportunities to remove unnecessary tiers for tasks that don't benefit from certain capabilities
4. **Weakness Detection**: Spot criteria that remain poor across all tiers, indicating fundamental gaps in agent capabilities or evaluation methodology

By analyzing criterion-level patterns, researchers can make informed decisions about tier configurations for different task categories. A documentation-heavy task may only need T0 (Prompts) or T1 (Skills), while a complex refactoring task may require T3+ (Delegation and Hierarchy) to achieve acceptable architectural scores.

## Data Source

**Primary DataFrame**: `criteria_df` - One row per (run, judge, criterion) with 30,929 total rows

**Key Columns**:

- `agent_model`: Agent model name (e.g., "Sonnet 4.5", "Haiku 4.5")
- `tier`: Testing tier (T0-T6)
- `criterion`: Criterion name (derived from rubric `categories` field)
- `criterion_score`: Numeric score for this criterion (0.0-1.0 scale)

**Data Filters**:

1. Exclude non-numeric scores (filters out "N/A" entries where criterion was not evaluated)
2. Only include criteria with at least one data point across all runs
3. Dynamic criterion discovery - no hardcoded criterion list

**Aggregation**:

```python
criteria_agg = criteria_numeric.groupby(["agent_model", "tier", "criterion"])["criterion_score"].mean().reset_index()
```

Each data point represents the mean criterion score across all runs and all judges for a specific (agent_model, tier, criterion) combination.

## Mathematical Formulas

### Criterion Score Aggregation

For each (agent_model, tier, criterion) tuple:

```
mean_criterion_score = (1/N) × Σ(criterion_score_i)
```

Where:

- `N` = number of (run, judge) pairs for this (agent_model, tier, criterion)
- `criterion_score_i` = individual criterion score from judge evaluation (0.0-1.0)

### Display Label Generation

Criterion names are transformed from snake_case to Title Case for readability:

```
criterion_label = criterion.replace("_", " ").title()
```

Examples:

- `functional_correctness` → "Functional Correctness"
- `code_quality` → "Code Quality"
- `architectural_cleanliness` → "Architectural Cleanliness"

### Dynamic Domain Calculation

Y-axis domains are computed dynamically and rounded to nearest 0.1 for clean axis labels:

```
raw_domain = [min(criterion_score), max(criterion_score)]
score_domain = [round(raw_domain[0] / 0.1) × 0.1, round(raw_domain[1] / 0.1) × 0.1]
```

This ensures axis ranges adapt to actual data while maintaining readable tick marks.

## Theoretical Foundation

### Criteria Definition

Criteria are defined in each test's `rubric.yaml` file under the `categories` section. Unlike requirements (R001-R008) which are task-specific binary/scaled checks, criteria represent higher-level quality dimensions that aggregate related requirements.

**Common Criteria** (varies by test):

1. **Functional Correctness**: Does the code work as intended? Do all features function correctly?
2. **Code Quality**: Is the code readable, maintainable, and well-structured?
3. **Architectural Cleanliness**: Is the code well-organized with proper separation of concerns?
4. **Test Coverage**: Are tests comprehensive and do they validate the implementation?
5. **Documentation**: Are comments, docstrings, and documentation clear and complete?
6. **Completeness**: Are all required features implemented?
7. **Simplicity**: Is the solution appropriately simple without over-engineering?
8. **Efficiency**: Is the implementation performant and resource-efficient?

**Note**: Not all tests use all criteria. The figure dynamically discovers criteria from the data, ensuring it only displays criteria with actual measurements.

### Expected Tier Progression Patterns

Different criteria exhibit distinct progression patterns as tiers advance:

**Strong Tier Dependency (Expected Improvement)**:

- **Documentation**: Should improve significantly with documentation skills (T1) and documentation-focused agents (T3)
- **Test Coverage**: Should improve with testing tools (T2) and test specialist agents (T3)
- **Architectural Cleanliness**: Should improve with architect agents (T3) and hierarchy (T4)

**Moderate Tier Dependency (Variable Improvement)**:

- **Code Quality**: May improve gradually with skills (T1) and code review agents (T3)
- **Completeness**: Should improve with better planning (T3+) but may plateau early for simple tasks
- **Efficiency**: Requires specialized optimization agents (T3+) to show meaningful gains

**Weak Tier Dependency (Minimal Improvement)**:

- **Functional Correctness**: Often achieves high scores at T0/T1 for simple tasks; complex tasks may require T3+
- **Simplicity**: May actually decrease with higher tiers as agents over-engineer solutions (strategic drift)

### Ablation Study Implications

Each criterion progression pattern reveals the marginal utility of tier additions:

- **Flat progression**: Tier additions provide no benefit for this criterion (candidate for removal)
- **Step function**: Specific tier addition unlocks significant improvement (high ROI tier)
- **Linear improvement**: Gradual gains across tiers (cumulative benefit)
- **Decline**: Higher tiers harm this criterion (over-engineering, strategic drift)

By analyzing criterion-specific patterns, researchers can construct task-specific tier configurations that optimize for relevant quality dimensions while minimizing unnecessary costs.

## Visualization Details

### Chart Type

**Faceted Bar Chart** with:

- **Row facets**: One subplot per criterion (vertically stacked)
- **Column facets**: One subplot group per agent model (side-by-side comparison)
- **X-axis**: Testing tier (T0-T6)
- **Y-axis**: Mean criterion score (0.0-1.0)
- **Color encoding**: Tier (color-coded bars for visual distinction)

### Layout Specifications

**Individual Subplot Dimensions**:

- Height: 150px per criterion subplot
- Width: 180px per agent model column

**Faceting Configuration**:

```python
row=alt.Row(
    "criterion_label:N",
    title="Criterion",
    sort=criterion_labels_list,  # Alphabetical sort
    header=alt.Header(labelAngle=0, labelAlign="left")
)
column=alt.Column("agent_model:N", title=None)
```

**Independent Y-Scales**: Each criterion uses its own y-axis scale (`resolve_scale(y="independent")`), allowing criteria with different score ranges to use appropriate scaling. This prevents criteria with narrow score ranges from appearing flat when sharing a global scale.

### Color Scheme

**Tier Colors** (Tableau palette):

```python
tier_colors = [
    "#1f77b4",  # T0: Blue
    "#ff7f0e",  # T1: Orange
    "#2ca02c",  # T2: Green
    "#d62728",  # T3: Red
    "#9467bd",  # T4: Purple
    "#8c564b",  # T5: Brown
    "#e377c2"   # T6: Pink
]
```

Colors are assigned in tier order, using only the number of colors needed for tiers present in the data.

### Interactive Elements

**Tooltip** displays on hover:

- Tier name
- Criterion name (human-readable label)
- Mean criterion score (formatted to 3 decimal places)

**No Legend**: Legend is omitted since tier labels are already displayed on the x-axis of each subplot.

### Data Filtering and Validation

**Filter 1 - Numeric Scores Only**:

```python
criteria_numeric = criteria_df[
    pd.to_numeric(criteria_df["criterion_score"], errors="coerce").notna()
].copy()
```

This removes "N/A" scores where judges could not evaluate a criterion (e.g., test coverage for runs with no tests).

**Filter 2 - Valid Criteria Only**:

```python
valid_criteria = criteria_agg_temp["criterion"].unique()
```

Only criteria with at least one data point after aggregation are included, preventing empty subplots.

## Interpretation Guidelines

### Reading the Visualization

1. **Vertical comparison (within a subplot)**: Compare bars across tiers to see if this criterion improves with tier progression
2. **Horizontal comparison (across rows)**: Compare different criteria to identify which quality dimensions benefit most from tier additions
3. **Model comparison (across columns)**: Compare agent models to see if different models benefit differently from tier additions

### Key Patterns to Identify

**Positive Tier Progression** (bars increase left-to-right):

- Indicates the criterion benefits from tier additions
- Steep increases after specific tiers reveal high-ROI capabilities
- Example: Documentation score jumps from T0 to T1 when documentation skills are added

**Flat Progression** (bars remain constant across tiers):

- Indicates the criterion is unaffected by tier additions
- May suggest the criterion is too easy (scores at ceiling) or too hard (scores at floor)
- Candidate for tier simplification - higher tiers provide no benefit

**Negative Progression** (bars decrease with higher tiers):

- Indicates strategic drift or over-engineering
- Higher tiers may add complexity that harms simplicity or architectural cleanliness
- Signals the need for better prompt engineering or tier configuration

**Criterion-Specific Patterns**:

- **Documentation**: Should show strong improvement with documentation skills (T1)
- **Test Coverage**: Should improve with testing tools (T2) and test specialists (T3)
- **Functional Correctness**: May plateau early for simple tasks, require T3+ for complex tasks
- **Simplicity**: May decline with higher tiers as agents over-engineer solutions

### Statistical Considerations

**Sample Size Awareness**: Each bar represents the mean across all runs and judges for that (agent_model, tier, criterion). Lower sample sizes (fewer runs in a tier) may produce less stable estimates.

**Independent Scales**: Remember that y-axes are independent per criterion. A "high" bar in one subplot may represent a different absolute score than a "high" bar in another subplot.

**Missing Data**: If a criterion is not evaluated for certain tiers (e.g., test coverage for T0 prompts that produce no tests), those bars will be absent from the chart.

## Related Figures

- **fig05_grade_heatmap** - Grade distribution across tiers (aggregate view)
- **fig04_pass_rate_by_tier** - Overall pass rates by tier with confidence intervals
- **fig01_score_variance_by_tier** - Score distributions showing variance and outliers
- **fig11_tier_uplift** - Tier-to-tier improvement deltas (overall performance)

**Complementary Analysis**: While fig05 shows overall grade distributions and fig11 shows aggregate tier uplift, this figure provides a granular breakdown of which specific quality dimensions drive those aggregate changes. Use this figure to understand the "why" behind aggregate tier performance patterns.

## Code Reference

**Source**: `/home/mvillmow/Scylla/scylla/analysis/figures/criteria_analysis.py:17-117`

**Function**: `fig09_criteria_by_tier(criteria_df, output_dir, render=True)`

**Key Implementation Details**:

1. Dynamic criterion discovery from data (no hardcoded criterion list)
2. Automatic generation of display labels from criterion names (snake_case → Title Case)
3. Independent y-axis scales per criterion for optimal readability
4. Filtering of non-numeric scores and empty criteria
5. Tier color encoding with automatic palette truncation

**Output Files**:

- `docs/figures/fig09_criteria_by_tier.vl.json` - Vega-Lite specification
- `docs/figures/fig09_criteria_by_tier.csv` - Data slice (aggregated criteria scores)
- `docs/figures/fig09_criteria_by_tier.png` - Rendered image (if `render=True`)
- `docs/figures/fig09_criteria_by_tier.pdf` - Vector graphic (if `render=True`)

**Dependencies**:

- `derive_tier_order()` - Determines tier ordering from data
- `compute_dynamic_domain()` - Calculates optimal y-axis range
- `save_figure()` - Exports chart to multiple formats
