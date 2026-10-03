# Findings: Plan GitHub issue #2050

## Requirements

- Preserve current required checks and unrelated protection fields.
- Make every required-context workflow support `merge_group` / `checks_requested`.
- Add the approved squash/ALLGREEN repository-level queue policy.
- Add focused validation, run normal checks, pass strict PR review, then activate and smoke-test one queued PR.

## Research Findings

### From Team Knowledge

- Prior findings reported no matching skills.

### From Codebase

- `.github/workflows/_required.yml:30-37` preserves `pull_request` and `push` to `main` but explicitly omits `merge_group`; it is the sole producer of eleven documented required contexts.
- `.github/workflows/merge-queue-smoke.yml:16-64` is merge-group-only and emits a separate `merge-queue-smoke` context, contradicting the issue requirement to run every required-context provider for `merge_group`.
- `tests/unit/ci/test_merge_queue_readiness.py:37-67` currently enforces the smoke-only design while preserving PR/push triggers and required job names.
- `docs/dev/merge-queue-readiness.md:8-13` says `Required Checks` runs for `merge_group`, contradicting the workflow and tests; its activation table already records all approved queue settings.
- No tracked local ruleset definition or management script matched the merge-queue/ruleset search; activation is live GitHub repository configuration.

### From Official GitHub Documentation

- The repository-ruleset `merge_queue` rule uses `check_response_timeout_minutes`, `grouping_strategy`, `max_entries_to_build`, `max_entries_to_merge`, `merge_method`, `min_entries_to_merge`, and `min_entries_to_merge_wait_minutes`.
- Allowed enum values include `ALLGREEN`/`HEADGREEN` and `MERGE`/`SQUASH`/`REBASE`.
- Updating a ruleset requires resubmitting the complete ruleset body, so the implementation must derive its payload from the live GET response and append/replace only the `merge_queue` rule.

## Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Planning scope | No GitHub mutations | User requested a plan and prohibited `git`/`gh` operations |
| Merge-group workflow | Add `merge_group: {types: [checks_requested]}` to `_required.yml`; remove the smoke-only workflow | This directly satisfies the checklist and preserves the same required contexts for PRs, pushes, and queued synthetic commits |
| Live ruleset mutation | Round-trip the live repository ruleset and append exactly one queue rule | Preserves bypass actors, conditions, enforcement, required contexts, and unrelated rules |

## Questions Answered

| Question | Answer | Source |
|---|---|---|
| Which workflow provides required contexts? | `_required.yml` | Workflow header and job names |
| How is the ruleset represented? | Live GitHub repository configuration, not a tracked file | Repository-wide `rg` |
| Which focused test exists? | `tests/unit/ci/test_merge_queue_readiness.py` | Test suite |

## Synthesis

The current tree contains an earlier smoke-only workaround that conflicts with both issue #2050 and its own readiness documentation. The plan should restore the required workflow on `merge_group`, remove the separate smoke context, revise focused regression tests, and stage the live ruleset update after PR review.
