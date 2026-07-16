# Architectural Decision Records

This directory holds the Scylla ADRs — short, dated records
documenting non-trivial architecture and design decisions. Each ADR
follows the standard `Status / Context / Decision / Consequences /
References` shape and cites real file paths and line numbers as
evidence.

## Index

| ADR | Status | Date | Topic |
|-----|--------|------|-------|
| [Docker Integration Testing Deferred](docker-testing-deferred.md) | Accepted | 2026-02-27 | Why `tests/docker/` does not exist and the CI workflow validates only Dockerfile/compose syntax. |
| [Ecosystem Role Reconciliation](ecosystem-role-reconciliation.md) | Accepted | 2026-03-25 | Scylla's role is ablation benchmarking, not chaos testing. |
| [Four-Level State Machine Hierarchy](state-machine-hierarchy.md) | Accepted | 2026-05-06 | Experiment / Tier / Subtest / Run state machines with checkpoint persistence. |
| [`to_dict()` Serialization Pattern](to-dict-serialization-pattern.md) | Accepted | 2026-05-06 | Persistence boundary for Pydantic models — JSON-mode dump, ephemeral exclusion, legacy injection. |
| [Circuit-Breaker Consolidation](circuit-breaker-consolidation.md) | Accepted | 2026-05-06 | Single circuit-breaker implementation owned by `hephaestus.resilience` (resolved by PR #1914). |
| [`TIER_DEPENDENCIES` Topology](tier-dependencies-topology.md) | Accepted | 2026-05-06 | Topological grouping of T0–T6 for parallel execution. |
| [Bootstrap BCa Confidence Intervals](bootstrap-bca-ci-statistics.md) | Accepted | 2026-05-06 | BCa bootstrap as the canonical CI method for all reported statistics. |

## Authoring guidelines

- Filename: kebab-case, no date prefix (decisions are tagged by their
  `**Date**:` line, not by filename).
- Length: 80–200 lines. ADRs are reference material, not stubs.
- Always cite specific files and line numbers. ADRs without evidence
  rot quickly.
- Sections required: `Status`, `Context`, `Decision`, `Consequences`,
  `References`. `Reasons` is acceptable as a substitute for the
  positive half of `Consequences` if the older ADRs in this directory
  use it.
- New ADRs should be added to the index above in the same PR.
