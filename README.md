# Scylla

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![Tests](https://github.com/HomericIntelligence/Scylla/actions/workflows/test.yml/badge.svg)](https://github.com/HomericIntelligence/Scylla/actions/workflows/test.yml)
[![CI Image](https://github.com/HomericIntelligence/Scylla/actions/workflows/ci-image.yml/badge.svg)](https://github.com/HomericIntelligence/Scylla/actions/workflows/ci-image.yml)
[![Docker Test](https://github.com/HomericIntelligence/Scylla/actions/workflows/docker-test.yml/badge.svg)](https://github.com/HomericIntelligence/Scylla/actions/workflows/docker-test.yml)
[![Security](https://github.com/HomericIntelligence/Scylla/actions/workflows/security.yml/badge.svg)](https://github.com/HomericIntelligence/Scylla/actions/workflows/security.yml)
[![Pre-commit](https://github.com/HomericIntelligence/Scylla/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/HomericIntelligence/Scylla/actions/workflows/pre-commit.yml)
[![Release](https://github.com/HomericIntelligence/Scylla/actions/workflows/release.yml/badge.svg)](https://github.com/HomericIntelligence/Scylla/actions/workflows/release.yml)

## 📑 Table of Contents

- [🎯 What is Scylla?](#-what-is-scylla)
- [Core Concepts](#core-concepts)
- [🚀 Quick Start](#-quick-start)
- [CLI Reference](#cli-reference)
- [📊 System Requirements](#-system-requirements)
- [Analysis Pipeline Architecture](#analysis-pipeline-architecture)
- [Scripts (Advanced / Internal Tooling)](#scripts-advanced--internal-tooling)
- [Development](#development)
  - [Git Hooks](#git-hooks)
- [🔧 Troubleshooting](#-troubleshooting)
- [Publication Readiness](#publication-readiness)
- [🤝 Contributing](#-contributing)

## 🎯 What is Scylla?

Scylla is a comprehensive testing framework for AI agent workflows that:

- **🔬 Measures** agent performance under constrained conditions
- **📈 Analyzes** results with rigorous statistical methods
- **⚖️ Optimizes** agent decisions through trade-off evaluation
- **📋 Generates** publication-ready reports, figures, and tables

**Key Output**: Publication-quality statistical reports with **34 figures** and **11 tables** from a single command.

> "In Homer's Odyssey, Scylla represents one of the greatest challenges on the journey home — a monster that forced sailors to navigate perilous straits where every choice carried risk. Scylla provides the same proving ground for AI agents."

## Quick Start Guide

```bash
pixi install && pixi run pytest tests/ -v
```

See [docs/dev/onboarding.md](docs/dev/onboarding.md) for full onboarding instructions,
IDE setup (VS Code / Codespaces), and a first-contribution walkthrough.

### 💡 Usage Examples

**Quick evaluation run:**

```bash
# List available test cases and tiers
scylla list
scylla list-tiers
scylla list-models

# Run a test case across one tier with a specific model
scylla run 001-justfile-to-makefile --tier T0 --model claude-sonnet-4-6

# Check evaluation status
scylla status 001-justfile-to-makefile

# Generate a markdown report
scylla report 001-justfile-to-makefile --format markdown
```

See [CLI Reference](#cli-reference) for the full command set.

---

## CLI Reference

Scylla ships a `scylla` command-line tool (declared in `pyproject.toml` as
`scylla = "scylla.cli.main:cli"`). After `pixi install` the binary is available in the
environment:

```bash
scylla --help
```

```
Usage: scylla [OPTIONS] COMMAND [ARGS]...

  Scylla - AI Agent Testing Framework.
  Evaluate and benchmark AI agent architectures across multiple tiers.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  audit        Audit configuration files for consistency issues.
  list         List available test cases.
  list-models  List configured models.
  list-tiers   List available evaluation tiers.
  report       Generate report for a completed test.
  run          Run evaluation for a test case.
  status       Show status of a test evaluation.
```

### Common Workflows

**Discover what is available:**

```bash
scylla list                  # all test cases
scylla list --verbose        # with detailed info
scylla list-tiers            # T0–T6 descriptions
scylla list-models           # configured models
```

**Run an evaluation:**

```bash
# Single tier
scylla run 001-justfile-to-makefile --tier T0

# Multiple tiers, specific model, 5 runs each
scylla run 001-justfile-to-makefile --tier T0 --tier T1 \
  --model claude-sonnet-4-6 --runs 5

# Override output directory
scylla run 001-justfile-to-makefile --output-dir ~/my-results --verbose
```

**Inspect results:**

```bash
scylla status 001-justfile-to-makefile

# Reports in different formats
scylla report 001-justfile-to-makefile --format markdown
scylla report 001-justfile-to-makefile --format json --output -
scylla report 001-justfile-to-makefile --format html --output report.html
```

**Audit configuration:**

```bash
scylla audit models          # check filename/model_id consistency
```

### Shell Completion

Enable tab-completion for your shell once:

```bash
# bash
_SCYLLA_COMPLETE=bash_source scylla > ~/.scylla-complete.bash
echo 'source ~/.scylla-complete.bash' >> ~/.bashrc

# zsh
_SCYLLA_COMPLETE=zsh_source scylla > ~/.scylla-complete.zsh
echo 'source ~/.scylla-complete.zsh' >> ~/.zshrc

# fish
_SCYLLA_COMPLETE=fish_source scylla > ~/.config/fish/completions/scylla.fish
```

---

## 📊 System Requirements

**Minimum Requirements:**

- Python 3.10+
- 8GB RAM for full dataset analysis
- 2GB disk space for results

**Typical Performance:**

- Full analysis: 10-15 minutes (10,000 bootstrap samples)
- Figures only: 2-3 minutes
- Tables only: 1-2 minutes

**Scale:** Handles experiments with 1000+ runs efficiently

---

## Core Concepts

- ⚖️ **Trade-Off Evaluation**: Agents face scenarios where every decision has cost, mirroring Scylla and Charybdis dilemma
- 📊 **Metrics & Benchmarks**: Structured measurement across adaptability, efficiency, and reliability
- 🔄 **Iterative Optimization**: Continuous refinement through repeated trials
- 🧭 **Ablation Benchmarking**: Systematic evaluation of agent architectures across complexity tiers

## Ecosystem

Part of a 12-repository ecosystem:

| Repository | Role |
|------------|------|
| **AchaeanFleet** | Container images for the agent mesh — base images, Dockerfiles, Compose |
| **Myrmidons** | GitOps agent provisioning — agent definitions as code |
| **Odysseus** | CLI and core platform for agent lifecycle management |
| **ProjectArgus** | Observability — monitoring and metrics |
| **ProjectHephaestus** | Shared Python utilities and foundational tools |
| **ProjectHermes** | Webhook-to-NATS bridge — event ingestion |
| **ProjectKeystone** | DAG execution engine |
| **ProjectMnemosyne** | Skills marketplace — team knowledge sharing |
| **ProjectOdyssey** | Training and capability development for agents |
| **ProjectProteus** | CI/CD pipeline infrastructure |
| **Scylla** | Testing, measurement, and optimization under constraints (this project) |
| **ProjectTelemachy** | Workflow engine |

---

## Running the Analysis Pipeline

> **Note:** This section uses internal `scripts/*.py` tools for bulk statistical analysis and
> publication-pipeline tasks. For running individual evaluations, see the [`scylla` CLI](#cli-reference).

### Full Analysis (Recommended)

Generate all outputs (data exports, figures, tables):

```bash
pixi run python scripts/generate_all_results.py \
  --data-dir ~/fullruns \
  --output-dir results/analysis
```

**Key Options:**

- `--data-dir` → Directory with experiment results (default: `~/fullruns`)
- `--output-dir` → Base output directory (default: `docs/`)
- `--no-render` → Skip PNG/PDF (faster, Vega-Lite specs only)
- `--skip-data/skip-figures/skip-tables` → Generate specific components only
- `--exclude` → Filter experiments (e.g., `--exclude test001-dryrun`)

```bash
# Development mode - no rendering
pixi run python scripts/generate_all_results.py \
  --no-render \
  --exclude test001-dryrun test001-debug

# Regenerate tables only (assumes data/figures exist)
pixi run python scripts/generate_all_results.py \
  --skip-data --skip-figures
```

### Individual Pipeline Steps

**1. Export Data Only**

```bash
pixi run python scripts/export_data.py \
  --data-dir ~/fullruns \
  --output-dir results/analysis/data
```

**Outputs:** `runs.csv`, `judges.csv`, `criteria.csv`, `subtests.csv`, `summary.json`, `statistical_results.json`

**2. Generate Figures Only (34 figures × 5 formats)**

```bash
pixi run python scripts/generate_figures.py \
  --data-dir ~/fullruns \
  --output-dir results/analysis/figures
```

**Outputs:** `*.vl.json`, `*.csv`, `*.png` (300 DPI), `*.pdf`, `*_include.tex`

**3. Generate Tables Only (11 tables × 2 formats)**

```bash
pixi run python scripts/generate_tables.py \
  --data-dir ~/fullruns \
  --output-dir results/analysis/tables
```

**Outputs:** `*.md` (human-readable), `*.tex` (LaTeX, booktabs formatted)

### Output Structure

```
results/analysis/
├── data/
│   ├── runs.csv                      # Per-run metrics
│   ├── judges.csv                    # Judge evaluations
│   ├── criteria.csv                  # Criterion-level scores
│   ├── subtests.csv                  # Subtest metadata
│   ├── summary.json                  # Experiment summary
│   └── statistical_results.json      # Statistical analysis
├── figures/                          # 34 figures × 5 formats
│   ├── fig01_score_variance.*
│   ├── fig02_grade_distribution.*
│   └── ... (34 total)
└── tables/                           # 11 tables × 2 formats
    ├── table01_tier_summary.md
    ├── table01_tier_summary.tex
    └── ... (11 total)
```

### Using the Outputs

**LaTeX Integration:**

```latex
\begin{figure}
  \centering
  \input{results/analysis/figures/fig04_pass_rate_by_tier_include.tex}
  \caption{Pass rate by tier with 95\% bootstrap confidence intervals.}
  \label{fig:pass-rate}
\end{figure}

\input{results/analysis/tables/table02_tier_comparison.tex}
```

**Python/Jupyter:**

```python
import pandas as pd
import json

# Load data
runs_df = pd.read_csv('results/analysis/data/runs.csv')
judges_df = pd.read_csv('results/analysis/data/judges.csv')

# Load statistical results
with open('results/analysis/data/statistical_results.json') as f:
    stats = json.load(f)
```

---

## Scripts (Advanced / Internal Tooling)

> **Note:** The `scripts/*.py` files are internal automation tools used for bulk experiment management
> and publication-pipeline tasks. Most users should use the [`scylla` CLI](#cli-reference) instead.
> These scripts are documented here for contributors and advanced workflows.

### 🧪 Running Experiments

**Primary Experiment Runner:**

```bash
# Run full experiment
pixi run python scripts/manage_experiment.py run --config config/test.yaml

# Run specific tiers
pixi run python scripts/manage_experiment.py run \
  --tiers-dir tests/fixtures/tests/test-001 \
  --tiers T0 T1 --runs 10 -v
```

**Container-Based Execution:**

```bash
./scripts/setup_api_key.sh
./scripts/run_experiment_in_container.sh \
  --tiers-dir tests/fixtures/tests/test-001 \
  --tiers T0 --runs 5 --verbose
```

### 🔄 Recovery & Re-running

```bash
# Re-run failed agents
pixi run python scripts/manage_experiment.py rerun-agents \
  ~/fullruns/test_experiment --tier T0 T1

# Re-run failed judges
pixi run python scripts/manage_experiment.py rerun-judges \
  ~/fullruns/test_experiment
```

### 📊 Results Management

```bash
# Regenerate all results
pixi run python scripts/manage_experiment.py regenerate \
  ~/fullruns/test_experiment

# Repair corrupt checkpoint
pixi run python scripts/manage_experiment.py repair \
  ~/fullruns/test_experiment/checkpoint.json
```

---

## Analysis Pipeline Architecture

### Statistical Methodology

Rigorous non-parametric methods for bounded, ordinal, non-normal data:

- **Bootstrap Confidence Intervals**: BCa with 10,000 resamples
- **Omnibus Testing**: Kruskal-Wallis H test (controls FWER)
- **Pairwise Comparisons**: Mann-Whitney U + Holm-Bonferroni correction
- **Effect Sizes**: Cliff's delta with bootstrapped CIs
- **Inter-Rater Reliability**: Krippendorff's alpha for judge agreement

Configuration: `src/scylla/analysis/config.yaml` (all parameters externalized)

### Metrics

**Quality:**

- Pass-Rate (functional test coverage)
- Implementation Rate (semantic satisfaction)
- Score (weighted rubric evaluation)
- Consistency (1 - Coefficient of Variation)

**Economic:**

- Cost-of-Pass (expected cost per success)
- Frontier CoP (minimum CoP across configs)
- Token Distribution (cost breakdown)

**Process:**

- Latency (query to resolution time)
- Judge Agreement (Krippendorff's alpha)

### Data Requirements

Expected structure:

```
fullruns/{experiment_name}/{timestamp}/
├── config/experiment.json            # Metadata
└── T0-T6/{subtest_id}/run_{01-10}/
    ├── run_result.json              # Outcomes
    └── judge/judge_{01-03}/judgment.json  # Evaluations
```

**Required in run.json:**

- `run_number` (integer)
- `exit_code` (0 = success)
- `judges` (list with grades & criteria)

Schema: `src/scylla/analysis/schemas/run_result.schema.json`

---

## Development

### 🧪 Testing

Scylla has a comprehensive test suite covering all functionality. To see the current test count:

```bash
pixi run pytest tests/ --collect-only -q | tail -1
```

#### Test Categories

- **Unit Tests**: Analysis (incl. integration-style tests), adapters, config, executors, judges, metrics, reporting
- **E2E Tests** (1 file): Full pipeline validation
- **Test Fixtures** (47+ scenarios): Complete test cases with expected outputs

#### Running Tests

```bash
# All tests (comprehensive)
pixi run pytest tests/ --verbose

# Unit tests only (fastest)
pixi run pytest tests/unit/ -v

# Specific modules
pixi run pytest tests/unit/analysis/ -v
pixi run pytest tests/unit/adapters/ -v
pixi run pytest tests/unit/config/ -v

# Coverage analysis
pixi run pytest tests/ --cov=src/scylla --cov-report=html

# Specific test file
pixi run pytest tests/unit/analysis/test_stats.py -v
```

#### Test Quality Assurance

```bash
# Code quality (linting + formatting)
pixi run ruff check src/scylla/
pixi run ruff format src/scylla/ --check
```

### Git Hooks

Git hooks enforce quality checks locally before code reaches CI.
Install them once after cloning:

```bash
bash scripts/install_hooks.sh
```

| Hook | Trigger | What it does |
|------|---------|--------------|
| `pre-push` | Every `git push` | Runs the full test suite with coverage; aborts the push if tests fail or coverage drops below the threshold in `pyproject.toml` |

The coverage threshold is read directly from `pyproject.toml` — update it there and the hook stays in sync automatically.

> Hook source files live in `scripts/hooks/` and are version-controlled.
> See [`scripts/README.md`](scripts/README.md) for details.

### Adding Components

**New Figures:**

1. Create module in `src/scylla/analysis/figures/`
2. Implement function following existing pattern
3. Register in `scripts/generate_figures.py`
4. Add tests in `tests/unit/analysis/test_figures.py`

**New Tables:**

1. Add function to module in `src/scylla/analysis/tables/`
2. Register in `scripts/generate_tables.py`
3. Add tests in `tests/unit/analysis/test_tables.py`

### Code Quality

```bash
# Linting
pixi run ruff check src/scylla/analysis/

# Auto-fix and format
pixi run ruff check --fix src/scylla/analysis/
pixi run ruff format src/scylla/analysis/
```

---

## 🔧 Troubleshooting

### Quick Reference

| Symptom | Solution |
|---------|----------|
| `Schema validation failed: 'N/A' does not match` | Ensure grades are S, A, B, C, D, or F only |
| `[Errno 2] No such file or directory` | Run: `find ~/fullruns -name "run_result.json"` |
| `TypeError: unsupported operand` | Fix type coercion in criterion.achieved values |
| Empty outputs | Check: ≥2 experiments, ≥1 completed run each |
| Slow performance | Use `--no-render` flag for faster iteration |

### Common Issues

**1. Data Validation Errors**

```
Schema validation failed: 'N/A' does not match '^[SABCDF]$'
```

**Fix:** Review problematic runs, ensure valid grades S/A/B/C/D/F or update schema.

**2. Missing Files**

```
Failed to load: [Errno 2] No such file or directory
```

**Fix:** Incomplete runs skipped with warnings. Investigate:

```bash
find ~/fullruns -name "run_*" -type d -exec sh -c 'test -f "$1/run_result.json" || echo "Missing: $1"' _ {} \;
```

**3. Type Errors**

```
TypeError: unsupported operand type(s) for +: 'float' and 'str'
```

**Fix:** Some `criterion.achieved` are strings. Fix in data generation or add coercion.

### Getting Help

- **Documentation**: `docs/research.md` for methodology
- **Examples**: `tests/unit/analysis/` for usage patterns
- **Issues**: [GitHub Issues](https://github.com/HomericIntelligence/Scylla/issues)
- **Support**: Create an issue with error message and steps to reproduce

---

## Publication Readiness

✅ **Rigorous non-parametric statistics** (Kruskal-Wallis, Mann-Whitney U, Cliff's delta)

✅ **Multiple comparison correction** (Holm-Bonferroni throughout)

✅ **Bootstrap confidence intervals** (BCa, 10K resamples, seed=42)

✅ **Effect sizes with confidence intervals**

✅ **300 DPI publication-quality figures**

✅ **LaTeX-ready tables** with booktabs formatting

✅ **Reproducible configuration** (all parameters in config.yaml)

✅ **Comprehensive test suite**

✅ **Documented methodology** with citations

See `docs/research.md` for complete research methodology and metric definitions.

### LaTeX Dependencies

Required packages for document compilation:

```latex
\documentclass{article}
 \usepackage{booktabs}   % Professional tables
 \usepackage{longtable}  % Multi-page tables
 \usepackage{threeparttable} % Table notes
 \usepackage{graphicx}   % Figure inclusion
 \usepackage{amsmath}    % Statistical symbols

\begin{document}
% Your content here
\end{document}
```

---

## 🤝 Contributing

We welcome contributions! Please see **[CONTRIBUTING.md](CONTRIBUTING.md)** for detailed guidelines on:

- Development setup and environment configuration
- Git workflow and branch management
- Code quality standards and testing requirements
- Pull request and code review process
- Issue reporting guidelines

**Quick Start for Contributors:**

1. Fork the repository and clone locally
2. Copy `.env.example` to `.env` and configure API keys
3. Install dependencies: `curl -fsSL https://pixi.sh/install.sh | bash`
4. Install git hooks: `bash scripts/install_hooks.sh`
5. Run tests: `pixi run pytest tests/ -v`
6. Check [CONTRIBUTING.md](CONTRIBUTING.md) for detailed workflow

**Areas for contribution:**

- Additional statistical methods and metrics
- New visualization types and formats
- Performance optimizations
- Documentation improvements
- Bug fixes and feature requests

Visit our [GitHub Repository](https://github.com/HomericIntelligence/Scylla) to get started.

---

## License

[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

## Citation

```bibtex
@software{scylla2026,
  title = {Scylla: A Testing and Optimization Framework for Agentic Workflows},
  author = {Micah Villmow},
  year = {2026},
  url = {https://github.com/HomericIntelligence/Scylla}
}
```
