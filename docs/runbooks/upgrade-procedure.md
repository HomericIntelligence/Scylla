# Upgrade Procedure Runbook

This runbook covers how to bump the Python version, the pixi version,
or the CI container base image without breaking experiments or CI.

Each upgrade type is independent; follow only the section that applies.

> **Conventions used below**
>
> - All `pixi run` commands assume you are at the repo root.
> - `NEW_PY` — the target CPython version, e.g. `3.12`.
> - `NEW_PIXI` — the target pixi version, e.g. `0.64.0`.

---

## 1. Python version bump

### Files to update

| File | What to change |
|------|---------------|
| `pixi.toml` | `[dependencies] python = ">=X.Y"` |
| `pyproject.toml` | `requires-python = ">=X.Y"` and `Programming Language :: Python :: X.Y` classifier |
| `ci/Containerfile` | `ARG PYTHON_VERSION=X.Y` (or the `FROM python:X.Y-slim` line in `Dockerfile`) |
| `.pre-commit-config.yaml` | `language_version: pythonX.Y` entries for hooks that pin it |

### Procedure

```bash
# 1. Edit the files listed above
# 2. Regenerate the lock file (Python version changes invalidate SHA256)
pixi install   # regenerates pixi.lock

# 3. Run full test suite in the updated environment
pixi run test

# 4. Run type checks (mypy may surface new errors on newer Python)
pre-commit run mypy --all-files

# 5. Run full pre-commit suite
pre-commit run --all-files

# 6. Commit (pixi.lock must be staged)
git add pixi.toml pyproject.toml ci/Containerfile .pre-commit-config.yaml pixi.lock
git commit -m "chore(deps): bump Python to $NEW_PY"
```

**NEVER skip `pixi install` after a Python version change.** The lock
file encodes the SHA256 of the editable install; any source change
invalidates it and CI will fail with `lock-file not up-to-date`.

---

## 2. pixi version bump

### Files to update

| File | What to change |
|------|---------------|
| `ci/Containerfile` | `ARG PIXI_VERSION=X.Y.Z` (line ~29) |
| Any CI workflow YAML | `pixi-version:` input or pinned install step |

### Procedure

```bash
# 1. Edit ci/Containerfile PIXI_VERSION
# 2. Rebuild the CI image locally to confirm it installs cleanly
pixi run ci-build

# 3. Regenerate pixi.lock against the new pixi binary
# (install new pixi locally first: https://pixi.sh/install.sh)
pixi install

# 4. Run tests in the new image
podman run --rm -v .:/workspace:Z scylla-ci:local pixi run test

# 5. Commit
git add ci/Containerfile pixi.lock
git commit -m "chore(deps): bump pixi to $NEW_PIXI"
```

---

## 3. CI container base image bump

The CI container (`ci/Containerfile`) uses a pinned Python base image.
The Dockerfile used for evaluation agent containers (`Dockerfile`) is
separate and may have a different version.

### Procedure

```bash
# 1. Edit FROM line(s) in ci/Containerfile (and Dockerfile if needed)
# 2. Rebuild locally
pixi run ci-build

# 3. Run the full CI suite inside the new image
podman run --rm -v .:/workspace:Z scylla-ci:local \
  bash -c "pixi run pre-commit run --all-files && pixi run test"

# 4. Commit
git add ci/Containerfile Dockerfile
git commit -m "chore(deps): bump CI container base to python:$NEW_PY-slim"
```

---

## 4. What we do NOT do

- We do **not** bump the Python version mid-experiment. Running
  experiments survive resume across Python minor versions only if the
  checkpoint and `run_result.json` schemas are unchanged. When in doubt,
  finish or checkpoint-snapshot the experiment first.
- We do **not** skip `pixi.lock` commits. The lock is load-bearing in CI.
- We do **not** use `--no-verify` to bypass pre-commit. If a hook fails
  after an upgrade, fix the code.

---

## See also

- `pixi.toml` — dependency specification
- `pyproject.toml` — build system and metadata
- `ci/Containerfile` — CI environment definition
- `Dockerfile` — evaluation agent container
- MEMORY.md: `pixi.lock Rebase Conflict Resolution` — how to handle
  lock-file conflicts during rebase
