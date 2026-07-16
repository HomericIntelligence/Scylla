# ADR: Circuit-Breaker Consolidation on `hephaestus.resilience`

**Date**: 2026-05-06
**Status**: Accepted
**Issues**: [#1870](https://github.com/HomericIntelligence/Scylla/issues/1870),
[#1882](https://github.com/HomericIntelligence/Scylla/issues/1882)

## Context

Scylla calls external APIs (Anthropic for agents, Anthropic again for
LLM judges, occasionally GitHub for issue and PR operations). Each of these
endpoints can fail transiently, rate-limit aggressively, or stall for minutes.
Long ablation runs amplify the cost of unprotected retries: a single broken
endpoint can burn the wall-clock budget for a 120-subtest sweep before any
human notices.

Historically the project carried two import paths for the same circuit-breaker
implementation:

- `scylla.core.circuit_breaker` — a thin re-export shim with the docstring
  "This module re-exports from hephaestus.resilience.circuit_breaker for
  backwards compatibility."
- `scylla.automation.circuit_breaker` — a second, identically-shaped re-export
  inside the `scylla.automation` package, which itself was a re-export shim.

Both pointed at the same upstream symbols in
`hephaestus.resilience.circuit_breaker`. The duplicate import surface was
flagged in audit issue #1870 ("automation/ package contains only a re-export
shim") under the strict-audit epic #1867. PR
[#1914](https://github.com/HomericIntelligence/Scylla/pull/1914)
removed the `scylla.automation` shim, leaving exactly one in-repo import
path plus the canonical upstream module.

## Decision

Use **one** circuit-breaker implementation, owned by ProjectHephaestus. New
code imports directly from `hephaestus.resilience.circuit_breaker`. Existing
call sites may continue to import via `scylla.core` for source compatibility.

PR #1914 removed:

- `src/scylla/automation/__init__.py`
- `src/scylla/automation/circuit_breaker.py`
- `tests/unit/automation/test_circuit_breaker.py`

The remaining surface is:

- `hephaestus.resilience.circuit_breaker` — canonical implementation
  (CircuitBreaker, CircuitBreakerOpenError, CircuitBreakerState,
  `get_circuit_breaker`, `reset_all_circuit_breakers`).
- [`src/scylla/core/__init__.py`](../../../src/scylla/core/__init__.py) —
  package-level re-export, lines 6–12 and 22–32. New code is encouraged to
  import directly from hephaestus, but the `scylla.core` re-export is
  retained because several call sites already use it and the shim has zero
  ongoing maintenance cost.
- [`src/scylla/core/circuit_breaker.py`](../../../src/scylla/core/circuit_breaker.py)
  — module-level re-export, marked "for backwards compatibility" in its
  docstring (line 3). Retained for the same reason: free, zero-cost,
  removable later if every caller migrates.

The `scylla.automation` package no longer exists. Any future import of
`scylla.automation.*` is an error.

## Consequences

**Positive**:

- A single source of truth for retry/cooldown semantics across the
  ecosystem. Bugs and tuning changes in
  `hephaestus.resilience.circuit_breaker` fix every consumer at once.
- The audit finding from #1870 is resolved: there is no longer a package
  whose only purpose is to re-export another package.
- New contributors no longer need to choose between two indistinguishable
  import paths.

**Negative**:

- One re-export shim still exists at `scylla.core.circuit_breaker`. It is
  three lines of imports plus an `__all__`. The cost of removing it is
  larger than the cost of keeping it (touches every call site), so it
  stays. New code should prefer `from hephaestus.resilience.circuit_breaker
  import …`.
- Scylla now has a hard runtime dependency on a specific
  hephaestus version range (`homericintelligence-hephaestus>=0.7.0,<1`,
  pinned in `pyproject.toml` per issue #1885). Bumping this range
  requires testing the consumer here.

## References

- [`src/scylla/core/__init__.py`](../../../src/scylla/core/__init__.py)
  — current public re-export, lines 6–12.
- [`src/scylla/core/circuit_breaker.py`](../../../src/scylla/core/circuit_breaker.py)
  — module-level re-export.
- PR [#1914](https://github.com/HomericIntelligence/Scylla/pull/1914)
  — removed the duplicate `scylla.automation` shim.
- Audit issues: [#1870](https://github.com/HomericIntelligence/Scylla/issues/1870),
  [#1867](https://github.com/HomericIntelligence/Scylla/issues/1867).
- Upstream: `hephaestus.resilience.circuit_breaker` in ProjectHephaestus.
