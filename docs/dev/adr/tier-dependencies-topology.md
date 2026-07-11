# ADR: `TIER_DEPENDENCIES` Topological Execution Model

**Date**: 2026-05-06
**Status**: Accepted
**Issue**: [#1882](https://github.com/HomericIntelligence/Scylla/issues/1882)

## Context

The ablation framework defines seven tiers (T0–T6) with structural
dependencies dictated by the experimental design:

- T0 (Prompts), T1 (Skills), T2 (Tooling), T3 (Delegation), and T4
  (Hierarchy) are **independent ablations**. None of them needs results
  from the others.
- T5 (Hybrid) is defined as "best combinations and permutations of T0–T4."
  It must run *after* the five base tiers so it can read each base
  tier's winning subtest.
- T6 (Super) is "everything enabled at maximum capability" and is defined
  as the extension of T5's winner, so it depends on T5.

Running T0–T4 sequentially when they have no inter-tier data dependency
is a multi-hour waste. The runner has to discover this parallelism
without hard-coding "run these five together, then this one, then this
one" into control flow — that style of code rots the moment a new tier
is added or removed at the CLI.

## Decision

Encode tier dependencies as a single dictionary, `TIER_DEPENDENCIES`, in
[`src/scylla/e2e/models.py:197`](../../../src/scylla/e2e/models.py):

```python
TIER_DEPENDENCIES: dict[TierID, list[TierID]] = {
    TierID.T0: [],
    TierID.T1: [],
    TierID.T2: [],
    TierID.T3: [],
    TierID.T4: [],
    TierID.T5: [TierID.T0, TierID.T1, TierID.T2, TierID.T3, TierID.T4],
    TierID.T6: [TierID.T5],
}
```

The runner consumes this map via `_get_tier_groups()` in
[`src/scylla/e2e/runner.py:163`](../../../src/scylla/e2e/runner.py),
which performs a topological *layering* — repeatedly extracting the set
of tiers whose dependencies are already satisfied — and returns a list
of parallelizable groups. For the canonical full sweep this yields
`[[T0, T1, T2, T3, T4], [T5], [T6]]` (documented as the example in the
function docstring at line 174).

The grouping algorithm has three properties worth noting:

1. **User-scoped**: a dependency is considered satisfied if it is *not in
   `tiers_to_run`*. Running just T5 in isolation is legal — the
   dependency check at `runner.py:190` reads
   `dep in completed or dep not in tiers_to_run`. This lets operators
   run partial sweeps (e.g., `--tiers T2,T5`) without the runner
   complaining about missing T0/T1/T3/T4.
2. **Deterministic order within a group**: ready tiers are sorted before
   being appended (`runner.py:201`), so logs and parallel-group ordering
   are reproducible.
3. **Cycle detection**: if `remaining` is non-empty but `ready` is
   empty, the runner raises `ValueError("Unable to resolve tier
   dependencies …")` (`runner.py:194-199`). This is dead code under the
   current static map, but it future-proofs against an edit that
   accidentally introduces a cycle.

## Consequences

**Positive**:

- One declaration, one consumer. Adding T7 is a one-line edit to
  `TIER_DEPENDENCIES`; the runner discovers the new layer
  automatically.
- The "T0–T4 in parallel" behavior is *emergent* from the empty
  dependency lists, not from a special-case branch in the runner.
- Partial runs work without configuration: `--tiers T5` is valid because
  the dependency check tolerates "missing" base tiers — the operator is
  presumed to know they are pointing T5 at a previous experiment's
  best-subtest record.
- The map is colocated with the `TierID` enum it references, so the
  one-and-only place to look when triaging "why is T5 running before
  T1 finished?" is `models.py:197`.

**Negative**:

- The empty-dependency-tolerated case (`dep not in tiers_to_run`) is
  pragmatic but easy to misuse. An operator who runs just T5 expecting
  the runner to also schedule T0–T4 will be surprised. The CLI
  documentation, not the data model, has to teach this.
- Tiers are coarse: the topology has nothing to say about subtest-level
  dependencies. Cross-subtest inheritance (T5 reading T0–T4 winners) is
  handled separately in `SubTestConfig.inherit_best_from` and
  best-subtest selection — see
  [`src/scylla/e2e/models.py:229-232`](../../../src/scylla/e2e/models.py).
- The "tiers within a group can run in parallel" guarantee imposes
  constraints on what a tier's action functions can do (no shared mutable
  state across tier executions). This is enforced by review, not types.

## References

- [`src/scylla/e2e/models.py:197-205`](../../../src/scylla/e2e/models.py)
  — the `TIER_DEPENDENCIES` declaration with the three-line comment
  explaining the topology.
- [`src/scylla/e2e/runner.py:163-205`](../../../src/scylla/e2e/runner.py)
  — `_get_tier_groups()` implementation.
- CLAUDE.md "Testing Tiers (Ablation Study Framework)" — operator-facing
  description of the seven tiers and their roles.
- Related ADR: [State Machine Hierarchy](state-machine-hierarchy.md) —
  tier execution within a group is driven by `TierStateMachine`.
