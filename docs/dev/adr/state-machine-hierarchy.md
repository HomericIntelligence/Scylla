# ADR: Four-Level State Machine Hierarchy

**Date**: 2026-05-06
**Status**: Accepted
**Issue**: [#1882](https://github.com/HomericIntelligence/Scylla/issues/1882)

## Context

Scylla executes long-running ablation experiments that can take hours
or days to complete. Each experiment runs many tiers; each tier runs many
subtests; each subtest runs many individual agent invocations. Any of these
can be interrupted by rate limits, kill signals, or transient failures, and
the cost of restarting from scratch is unacceptable (full T0–T6 sweeps cost
tens of dollars and many wall-hours).

The runner therefore needs a resumable execution model. Rather than tracking
progress in ad-hoc booleans scattered across the codebase, the framework
models execution as a hierarchy of **four nested state machines**, each
persisted to a single `checkpoint.json`. Every transition saves the
checkpoint atomically so a crash, kill, or rate-limit error leaves the
experiment in a well-defined state from which `--resume` can continue.

## Decision

Model E2E execution as four nested state machines, from outermost (longest
lifetime) to innermost (shortest):

| Level | Enum | States | Defined in |
|-------|------|--------|------------|
| Experiment | `ExperimentState` | INITIALIZING → DIR_CREATED → REPO_CLONED → TIERS_RUNNING → TIERS_COMPLETE → REPORTS_GENERATED → COMPLETE (terminals: COMPLETE, INTERRUPTED, FAILED) | [`src/scylla/e2e/models.py:147`](../../../src/scylla/e2e/models.py) |
| Tier | `TierState` | PENDING → CONFIG_LOADED → SUBTESTS_RUNNING → SUBTESTS_COMPLETE → BEST_SELECTED → REPORTS_GENERATED → COMPLETE (terminal: COMPLETE, FAILED) | [`src/scylla/e2e/models.py:134`](../../../src/scylla/e2e/models.py) |
| Subtest | `SubtestState` | PENDING → RUNS_IN_PROGRESS → RUNS_COMPLETE → AGGREGATED (terminal: AGGREGATED, FAILED) | [`src/scylla/e2e/models.py:124`](../../../src/scylla/e2e/models.py) |
| Run | `RunState` | PENDING → DIR_STRUCTURE_CREATED → WORKTREE_CREATED → SYMLINKS_APPLIED → CONFIG_COMMITTED → BASELINE_CAPTURED → PROMPT_WRITTEN → REPLAY_GENERATED → AGENT_COMPLETE → AGENT_CHANGES_COMMITTED → DIFF_CAPTURED → PROMOTED_TO_COMPLETED → JUDGE_PIPELINE_RUN → JUDGE_PROMPT_BUILT → JUDGE_COMPLETE → RUN_FINALIZED → REPORT_WRITTEN → CHECKPOINTED → WORKTREE_CLEANED (terminals: WORKTREE_CLEANED, FAILED, RATE_LIMITED) | [`src/scylla/e2e/models.py:85`](../../../src/scylla/e2e/models.py) |

Each level has a dedicated state-machine module that owns its transition
registry, terminal-state set, and `advance()` driver:

- [`experiment_state_machine.py`](../../../src/scylla/e2e/experiment_state_machine.py)
  — see `EXPERIMENT_TRANSITION_REGISTRY` (line 69) and
  `ExperimentStateMachine.advance` (line 191).
- [`tier_state_machine.py`](../../../src/scylla/e2e/tier_state_machine.py)
  — `TIER_TRANSITION_REGISTRY` (line 67).
- [`subtest_state_machine.py`](../../../src/scylla/e2e/subtest_state_machine.py)
  — `SUBTEST_TRANSITION_REGISTRY` (line 71). Notably also defines
  `UntilHaltError` (line 32) so the `--until-run` flag can stop
  cleanly without poisoning the subtest as FAILED.
- Run-level transitions are driven by `subtest_executor.py` which mutates
  `RunState` per checkpoint save.

The four enums are colocated in `src/scylla/e2e/models.py` so they share
a single import path and a single canonical ordering.

## Consequences

**Positive**:

- Resume is uniform: `--resume` reads `checkpoint.json` and asks each
  state machine "what's next?" by looking up the registry. There is no
  per-component custom resume code.
- Partial failures are first-class. A tier in `FAILED` does not abort the
  experiment — `experiment_state` can reach `COMPLETE` even with mixed
  `tier_states` (this is the behavior CLAUDE.md flags under "Partial-Failure
  Semantics" and is enforced by the disjoint terminal sets above).
- `--until-experiment`, `--until-tier`, `--until-run`, and the symmetric
  `--from-*` flags all map directly to one state value at one level.
  See `ExperimentStateMachine.advance_to_completion(until_state=…)` at
  [`experiment_state_machine.py:250`](../../../src/scylla/e2e/experiment_state_machine.py).
- Each level's transition registry is small, reviewable, and can be tested
  independently of the others.

**Negative**:

- Adding a new state at any level is a four-touch change: enum, transition
  registry, action handler, and (often) checkpoint schema migration. This
  is intentional friction — states are persisted on disk and renaming one
  breaks every in-flight experiment.
- The `RunState` enum has 19 non-terminal states, which is more granular
  than the other three levels combined. The granularity is justified by
  the cost of redoing work (e.g., re-running the agent after a crash in
  `JUDGE_PROMPT_BUILT` would waste the entire agent execution), but it
  also means `RunState` is the primary place where checkpoint schema
  evolution is painful.
- Operators must inspect the correct level when diagnosing stalls.
  `experiment_state=COMPLETE` does not imply success; `tier_states` must
  be checked too (called out explicitly in CLAUDE.md).

## References

- [`src/scylla/e2e/models.py:85-160`](../../../src/scylla/e2e/models.py) —
  all four state enums.
- [`src/scylla/e2e/experiment_state_machine.py`](../../../src/scylla/e2e/experiment_state_machine.py)
  — top-level driver, full state sequence at line 36, registry at line 69.
- [`src/scylla/e2e/tier_state_machine.py`](../../../src/scylla/e2e/tier_state_machine.py)
- [`src/scylla/e2e/subtest_state_machine.py`](../../../src/scylla/e2e/subtest_state_machine.py)
- [`src/scylla/e2e/checkpoint.py`](../../../src/scylla/e2e/checkpoint.py)
  — `save_checkpoint()` provides the atomic-write primitive every level
  depends on.
- CLAUDE.md, "Partial-Failure Semantics" — operator-facing rule that
  follows directly from disjoint per-level terminal sets.
