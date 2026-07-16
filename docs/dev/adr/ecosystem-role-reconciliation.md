# ADR: Ecosystem Role Reconciliation

**Date**: 2026-03-25
**Status**: Accepted
**Issue**: [#1503](https://github.com/HomericIntelligence/Scylla/issues/1503)

## Context

ProjectOdyssey's `architecture.md` describes Scylla as performing "Chaos and
resilience testing; calls /agents to inject failures; Uses NATS events from
ProjectHermes." The actual implementation is an AI agent benchmarking and ablation
study framework with ~69K lines of code, a 7-tier ablation framework (T0-T6 with
120 sub-tests), a statistical analysis pipeline, and an LLM judge evaluation system.

Zero chaos engineering code exists in the codebase. There is no failure injection
module, no NATS integration, and no ProjectHermes dependency.

## Decision

Formalize Scylla's ecosystem role as **AI agent benchmarking and ablation
study framework** — specifically: testing, measurement, and optimization of agentic
AI workflows under constraints. Update all stale references within Scylla and
file a cross-repo issue for ProjectOdyssey to correct their `architecture.md`.

Do not add a chaos testing module. The codebase's entire architecture is purpose-built
for ablation benchmarking, and retrofitting chaos engineering would be scope creep with
no supporting infrastructure.

## Reasons

- The codebase contains 69K+ lines of ablation benchmarking infrastructure with zero
  chaos engineering code.
- NATS and ProjectHermes were never integrated; no imports, dependencies, or
  configuration references exist.
- Scylla's own documentation (README.md, CLAUDE.md, docs/design/architecture.md)
  already accurately describes the framework as "testing, measurement, and optimization
  under constraints."
- The only inaccuracy within Scylla was a "Resilience Testing" label in
  README.md's Core Concepts, which has been updated to "Ablation Benchmarking."

## Consequences

- Scylla's documentation is now internally consistent and accurately describes
  the framework's purpose.
- A drift-detection test (`tests/unit/test_ecosystem_role_consistency.py`) prevents
  future reintroduction of stale chaos/resilience claims.
- ProjectOdyssey's `architecture.md` must be updated separately via a cross-repo
  issue or PR to replace the chaos testing description with the actual ablation
  benchmarking role.
