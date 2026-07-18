#!/usr/bin/env bash
#
# Create GitHub issues for February 2026 Code Quality Audit findings
# Usage: ./scripts/quality_audit_feb_2026_issues.sh
#

set -euo pipefail

echo "Creating GitHub issues for Code Quality Audit findings..."

# Validate required labels exist
echo "Validating GitHub labels..."
required_labels=("testing" "documentation" "refactor")
for label in "${required_labels[@]}"; do
    if ! gh label list --limit 100 | grep -q "^${label}[[:space:]]"; then
        echo "ERROR: Required label '${label}' not found"
        exit 1
    fi
done

# Track created issue numbers
declare -a issue_numbers=()

echo ""
echo "Creating HIGH priority issues..."

# HIGH-1: Resolve skipped tests and .orig artifacts
echo "Creating issue: Resolve skipped tests and clean up .orig artifacts..."
issue_url=$(gh issue create \
  --title "HIGH: Resolve 4 skipped tests and clean up .orig artifacts" \
  --label "testing" \
  --body "$(cat <<'EOF'
## Objective
Clean up test suite by resolving skipped tests and removing .orig backup artifacts.

## Deliverables
- [ ] Investigate and resolve 4 skipped tests
- [ ] Remove all .orig artifacts from tests directory
- [ ] Update .gitignore to prevent .orig files from being committed

## Success Criteria
- Zero skipped tests in CI
- No .orig files in repository
- .gitignore prevents future .orig commits

## Priority
HIGH - Affects test reliability and repository cleanliness

## Estimated Effort
1-2 hours

## Verification
```bash
# Check for skipped tests
uv run python -m pytest tests/ -v -rs

# Find .orig artifacts
find tests -name "*.orig" -type f
```

## Context
From February 2026 Code Quality Audit (#594)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

# HIGH-2: Configure test coverage thresholds
echo "Creating issue: Configure test coverage thresholds in CI..."
issue_url=$(gh issue create \
  --title "HIGH: Configure test coverage thresholds in CI (75%)" \
  --label "testing" \
  --body "$(cat <<'EOF'
## Objective
Enforce minimum test coverage thresholds to prevent coverage regression.

## Deliverables
- [ ] Create pytest.ini with coverage configuration
- [ ] Set line coverage threshold to 75%
- [ ] Configure coverage report formats (term-missing, html)
- [ ] Add coverage configuration to pyproject.toml

## Success Criteria
- CI fails if coverage drops below 75%
- Coverage reports show missing lines
- HTML coverage report generated for detailed analysis

## Priority
HIGH - Critical for maintaining code quality

## Estimated Effort
1 hour

## Verification
```bash
# Run tests with coverage (should fail if <75%)
uv run python -m pytest tests/ --cov=src/scylla --cov-report=term-missing --cov-fail-under=75
```

## Context
From February 2026 Code Quality Audit (#594)
Current coverage: 70% (too low for a testing framework)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

# HIGH-3: Add mypy type checking to pre-commit
echo "Creating issue: Add mypy type checking to pre-commit hooks..."
issue_url=$(gh issue create \
  --title "HIGH: Add mypy type checking to pre-commit hooks" \
  --label "refactor" \
  --label "testing" \
  --body "$(cat <<'EOF'
## Objective
Add static type checking to pre-commit workflow to catch type errors before commit.

## Deliverables
- [ ] Add mypy hook to .pre-commit-config.yaml
- [ ] Configure mypy to check scylla/ directory
- [ ] Document known type errors (159 errors with 20 codes disabled)
- [ ] Create roadmap issue for mypy strictness improvements

## Success Criteria
- Mypy runs on every commit
- Type errors are caught before code review
- Known errors documented with suppression plan

## Priority
HIGH - Prevents type errors from reaching production

## Estimated Effort
2 hours (including roadmap)

## Implementation
Add to `.pre-commit-config.yaml`:
```yaml
- id: mypy-check-python
  name: Mypy Type Check Python
  entry: uv run mypy scylla/ --strict
  language: system
  files: ^scylla/.*\.py$
  types: [python]
  pass_filenames: false
```

## Verification
```bash
pre-commit run --all-files
```

## Context
From February 2026 Code Quality Audit (#594)
Current status: 159 known type errors, 20 error codes disabled
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

# HIGH-4: Fix duplicate model config names
echo "Creating issue: Fix duplicate model config names..."
issue_url=$(gh issue create \
  --title "HIGH: Fix duplicate model config names (same model_id)" \
  --label "refactor" \
  --body "$(cat <<'EOF'
## Objective
Resolve naming inconsistency in model configuration files where file name and model name don't match.

## Deliverables
- [ ] Fix config/models/claude-opus-4.yaml name field to match file name
- [ ] Or rename file to claude-opus-4-1.yaml to match model_id
- [ ] Add comment explaining version naming convention
- [ ] Verify all model configs follow consistent naming

## Success Criteria
- File names match model names or vice versa
- Naming convention documented
- No duplicate or confusing model identifiers

## Priority
HIGH - Causes configuration confusion

## Estimated Effort
30 minutes

## Options
1. Change `name: "Claude Opus 4.1"` → `name: "Claude Opus 4"` (match file)
2. Rename `claude-opus-4.yaml` → `claude-opus-4-1.yaml` (match model_id)

## Verification
```bash
# Check model config consistency
grep -r "name:" config/models/
```

## Context
From February 2026 Code Quality Audit (#594)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

echo ""
echo "Creating MEDIUM priority issues..."

# MEDIUM-1: Decompose ExperimentRunner.run()
echo "Creating issue: Decompose ExperimentRunner.run() method..."
issue_url=$(gh issue create \
  --title "MEDIUM: Decompose ExperimentRunner.run() (327 lines)" \
  --label "refactor" \
  --body "$(cat <<'EOF'
## Objective
Refactor long ExperimentRunner.run() method into smaller, focused functions.

## Deliverables
- [ ] Extract setup/initialization logic
- [ ] Extract pipeline execution logic
- [ ] Extract results collection logic
- [ ] Extract cleanup/finalization logic
- [ ] Target: <50 lines per function

## Success Criteria
- run() method reduced to orchestration logic only
- Each extracted function has single responsibility
- Tests still pass
- No behavior changes

## Priority
MEDIUM - Code maintainability improvement

## Estimated Effort
4-6 hours

## Verification
```bash
# Check function length
grep -A 330 "def run(" scylla/executor/experiment_runner.py | wc -l
```

## Context
From February 2026 Code Quality Audit (#594)
Current length: 327 lines (target: <50 lines per function)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

# MEDIUM-2: Decompose _save_pipeline_commands()
echo "Creating issue: Decompose _save_pipeline_commands() method..."
issue_url=$(gh issue create \
  --title "MEDIUM: Decompose _save_pipeline_commands() (261 lines)" \
  --label "refactor" \
  --body "$(cat <<'EOF'
## Objective
Refactor long _save_pipeline_commands() method into smaller, focused functions.

## Deliverables
- [ ] Extract command formatting logic
- [ ] Extract file writing logic
- [ ] Extract validation logic
- [ ] Target: <50 lines per function

## Success Criteria
- Method reduced to orchestration logic only
- Each extracted function has single responsibility
- Tests still pass
- No behavior changes

## Priority
MEDIUM - Code maintainability improvement

## Estimated Effort
3-4 hours

## Verification
```bash
# Check function length
grep -A 265 "def _save_pipeline_commands" scylla/executor/experiment_runner.py | wc -l
```

## Context
From February 2026 Code Quality Audit (#594)
Current length: 261 lines (target: <50 lines per function)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

# MEDIUM-3: Add multi-stage Docker build
echo "Creating issue: Add multi-stage Docker build..."
issue_url=$(gh issue create \
  --title "MEDIUM: Add multi-stage Docker build" \
  --label "refactor" \
  --body "$(cat <<'EOF'
## Objective
Convert Dockerfile to multi-stage build to reduce production image size.

## Deliverables
- [ ] Create builder stage for dependencies and build artifacts
- [ ] Create runtime stage with minimal dependencies
- [ ] Target: 30-40% size reduction
- [ ] Verify functionality unchanged

## Success Criteria
- Image size reduced by 30%+
- All functionality works in production image
- Build time acceptable (<5 min)
- Multi-stage pattern documented

## Priority
MEDIUM - Deployment optimization

## Estimated Effort
2-3 hours

## Implementation Pattern
```dockerfile
# Stage 1: Builder
FROM python:3.10-slim AS builder
# Install build deps, build scylla package

# Stage 2: Runtime
FROM python:3.10-slim
# Copy artifacts from builder, minimal dependencies
```

## Verification
```bash
# Build and check size
docker build -f docker/Dockerfile -t scylla:test .
docker images | grep scylla

# Verify functionality
docker run --rm scylla:test --help
```

## Context
From February 2026 Code Quality Audit (#594)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

# MEDIUM-4: Create .env.example
echo "Creating issue: Create .env.example template..."
issue_url=$(gh issue create \
  --title "MEDIUM: Create .env.example and CONTRIBUTING.md" \
  --label "documentation" \
  --body "$(cat <<'EOF'
## Objective
Provide template environment file and contributor guidelines.

## Deliverables
- [ ] Create .env.example with documented variables
- [ ] Document required API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY)
- [ ] Document optional config (TIMEOUT, MAX_COST_USD)
- [ ] Create CONTRIBUTING.md with setup and workflow
- [ ] Verify .env in .gitignore

## Success Criteria
- New contributors can set up environment from .env.example
- CONTRIBUTING.md covers setup, testing, PR workflow
- All environment variables documented

## Priority
MEDIUM - Onboarding improvement

## Estimated Effort
2 hours

## Verification
```bash
# Verify .env.example exists and is documented
cat .env.example

# Verify .env in .gitignore
grep "^\.env$" .gitignore
```

## Context
From February 2026 Code Quality Audit (#594)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

# MEDIUM-5: Enable YAML and markdown linting
echo "Creating issue: Enable YAML and markdown pre-commit hooks..."
issue_url=$(gh issue create \
  --title "MEDIUM: Enable YAML and markdown linting in pre-commit" \
  --label "refactor" \
  --body "$(cat <<'EOF'
## Objective
Enable commented-out YAML and markdown linting hooks in pre-commit configuration.

## Deliverables
- [ ] Uncomment check-yaml hook (lines 67-68)
- [ ] Uncomment markdownlint hook (lines 38-45)
- [ ] Fix any linting errors that surface
- [ ] Update pre-commit hook versions if needed

## Success Criteria
- YAML and markdown linting runs on every commit
- All existing files pass linting
- Documentation updated

## Priority
MEDIUM - Code quality improvement

## Estimated Effort
1-2 hours (includes fixing lint errors)

## Verification
```bash
# Install and run hooks
pre-commit install
pre-commit run --all-files
```

## Context
From February 2026 Code Quality Audit (#594)
Hooks are already configured but commented out
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

echo ""
echo "Creating LOW priority issues..."

# LOW-1: Consolidate RunResult types
echo "Creating issue: Consolidate 5 RunResult types..."
issue_url=$(gh issue create \
  --title "LOW: Consolidate 5 RunResult types (post-Pydantic migration)" \
  --label "refactor" \
  --body "$(cat <<'EOF'
## Objective
Consolidate multiple RunResult type definitions into single canonical version.

## Deliverables
- [ ] Identify all 5 RunResult type locations
- [ ] Determine canonical RunResult definition
- [ ] Migrate all usages to canonical type
- [ ] Remove duplicate definitions
- [ ] Update tests

## Success Criteria
- Single RunResult type definition
- All code uses canonical type
- No duplicate types
- Tests pass

## Priority
LOW - Technical debt cleanup (post-Pydantic migration)

## Estimated Effort
3-4 hours

## Verification
```bash
# Find RunResult definitions
grep -r "class RunResult" scylla/
```

## Context
From February 2026 Code Quality Audit (#594)
Left over from Pydantic v2 migration (commit 38a3df1)
EOF
)")
issue_num=$(echo "$issue_url" | grep -oP '\d+$')
issue_numbers+=("$issue_num")
echo "  Created issue #${issue_num}"

echo ""
echo "All issues created successfully!"
echo ""
echo "Created issues:"
for num in "${issue_numbers[@]}"; do
    echo "  #${num}"
done

echo ""
echo "Updating tracking issue #594..."
gh issue comment 594 --body "$(cat <<EOF
## GitHub Issues Created

Created 10 tracking issues for code quality audit findings:

### HIGH Priority
- #${issue_numbers[0]} - Resolve 4 skipped tests and clean up .orig artifacts
- #${issue_numbers[1]} - Configure test coverage thresholds in CI (75%)
- #${issue_numbers[2]} - Add mypy type checking to pre-commit hooks
- #${issue_numbers[3]} - Fix duplicate model config names (same model_id)

### MEDIUM Priority
- #${issue_numbers[4]} - Decompose ExperimentRunner.run() (327 lines)
- #${issue_numbers[5]} - Decompose _save_pipeline_commands() (261 lines)
- #${issue_numbers[6]} - Add multi-stage Docker build
- #${issue_numbers[7]} - Create .env.example and CONTRIBUTING.md
- #${issue_numbers[8]} - Enable YAML and markdown linting in pre-commit

### LOW Priority
- #${issue_numbers[9]} - Consolidate 5 RunResult types (post-Pydantic migration)

---
🤖 Issues created by [Claude Code](https://claude.com/claude-code)
EOF
)"

echo ""
echo "Done! Check issue #594 for summary."
