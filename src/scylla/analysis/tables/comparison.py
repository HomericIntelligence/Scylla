"""Statistical comparison tables.

Generates comparison tables (Table 2, 2b, 4, 6) for tier and model comparisons.

Effect size interpretation follows Romano et al. (2006) for Cliff's delta:
    negligible (<0.11), small (0.11-0.28), medium (0.28-0.43), large (>0.43)

LaTeX Dependencies:
    - booktabs package (for professional table formatting)
    - longtable package (for multi-page tables)
    - threeparttable package (for table notes/footnotes)
"""

from __future__ import annotations

import math
from itertools import combinations

import pandas as pd

from scylla.analysis.config import ALPHA, config
from scylla.analysis.figures import derive_tier_order
from scylla.analysis.stats import (
    cliffs_delta,
    compute_consistency,
    compute_cop,
    holm_bonferroni_correction,
    kruskal_wallis,
    kruskal_wallis_power,
    mann_whitney_power,
    mann_whitney_u,
)

# Format strings from config
_FMT_PVAL = f".{config.precision_p_values}f"
_FMT_EFFECT = f".{config.precision_effect_sizes}f"
_FMT_RATE = f".{config.precision_rates}f"
_FMT_COST = f".{config.precision_costs}f"


def _generate_pairwise_comparison(  # noqa: C901  # pairwise comparison with many metric types
    runs_df: pd.DataFrame,
    metric_column: str,
    metric_name: str,
    table_title: str,
    table_label: str,
) -> tuple[str, str]:
    """Generate pairwise comparison table for a metric.

    Shared statistical pipeline:
    1. Kruskal-Wallis omnibus test across all tiers
    2. If omnibus p < ALPHA, proceed to pairwise comparisons
    3. Apply Holm-Bonferroni correction to pairwise p-values
    4. Generate markdown and LaTeX tables

    Args:
        runs_df: Runs DataFrame
        metric_column: Column name for the metric (e.g., "passed", "impl_rate")
        metric_name: Display name for the metric (e.g., "Pass Rate", "Impl-Rate")
        table_title: Title for the table
        table_label: LaTeX label for the table

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    import logging

    logger = logging.getLogger(__name__)

    # Derive tier order from data
    tier_order = derive_tier_order(runs_df)

    # Compute pairwise comparisons
    rows = []
    omnibus_results = []  # Store omnibus test results for table footer
    omnibus_powers = []  # Store omnibus KW power per model

    for model in sorted(runs_df["agent_model"].unique()):
        model_runs = runs_df[runs_df["agent_model"] == model]

        # Step 1: Kruskal-Wallis omnibus test across all tiers
        tier_groups = [
            model_runs[model_runs["tier"] == tier][metric_column].dropna() for tier in tier_order
        ]
        # Filter out empty groups
        tier_groups = [g for g in tier_groups if len(g) > 0]

        if len(tier_groups) < 2:
            logger.warning(
                f"Model {model}: Insufficient tier groups ({len(tier_groups)}) for omnibus test"
            )
            continue

        h_stat, omnibus_p = kruskal_wallis(*tier_groups)
        dof = len(tier_groups) - 1  # Degrees of freedom for Kruskal-Wallis
        omnibus_results.append((model, h_stat, omnibus_p, dof))

        # Compute KW omnibus power (medium reference effect ε² = 0.06)
        group_sizes = [len(g) for g in tier_groups]
        if all(n >= 5 for n in group_sizes):
            kw_power = kruskal_wallis_power(group_sizes, effect_size=0.06)
        else:
            kw_power = float("nan")
        omnibus_powers.append((model, kw_power))

        # Step 2: Only proceed to pairwise tests if omnibus is significant
        proceed_to_pairwise = omnibus_p < ALPHA

        # Collect all pairwise raw p-values for Holm-Bonferroni correction
        pairwise_data = []

        for i in range(len(tier_order) - 1):
            tier1, tier2 = tier_order[i], tier_order[i + 1]
            tier1_data = model_runs[model_runs["tier"] == tier1]
            tier2_data = model_runs[model_runs["tier"] == tier2]

            if len(tier1_data) == 0 or len(tier2_data) == 0:
                continue

            # Check for small sample sizes
            n1, n2 = len(tier1_data), len(tier2_data)
            if n1 < 10 or n2 < 10:
                logger.warning(f"Model {model}, {tier1}→{tier2}: Small sample size (N={n1}, {n2})")

            # Metric delta
            m1 = tier1_data[metric_column].mean()
            m2 = tier2_data[metric_column].mean()
            metric_delta = m2 - m1

            # Mann-Whitney U test (raw p-value)
            _, pvalue_raw = mann_whitney_u(
                tier1_data[metric_column].dropna(),
                tier2_data[metric_column].dropna(),
            )

            # Effect size (Cliff's delta)
            delta = cliffs_delta(
                tier2_data[metric_column].dropna(),
                tier1_data[metric_column].dropna(),
            )

            # Post-hoc power (Mann-Whitney) — skip for small samples
            power = mann_whitney_power(n1, n2, abs(delta)) if n1 >= 5 and n2 >= 5 else float("nan")

            pairwise_data.append(
                {
                    "Model": model,
                    "Transition": f"{tier1}→{tier2}",
                    "N1": n1,
                    "N2": n2,
                    f"{metric_name} Δ": metric_delta,
                    "p_raw": pvalue_raw,
                    "Cliff's δ": delta,
                    "Power": power,
                }
            )

        # Add overall first→last tier comparison
        first_tier = tier_order[0]
        last_tier = tier_order[-1]
        first_data = model_runs[model_runs["tier"] == first_tier]
        last_data = model_runs[model_runs["tier"] == last_tier]

        if len(first_data) > 0 and len(last_data) > 0:
            n1, n2 = len(first_data), len(last_data)
            m_first = first_data[metric_column].mean()
            m_last = last_data[metric_column].mean()
            metric_delta = m_last - m_first

            _, pvalue_raw = mann_whitney_u(
                first_data[metric_column].dropna(),
                last_data[metric_column].dropna(),
            )

            delta = cliffs_delta(
                last_data[metric_column].dropna(),
                first_data[metric_column].dropna(),
            )

            # Post-hoc power (Mann-Whitney) — skip for small samples
            power = mann_whitney_power(n1, n2, abs(delta)) if n1 >= 5 and n2 >= 5 else float("nan")

            pairwise_data.append(
                {
                    "Model": model,
                    "Transition": f"{first_tier}→{last_tier}",
                    "N1": n1,
                    "N2": n2,
                    f"{metric_name} Δ": metric_delta,
                    "p_raw": pvalue_raw,
                    "Cliff's δ": delta,
                    "Power": power,
                }
            )

        # Step 3: Apply Holm-Bonferroni correction to all pairwise p-values for this model
        if proceed_to_pairwise:
            raw_p_values = [d["p_raw"] for d in pairwise_data]
            corrected_p_values = holm_bonferroni_correction(raw_p_values)

            for i, corrected_p in enumerate(corrected_p_values):
                pairwise_data[i]["p-value"] = corrected_p
                pairwise_data[i]["Significant"] = "Yes" if corrected_p < ALPHA else "No"
        else:
            # Omnibus test not significant - don't perform pairwise tests
            for i in range(len(pairwise_data)):
                pairwise_data[i]["p-value"] = None
                pairwise_data[i]["Significant"] = "N/A (omnibus n.s.)"

        rows.extend(pairwise_data)

    df = pd.DataFrame(rows)

    # Markdown table
    md_lines = [
        f"# {table_title}",
        "",
        "*Statistical workflow: Kruskal-Wallis omnibus test, then pairwise Mann-Whitney U "
        "with Holm-Bonferroni correction (step-down)*",
        "",
    ]

    # Add omnibus results to header
    omnibus_power_map = dict(omnibus_powers)
    md_lines.append("**Omnibus Test Results (Kruskal-Wallis):**")
    md_lines.append("")
    for model, h_stat, omnibus_p, dof in omnibus_results:
        sig_str = "✓ (proceed to pairwise)" if omnibus_p < ALPHA else "✗ (skip pairwise)"
        kw_power = omnibus_power_map.get(model, float("nan"))
        power_str = f"{kw_power:.3f}" if not math.isnan(kw_power) else "—"
        md_lines.append(
            f"- {model}: H({dof})={h_stat:{_FMT_COST}}, p={omnibus_p:{_FMT_PVAL}} {sig_str}, "
            f"power={power_str}"
        )
    md_lines.append("")

    md_lines.append(
        f"| Model | Transition | N (T1, T2) | {metric_name} Δ | p-value | "
        f"Cliff's δ | Power | Significant? |"
    )
    md_lines.append(
        "|-------|------------|------------|-------------|---------|-----------|-------|--------------|"
    )

    for _, row in df.iterrows():
        cliffs_delta_val = row["Cliff's δ"]
        n_str = f"({row['N1']}, {row['N2']})"
        pval_str = f"{row['p-value']:{_FMT_PVAL}}" if pd.notna(row["p-value"]) else "—"
        power_val = row["Power"]
        power_str = f"{power_val:.3f}" if not math.isnan(power_val) else "—"

        md_lines.append(
            f"| {row['Model']} | {row['Transition']} | {n_str} | {row[f'{metric_name} Δ']:+.4f} | "
            f"{pval_str} | {cliffs_delta_val:+.3f} | {power_str} | {row['Significant']} |"
        )

    markdown = "\n".join(md_lines)

    # LaTeX table
    latex_lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        rf"\caption{{{table_title}}}",
        rf"\label{{tab:{table_label}}}",
        r"\begin{tabular}{llrrrrrl}",
        r"\toprule",
        rf"Model & Transition & N (T1, T2) & {metric_name} $\Delta$ & p-value & "
        r"Cliff's $\delta$ & Power & Significant? \\",
        r"\midrule",
    ]

    for _, row in df.iterrows():
        sig_mark = r"\checkmark" if row["Significant"] == "Yes" else ""
        cliffs_delta_val = row["Cliff's δ"]
        n_str = f"({row['N1']}, {row['N2']})"
        pval_str = f"{row['p-value']:{_FMT_PVAL}}" if pd.notna(row["p-value"]) else "---"
        power_val = row["Power"]
        power_str = f"{power_val:.3f}" if not math.isnan(power_val) else "---"

        latex_lines.append(
            f"{row['Model']} & {row['Transition']} & {n_str} & {row[f'{metric_name} Δ']:+.4f} & "
            f"{pval_str} & {cliffs_delta_val:+.3f} & {power_str} & {sig_mark} \\\\"
        )

    latex_lines.extend(
        [
            r"\midrule",
            r"\multicolumn{8}{l}{\textbf{Omnibus Test (Kruskal-Wallis):}} \\",
        ]
    )

    for model, h_stat, omnibus_p, dof in omnibus_results:
        sig_str = rf"$p < {ALPHA}$" if omnibus_p < ALPHA else rf"$p \geq {ALPHA}$ (n.s.)"
        kw_power = omnibus_power_map.get(model, float("nan"))
        power_str = f"{kw_power:.3f}" if not math.isnan(kw_power) else "---"
        latex_lines.append(
            rf"\multicolumn{{8}}{{l}}{{{model}: $H({dof})={h_stat:{_FMT_COST}}$, "
            rf"$p={omnibus_p:{_FMT_PVAL}}$ {sig_str}, power={power_str}}} \\"
        )

    # Add correction method footnote
    latex_lines.append(
        r"\multicolumn{8}{l}{\footnotesize "
        r"Pairwise p-values corrected with Holm-Bonferroni method.} \\"
    )

    latex_lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )

    latex = "\n".join(latex_lines)

    return markdown, latex


def table02_tier_comparison(runs_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 2: Tier Pairwise Comparison.

    Uses Kruskal-Wallis omnibus test followed by pairwise Mann-Whitney U tests
    with Holm-Bonferroni correction (step-down, less conservative than Bonferroni).

    Statistical workflow:
    1. Run Kruskal-Wallis omnibus test across all tiers
    2. If omnibus p < ALPHA, proceed to pairwise comparisons
    3. Apply Holm-Bonferroni correction to pairwise p-values

    Args:
        runs_df: Runs DataFrame

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    # Convert boolean to int for statistical tests
    runs_df_copy = runs_df.copy()
    runs_df_copy["passed"] = runs_df_copy["passed"].astype(int)

    return _generate_pairwise_comparison(
        runs_df_copy,
        metric_column="passed",
        metric_name="Pass Rate",
        table_title="Table 2: Tier Pairwise Comparison",
        table_label="tier_comparison",
    )


def table02b_impl_rate_comparison(runs_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 2b: Impl-Rate Tier Pairwise Comparison.

    Uses Kruskal-Wallis omnibus test followed by pairwise Mann-Whitney U tests
    with Holm-Bonferroni correction (step-down, less conservative than Bonferroni).

    Analogous to table02 but for Implementation Rate instead of Pass-Rate.

    Statistical workflow:
    1. Run Kruskal-Wallis omnibus test across all tiers
    2. If omnibus p < ALPHA, proceed to pairwise comparisons
    3. Apply Holm-Bonferroni correction to pairwise p-values

    Args:
        runs_df: Runs DataFrame (must include impl_rate column)

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    import logging

    logger = logging.getLogger(__name__)

    # Check if impl_rate column exists
    if "impl_rate" not in runs_df.columns:
        logger.error("impl_rate column not found in runs_df")
        return "Error: impl_rate column not found", "Error: impl_rate column not found"

    return _generate_pairwise_comparison(
        runs_df,
        metric_column="impl_rate",
        metric_name="Impl-Rate",
        table_title="Table 2b: Impl-Rate Tier Pairwise Comparison",
        table_label="impl_rate_tier_comparison",
    )


def table04_criteria_performance(  # noqa: C901  # table generation with many criteria branches
    criteria_df: pd.DataFrame,
    runs_df: pd.DataFrame,
    criteria_weights: dict[str, float] | None = None,
) -> tuple[str, str]:
    """Generate Table 4: Per-Criteria Performance.

    Uses Mann-Whitney U tests with Holm-Bonferroni correction for cross-model
    comparison of criteria scores.

    Args:
        criteria_df: Criteria DataFrame
        runs_df: Runs DataFrame for model filtering
        criteria_weights: Optional criteria weights dict. Derived from data if not provided.

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    # Use provided weights or derive from data
    if criteria_weights is None:
        # Derive criteria and uniform weights from the actual data
        unique_criteria = sorted(criteria_df["criterion"].unique())
        n = len(unique_criteria)
        criteria_weights = dict.fromkeys(unique_criteria, 1.0 / n) if n > 0 else {}

    # Aggregate by (agent_model, criterion)
    criterion_stats = []
    for model in sorted(criteria_df["agent_model"].unique()):
        for criterion in criteria_weights:
            subset = criteria_df[
                (criteria_df["agent_model"] == model) & (criteria_df["criterion"] == criterion)
            ]
            if len(subset) == 0:
                continue

            # Filter to numeric scores only
            numeric_scores = pd.to_numeric(subset["criterion_score"], errors="coerce")
            numeric_scores = numeric_scores.dropna()

            if len(numeric_scores) == 0:
                continue

            mean_score = numeric_scores.mean()
            std_score = numeric_scores.std()

            criterion_stats.append(
                {
                    "Model": model,
                    "Criterion": criterion,
                    "Weight": criteria_weights[criterion],
                    "Mean Score": mean_score,
                    "Std Dev": std_score,
                }
            )

    df = pd.DataFrame(criterion_stats)

    # Cross-model comparison (Mann-Whitney U tests with Holm-Bonferroni correction)
    # Collect all raw p-values first, then apply correction
    if len(df["Model"].unique()) == 2:
        models = sorted(df["Model"].unique())
        model1, model2 = models[0], models[1]

        raw_p_values = []
        test_metadata = []

        for criterion in criteria_weights:
            m1_data = criteria_df[
                (criteria_df["agent_model"] == model1) & (criteria_df["criterion"] == criterion)
            ]["criterion_score"]
            m2_data = criteria_df[
                (criteria_df["agent_model"] == model2) & (criteria_df["criterion"] == criterion)
            ]["criterion_score"]

            # Filter to numeric
            m1_numeric = pd.to_numeric(m1_data, errors="coerce").dropna()
            m2_numeric = pd.to_numeric(m2_data, errors="coerce").dropna()

            if len(m1_numeric) > 0 and len(m2_numeric) > 0:
                _, pvalue_raw = mann_whitney_u(m1_numeric, m2_numeric)
                winner = model1 if m1_numeric.mean() > m2_numeric.mean() else model2

                raw_p_values.append(pvalue_raw)
                test_metadata.append({"criterion": criterion, "winner": winner})

        # Apply Holm-Bonferroni correction to all raw p-values
        if raw_p_values:
            corrected_p_values = holm_bonferroni_correction(raw_p_values)

            for i, metadata in enumerate(test_metadata):
                df.loc[
                    (df["Model"] == model1) & (df["Criterion"] == metadata["criterion"]), "p-value"
                ] = corrected_p_values[i]
                df.loc[
                    (df["Model"] == model1) & (df["Criterion"] == metadata["criterion"]), "Winner"
                ] = metadata["winner"]

    # Get models dynamically
    models = sorted(df["Model"].unique())

    # Markdown table
    md_lines = ["# Table 4: Per-Criteria Performance", ""]

    # Build header dynamically
    model_headers = " | ".join([f"{model} Mean (±σ)" for model in models])
    md_lines.append(f"| Criterion | Weight | {model_headers} | p-value | Winner |")

    separator = "|" + "|".join(["-" * 10 for _ in range(3 + len(models))]) + "|"
    md_lines.append(separator)

    for criterion in criteria_weights:
        criterion_rows = df[df["Criterion"] == criterion]
        if len(criterion_rows) == 0:
            continue

        # Build model columns dynamically
        model_strs = []
        for model in models:
            model_row = criterion_rows[criterion_rows["Model"] == model]
            if len(model_row) > 0:
                model_strs.append(
                    f"{model_row['Mean Score'].iloc[0]:.3f} ± {model_row['Std Dev'].iloc[0]:.3f}"
                )
            else:
                model_strs.append("—")

        # Get p-value and winner from first model row (they're identical across models)
        first_model_row = criterion_rows[criterion_rows["Model"] == models[0]]
        pvalue_str = (
            f"{first_model_row['p-value'].iloc[0]:{_FMT_PVAL}}"
            if len(first_model_row) > 0 and "p-value" in first_model_row.columns
            else "—"
        )
        winner_str = (
            first_model_row["Winner"].iloc[0]
            if len(first_model_row) > 0 and "Winner" in first_model_row.columns
            else "—"
        )

        model_cols = " | ".join(model_strs)
        md_lines.append(
            f"| {criterion} | {criteria_weights[criterion]:{_FMT_COST}} | "
            f"{model_cols} | {pvalue_str} | {winner_str} |"
        )

    markdown = "\n".join(md_lines)

    # LaTeX table
    # Build column format dynamically:
    # l (criterion) r (weight) + l for each model + l (pvalue) + l (winner)
    col_format = "lr" + "l" * len(models) + "ll"

    latex_lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Per-Criteria Performance Comparison}",
        r"\label{tab:criteria_performance}",
        rf"\begin{{tabular}}{{{col_format}}}",
        r"\toprule",
    ]

    # Build header dynamically
    model_headers = " & ".join([f"{model} Mean ($\\pm\\sigma$)" for model in models])
    latex_lines.append(rf"Criterion & Weight & {model_headers} & p-value & Winner \\")
    latex_lines.append(r"\midrule")

    for criterion in criteria_weights:
        criterion_rows = df[df["Criterion"] == criterion]
        if len(criterion_rows) == 0:
            continue

        # Build model columns dynamically
        model_strs = []
        for model in models:
            model_row = criterion_rows[criterion_rows["Model"] == model]
            if len(model_row) > 0:
                mean_score = model_row["Mean Score"].iloc[0]
                std_dev = model_row["Std Dev"].iloc[0]
                model_strs.append(f"{mean_score:.3f} $\\pm$ {std_dev:.3f}")
            else:
                model_strs.append("---")

        # Get p-value and winner from first model row
        first_model_row = criterion_rows[criterion_rows["Model"] == models[0]]
        pvalue_str = (
            f"{first_model_row['p-value'].iloc[0]:{_FMT_PVAL}}"
            if len(first_model_row) > 0 and "p-value" in first_model_row.columns
            else "---"
        )
        winner_str = (
            first_model_row["Winner"].iloc[0]
            if len(first_model_row) > 0 and "Winner" in first_model_row.columns
            else "---"
        )

        model_cols = " & ".join(model_strs)
        latex_lines.append(
            f"{criterion} & {criteria_weights[criterion]:{_FMT_COST}} & "
            f"{model_cols} & {pvalue_str} & {winner_str} \\\\"
        )

    # Add correction method footnote
    latex_lines.append(r"\midrule")
    latex_lines.append(
        r"\multicolumn{" + str(len(models) + 4) + r"}{l}{\footnotesize "
        r"p-values corrected with Holm-Bonferroni method.} \\"
    )

    latex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])

    latex = "\n".join(latex_lines)

    return markdown, latex


def table06_model_comparison(runs_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 6: Model Comparison Summary.

    Applies Holm-Bonferroni correction for all pairwise model comparisons.
    For N models, performs C(N,2) pairwise comparisons, each with 2 tests (pass rate + mean score).

    Args:
        runs_df: Runs DataFrame

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    models = sorted(runs_df["agent_model"].unique())

    if len(models) < 2:
        return "# Table 6: Model Comparison\n\nError: Need at least 2 models", ""

    # Generate all pairwise comparisons
    model_pairs = list(combinations(models, 2))

    # Collect all raw p-values and metadata for Holm-Bonferroni correction
    raw_p_values = []
    test_metadata = []

    for model1, model2 in model_pairs:
        m1_data = runs_df[runs_df["agent_model"] == model1]
        m2_data = runs_df[runs_df["agent_model"] == model2]

        # Pass rate
        pr1, pr2 = m1_data["passed"].mean(), m2_data["passed"].mean()
        _, pr_pvalue_raw = mann_whitney_u(
            m1_data["passed"].astype(int), m2_data["passed"].astype(int)
        )
        raw_p_values.append(pr_pvalue_raw)
        test_metadata.append(
            {
                "pair": (model1, model2),
                "metric": "Overall Pass Rate",
                "model1_val": pr1,
                "model2_val": pr2,
                "delta": pr1 - pr2,
            }
        )

        # Mean score
        ms1, ms2 = m1_data["score"].mean(), m2_data["score"].mean()
        _, ms_pvalue_raw = mann_whitney_u(m1_data["score"], m2_data["score"])
        raw_p_values.append(ms_pvalue_raw)
        test_metadata.append(
            {
                "pair": (model1, model2),
                "metric": "Mean Score",
                "model1_val": ms1,
                "model2_val": ms2,
                "delta": ms1 - ms2,
            }
        )

    # Apply Holm-Bonferroni correction to all raw p-values
    corrected_p_values = holm_bonferroni_correction(raw_p_values)

    # Build comparison table with corrected p-values
    all_metrics = []
    for i, metadata in enumerate(test_metadata):
        model1, model2 = metadata["pair"]
        all_metrics.append(
            {
                "Pair": f"{model1} vs {model2}",
                "Metric": metadata["metric"],
                model1: metadata["model1_val"],
                model2: metadata["model2_val"],
                "Δ": metadata["delta"],
                "p-value": corrected_p_values[i],
            }
        )

        # Mean cost (no p-value)
        mc1, mc2 = m1_data["cost_usd"].mean(), m2_data["cost_usd"].mean()
        all_metrics.append(
            {
                "Pair": f"{model1} vs {model2}",
                "Metric": "Mean Cost ($)",
                model1: mc1,
                model2: mc2,
                "Δ": mc1 - mc2,
                "p-value": None,
            }
        )

        # Frontier CoP
        # Compute CoP per tier, then take minimum (frontier)
        tier_costs_1 = m1_data.groupby("tier")["cost_usd"].mean()
        tier_pass_rates_1 = m1_data.groupby("tier")["passed"].mean()
        tier_cops_1 = pd.Series(
            {
                tier: compute_cop(tier_costs_1[tier], tier_pass_rates_1[tier])
                for tier in tier_costs_1.index
            }
        )
        cop1 = tier_cops_1.min()

        tier_costs_2 = m2_data.groupby("tier")["cost_usd"].mean()
        tier_pass_rates_2 = m2_data.groupby("tier")["passed"].mean()
        tier_cops_2 = pd.Series(
            {
                tier: compute_cop(tier_costs_2[tier], tier_pass_rates_2[tier])
                for tier in tier_costs_2.index
            }
        )
        cop2 = tier_cops_2.min()
        all_metrics.append(
            {
                "Pair": f"{model1} vs {model2}",
                "Metric": "Frontier CoP ($)",
                model1: cop1,
                model2: cop2,
                "Δ": cop1 - cop2,
                "p-value": None,
            }
        )

        # Best tier
        best_tier1 = m1_data.groupby("tier")["passed"].mean().idxmax()
        best_tier2 = m2_data.groupby("tier")["passed"].mean().idxmax()
        all_metrics.append(
            {
                "Pair": f"{model1} vs {model2}",
                "Metric": "Best Tier (Pass Rate)",
                model1: best_tier1,
                model2: best_tier2,
                "Δ": "—",
                "p-value": None,
            }
        )

        # Consistency
        tier_stats1 = m1_data.groupby("tier")["score"].agg(["mean", "std"])
        tier_stats2 = m2_data.groupby("tier")["score"].agg(["mean", "std"])

        consistencies1 = [
            compute_consistency(row["mean"], row["std"]) for _, row in tier_stats1.iterrows()
        ]
        consistencies2 = [
            compute_consistency(row["mean"], row["std"]) for _, row in tier_stats2.iterrows()
        ]

        consistency1 = sum(consistencies1) / len(consistencies1) if consistencies1 else 0.0
        consistency2 = sum(consistencies2) / len(consistencies2) if consistencies2 else 0.0

        all_metrics.append(
            {
                "Pair": f"{model1} vs {model2}",
                "Metric": "Mean Consistency",
                model1: consistency1,
                model2: consistency2,
                "Δ": consistency1 - consistency2,
                "p-value": None,
            }
        )

        # Total tokens
        tt1 = m1_data["total_tokens"].sum()
        tt2 = m2_data["total_tokens"].sum()
        all_metrics.append(
            {
                "Pair": f"{model1} vs {model2}",
                "Metric": "Total Tokens",
                model1: tt1,
                model2: tt2,
                "Δ": tt1 - tt2,
                "p-value": None,
            }
        )

    df = pd.DataFrame(all_metrics)

    # Markdown table
    md_lines = ["# Table 6: Model Comparison Summary", ""]

    # If only 2 models, use original 2-column format
    if len(models) == 2:
        model1, model2 = models[0], models[1]
        md_lines.append(f"| Metric | {model1} | {model2} | Δ | p-value |")
        md_lines.append("|--------|----------|----------|---|---------|")

        for _, row in df.iterrows():
            val1_str = f"{row[model1]:.3f}" if isinstance(row[model1], float) else str(row[model1])
            val2_str = f"{row[model2]:.3f}" if isinstance(row[model2], float) else str(row[model2])
            delta_str = f"{row['Δ']:+.3f}" if isinstance(row["Δ"], float) else str(row["Δ"])
            pval_str = f"{row['p-value']:{_FMT_PVAL}}" if pd.notna(row["p-value"]) else "—"

            md_lines.append(
                f"| {row['Metric']} | {val1_str} | {val2_str} | {delta_str} | {pval_str} |"
            )
    else:
        # For N models, group by pair
        md_lines.append("| Pair | Metric | Model 1 | Model 2 | Δ | p-value |")
        md_lines.append("|------|--------|---------|---------|---|---------|")

        for _, row in df.iterrows():
            # Model names from the pair
            pair_models = row["Pair"].split(" vs ")
            model1, model2 = pair_models[0], pair_models[1]

            val1_str = f"{row[model1]:.3f}" if isinstance(row[model1], float) else str(row[model1])
            val2_str = f"{row[model2]:.3f}" if isinstance(row[model2], float) else str(row[model2])
            delta_str = f"{row['Δ']:+.3f}" if isinstance(row["Δ"], float) else str(row["Δ"])
            pval_str = f"{row['p-value']:{_FMT_PVAL}}" if pd.notna(row["p-value"]) else "—"

            md_lines.append(
                f"| {row['Pair']} | {row['Metric']} | {val1_str} | {val2_str} | "
                f"{delta_str} | {pval_str} |"
            )

    markdown = "\n".join(md_lines)

    # LaTeX table
    latex_lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Model Comparison Summary}",
        r"\label{tab:model_comparison}",
    ]

    if len(models) == 2:
        model1, model2 = models[0], models[1]
        latex_lines.extend(
            [
                r"\begin{tabular}{lrrrl}",
                r"\toprule",
                f"Metric & {model1} & {model2} & $\\Delta$ & p-value \\\\",
                r"\midrule",
            ]
        )

        for _, row in df.iterrows():
            val1_str = f"{row[model1]:.3f}" if isinstance(row[model1], float) else str(row[model1])
            val2_str = f"{row[model2]:.3f}" if isinstance(row[model2], float) else str(row[model2])
            delta_str = f"{row['Δ']:+.3f}" if isinstance(row["Δ"], float) else str(row["Δ"])
            pval_str = f"{row['p-value']:{_FMT_PVAL}}" if pd.notna(row["p-value"]) else "---"

            latex_lines.append(
                f"{row['Metric']} & {val1_str} & {val2_str} & {delta_str} & {pval_str} \\\\"
            )
    else:
        latex_lines.extend(
            [
                r"\begin{tabular}{llrrrl}",
                r"\toprule",
                "Pair & Metric & Model 1 & Model 2 & $\\Delta$ & p-value \\\\",
                r"\midrule",
            ]
        )

        for _, row in df.iterrows():
            pair_models = row["Pair"].split(" vs ")
            model1, model2 = pair_models[0], pair_models[1]

            val1_str = f"{row[model1]:.3f}" if isinstance(row[model1], float) else str(row[model1])
            val2_str = f"{row[model2]:.3f}" if isinstance(row[model2], float) else str(row[model2])
            delta_str = f"{row['Δ']:+.3f}" if isinstance(row["Δ"], float) else str(row["Δ"])
            pval_str = f"{row['p-value']:{_FMT_PVAL}}" if pd.notna(row["p-value"]) else "---"

            latex_lines.append(
                f"{row['Pair']} & {row['Metric']} & {val1_str} & {val2_str} & "
                f"{delta_str} & {pval_str} \\\\"
            )

    # Add correction method footnote
    latex_lines.append(r"\midrule")
    num_cols = 5 if len(models) == 2 else 6
    latex_lines.append(
        rf"\multicolumn{{{num_cols}}}{{l}}{{\footnotesize "
        r"p-values corrected with Holm-Bonferroni method.}} \\"
    )

    latex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])

    latex = "\n".join(latex_lines)

    return markdown, latex


def table_cfp_comparison(runs_df: pd.DataFrame) -> tuple[str, str]:
    """Compare Change Fail Percentage (CFP) and R_Prog across tiers.

    Uses the same Kruskal-Wallis → pairwise Mann-Whitney U → Holm-Bonferroni
    pipeline as table02_tier_comparison. Reports results for both CFP
    and R_Prog (Fine-Grained Progress Rate) to support research.md §6.3.

    Args:
        runs_df: Runs DataFrame (requires 'cfp' and 'r_prog' columns).

    Returns:
        Tuple of (markdown_table, latex_table).

    """
    if "cfp" not in runs_df.columns:
        return (
            "*(CFP data not yet collected)*",
            "% CFP data not yet collected",
        )

    cfp_md, cfp_latex = _generate_pairwise_comparison(
        runs_df,
        metric_column="cfp",
        metric_name="CFP",
        table_title="Change Fail Percentage by Tier",
        table_label="cfp_comparison",
    )
    r_prog_md, r_prog_latex = _generate_pairwise_comparison(
        runs_df,
        metric_column="r_prog",
        metric_name="R\\_Prog",
        table_title="Fine-Grained Progress Rate by Tier",
        table_label="r_prog_comparison",
    )
    return (cfp_md + "\n\n" + r_prog_md, cfp_latex + "\n\n" + r_prog_latex)


__all__ = [
    "table02_tier_comparison",
    "table02b_impl_rate_comparison",
    "table04_criteria_performance",
    "table06_model_comparison",
    "table_cfp_comparison",
]
