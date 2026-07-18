
## Overview

Analyze Scylla for completeness, quality, and maturity across six dimensions. Provide letter grades with specific evidence drawn from the actual codebase.

**Context**: Scylla is a Python 3.10+ AI agent benchmarking framework that evaluates agent architectures across 7 tiers (T0-T6, 120 sub-tests). It runs agents against task fixtures, scores outputs with an LLM judge, and produces statistical reports (34 figures, 11 tables). The framework is actively operational — experiment runs exist in `results/` from today.

---

## Analysis Framework

### 1. Project Structure & Organization (Weight: 15%)

**Grading Criteria:**

- **A (90-100%):** Clear hierarchy, separation of concerns, consistent conventions
- **B (80-89%):** Good structure with minor gaps
- **C (70-79%):** Adequate but with notable disorganization
- **D (60-69%):** Hard to navigate
- **F (<60%):** No clear structure

**Success Criteria:**

- `src/scylla/` package mirrors conceptual layers (adapters → e2e → metrics → reporting)
- `tests/` mirrors `src/scylla/` with unit and fixture separation
- Config, scripts, docs, and docker are logically separate
- Naming conventions consistent across all modules

**Tasks to Evaluate:**

1. Map `src/scylla/` sub-packages against the conceptual pipeline (ingest → execute → judge → metrics → report)
2. Check `tests/` mirrors `src/scylla/` structure with matching unit/fixture split
3. Verify `tests/claude-code/shared/` tier/agent/block/skill layout is internally consistent
4. Identify any orphaned files or directories referenced in CLAUDE.md that don't exist (e.g., `agents/`)
5. Check `scripts/` for naming clarity and whether scripts duplicate CLI entry points

---

### 2. Documentation Quality (Weight: 20%)

**Grading Criteria:**

- **A (90-100%):** Comprehensive, accurate, up-to-date at every layer
- **B (80-89%):** Good coverage, minor staleness
- **C (70-79%):** Basic docs with gaps or stale sections
- **D (60-69%):** Minimal, hard to onboard
- **F (<60%):** Absent or misleading

**Success Criteria:**

- `README.md` accurate to current implementation state (not just planned state)
- `CLAUDE.md` matches actual repo structure (no dead links, no phantom directories)
- `docs/research.md` / `docs/design/` reflect the implemented architecture
- Inline docstrings on public APIs in `src/scylla/`
- `tests/claude-code/shared/blocks/` CLAUDE.md building blocks are well-documented
- `.claude/shared/` reference files are consistent with each other and with CLAUDE.md

**Tasks to Evaluate:**

1. Check CLAUDE.md for stale references (e.g., `agents/hierarchy.md`, `agents/delegation-rules.md`)
2. Review README.md accuracy against the implemented framework
3. Sample 5 public functions across `src/scylla/` for docstring presence and quality
4. Verify `docs/design/` files match the implemented architecture (adapter interface, judge protocol, rubric schema)
5. Check `.claude/shared/metrics-definitions.md` for consistency with `src/scylla/metrics/`

---

### 3. Testing Coverage & Quality (Weight: 25%)

**Grading Criteria:**

- **A (90-100%):** High coverage, well-organized, varied test types
- **B (80-89%):** Good coverage, some gaps
- **C (70-79%):** Adequate unit tests, limited integration coverage
- **D (60-69%):** Minimal tests, poor isolation
- **F (<60%):** Little to no tests

**Success Criteria:**

- `pytest --cov` meets or exceeds the 75% `--cov-fail-under` threshold
- Unit tests cover all `scylla/` sub-packages (adapters, analysis, e2e, executor, judge, metrics, reporting)
- 47 test fixtures (test-001 to test-047) have complete `test.yaml`, `prompt.md`, `expected/criteria.md`, `expected/rubric.yaml`
- Sub-test YAML configs in `tests/claude-code/shared/subtests/t0/`–`t6/` are all valid per `schemas/`
- Tests use proper mocking for external calls (Docker, GitHub API, Claude API)

**Tasks to Evaluate:**

1. Run `uv run python -m pytest tests/unit/ --co -q 2>/dev/null | tail -5` to count collected tests
2. Check that each `src/scylla/` module has a corresponding test file in `tests/unit/`
3. Sample 3 test files for mocking discipline (no real network/filesystem calls in unit tests)
4. Count how many of the 47 test fixtures have all 4 required files present
5. Verify `tests/claude-code/shared/subtests/` sub-test counts match the tier table in CLAUDE.md (T0:24, T1:10, T2:15, T3:41, T4:14, T5:15, T6:1)

---

### 4. Code Quality & Standards (Weight: 20%)

**Grading Criteria:**

- **A (90-100%):** Consistent style, typed, well-structured
- **B (80-89%):** Good quality with minor issues
- **C (70-79%):** Functional but inconsistent
- **D (60-69%):** Many quality issues
- **F (<60%):** Major problems

**Success Criteria:**

- All `src/scylla/` code passes `ruff` (style/lint) and `mypy` (type checking) — enforced by pre-commit
- Pydantic models used for all structured data (config, results, metrics)
- No bare `except:` clauses; specific exception handling throughout
- Functions under ~50 lines; clear single responsibility
- No hardcoded paths or magic strings — constants centralized

**Tasks to Evaluate:**

1. Check `pyproject.toml` ruff and mypy configuration for enforcement level
2. Sample `src/scylla/e2e/runner.py` and `src/scylla/metrics/grading.py` for type hint completeness
3. Review `src/scylla/config/models.py` Pydantic models for completeness and validation rules
4. Check `src/scylla/adapters/base.py` for proper abstract method enforcement
5. Identify any known mypy errors (referenced as issue #687 — check if tracking exists)

---

### 5. Build & Deployment Readiness (Weight: 10%)

**Grading Criteria:**

- **A (90-100%):** Fully automated, containerized, CI-gated
- **B (80-89%):** Good setup with minor gaps
- **C (70-79%):** Basic setup, some manual steps
- **D (60-69%):** Limited automation
- **F (<60%):** No clear build process

**Success Criteria:**

- `pyproject.toml` defines reproducible environments with pinned versions
- `docker/Dockerfile` + `docker/docker-compose.yml` support containerized agent execution
- `.github/` CI workflows gate on tests and lint
- `.pre-commit-config.yaml` enforces ruff, mypy, yamllint, markdownlint on commit
- `.env.example` documents all required environment variables

**Tasks to Evaluate:**

1. Check `.github/` for CI workflow files and what they gate on
2. Verify `docker/Dockerfile` and `docker/docker-compose.yml` are complete and match `docs/design/container-architecture.md`
3. Check `pyproject.toml` for version pinning strategy
4. Verify `.pre-commit-config.yaml` hooks cover all configured linters
5. Check `.env.example` lists all API keys needed (Anthropic, GitHub, etc.)

---

### 6. Version Control & Collaboration (Weight: 10%)

**Grading Criteria:**

- **A (90-100%):** Clean commit history, enforced workflow, clear branching strategy
- **B (80-89%):** Good practices with minor gaps
- **C (70-79%):** Adequate
- **D (60-69%):** Inconsistent
- **F (<60%):** Poor VCS hygiene

**Success Criteria:**

- Conventional commits enforced (`feat:`, `fix:`, `chore:`, `docs:`, etc.)
- `.gitignore` covers Python artifacts, Docker volumes, API keys, run outputs
- Branch protection on `main` with PR-only merges (documented in CLAUDE.md)
- `CONTRIBUTING.md` present and accurate
- Issue-linked PR workflow followed (Closes #N in PR body)

**Tasks to Evaluate:**

1. Sample last 10 git commits for conventional commit format compliance
2. Check `.gitignore` for coverage of: `__pycache__/`, `.env`, `results/`, `htmlcov/`, `*.pyc`
3. Verify `CONTRIBUTING.md` describes the correct workflow
4. Check `.claude/shared/pr-workflow.md` for completeness
5. Verify current branch naming follows `<issue-number>-description` convention

---

## Analysis Process

### Step 1: Ground Truth Assessment

1. List `src/scylla/` and `tests/unit/` top-level directories to establish actual module coverage
2. Verify CLAUDE.md claims against actual filesystem (especially `agents/` directory)
3. Check `results/` for existing run data to confirm the framework has been executed end-to-end

### Step 2: Deep Dive (by section)

1. **Structure**: Map pipeline layers, identify gaps between CLAUDE.md and reality
2. **Documentation**: Audit README, CLAUDE.md dead links, and docstring sampling
3. **Testing**: Count tests, check fixture completeness, verify sub-test counts
4. **Code Quality**: Sample key modules, check ruff/mypy config enforcement
5. **Build/Deploy**: Check CI workflows, Docker setup, pre-commit hooks
6. **VCS**: Sample commits, check gitignore, verify CONTRIBUTING.md

### Step 3: Scoring

For each section: assign a score with 2-3 specific evidence points (file paths with line numbers where relevant).

---

## Output Template

### Overall Grade: [X]/100 ([Letter Grade])

### Section Grades

| Section | Weight | Raw Score | Weighted |
|---------|--------|-----------|---------|
| Project Structure | 15% | [X]/100 | [X] |
| Documentation | 20% | [X]/100 | [X] |
| Testing | 25% | [X]/100 | [X] |
| Code Quality | 20% | [X]/100 | [X] |
| Build & Deployment | 10% | [X]/100 | [X] |
| Version Control | 10% | [X]/100 | [X] |

### Detailed Feedback by Section

#### [Section Name] — [X]/100

**Strengths:**

- [Specific evidence with file path:line_number]

**Issues:**

- [Specific issue with evidence and recommendation]

### Priority Actions (Top 5)

1. [Most critical — specific file/action]
2. [Second priority]
3. [Third priority]
4. [Fourth priority]
5. [Fifth priority]

### Scylla-Specific Checklist

- [ ] `agents/` directory created with `hierarchy.md` and `delegation-rules.md` (referenced in CLAUDE.md but missing)
- [ ] CLAUDE.md "Current Status" updated from "Research and planning phase" to reflect actual implemented state
- [ ] All 47 test fixtures verified complete (`test.yaml`, `prompt.md`, `expected/criteria.md`, `expected/rubric.yaml`)
- [ ] mypy issue #687 (159 type errors) tracked and progress visible in CI
- [ ] `results/` directory added to `.gitignore` (contains experiment output, not source)
- [ ] Sub-test YAML counts verified: T0:24, T1:10, T2:15, T3:41, T4:14, T5:15, T6:1

---

## Technology-Specific Checklist (Python / AI Research Framework)

- [ ] `pyproject.toml` defines package metadata, entry points, and dependency bounds
- [ ] `uv.lock` locks dependencies for reproducible environments
- [ ] `ruff` configured with appropriate rule sets (not just defaults)
- [ ] `mypy` configured with `strict` or documented relaxations
- [ ] `pytest` configured with `--cov-fail-under` threshold
- [ ] Pydantic v2 models used for all structured config and result data
- [ ] Type hints present on all public function signatures in `src/scylla/`
- [ ] Docstrings present on all public classes and functions
- [ ] No hardcoded API endpoints or model IDs in source (use `config/models/*.yaml`)
- [ ] Docker image supports all agent adapters (Claude Code, Cline, Codex, Opencode)
- [ ] LLM judge system prompt versioned and testable (in `config/judge/system_prompt.md`)
- [ ] Statistical tests documented with assumptions and effect sizes (in `src/scylla/analysis/stats.py`)

---

Analyze this project, Scylla
