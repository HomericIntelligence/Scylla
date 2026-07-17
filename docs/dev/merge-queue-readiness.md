# Merge queue readiness

Scylla uses a staged merge-queue rollout for `main`. This repository prepares
the required checks; Odysseus owns the later live activation and smoke test.

## Workflow contract

The `Required Checks` workflow is the only workflow that emits the status
contexts required by the active `homeric-main-baseline` ruleset. It runs for:

- pull requests;
- pushes to `main`; and
- `merge_group` events with the `checks_requested` activity.

The required contexts remain:

- `lint`
- `unit-tests`
- `integration-tests`
- `security/dependency-scan`
- `security/secrets-scan`
- `build`
- `schema-validation`
- `deps/version-sync`
- `test`
- `package`
- `install`

Other workflows retain their existing triggers. In particular, merge-group
runs must not trigger image publishing or release jobs. The required workflow
retains read-only repository contents permission, and its dependency and secret
scans remain required gates.

## Activation authority

Do not activate or modify the live merge queue from this repository. After this
readiness change is merged and reviewed, Odysseus is the sole authority that may
update Scylla's live ruleset. It must preserve unrelated rules, bypass actors,
required contexts, and protections while adding this approved queue policy:

| Parameter | Approved value |
|-----------|----------------|
| Merge method | `SQUASH` |
| Grouping strategy | `ALLGREEN` |
| Maximum entries building | `10` |
| Maximum entries merged per group | `5` |
| Minimum entries merged | `1` |
| Minimum wait | `5` minutes |
| Check response timeout | `60` minutes |

Because readiness changes GitHub Actions behavior, a human reviewer must approve
the implementation PR before it merges. Automated or AI review evidence does
not satisfy that human-review gate.

## Post-merge evidence

Keep issue #2050 open through activation. Odysseus must record the live ruleset
response, one `merge_group` / `checks_requested` workflow run containing every
required context, and the representative queued merge result before the issue
can be closed. If the queued smoke test fails, report the failure rather than
bypassing or weakening any required check.
