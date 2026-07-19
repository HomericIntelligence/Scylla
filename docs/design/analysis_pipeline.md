# Analysis Pipeline

This document describes the analysis pipeline for Scylla experiment results.

## Overview

The analysis pipeline loads experiment data from `~/fullruns/`, computes statistical metrics, and generates publication-quality figures and tables for the paper.

## Data Structure

### Experiment Data (`~/fullruns/`)

```
fullruns/
├── test001-nothinking/
│   └── 2026-01-20T06-50-26-test-001/  # Sonnet 4.5
│       ├── T0/00/run_01/...run_10/
│       ├── ...
│       └── T6/01/run_01/...run_10/
└── test001-nothinking-haiku/
    └── 2026-01-23T17-01-08-test-001/  # Haiku 4.5
        ├── T0/00/run_01/...run_10/
        └── ...
```

### Exported Data (`docs/data/`)

| File | Rows | Description |
|------|------|-------------|
| `runs.csv` | 2,238 | One row per run (113 subtests × 10 runs × 2 models) |
| `judges.csv` | 6,216 | One row per (run, judge) - 3 judges per run |
| `criteria.csv` | 30,929 | One row per (run, judge, criterion) - 5 criteria per judge |
| `subtests.csv` | 226 | Pre-aggregated per (experiment, tier, subtest) |
| `summary.json` | - | Overall statistics and summary |

### Generated Figures (`docs/figures/`)

Each figure has three files:

- `.vl.json` - Vega-Lite specification (text-based, human-readable)
- `.csv` - Data slice used by the figure
- `.png`, `.pdf` (optional) - Rendered images

| Figure | Description | Data Source |
|--------|-------------|-------------|
| `fig01_score_variance_by_tier` | Box plots of score distribution | runs_df |
| `fig02_judge_variance` | Per-judge scoring variance | judges_df |
| `fig03_failure_rate_by_tier` | Grade distribution stacked bars | runs_df |
| `fig04_pass_rate_by_tier` | Pass rate with 95% CI | runs_df |
| `fig05_grade_heatmap` | Grade proportions heatmap | runs_df |
| `fig06_cop_by_tier` | Cost-of-Pass by tier (log scale) | runs_df |
| `fig07_token_distribution` | Token breakdown stacked bars | runs_df |
| `fig08_cost_quality_pareto` | Cost vs quality Pareto frontier | runs_df |
| `fig09_criteria_by_tier` | Per-criteria performance | criteria_df |
| `fig10_score_violin` | Score distribution violins | runs_df |
| `fig11_tier_uplift` | Tier transition uplift line chart | runs_df |
| `fig12_consistency` | Consistency by tier with 95% CI | runs_df |
| `fig13_latency` | Latency breakdown by tier | runs_df |
| `fig14_judge_agreement` | Inter-judge correlation scatter matrix | judges_df |
| `fig15_subtest_heatmap` | Subtest performance heatmap | runs_df |
| `fig16_success_variance_by_test` | Success variance by test | runs_df |
| `fig17_judge_variance_overall` | Overall judge variance | judges_df |
| `fig18_failure_rate_by_test` | Failure rate by test | runs_df |

## Usage

### Install Analysis Environment

```bash
# Install analysis dependencies (pandas, matplotlib, altair, etc.)
uv sync --all-groups --all-extras
```

### Export Data

```bash
# Export all data to CSV
uv run python scripts/export_data.py

# Outputs:
#   docs/data/runs.csv
#   docs/data/judges.csv
#   docs/data/criteria.csv
#   docs/data/subtests.csv
#   docs/data/summary.json
```

### Generate Figures

```bash
# Generate all figures (specs + CSV only, no rendering)
uv run python scripts/generate_figures.py --no-render

# Generate specific figures
uv run python scripts/generate_figures.py \
    --no-render \
    --figures fig01_score_variance_by_tier,fig02_judge_variance

# List available figures
uv run python scripts/generate_figures.py --list-figures

# Outputs:
#   docs/figures/figNN_*.vl.json  (Vega-Lite specs)
#   docs/figures/figNN_*.csv      (Data slices)
```

### Render Figures to Images (Optional)

```bash
# Requires vl-convert-python (already in the uv environment)
uv run python scripts/generate_figures.py

# Outputs additional files:
#   docs/figures/figNN_*.png  (300 DPI raster)
#   docs/figures/figNN_*.pdf  (vector)
```

### View Figures

**Vega-Lite Specs (Recommended):**

- Open `.vl.json` files in [Vega Editor](https://vega.github.io/editor/)
- Interactive, zoomable, tooltips work
- Can export to PNG/SVG/PDF from the editor

**CSV Data:**

- Open in Excel, R, Python, or any tool
- Portable, text-based

**Rendered Images:**

- Use for quick preview
- Embed in LaTeX or Markdown documents

## Summary Statistics

From `docs/data/summary.json`:

```json
{
  "total_experiments": 2,
  "total_runs": 2238,
  "total_judge_evaluations": 6216,
  "total_criteria_scores": 30929,
  "total_subtests": 226,
  "models": ["Sonnet 4.5", "Haiku 4.5"],
  "tiers": ["T0", "T1", "T2", "T3", "T4", "T5", "T6"],
  "overall_stats": {
    "pass_rate": 0.839,
    "mean_score": 0.786,
    "total_cost": 134.49,
    "mean_cost_per_run": 0.060
  },
  "by_model": {
    "Sonnet 4.5": {
      "total_runs": 1130,
      "pass_rate": 0.942,
      "mean_score": 0.908,
      "total_cost": 86.87,
      "mean_cost_per_run": 0.077
    },
    "Haiku 4.5": {
      "total_runs": 1108,
      "pass_rate": 0.734,
      "mean_score": 0.662,
      "total_cost": 47.62,
      "mean_cost_per_run": 0.043
    }
  }
}
```

## Architecture

### Data Loading (`scylla.analysis.loader`)

- Traverses experiment directory hierarchy
- Parses `run_result.json` for consensus metrics
- Parses `judge/judge_NN/judgment.json` for per-judge evaluations
- Parses `judge/judge_NN/MODEL.md` for judge model IDs
- Handles corrupted/incomplete runs gracefully (skips with warnings)

### DataFrame Construction (`scylla.analysis.dataframes`)

- Converts loaded data to pandas DataFrames
- Four core DataFrames: runs, judges, criteria, subtests
- Provides aggregation helpers: tier_summary(), model_comparison(), etc.

### Statistical Analysis (`scylla.analysis.stats`)

- Bootstrap confidence intervals (95% CI, 10K resamples, BCa method)
- Mann-Whitney U test (non-parametric significance)
- Cliff's delta (non-parametric effect size)
- Inter-rater reliability: Krippendorff's alpha, Spearman/Pearson correlation
- Multiple comparison correction: Bonferroni

### Figure Generation (`scylla.analysis.figures`)

- Uses altair (Python Vega-Lite API) for declarative specifications
- Consistent color palettes across all figures
- Publication-quality theme (serif fonts, clean axes)
- Dual output: Vega-Lite JSON + CSV data

### Color Palette

```python
COLORS = {
    "models": {
        "Sonnet 4.5": "#4C78A8",  # Blue
        "Haiku 4.5": "#E45756",   # Red
    },
    "tiers": {
        "T0": "#66c2a5", "T1": "#fc8d62", "T2": "#8da0cb",
        "T3": "#e78ac3", "T4": "#a6d854", "T5": "#ffd92f", "T6": "#e5c494"
    },
    "grades": {
        "S": "#FFD700", "A": "#2ecc71", "B": "#3498db",
        "C": "#f39c12", "D": "#e67e22", "F": "#e74c3c"
    },
    "criteria": {
        "functional": "#4C78A8",
        "code_quality": "#E45756",
        "proportionality": "#72B7B2",
        "build_pipeline": "#F58518",
        "overall_quality": "#54A24B"
    }
}
```

### Generated Tables (`docs/tables/`)

Each table has two files:

- `.md` - Markdown format (GitHub-rendered)
- `.tex` - LaTeX format (paper integration)

| Table | Description | Data Source |
|-------|-------------|-------------|
| `table01_tier_summary` | Tier performance summary with 95% CI | runs_df |
| `table02_tier_comparison` | Pairwise tier comparison with Mann-Whitney U | runs_df |
| `table03_judge_agreement` | Inter-rater reliability (Krippendorff's alpha) | judges_df |
| `table04_criteria_performance` | Per-criteria performance with significance tests | criteria_df |
| `table05_cost_analysis` | Cost metrics by tier | runs_df |
| `table06_model_comparison` | Model comparison summary | runs_df |
| `table07_subtest_results` | Full subtest results (Appendix B) | subtests_df |

### Generate Tables

```bash
# Generate all tables
uv run python scripts/generate_tables.py

# Generate specific tables
uv run python scripts/generate_tables.py \
    --tables table01_tier_summary,table02_tier_comparison

# List available tables
uv run python scripts/generate_tables.py --list-tables

# Outputs:
#   docs/tables/tableNN_*.md   (Markdown)
#   docs/tables/tableNN_*.tex  (LaTeX)
```

## Complete Pipeline

Run the entire analysis pipeline (data export, figures, tables):

```bash
uv run python scripts/generate_all_results.py
```

This script runs:

1. `export_data.py` - Export DataFrames to CSV
2. `generate_figures.py --no-render` - Generate all 18 figures
3. `generate_tables.py` - Generate all 7 tables

## Next Steps

### Narrative Generation (Future Work)

- Section 9: Results (performance, judges, economics)
- Section 10: Discussion (diminishing returns, hypothesis validation)
- Section 11: Conclusions
- Appendix B: Detailed results
This entire module uses Python because it interfaces with Python-only scientific computing libraries:

- **pandas**: DataFrame operations, aggregation
- **numpy**: Numerical operations, array manipulation
- **scipy**: Statistical tests (Mann-Whitney, bootstrap)
- **matplotlib/seaborn**: Plotting libraries (optional renderers)
- **altair**: Vega-Lite specification generation

Per AGENTS.md: "Interface with Python-only libraries → Python (allowed, document why)".

Mojo cannot be used here as there are no equivalent libraries in Mojo for these operations.
