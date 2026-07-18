# Skill: backward-compat-removal

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-02-20 |
| Issue | #784 |
| PR | #832 |
| Objective | Remove deprecated `BaseExecutionInfo` dataclass as part of the target major version cleanup |
| Outcome | Success — 209 lines deleted, 2266 tests pass, all pre-commit hooks green |
| Category | testing |

## When to Use

Trigger this skill when:

- A class or symbol has a `DeprecationWarning` added via `warnings.warn()`
- The deprecation milestone (e.g. the target major version) has arrived
- Issue says "delete", "remove", or "cleanup" for a previously deprecated symbol
- You see `TestXxxBackwardCompatibility` or `TestXxx` test classes only testing deprecated code

## Verified Workflow

### Phase 1 — Identify all references

```bash
grep -rn "BaseExecutionInfo" scylla/ tests/
```

Check for:

1. The class definition in `scylla/core/results.py`
2. The `__init__.py` export
3. Any `import` in test files
4. Docstring mentions in other modules (not imports, just text)

### Phase 2 — Remove the class

In the source file (`scylla/core/results.py`):

- Delete the `@dataclass` decorator and entire class body
- Delete `import warnings` **only if** it becomes unused — check the whole file first
- Keep `from dataclasses import dataclass` **if** any other dataclass exists in the file
- Remove any module-level docstring line that references the deprecated class

### Phase 3 — Remove the export

In `scylla/core/__init__.py`:

- Remove from the `from scylla.core.results import (...)` block
- Remove from `__all__`

### Phase 4 — Delete test classes entirely

In `tests/unit/core/test_results.py`:

- Delete `TestBaseExecutionInfo` class entirely (all methods)
- Delete `TestBaseExecutionInfoBackwardCompatibility` class entirely
- Update the import line to remove the deleted symbol
- Remove any methods in other test classes (`TestComposedTypes`, etc.) that reference the deleted symbol
- **Never leave test classes as `@pytest.mark.skip`** — delete them outright

### Phase 5 — Update docstring cross-references

Search for text-only mentions in docstrings:

```bash
grep -rn "BaseExecutionInfo" scylla/
```

Remove lines like `- BaseExecutionInfo (core/results.py) - Legacy dataclass (deprecated)` from docstring "see also" lists in other modules.

### Phase 6 — Verify

```bash
uv run python -m pytest tests/ -v
grep -rn "BaseExecutionInfo" scylla/ tests/   # should return empty
pre-commit run --all-files
```

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Delete test classes, not skip | Skipped tests are dead weight; they will never be unskipped |
| Keep `@dataclass` import if other dataclasses exist | `BaseRunMetrics` is also a `@dataclass` in `results.py` |
| Scope: deletion only | No migration, no refactoring of other callers — those should already use the replacement |
| Remove docstring mentions | Stale "see also" references mislead future readers |

## Failed Attempts

None — the systematic 6-phase approach from the issue plan worked first time.

The only non-obvious step was checking whether `import warnings` could be removed (yes, it was only used by `BaseExecutionInfo.__post_init__`), and whether `from dataclasses import dataclass` could be removed (no — `BaseRunMetrics` is also a dataclass).

## Results & Parameters

```
Files changed: 5
Lines deleted: 209
Lines added: 1
Tests: 2266 passed, 0 failed
Coverage: 73.57% (above 73% threshold)
Pre-commit hooks: all passed
Zero remaining references after cleanup
```
