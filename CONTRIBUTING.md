# Contributing to ProjectScylla

Thank you for your interest in contributing to ProjectScylla! This guide will help you get started.

## Table of Contents

- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Versioning and Releases](#versioning-and-releases)
- [Code Quality Standards](#code-quality-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting Guidelines](#issue-reporting-guidelines)
- [Documentation Expectations](#documentation-expectations)
- [Code Review Process](#code-review-process)
- [Code of Conduct](#code-of-conduct)
- [Getting Help](#getting-help)

## Quick Start

**New to ProjectScylla?** See [docs/dev/onboarding.md](docs/dev/onboarding.md) for the
canonical setup guide: prerequisites, `pixi install`, running tests, IDE setup (VS Code /
Codespaces), and a first-contribution walkthrough.

**TL;DR:**

```bash
pixi install && pixi run pytest tests/ -v
```

## Development Setup

### Prerequisites

- **Python**: 3.10+ (managed via Pixi)
- **Git**: For version control
- **Docker**: Optional, for containerized experiments
- **API Keys**: See `.env.example` for required keys

### Installing Dependencies

ProjectScylla uses Pixi for dependency management:

```bash
# Pixi automatically manages dependencies from pixi.toml
pixi run python --version

# All dependencies are installed in .pixi/ directory
# No manual pip install needed
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

**Required variables:**

- `ANTHROPIC_API_KEY` - For LLM judge and agent execution
- `GITHUB_TOKEN` - For GitHub operations

**Optional variables:**

- `OPENAI_API_KEY` - For OpenAI-based agents
- `SCYLLA_LOG_LEVEL` - Set to `DEBUG` for verbose output

See `.env.example` for complete documentation.

## Development Workflow

### 1. Create a Feature Branch

**IMPORTANT:** Never push directly to `main`. All changes must go through pull requests.

```bash
# Create a feature branch
git checkout -b <issue-number>-<short-description>

# Examples:
git checkout -b 42-add-cop-metric
git checkout -b 123-fix-judge-timeout
```

### 2. Make Your Changes

- Follow existing code patterns in `src/scylla/`
- Add type hints to all function signatures
- Write docstrings for public APIs
- Keep changes focused and minimal

### 3. Write Tests

```bash
# Create tests in tests/unit/
# Follow existing test patterns

# Run your tests
pixi run pytest tests/unit/your_test.py -v
```

### 4. Run Code Quality Checks

```bash
# Format and lint code
pixi run ruff check src/scylla/ --fix
pixi run ruff format src/scylla/

# Run all tests
pixi run pytest tests/ -v

# Type checking (via pre-commit)
pre-commit run mypy --all-files
```

### 5. Commit Your Changes

Follow conventional commits format:

```bash
git add <files>
git commit -m "type(scope): Brief description

Longer description if needed.

Closes #<issue-number>"
```

**Commit types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `chore`: Maintenance tasks

**Examples:**

```
feat(metrics): Add Cost-of-Pass calculation
fix(evaluation): Correct token counting logic
docs(readme): Update benchmark instructions
test(analysis): Add bootstrap CI tests
```

### 6. Push and Create PR

```bash
# Push your branch
git push -u origin <branch-name>

# Create pull request
gh pr create \
  --title "Brief description" \
  --body "Closes #<issue-number>

## Summary
Brief summary of changes

## Testing
How you tested the changes

## Checklist
- [x] Tests pass
- [x] Code formatted
- [x] Documentation updated"
```

## Versioning and Releases

ProjectScylla follows [Semantic Versioning](https://semver.org/) (SemVer).

### Version Declaration Sites

The version is declared in three files that **must stay in sync**:

| File | Field | Role |
|------|-------|------|
| `pyproject.toml` | `project.version` | Canonical source (used by hatchling for package metadata) |
| `pixi.toml` | `workspace.version` | Pixi workspace version |
| `src/scylla/__init__.py` | `__version__` | Runtime access; imported by the CLI |

A CI check (`scripts/check_version_consistency.py`) verifies all three agree on every PR.

### How to Bump the Version

1. Update the version string in all three files listed above.
2. Run `pixi install` to regenerate `pixi.lock` (the lock encodes the package SHA).
3. Commit all changes (including `pixi.lock`).

### Creating a Release

Releases are created by pushing a version tag:

```bash
# After your version-bump PR is merged on main:
git checkout main && git pull
git tag v<VERSION>      # e.g. git tag v0.2.0
git push origin v<VERSION>
```

The `.github/workflows/release.yml` workflow automatically creates a GitHub release
with auto-generated release notes from conventional commits.

### Versioning & Compatibility

ProjectScylla's backwards-compatibility policy, deprecation window, and curated public-API surface
are documented in [`docs/dev/compatibility.md`](docs/dev/compatibility.md). Key points:

- **MAJOR** bump required for any breaking change to the public API.
- **Deprecation window**: one full minor release cycle of `DeprecationWarning` before removal.
- **Migration notes** go in the PR description and in GitHub release notes
  (auto-generated via `gh release create --generate-notes`); there is no CHANGELOG file.

Read the full policy before landing any change that affects public symbols, CLI flags, or
experiment/output schemas.

## Code Quality Standards

### Python Style

- **PEP 8**: Follow Python style guide
- **Type Hints**: Required for all function signatures
- **Docstrings**: Required for public APIs
- **Line Length**: 100 characters maximum

### Code Principles

1. **KISS** - Keep It Simple, Stupid
2. **YAGNI** - You Ain't Gonna Need It
3. **DRY** - Don't Repeat Yourself
4. **TDD** - Test-Driven Development
5. **SOLID** - Single Responsibility, Open-Closed, etc.

### Handling Long Lines (E501)

The project enforces a **100-character line limit** (ruff rule E501). When a line exceeds this
limit, apply the following triage rule to decide whether to break the line or suppress the warning.

**Fix the line (preferred)** when the line can be broken without harming readability:

- Long string concatenations → use implicit string joining or a variable
- Long function call chains → break across multiple lines with trailing commas
- Long import lists → use parentheses and one import per line
- Long conditionals → extract sub-expressions into named variables

```python
# Before — too long
result = some_function(argument_one, argument_two, argument_three, argument_four, argument_five)

# After — broken across lines
result = some_function(
    argument_one,
    argument_two,
    argument_three,
    argument_four,
    argument_five,
)
```

**Suppress with `# noqa: E501`** only when breaking the line would reduce readability or is
technically impractical:

- URLs in comments or docstrings (breaking a URL makes it non-clickable and hard to copy)
- Regex patterns where splitting would obscure the pattern's meaning
- Long string literals that must remain intact (e.g., error messages compared in tests)
- Machine-generated or data-table lines where alignment matters

```python
# Acceptable suppression — URL that cannot be meaningfully split
# See https://docs.anthropic.com/en/api/getting-started#very-long-path-that-exceeds-the-limit  # noqa: E501

# Acceptable suppression — regex whose structure would be obscured by line breaks
PATTERN = re.compile(r"^(?P<tier>T\d+)/(?P<subtest>\d+)/run_(?P<run>\d+)/(?P<file>.+)$")  # noqa: E501
```

**Decision checklist:**

1. Can the line be reformatted without hurting readability? → **Fix it.**
2. Is the offending content a URL, regex, or test literal? → **Suppress with `# noqa: E501`.**
3. Would splitting create more confusion than the long line? → **Suppress with `# noqa: E501`.**
4. None of the above? → **Fix it.**

### Pre-commit Hooks

Install pre-commit hooks to automatically check code quality:

```bash
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

**Never skip hooks** with `--no-verify`. Fix the code instead.

## Testing Requirements

### Test Coverage

- **Unit tests**: Required for all new functionality
- **Integration tests**: For multi-component features
- **E2E tests**: For complete workflow changes

### Coverage Thresholds

ProjectScylla uses a dual-threshold coverage strategy:

| Threshold | Scope | Where Enforced | Value |
|-----------|-------|----------------|-------|
| Combined floor | `src/scylla/` + `scripts/` | `pyproject.toml` (`fail_under`) — local runs | 75% |
| Unit floor | `src/scylla/` only | CI `test.yml` unit step (`--cov-fail-under=75`) | 75% |
| Integration floor | `src/scylla/` only | CI `test.yml` integration step (`--cov-fail-under=5`) | 5% |

- **`pixi run test`** runs all tests with the combined 75% floor from `pyproject.toml`.
- **`pixi run test-unit`** runs `tests/unit/` with the same 75% `src/scylla/` floor as CI, giving you local parity with the CI unit step.
- **CI** uses `--override-ini="addopts="` to bypass `pyproject.toml` and apply its own per-step floors independently.

### Running Tests

```bash
# All tests (combined 75% coverage floor)
pixi run test

# Unit tests with CI-matching 75% src/scylla/ coverage floor
pixi run test-unit

# Specific categories
pixi run pytest tests/unit/ -v          # Unit tests only
pixi run pytest tests/unit/analysis/ -v # Includes integration-style tests

# Specific modules
pixi run pytest tests/unit/analysis/ -v
pixi run pytest tests/unit/metrics/ -v

# With coverage
pixi run pytest tests/ --cov=src/scylla --cov-report=html
```

### Writing Tests

Use pytest with fixtures and parametrization:

```python
import pytest

def test_metric_calculation():
    """Test that metric calculates correctly."""
    result = calculate_metric(input_data)
    assert result == expected_value

@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
])
def test_with_params(input, expected):
    """Test with multiple inputs."""
    assert double(input) == expected
```

## Pull Request Process

### Before Submitting

- [ ] All tests pass locally
- [ ] Code is formatted (`ruff format`)
- [ ] Code is linted (`ruff check`)
- [ ] Type hints added to new functions
- [ ] Documentation updated
- [ ] Commit message follows conventional commits
- [ ] PR links to related issue

### PR Description Template

```markdown
## Summary
Brief description of changes

## Motivation
Why this change is needed

## Testing
How you tested the changes

## Checklist
- [x] Tests pass
- [x] Code formatted and linted
- [x] Type hints added
- [x] Documentation updated
- [x] Linked to issue #XXX
```

### Review Process

1. **Automated Checks**: CI must pass (tests, linting, type checking)
2. **Code Review**: At least one maintainer approval required
3. **Changes Requested**: Address feedback in new commits
4. **Approval**: PR merged via rebase to maintain linear history

### Responding to Review Comments

Reply to each comment with:

- `Fixed - [brief description of change]`
- `Won't fix - [explanation]`
- `Question - [clarifying question]`

## Issue Reporting Guidelines

### Bug Reports

Use this template:

```markdown
## Description
Clear description of the bug

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- OS: [e.g., Ubuntu 22.04]
- Python: [e.g., 3.10]
- ProjectScylla version: [e.g., commit SHA]

## Additional Context
Any other relevant information
```

### Feature Requests

```markdown
## Problem
What problem does this solve?

## Proposed Solution
How should it work?

## Alternatives Considered
What other approaches did you consider?

## Additional Context
Any other relevant information
```

### Questions

For questions about usage or implementation:

1. Check existing documentation first
2. Search closed issues
3. Create a new issue with `question` label

## Documentation Expectations

### Code Documentation

- **Docstrings**: Required for public functions, classes, and modules
- **Type hints**: Required for all function signatures
- **Comments**: Only for non-obvious logic

```python
def calculate_metric(data: pd.DataFrame, threshold: float = 0.5) -> float:
    """Calculate performance metric from experiment data.

    Args:
        data: DataFrame with columns 'score' and 'pass_rate'
        threshold: Minimum pass rate to consider (default: 0.5)

    Returns:
        Calculated metric value between 0.0 and 1.0

    Raises:
        ValueError: If data is empty or missing required columns
    """
    # Implementation here
```

### Project Documentation

- **README.md**: Update if changing user-facing features
- **CLAUDE.md**: Reference for AI agent development (don't modify without discussion)
- **docs/**: Add design docs for major features
- **docs/dev/data-policy.md**: Data retention and deletion policy for the `results/` directory
  (what is stored, how long to keep it, and how to purge runs)

## Code Review Process

### For Contributors

1. **Self-review**: Review your own code before requesting review
2. **Small PRs**: Keep PRs focused and reviewable (< 400 lines)
3. **Tests included**: All PRs should include tests
4. **Documentation**: Update docs for user-facing changes

### For Reviewers

1. **Timely**: Respond within 48 hours
2. **Constructive**: Be specific and helpful
3. **Thorough**: Check tests, docs, and edge cases
4. **Blocking vs. Non-blocking**: Clarify which comments must be addressed

## Getting Help

- **Documentation**: Check `docs/` directory
- **Issues**: Search existing issues first
- **Discussions**: Use GitHub Discussions for general questions
- **Chat**: Join our community chat (link in README)

## Development Tips

### Quick Iteration

```bash
# Fast test iteration (no rendering)
pixi run python scripts/generate_all_results.py --no-render

# Run specific test file
pixi run pytest tests/unit/analysis/test_stats.py -v -k "test_bootstrap"

# Auto-format on save in your editor
# Configure VSCode/PyCharm to run ruff on save
```

### Debugging

```bash
# Enable debug logging
export SCYLLA_LOG_LEVEL=DEBUG

# Run with pdb
pixi run python -m pdb scripts/manage_experiment.py

# Pytest debugging
pixi run pytest tests/ -v --pdb  # Drop into debugger on failure
```

## Project Structure

```
ProjectScylla/
├── src/scylla/          # Python source code
│   ├── analysis/        # Statistical analysis
│   ├── adapters/        # CLI adapters
│   ├── automation/      # Automation utilities
│   ├── cli/             # CLI interface
│   ├── config/          # Configuration
│   ├── core/            # Core types
│   ├── discovery/       # Resource discovery
│   ├── e2e/             # E2E testing framework
│   ├── executor/        # Execution engine
│   ├── judge/           # LLM judge system
│   ├── metrics/         # Metrics calculation
│   ├── reporting/       # Report generation
│   └── utils/           # Utility functions
├── tests/               # Test suite
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── fixtures/        # Test fixtures
├── scripts/             # Automation scripts
├── config/              # Configuration files
├── docs/                # Documentation
└── .claude/             # AI agent configs
```

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating,
you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## License

By contributing, you agree that your contributions will be licensed under the BSD-3-Clause License.

---

**Thank you for contributing to ProjectScylla!** 🚀
