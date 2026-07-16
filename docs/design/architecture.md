# Scylla Architecture

This document provides comprehensive architecture documentation for the Scylla evaluation framework. It describes the three-phase execution model, component relationships, data flow, and key design decisions.

---

## 1. Overview

Scylla is an AI agent testing and optimization framework designed to measure, evaluate, and improve the performance and cost-efficiency of agentic AI workflows. Named after the mythic trial from Homer's Odyssey, Scylla represents the challenge of navigating trade-offs between capability gains and operational costs.

### Core Purpose

- **Measure**: Quantify agent performance across multiple tiers of complexity
- **Evaluate**: Use Claude + Opus 4.5 as a semantic judge for validation
- **Optimize**: Identify the most cost-effective architectural tier for each task

### Ecosystem Context

Scylla is part of a 12-repository ecosystem:

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

### Framework Characteristics

- **Language**: Python only (for framework implementation)
- **Testing Scope**: Can evaluate agents in any language
- **Core Metric**: Cost-of-Pass (CoP)
- **Validation**: LLM-as-a-Judge paradigm using Claude + Opus 4.5

---

## 2. Core Principles

### 2.1 Tests as Data

Tests are pure configuration (YAML + Markdown) with no embedded code. This separation enables:

- **Portability**: Test cases work across different adapters and models
- **Reproducibility**: Configuration-based tests are deterministic
- **Extensibility**: New test cases require no framework changes

**Test Case Structure**:

```
tests/<test-id>/
    test.yaml         # Test definition (repo, hash, timeout)
    prompt.md         # Agent prompt
    expected/
        criteria.md   # Success criteria
        rubric.yaml   # Scoring rubric
```

### 2.2 Claude as Judge

The framework uses Claude + Opus 4.5 as an LLM-as-a-Judge for semantic evaluation:

- **3-run Consensus**: Each judgment runs 3 times with confidence-weighted averaging
- **10 Evaluation Categories**: Weighted rubric covering functional correctness to code quality
- **Separate Container**: Judge runs in isolated container from the agent under test

**Evaluation Categories** (Total Weight: 9.5):

| Category | Weight | Description |
|----------|--------|-------------|
| Functional Correctness | 2.0 | Does the solution work as intended? |
| Completeness | 1.5 | Are all requirements addressed? |
| Code Quality | 1.0 | Readability, maintainability, best practices |
| Simplicity | 1.0 | Prefer simple working solutions over complex ones |
| Lack of Duplication | 0.5 | DRY principle adherence |
| Clarity | 1.0 | Clear, understandable implementation |
| Documentation | 0.5 | Appropriate comments and documentation |
| Architectural Cleanliness | 0.5 | Clean separation of concerns |
| Efficiency | 0.5 | Resource usage, performance considerations |
| Cleanup Script Quality | 1.0 | Proper cleanup/teardown script creation |

### 2.3 9-Run Statistical Analysis

Each tier runs 9 times per test case for statistical validity:

- **Statistical Validity**: Sufficient sample size for meaningful confidence intervals
- **Variance Measurement**: Captures consistency/reliability of each tier
- **Cross-Tier Comparison**: Enables rigorous statistical tests (t-test, ANOVA)

---

## 3. System Architecture Diagram

```
+------------------------------------------------------------------------------+
|                          SCYLLA ARCHITECTURE                           |
+------------------------------------------------------------------------------+

    +---------------+                                      +------------------+
    |  TEST CASES   |                                      |     OUTPUTS      |
    |    (Data)     |                                      |    (Results)     |
    |               |                                      |                  |
    | - test.yaml   |                                      | - judgment.json  |
    | - prompt.md   |                                      | - result.json    |
    | - criteria.md |                                      | - summary.json   |
    | - rubric.yaml |                                      | - report.md      |
    +-------+-------+                                      +--------+---------+
            |                                                       ^
            |                                                       |
            v                                                       |
    +----------------------------------------------------------------------+
    |                         FRAMEWORK (Python)                            |
    |                                                                       |
    |  PHASE 1: EXECUTE      PHASE 2: JUDGE        PHASE 3: REPORT         |
    |  +---------------+     +---------------+     +---------------+        |
    |  |   Executor    |---->|    Judge      |---->|   Reporter    |        |
    |  |               |     |               |     |               |        |
    |  | - Workspace   |     | - 3-run       |     | - Statistics  |        |
    |  | - Docker      |     |   consensus   |     | - Aggregation |        |
    |  | - Adapter     |     | - Rubric      |     | - Markdown    |        |
    |  | - 9 runs/tier |     |   scoring     |     |   reports     |        |
    |  | - Agamemnon   |     |               |     |               |        |
    |  |   (optional)  |     |               |     |               |        |
    |  +-------+-------+     +-------+-------+     +---------------+        |
    |          |                     |                                      |
    |          v                     v                                      |
    |  +---------------+     +---------------+     +---------------+        |
    |  |   ADAPTERS    |     |  OPUS 4.5     |     |   METRICS     |        |
    |  |               |     |               |     |               |        |
    |  | - Claude Code |     |  Judge        |     | - Pass-Rate   |        |
    |  | - Codex       |     |  Container    |     | - CoP         |        |
    |  | - Cline       |     |               |     | - Latency     |        |
    |  | - OpenCode    |     |               |     | - R_Prog      |        |
    |  | - Goose       |     |               |     |               |        |
    |  +---------------+     +---------------+     +---------------+        |
    |          :                                                            |
    |          : (optional)                                                 |
    |          v                                                            |
    |  +- - - - - - - -+                                                   |
    |  : AGAMEMNON API :                                                   |
    |  :               :                                                   |
    |  : - Health      :                                                   |
    |  : - Inject      :                                                   |
    |  : - Clear       :                                                   |
    |  : - Agents      :                                                   |
    |  +- - - - - - - -+                                                   |
    |                                                                       |
    +----------------------------------------------------------------------+
```

---

## 4. Components

### 4.1 Test Cases (Data)

Test cases are pure configuration files containing no executable code.

**Location**: `tests/<test-id>/`

**Files**:

| File | Purpose |
|------|---------|
| `test.yaml` | Test definition (repo URL, git hash, timeout) |
| `prompt.md` | Agent prompt describing the task |
| `expected/criteria.md` | Human-readable success criteria |
| `expected/rubric.yaml` | Weighted scoring rubric for judge |

**Example** (`tests/001-justfile-to-makefile/test.yaml`):

```yaml
id: "001-justfile-to-makefile"
name: "Convert Justfile to Makefile"
description: |
  Convert ProjectOdyssey's justfile to an equivalent Makefile.

source:
  repo: "https://github.com/mvillmow/ProjectOdyssey"
  hash: "ce739d4aa328f1c0815b33e2812c4b889868b740"

task:
  prompt_file: "prompt.md"
  timeout_seconds: 3600

validation:
  criteria_file: "expected/criteria.md"
  rubric_file: "expected/rubric.yaml"
```

### 4.2 Executor

The Executor orchestrates test execution across tiers and runs.

**Location**: `src/scylla/executor/`

**Responsibilities**:

- **Workspace Management** (`workspace.py`): Clone repos, manage git state
- **Docker Orchestration** (`docker.py`): Create isolated containers per run
- **Tier Configuration** (`tier_config.py`): Load and apply tier-specific prompts
- **Run Coordination** (`runner.py`): Execute 9 runs per tier, capture logs

**Execution Matrix**:

```
Test: 001-justfile-to-makefile
    Tier: T0 (Vanilla)
        Run 01 [container-001-t0-r01]
        Run 02 [container-001-t0-r02]
        ... (9 runs)
    Tier: T1 (Prompted)
        ... (9 runs)
    Tier: T2 (Tooling)
        ... (9 runs)
    Tier: T3+ (Tooling)
        ... (9 runs)

Total: 36 runs per test x N adapters
```

### 4.3 Adapters

Adapters provide a unified interface for different agent CLI tools.

**Location**: `src/scylla/adapters/`

**Interface**:

```python
class BaseAdapter:
    def execute(self, prompt: str, workspace: Path, tier: Tier) -> ExecutionResult:
        """Run the agent with given prompt in workspace."""
        ...

    def get_token_usage(self) -> TokenUsage:
        """Return token consumption for cost calculation."""
        ...
```

**Implementations**:

| Adapter | Agent Tool | Status |
|---------|------------|--------|
| `ClaudeCodeAdapter` | Claude Code CLI | Implemented |
| `CodexAdapter` | OpenAI Codex CLI | Implemented |
| `ClineAdapter` | Cline | Implemented |
| `OpenCodeAdapter` | OpenCode | Implemented |
| `GooseAdapter` | Goose CLI | Implemented |

### 4.4 Judge

The Judge evaluates agent outputs using Claude + Opus 4.5 with a two-layer prompt architecture.

**Location**: `src/scylla/judge/`

**Components**:

- **Rubric Parser** (`rubric.py`): Parse `rubric.yaml` into evaluation criteria
- **Judge Prompts** (`prompts.py`): Consolidated prompt generation
  - `JUDGE_SYSTEM_PROMPT_FILE`: Path to global system prompt (`config/judge/system_prompt.md`)
  - `build_task_prompt()`: Generates task-specific evaluation context
  - `build_judge_prompt()`: Legacy wrapper for backward compatibility
- **Evaluator** (`evaluator.py`): Invoke Opus 4.5 for judgment
- **Judgment Parser** (`parser.py`): Parse judgment JSON from LLM response

**Prompt Architecture**:

1. **Global System Prompt**: `config/judge/system_prompt.md` (evaluation methodology, grading scale reference at `docs/design/grading-scale.md`)
2. **Task-Specific Prompt**: Generated dynamically with rubric, agent output, workspace state, and pipeline results

**3-Run Consensus Process**:

```
Execution Output
        |
        v
+------------------+
| Rubric Parser    |-----> Evaluation Criteria
+------------------+
        |
        v
+------------------+     +------------------+
| Judge Run 1      |     | Judge Run 2      |
| (Opus 4.5)       |     | (Opus 4.5)       |
+--------+---------+     +--------+---------+
         |                        |
         v                        v
    Judgment 1               Judgment 2
         |                        |
         +----------+-------------+
                    |
                    v
            +------------------+
            | Judge Run 3      |  (if disagreement)
            | (Opus 4.5)       |
            +--------+---------+
                     |
                     v
         +----------------------+
         | Confidence-Weighted  |
         | Averaging            |
         +----------+-----------+
                    |
                    v
             Final Judgment
```

### 4.5 Metrics

The Metrics component calculates quality, economic, and process metrics.

**Location**: `src/scylla/metrics/`

**Quality Metrics**:

| Metric | Formula | Description | Status |
|--------|---------|-------------|--------|
| Pass-Rate | `correct / total` | Proportion of correct solutions | Implemented |
| Impl-Rate | `satisfied / total_requirements` | Requirement satisfaction | Implemented |
| R_Prog | `achieved_steps / expected_steps` | Fine-grained progress | **Excluded** |
| Consistency | `1 - (std / mean)` | Output stability | Implemented |

**Economic Metrics**:

| Metric | Formula | Description |
|--------|---------|-------------|
| Cost-of-Pass (CoP) | `total_cost / pass_rate` | Expected cost per correct solution |
| Frontier CoP | `min(CoP across tiers)` | Best achievable cost |
| Token Distribution | Component breakdown | Cost attribution |

**Process Metrics**:

| Metric | Description |
|--------|-------------|
| Latency | Time from query to resolution |
| Strategic Drift | Goal coherence over multi-step tasks |

### 4.6 Reporter

The Reporter generates output artifacts from evaluation results.

**Location**: `src/scylla/reporting/`

**Output Files**:

| File | Purpose |
|------|---------|
| `result.json` | Individual run results |
| `summary.json` | Aggregated statistics across runs |
| `scorecard.json` | Tier comparison scorecard |
| `report.md` | Human-readable Markdown report |

### 4.7 Agamemnon Chaos Client (Optional)

The Agamemnon Chaos Client provides optional fault-injection capabilities for
the Odysseus agent mesh. It is fully opt-in and disabled by default.
Chaos injection is managed by ProjectCharybdis per ADR-006.

**Location**: `scylla/agamemnon/`

**Module Structure**:

| File | Purpose |
|------|---------|
| `client.py` | Synchronous HTTP client (`AgamemnonClient`) |
| `models.py` | Configuration and data models |
| `errors.py` | Exception hierarchy |

**Client Interface** (`AgamemnonClient`):

| Method | Return Type | Description |
|--------|-------------|-------------|
| `health_check()` | `HealthResponse \| None` | `GET /v1/health`; `None` if unreachable |
| `inject_failure(spec)` | `InjectionResult` | `POST /v1/chaos/inject` — inject a failure into an agent |
| `clear_failure(injection_id)` | `None` | `DELETE /v1/chaos/inject/{id}` — remove an injected failure |
| `list_agents()` | `list[dict[str, Any]]` | `GET /v1/agents` — list all registered agents |

**Configuration** (`AgamemnonConfig`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base_url` | `str` | `http://localhost:8080` | Agamemnon REST API base URL |
| `enabled` | `bool` | `False` | Whether integration is active |
| `timeout_seconds` | `int` | `10` | Timeout for mutation requests (1-300) |
| `health_check_timeout_seconds` | `int` | `5` | Timeout for health checks (1-60) |
| `max_retries` | `int` | `3` | Retry attempts for transient failures (0-10) |

**Data Models**:

| Model | Key Fields | Description |
|-------|------------|-------------|
| `FailureSpec` | `agent_id`, `failure_type`, `duration_seconds`, `parameters` | Describes a failure to inject |
| `HealthResponse` | `status`, `version` | API health status |
| `InjectionResult` | `injection_id`, `status` | Result of a successful injection |

**Error Hierarchy**:

```
AgamemnonError (base)
├── AgamemnonConnectionError   — network failures, timeouts
└── AgamemnonAPIError          — non-2xx HTTP responses (status_code, response_body)
```

**Retry Strategy**: Transient failures (connection errors, timeouts,
HTTP 502/503/504) are retried with exponential backoff (1s base, 2×
factor, up to `max_retries` attempts).

**Design Properties**:

- **Opt-in**: Disabled by default; zero behavioral change when unconfigured
- **Graceful degradation**: All stages log warnings and continue on API errors
- **Resumable**: Injection ID persisted to `agamemnon_injection.json` for
  checkpoint/resume support

---

## 5. Data Flow

### 5.1 Execution Phase

```
Test Case (YAML)
        |
        v
+------------------+
| Config Loader    |-----> Test configuration
+------------------+
        |
        v
+------------------+
| Workspace Setup  |-----> Git clone to isolated directory
+------------------+
        |
        v
+------------------+
| Docker Container |-----> Isolated execution environment
+------------------+
        |
        v
+- - - - - - - - - +
: Inject Failure   :-----> (optional) Agamemnon chaos fault injection
: [REPLAY_GENERATED]:      Persists agamemnon_injection.json
+- - - - - - - - - +
        |
        v
+------------------+
| Adapter          |-----> Agent invocation (9 runs per tier)
+------------------+
        |
        v
+- - - - - - - - - +
: Clear Failure    :-----> (optional) Agamemnon chaos fault clearing
: [AGENT_COMPLETE]:        Deletes agamemnon_injection.json
+- - - - - - - - - +
        |
        v
+------------------+
| Log Capture      |-----> stdout, stderr, metrics
+------------------+
        |
        v
    workspace/
    logs/
    raw_metrics/
```

**Input**: `test.yaml`, tier definitions from `tests/claude-code/shared/tiers.yaml`

**Process**: Docker isolation, optional chaos fault injection via Agamemnon,
adapter invocation, failure clearing, metric collection

**Output**: Modified workspace, execution logs, raw metrics

**Agamemnon Stages** (optional, dashed boxes above):

The `stage_inject_failure` and `stage_clear_failure` stages bracket the
adapter invocation. They are no-ops when Agamemnon is unconfigured or
disabled. On API errors, both stages log warnings and continue
(graceful degradation). The injection ID is persisted to
`agamemnon_injection.json` in the run directory to support
checkpoint/resume — if a run resumes between `REPLAY_GENERATED` and
`AGENT_COMPLETE`, the injection ID is restored from disk so the
failure can be properly cleared.

### 5.2 Judgment Phase

```
Execution Output (workspace contents)
        |
        v
+------------------+
| Criteria Loader  |-----> criteria.md
+------------------+
        |
        v
+------------------+
| Rubric Parser    |-----> rubric.yaml -> Evaluation criteria
+------------------+
        |
        v
+------------------+
| Judge Prompt     |-----> Fill template with workspace + rubric
| Template         |
+------------------+
        |
        v
+------------------+
| Opus 4.5         |-----> LLM evaluation (3 runs)
| Evaluator        |
+------------------+
        |
        v
+------------------+
| Consensus        |-----> Confidence-weighted averaging
| Engine           |
+------------------+
        |
        v
    judgment.json
```

**Input**: Workspace contents, `criteria.md`, `rubric.yaml`

**Process**: 3-run consensus evaluation, disagreement handling

**Output**: `judgment.json` with scores and rationale

### 5.3 Reporting Phase

```
All Judgments (across runs/tiers)
        |
        v
+------------------+
| Statistical      |-----> Mean, std, CI for each metric
| Aggregation      |
+------------------+
        |
        v
+------------------+
| Cross-Tier       |-----> Tier comparison, Frontier CoP
| Analysis         |
+------------------+
        |
        v
+------------------+
| Report Generator |-----> Markdown, JSON outputs
+------------------+
        |
        v
    result.json
    summary.json
    scorecard.json
    report.md
```

**Input**: All judgments from all runs and tiers

**Process**: Statistical calculations, cross-tier analysis

**Output**: Structured reports for analysis and visualization

---

## 6. Directory Structure

```
Scylla/
    tests/                              # TEST CASES (Pure Data)
        <test-id>/
            test.yaml                   # Test definition
            prompt.md                   # Agent prompt
            expected/
                criteria.md             # Success criteria
                rubric.yaml             # Scoring rubric

    config/
        defaults.yaml                   # Global defaults
        models/                         # Model-specific configs
        tiers/                          # Tier definitions (T0-T6)
            tiers.yaml                  # Master tier definitions
            t0-prompts.md               # T0 prompt template
            t1-skills.md                # T1 prompt template
            t2-tooling.md               # T2 prompt template
            t3-delegation.md            # T3 prompt template
            t4-hierarchy.md             # T4 prompt template
            t5-hybrid.md                # T5 prompt template
            t6-super.md                 # T6 prompt template

    src/
        scylla/
            __init__.py
            cli.py                          # Command-line interface
            executor/                       # Test execution
                runner.py                   # Main test runner
                workspace.py                # Git clone management
                docker.py                   # Container orchestration
                tier_config.py              # Tier configuration
            adapters/                       # Agent CLI adapters
                base.py                     # Abstract base class
                claude_code.py              # Claude Code adapter
                openai_codex.py             # OpenAI Codex adapter
                cline.py                    # Cline adapter
                opencode.py                 # OpenCode adapter
                goose.py                    # Goose adapter
            agamemnon/                      # Chaos fault injection client (optional)
                client.py                   # Synchronous HTTP client
                models.py                   # AgamemnonConfig, FailureSpec, etc.
                errors.py                   # AgamemnonError hierarchy
            judge/                          # Claude + Opus evaluation
                rubric.py                   # Rubric parser
                prompts/                    # Judge prompt templates
                evaluator.py                # Opus 4.5 invocation
                parser.py                   # Judgment parser
            metrics/                        # Statistical calculations
                quality.py                  # Pass-Rate, Impl-Rate, R_Prog
                economic.py                 # CoP, token distribution
                process.py                  # Latency, strategic drift
            reporting/                      # Report generation
                result_writer.py            # result.json
                summary_writer.py           # summary.json
                scorecard_writer.py         # scorecard.json
                markdown_writer.py          # report.md

    runs/                               # OUTPUTS (gitignored)
        <test-id>/
            <tier>/
                <run-id>/
                    workspace/          # Modified repo
                    logs/               # Execution logs
                    judgment.json       # Judge output

    summaries/                          # AGGREGATED RESULTS
        <test-id>/
            summary.json
            scorecard.json

    reports/                            # HUMAN-READABLE REPORTS
        <test-id>/
            report.md

    docs/
        design/                         # DOCUMENTATION
            architecture.md             # This document
```

---

## 7. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Language** | Python only | Simplicity, ecosystem, subprocess capture |
| **Validation** | Claude + Opus 4.5 | Semantic evaluation beyond programmatic checks |
| **Judge Consensus** | 3 runs, confidence-weighted | Ensure consistent evaluations (retry on disagreement) |
| **Runs per tier** | 9 | Statistical validity for meaningful confidence intervals |
| **Container isolation** | Docker (required) | Independent runs, reproducibility |
| **Tiers** | T0-T3+ | Test prompt sensitivity across complexity levels |
| **Test Focus** | Tiers AND models | Compare both prompt tiers and different models |
| **T0 Baseline** | Tool default behavior | Use agent CLI defaults for vanilla tier |
| **Tier Prompts** | Independent | Each tier is self-contained (not cumulative) |
| **Judge Container** | Separate | Judge runs in separate container from agent |
| **API Keys** | Environment variables | Pass from host via docker `-e` flags |
| **Timeout Handling** | Include as failures | Count timeouts as pass_rate=0, impl_rate=0 |
| **Agamemnon Integration** | Opt-in, graceful degradation | Chaos fault injection must never block execution; API errors are logged and skipped |

---

## 8. Tier System

The framework tests across 7 tiers of increasing complexity:

| Tier | Name | Sub-tests | Description |
|------|------|-----------|-------------|
| T0 | Prompts | 24 | System prompt ablation |
| T1 | Skills | 10 | Domain expertise via skills |
| T2 | Tooling | 15 | External tools and MCP |
| T3 | Delegation | 41 | Flat multi-agent |
| T4 | Hierarchy | 7 | Nested orchestration |
| T5 | Hybrid | 15 | Best combinations |
| T6 | Super | 1 | Everything enabled |

### Tier Comparison Goals

- **Pass-Rate Variance**: `var(pass_rates_by_tier)` - Measure prompt sensitivity
- **Cost-of-Pass Delta**: `max(CoP) - min(CoP)` - Cost difference between tiers
- **Tier Uplift**: `(T_n - T_0) / T_0` - Percentage improvement over baseline
- **Consistency**: `std_dev(scores_within_tier)` - Reliability of each tier

---

## 9. Integration Points

### 9.1 External Dependencies

- **Docker**: Required for container isolation
- **Git**: Repository cloning and version control
- **Claude API**: Judge evaluation via Opus 4.5
- **Agent CLIs**: Claude Code, Codex, Cline, OpenCode
- **Maestro API** (optional): Fault injection for the Odysseus agent
  mesh. Default endpoint `http://localhost:23000`. API routes used:
  `/api/v1/health`, `/api/agents/inject`, `/api/agents/inject/{id}`,
  `/api/agents`, `/api/diagnostics`. Enabled via
  `ExperimentConfig.maestro`

### 9.2 Configuration Hierarchy

```
config/defaults.yaml          # Global defaults
    |
    v
config/models/<model>.yaml    # Model-specific overrides
    |
    v
tests/<test-id>/test.yaml     # Test-specific settings
    |
    v
CLI arguments                 # Runtime overrides
```

### 9.3 API Key Management

API keys are passed via environment variables:

```bash
docker run \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  scylla-runner ...
```

---

## 10. References

- **Implementation Plan**: `docs/plan.md`
- **Research Methodology**: `docs/research.md`
- **Metrics Definitions**: `.claude/shared/metrics-definitions.md`
- **Evaluation Guidelines**: `.claude/shared/evaluation-guidelines.md`
- **Example Test Case**: `tests/001-justfile-to-makefile/`

---
