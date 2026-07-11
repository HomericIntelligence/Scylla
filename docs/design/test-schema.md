# Test Schema Specification

> Version 1.0 | Last Updated: 2025-12-30

This document defines the YAML schema for `test.yaml` files used in Scylla's
evaluation framework. These files configure individual test cases that benchmark AI
agent performance across different architectural tiers.

## Table of Contents

- [Overview](#overview)
- [File Location](#file-location)
- [Schema Definition](#schema-definition)
- [Field Reference](#field-reference)
- [Validation Rules](#validation-rules)
- [Complete Example](#complete-example)
- [Migration Guide](#migration-guide)
- [Related Documents](#related-documents)

## Overview

### Purpose

A `test.yaml` file defines a single test case for evaluating AI agent capabilities.
Each test case specifies:

- **Identity**: Unique identifier and human-readable name
- **Source**: Git repository and commit to test against
- **Task**: The prompt and timeout configuration
- **Validation**: Criteria and rubric for scoring

### Design Principles

1. **Self-Contained**: Each test case directory contains all necessary files
2. **Reproducible**: Git hash pinning ensures consistent evaluation
3. **Extensible**: Optional fields allow customization without breaking changes
4. **Validated**: Schema enables automated validation

## File Location

Test cases follow a standardized directory structure:

```
tests/
  <test-id>/
    test.yaml          # Test configuration (this schema)
    prompt.md          # Task prompt for the agent
    expected/
      criteria.md      # Human-readable success criteria
      rubric.yaml      # Scoring rubric (see rubric-schema.md)
```

### Naming Conventions

- **Directory name**: Must match the `id` field in `test.yaml`
- **Format**: `<NNN>-<kebab-case-description>`
- **Example**: `001-justfile-to-makefile`

## Schema Definition

### Top-Level Structure

```yaml
# Required fields
id: string           # Unique test identifier
name: string         # Human-readable name
source: object       # Git repository configuration
task: object         # Task execution settings
validation: object   # Validation file references

# Optional fields
description: string  # Detailed description (multiline)
models: array        # Model overrides per tier
tags: array          # Classification tags
```

## Field Reference

### Root Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | - | Unique test identifier |
| `name` | string | Yes | - | Human-readable test name |
| `description` | string | No | `""` | Detailed description |
| `source` | object | Yes | - | Git repository configuration |
| `task` | object | Yes | - | Task execution settings |
| `validation` | object | Yes | - | Validation file references |
| `models` | array | No | `[]` | Model overrides per tier |
| `tags` | array | No | `[]` | Classification tags |

### `id` Field

**Type**: `string`
**Required**: Yes
**Pattern**: `^[0-9]{3}-[a-z0-9]+(-[a-z0-9]+)*$`

Unique identifier for the test case. Must be:

- Prefixed with a 3-digit number (zero-padded)
- Followed by a hyphen
- Followed by lowercase alphanumeric words separated by hyphens

**Examples**:

```yaml
id: "001-justfile-to-makefile"    # Valid
id: "042-api-integration-test"    # Valid
id: "justfile-to-makefile"        # Invalid (missing number prefix)
id: "001_justfile_to_makefile"    # Invalid (underscores not allowed)
```

### `name` Field

**Type**: `string`
**Required**: Yes
**Min Length**: 3
**Max Length**: 100

Human-readable name displayed in reports and dashboards.

**Examples**:

```yaml
name: "Convert Justfile to Makefile"
name: "API Integration Test Suite"
```

### `description` Field

**Type**: `string`
**Required**: No
**Default**: Empty string

Detailed description of the test case. Supports multiline YAML syntax.

**Example**:

```yaml
description: |
  Convert ProjectOdyssey's justfile to an equivalent Makefile.
  The Makefile must support all existing recipes and produce
  equivalent outputs when run.
```

### `source` Object

Git repository configuration for the test case.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source.repo` | string | Yes | - | Git repository URL |
| `source.hash` | string | Yes | - | Git commit hash (40 characters) |
| `source.branch` | string | No | `"main"` | Branch name |

#### `source.repo`

**Type**: `string`
**Required**: Yes
**Pattern**: `^https?://[^\s]+$`

Git repository URL. Supports HTTPS URLs only.

**Examples**:

```yaml
source:
  repo: "https://github.com/mvillmow/ProjectOdyssey"
```

#### `source.hash`

**Type**: `string`
**Required**: Yes
**Pattern**: `^[a-f0-9]{40}$`

Full 40-character Git commit SHA hash. Short hashes are not accepted
to ensure reproducibility.

**Examples**:

```yaml
source:
  hash: "ce739d4aa328f1c0815b33e2812c4b889868b740"  # Valid
  hash: "ce739d4"                                     # Invalid (too short)
```

#### `source.branch`

**Type**: `string`
**Required**: No
**Default**: `"main"`

Git branch name. Used for informational purposes when the hash is
on a feature branch.

**Example**:

```yaml
source:
  repo: "https://github.com/mvillmow/ProjectOdyssey"
  hash: "ce739d4aa328f1c0815b33e2812c4b889868b740"
  branch: "feature/new-api"
```

### `task` Object

Task execution configuration.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task.prompt_file` | string | Yes | - | Path to prompt file |
| `task.timeout_seconds` | integer | No | `3600` | Execution timeout |

#### `task.prompt_file`

**Type**: `string`
**Required**: Yes
**Pattern**: `^[^/].*\.md$`

Relative path to the prompt markdown file. Path is relative to the
`test.yaml` file location.

**Examples**:

```yaml
task:
  prompt_file: "prompt.md"           # Same directory
  prompt_file: "prompts/main.md"     # Subdirectory
```

#### `task.timeout_seconds`

**Type**: `integer`
**Required**: No
**Default**: `3600`
**Minimum**: `60`
**Maximum**: `86400`

Maximum time in seconds for the agent to complete the task.
Defaults to 1 hour (3600 seconds).

**Examples**:

```yaml
task:
  prompt_file: "prompt.md"
  timeout_seconds: 1800    # 30 minutes
```

### `validation` Object

References to validation files.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `validation.criteria_file` | string | Yes | - | Path to criteria markdown |
| `validation.rubric_file` | string | Yes | - | Path to rubric YAML |

#### `validation.criteria_file`

**Type**: `string`
**Required**: Yes
**Pattern**: `^[^/].*\.md$`

Relative path to the human-readable success criteria file.

**Example**:

```yaml
validation:
  criteria_file: "expected/criteria.md"
```

#### `validation.rubric_file`

**Type**: `string`
**Required**: Yes
**Pattern**: `^[^/].*\.ya?ml$`

Relative path to the scoring rubric YAML file.

**Example**:

```yaml
validation:
  rubric_file: "expected/rubric.yaml"
```

### `models` Array (Optional)

Override default model assignments for specific tiers.

**Type**: `array` of `object`
**Required**: No
**Default**: Empty array (use tier defaults)

Each entry specifies a tier and the model to use:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `models[].tier` | string | Yes | Tier identifier (T0-T6) |
| `models[].model` | string | Yes | Model identifier |

**Example**:

```yaml
models:
  - tier: "T0"
    model: "claude-3-opus"
  - tier: "T1"
    model: "claude-3-sonnet"
```

### `tags` Array (Optional)

Classification tags for filtering and organization.

**Type**: `array` of `string`
**Required**: No
**Default**: Empty array

**Example**:

```yaml
tags:
  - "build-system"
  - "migration"
  - "mojo"
```

## Validation Rules

### Required Field Validation

1. All required fields must be present
2. Required fields cannot be null or empty strings

### Type Validation

1. String fields must contain valid UTF-8 text
2. Integer fields must be whole numbers within specified ranges
3. Arrays must contain the correct element types

### Format Validation

1. **ID Format**: Must match pattern `^[0-9]{3}-[a-z0-9]+(-[a-z0-9]+)*$`
2. **Hash Format**: Must be exactly 40 hexadecimal characters (lowercase)
3. **URL Format**: Must be a valid HTTP/HTTPS URL
4. **File Paths**: Must be relative paths (no leading `/`)

### Reference Validation

1. `task.prompt_file` must reference an existing file
2. `validation.criteria_file` must reference an existing file
3. `validation.rubric_file` must reference an existing file

### Cross-Field Validation

1. Directory name must match the `id` field value
2. Timeout must be within valid range (60-86400 seconds)

## Complete Example

```yaml
# Test case identifier (required)
# Format: NNN-kebab-case-description
id: "001-justfile-to-makefile"

# Human-readable name (required)
name: "Convert Justfile to Makefile"

# Detailed description (optional)
# Use | for multiline strings
description: |
  Convert ProjectOdyssey's justfile to an equivalent Makefile.
  The Makefile must support all existing recipes and produce
  equivalent outputs when run.

# Git source configuration (required)
source:
  # Repository URL (required)
  repo: "https://github.com/mvillmow/ProjectOdyssey"
  # Full 40-character commit hash (required)
  hash: "ce739d4aa328f1c0815b33e2812c4b889868b740"
  # Branch name (optional, defaults to "main")
  # branch: "main"

# Task configuration (required)
task:
  # Path to prompt file, relative to test.yaml (required)
  prompt_file: "prompt.md"
  # Timeout in seconds (optional, defaults to 3600)
  timeout_seconds: 3600

# Validation configuration (required)
validation:
  # Path to criteria markdown (required)
  criteria_file: "expected/criteria.md"
  # Path to rubric YAML (required)
  rubric_file: "expected/rubric.yaml"

# Model overrides per tier (optional)
# Uncomment to override default model assignments
# models:
#   - tier: "T0"
#     model: "claude-3-opus"

# Classification tags (optional)
# Used for filtering and organization
# tags:
#   - "build-system"
#   - "migration"
```

## Migration Guide

### Adding a New Test Case

1. **Create directory structure**:

   ```bash
   mkdir -p tests/<NNN>-<description>/expected
   ```

2. **Create test.yaml** with required fields:

   ```yaml
   id: "<NNN>-<description>"
   name: "Your Test Name"
   source:
     repo: "https://github.com/owner/repo"
     hash: "<40-character-commit-hash>"
   task:
     prompt_file: "prompt.md"
   validation:
     criteria_file: "expected/criteria.md"
     rubric_file: "expected/rubric.yaml"
   ```

3. **Create prompt.md** with the task description

4. **Create expected/criteria.md** with success criteria

5. **Create expected/rubric.yaml** following [rubric-schema.md](rubric-schema.md)

6. **Validate** using the JSON Schema:

   ```bash
   # Using ajv-cli or similar
   ajv validate -s schemas/test.schema.json -d tests/<NNN>-*/test.yaml
   ```

### Field Requirements Checklist

- [ ] `id` matches directory name
- [ ] `id` follows `NNN-kebab-case` format
- [ ] `source.hash` is full 40-character SHA
- [ ] `task.prompt_file` file exists
- [ ] `validation.criteria_file` file exists
- [ ] `validation.rubric_file` file exists

### Best Practices

1. **Use descriptive IDs**: The ID should convey the test purpose
2. **Pin specific commits**: Always use exact commit hashes
3. **Document edge cases**: Include non-obvious requirements in the description
4. **Keep prompts focused**: One clear task per test case
5. **Match criteria to rubric**: Ensure criteria.md aligns with rubric.yaml requirements

## Related Documents

- [Rubric Schema Specification](rubric-schema.md) - Scoring rubric YAML schema
- [Evaluation Guidelines](/.claude/shared/evaluation-guidelines.md) - Evaluation methodology
- [Metrics Definitions](/.claude/shared/metrics-definitions.md) - Quality and economic metrics
