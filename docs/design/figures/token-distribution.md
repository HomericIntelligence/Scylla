# Token Distribution by Tier

## Overview

Figure 07 visualizes the breakdown of token usage across four distinct token types for each testing tier, showing how different architectural configurations impact token consumption patterns. The figure uses stacked bar charts with normalized percentages to compare the relative contribution of each token type across tiers, faceted by agent model.

The four token types tracked are:

1. **Input (Fresh)**: New input tokens parsed for the first time (not from cache)
2. **Input (Cached)**: Input tokens retrieved from Claude's prompt caching system
3. **Output**: Generated response tokens from the model
4. **Cache Creation**: Tokens stored to cache for future reuse

This breakdown enables identification of cache efficiency patterns and understanding which tiers maximize prompt caching benefits versus requiring fresh input processing.

## Purpose

The token distribution figure serves multiple critical purposes in Scylla's evaluation framework:

1. **Cost Driver Identification**: Token usage directly determines API costs. Understanding the breakdown reveals which components (fresh input, cached input, output generation, cache creation) drive costs in each tier.

2. **Cache Efficiency Analysis**: Reveals how effectively each tier architecture leverages Claude's prompt caching. Higher-tier architectures (T4, T6) should show extreme cache efficiency with minimal fresh input tokens.

3. **Architectural Trade-off Visualization**: Demonstrates the token-level consequences of architectural decisions (e.g., delegation, hierarchy, tooling) on overall token consumption patterns.

4. **Cost Optimization Opportunities**: Identifies tiers with inefficient token usage patterns (e.g., high fresh input with low cache reuse) that could benefit from prompt caching optimization.

5. **Baseline Comparison**: Establishes token distribution baselines for each tier to measure improvements from architectural or configuration changes.

## Data Source

The figure is generated from the runs DataFrame (`runs_df`) with the following token-related columns:

- **`input_tokens`**: Fresh input tokens (not from cache)
- **`output_tokens`**: Generated output tokens
- **`cache_creation_tokens`**: Tokens stored for cache creation
- **`cache_read_tokens`**: Cached input tokens retrieved from cache

**Aggregation Method**: Mean tokens per tier and agent model

- Group by: `agent_model`, `tier`
- Aggregation: Mean of each token column

**Data Transformation**: Long format reshape for stacking

- Variables: `input_tokens`, `output_tokens`, `cache_creation_tokens`, `cache_read_tokens`
- Labels: "Input (Fresh)", "Input (Cached)", "Output", "Cache Creation"

**Tier Ordering**: Derived from data using `derive_tier_order()` to ensure consistent T0→T1→T2→T3→T4→T5→T6 sequence.

## Mathematical Formulas

### Token Aggregation

For each tier `t` and agent model `m`, compute mean tokens:

```
input_fresh(t,m) = mean(input_tokens | tier=t, agent_model=m)
input_cached(t,m) = mean(cache_read_tokens | tier=t, agent_model=m)
output(t,m) = mean(output_tokens | tier=t, agent_model=m)
cache_creation(t,m) = mean(cache_creation_tokens | tier=t, agent_model=m)
```

### Total Tokens

```
total_tokens(t,m) = input_fresh(t,m) + input_cached(t,m) + output(t,m) + cache_creation(t,m)
```

### Normalized Distribution (Percentage)

For visualization with `stack="normalize"`:

```
pct_input_fresh(t,m) = input_fresh(t,m) / total_tokens(t,m) × 100%
pct_input_cached(t,m) = input_cached(t,m) / total_tokens(t,m) × 100%
pct_output(t,m) = output(t,m) / total_tokens(t,m) × 100%
pct_cache_creation(t,m) = cache_creation(t,m) / total_tokens(t,m) × 100%
```

### Cache Efficiency Ratio

Derived metric (not shown in visualization but calculable from data):

```
cache_efficiency(t,m) = input_cached(t,m) / (input_fresh(t,m) + input_cached(t,m))
```

Where `cache_efficiency → 1.0` indicates maximum cache usage (minimal fresh parsing).

## Theoretical Foundation

### LLM Token Economics

Claude's API pricing is based on token consumption with different costs for different token types:

- **Input (Fresh)**: Standard input token pricing (~$3.00 per million tokens for Claude Sonnet)
- **Input (Cached)**: Discounted pricing (~$0.30 per million tokens, 90% savings)
- **Output**: Higher cost than input (~$15.00 per million tokens for Claude Sonnet)
- **Cache Creation**: Similar to input pricing (~$3.75 per million tokens)

### Prompt Caching Theory

Claude's prompt caching system stores frequently reused input content (e.g., system prompts, project context, documentation) to reduce fresh parsing costs. Key principles:

1. **Cache Eligibility**: Input content exceeding minimum length threshold (typically 1024+ tokens)
2. **Cache Lifetime**: 5-minute TTL (time-to-live) for cached content
3. **Cache Invalidation**: Any change to cached content requires fresh parsing
4. **Cost Savings**: 90% reduction in input costs for cached content (fresh: $3.00/M → cached: $0.30/M)

### Architectural Impact on Token Distribution

Different tier architectures produce distinct token distribution patterns:

**T0 (Prompts Only)**:

- High fresh input (no caching optimization)
- Moderate output (single-shot responses)
- Zero cache creation/reuse

**T1 (Skills) through T3 (Delegation)**:

- Increasing cache creation as context grows
- Growing cached input as repeated operations reuse context
- Variable output based on tool usage

**T4 (Hierarchy) through T6 (Super)**:

- Extreme cache efficiency (>99.98% cached input)
- Minimal fresh input (~0.01-0.02% of total input)
- High cache creation to support hierarchical context sharing
- Variable output based on complexity

### Cost Attribution

Token distribution enables precise cost attribution:

```
cost(t,m) = (input_fresh(t,m) × price_input_fresh) +
            (input_cached(t,m) × price_input_cached) +
            (output(t,m) × price_output) +
            (cache_creation(t,m) × price_cache_creation)
```

This breakdown reveals which token types drive costs in each tier.

## Visualization Details

### Chart Type

**Stacked Bar Chart** with normalized percentages (stack="normalize")

### Visual Encoding

- **X-axis**: Tier (T0, T1, T2, T3, T4, T5, T6) - categorical, ordered
- **Y-axis**: Token Distribution (%) - quantitative, 0-100% normalized scale
- **Color**: Token Type - categorical with 4 levels
  - Input (Fresh)
  - Input (Cached)
  - Output
  - Cache Creation
- **Facet**: Agent Model (column faceting) - categorical

### Stacking Order

Bars are stacked in the following order (bottom to top):

1. Input (Fresh) - bottom layer
2. Input (Cached)
3. Output
4. Cache Creation - top layer

Order defined by `token_type_order` mapping (0→1→2→3).

### Color Palette

Colors retrieved from centralized palette via `get_color_scale("token_types", ...)`:

- Input (Fresh): Distinct color for fresh parsing
- Input (Cached): Distinct color for cached retrieval
- Output: Distinct color for generated tokens
- Cache Creation: Distinct color for cache storage

### Tooltip

Interactive tooltip displays:

- **Tier**: Tier label (T0-T6)
- **Token Type**: Human-readable token type label
- **Mean Tokens**: Absolute token count (formatted with comma separators)

**Critical Note**: Tooltip preserves absolute counts even when visual representation is invisible due to normalization (e.g., T4/T6 fresh input tokens).

### Normalization Behavior

The `stack="normalize"` parameter converts absolute token counts to percentages of total tokens per tier. This causes very small token counts to become visually invisible:

**T4 Example**:

- Fresh input: ~23 tokens
- Cached input: ~92,000 tokens
- Fresh % = 23 / 92,023 ≈ 0.02% (invisible in visualization)

**T6 Example**:

- Fresh input: ~29 tokens
- Cached input: ~219,000 tokens
- Fresh % = 29 / 219,029 ≈ 0.01% (invisible in visualization)

This is **expected behavior** demonstrating extreme cache efficiency in higher-tier architectures.

### Figure Properties

- **Title**: "Token Distribution by Tier"
- **Facet Title**: None (column header shows agent_model directly)
- **Output Formats**: PNG, PDF, JSON (Vega-Lite spec), CSV (data)

## Interpretation Guidelines

### Identifying High-Token Components

1. **Visual Inspection**: Largest stack segments indicate dominant token types
   - Large "Output" segments → high response generation costs
   - Large "Input (Fresh)" segments → poor cache efficiency
   - Large "Input (Cached)" segments → effective caching

2. **Tooltip Exploration**: Hover over segments to view absolute token counts
   - Compare absolute counts across tiers
   - Identify invisible segments (e.g., T4/T6 fresh input)

3. **Cross-Tier Comparison**: Track token type evolution across tiers
   - T0→T1: Introduction of cache creation
   - T1→T3: Growing cache reuse
   - T4+: Extreme cache efficiency (>99.98% cached input)

### Cache Efficiency Patterns

**High Cache Efficiency** (Desirable):

- Minimal "Input (Fresh)" segment
- Large "Input (Cached)" segment
- Indicates effective prompt caching, 90% cost savings on input

**Low Cache Efficiency** (Undesirable):

- Large "Input (Fresh)" segment
- Small "Input (Cached)" segment
- Indicates poor caching, missing optimization opportunities

**Example**: T4/T6 show optimal cache efficiency with invisible fresh input segments (~0.01-0.02%).

### Cost Optimization Opportunities

1. **High Fresh Input**: Tiers with large fresh input percentages should investigate:
   - Is the input content reusable? → Add to cache
   - Is the input changing frequently? → Stabilize context
   - Is the input below cache threshold? → Batch operations

2. **High Output Tokens**: Tiers with large output percentages should investigate:
   - Are responses unnecessarily verbose? → Adjust prompts
   - Are multiple operations duplicating output? → Consolidate
   - Is the task inherently output-heavy? → Accept as necessary

3. **High Cache Creation**: Tiers with large cache creation percentages should verify:
   - Is the cached content reused? → Check cache_read_tokens
   - Is the cache TTL adequate? → Monitor cache hit rates
   - Is cache creation wasteful? → Reduce unnecessary context

### Tier-Specific Expectations

**T0 (Prompts Only)**:

- Expect: High fresh input, minimal/zero caching
- Warning: Any significant cache usage indicates configuration error

**T1-T3 (Progressive Features)**:

- Expect: Growing cache creation and reuse
- Warning: Decreasing cache efficiency indicates architectural issues

**T4-T6 (Advanced Architectures)**:

- Expect: Extreme cache efficiency (>99.98% cached input)
- Warning: Visible fresh input indicates caching failure

### Invisible Segments (T4/T6 Fresh Input)

When fresh input tokens are invisible in T4/T6 visualizations:

1. **This is expected behavior** - demonstrates extreme cache efficiency
2. **Use tooltip** to confirm absolute counts (~23-29 fresh tokens)
3. **Validate cache ratio**: cached_tokens / total_input_tokens > 0.9998
4. **Interpret as success**: Hierarchical architectures maximize caching

## Related Figures

### fig06: Cost-of-Pass (CoP)

**Relationship**: Token distribution directly impacts CoP calculations.

- **How they connect**: CoP = total_cost / pass_count, where total_cost is derived from token distribution × token prices
- **Combined insights**: High CoP in a tier can be explained by examining token distribution (e.g., excessive output tokens, poor cache efficiency)
- **Analysis workflow**: CoP identifies expensive tiers → Token distribution explains why

**Example**: If T3 has high CoP, check token distribution for:

- Excessive output tokens (verbose responses)
- Low cache efficiency (high fresh input)
- Inefficient cache creation (creation without reuse)

### fig22: Cumulative Cost Analysis

**Relationship**: Token distribution explains component-level cost contributions to cumulative total.

- **How they connect**: Cumulative cost aggregates costs over time/runs, token distribution breaks down cost by component type
- **Combined insights**: Cumulative cost trends can be traced to specific token type increases (e.g., output tokens growing over time)
- **Analysis workflow**: Cumulative cost shows total spend → Token distribution shows which token types drive spending

**Example**: If cumulative cost accelerates in T4+, check token distribution for:

- Unexpected fresh input increase (cache invalidation?)
- Output token growth (more complex responses?)
- Cache creation inefficiency (creating but not reusing?)

### Additional Related Figures

**fig08: Token Efficiency**: Likely shows tokens per task/operation, complementing distribution analysis

**fig09-fig11: Cost-related figures**: May show cost breakdowns, pricing impact, or economic metrics derived from token distribution

**fig26: Latency Analysis**: Token count (especially output tokens) correlates with generation latency

## Code Reference

### Source Location

- **File**: `/home/mvillmow/Scylla/scylla/analysis/figures/token_analysis.py`
- **Function**: `fig07_token_distribution(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None`
- **Lines**: 17-102

### Function Signature

```python
def fig07_token_distribution(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None:
    """Generate Fig 7: Token Distribution by Tier.

    Stacked bar chart showing token breakdown by type using normalized percentages.

    Args:
        runs_df: Runs DataFrame with token columns (input_tokens, output_tokens,
                 cache_creation_tokens, cache_read_tokens)
        output_dir: Output directory for figure files
        render: Whether to render to PNG/PDF (default: True)
    """
```

### Key Implementation Details

1. **Data Aggregation**: `runs_df.groupby(["agent_model", "tier"])[token_cols].mean()`
2. **Tier Ordering**: `derive_tier_order(token_agg)` for consistent T0-T6 sequence
3. **Reshape to Long Format**: `melt()` with `token_cols` as value_vars
4. **Token Type Labels**: Mapping from column names to human-readable labels
5. **Color Scale**: `get_color_scale("token_types", ...)` from centralized palette
6. **Normalization**: `stack="normalize"` in Y-axis encoding
7. **Stacking Order**: `order=alt.Order("token_type_order:Q")` for consistent layering
8. **Tooltip**: Absolute token counts preserved despite normalization
9. **Faceting**: `facet(column=alt.Column("agent_model:N"))` for model comparison
10. **Output**: `save_figure(chart, "fig07_token_distribution", output_dir, render)`

### Dependencies

- **pandas**: DataFrame operations and aggregation
- **altair**: Declarative visualization library
- **derive_tier_order()**: Utility function for tier ordering
- **get_color_scale()**: Centralized color palette management
- **save_figure()**: Multi-format output (PNG, PDF, JSON, CSV)

### Output Files

When rendered, the function generates:

- `fig07_token_distribution.png`: Raster visualization
- `fig07_token_distribution.pdf`: Vector visualization (publication-quality)
- `fig07_token_distribution.vl.json`: Vega-Lite specification (reproducible)
- `fig07_token_distribution.csv`: Underlying data (for external analysis)

### Critical Code Comments

From lines 22-29 (docstring):

> **Note on T4/T6 Fresh Input Tokens**: Higher-tier architectures (T4, T6) show minimal
> or invisible "Input (Fresh)" tokens due to extreme cache efficiency. For example:
>
> - T4: ~23 fresh tokens vs ~92K cached tokens (0.02% fresh)
> - T6: ~29 fresh tokens vs ~219K cached tokens (0.01% fresh)
>
> This is expected behavior demonstrating that hierarchical/super-tier architectures
> maximize prompt caching, with nearly all input coming from cache rather than fresh
> parsing. The tooltip still shows absolute token counts for precise comparison.

From lines 77-79 (normalization comment):

> NOTE: stack="normalize" causes very small token counts to become invisible.
> This is expected for T4/T6 fresh input tokens (~0.01-0.02% of total).
> The tooltip preserves absolute counts for detailed inspection.
