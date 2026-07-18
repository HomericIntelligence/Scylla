# CI Container

The `ci/` directory contains the container image definition for running Scylla's CI
pipeline — tests, linting, security scans — in an isolated, reproducible environment.

This is **separate** from the experiment container (`docker/Dockerfile`), which runs AI agent
evaluations and includes Node.js and the Claude Code CLI. The CI container is lightweight:
Python 3.12, uv, pre-commit, bats — no experiment-specific tooling.

## Building

OCI-compliant — works with both Podman (rootless, no SU) and Docker:

```bash
# Podman (recommended — no root required)
podman build -f ci/Containerfile -t scylla-ci:local .

# Docker
docker build -f ci/Containerfile -t scylla-ci:local .

# Or use the uv task
uv run ci-build
```

## Running CI locally

Use `scripts/run_ci_local.sh` to run the full CI suite inside the container:

```bash
# All checks (pre-commit + tests + security + shell tests)
./scripts/run_ci_local.sh

# Specific subset
./scripts/run_ci_local.sh pre-commit    # linting only
./scripts/run_ci_local.sh test          # pytest unit + integration
./scripts/run_ci_local.sh security      # pip-audit
./scripts/run_ci_local.sh shell-test    # BATS shell tests
```

Or individual uv tasks:

```bash
uv run ci-lint   # pre-commit
uv run ci-test   # pytest
uv run ci-all    # everything
```

## Container engine

The script auto-detects the container engine: Podman first, Docker as fallback.
Override with the `CONTAINER_ENGINE` environment variable:

```bash
CONTAINER_ENGINE=docker ./scripts/run_ci_local.sh test
```

## Podman rootless notes

The container runs as UID 1000 (user `ci`). When volume-mounting the repo:

```bash
# :Z flag handles SELinux relabeling on Podman
podman run --rm \
  --userns=keep-id \
  --volume .:/workspace:Z \
  scylla-ci:local \
  uv run pytest tests/unit
```

`--userns=keep-id` maps your host UID into the container so mounted files have
correct ownership. No `sudo` or `--privileged` required.

## What's baked in

The CI image pre-installs:

- **uv** with all dependency groups and extras synced from `uv.lock` (`uv sync --all-groups --all-extras --locked`)
- **pre-commit hook environments** (the biggest speedup — no network calls at CI time)
- **BATS** for shell testing

Source code is **not** baked in — it is volume-mounted at runtime from the host. This means:

- Container image only rebuilds when `uv.lock`, `pyproject.toml`, or `.pre-commit-config.yaml` change
- Source changes do not require a container rebuild

## Image registry

In CI, the image is built and pushed to GHCR by `.github/workflows/ci-image.yml`:

```
ghcr.io/HomericIntelligence/scylla-ci:latest
ghcr.io/HomericIntelligence/scylla-ci:<git-sha>
```

Workflows pull `scylla-ci:latest` and mount the current checkout as `/workspace`.
