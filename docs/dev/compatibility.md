# Backwards-Compatibility and Migration Policy

This document defines ProjectScylla's SemVer interpretation, deprecation window, and curated public-API
surface. All contributors and consumers of the `scylla` package must follow these rules.

## Semantic Versioning

ProjectScylla follows [Semantic Versioning 2.0.0](https://semver.org/): `MAJOR.MINOR.PATCH`.

### What triggers each version component

| Component | Trigger |
|-----------|---------|
| **MAJOR** | Any breaking change to the public API (see [Public API Surface](#public-api-surface)) |
| **MINOR** | New backwards-compatible functionality, or deprecation of an existing public symbol |
| **PATCH** | Backwards-compatible bug fixes, documentation updates, and internal refactors |

### What counts as a breaking change

A change is **breaking** (and requires a MAJOR bump) if it:

- Removes or renames a symbol listed in [Public API Surface](#public-api-surface)
- Changes the signature of a public function or method in an incompatible way
  (removing a parameter, changing its type, or changing its semantics)
- Removes or renames a CLI subcommand or flag documented in `--help`
- Changes the schema of experiment YAML files in a way that makes existing files invalid
- Changes the schema of output JSON artefacts (run results, metrics exports) in a non-additive way
- Removes support for a Python minor version that was previously supported

A change is **not** breaking if it:

- Adds a new optional keyword argument with a default value
- Adds a new public symbol
- Adds fields to output JSON (additive schema change)
- Changes internal implementation details not exposed through the public API
- Fixes behaviour that was documented as undefined or erroneous

## Deprecation Window

Before removing or renaming a public symbol, it must pass through **one full minor release cycle**
of explicit deprecation:

1. In the MINOR release that introduces the deprecation, emit a `DeprecationWarning` at call site:

   ```python
   import warnings

   def old_function(...):
       warnings.warn(
           "old_function is deprecated and will be removed in the next major release. "
           "Use new_function instead.",
           DeprecationWarning,
           stacklevel=2,
       )
       return new_function(...)
   ```

2. Document the deprecation in the PR description and in the GitHub release notes
   (auto-generated via `gh release create --generate-notes`).
3. In the subsequent MAJOR release, remove the deprecated symbol.

**Minimum window**: At least one tagged minor release must exist between the deprecation commit and
the removal commit. A symbol deprecated in v0.5.0 may not be removed until v1.0.0 or later.

**No CHANGELOG requirement**: CHANGELOG.md was removed in PR #1960. Migration notes for breaking
changes, deprecations, and removals are recorded exclusively in:

- The PR description (required for all breaking/deprecating PRs)
- GitHub release notes, auto-generated from conventional commits via
  `gh release create vX.Y.Z --generate-notes`

Consumers are encouraged to watch [GitHub Releases](https://github.com/HomericIntelligence/ProjectScylla/releases)
for migration guidance.

## Public API Surface

The `scylla` package's `__init__.py` re-exports nine sub-packages. **Not all of these are considered
public API.** The curated public surface is narrower:

### Stable public API (backwards-compatibility guaranteed)

| Symbol | Location | Description |
|--------|----------|-------------|
| `scylla.__version__` | `src/scylla/__init__.py` | Package version string |
| `scylla.config` | `src/scylla/config/` | Experiment configuration loading and validation |
| `scylla.metrics` | `src/scylla/metrics/` | Metric calculation and aggregation |
| `scylla.judge` | `src/scylla/judge/` | LLM judge interface |
| `scylla.reporting` | `src/scylla/reporting/` | Report generation |
| `scylla.executor` | `src/scylla/executor/` | Execution engine public interface |
| CLI commands | `scylla --help` | All documented subcommands and flags |
| Experiment YAML schema | `schemas/` | Config file format |
| Output JSON schema | `schemas/` | Run-result and metrics-export format |

### Internal / unstable (no compatibility guarantee)

| Symbol | Reason |
|--------|--------|
| `scylla.adapters` | Implementation detail; subject to change |
| `scylla.e2e` | Internal test orchestration; not intended for external use |
| `scylla.nats` | Infrastructure adapter; may be replaced or removed |
| `scylla.cli` | Entry point internals; use the CLI binary, not the module |
| `scylla.analysis` | Research utilities; API evolves with research needs |
| `scylla.automation` | Internal automation; not part of the public interface |
| `scylla.discovery` | Internal resource discovery; subject to change |
| `scylla.utils` | Internal helpers; may be reorganised at any time |

> **Rule of thumb**: if it is not listed in the "Stable public API" table above, treat it as
> internal. Imports of `scylla.adapters`, `scylla.e2e`, `scylla.nats`, or `scylla.cli` internals
> may break at any minor release.

## Migration Guidance for Consumers

When a breaking change is shipped:

1. The PR description contains a **Migration** section explaining what changed and how to update.
2. The GitHub release notes (auto-generated) include the PR title and link.
3. Deprecated symbols emit `DeprecationWarning` for at least one minor cycle before removal,
   giving consumers a warning window before the breaking MAJOR release.

To receive migration alerts automatically, enable **GitHub Release notifications** for this
repository or subscribe to the release RSS feed:

```
https://github.com/HomericIntelligence/ProjectScylla/releases.atom
```
