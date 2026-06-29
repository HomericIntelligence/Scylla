# Developer Onboarding — ProjectScylla

This is the canonical quickstart reference. Both `README.md` and `CONTRIBUTING.md` link here.

## Prerequisites

The following tools are required. Versions are pinned in `.tool-versions` at the repo root
(used by `mise` / `asdf`):

| Tool | Pinned version | Purpose |
|------|---------------|---------|
| `pixi` | 0.63.2 | Dependency and environment manager |
| `just` | 1.36.0 | Task runner (delegates to `pixi run`) |
| `gh` | 2.65.0 | GitHub CLI (PR workflow) |

Install `pixi` if not already present:

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

Install `just` and `gh` via your system package manager, or let `mise`/`asdf` pick up `.tool-versions`.

## Environment Setup

```bash
# Clone the repo (or your fork)
git clone https://github.com/HomericIntelligence/ProjectScylla.git
cd ProjectScylla

# Install all dependencies (creates .pixi/ env)
pixi install

# Copy environment template and add API keys
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, GITHUB_TOKEN, etc.
```

## Verify Installation

```bash
pixi run python --version   # Should be 3.10+
pixi run pytest tests/ -v   # All tests should pass
just --list                  # Shows available task recipes
```

## Common Development Tasks

```bash
# Run all tests
just test

# Run unit tests with coverage (mirrors CI threshold)
just test-unit

# Lint code
just lint

# Format code
just format

# Type-check
just typecheck

# Watch tests — re-runs automatically on file change
# (requires pytest-watch, already in pixi.toml [feature.dev.pypi-dependencies])
just watch

# Debug a single test with pdb
just debug tests/unit/path/test_foo.py::test_bar

# Run all pre-commit hooks
just pre-commit
```

## IDE Setup

### VS Code / Codespaces

The repository ships three committed VS Code configs in `.vscode/`:

- `extensions.json` — recommended extensions (Ruff, Pylance, mypy, TOML, YAML)
- `launch.json` — debug configs for pytest and the `scylla` CLI
- `settings.json` — format-on-save, ruff formatter, mypy strategy

VS Code will prompt to install the recommended extensions on first open.

For Codespaces, a `.devcontainer/devcontainer.json` is provided. It uses the
`mcr.microsoft.com/devcontainers/python:1-3.10-bookworm` base image and installs
`pixi` via a community devcontainer feature, then runs `pixi install` after creation.

> **Note**: The `ghcr.io/prulloac/devcontainer-features/pixi:1` feature is a community
> contribution. If it is unavailable, replace `postCreateCommand` with a shell command
> that downloads and installs pixi directly:
> `"postCreateCommand": "curl -fsSL https://pixi.sh/install.sh | bash && pixi install"`

## First Contribution Walkthrough

1. Find or open an issue.
2. Create a branch: `git checkout -b <issue-number>-short-description`
3. Make changes. Write or update tests in `tests/unit/`.
4. Run `just lint`, `just test`, `just typecheck`.
5. Commit: `git commit -m "type(scope): description (#<issue>)"`
6. Push and open a PR: `gh pr create --title "..." --body "Closes #<issue>"`
7. Enable auto-merge: `gh pr merge <PR#> --auto --squash`

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for full contributor guidelines, PR conventions,
coverage thresholds, and review etiquette.
