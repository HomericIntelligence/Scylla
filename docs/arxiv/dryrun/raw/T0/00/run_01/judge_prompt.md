## Rubric (Evaluation Criteria)

```yaml
# Test fixture: Rubric for Hello World Task (test-001)
# Hybrid evaluation: Objective checklists + Subjective engineering judgment

categories:
  functional:
    weight: 0.35
    scoring_type: "checklist"
    items:
      - id: F1
        check: "File hello.py exists in workspace root"
        points: 1.0

      - id: F2
        check: "Running `python hello.py` produces output containing 'Hello, World!'"
        points: 1.0

      - id: F3
        check: "Script exits with code 0 (successful execution)"
        points: 1.0

      - id: F4
        check: "Output is EXACTLY 'Hello, World!' with no extra text or trailing output"
        points: 0.5

  code_quality:
    weight: 0.20
    scoring_type: "checklist"
    items:
      - id: Q1
        check: "Python syntax is valid (python -m compileall passes)"
        points: 1.0

      - id: Q2
        check: "Code is idiomatic Python (not overly complex)"
        points: 1.0

      - id: Q3
        check: "No unused imports or variables"
        points: 1.0

      - id: Q4
        check: "Code follows PEP8 formatting standards (ruff check passes)"
        points: 1.0
        na_condition: "ruff not available in workspace"

  proportionality:
    weight: 0.15
    scoring_type: "checklist"
    items:
      - id: P1
        check: "Total files created ≤ 3 (hello.py plus optionally README, .gitignore)"
        points: 1.0

      - id: P2
        check: "Total lines of code in hello.py ≤ 3"
        points: 1.0

      - id: P3
        check: "No unnecessary test files created for this trivial task"
        points: 1.0
        na_condition: "Task explicitly required tests"

      - id: P4
        check: "No build artifacts remaining (__pycache__, *.pyc cleaned up or ignored)"
        points: 0.5

  build_pipeline:
    weight: 0.10
    scoring_type: "checklist"
    items:
      - id: B1
        check: "Python build/syntax check passes without errors"
        points: 1.0

      - id: B2
        check: "Python format check passes (if ruff available)"
        points: 1.0
        na_condition: "ruff not available in workspace"

      - id: B3
        check: "Tests pass (if task requires tests)"
        points: 1.0
        na_condition: "Task does not require tests"

      - id: B4
        check: "Pre-commit hooks pass"
        points: 1.0
        na_condition: "Workspace lacks .pre-commit-config.yaml"

  overall_quality:
    weight: 0.20
    scoring_type: "subjective"
    items:
      - id: OQ1
        check: "Overall engineering judgment: Is the solution appropriately scoped for a Hello World task? Consider: simplicity vs over-engineering, maintainability, clarity, and whether a senior engineer would approve this PR."
        points: 2.0

grading:
  pass_threshold: 0.60
  # Industry-aligned grade scale - see docs/design/grading-scale.md
  grade_scale:
    S: 1.00    # Amazing - above and beyond
    A: 0.80    # Excellent - production ready
    B: 0.60    # Good - minor improvements possible
    C: 0.40    # Acceptable - functional with issues
    D: 0.20    # Marginal - significant issues
    F: 0.0     # Failing - does not meet requirements

```

## Task Given to Agent

# Task: Create a Hello World Script

Create a simple Python script called `hello.py` that prints "Hello, World!" to stdout.

## Requirements

1. Create a file named `hello.py` in the current working directory (use relative path `./hello.py`, NOT an absolute path)
2. The script should print exactly: `Hello, World!`
3. The script should exit with code 0
4. Specify the directory where the script was created using absolute path to the file

## Expected Output

When running `python hello.py`, the output should be:

```
Hello, World!
```

## Success Criteria

- File `hello.py` exists in the current working directory (created with relative path)
- Running `python hello.py` from the current directory prints "Hello, World!"
- Exit code is 0

**IMPORTANT**: Use relative paths only. Do NOT use absolute paths like `/home/...`.

## Agent's Output

{"type":"result","subtype":"success","is_error":false,"duration_ms":29039,"duration_api_ms":29535,"num_turns":6,"result":"Task completed successfully! \n\nI've created the `hello.py` script with the following details:\n\n**File created**: `hello.py` (using relative path `./hello.py`)\n\n**Absolute path**: `/home/mvillmow/fullruns/test001-dryrun/2026-01-20T06-13-07-test-001/T0/00/run_01/workspace/hello.py`\n\n**Output**: The script prints exactly `Hello, World!` and exits with code 0.\n\nAll requirements have been met:\n- File created using relative path\n- Prints \"Hello, World!\" to stdout\n- Exits with code 0","session_id":"dc93aac8-fe7f-4d4a-83ef-2bd2c070444e","total_cost_usd":0.1351093,"usage":{"input_tokens":29,"cache_creation_input_tokens":23106,"cache_read_input_tokens":112686,"output_tokens":656,"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":23106}},"modelUsage":{"claude-haiku-4-5-20251001":{"inputTokens":3774,"outputTokens":191,"cacheReadInputTokens":0,"cacheCreationInputTokens":0,"webSearchRequests":0,"costUSD":0.004729,"contextWindow":200000,"maxOutputTokens":64000},"claude-sonnet-4-5-20250929":{"inputTokens":29,"outputTokens":656,"cacheReadInputTokens":112686,"cacheCreationInputTokens":23106,"webSearchRequests":0,"costUSD":0.13038029999999998,"contextWindow":200000,"maxOutputTokens":64000}},"permission_denials":[],"uuid":"e6cfcb90-ee51-4c2c-b73e-3c0c3e368196"}

## Workspace State After Agent Execution

Files modified/created by agent:

- `hello.py` (created)

## Build/Lint/Test Pipeline Results

**Overall Status**: ALL PASSED ✓

### Python Build (PASSED)

```
Python syntax check passed

## Script Execution Results


### Running: python hello.py
Exit code: 0
Output:
Hello, World!

```

### Python Format Check (PASSED)

```
All checks passed!


```

### Python Test (PASSED)

```
============================= test session starts ==============================
platform linux -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /home/mvillmow/Scylla/.pixi/envs/default/bin/python3.14
cachedir: .pytest_cache
rootdir: /home/mvillmow/fullruns/test001-dryrun/2026-01-20T06-13-07-test-001/T0/00/run_01/workspace
plugins: cov-7.0.0
collecting ... collected 0 items

============================ no tests ran in 0.08s =============================


```

### Pre-commit Hooks (PASSED)

```
An error has occurred: InvalidConfigError:
=====> .pre-commit-config.yaml is not a file
Check the log at /home/mvillmow/.cache/pre-commit/pre-commit.log


```

---

Evaluate the agent's work using the rubric and criteria in your system prompt.
