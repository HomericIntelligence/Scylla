# Scylla task runner — delegates to uv
# Ecosystem convention: justfile + uv (invokable from Odysseus via just scylla-*)

# List all available recipes
default:
    @just --list

# Sync the locked dev environment (all groups + extras)
sync:
    uv sync --all-groups --all-extras --locked

# Run pytest
test:
    uv run pytest

# Run unit tests with coverage
test-unit:
    uv run pytest tests/unit --override-ini='addopts=' -v --strict-markers --cov=src/scylla --cov-report=term-missing --cov-fail-under=75

# Run BATS shell tests
test-shell:
    bats tests/shell/ --recursive --timing

# Run ruff check
lint:
    uv run ruff check src/scylla scripts tests

# Run ruff format
format:
    uv run ruff format src/scylla scripts tests

# Run mypy type checker
typecheck:
    uv run mypy src/scylla scripts tests

# Check import-layer contracts (import-linter)
lint-imports:
    uv run lint-imports --config pyproject.toml

# Build CI container image
ci-build:
    podman build -f ci/Containerfile -t scylla-ci:local . || docker build -f ci/Containerfile -t scylla-ci:local .

# Run CI lint in container
ci-lint:
    ./scripts/run_ci_local.sh pre-commit

# Run CI tests in container
ci-test:
    ./scripts/run_ci_local.sh test

# Run all CI in container
ci-all:
    ./scripts/run_ci_local.sh all

# Run pip-audit security scan
audit:
    uv run pip-audit --format json | uv run python scripts/filter_audit.py

# Bump project version (usage: just bump patch|minor|major)
bump part:
    uv run python scripts/bump_version.py {{part}}
    uv lock

# Bump patch version (e.g. 0.1.0 -> 0.1.1)
bump-patch:
    uv run python scripts/bump_version.py patch
    uv lock

# Bump minor version (e.g. 0.1.0 -> 0.2.0)
bump-minor:
    uv run python scripts/bump_version.py minor
    uv lock

# Bump major version (e.g. 0.1.0 -> 1.0.0)
bump-major:
    uv run python scripts/bump_version.py major
    uv lock

# Run all pre-commit hooks
pre-commit:
    uv run pre-commit run --all-files

# Watch tests and re-run on file changes (pytest-watch is in the dev group)
watch:
    uv run ptw tests/

# Drop into pdb for a specific test (usage: just debug tests/path/test_foo.py::test_bar)
debug TEST:
    uv run python -m pdb -m pytest -xvs {{TEST}}
