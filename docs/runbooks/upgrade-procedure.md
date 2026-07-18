# Upgrade Procedure Runbook

This runbook covers how to bump the Python version, the uv version,
or the CI container base image without breaking experiments or CI.

Each upgrade type is independent; follow only the section that applies.

> **Conventions used below**
>
> - All `uv run` commands assume you are at the repo root.
> - `NEW_PY` — the target CPython version, e.g. `3.12`.
> - `NEW_UV` — the target uv version, e.g. `0.64.0`.

---

## 1. Python version bump

### Files to update

| File | What to change |
|------|---------------|
| `pyproject.toml` | `requires-python = ">=X.Y"` and `Programming Language :: Python :: X.Y` classifier |
| `ci/Containerfile` | `ARG PYTHON_VERSION=X.Y` (or the `FROM python:X.Y-slim` line in `Dockerfile`) |
| `.pre-commit-config.yaml` | `language_version: pythonX.Y` entries for hooks that pin it |

### Procedure

```bash
# 1. Edit the files listed above
# 2. Regenerate the lock file (Python version changes invalidate SHA256)
uv lock   # regenerates uv.lock

# 3. Run full test suite in the updated environment
uv run pytest

# 4. Run type checks (mypy may surface new errors on newer Python)
pre-commit run mypy --all-files

# 5. Run full pre-commit suite
pre-commit run --all-files

# 6. Commit (uv.lock must be staged)
git add pyproject.toml ci/Containerfile .pre-commit-config.yaml uv.lock
git commit -m "chore(deps): bump Python to $NEW_PY"
```

**NEVER skip `uv lock` after a Python version change.** The lock
file encodes the SHA256 of the editable install; any source change
invalidates it and CI will fail with `lock-file not up-to-date`.

---

## 2. uv version bump

### Files to update

| File | What to change |
|------|---------------|
| `ci/Containerfile` | `ARG UV_VERSION=X.Y.Z` (line ~29) |
| Any CI workflow YAML | `uv-version:` input or pinned install step |

### Procedure

```bash
# 1. Edit ci/Containerfile UV_VERSION
# 2. Rebuild the CI image locally to confirm it installs cleanly
uv run ci-build

# 3. Regenerate uv.lock against the new uv binary
# (install new uv locally first: https://astral.sh/uv/install.sh)
uv lock

# 4. Run tests in the new image
podman run --rm -v .:/workspace:Z scylla-ci:local uv run pytest

# 5. Commit
git add ci/Containerfile uv.lock
git commit -m "chore(deps): bump uv to $NEW_UV"
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
uv run ci-build

# 3. Run the full CI suite inside the new image
podman run --rm -v .:/workspace:Z scylla-ci:local \
  bash -c "uv run pre-commit run --all-files && uv run pytest"

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
- We do **not** skip `uv.lock` commits. The lock is load-bearing in CI.
- We do **not** use `--no-verify` to bypass pre-commit. If a hook fails
  after an upgrade, fix the code.

---

## See also

- `pyproject.toml` — dependency specification, build system, and metadata
- `ci/Containerfile` — CI environment definition
- `Dockerfile` — evaluation agent container
- MEMORY.md: `uv.lock Rebase Conflict Resolution` — how to handle
  lock-file conflicts during rebase
