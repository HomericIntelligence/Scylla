# Table 2b: Impl-Rate Tier Pairwise Comparison

*Statistical workflow: Kruskal-Wallis omnibus test, then pairwise Mann-Whitney U with Holm-Bonferroni correction (step-down)*

**Omnibus Test Results (Kruskal-Wallis):**

- claude-haiku-4-5: H(6)=5.83, p=0.4423 ✗ (skip pairwise), power=1.000

| Model | Transition | N (T1, T2) | Impl-Rate Δ | p-value | Cliff's δ | Power | Significant? |
|-------|------------|------------|-------------|---------|-----------|-------|--------------|
| claude-haiku-4-5 | T0→T1 | (216, 90) | +0.0373 | — | +0.057 | 0.125 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T1→T2 | (90, 135) | -0.0108 | — | -0.038 | 0.079 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T2→T3 | (135, 369) | +0.0128 | — | +0.081 | 0.282 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T3→T4 | (369, 126) | +0.0068 | — | +0.031 | 0.086 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T4→T5 | (126, 135) | -0.0203 | — | -0.058 | 0.124 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T5→T6 | (135, 9) | +0.0187 | — | -0.030 | 0.053 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T0→T6 | (216, 9) | +0.0445 | — | +0.045 | 0.052 | N/A (omnibus n.s.) |
