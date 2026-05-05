"""Detailed and appendix tables.

Generates detailed tables (Table 3, 7-11) for judge agreement, subtest details,
summary statistics, experiment configuration, and normality tests.
"""

from __future__ import annotations

import pandas as pd
from scipy import stats as scipy_stats

from scylla.analysis.config import ALPHA, config
from scylla.analysis.figures import derive_tier_order
from scylla.analysis.stats import (
    krippendorff_alpha,
    pearson_correlation,
    shapiro_wilk,
    spearman_correlation,
)

# Format strings from config
_FMT_PVAL = f".{config.precision_p_values}f"
_FMT_EFFECT = f".{config.precision_effect_sizes}f"
_FMT_PCT = f".{config.precision_percentages}f"
_FMT_RATE = f".{config.precision_rates}f"


def table03_judge_agreement(judges_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 3: Judge Agreement.

    Args:
        judges_df: Judges DataFrame

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    # Pivot judges to wide format
    judge_pivot = judges_df.pivot_table(
        index=["tier", "subtest", "run_number"],
        columns="judge_number",
        values="judge_score",
    ).reset_index()

    # Get dynamic judge column names from pivot result
    # Column names are: ['tier', 'subtest', 'run_number', 1, 2, 3, ...]
    index_cols = ["tier", "subtest", "run_number"]
    judge_cols = [col for col in judge_pivot.columns if col not in index_cols]

    # Rename judge columns to judge_1, judge_2, etc.
    new_cols = index_cols + [f"judge_{i}" for i in range(1, len(judge_cols) + 1)]
    judge_pivot.columns = new_cols
    judge_cols_renamed = [f"judge_{i}" for i in range(1, len(judge_cols) + 1)]

    judge_pivot = judge_pivot.dropna()

    # Pairwise correlations (dynamic based on number of judges)
    # Generate all pairs: (0,1), (0,2), (1,2), etc.
    rows = []
    n_judges = len(judge_cols_renamed)
    for i in range(n_judges):
        for j in range(i + 1, n_judges):
            col_x = judge_cols_renamed[i]
            col_y = judge_cols_renamed[j]

            spearman_r, _ = spearman_correlation(judge_pivot[col_x], judge_pivot[col_y])
            pearson_r, _ = pearson_correlation(judge_pivot[col_x], judge_pivot[col_y])
            mean_delta = (judge_pivot[col_x] - judge_pivot[col_y]).abs().mean()

            rows.append(
                {
                    "Judge Pair": f"Judge {i + 1} – Judge {j + 1}",
                    "Spearman ρ": spearman_r,
                    "Pearson r": pearson_r,
                    "Mean |Δ Score|": mean_delta,
                }
            )

    # Krippendorff's alpha (all judges)
    ratings_matrix = judge_pivot[judge_cols_renamed].values.T
    alpha = krippendorff_alpha(ratings_matrix, level="interval")

    rows.append(
        {
            "Judge Pair": "All Judges (Overall)",
            "Spearman ρ": None,
            "Pearson r": None,
            "Mean |Δ Score|": None,
        }
    )

    df = pd.DataFrame(rows)

    # Markdown
    md_lines = ["# Table 3: Judge Agreement", ""]
    md_lines.append("| Judge Pair | Spearman ρ | Pearson r | Mean |Δ Score| |")
    md_lines.append("|------------|------------|-----------|---------------|")

    for _, row in df.iterrows():
        if pd.notna(row["Spearman ρ"]):
            md_lines.append(
                f"| {row['Judge Pair']} | {row['Spearman ρ']:.3f} | "
                f"{row['Pearson r']:.3f} | {row['Mean |Δ Score|']:{_FMT_PVAL}} |"
            )
        else:
            md_lines.append(f"| {row['Judge Pair']} | — | — | — |")

    md_lines.append(f"\n**Krippendorff's α** (interval): {alpha:.3f}")

    markdown = "\n".join(md_lines)

    # LaTeX
    latex_lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Judge Agreement Metrics}",
        r"\label{tab:judge_agreement}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Judge Pair & Spearman $\rho$ & Pearson $r$ & " r"Mean $|\Delta \text{Score}|$ \\",
        r"\midrule",
    ]

    for _, row in df.iterrows():
        if pd.notna(row["Spearman ρ"]):
            latex_lines.append(
                f"{row['Judge Pair']} & {row['Spearman ρ']:.3f} & "
                f"{row['Pearson r']:.3f} & {row['Mean |Δ Score|']:{_FMT_PVAL}} \\\\"
            )
        else:
            latex_lines.append(f"{row['Judge Pair']} & -- & -- & -- \\\\")

    latex_lines.extend(
        [
            r"\midrule",
            rf"\multicolumn{{4}}{{l}}{{Krippendorff's $\alpha$ (interval): {alpha:.3f}}} \\",
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )

    latex = "\n".join(latex_lines)

    return markdown, latex


def table07_subtest_detail(runs_df: pd.DataFrame, subtests_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 7: Full Subtest Results (Appendix B).

    Args:
        runs_df: Runs DataFrame
        subtests_df: Subtests DataFrame

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    # Derive tier order from data
    tier_order = derive_tier_order(runs_df)

    # Build detailed subtest table
    rows = []
    for model in sorted(runs_df["agent_model"].unique()):
        for tier in tier_order:
            tier_subtests = subtests_df[
                (subtests_df["agent_model"] == model) & (subtests_df["tier"] == tier)
            ].sort_values("subtest")

            for _, subtest_row in tier_subtests.iterrows():
                # Grade distribution as string
                grade_dist = (
                    f"S:{int(subtest_row['grade_S'])} A:{int(subtest_row['grade_A'])} "
                    f"B:{int(subtest_row['grade_B'])} C:{int(subtest_row['grade_C'])} "
                    f"D:{int(subtest_row['grade_D'])} F:{int(subtest_row['grade_F'])}"
                )

                rows.append(
                    {
                        "Tier": tier,
                        "Subtest": subtest_row["subtest"],
                        "Pass Rate": subtest_row["pass_rate"],
                        "Mean Score": subtest_row["mean_score"],
                        "Std Dev": subtest_row["std_score"],
                        "Cost ($)": subtest_row["mean_cost"],
                        "Modal Grade": subtest_row["modal_grade"],
                        "Grade Dist": grade_dist,
                    }
                )

    df = pd.DataFrame(rows)

    # Markdown table (paginated for readability)
    md_lines = ["# Table 7: Full Subtest Results (Appendix B)", ""]
    md_lines.append(
        "| Tier | Subtest | Pass Rate | Mean Score | Std Dev | Cost ($) | "
        "Modal Grade | Grade Distribution |"
    )
    md_lines.append(
        "|------|---------|-----------|------------|---------|----------|"
        "-------------|-------------------|"
    )

    for _, row in df.iterrows():
        md_lines.append(
            f"| {row['Tier']} | {row['Subtest']} | "
            f"{row['Pass Rate']:.3f} | {row['Mean Score']:.3f} | {row['Std Dev']:.3f} | "
            f"{row['Cost ($)']:{_FMT_PVAL}} | {row['Modal Grade']} | {row['Grade Dist']} |"
        )

    markdown = "\n".join(md_lines)

    # LaTeX table (use longtable for multi-page)
    latex_lines = [
        r"\begin{longtable}{lrrrrrll}",
        r"\caption{Full Subtest Results (Appendix B)} \\",
        r"\toprule",
        r"Tier & ST & Pass Rate & Mean Score & Std Dev & Cost (\$) & "
        r"Grade & Distribution \\",
        r"\midrule",
        r"\endfirsthead",
        r"\multicolumn{8}{c}{\textit{Table 7 (continued)}} \\",
        r"\toprule",
        r"Tier & ST & Pass Rate & Mean Score & Std Dev & Cost (\$) & "
        r"Grade & Distribution \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
    ]

    for _, row in df.iterrows():
        latex_lines.append(
            f"{row['Tier']} & {row['Subtest']} & "
            f"{row['Pass Rate']:.3f} & {row['Mean Score']:.3f} & {row['Std Dev']:.3f} & "
            f"{row['Cost ($)']:{_FMT_PVAL}} & {row['Modal Grade']} & "
            f"\\tiny {row['Grade Dist']} \\\\"
        )

    latex_lines.append(r"\end{longtable}")

    latex = "\n".join(latex_lines)

    return markdown, latex


def table08_summary_statistics(runs_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 8: Summary Statistics.

    Descriptive statistics for all metrics by model.
    Essential foundation for any paper - shows data characteristics.

    Args:
        runs_df: Runs DataFrame

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    metrics = {
        "score": "Score",
        "cost_usd": "Cost (USD)",
        "duration_seconds": "Duration (s)",
        "total_tokens": "Total Tokens",
    }

    rows = []
    for model in sorted(runs_df["agent_model"].unique()):
        model_data = runs_df[runs_df["agent_model"] == model]

        for metric_col, metric_name in metrics.items():
            data = model_data[metric_col].dropna()

            if len(data) == 0:
                continue

            # Calculate statistics
            n = len(data)
            mean_val = data.mean()
            median_val = data.median()
            min_val = data.min()
            max_val = data.max()
            q1 = data.quantile(0.25)
            q3 = data.quantile(0.75)
            std_val = data.std()

            # Skewness and kurtosis using scipy
            skew_val = scipy_stats.skew(data)
            kurt_val = scipy_stats.kurtosis(data)

            rows.append(
                {
                    "Model": model,
                    "Metric": metric_name,
                    "N": n,
                    "Mean": mean_val,
                    "Median": median_val,
                    "Min": min_val,
                    "Max": max_val,
                    "Q1": q1,
                    "Q3": q3,
                    "StdDev": std_val,
                    "Skewness": skew_val,
                    "Kurtosis": kurt_val,
                }
            )

    df = pd.DataFrame(rows)

    # Markdown table
    md_lines = ["# Table 8: Summary Statistics", ""]
    md_lines.append(
        "| Model | Metric | N | Mean | Median | Min | Max | Q1 | Q3 | StdDev | Skew | Kurt |"
    )
    md_lines.append(
        "|-------|--------|---|------|--------|-----|-----|----|----|--------|------|------|"
    )

    for _, row in df.iterrows():
        md_lines.append(
            f"| {row['Model']} | {row['Metric']} | {row['N']} | "
            f"{row['Mean']:{_FMT_PVAL}} | {row['Median']:{_FMT_PVAL}} | {row['Min']:{_FMT_PVAL}} | "
            f"{row['Max']:{_FMT_PVAL}} | {row['Q1']:{_FMT_PVAL}} | {row['Q3']:{_FMT_PVAL}} | "
            f"{row['StdDev']:{_FMT_PVAL}} | {row['Skewness']:.3f} | {row['Kurtosis']:.3f} |"
        )

    markdown = "\n".join(md_lines)

    # LaTeX table
    latex_lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Summary Statistics by Model and Metric}",
        r"\label{tab:summary_statistics}",
        r"\small",
        r"\begin{tabular}{llrrrrrrrrrrr}",
        r"\toprule",
        r"Model & Metric & N & Mean & Median & Min & Max & Q1 & Q3 & StdDev & Skew & Kurt \\",
        r"\midrule",
    ]

    for _, row in df.iterrows():
        latex_lines.append(
            f"{row['Model']} & {row['Metric']} & {row['N']} & "
            f"{row['Mean']:{_FMT_PVAL}} & {row['Median']:{_FMT_PVAL}} & {row['Min']:{_FMT_PVAL}} & "
            f"{row['Max']:{_FMT_PVAL}} & {row['Q1']:{_FMT_PVAL}} & {row['Q3']:{_FMT_PVAL}} & "
            f"{row['StdDev']:{_FMT_PVAL}} & {row['Skewness']:.3f} & {row['Kurtosis']:.3f} \\\\"
        )

    latex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])

    latex = "\n".join(latex_lines)

    return markdown, latex


def table09_experiment_config(runs_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 9: Experiment Configuration.

    Derived entirely from data - no hardcoded values.
    Documents the experimental setup for reproducibility.

    Args:
        runs_df: Runs DataFrame

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    rows = []

    # Group by experiment (if experiment column exists, else treat all as one experiment)
    if "experiment" in runs_df.columns:
        experiments = sorted(runs_df["experiment"].unique())
    else:
        experiments = ["default"]
        runs_df = runs_df.copy()
        runs_df["experiment"] = "default"

    for experiment in experiments:
        exp_data = (
            runs_df[runs_df["experiment"] == experiment] if experiment != "default" else runs_df
        )

        # Derive configuration from data
        tiers = derive_tier_order(exp_data)
        n_tiers = len(tiers)

        # Subtests per tier (count unique subtests in each tier)
        subtests_per_tier = {}
        for tier in tiers:
            tier_data = exp_data[exp_data["tier"] == tier]
            subtests_per_tier[tier] = tier_data["subtest"].nunique()

        # Runs per subtest (mode of run counts across all subtests)
        runs_per_subtest_counts = exp_data.groupby(["tier", "subtest"]).size()
        runs_per_subtest = int(runs_per_subtest_counts.mode().iloc[0])

        # Total runs
        total_runs = len(exp_data)

        # Judge models (if available)
        if "judge_model" in exp_data.columns:
            judge_models = sorted(exp_data["judge_model"].dropna().unique())
            judge_models_str = ", ".join(judge_models)
        else:
            judge_models_str = "N/A"

        # Format subtests/tier as summary
        subtest_summary = f"{min(subtests_per_tier.values())}-{max(subtests_per_tier.values())}"
        if min(subtests_per_tier.values()) == max(subtests_per_tier.values()):
            subtest_summary = str(min(subtests_per_tier.values()))

        rows.append(
            {
                "Experiment": experiment,
                "Tiers": n_tiers,
                "Tier IDs": ", ".join(tiers),
                "Subtests/Tier": subtest_summary,
                "Runs/Subtest": runs_per_subtest,
                "Total Runs": total_runs,
                "Judge Models": judge_models_str,
            }
        )

    df = pd.DataFrame(rows)

    # Markdown table
    md_lines = ["# Table 9: Experiment Configuration", ""]
    md_lines.append(
        "| Experiment | Tiers | Tier IDs | Subtests/Tier | "
        "Runs/Subtest | Total Runs | Judge Models |"
    )
    md_lines.append(
        "|------------|-------|----------|---------------|"
        "--------------|------------|--------------|"
    )

    for _, row in df.iterrows():
        # Truncate long tier IDs for markdown
        tier_ids = row["Tier IDs"]
        if len(tier_ids) > 40:
            tier_ids = tier_ids[:37] + "..."

        md_lines.append(
            f"| {row['Experiment']} | {row['Tiers']} | "
            f"{tier_ids} | {row['Subtests/Tier']} | {row['Runs/Subtest']} | "
            f"{row['Total Runs']} | {row['Judge Models']} |"
        )

    markdown = "\n".join(md_lines)

    # LaTeX table
    latex_lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Experiment Configuration (Data-Derived)}",
        r"\label{tab:experiment_config}",
        r"\small",
        r"\begin{tabular}{lrllrrr}",
        r"\toprule",
        r"Experiment & Tiers & Tier IDs & ST/Tier & Runs/ST & Total & Judges \\",
        r"\midrule",
    ]

    for _, row in df.iterrows():
        # Truncate tier IDs for LaTeX
        tier_ids = row["Tier IDs"]
        if len(tier_ids) > 30:
            tier_ids = tier_ids[:27] + "..."

        latex_lines.append(
            f"{row['Experiment']} & {row['Tiers']} & "
            f"{tier_ids} & {row['Subtests/Tier']} & {row['Runs/Subtest']} & "
            f"{row['Total Runs']} & {row['Judge Models']} \\\\"
        )

    latex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])

    latex = "\n".join(latex_lines)

    return markdown, latex


def table10_normality_tests(runs_df: pd.DataFrame) -> tuple[str, str]:
    """Generate Table 10: Normality Tests.

    Shapiro-Wilk tests for all metric distributions.
    Justifies use of non-parametric statistical tests.

    Args:
        runs_df: Runs DataFrame

    Returns:
        Tuple of (markdown_table, latex_table)

    """
    from scylla.analysis.figures import derive_tier_order

    tier_order = derive_tier_order(runs_df)
    metrics = {
        "score": "Score",
        "cost_usd": "Cost (USD)",
    }

    rows = []
    for model in sorted(runs_df["agent_model"].unique()):
        for tier in tier_order:
            tier_data = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)]

            if len(tier_data) < 3:
                # Shapiro-Wilk requires at least 3 samples
                continue

            for metric_col, metric_name in metrics.items():
                data = tier_data[metric_col].dropna()

                if len(data) < 3:
                    continue

                # Shapiro-Wilk test
                w_stat, p_value = shapiro_wilk(data)

                # Interpret result
                is_normal = "Yes" if p_value > ALPHA else "No"

                rows.append(
                    {
                        "Model": model,
                        "Tier": tier,
                        "Metric": metric_name,
                        "N": len(data),
                        "W": w_stat,
                        "p-value": p_value,
                        "Normal? (α=0.05)": is_normal,
                    }
                )

    df = pd.DataFrame(rows)

    # Markdown table
    md_lines = [
        "# Table 10: Normality Tests (Shapiro-Wilk)",
        "",
        "*Tests null hypothesis that data is normally distributed. "
        f"p > {ALPHA} means cannot reject normality.*",
        "",
    ]
    md_lines.append("| Model | Tier | Metric | N | W | p-value | Normal? (α=0.05) |")
    md_lines.append("|-------|------|--------|---|---|---------|------------------|")

    for _, row in df.iterrows():
        md_lines.append(
            f"| {row['Model']} | {row['Tier']} | {row['Metric']} | {row['N']} | "
            f"{row['W']:{_FMT_PVAL}} | {row['p-value']:{_FMT_PVAL}} | {row['Normal? (α=0.05)']} |"
        )

    # Summary statistics
    normal_count = len(df[df["Normal? (α=0.05)"] == "Yes"])
    total_count = len(df)
    md_lines.append(
        f"\n**Summary**: {normal_count}/{total_count} "
        f"({100 * normal_count / total_count:{_FMT_PCT}}%) distributions pass normality test"
    )

    markdown = "\n".join(md_lines)

    # LaTeX table
    latex_lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Normality Tests (Shapiro-Wilk)}",
        r"\label{tab:normality_tests}",
        r"\begin{tabular}{llrrrrl}",
        r"\toprule",
        r"Model & Tier & Metric & N & W & p-value & Normal? ($\alpha=0.05$) \\",
        r"\midrule",
    ]

    for _, row in df.iterrows():
        normal_symbol = r"\checkmark" if row["Normal? (α=0.05)"] == "Yes" else r"$\times$"
        latex_lines.append(
            f"{row['Model']} & {row['Tier']} & {row['Metric']} & {row['N']} & "
            f"{row['W']:{_FMT_PVAL}} & {row['p-value']:{_FMT_PVAL}} & {normal_symbol} \\\\"
        )

    latex_lines.extend(
        [
            r"\midrule",
            rf"\multicolumn{{7}}{{l}}{{\textit{{Summary: {normal_count}/{total_count} "
            rf"({100 * normal_count / total_count:{_FMT_PCT}}\%) pass normality test}}}} \\",
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )

    latex = "\n".join(latex_lines)

    return markdown, latex


__all__ = [
    "table03_judge_agreement",
    "table07_subtest_detail",
    "table08_summary_statistics",
    "table09_experiment_config",
    "table10_normality_tests",
]
