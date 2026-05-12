"""Diagnostic figures for distribution analysis.

Generates Fig 23 (Q-Q plots) and Fig 24 (score histograms with KDE).
Now split into per-tier figures for better readability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
from scipy import stats

from scylla.analysis.figures import derive_tier_order, get_color_scale
from scylla.analysis.figures.spec_builder import save_figure


def fig23_qq_plots(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None:
    """Generate Fig 23: Q-Q Plots (Quantile-Quantile).

    Q-Q plots per (model, tier) to assess normality.
    Compares theoretical quantiles (normal distribution) vs observed quantiles.
    Points should fall on diagonal line if data is normally distributed.

    Now generates separate figures per tier (fig23a-T0, fig23b-T1, etc.)
    for improved readability and analysis.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF

    """
    tier_order = derive_tier_order(runs_df)

    qq_data = []

    for model in sorted(runs_df["agent_model"].unique()):
        for tier in tier_order:
            tier_data = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)]

            if len(tier_data) < 3:
                continue

            # Get score data
            scores = tier_data["score"].dropna().values

            if len(scores) < 3:
                continue

            # Compute theoretical quantiles (standard normal)
            theoretical_quantiles = stats.norm.ppf(
                np.linspace(0.01, 0.99, len(scores))
            )  # Avoid 0 and 1

            # Compute observed quantiles (sorted, standardized)
            observed_sorted = np.sort(scores)
            observed_mean = np.mean(scores)
            observed_std = np.std(scores)
            observed_quantiles = (
                (observed_sorted - observed_mean) / observed_std
                if observed_std > 0
                else observed_sorted
            )

            for theoretical_q, observed_q, original_score in zip(
                theoretical_quantiles, observed_quantiles, observed_sorted, strict=False
            ):
                qq_data.append(
                    {
                        "agent_model": model,
                        "tier": tier,
                        "theoretical_quantile": theoretical_q,
                        "observed_quantile": observed_q,
                        "original_score": original_score,
                    }
                )

    qq_df = pd.DataFrame(qq_data)

    if len(qq_df) == 0:
        print("  Warning: No data for Q-Q plots")  # noqa: T201
        return

    # Generate separate figure for each tier
    for tier in tier_order:
        tier_qq_df = qq_df[qq_df["tier"] == tier]

        if len(tier_qq_df) == 0:
            continue

        # Get extent for reference line
        q_min = min(tier_qq_df["theoretical_quantile"].min(), tier_qq_df["observed_quantile"].min())
        q_max = max(tier_qq_df["theoretical_quantile"].max(), tier_qq_df["observed_quantile"].max())

        # Create base chart with data
        base = alt.Chart(tier_qq_df)

        # Get dynamic color scale for models
        models = sorted(tier_qq_df["agent_model"].unique())
        model_domain, model_range = get_color_scale("models", models)

        # Create scatter plot layer with both models
        scatter = base.mark_circle(size=60, opacity=0.7).encode(
            x=alt.X(
                "theoretical_quantile:Q",
                title="Theoretical Quantiles (Normal)",
                scale=alt.Scale(zero=False),
            ),
            y=alt.Y(
                "observed_quantile:Q",
                title="Observed Quantiles (Standardized Score)",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color(
                "agent_model:N",
                title="Model",
                scale=alt.Scale(domain=model_domain, range=model_range),
            ),
            tooltip=[
                alt.Tooltip("agent_model:N", title="Model"),
                alt.Tooltip("tier:O", title="Tier"),
                alt.Tooltip("theoretical_quantile:Q", title="Theoretical Q", format=".2f"),
                alt.Tooltip("observed_quantile:Q", title="Observed Q", format=".2f"),
                alt.Tooltip("original_score:Q", title="Original Score", format=".3f"),
            ],
        )

        # Create single reference line (shared for both models)
        ref_df = pd.DataFrame(
            [
                {"theoretical_quantile": q_min, "observed_quantile": q_min},
                {"theoretical_quantile": q_max, "observed_quantile": q_max},
            ]
        )

        reference_line = (
            alt.Chart(ref_df)
            .mark_line(strokeDash=[5, 5], color="red", strokeWidth=2)
            .encode(x="theoretical_quantile:Q", y="observed_quantile:Q")
        )

        # Combine both models in single chart
        chart = (
            alt.layer(reference_line, scatter)
            .properties(
                title=f"Q-Q Plots - {tier} (Normal Distribution Assessment)",
                width=400,
                height=350,
            )
            .configure_view(strokeWidth=0)
        )

        # Save with tier-specific filename
        tier_suffix = tier.lower().replace(" ", "-")
        save_figure(chart, f"fig23_{tier_suffix}_qq_plots", output_dir, render)


def _compute_kde_data(runs_df: pd.DataFrame, tier_order: list[str]) -> pd.DataFrame:
    """Compute KDE density values for each (model, tier) combination.

    Args:
        runs_df: Runs DataFrame with agent_model, tier, and score columns.
        tier_order: Ordered list of tier labels.

    Returns:
        DataFrame with columns: agent_model, tier, score, density.

    """
    kde_data = []
    for model in sorted(runs_df["agent_model"].unique()):
        for tier in tier_order:
            tier_data = runs_df[(runs_df["agent_model"] == model) & (runs_df["tier"] == tier)]
            scores = tier_data["score"].dropna().values
            if len(scores) < 3:
                continue
            try:
                kde = stats.gaussian_kde(scores)
                x_range = np.linspace(0, 1, 100)
                kde_values = kde(x_range)
                for x, density in zip(x_range, kde_values, strict=False):
                    kde_data.append(
                        {"agent_model": model, "tier": tier, "score": x, "density": density}
                    )
            except Exception as e:
                print(f"  Warning: KDE failed for {model}/{tier}: {e}")  # noqa: T201
    return pd.DataFrame(kde_data)


def _build_kde_overlay(
    tier_kde_df: pd.DataFrame,
    tier_runs_df: pd.DataFrame,
    domain: list[str],
    range_: list[str],
) -> Any:
    """Build a scaled KDE line overlay chart for a single tier.

    Args:
        tier_kde_df: KDE data for the tier.
        tier_runs_df: Run data for the tier (used for count scaling).
        domain: Color domain list.
        range_: Color range list.

    Returns:
        Altair line chart with scaled density.

    """
    tier_kde_df = tier_kde_df.copy()
    for model in tier_kde_df["agent_model"].unique():
        model_mask = tier_kde_df["agent_model"] == model
        model_density_max = tier_kde_df.loc[model_mask, "density"].max()
        model_count = len(tier_runs_df[tier_runs_df["agent_model"] == model])
        if model_density_max > 0:
            tier_kde_df.loc[model_mask, "scaled_density"] = tier_kde_df.loc[
                model_mask, "density"
            ] * (model_count / model_density_max)
    return (
        alt.Chart(tier_kde_df)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("score:Q"),
            y=alt.Y("scaled_density:Q"),
            color=alt.Color(
                "agent_model:N",
                scale=alt.Scale(domain=domain, range=range_),
            ),
        )
    )


def fig24_score_histograms(runs_df: pd.DataFrame, output_dir: Path, render: bool = True) -> None:
    """Generate Fig 24: Score Histograms with KDE Overlay.

    Histograms with kernel density estimate (KDE) overlay.
    Now generates separate figures per tier (fig24a-T0, fig24b-T1, etc.)
    for improved readability.

    Args:
        runs_df: Runs DataFrame
        output_dir: Output directory
        render: Whether to render to PNG/PDF

    """
    tier_order = derive_tier_order(runs_df)
    kde_df = _compute_kde_data(runs_df, tier_order)

    # Get dynamic color scale for models
    models = sorted(runs_df["agent_model"].unique())
    domain, range_ = get_color_scale("models", models)

    # Generate separate figure for each tier
    for tier in tier_order:
        tier_runs_df = runs_df[runs_df["tier"] == tier]
        tier_kde_df = kde_df[kde_df["tier"] == tier]

        if len(tier_runs_df) == 0:
            continue

        # Create histogram
        histogram = (
            alt.Chart(tier_runs_df)
            .mark_bar(opacity=0.5, binSpacing=0)
            .encode(
                x=alt.X("score:Q", title="Score", bin=alt.Bin(maxbins=20)),
                y=alt.Y("count():Q", title="Frequency"),
                color=alt.Color(
                    "agent_model:N",
                    title="Agent Model",
                    scale=alt.Scale(domain=domain, range=range_),
                ),
                tooltip=[
                    alt.Tooltip("agent_model:N", title="Model"),
                    alt.Tooltip("count():Q", title="Count"),
                ],
            )
        )

        # Create KDE overlay if data exists
        if len(tier_kde_df) > 0:
            kde_lines = _build_kde_overlay(tier_kde_df, tier_runs_df, domain, range_)
            chart = alt.layer(histogram, kde_lines, data=tier_runs_df)
        else:
            chart = histogram

        # Configure chart
        chart = (
            chart.properties(
                title=f"Score Distribution - {tier} (with KDE Overlay)",
                width=600,
                height=400,
            )
            .configure_view(strokeWidth=0)
            .configure_axis(labelFontSize=12, titleFontSize=14)
            .configure_legend(labelFontSize=12, titleFontSize=14)
        )

        # Save with tier-specific filename
        tier_suffix = tier.lower().replace(" ", "-")
        save_figure(chart, f"fig24_{tier_suffix}_score_histogram", output_dir, render)
