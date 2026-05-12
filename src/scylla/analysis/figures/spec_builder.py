"""Vega-Lite specification builder utilities.

Provides helpers for creating publication-quality Vega-Lite charts with
consistent theming and color schemes.
"""

from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd

from scylla.analysis.figures import get_color_scale


def compute_dynamic_domain(
    series: pd.Series,
    padding_fraction: float = 0.1,
    min_range: float = 0.1,
    floor: float = 0.0,
    ceiling: float = 1.0,
) -> list[float]:
    """Compute tight axis domain from data with padding.

    Calculates data min/max, adds padding, enforces minimum range,
    rounds to nearest 0.05 for clean axis labels, and clamps to [floor, ceiling].

    Args:
        series: Pandas series containing numeric data
        padding_fraction: Fraction of range to add as padding (default: 0.1 = 10%)
        min_range: Minimum range to enforce (default: 0.1)
        floor: Minimum allowed domain value (default: 0.0)
        ceiling: Maximum allowed domain value (default: 1.0)

    Returns:
        Two-element list [min, max] suitable for alt.Scale(domain=...)

    Example:
        >>> data = pd.Series([0.94, 0.95, 0.96, 0.97, 0.98])
        >>> compute_dynamic_domain(data)
        [0.90, 1.00]  # Tight domain showing actual variation

    """
    if len(series) == 0 or series.isna().all():
        return [floor, ceiling]

    # Compute data min/max
    data_min = float(series.min())
    data_max = float(series.max())

    # Add padding
    data_range = data_max - data_min
    if data_range < min_range:
        # Center the range if it's too small
        center = (data_min + data_max) / 2
        data_min = center - min_range / 2
        data_max = center + min_range / 2
        data_range = min_range

    padding = data_range * padding_fraction
    domain_min = data_min - padding
    domain_max = data_max + padding

    # Round to nearest 0.05 for clean axis labels
    domain_min = round(domain_min / 0.05) * 0.05
    domain_max = round(domain_max / 0.05) * 0.05

    # Clamp to [floor, ceiling]
    domain_min = max(floor, domain_min)
    domain_max = min(ceiling, domain_max)

    # Ensure domain_min < domain_max
    if domain_min >= domain_max:
        domain_min = floor
        domain_max = ceiling

    return [domain_min, domain_max]


def compute_dynamic_domain_with_ci(
    means: pd.Series, ci_lows: pd.Series, ci_highs: pd.Series, **kwargs: float
) -> list[float]:
    """Compute tight axis domain from data including CI bounds.

    Combines means and confidence interval bounds to compute a domain that
    encompasses all error bar whiskers.

    Args:
        means: Pandas series containing mean values
        ci_lows: Pandas series containing lower CI bounds
        ci_highs: Pandas series containing upper CI bounds
        **kwargs: Additional arguments passed to compute_dynamic_domain

    Returns:
        Two-element list [min, max] suitable for alt.Scale(domain=...)

    Example:
        >>> means = pd.Series([0.50, 0.60, 0.70])
        >>> ci_lows = pd.Series([0.45, 0.55, 0.65])
        >>> ci_highs = pd.Series([0.55, 0.65, 0.75])
        >>> compute_dynamic_domain_with_ci(means, ci_lows, ci_highs)
        [0.40, 0.80]  # Domain encompasses all whiskers

    """
    combined = pd.concat([means, ci_lows, ci_highs]).dropna()
    return compute_dynamic_domain(combined, **kwargs)


def apply_publication_theme() -> None:
    """Register publication-quality theme for all charts."""
    theme = {
        "config": {
            "font": "serif",
            "axis": {
                "labelFontSize": 11,
                "titleFontSize": 13,
                "gridColor": "#e0e0e0",
                "domainColor": "#333333",
            },
            "legend": {
                "labelFontSize": 11,
                "titleFontSize": 12,
            },
            "title": {
                "fontSize": 14,
                "anchor": "start",
                "fontWeight": "normal",
            },
            "view": {
                "stroke": None,
                "continuousWidth": 400,
                "continuousHeight": 300,
            },
            "mark": {
                "tooltip": True,
            },
        }
    }

    alt.themes.register("publication", lambda: theme)
    alt.themes.enable("publication")


def model_color_scale(models: list[str]) -> alt.Scale:
    """Create consistent color scale for agent models.

    Args:
        models: List of model display names

    Returns:
        Altair Scale with model colors

    """
    domain, range_ = get_color_scale("models", models)
    return alt.Scale(domain=domain, range=range_)


def save_figure(
    chart: alt.TopLevelMixin,
    name: str,
    output_dir: Path,
    render: bool = True,
    formats: list[str] | None = None,
    latex_caption: str | None = None,
) -> None:
    """Save chart as Vega-Lite JSON + optionally rendered images + LaTeX snippet.

    Args:
        chart: Altair chart
        name: Figure name (without extension)
        output_dir: Output directory
        render: Whether to render to raster/vector formats
        formats: List of formats to render ("png", "pdf", "svg")
        latex_caption: Optional custom LaTeX caption (defaults to chart title)

    """
    if formats is None:
        formats = ["png"]  # PDF generation disabled by default

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save Vega-Lite JSON spec with proper formatting
    spec = chart.to_dict()
    spec_path = output_dir / f"{name}.vl.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"  Saved spec: {spec_path}")  # noqa: T201

    # Optionally render to images
    if render:
        for fmt in formats:
            try:
                img_path = output_dir / f"{name}.{fmt}"
                if fmt == "png":
                    chart.save(str(img_path), scale_factor=3.0)  # 300 DPI for publication
                else:
                    chart.save(str(img_path))
                print(f"  Rendered: {img_path}")  # noqa: T201
            except Exception as e:
                print(f"  Warning: Could not render {fmt}: {e}")  # noqa: T201

        # Generate LaTeX inclusion snippet if PDF was rendered
        if "pdf" in formats:
            _generate_latex_snippet(name, output_dir, chart, latex_caption)


def _generate_latex_snippet(
    name: str, output_dir: Path, chart: alt.TopLevelMixin, custom_caption: str | None = None
) -> None:
    """Generate LaTeX figure inclusion snippet.

    Args:
        name: Figure name (without extension)
        output_dir: Output directory
        chart: Altair chart (for extracting title)
        custom_caption: Optional custom caption (overrides chart title)

    """
    # Extract caption from chart title or use custom caption
    caption = custom_caption
    if caption is None:
        # Try to extract title from chart spec
        if hasattr(chart, "title") and chart.title:
            if isinstance(chart.title, str):
                caption = chart.title
            elif isinstance(chart.title, dict) and "text" in chart.title:
                caption = chart.title["text"]
        else:
            # Fallback: generate caption from name
            caption = name.replace("_", " ").replace("fig", "Figure ").title()

    # Generate LaTeX label from name
    label = f"fig:{name}"

    # Create LaTeX snippet
    latex_snippet = f"""\\begin{{figure}}[htbp]
\\centering
\\includegraphics[width=\\textwidth]{{{name}.pdf}}
\\caption{{{caption}}}
\\label{{{label}}}
\\end{{figure}}
"""

    # Save snippet
    snippet_path = output_dir / f"{name}_include.tex"
    snippet_path.write_text(latex_snippet)
    print(f"  Saved LaTeX snippet: {snippet_path}")  # noqa: T201
