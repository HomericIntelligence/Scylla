# Deployment Rollback Runbook

This runbook covers how to ship a new release tag and how to revert to
a prior tag if a release causes regressions.

All procedures assume you are at the repo root with a clean working tree
and `git remote origin` pointing at `HomericIntelligence/Scylla`.

> **Conventions used below**
>
> - `NEW_TAG` — the version being shipped, e.g. `v0.2.0`.
> - `PREV_TAG` — the last known-good tag, e.g. `v0.1.0`.
> - All `uv run` commands assume you are at the repo root.

---

## 1. Shipping a new tag

### Pre-flight checks

```bash
# Ensure main is up to date
git fetch origin && git status

# Confirm the version in pyproject.toml matches CHANGELOG.md
grep -m1 'version' pyproject.toml
grep -m1 '^## \[' CHANGELOG.md

# Run full pre-commit suite
pre-commit run --all-files
```

### Tag and push

```bash
# Create annotated tag (uv.lock and pyproject.toml must be committed)
git tag -a "$NEW_TAG" -m "Release $NEW_TAG"
git push origin "$NEW_TAG"
```

CI validates the tag build automatically. Monitor the
`Release` GitHub Actions workflow to completion before proceeding.

### Verify the release artifact

```bash
# Confirm the tag is visible and the wheel builds cleanly
gh release list --repo HomericIntelligence/Scylla | head -5
uv run python -m build --wheel --no-isolation 2>&1 | tail -5
```

---

## 2. Rolling back to a previous tag

### When to roll back

Roll back when all three are true:

1. The new tag is deployed on the evaluation hosts.
2. Experiment runs started against it produce unexpected failures (not
   covered by `experiment-failure-recovery.md`).
3. The defect cannot be hot-patched in a forward commit within ~1 hour.

### Roll-back steps

```bash
# Branch naming follows <issue-number>-<description>; substitute real values.
# Example for incident #2001 reverting v0.2.0 back to v0.1.0:
git checkout -b 2001-rollback-to-v0.1.0 v0.1.0

# If you need to force evaluation hosts to use the prior image, rebuild:
uv run ci-build   # builds scylla-ci:local from ci/Containerfile

# Push the rollback branch and open an expedited PR
git push -u origin 2001-rollback-to-v0.1.0
gh pr create --repo HomericIntelligence/Scylla \
  --title "hotfix: rollback to $PREV_TAG" \
  --body "Emergency rollback. Closes #2001"
gh pr merge --auto --squash --repo HomericIntelligence/Scylla
```

### What we do NOT do

- We do **not** force-push to `main`. Branch protection blocks it; use PRs.
- We do **not** delete the bad tag from the remote. Tags are immutable
  historical records; deprecate in `CHANGELOG.md` instead.
- We do **not** reuse the same version string. Bump patch (e.g.
  `v0.2.0` → `v0.2.1`) even for a rollback commit.

---

## See also

- `CHANGELOG.md` — per-version release notes
- `pyproject.toml` — authoritative version string
- `ci/Containerfile` — CI image used for evaluations
- `experiment-failure-recovery.md` — recover a running experiment
