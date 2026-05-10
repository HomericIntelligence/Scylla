# ProjectScylla task runner — delegates to pixi run
# Ecosystem convention: justfile + pixi (invokable from Odysseus via just scylla-*)

# List all available recipes
default:
    @just --list

# Run pytest
test:
    pixi run test

# Run unit tests with coverage
test-unit:
    pixi run test-unit

# Run BATS shell tests
test-shell:
    pixi run test-shell

# Run ruff check
lint:
    pixi run lint

# Run ruff format
format:
    pixi run format

# Run mypy type checker
typecheck:
    pixi run mypy src/scylla scripts tests

# Build CI container image
ci-build:
    pixi run ci-build

# Run CI lint in container
ci-lint:
    pixi run ci-lint

# Run CI tests in container
ci-test:
    pixi run ci-test

# Run all CI in container
ci-all:
    pixi run ci-all

# Run pip-audit security scan
audit:
    pixi run audit

# Bump project version (usage: just bump patch|minor|major)
bump part:
    pixi run python scripts/bump_version.py {{part}}
    pixi lock

# Bump patch version (e.g. 0.1.0 -> 0.1.1)
bump-patch:
    pixi run python scripts/bump_version.py patch
    pixi lock

# Bump minor version (e.g. 0.1.0 -> 0.2.0)
bump-minor:
    pixi run python scripts/bump_version.py minor
    pixi lock

# Bump major version (e.g. 0.1.0 -> 1.0.0)
bump-major:
    pixi run python scripts/bump_version.py major
    pixi lock

# Run all pre-commit hooks
pre-commit:
    pixi run pre-commit run --all-files
