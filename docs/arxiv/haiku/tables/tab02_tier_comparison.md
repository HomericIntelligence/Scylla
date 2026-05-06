# Table 2: Tier Pairwise Comparison

*Statistical workflow: Kruskal-Wallis omnibus test, then pairwise Mann-Whitney U with Holm-Bonferroni correction (step-down)*

**Omnibus Test Results (Kruskal-Wallis):**

- claude-haiku-4-5: H(6)=8.53, p=0.2015 ✗ (skip pairwise), power=1.000

| Model | Transition | N (T1, T2) | Pass Rate Δ | p-value | Cliff's δ | Power | Significant? |
|-------|------------|------------|-------------|---------|-----------|-------|--------------|
| claude-haiku-4-5 | T0→T1 | (216, 90) | +0.0315 | — | +0.031 | 0.069 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T1→T2 | (90, 135) | +0.0111 | — | +0.011 | 0.054 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T2→T3 | (135, 369) | -0.0022 | — | -0.002 | 0.050 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T3→T4 | (369, 126) | +0.0006 | — | +0.001 | 0.053 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T4→T5 | (126, 135) | -0.0132 | — | -0.013 | 0.050 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T5→T6 | (135, 9) | +0.0370 | — | +0.037 | 0.054 | N/A (omnibus n.s.) |
| claude-haiku-4-5 | T0→T6 | (216, 9) | +0.0648 | — | +0.065 | 0.059 | N/A (omnibus n.s.) |
