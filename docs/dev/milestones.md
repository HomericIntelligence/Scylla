# Milestone Strategy

Scylla uses GitHub milestones to track progress toward planned releases.

## Active Milestones

### v0.2.0 -- Next Feature Release

Tracks enhancements, new evaluation capabilities, and non-breaking improvements beyond
the v0.1.x baseline. Issues assigned here represent near-term work that advances the
framework's feature set without requiring API-breaking changes.

**Scope includes:**

- New CLI commands and flags (report formats, NATS integration, Maestro wiring)
- Resilience patterns (retry logic, failure injection, backoff)
- Evaluation infrastructure improvements
- Supply chain hardening (SHA pinning, CI hardening)
- Versioning and release tooling

### v1.0.0 -- Stable Release

Tracks requirements for graduating from Alpha to Production/Stable. This milestone
represents the quality bar that must be met before the project's Development Status
classifier changes.

**Graduation criteria:**

- [ ] Src-layout migration fully complete (no stale `scylla/` path references)
- [ ] Comprehensive test coverage (unit, integration, and CLI tests)
- [ ] Stable public API (no breaking changes expected)
- [ ] Complete documentation (architecture, API, configuration, user guides)
- [ ] All audit findings resolved (S1 Structure, S10 Planning, S15 Compliance)
- [ ] CODE_OF_CONDUCT.md present
- [ ] py.typed marker verified in sdist/wheel builds

## Assigning Issues to Milestones

When creating or triaging issues, assign them to a milestone based on:

| Assign to | When the issue... |
|-----------|-------------------|
| **v0.2.0** | Adds a new feature, enhancement, or non-breaking improvement |
| **v1.0.0** | Addresses stability, documentation completeness, test coverage, or audit findings required for a stable release |
| **Neither** | Is a patch-level bug fix for v0.1.x, a one-off process task, or not tied to a specific release |

## Milestone Naming Convention

Milestones use semantic versioning (`vMAJOR.MINOR.PATCH`). New milestones should be
created as release planning progresses -- for example, `v0.3.0` after v0.2.0 ships.
