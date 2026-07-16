# Rubric Schema Specification

> Version 1.1 | Last Updated: 2026-01-02

This document defines the YAML schema for `rubric.yaml` files used in Scylla's
LLM-as-Judge evaluation system. These files specify the requirements and scoring
methodology for grading AI agent outputs.

## Table of Contents

- [Overview](#overview)
- [File Location](#file-location)
- [Schema Definition](#schema-definition)
- [Field Reference](#field-reference)
- [Scoring Methodology](#scoring-methodology)
- [Validation Rules](#validation-rules)
- [Complete Example](#complete-example)
- [Best Practices](#best-practices)
- [Related Documents](#related-documents)

## Overview

### Purpose

A `rubric.yaml` file defines the scoring framework for evaluating AI agent outputs.
Each rubric specifies:

- **Requirements**: Individual evaluation criteria with weights
- **Grading**: Pass threshold and optional letter grade scale

### Integration with LLM-as-Judge

The rubric is used by the LLM-as-Judge evaluation protocol:

1. Judge receives the agent's output and the rubric
2. Each requirement is evaluated independently
3. Scores are aggregated using weighted averaging
4. Final score determines pass/fail and letter grade

### Design Principles

1. **Weighted Scoring**: Requirements can have different importance levels
2. **Flexible Evaluation**: Support for binary (yes/no) and scaled (0-1) scoring
3. **Transparent Grading**: Clear thresholds for pass/fail and grades
4. **Reproducible**: Same rubric produces consistent evaluations

## File Location

Rubric files are stored in the test case's `expected/` directory:

```
tests/
  <test-id>/
    test.yaml          # References this rubric
    prompt.md
    expected/
      criteria.md      # Human-readable version
      rubric.yaml      # Machine-readable scoring (this schema)
```

### Relationship to criteria.md

The `criteria.md` file provides human-readable success criteria, while
`rubric.yaml` provides the structured scoring framework. These files
should be kept in sync:

- Each major criterion in `criteria.md` should map to a requirement in `rubric.yaml`
- The rubric provides the scoring weights and evaluation types
- The criteria provides detailed explanations and examples

## Schema Definition

### Top-Level Structure

```yaml
# Required fields
requirements: array    # List of requirement objects
grading: object        # Grading configuration

# Each requirement
requirements:
  - id: string         # Unique requirement ID
    description: string # What this measures
    weight: number     # Scoring weight (0.0-10.0)
    evaluation: string # "binary" or "scaled"

# Grading configuration
grading:
  pass_threshold: number  # Pass threshold (0.0-1.0)
  grade_scale: object     # Optional letter grades
```

## Field Reference

### Root Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `requirements` | array | Yes | List of requirement objects |
| `grading` | object | Yes | Grading configuration |

### `requirements` Array

**Type**: `array` of `object`
**Required**: Yes
**Min Items**: 1

List of evaluation requirements. Order does not affect scoring.

### Requirement Object Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | - | Unique requirement identifier |
| `description` | string | Yes | - | What this requirement measures |
| `weight` | number | Yes | - | Scoring weight |
| `evaluation` | string | Yes | - | Evaluation type |

#### `requirements[].id`

**Type**: `string`
**Required**: Yes
**Pattern**: `^R[0-9]{3}$`

Unique identifier for the requirement. Must be:

- Prefixed with uppercase `R`
- Followed by exactly 3 digits (zero-padded)

**Examples**:

```yaml
requirements:
  - id: "R001"   # Valid
  - id: "R042"   # Valid
  - id: "R1"     # Invalid (not 3 digits)
  - id: "REQ01"  # Invalid (wrong prefix)
```

#### `requirements[].description`

**Type**: `string`
**Required**: Yes
**Min Length**: 10
**Max Length**: 200

Clear description of what this requirement evaluates. Should be:

- Specific and measurable
- Written as a statement (not a question)
- Evaluable by an LLM judge

**Examples**:

```yaml
requirements:
  - id: "R001"
    description: "Makefile exists and is syntactically valid"

  - id: "R002"
    description: "All justfile recipes have Makefile equivalents"
```

#### `requirements[].weight`

**Type**: `number`
**Required**: Yes
**Minimum**: `0.0`
**Maximum**: `10.0`

Relative importance of this requirement. Higher weights contribute more
to the final score.

**Recommended Weight Guidelines**:

| Weight | Importance | Example |
|--------|------------|---------|
| 0.5 | Minor | Code style, comments |
| 1.0 | Standard | Individual feature |
| 1.5 | Important | Core functionality |
| 2.0 | Critical | Main deliverable |
| 3.0+ | Essential | Must-pass requirement |

**Example**:

```yaml
requirements:
  - id: "R001"
    description: "Main file exists"
    weight: 2.0    # Critical requirement

  - id: "R007"
    description: "Code is well-commented"
    weight: 0.5    # Nice-to-have
```

#### `requirements[].evaluation`

**Type**: `string`
**Required**: Yes
**Enum**: `["binary", "scaled"]`

Evaluation type determines how the requirement is scored:

- **`binary`**: Pass (1.0) or fail (0.0)
- **`scaled`**: Continuous score from 0.0 to 1.0

**When to use each type**:

| Type | Use When | Examples |
|------|----------|----------|
| `binary` | Requirement is absolute | File exists, syntax valid |
| `scaled` | Partial credit makes sense | Coverage percentage, code quality |

**Example**:

```yaml
requirements:
  # Binary: Either the file exists or it doesn't
  - id: "R001"
    description: "Makefile exists and is syntactically valid"
    weight: 2.0
    evaluation: "binary"

  # Scaled: Partial credit for covering some recipes
  - id: "R002"
    description: "All justfile recipes have Makefile equivalents"
    weight: 2.0
    evaluation: "scaled"
```

### `grading` Object

**Type**: `object`
**Required**: Yes

Grading configuration with pass threshold and optional grade scale.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `pass_threshold` | number | Yes | - | Minimum score to pass |
| `grade_scale` | object | No | - | Letter grade thresholds |

#### `grading.pass_threshold`

**Type**: `number`
**Required**: Yes
**Minimum**: `0.0`
**Maximum**: `1.0`

Minimum weighted score (as a decimal) required to pass the test.

**Common Thresholds**:

| Threshold | Meaning |
|-----------|---------|
| 0.60 | Lenient (60% required) |
| 0.70 | Standard (70% required) |
| 0.80 | Strict (80% required) |
| 0.90 | Very strict (90% required) |

**Example**:

```yaml
grading:
  pass_threshold: 0.70  # 70% weighted score required to pass
```

#### `grading.grade_scale` (Optional)

**Type**: `object`
**Required**: No

Letter grade thresholds. If omitted, only pass/fail is reported.

> **Centralized Definition**: See [grading-scale.md](/docs/design/grading-scale.md) for the
> standard industry-aligned grade scale used across all Scylla rubrics.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `S` | number | No | Amazing - exceptional, above and beyond (1.00) |
| `A` | number | No | Excellent - production ready (0.80) |
| `B` | number | No | Good - minor improvements possible (0.60) |
| `C` | number | No | Acceptable - functional with issues (0.40) |
| `D` | number | No | Marginal - significant issues (0.20) |
| `F` | number | No | Failing - does not meet requirements (0.00) |

**Rules**:

- Thresholds must be in descending order (S > A > B > C > D > F)
- F is always `0.0` (any score below D)
- Score >= threshold receives that grade

**Industry-Aligned Scale** (Recommended):

```yaml
grading:
  pass_threshold: 0.60
  grade_scale:
    S: 1.00    # Amazing - above and beyond
    A: 0.80    # Excellent - production ready
    B: 0.60    # Good - minor improvements possible
    C: 0.40    # Acceptable - functional with issues
    D: 0.20    # Marginal - significant issues
    F: 0.0     # Failing - does not meet requirements
```

**Why Industry-Aligned vs Academic Scale**:

The traditional academic scale (A=95%, B=85%, etc.) was replaced with an industry-aligned
scale for several reasons:

1. **Production semantics**: Grades map to deployment decisions (ship/fix/rework)
2. **No grade inflation**: Academic 95% threshold is unrealistic for complex tasks
3. **Meaningful differentiation**: Each grade represents a distinct action item
4. **Industry alignment**: Matches SonarQube, LLM evaluation, and QA scorecard patterns

## Scoring Methodology

### Score Calculation Formula

The final score is calculated using weighted averaging:

```
final_score = sum(requirement_score[i] * weight[i]) / sum(weight[i])
```

Where:

- `requirement_score[i]` is 0.0-1.0 for each requirement
- `weight[i]` is the weight for requirement i

### Binary vs Scaled Scoring

**Binary Evaluation**:

```
score = 1.0 if requirement_met else 0.0
```

**Scaled Evaluation**:

```
score = degree_of_completion  # 0.0 to 1.0
```

### Example Calculation

Given this rubric:

```yaml
requirements:
  - id: "R001"
    weight: 2.0
    evaluation: "binary"
  - id: "R002"
    weight: 2.0
    evaluation: "scaled"
  - id: "R003"
    weight: 1.0
    evaluation: "binary"
```

And these scores:

- R001: 1.0 (passed)
- R002: 0.75 (75% complete)
- R003: 0.0 (failed)

Calculation:

```
final_score = (1.0 * 2.0 + 0.75 * 2.0 + 0.0 * 1.0) / (2.0 + 2.0 + 1.0)
            = (2.0 + 1.5 + 0.0) / 5.0
            = 3.5 / 5.0
            = 0.70
```

With `pass_threshold: 0.70`, this would barely pass.

### Grade Assignment

Grades are assigned based on the final score:

```
if final_score >= A_threshold: grade = "A"
elif final_score >= B_threshold: grade = "B"
elif final_score >= C_threshold: grade = "C"
elif final_score >= D_threshold: grade = "D"
else: grade = "F"
```

### LLM-as-Judge Protocol

The rubric integrates with the 3-run consensus evaluation protocol:

1. **Three Independent Runs**: The judge evaluates each requirement 3 times
2. **Consensus Scoring**: Final requirement score is the median of 3 runs
3. **Confidence Weighting**: Consistent scores have higher confidence
4. **Final Aggregation**: Weighted average produces final score

## Validation Rules

### Required Field Validation

1. `requirements` array must have at least one item
2. `grading.pass_threshold` must be present
3. All requirement fields (`id`, `description`, `weight`, `evaluation`) are required

### Type Validation

1. `weight` must be a number, not a string
2. `evaluation` must be exactly `"binary"` or `"scaled"`
3. `pass_threshold` must be a number between 0.0 and 1.0

### Format Validation

1. **Requirement ID**: Must match pattern `^R[0-9]{3}$`
2. **Evaluation Type**: Must be `"binary"` or `"scaled"` (case-sensitive)

### Uniqueness Validation

1. All requirement IDs must be unique within the file

### Ordering Validation (grade_scale)

1. If provided, grade thresholds must be in descending order
2. A >= B >= C >= D >= F

### Logical Validation

1. Weights must be positive (> 0.0)
2. `pass_threshold` should typically be >= lowest non-F grade threshold
3. Sum of weights should be documented (no specific requirement)

## Complete Example

```yaml
# Rubric for: Convert Justfile to Makefile
# Test Case: 001-justfile-to-makefile

# Requirements list (required)
# Each requirement defines one evaluation criterion
requirements:
  # Critical: File must exist and be valid
  - id: "R001"
    description: "Makefile exists and is syntactically valid"
    weight: 2.0          # High weight - critical requirement
    evaluation: "binary"  # Either valid or not

  # Core: Recipe coverage
  - id: "R002"
    description: "All justfile recipes have Makefile equivalents"
    weight: 2.0
    evaluation: "scaled"  # Partial credit for partial coverage

  # Feature: Help command
  - id: "R003"
    description: "help command works and lists targets"
    weight: 1.0
    evaluation: "binary"

  # Functionality: Build commands
  - id: "R004"
    description: "build commands produce equivalent output"
    weight: 1.5
    evaluation: "scaled"  # Partial credit if some builds work

  # Functionality: Clean command
  - id: "R005"
    description: "clean command removes correct artifacts"
    weight: 1.0
    evaluation: "binary"

  # Technical: Variable handling
  - id: "R006"
    description: "Variable substitution works correctly"
    weight: 1.0
    evaluation: "binary"

  # Quality: Code quality (nice-to-have)
  - id: "R007"
    description: "Code quality: readable, well-commented"
    weight: 0.5
    evaluation: "scaled"

# Grading configuration (required)
grading:
  # Minimum weighted score to pass (required)
  # 0.60 means 60% weighted score needed (Good grade)
  pass_threshold: 0.60

  # Industry-aligned grade scale
  # See docs/design/grading-scale.md for full specification
  grade_scale:
    S: 1.00    # Amazing - above and beyond
    A: 0.80    # Excellent - production ready
    B: 0.60    # Good - minor improvements possible
    C: 0.40    # Acceptable - functional with issues
    D: 0.20    # Marginal - significant issues
    F: 0.0     # Failing - does not meet requirements

# Total weights: 2.0 + 2.0 + 1.0 + 1.5 + 1.0 + 1.0 + 0.5 = 9.0
# Maximum possible score: 9.0 / 9.0 = 1.0 (100%)
```

## Best Practices

### Designing Requirements

1. **Be Specific**: Each requirement should measure one clear thing
2. **Be Measurable**: Requirements must be evaluable by an LLM
3. **Avoid Overlap**: Requirements should not duplicate evaluation
4. **Cover Edge Cases**: Include requirements for error handling

### Assigning Weights

1. **Prioritize Core Functionality**: Main deliverables get highest weights
2. **Balance Quality vs Features**: Don't over-weight code style
3. **Consider Dependencies**: If R001 fails, can R002-R007 be evaluated?
4. **Document Total Weight**: Comment the sum for transparency

### Choosing Evaluation Types

1. **Use Binary for Absolutes**: File exists, syntax valid, test passes
2. **Use Scaled for Gradients**: Coverage percentage, code quality, partial implementations
3. **Default to Binary**: When in doubt, binary is simpler to evaluate

### Setting Pass Thresholds

1. **Consider Task Difficulty**: Harder tasks may warrant lower thresholds
2. **Consider Critical Requirements**: High-weight requirements affect threshold
3. **Test the Threshold**: Verify it produces sensible pass/fail results
4. **Document Rationale**: Explain why you chose the threshold

### Maintaining Rubrics

1. **Version Control**: Track changes to rubrics over time
2. **Sync with Criteria**: Keep `rubric.yaml` aligned with `criteria.md`
3. **Review Periodically**: Adjust weights based on evaluation results
4. **Document Changes**: Note why weights or thresholds were modified

## Related Documents

- [Grading Scale Definition](/docs/design/grading-scale.md) - **Single source of truth** for grade thresholds
- [Test Schema Specification](test-schema.md) - Test case YAML schema
- [Evaluation Guidelines](/.claude/shared/evaluation-guidelines.md) - Evaluation methodology
- [Metrics Definitions](/.claude/shared/metrics-definitions.md) - Quality metrics including Pass-Rate
