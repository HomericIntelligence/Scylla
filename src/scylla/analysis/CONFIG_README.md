# Analysis Configuration

## Overview

The analysis pipeline uses a centralized configuration system to ensure reproducibility and consistency across all statistical analyses, figures, and tables.

**Configuration File**: `src/scylla/analysis/config.yaml`
**Python Module**: `src/scylla/analysis/config.py`

## Design Principles

1. **Single Source of Truth**: All tunable parameters are defined in `config.yaml`
2. **Reproducibility**: Configuration versioning and dependency tracking
3. **Type Safety**: Python module provides typed access to parameters
4. **Backwards Compatibility**: Module-level constants for legacy code
5. **Testability**: Configuration values can be verified in tests

## Usage

### Import Configuration

```python
# Recommended: Import specific constants
from scylla.analysis.config import ALPHA, BOOTSTRAP_RESAMPLES

# Alternative: Import config object for dynamic access
from scylla.analysis.config import config

alpha = config.alpha
n_resamples = config.bootstrap_resamples
```

### Access Configuration Values

```python
from scylla.analysis.config import config

# Statistical parameters
alpha = config.alpha  # 0.05
n_resamples = config.bootstrap_resamples  # 10000
random_state = config.bootstrap_random_state  # 42

# Figure parameters
dpi_scale = config.png_dpi_scale  # 3.0 (for 300 DPI)
width = config.figure_width  # 400
height = config.figure_height  # 300

# Minimum sample sizes
min_n = config.min_sample_bootstrap  # 2
```

### Nested Access

```python
# Get nested values with fallback
value = config.get("figures", "dpi", "png", default=300)
```

## Configuration Structure

### Statistical Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `statistical.alpha` | 0.05 | Significance threshold for hypothesis tests |
| `statistical.bootstrap.n_resamples` | 10000 | Bootstrap iterations |
| `statistical.bootstrap.random_state` | 42 | Random seed for reproducibility |
| `statistical.bootstrap.confidence_level` | 0.95 | Confidence level for CIs |
| `statistical.bootstrap.method` | "BCa" | Bias-Corrected and accelerated |

### Minimum Sample Sizes

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `min_samples.bootstrap_ci` | 2 | Minimum for bootstrap CI |
| `min_samples.mann_whitney` | 2 | Minimum for Mann-Whitney U |
| `min_samples.normality_test` | 3 | Minimum for Shapiro-Wilk |
| `min_samples.correlation` | 3 | Minimum for correlations |

### Figure Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `figures.dpi.png` | 300 | Publication-quality DPI |
| `figures.default_width` | 400 | Default width in pixels |
| `figures.default_height` | 300 | Default height in pixels |
| `figures.fonts.family` | "serif" | Font family |
| `figures.fonts.title_size` | 14 | Title font size |

### Reproducibility Metadata

| Parameter | Value | Description |
|-----------|-------|-------------|
| `reproducibility.pipeline_version` | "1.0.0" | Analysis pipeline version |
| `reproducibility.config_version` | "1.0.0" | Configuration schema version |

## Versioning

The configuration file includes version metadata to track changes:

```yaml
reproducibility:
  pipeline_version: "1.0.0"
  config_version: "1.0.0"
```

When making breaking changes to the configuration schema:

1. Increment `config_version` (major.minor.patch)
2. Update `pipeline_version` if analysis logic changes
3. Document changes in this README

## Testing

Configuration values are tested in `tests/unit/analysis/test_config.py`:

```bash
uv run pytest tests/unit/analysis/test_config.py -v
```

## Migration Guide

### From Hardcoded Constants

**Before:**

```python
ALPHA = 0.05  # Hardcoded in tables.py
n_resamples = 10000  # Hardcoded in stats.py
```

**After:**

```python
from scylla.analysis.config import ALPHA, BOOTSTRAP_RESAMPLES

# Use ALPHA and BOOTSTRAP_RESAMPLES directly
```

### Updating Configuration

1. Edit `src/scylla/analysis/config.yaml`
2. Run tests to verify: `uv run pytest tests/unit/analysis/`
3. Commit both `config.yaml` and `config.py` together

## Benefits

1. **Reproducibility**: All parameters in one place with version tracking
2. **Consistency**: Same values used across all analysis components
3. **Transparency**: Parameters documented in YAML with comments
4. **Maintainability**: Easy to update parameters without code changes
5. **Auditability**: Configuration changes tracked in version control

## See Also

- Analysis pipeline documentation: `docs/analysis_pipeline.md`
- Statistical methods: `src/scylla/analysis/stats.py`
- Figure generation: `src/scylla/analysis/figures/`
- Table generation: `src/scylla/analysis/tables.py`
