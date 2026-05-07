# ADR: `to_dict()` Serialization Pattern on Pydantic Models

**Date**: 2026-05-06
**Status**: Accepted
**Issue**: [#1882](https://github.com/HomericIntelligence/ProjectScylla/issues/1882)

## Context

ProjectScylla persists almost every long-lived data object as JSON: experiment
configs, checkpoints, per-run results, judge outputs, and the rolled-up
experiment results. The data classes themselves are Pydantic `BaseModel`s,
which already provide `model_dump()` and `model_dump_json()`. Despite that,
the codebase consistently exposes a hand-written `to_dict(self) -> dict[str, Any]`
method on every model that is written to disk, and call sites use that method
rather than calling `model_dump()` directly.

A naive reader will ask: why duplicate Pydantic's serialization API? The
answer is that several persisted models need behavior that plain `model_dump()`
cannot express:

1. **Mode coercion**. Persisted JSON must always be in `mode="json"` (so
   `Path` becomes `str`, `Enum` becomes its value, etc.). Most call sites
   would otherwise forget the kwarg.
2. **Legacy field injection**. `E2ERunResult.to_dict()` re-injects
   `tokens_input` / `tokens_output` derived properties so older readers
   that predate `TokenStats` still parse run JSONs.
3. **Ephemeral-field exclusion**. `ExperimentConfig.to_dict()` strips a
   curated allowlist of CLI-only fields (`--until-*`, `--from-*`, filter
   flags, `keep_failed_workspaces`, etc.) so they do not get persisted into
   the experiment's canonical config and accidentally re-applied on
   `--resume`.
4. **Nested override**. `E2ECheckpoint.to_dict()` overwrites the full
   `model_dump()` of `config` with `config.to_dict()` so the ephemeral-field
   filter actually takes effect through nested serialization.

These are non-trivial behaviors. Centralising them in `to_dict()` lets every
caller serialize correctly with one method and gives reviewers a single
place to audit the JSON contract.

## Decision

Every persisted Pydantic model in `scylla.e2e` and adjacent packages
exposes a `to_dict(self) -> dict[str, Any]` method. Call sites that write
JSON go through `to_dict()`; they do **not** call `model_dump()` directly.

The canonical implementations live in [`src/scylla/e2e/models.py`](../../../src/scylla/e2e/models.py):

- `TokenStats.to_dict` (line 61) — simplest case, plain
  `self.model_dump()` so legacy callers can swap dataclasses for Pydantic
  without touching call sites.
- `SubTestConfig.to_dict` (line 248), `TierConfig.to_dict` (line 275),
  `JudgeResultSummary.to_dict` (line 306), `SubTestResult.to_dict` (line 436),
  `TierResult.to_dict` (line 466) — all delegate to
  `self.model_dump(mode="json")`.
- `E2ERunResult.to_dict` (line 378) — JSON-mode dump plus injected
  `tokens_input` / `tokens_output` legacy keys (lines 382–383).
- `ExperimentConfig.to_dict` (line 813) — JSON-mode dump with the
  ephemeral-field allowlist excluded (lines 822–842). The exclusion list
  is the authoritative declaration of which CLI flags are *not* persisted.
- `E2ECheckpoint.to_dict` (line 915) — composes `model_dump()` then
  replaces the embedded `config` with `self.config.to_dict()` so the
  ephemeral exclusion propagates (line 919).

Other modules follow the same shape:

- [`src/scylla/e2e/llm_judge_models.py:38`](../../../src/scylla/e2e/llm_judge_models.py)
- [`src/scylla/e2e/judge_selection.py:35,60`](../../../src/scylla/e2e/judge_selection.py)

Persistence call sites use `to_dict()` exclusively, e.g.:

- `models.py:506,848,926` — `json.dump(self.to_dict(), f, indent=2)` from
  the model's own `save()` method.
- [`src/scylla/e2e/experiment_result_writer.py:85`](../../../src/scylla/e2e/experiment_result_writer.py)
- [`src/scylla/e2e/stage_finalization.py:425,519`](../../../src/scylla/e2e/stage_finalization.py)
- [`src/scylla/e2e/run_report_hierarchy.py:131,366,511`](../../../src/scylla/e2e/run_report_hierarchy.py)
- [`src/scylla/e2e/regenerate.py:416`](../../../src/scylla/e2e/regenerate.py)
- [`src/scylla/e2e/pipeline_scripts.py:244`](../../../src/scylla/e2e/pipeline_scripts.py)

## Consequences

**Positive**:

- One method per model defines the on-disk JSON shape. Schema review
  becomes "read every `to_dict()`," not "audit every call site."
- Ephemeral-vs-persisted is enforced by code, not by convention.
  `--resume` cannot accidentally reapply a one-shot CLI flag because the
  flag never reaches disk.
- Backward-compatible field injection (the `tokens_input` /
  `tokens_output` case) is invisible to callers.
- `mode="json"` is applied uniformly, so `Path` / `Enum` / `datetime`
  values are always serialized to strings.

**Negative**:

- Boilerplate. ~13 near-identical `to_dict()` methods exist in `models.py`
  alone, most of which are one-liners. A shared base class or mixin
  would reduce the duplication, but each model has different override
  needs (`E2ERunResult` injects, `ExperimentConfig` excludes,
  `E2ECheckpoint` recurses), so the duplication is largely irreducible.
- Reviewers must remember that adding a new field to `ExperimentConfig`
  requires a decision: persist it, or add it to the ephemeral allowlist?
  The default (persist) is usually wrong for CLI-only fields and right
  for everything else.
- `model_dump()` is *not* banned at non-persistence call sites (e.g.,
  in-memory diffing, logging). The boundary is "anything that hits
  disk," which is enforceable by review but not by mypy.

## References

- [`src/scylla/e2e/models.py`](../../../src/scylla/e2e/models.py)
  — all canonical `to_dict()` implementations, lines 61, 248, 275, 306,
  378, 436, 466, 498, 569, 813, 915.
- [`src/scylla/e2e/llm_judge_models.py`](../../../src/scylla/e2e/llm_judge_models.py)
- [`src/scylla/e2e/judge_selection.py`](../../../src/scylla/e2e/judge_selection.py)
- Persisted JSON consumers: `experiment_result_writer.py`,
  `stage_finalization.py`, `run_report_hierarchy.py`, `pipeline_scripts.py`.
- Related: MEMORY.md "Pydantic None Coercion Pattern" — defensive
  validators that keep `to_dict()` round-trips lossless.
