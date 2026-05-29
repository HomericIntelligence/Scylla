# Developer Onboarding

## Prerequisites

The following tools are required. Pinned versions are in `.tool-versions` (used by `mise`/`asdf`):

| Tool | Version | Install |
|------|---------|---------|
| [pixi](https://pixi.sh) | 0.63.2+ | `curl -fsSL https://pixi.sh/install.sh \| bash` |
| [just](https://just.systems) | 1.36.0+ | `pixi global install just` or package manager |
| [gh](https://cli.github.com) | 2.65.0+ | `pixi global install gh` or package manager |

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/HomericIntelligence/ProjectScylla.git
cd ProjectScylla

# 2. Configure environment variables
cp .env.example .env
# Edit .env and add your API keys (ANTHROPIC_API_KEY, GITHUB_TOKEN)

# 3. Install all dependencies
pixi install

# 4. Verify installation
pixi run python --version  # Should print Python 3.10+
pixi run pytest tests/ -v  # Run test suite
```

## IDE Setup (VS Code)

This repo ships three committed `.vscode/` config files:

- **`extensions.json`** — recommended extensions (Ruff, Python, mypy, TOML, YAML)
- **`launch.json`** — debug configs for tests and the `scylla` CLI
- **`settings.json`** — format-on-save, mypy import strategy, search exclusions

Open the repository in VS Code and accept the "Install Recommended Extensions" prompt.

## Development Commands

```bash
just              # List all available recipes
just test         # Run pytest
just lint         # Run ruff check
just format       # Run ruff format
just typecheck    # Run mypy
just pre-commit   # Run all pre-commit hooks
just watch        # Re-run tests on file changes (requires dev environment)
just debug <test> # Run a single test with --pdb on failure
```

## First PR Walkthrough

1. Pick an issue and comment to claim it
2. Create a feature branch: `git checkout -b <issue-number>-brief-description`
3. Make changes and run `pre-commit run --all-files` before committing
4. Push and open a PR: `gh pr create --body "Closes #<issue-number>"`
5. Enable auto-merge: `gh pr merge <PR#> --auto --squash`

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for branch naming conventions, commit format, and review etiquette.

## Codespaces / Dev Containers

This repo includes `.devcontainer/devcontainer.json` for one-click GitHub Codespaces setup.
The container installs pixi via a community feature and runs `pixi install` on creation.

> **Note:** The `ghcr.io/prulloac/devcontainer-features/pixi` community feature is unverified
> outside of Codespaces. If it fails, fall back to the Quick Start steps above inside the container.
