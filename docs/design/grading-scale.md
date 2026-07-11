# Grading Scale Definition

> Version 1.0 | Last Updated: 2026-01-02

This document defines the **single source of truth** for grading scales used across
all Scylla rubrics. All `rubric.yaml` files reference this definition.

## Industry-Aligned Grade Scale

Scylla uses an industry-aligned grading scale focused on **production readiness**
rather than academic performance. This approach was chosen based on industry standards
from SonarQube, LLM evaluation frameworks, and QA scorecard best practices.

### Grade Thresholds

| Grade | Threshold | Label | Description |
|-------|-----------|-------|-------------|
| S | 1.00 | Amazing | Exceptional work that goes above and beyond requirements |
| A | 0.80 | Excellent | Production ready, no significant issues |
| B | 0.60 | Good | Minor improvements possible, meets requirements |
| C | 0.40 | Acceptable | Functional with some issues, partial credit |
| D | 0.20 | Marginal | Significant issues, barely functional |
| F | 0.00 | Failing | Does not meet requirements |

### YAML Configuration

Rubric files only need to configure the pass threshold. The grade scale itself is
defined in code (`scylla.metrics.grading.assign_letter_grade()`) and cannot be customized:

```yaml
grading:
  pass_threshold: 0.60  # Minimum score to pass (Good)
  # Note: Grade scale (S/A/B/C/D/F thresholds) is centralized in scylla.metrics.grading
  #       and uses the industry-aligned scale defined in this document
```

## Grade Assignment Logic

Grades are assigned using **greater-than-or-equal** comparison in descending order,
with the exception that **S grade requires exactly 1.00** (perfect score):

```python
def assign_letter_grade(score: float) -> str:
    """Assign letter grade based on score.

    Note: S grade requires exactly 1.00 (perfect score).
    All other grades use >= thresholds.
    """
    assert 0.0 <= score <= 1.0, f"Score {score} is outside valid range [0.0, 1.0]"

    if score == 1.00: return "S"   # Amazing (perfect score only)
    if score >= 0.80: return "A"   # Excellent
    if score >= 0.60: return "B"   # Good
    if score >= 0.40: return "C"   # Acceptable
    if score >= 0.20: return "D"   # Marginal
    return "F"                      # Failing
```

## Pass/Fail Determination

A score is considered **passing** if it meets the `pass_threshold`:

- **Default pass threshold**: 0.60 (Good)
- Individual tests may override this in their `rubric.yaml`

### Pass Threshold Guidelines

| Threshold | Use Case |
|-----------|----------|
| 0.80 | High-stakes evaluations requiring production quality |
| 0.60 | Standard evaluations (default) |
| 0.40 | Lenient evaluations accepting partial implementations |

### Score Interpretation

| Score Range | Interpretation | Action |
|-------------|----------------|--------|
| 1.00 | Perfect + bonus criteria | Ship immediately |
| 0.80-0.99 | Production ready | Ship with confidence |
| 0.60-0.79 | Meets requirements | Ship after minor fixes |
| 0.40-0.59 | Partial success | Rework required |
| 0.20-0.39 | Major issues | Significant rework |
| 0.00-0.19 | Failed | Start over |

## Usage in Rubric Files

All rubrics use the centralized grade assignment function. Only the pass threshold
is configurable per rubric:

```yaml
# rubric.yaml
requirements:
  # ... requirements ...

grading:
  pass_threshold: 0.60  # Default: 0.60 (Good grade)
  # Grade assignment uses scylla.metrics.grading.assign_letter_grade()
  # See docs/design/grading-scale.md for complete specification
```

## Related Documents

- [Rubric Schema](../../docs/design/rubric-schema.md) - Full rubric YAML specification
- [Metrics Definitions](metrics-definitions.md) - Quality and economic metrics
- [Evaluation Guidelines](evaluation-guidelines.md) - LLM-as-Judge methodology
