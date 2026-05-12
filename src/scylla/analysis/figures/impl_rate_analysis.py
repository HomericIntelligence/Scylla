"""Implementation Rate analysis figures.

Generates figures for Impl-Rate metric analysis:
- Fig 25: Impl-Rate by tier (bar chart with CIs)
- Fig 26: Impl-Rate vs Pass-Rate scatter
- Fig 27: Impl-Rate distribution by tier
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
from scylla.analysis.stats import bootstrap_ci


def fig25_impl_rate_by_tier(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True,
) -> None:
    """Generate Fig 25: Implementation Rate by Tier.

    Grouped bar chart with 95% bootstrap confidence intervals.
    Analogous to fig04 but for Impl-Rate instead of Pass-Rate.

    Args:
        runs_df: Runs DataFrame (must include impl_rate column)
        output_dir: Output directory
        render: Whether to render to PNG/PDF

    """
    # Check if impl_rate column exists
    if "impl_rate" not in runs_df.columns:
        print("Warning: impl_rate column not found in runs_df, skipping fig25")  # noqa: T201
        return

    # Derive tier order from data
    tier_order = derive_tier_order(runs_df)

    # Count unique subtests per tier for annotations
    subtest_counts = {}
    for tier in tier_order:
        tier_data = runs_df[runs_df["tier"] == tier]
        if "subtest" in tier_data.columns:
            subtest_counts[tier] = tier_data["subtest"].nunique()
        else:
            # Fallback if subtest column doesn't exist
            subtest_counts[tier] = 0

    stats = []
    for model in runs_df["agent_model"].unique():
        for tier in tier_order:
            subset = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)]
            if len(subset) == 0:
                continue

            impl_rate = subset["impl_rate"].dropna()
            if len(impl_rate) == 0:
                continue

            mean, ci_low, ci_high = bootstrap_ci(impl_rate)

            # Add tier label with subtest count
            tier_label = f"{tier} (n={subtest_counts[tier]})" if subtest_counts[tier] > 0 else tier

            stats.append(
                {
                    "agent_model": model,
                    "tier": tier,
                    "tier_label": tier_label,
                    "impl_rate": mean,
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "n": len(impl_rate),
                }
            )

    df = pd.DataFrame(stats)

    # Get color scale for models
    models = sorted(df["agent_model"].unique())
    domain, range_ = get_color_scale("models", models)

    # Compute dynamic domain for impl_rate axis - include CI bounds
    impl_rate_domain = compute_dynamic_domain_with_ci(df["impl_rate"], df["ci_low"], df["ci_high"])

    # Create tier_label_order based on tier_order with counts
    tier_label_order = [
        f"{tier} (n={subtest_counts[tier]})" if subtest_counts[tier] > 0 else tier
        for tier in tier_order
    ]

    # Vega-Lite spec
    bars = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(
                "tier_label:N",
                title="Tier (Subtest Count)",
                axis=alt.Axis(labelAngle=0),
                sort=tier_label_order,
            ),
            y=alt.Y(
                "impl_rate:Q",
                title="Implementation Rate",
                scale=alt.Scale(domain=impl_rate_domain),
            ),
            color=alt.Color(
                "agent_model:N",
                title="Model",
                scale=alt.Scale(domain=domain, range=range_),
            ),
            xOffset="agent_model:N",
            tooltip=[
                alt.Tooltip("agent_model:N", title="Model"),
                alt.Tooltip("tier:N", title="Tier"),
                alt.Tooltip("impl_rate:Q", title="Impl-Rate", format=".3f"),
                alt.Tooltip("ci_low:Q", title="95% CI Low", format=".3f"),
                alt.Tooltip("ci_high:Q", title="95% CI High", format=".3f"),
                alt.Tooltip("n:Q", title="N"),
            ],
        )
    )

    # Error bars (95% CI)
    error_bars = (
        alt.Chart(df)
        .mark_errorbar()
        .encode(
            x=alt.X("tier_label:N", sort=tier_label_order),
            y=alt.Y("ci_low:Q", title="Implementation Rate"),
            y2="ci_high:Q",
            xOffset="agent_model:N",
        )
    )

    chart = (bars + error_bars).properties(
        title="Implementation Rate by Tier (95% Bootstrap CI)",
        width=400,
        height=300,
    )

    save_figure(chart, "fig25_impl_rate_by_tier", output_dir, render=render)


def fig26_impl_rate_vs_pass_rate(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True,
) -> None:
    """Generate Fig 26: Implementation Rate vs Pass-Rate Comparison.

    Grouped bar chart showing Impl-Rate and Pass-Rate side-by-side per model,
    with per-tier subfigures for detailed comparison.

    Args:
        runs_df: Runs DataFrame (must include impl_rate and passed columns)
        output_dir: Output directory
        render: Whether to render to PNG/PDF

    """
    # Check required columns
    if "impl_rate" not in runs_df.columns:
        print("Warning: impl_rate column not found in runs_df, skipping fig26")  # noqa: T201
        return

    # Compute aggregate metrics per (agent_model, tier)
    stats = []
    for (model, tier), group in runs_df.groupby(["agent_model", "tier"]):
        impl_rate_mean = group["impl_rate"].mean()
        pass_rate_mean = group["passed"].mean()

        stats.append(
            {"agent_model": model, "tier": tier, "metric": "Impl-Rate", "value": impl_rate_mean}
        )
        stats.append(
            {"agent_model": model, "tier": tier, "metric": "Pass-Rate", "value": pass_rate_mean}
        )

    df = pd.DataFrame(stats)

    if len(df) == 0:
        print("Warning: No valid data for fig26")  # noqa: T201
        return

    # Derive tier order
    tier_order = derive_tier_order(runs_df)

    # Get color scale for metrics
    metric_domain = ["Impl-Rate", "Pass-Rate"]
    metric_colors = ["#1f77b4", "#ff7f0e"]  # Blue for impl, orange for pass

    # Create grouped bar chart with per-tier subfigures
    bars = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("agent_model:N", title="Agent Model"),
            y=alt.Y("value:Q", title="Rate", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color(
                "metric:N",
                title="Metric",
                scale=alt.Scale(domain=metric_domain, range=metric_colors),
            ),
            xOffset="metric:N",
            tooltip=[
                alt.Tooltip("agent_model:N", title="Model"),
                alt.Tooltip("tier:O", title="Tier"),
                alt.Tooltip("metric:N", title="Metric"),
                alt.Tooltip("value:Q", title="Rate", format=".3f"),
            ],
        )
    )

    # Facet by tier
    chart = (
        bars.facet(
            column=alt.Column("tier:O", title="Tier", sort=tier_order),
        )
        .properties(title="Implementation Rate vs Pass-Rate per Tier")
        .resolve_scale(x="independent")
    )

    save_figure(chart, "fig26_impl_rate_vs_pass_rate", output_dir, render=render)


def fig27_impl_rate_distribution(
    runs_df: pd.DataFrame,
    output_dir: Path,
    render: bool = True,
) -> None:
    """Generate Fig 27: Implementation Rate Distribution by Tier.

    Violin plot showing distribution of Impl-Rate across tiers.

    Args:
        runs_df: Runs DataFrame (must include impl_rate column)
        output_dir: Output directory
        render: Whether to render to PNG/PDF

    """
    # Check if impl_rate column exists
    if "impl_rate" not in runs_df.columns:
        print("Warning: impl_rate column not found in runs_df, skipping fig27")  # noqa: T201
        return

    # Filter out NaN values
    df = runs_df[["agent_model", "tier", "impl_rate"]].dropna()

    if len(df) == 0:
        print("Warning: No valid data for fig27")  # noqa: T201
        return

    # Derive tier order from data
    tier_order = derive_tier_order(runs_df)

    # Get color scale for models
    models = sorted(df["agent_model"].unique())
    domain, range_ = get_color_scale("models", models)

    # Compute dynamic domain for impl_rate axis with increased padding for boxplot whiskers
    impl_rate_domain = compute_dynamic_domain(df["impl_rate"], padding_fraction=0.15)

    # Create base layered chart without faceting
    base_violin = (
        alt.Chart(df)
        .transform_density(
            density="impl_rate",
            groupby=["tier", "agent_model"],
            as_=["impl_rate", "density"],
        )
        .mark_area(orient="horizontal", opacity=0.5)
        .encode(
            x=alt.X(
                "density:Q",
                title=None,
                axis=alt.Axis(labels=False, ticks=False, grid=False),
            ),
            y=alt.Y(
                "impl_rate:Q",
                title="Implementation Rate",
                scale=alt.Scale(domain=impl_rate_domain),
            ),
            color=alt.Color(
                "agent_model:N",
                title="Model",
                scale=alt.Scale(domain=domain, range=range_),
            ),
        )
    )

    base_box = (
        alt.Chart(df)
        .mark_boxplot(size=20, opacity=0.7)
        .encode(
            x=alt.X(
                "agent_model:N",
                title="Model",
                axis=alt.Axis(labels=False, ticks=False),
            ),
            y=alt.Y(
                "impl_rate:Q",
                scale=alt.Scale(domain=impl_rate_domain),
            ),
            color=alt.Color(
                "agent_model:N",
                scale=alt.Scale(domain=domain, range=range_),
            ),
        )
    )

    # Layer first, then facet
    chart = (
        (base_violin + base_box)
        .properties(
            title="Implementation Rate Distribution by Tier",
            width=300,
            height=100,
        )
        .facet(
            row=alt.Row(
                "tier:N",
                title="Tier",
                sort=tier_order,
            ),
        )
    )

    save_figure(chart, "fig27_impl_rate_distribution", output_dir, render=render)
