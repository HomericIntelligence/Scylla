"""Model comparison figures.

Generates Fig 11 (tier uplift) and Fig 12 (consistency).
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd

from scylla.analysis.figures import derive_tier_order, get_color_scale
from scylla.analysis.figures.spec_builder import (
    compute_dynamic_domain,
    compute_dynamic_domain_with_ci,
    save_figure,
)
from scylla.analysis.stats import (
    bonferroni_correction,
    bootstrap_ci,
    compute_consistency,
    mann_whitney_u,
)


def fig11_tier_uplift(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None:
    """Generate Fig 11: Tier Transition Uplift.

    Line chart showing cumulative improvement relative to T0-Subtest0 baseline.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF

    """
    # Derive tier order from data
    tier_order = derive_tier_order(runs_df)

    # Compute pass rate per (agent_model, tier)
    tier_stats = (
        runs_df.groupby(["agent_model", "tier"])["passed"]
        .mean()
        .reset_index()
        .rename(columns={"passed": "pass_rate"})
    )

    # Compute uplift relative to T0-Subtest0 baseline
    uplift_data = []
    for model in tier_stats["agent_model"].unique():
        model_data = tier_stats[tier_stats["agent_model"] == model]

        # Get T0-Subtest0 baseline (no enhancements)
        t0_subtest0_data = runs_df[
            (runs_df["agent_model"] == model)
            & (runs_df["tier"] == "T0")
            & (runs_df["subtest"] == "00")
        ]["passed"]

        # Skip model if no T0-Subtest0 baseline data
        if len(t0_subtest0_data) == 0:
            continue

        t0_pass_rate = t0_subtest0_data.mean()

        for _, row in model_data.iterrows():
            tier = row["tier"]
            pass_rate = row["pass_rate"]
            uplift = pass_rate - t0_pass_rate
            uplift_pct = (uplift / t0_pass_rate) * 100 if t0_pass_rate > 0 else 0

            uplift_data.append(
                {
                    "agent_model": model,
                    "tier": tier,
                    "pass_rate": pass_rate,
                    "uplift": uplift,
                    "uplift_pct": uplift_pct,
                }
            )

    uplift_df = pd.DataFrame(uplift_data)

    # Compute statistical significance between consecutive tiers
    # Apply Bonferroni correction for consecutive comparisons per model
    n_tests = len(tier_order) - 1  # n-1 consecutive comparisons
    significance_data = []
    for model in runs_df["agent_model"].unique():
        model_runs = runs_df[runs_df["agent_model"] == model]

        for i in range(len(tier_order) - 1):
            tier1, tier2 = tier_order[i], tier_order[i + 1]
            tier1_data = model_runs[model_runs["tier"] == tier1]["passed"].astype(int)
            tier2_data = model_runs[model_runs["tier"] == tier2]["passed"].astype(int)

            if len(tier1_data) > 0 and len(tier2_data) > 0:
                _, pvalue_raw = mann_whitney_u(tier1_data, tier2_data)
                pvalue = bonferroni_correction(pvalue_raw, n_tests)
                significance_data.append(
                    {
                        "agent_model": model,
                        "tier": tier2,  # Mark the destination tier
                        "transition": f"{tier1}→{tier2}",
                        "pvalue": pvalue,
                        "significant": pvalue < 0.05,
                    }
                )

    significance_df = pd.DataFrame(significance_data)

    # Merge significance markers into uplift data
    uplift_df = uplift_df.merge(
        significance_df[["agent_model", "tier", "significant"]],
        on=["agent_model", "tier"],
        how="left",
    )
    uplift_df["significant"] = uplift_df["significant"].fillna(False)

    # Get dynamic color scale for models
    models = sorted(uplift_df["agent_model"].unique())
    domain, range_ = get_color_scale("models", models)

    # Create line chart
    line = (
        alt.Chart(uplift_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("tier:O", title="Tier", sort=tier_order),
            y=alt.Y(
                "uplift:Q",
                title="Pass Rate Uplift vs T0-Subtest0",
                scale=alt.Scale(
                    domain=compute_dynamic_domain(uplift_df["uplift"], floor=-1.0, ceiling=1.0)
                ),
            ),
            color=alt.Color(
                "agent_model:N",
                title="Agent Model",
                scale=alt.Scale(domain=domain, range=range_),
            ),
            tooltip=[
                alt.Tooltip("tier:O", title="Tier"),
                alt.Tooltip("agent_model:N", title="Model"),
                alt.Tooltip("pass_rate:Q", title="Pass Rate", format=".2%"),
                alt.Tooltip("uplift:Q", title="Uplift", format=".2%"),
                alt.Tooltip("uplift_pct:Q", title="Uplift %", format=".1f"),
            ],
        )
    )

    # Add significance markers (asterisks on points where p < 0.05)
    significant_points = uplift_df[uplift_df["significant"]]
    if len(significant_points) > 0:
        markers = (
            alt.Chart(significant_points)
            .mark_text(text="*", fontSize=12, dy=-15, fontWeight="bold", color="black")
            .encode(
                x=alt.X("tier:O", sort=tier_order),
                y="uplift:Q",
            )
        )
        chart = (line + markers).properties(
            title="Tier Transition Uplift (vs T0-Subtest0, * = p < 0.05)"
        )
    else:
        chart = line.properties(title="Tier Transition Uplift (vs T0-Subtest0)")

    save_figure(chart, "fig11_tier_uplift", output_dir, render)

    # Also save significance table
    sig_csv = output_dir / "fig11_tier_uplift_significance.csv"
    significance_df.to_csv(sig_csv, index=False)
    print(f"  Saved significance data: {sig_csv}")  # noqa: T201


def fig12_consistency(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None:
    """Generate Fig 12: Consistency by Tier.

    Line plot with confidence bands showing consistency scores.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF

    """
    # Derive tier order from data
    tier_order = derive_tier_order(runs_df)

    # Compute consistency per subtest, then aggregate by tier
    consistency_data = []

    for model in runs_df["agent_model"].unique():
        for tier in tier_order:
            # Get all subtests in this tier
            tier_subtests = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)][
                "subtest"
            ].unique()

            subtest_consistencies = []
            for subtest in tier_subtests:
                subtest_runs = runs_df[
                    (runs_df["agent_model"] == model)
                    & (runs_df["tier"] == tier)
                    & (runs_df["subtest"] == subtest)
                ]

                if len(subtest_runs) > 1:
                    mean_score = subtest_runs["score"].mean()
                    std_score = subtest_runs["score"].std()

                    # Use shared compute_consistency function
                    consistency = compute_consistency(mean_score, std_score)

                    subtest_consistencies.append(consistency)

            if subtest_consistencies:
                # Compute bootstrap CI if we have enough samples
                consistencies_array = pd.Series(subtest_consistencies)
                if len(consistencies_array) >= 2:
                    mean_consistency, ci_low, ci_high = bootstrap_ci(consistencies_array)
                else:
                    # Single subtest: use value as mean, no CI
                    mean_consistency = consistencies_array.iloc[0]
                    ci_low = mean_consistency
                    ci_high = mean_consistency

                consistency_data.append(
                    {
                        "agent_model": model,
                        "tier": tier,
                        "mean_consistency": mean_consistency,
                        "ci_low": ci_low,
                        "ci_high": ci_high,
                    }
                )

    consistency_df = pd.DataFrame(consistency_data)

    # Clamp CI to [0, 1]
    consistency_df["ci_low"] = consistency_df["ci_low"].clip(lower=0)
    consistency_df["ci_high"] = consistency_df["ci_high"].clip(upper=1)

    # Get dynamic color scale for models
    models = sorted(consistency_df["agent_model"].unique())
    domain, range_ = get_color_scale("models", models)

    # Compute dynamic domain for consistency axis - include CI bounds
    consistency_domain = compute_dynamic_domain_with_ci(
        consistency_df["mean_consistency"], consistency_df["ci_low"], consistency_df["ci_high"]
    )

    # Create line chart
    line = (
        alt.Chart(consistency_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("tier:O", title="Tier", sort=tier_order),
            y=alt.Y(
                "mean_consistency:Q",
                title="Consistency Score (1 - CV)",
                scale=alt.Scale(domain=consistency_domain),
            ),
            color=alt.Color(
                "agent_model:N",
                title="Agent Model",
                scale=alt.Scale(domain=domain, range=range_),
            ),
            tooltip=[
                alt.Tooltip("tier:O", title="Tier"),
                alt.Tooltip("agent_model:N", title="Model"),
                alt.Tooltip("mean_consistency:Q", title="Consistency", format=".3f"),
                alt.Tooltip("ci_low:Q", title="CI Low", format=".3f"),
                alt.Tooltip("ci_high:Q", title="CI High", format=".3f"),
            ],
        )
    )

    # Add confidence bands
    band = (
        alt.Chart(consistency_df)
        .mark_area(opacity=0.2)
        .encode(
            x=alt.X("tier:O", sort=tier_order),
            y="ci_low:Q",
            y2="ci_high:Q",
            color=alt.Color(
                "agent_model:N",
                scale=alt.Scale(domain=domain, range=range_),
            ),
        )
    )

    # Combine
    chart = (band + line).properties(
        title="Consistency Score by Tier (Higher = More Deterministic)"
    )

    save_figure(chart, "fig12_consistency", output_dir, render)
