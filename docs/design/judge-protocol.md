# Judge Protocol Documentation

This document describes the judge system for evaluating AI agent work in Scylla.

## Overview

### Purpose of the Judge

The judge evaluates AI agent work against defined criteria and rubrics, providing:

- **Requirement scores**: Per-requirement scores with confidence levels
- **Category scores**: Quality scores across 10 evaluation categories
- **Pass/fail determination**: Based on weighted score thresholds
- **Qualitative feedback**: Strengths, weaknesses, and recommendations

### Why Claude Code + Opus 4.5

The judge uses Claude Code with Opus 4.5 because:

1. **Workspace access**: Claude Code can explore the file system to examine agent outputs
2. **Tool execution**: Can run validation commands specified in rubrics
3. **High capability**: Opus 4.5 provides strong reasoning for nuanced evaluation
4. **Consistency**: Same tooling ecosystem as the agents being evaluated

### 3-Run Consensus

Each evaluation runs **3 times** with disagreements resolved by **confidence-weighted averaging**:

```
consensus_score = Σ(score_i × confidence_i) / Σ(confidence_i)
```

This reduces variance and provides more reliable scores.

## Judge Invocation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      Judge Invocation Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Prepare Context                                              │
│     ├── Load rubric.yaml                                         │
│     ├── Read task prompt                                         │
│     ├── Gather success criteria                                  │
│     └── Build evaluation prompt                                  │
│                                                                  │
│  2. Run 3 Evaluations                                            │
│     ├── Run 1: Invoke Claude Code + Opus 4.5                     │
│     ├── Run 2: Invoke Claude Code + Opus 4.5                     │
│     └── Run 3: Invoke Claude Code + Opus 4.5                     │
│                                                                  │
│  3. Parse Judgments                                              │
│     ├── Extract JSON from each output                            │
│     ├── Parse requirement scores                                 │
│     ├── Parse category scores                                    │
│     └── Parse summaries                                          │
│                                                                  │
│  4. Calculate Consensus                                          │
│     ├── Weighted average per requirement                         │
│     ├── Weighted average per category                            │
│     └── Overall weighted score                                   │
│                                                                  │
│  5. Write Results                                                │
│     ├── judgment.json with consensus scores                      │
│     └── Individual run outputs for analysis                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Step 1: Prepare Context

```python
from scylla.judge.prompts import build_judge_prompt
from scylla.judge.rubric import RubricParser

# Load rubric
rubric = RubricParser.parse(Path("rubric.yaml"))

# Read task prompt
task_prompt = Path("task.md").read_text()

# Build evaluation prompt
prompt = build_judge_prompt(
    task_prompt=task_prompt,
    criteria=rubric.description,
    rubric=rubric_text,
    tier_id="T3",  # Optional tier context
)
```

### Step 2: Run Evaluations

```python
from scylla.judge.evaluator import JudgeEvaluator, EvaluatorConfig

config = EvaluatorConfig(
    model="claude-opus-4-5-20251101",
    num_runs=3,
    timeout=300,
    pass_threshold=0.70,
)

evaluator = JudgeEvaluator(config=config, adapter=claude_adapter)

consensus = evaluator.evaluate_with_consensus(
    workspace=Path("/path/to/agent/output"),
    prompt=task_prompt,
    criteria=criteria,
    rubric=rubric_text,
    tier_id="T3",
)
```

### Step 3: Parse Judgments

The parser extracts JSON from judge output:

```python
from scylla.judge.parser import JudgmentParser

parser = JudgmentParser()
judgment = parser.parse(output, judge_model="claude-opus-4-5-20251101")
```

### Step 4: Calculate Consensus

```python
from scylla.judge.evaluator import weighted_consensus, JudgeScore

# For each requirement
scores = [
    JudgeScore(score=0.8, confidence=0.9),
    JudgeScore(score=0.85, confidence=0.7),
    JudgeScore(score=0.75, confidence=0.8),
]
consensus_score = weighted_consensus(scores)  # ~0.80
```

### Step 5: Write Results

```python
judgment.write_json(Path("output/judgment.json"))
```

## Prompt Architecture

The judge system uses a **two-layer prompt architecture**:

### 1. Global System Prompt (config/judge/system_prompt.md)

The system prompt is loaded from `config/judge/system_prompt.md` and contains:

- Evaluation methodology (checklist vs subjective scoring)
- Deduction tier guidelines (Tiny → Catastrophic)
- N/A handling rules
- JSON output schema
- Reference to grading scale (`docs/design/grading-scale.md`)

This is the **single source of truth** for evaluation criteria and is passed via `--system-prompt-file` to Claude CLI.

### 2. Task-Specific Prompt (Generated Dynamically)

The task-specific prompt is generated by `scylla.judge.prompts.build_task_prompt()` and contains:

```markdown
## Rubric (Evaluation Criteria)
```yaml
<rubric content>
\```

## Task Given to Agent
<task prompt>

## Agent's Output
<agent output>

## Workspace State After Agent Execution
<workspace file listing>

## Git Diff (Patchfile)
```diff
<git diff>
\```

## Build/Lint/Test Pipeline Results
<pipeline results>

---

Evaluate the agent's work using the rubric and criteria in your system prompt.
```

### Prompt Generation Flow

```python
from scylla.judge.prompts import build_task_prompt, JUDGE_SYSTEM_PROMPT_FILE

# Build task-specific context
task_prompt = build_task_prompt(
    task_prompt=task,
    agent_output=output,
    workspace_state=workspace,
    patchfile=diff,
    pipeline_result_str=pipeline_results,
    rubric_content=rubric_yaml,
)

# Claude CLI invocation uses both prompts
claude \
  --system-prompt-file <JUDGE_SYSTEM_PROMPT_FILE> \
  --prompt <task_prompt>
```

### Evaluation Phases

The prompt includes tier-specific context when evaluating tiered experiments:

| Tier | Context |
|------|---------|
| T0 | Vanilla baseline, zero-shot prompting |
| T1 | System prompts and chain-of-thought |
| T2 | Prompt-encoded domain expertise |
| T3 | External function calling with tools |
| T4 | Flat multi-agent delegation |
| T5 | Nested orchestration with self-correction |
| T6 | Hybrid best-of-breed architecture |

## Evaluation Categories

The judge scores 10 quality categories:

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

**Total Weight**: 9.5

## judgment.json Schema

```json
{
  "timestamp": "2024-01-15T14:45:00Z",
  "judge_model": "claude-opus-4-5-20251101",
  "requirements": {
    "R001": {
      "id": "R001",
      "score": 0.9,
      "confidence": 0.85,
      "notes": "Requirement fully met"
    },
    "R002": {
      "id": "R002",
      "score": 0.7,
      "confidence": 0.9,
      "notes": "Partially implemented"
    }
  },
  "categories": {
    "functional_correctness": {
      "name": "functional_correctness",
      "score": 0.85,
      "confidence": 0.9,
      "weight": 2.0,
      "notes": "Core functionality works"
    },
    "completeness": {
      "name": "completeness",
      "score": 0.8,
      "confidence": 0.85,
      "weight": 1.5,
      "notes": "Most requirements addressed"
    }
  },
  "summary": {
    "weighted_score": 0.82,
    "passed": true,
    "letter_grade": "B",
    "overall_confidence": 0.87,
    "strengths": [
      "Clean implementation",
      "Good test coverage"
    ],
    "weaknesses": [
      "Missing edge case handling",
      "Documentation could be improved"
    ]
  },
  "exploratory_testing": {
    "commands_run": ["pytest tests/", "mypy scylla/"],
    "observations": ["All tests pass", "No type errors"],
    "failures": []
  },
  "qualitative_feedback": "Overall solid implementation..."
}
```

## Error Handling

### Parse Failures

If JSON extraction fails:

1. Log warning with raw output
2. Return empty judgment
3. Include raw output for debugging

```python
try:
    json_data = extract_json(output)
except JSONDecodeError:
    logger.warning("Failed to parse JSON from judge output")
    return Judgment(raw_output=output)
```

### Evaluation Failures

If a single evaluation run fails:

1. Log warning with error details
2. Add empty judgment to run list
3. Continue with remaining runs
4. Calculate consensus from successful runs

```python
for run in range(num_runs):
    try:
        judgment = single_evaluation(...)
    except Exception as e:
        logger.warning(f"Run {run} failed: {e}")
        judgment = Judgment()  # Empty judgment
    judgments.append(judgment)
```

### Timeout Handling

If evaluation times out:

1. Return partial output if available
2. Mark as timed out
3. Include in consensus with low confidence

```python
except subprocess.TimeoutExpired as e:
    return AdapterResult(
        exit_code=-1,
        timed_out=True,
        stdout=e.output.decode() if e.output else "",
    )
```

## Examples

### Example 1: Simple Evaluation

```python
from scylla.judge.evaluator import JudgeEvaluator, EvaluatorConfig
from scylla.adapters import ClaudeCodeAdapter

# Configure
config = EvaluatorConfig(
    model="claude-opus-4-5-20251101",
    num_runs=3,
    pass_threshold=0.70,
)

adapter = ClaudeCodeAdapter()
evaluator = JudgeEvaluator(config=config, adapter=adapter)

# Evaluate
consensus = evaluator.evaluate_with_consensus(
    workspace=Path("./agent_output"),
    prompt="Implement a REST API for user management",
    criteria="Must support CRUD operations",
    rubric="R001: Create user endpoint\nR002: Read user endpoint",
)

# Check result
print(f"Score: {consensus.weighted_score:.2f}")
print(f"Passed: {consensus.passed}")
print(f"Grade: {consensus.letter_grade}")
```

### Example 2: Loading and Analyzing Judgment

```python
from scylla.judge.parser import load_judgment

# Load saved judgment
judgment = load_judgment(Path("output/judgment.json"))

# Analyze results
print(f"Model: {judgment.judge_model}")
print(f"Score: {judgment.summary.weighted_score:.2f}")

for req_id, score in judgment.requirements.items():
    print(f"{req_id}: {score.score:.2f} (confidence: {score.confidence:.2f})")
```

### Example 3: Custom Rubric

```yaml
# rubric.yaml
name: API Implementation Rubric
description: Evaluate REST API implementation
pass_threshold: 0.75

grade_scale:
  S: 1.00
  A: 0.80
  B: 0.60
  C: 0.40
  D: 0.20
  F: 0.0

requirements:
  - id: R001
    description: Create user endpoint returns 201
    weight: 2.0
    evaluation: binary
    validation_command: "curl -X POST /users"

  - id: R002
    description: Get user endpoint returns user data
    weight: 1.5
    evaluation: scaled
    validation_command: "curl /users/1"
```

## Related Documentation

- [Rubric Parser](../dev/rubric-parser.md) - Parsing rubric.yaml files
- [Adapters](../dev/adapters.md) - Claude Code adapter implementation
- [Metrics](../dev/metrics.md) - How scores feed into metrics
