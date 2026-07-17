# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scylla is an AI agent testing and optimization framework designed to measure, evaluate, and improve
the performance and cost-efficiency of agentic AI workflows. Named after the mythic trial from Homer's Odyssey,
Scylla represents the challenge of navigating trade-offs between capability gains and operational costs.

**Current Status**: Operational - active research with full evaluation infrastructure, running T0–T6 ablation
studies across 120 YAML subtests with published results and 75%+ test coverage enforced locally and in CI
(combined src/scylla/ + scripts/ floor; src/scylla/ unit coverage is also enforced at 75% in the CI unit step).

**Ecosystem Context**: Part of a 12-repository ecosystem:

| Repository | Role |
|------------|------|
| **AchaeanFleet** | Container images for the agent mesh — base images, Dockerfiles, Compose |
| **Myrmidons** | GitOps agent provisioning — agent definitions as code |
| **Odysseus** | CLI and core platform for agent lifecycle management |
| **ProjectArgus** | Observability — monitoring and metrics |
| **ProjectHephaestus** | Shared Python utilities and foundational tools |
| **ProjectHermes** | Webhook-to-NATS bridge — event ingestion |
| **ProjectKeystone** | DAG execution engine |
| **ProjectMnemosyne** | Skills marketplace — team knowledge sharing |
| **ProjectOdyssey** | Training and capability development for agents |
| **ProjectProteus** | CI/CD pipeline infrastructure |
| **Scylla** | Testing, measurement, and optimization under constraints (this project) |
| **ProjectTelemachy** | Workflow engine |

## Critical Rules - Read First

### Never Push Directly to Main

**The `main` branch is protected. ALL changes MUST go through a pull request.**

**ABSOLUTELY PROHIBITED:**

```bash
git checkout main
git add <files>
git commit -m "changes"
git push origin main  # BLOCKED - Will be rejected by GitHub
```

**Why this is prohibited:**

- Bypasses code review and CI checks
- Can break production immediately
- Violates GitHub branch protection rules
- Makes it impossible to track changes properly

**CORRECT WORKFLOW (Always Use PRs):**

**Never use labels**

```bash
# 1. Create feature branch
git checkout -b <issue-number>-description

# 2. Make changes and commit
git add <files>
git commit -m "type(scope): description"

# 3. Push feature branch
git push -u origin <issue-number>-description

# 4. Create pull request
gh pr create \
  --title "[Type] Brief description" \
  --body "Closes #<issue-number>"

# 5. Enable auto-merge
gh pr merge --auto --squash
```

**Emergency Situations:**

- Even for critical CI fixes, CREATE A PR
- Even for one-line changes, CREATE A PR
- Even if you're fixing your own mistake, CREATE A PR
- NO EXCEPTIONS - Always use the PR workflow

**See Also:**

- PR Best Practices: [PR Workflow](/.claude/shared/pr-workflow.md)

## Quick Links

### Core Guidelines

- [PR Workflow](/.claude/shared/pr-workflow.md)
- [GitHub Issue Workflow](/.claude/shared/github-issue-workflow.md)
- [Common Constraints](/.claude/shared/common-constraints.md)
- [Error Handling](/.claude/shared/error-handling.md)
- [Evaluation Guidelines](/.claude/shared/evaluation-guidelines.md)
- [Metrics Definitions](/.claude/shared/metrics-definitions.md)
- [Thinking Mode Configuration](/.claude/shared/thinking-mode.md) - Disabled by default

### Agent System

- [Agent Configurations](/.claude/agents/) - Evaluation-focused agents

## Working with Agents

This project uses a hierarchical agent system for all development work. **Always use agents** as the primary
method for completing tasks.

### Agent Hierarchy

Agent hierarchy is defined in `.claude/agents/` and `tests/claude-code/shared/agents/`:

- 6-level hierarchy (L0 Chief Evaluator → L5 Junior Engineers)
- Model assignments (Opus, Sonnet, Haiku)
- Specialized evaluation and benchmarking agents

### Key Agent Principles

1. **Always start with orchestrators** for new evaluation work
1. **All outputs** must be posted as comments on the GitHub issue
1. **Link all PRs** to issues using `gh pr create --issue <number>` or "Closes #123" in description
1. **Minimal changes only** - smallest change that solves the problem
1. **No scope creep** - focus only on issue requirements
1. **Reply to each review comment** with `Fixed - [brief description]`
1. **Delegate to skills** - Use "Use the X skill to..." pattern for automation

### Key Development Principles

1. KISS - *K*eep *I*t *S*imple *S*tupid -> Don't add complexity when a simpler solution works
1. YAGNI - *Y*ou *A*in't *G*onna *N*eed *I*t -> Don't add things until they are required
1. TDD - *T*est *D*riven *D*evelopment -> Write tests to drive the implementation
1. DRY - *D*on't *R*epeat *Y*ourself -> Don't duplicate functionality, data structures, or algorithms
1. SOLID - *S**O**L**I**D* ->
   . Single Responsibility
   . Open-Closed
   . Liskov Substitution
   . Interface Segregation
   . Dependency Inversion
1. Modularity - Develop independent modules through well defined interfaces
1. POLA - *P*rinciple *O*f *L*east *A*stonishment - Create intuitive and predictable interfaces

Relevant links:

- [Core Principles of Software Development](<https://softjourn.com/insights/core-principles-of-software-development>)
- [7 Common Programming Principles](<https://www.geeksforgeeks.org/blogs/7-common-programming-principles-that-every-developer-must-follow/>)
- [Software Development Principles](<https://coderower.com/blogs/software-development-principles-software-engineering>)
- [Clean Coding Principles](<https://www.pullchecklist.com/posts/clean-coding-principles>)

### Documentation Rules

- **Issue-specific outputs**: Post as comments on the GitHub issue using `gh issue comment <number>`
- **Developer documentation**: `/docs/dev/` (architectural decisions, design docs)
- **Agent guides**: `/.claude/agents/` (configurations, roles, capabilities)
- **Never duplicate** documentation across locations - link instead
- See `.claude/shared/github-issue-workflow.md` for GitHub issue read/write patterns

## Testing Tiers (Ablation Study Framework)

Scylla benchmarks AI agent architectures across 7 testing tiers with 120 sub-tests:

| Tier | Name | Sub-tests | Description |
|------|------|-----------|-------------|
| T0 | Prompts | 24 | System prompt ablation (empty → full CLAUDE.md) |
| T1 | Skills | 10 | Domain expertise via installed skills by category |
| T2 | Tooling | 15 | External tools and MCP servers |
| T3 | Delegation | 41 | Flat multi-agent with specialist agents |
| T4 | Hierarchy | 14 | Nested orchestration with orchestrator agents (7 hierarchy + 7 agent teams) |
| T5 | Hybrid | 15 | Best combinations and permutations |
| T6 | Super | 1 | Everything enabled at maximum capability |

### Evaluation Protocol

Each tier is evaluated against:

1. **Quality Metrics**: Pass-Rate, Implementation Rate, Fine-Grained Progress Rate
2. **Economic Metrics**: Cost-of-Pass (CoP), token distribution, component-level costs
3. **Process Metrics**: Latency, consistency, strategic drift

### Partial-Failure Semantics

When multiple tiers run in parallel, a tier failure does **not** abort the experiment. The experiment
continues with remaining tiers and can reach `experiment_state=COMPLETE` even if some tiers are in
`FAILED` state. This is intentional — partial results are preserved and reported.

**Operators must check `tier_states` in the checkpoint, not just `experiment_state`, to determine
whether all tiers succeeded.** A complete experiment may contain a mix of `complete` and `failed`
tier states.

## Core Metrics

Scylla evaluates agent performance across three metric categories:

1. **Quality Metrics**: Pass-Rate, Implementation Rate, Fine-Grained Progress
2. **Economic Metrics**: Cost-of-Pass (CoP), Token Distribution, Change Fail Percentage
3. **Process Metrics**: Latency, Strategic Drift, Ablation Score

**For complete metric definitions, formulas, and calculation methods, see:**

- [Metrics Definitions](/.claude/shared/metrics-definitions.md) - Authoritative reference
- [Research Methodology](/docs/research.md) - Context and usage

## Language Preference

### Python - Implementation Language

**Python 3.10+** is the implementation language for all Scylla code:

- Evaluation harnesses and benchmark runners
- Metrics calculation and collection
- Statistical analysis and data processing
- Agent execution and orchestration
- Automation scripts and utilities

### Configuration Files

- YAML for experiment configurations
- JSON for API schemas and tool definitions
- Markdown for documentation and reports

### Python Development Guidelines

**Current Version**: Python 3.10+

**Key Principles**:

- Use type hints for all function signatures
- Leverage dataclasses and Pydantic models for structured data
- Follow PEP 8 style guidelines (enforced by pre-commit hooks)
- Write comprehensive docstrings for public APIs
- Use pytest for all testing with parametrized tests where appropriate

## Claude 4 & Claude Code Optimization

### Extended Thinking

**When to Use Extended Thinking**: Use for complex reasoning tasks:

- Designing evaluation protocols and experiment methodology
- Analyzing benchmark results and identifying patterns
- Planning multi-tier comparison studies
- Debugging complex evaluation failures
- Statistical analysis and interpretation

**When NOT to Use Extended Thinking**:

- Simple metric calculations
- Boilerplate test generation
- Straightforward data collection
- Well-defined configuration tasks

### Thinking Budget Guidelines

| Task Type | Budget | Examples | Rationale |
|-----------|--------|----------|-----------|
| **Simple** | None | Update config | Mechanical changes |
| **Standard** | 5K-10K | Add test case | Well-defined |
| **Complex** | 10K-20K | Design experiment | Dependencies |
| **Analysis** | 20K-50K | Interpret results | Deep analysis |
| **Research** | 50K+ | New methodology | Novel design |

### Agent Skills vs Sub-Agents

**Decision Tree**: Choose between skills and sub-agents based on task characteristics:

```text
Is the task well-defined with predictable steps?
+-- YES -> Use an Agent Skill
|   +-- Is it a GitHub operation? -> Use gh-* skills
|   +-- Is it data collection? -> Use metrics-* skills
|   +-- Is it a CI/CD task? -> Use ci-* skills
|   +-- Is it report generation? -> Use report-* skills
|
+-- NO -> Use a Sub-Agent
    +-- Does it require exploration/discovery? -> Use sub-agent
    +-- Does it need adaptive decision-making? -> Use sub-agent
    +-- Is the workflow dynamic/context-dependent? -> Use sub-agent
    +-- Does it need extended thinking? -> Use sub-agent
```

### Output Style Guidelines

#### Code References

**DO**: Use absolute file paths with line numbers when referencing code:

```markdown
GOOD: Updated /home/user/Scylla/src/scylla/metrics/grading.py:45-52

BAD: Updated grading.py (ambiguous - which file?)
```

#### Benchmark Results

**DO**: Use structured tables for benchmark results:

```markdown
## Benchmark Results: Task-X

| Tier | Pass-Rate | CoP ($) | Latency (s) |
|------|-----------|---------|-------------|
| T0   | 0.23      | 4.35    | 12.3        |
| T1   | 0.45      | 2.22    | 15.7        |
| T2   | 0.67      | 1.49    | 18.2        |
```

## Delegation to Agent Hub

.claude/ is the centralized location for agent configurations. Sub-agents reference
`.claude/agents/*.md` for roles and capabilities.

### Skills and Knowledge Sharing

Skills live in two places. Pick the right location based on **scope**, not convenience.

**Local skills** (in this repo) — for Scylla-specific knowledge:

- Location: `.claude-plugin/skills/<name>/SKILL.md` (39 skills) and `skills/<name>/SKILL.md` (1 skill)
- Use when the skill is tightly coupled to Scylla's domain:
  - Evaluation tier semantics (T0–T6 ablation patterns)
  - Repo-specific config schemas (pixi, model configs, judge prompts)
  - Scylla automation (e2e runner internals, batch result analysis)
  - Fixes to this repo's CI, pre-commit hooks, or doc policies
- Examples: `doc-contradiction-resolution`, `config-default-model-drift`, `wired-runner-fixture`

**Mnemosyne skills** (in `HomericIntelligence/ProjectMnemosyne`) — for cross-project reusable patterns:

- Location: `HomericIntelligence/ProjectMnemosyne/skills/<name>.md` (flat format)
- Use when the skill benefits other HomericIntelligence repos:
  - Language/tooling techniques (Python, mypy, pixi, pre-commit) that apply broadly
  - Generic debugging patterns (e.g., Pydantic None-coercion, rebase conflict resolution)
  - CI/CD patterns reusable across the 12-repo ecosystem
  - Cross-cutting research methodology
- Search: `/mnemosyne:advise` to discover existing Mnemosyne skills

**When `/retrospective` or `/learn` captures a session learning**, decide local-vs-Mnemosyne with the
criteria above. If the lesson is reusable across repos, push to Mnemosyne:

```bash
# Clone if needed
MNEMOSYNE_DIR="build/$$/ProjectMnemosyne"
if [ ! -d "$MNEMOSYNE_DIR" ]; then
  mkdir -p "build/$$"
  gh repo clone HomericIntelligence/ProjectMnemosyne "$MNEMOSYNE_DIR"
fi

# Create PR in ProjectMnemosyne
cd "$MNEMOSYNE_DIR"
git checkout -b skill/{category}/{name} origin/main
# ... create skill files ...
git push -u origin skill/{category}/{name}
gh pr create --title "feat(skills): Add {name}"
```

If the lesson is Scylla-specific, add it locally under `.claude-plugin/skills/<name>/SKILL.md`.

**When in doubt**, prefer Mnemosyne — broader reach, easier discovery via `/mnemosyne:advise`.

### Shared Reference Files

All agents reference these shared files to avoid duplication:

| File | Purpose |
|------|---------|
| `.claude/shared/common-constraints.md` | Minimal changes principle, scope discipline |
| `.claude/shared/pr-workflow.md` | PR creation, verification, review responses |
| `.claude/shared/github-issue-workflow.md` | Issue read/write patterns |
| `.claude/shared/error-handling.md` | Retry strategy, timeout handling, escalation |
| `.claude/shared/evaluation-guidelines.md` | Evaluation methodology and best practices |
| `.claude/shared/metrics-definitions.md` | Complete metrics definitions and formulas |

## Environment Setup

This project uses Pixi for environment management with Python 3.10+:

```bash
# Pixi is already configured - dependencies are in pixi.toml

# Run Python tests
pixi run python -m pytest tests/ -v

# Run pre-commit hooks (includes black, ruff, mypy)
pre-commit run --all-files
```

## Common Commands

### Quick Start (justfile)

The justfile provides a convenient interface to all development tasks:

```bash
just              # List all available recipes
just test         # Run pytest
just lint         # Run ruff check
just format       # Run ruff format
just typecheck    # Run mypy
just pre-commit   # Run all pre-commit hooks
just ci-all       # Run full CI suite in container
```

### Development Workflows

**Pull Requests**: See [pr-workflow.md](/.claude/shared/pr-workflow.md)

- Creating PRs with `gh pr create --body "Closes #<number>"`
- Responding to review comments
- Post-merge cleanup

**GitHub Issues**: See [github-issue-workflow.md](/.claude/shared/github-issue-workflow.md)

- Read context: `gh issue view <number> --comments`
- Post updates: `gh issue comment <number> --body "..."`

**Git Workflow**: Feature branch -> PR -> Auto-merge (never push to main)

### Pre-commit Hooks

Pre-commit hooks automatically check code quality before commits.

```bash
# Install pre-commit hooks (one-time setup)
pre-commit install

# Run hooks manually on all files
pre-commit run --all-files

# NEVER skip hooks with --no-verify
# If a hook fails, fix the code instead
```

**--no-verify is ABSOLUTELY PROHIBITED**. No exceptions.

**No CHANGELOG.md.** Do not create, edit, or file issues against `CHANGELOG.md`. Release notes are generated from commits at release time via `gh release create --generate-notes`. Audit reports MUST NOT flag missing/stale changelog entries.

**After any `pyproject.toml` or `pixi.toml` change**, regenerate the lock file before committing:

```bash
pixi install  # regenerates pixi.lock
git add pixi.lock
```

**Before pushing from a worktree** (auto-impl agents), always run:

```bash
pre-commit run --all-files
```

Skipping this step is the primary cause of CI failures on auto-impl branches.

## Repository Architecture

### Project Structure

```text
Scylla/
+-- config/                      # Configuration files
|   +-- models/                  # Model configurations (YAML)
+-- docker/                      # Docker configurations
+-- docs/
|   +-- research.md              # Research methodology
|   +-- dev/                     # Developer documentation
+-- schemas/                     # JSON schemas
+-- src/                         # Python source root (src-layout)
|   +-- scylla/                  # Python source code
|       +-- adapters/            # CLI adapters (.py)
|       +-- analysis/            # Statistical analysis (.py)
|       +-- cli/                 # CLI interface (.py)
|       +-- config/              # Configuration (.py)
|       +-- core/                # Core types (.py)
|       +-- discovery/           # Resource discovery (.py)
|       +-- e2e/                 # E2E testing framework + EvalOrchestrator (.py)
|       +-- executor/            # Execution engine (.py)
|       +-- judge/               # LLM judge system (.py)
|       +-- metrics/             # Metrics calculation (.py)
|       +-- nats/                # NATS bridge integration (.py)
|       +-- reporting/           # Report generation (.py)
|       +-- utils/               # Utility functions (.py)
+-- scripts/                     # Python automation scripts
+-- tests/                       # Python test suite (pytest)
+-- .claude/                     # Operational configurations
|   +-- agents/                  # Agent configs
|   +-- shared/                  # Shared reference files
+-- pixi.toml                    # Pixi configuration
+-- CLAUDE.md                    # This file
+-- README.md                    # Project overview
```

### 4-Phase Development Workflow

Every component follows a hierarchical workflow with clear dependencies:

**Workflow**: Plan -> [Test | Implementation] -> Review

1. **Plan** - Design evaluation methodology and experiment protocols (MUST complete first)
1. **Test** - Write test harnesses and validation (parallel after Plan)
1. **Implementation** - Build evaluation infrastructure (parallel after Plan)
1. **Review** - Validate results and document findings (runs after parallel phases complete)

## GitHub Issue Structure

All planning is done through GitHub issues with clear structure:

### Issue Body Format

```markdown
## Objective
Brief description (2-3 sentences)

## Deliverables
- [ ] Deliverable 1
- [ ] Deliverable 2

## Success Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Dependencies
- Depends on #<parent-issue>
- Related: #<sibling-issue>

## Notes
Additional context
```

### Issue Labels

- `research` - Research and methodology
- `evaluation` - Evaluation infrastructure
- `metrics` - Metrics implementation
- `benchmark` - Benchmark definitions
- `analysis` - Statistical analysis
- `documentation` - Documentation work

## Git Workflow

### Branch Naming

- `main` - Production branch (protected, requires PR)
- `<issue-number>-<description>` - Feature/fix branches (e.g., `42-add-cop-metric`)

### Development Workflow

**IMPORTANT:** The `main` branch is protected. All changes must go through a pull request.

1. **Create a feature branch:**

   ```bash
   git checkout -b <issue-number>-<description>
   ```

1. **Make your changes and commit:**

   ```bash
   git add <files>
   git commit -m "type(scope): Brief description"
   ```

1. **Push the feature branch:**

   ```bash
   git push -u origin <branch-name>
   ```

1. **Create pull request:**

   ```bash
   gh pr create \
     --title "[Type] Brief description" \
     --body "Closes #<issue-number>"
   ```

1. **Enable auto-merge:**

   ```bash
   gh pr merge --auto --squash
   ```

   **Always enable auto-merge** so PRs merge automatically once CI passes.

## Commit Message Format

Follow conventional commits:

```text
feat(metrics): Add Cost-of-Pass calculation
fix(evaluation): Correct token counting logic
docs(readme): Update benchmark instructions
refactor(analysis): Standardize statistical tests
```

## Troubleshooting

### GitHub CLI Issues

```bash
# Check authentication
gh auth status

# If missing scopes, refresh authentication
gh auth refresh -h github.com
```

### Python Type Checking

- Run mypy: `pre-commit run mypy --all-files`
- Check Python version: `python3 --version` (requires 3.10+)
- Review type hints in function signatures

### Script Errors

- Verify Python version: `python3 --version` (requires 3.10+)
- Check file permissions
- Review error logs

## Important Files

- `docs/research.md` - Research methodology and evaluation framework
- `README.md` - Main project documentation
- `.claude/shared/github-issue-workflow.md` - GitHub issue read/write patterns
