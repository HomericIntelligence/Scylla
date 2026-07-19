# Metrics Definitions

Complete definitions of all metrics used in Scylla evaluations.

**See also:**

- [AGENTS.md](/AGENTS.md#core-metrics) - Quick reference summary
- [Research Methodology](/docs/research.md) - Application and context

## Quality Metrics

### Pass-Rate

**Definition**: Proportion of attempts that produce a correct solution.

**Formula**:

```
Pass-Rate = correct_solutions / total_attempts
```

**Range**: [0, 1]

**Interpretation**:

- 0.0 = No correct solutions
- 1.0 = All solutions correct

**Notes**:

- "Correct" defined by task-specific test suite
- Report with confidence intervals

### Implementation Rate (Impl-Rate)

**Definition**: Proportion of semantic requirements satisfied by the solution.

**Formula**:

```
Impl-Rate = satisfied_requirements / total_requirements
```

**Range**: [0, 1]

**Interpretation**:

- Measures partial credit for incomplete solutions
- More granular than binary Pass-Rate

**Notes**:

- Requires predefined requirement checklist
- Each requirement should be independently verifiable

### Fine-Grained Progress Rate (R_Prog)

**Definition**: Proportion of expected progress steps achieved during problem-solving.

**Formula**:

```
R_Prog = achieved_progress_steps / expected_progress_steps
```

**Range**: [0, 1+]

**Interpretation**:

- Captures step-by-step advancement
- Can exceed 1.0 if agent takes extra (beneficial) steps

**Notes**:

- Requires progress step definitions per task
- Useful for debugging agent behavior

### Consistency

**Definition**: Stability of outputs across multiple runs with identical inputs.

**Formula**:

```
Consistency = 1 - (std(outputs) / mean(outputs))
```

**Range**: [0, 1] (higher is more consistent)

**Notes**:

- Requires multiple runs per task
- Temperature=0 should yield high consistency

## Economic Metrics

### Cost-of-Pass (CoP)

**Definition**: Expected monetary cost to obtain one correct solution.

**Formula**:

```
CoP = total_cost / pass_rate
```

**Unit**: USD ($)

**Range**: [0, infinity)

**Interpretation**:

- Lower is better
- Infinite if pass_rate = 0

**Notes**:

- Primary economic metric for tier comparison
- Include all costs (input tokens, output tokens, tools)

### Frontier CoP

**Definition**: Minimum Cost-of-Pass across all evaluated tiers.

**Formula**:

```
Frontier_CoP = min(CoP_T0, CoP_T1, ..., CoP_T6)
```

**Interpretation**:

- Identifies most cost-effective tier
- Target for optimization

### Token Distribution

**Definition**: Breakdown of token usage by component.

**Formula**:

```
token_dist = {
    'input': input_tokens / total_tokens,
    'output': output_tokens / total_tokens,
    'tool_input': tool_input_tokens / total_tokens,
    'tool_output': tool_output_tokens / total_tokens
}
```

**Notes**:

- Helps identify cost drivers
- Useful for optimization targeting

### Change Fail Percentage (CFP)

**Definition**: Proportion of code changes that cause failures.

**Formula**:

```
CFP = failed_changes / total_changes
```

**Range**: [0, 1]

**Interpretation**:

- Lower is better
- Measures production stability

### PR Revert Rate

**Definition**: Proportion of pull requests that are reverted.

**Formula**:

```
PR_Revert_Rate = reverted_prs / merged_prs
```

**Range**: [0, 1]

**Interpretation**:

- Lower is better
- Indicates code quality

## Process Metrics

### Latency

**Definition**: Time from query submission to response completion.

**Unit**: Seconds (s)

**Components**:

- Time-to-First-Token (TTFT)
- Total response time
- Tool execution time (if applicable)

### Strategic Drift

**Definition**: Deviation from original goal over multi-step tasks.

**Measurement**:

```
Strategic_Drift = cosine_distance(initial_goal_embedding, final_action_embedding)
```

**Range**: [0, 2]

**Interpretation**:

- 0 = Perfect goal alignment
- 2 = Completely opposite direction

### Ablation Score

**Definition**: Isolated contribution of a single component to overall performance.

**Formula**:

```
Ablation_Score = performance_with_component - performance_without_component
```

**Interpretation**:

- Positive = Component improves performance
- Negative = Component hurts performance
- Near zero = Component has no effect

## Tier-Specific Metrics

### T2 (Tooling)

**Tool Call Success Rate**:

```
Tool_Success_Rate = successful_tool_calls / total_tool_calls
```

**Tool Utilization**:

```
Tool_Utilization = tasks_using_tools / total_tasks
```

### T3 (Delegation)

**Delegation Overhead**:

```
Delegation_Overhead = multi_agent_cost / single_agent_equivalent_cost
```

**Task Distribution Efficiency**:

```
Task_Distribution_Efficiency = 1 - (idle_time / total_time)
```

### T4 (Hierarchy)

**Correction Frequency**:

```
Correction_Frequency = corrections_made / total_steps
```

**Iterations to Success**:

```
Iterations_to_Success = number_of_self_correction_loops
```

## Statistical Reporting

### Standard Format

Always report metrics with:

1. **Point estimate**: The calculated value
2. **Confidence interval**: 95% CI recommended
3. **Sample size**: n for the calculation
4. **Comparison p-value**: If comparing tiers

### Example

```markdown
Pass-Rate: 0.67 (95% CI: 0.54-0.80), n=50
CoP: $1.49 (95% CI: $1.21-$1.77), n=50
Latency: 18.2s (95% CI: 16.4-20.0s), n=50
```

## Aggregation Methods

### Across Tasks

For comparing tiers across multiple tasks:

```
Aggregate_Metric = mean(task_metrics, weights=task_importance)
```

### Across Runs

For combining multiple runs of same experiment:

```
Combined_Estimate = mean(run_estimates)
Combined_SE = sqrt(sum(run_SE^2)) / n_runs
```

## Metric Selection Guide

| Question | Primary Metric | Secondary Metrics |
|----------|---------------|-------------------|
| Which tier is most accurate? | Pass-Rate | Impl-Rate, R_Prog |
| Which tier is most cost-effective? | CoP | Token Distribution |
| Which tier is fastest? | Latency | TTFT |
| Which tier is most reliable? | Consistency | CFP |
| Is this component useful? | Ablation Score | - |

## Future Instrumentation

The following tier-specific metrics are defined in the architecture but **cannot be computed from current data collection**. Each requires additional instrumentation before implementation.

### 1. Tool Call Success Rate (T2 - Tooling)

**Status**: Not computable

**Formula**:

```
Tool_Success_Rate = successful_tool_calls / total_tool_calls
```

**Current Data Gap**:

- `agent/result.json` provides `api_calls` (total count) but does not track individual tool call outcomes
- No success/failure distinction for tool invocations
- No per-tool success tracking

**Required Instrumentation**:

1. **Claude API conversation-level logging** to capture:
   - Each tool invocation request (tool name, parameters)
   - Tool execution outcome (success/failure/error)
   - Error messages for failed tool calls
   - Timestamp for each tool call

2. **Data schema extension** in `agent/result.json`:

   ```json
   "toolMetrics": {
     "total_tool_calls": 42,
     "successful_calls": 38,
     "failed_calls": 4,
     "by_tool": {
       "Bash": {"success": 15, "failure": 1},
       "Read": {"success": 12, "failure": 0},
       "Edit": {"success": 11, "failure": 3}
     }
   }
   ```

**Implementation Approach**:

- Add tool call result tracking in Claude API wrapper
- Categorize outcomes: success (tool returned result), failure (tool error), timeout
- Aggregate per-tool and overall success rates
- Store in extended result.json schema

---

### 2. Tool Utilization (T2 - Tooling)

**Status**: Not computable

**Formula**:

```
Tool_Utilization = tasks_using_tools / total_tasks
```

**Current Data Gap**:

- No explicit marker for whether a task used tools vs. relied purely on prompting
- `api_calls > 0` is a proxy but doesn't distinguish intentional tool use from incidental calls
- Cannot differentiate tool-appropriate tasks from prompt-only tasks

**Required Instrumentation**:

1. **Task metadata tracking**:
   - Task classification: tool-required, tool-optional, prompt-only
   - Explicit tool usage flag per task execution
   - Count of unique tools used per task

2. **Data schema extension** in `agent/result.json`:

   ```json
   "taskMetrics": {
     "task_id": "benchmark-42",
     "task_category": "tool-optional",
     "tools_used": ["Bash", "Read", "Edit"],
     "tool_usage_required": false,
     "tool_usage_occurred": true
   }
   ```

**Implementation Approach**:

- Add task categorization to benchmark definitions (YAML)
- Track tool invocation presence per task execution
- Calculate utilization rate across task categories
- Compare tool-optional vs. tool-required task patterns

---

### 3. Task Distribution Efficiency (T3 - Delegation)

**Status**: Not computable

**Formula**:

```
Task_Distribution_Efficiency = 1 - (idle_time / total_time)
```

**Current Data Gap**:

- No per-agent timing instrumentation
- No idle time tracking (time when agent is waiting vs. actively working)
- `agent/result.json` contains total duration but not per-agent activity logs
- Cannot distinguish parallel work from sequential bottlenecks

**Required Instrumentation**:

1. **Per-agent activity tracking**:
   - Agent start/end timestamps for each sub-task
   - Active vs. idle state transitions
   - Blocking/waiting periods (e.g., waiting for delegated sub-agent)
   - Parallel vs. sequential execution markers

2. **Data schema extension** in `agent/result.json`:

   ```json
   "delegationMetrics": {
     "agents": [
       {
         "agent_id": "orchestrator-1",
         "active_time_ms": 12500,
         "idle_time_ms": 3500,
         "tasks_completed": 3,
         "blocked_on": ["specialist-2"]
       },
       {
         "agent_id": "specialist-2",
         "active_time_ms": 8000,
         "idle_time_ms": 1000,
         "tasks_completed": 5,
         "blocked_on": []
       }
     ],
     "total_time_ms": 16000,
     "total_idle_time_ms": 4500,
     "parallelization_factor": 1.25
   }
   ```

**Implementation Approach**:

- Add state machine tracking for each agent (active/idle/blocked/completed)
- Instrument agent framework to log state transitions
- Calculate idle percentage and parallelization efficiency
- Detect bottlenecks in delegation chains

---

### 4. Correction Frequency (T4 - Hierarchy)

**Status**: Not computable (requires semantic analysis)

**Formula**:

```
Correction_Frequency = corrections_made / total_steps
```

**Current Data Gap**:

- No explicit correction markers in agent conversations
- `num_turns` from `agent/result.json` is a rough proxy but includes all turns, not just corrections
- Cannot distinguish correction loops from normal multi-step progress
- Requires semantic analysis of agent messages to identify corrections

**Required Instrumentation**:

1. **Explicit correction markers** in agent output:
   - Agent self-identifies when correcting previous work
   - Hierarchical correction: orchestrator corrects specialist
   - Correction reason (error, misunderstanding, quality improvement)

2. **Semantic analysis pipeline**:
   - NLP-based detection of correction patterns in agent messages
   - Keywords: "fix", "correct", "mistake", "revise", "retry"
   - Message similarity analysis (detect repeated attempts)

3. **Data schema extension** in `agent/result.json`:

   ```json
   "correctionMetrics": {
     "total_steps": 24,
     "corrections_made": 5,
     "correction_types": {
       "self_correction": 3,
       "hierarchical_correction": 2,
       "user_correction": 0
     },
     "correction_details": [
       {
         "turn_number": 8,
         "correcting_agent": "orchestrator",
         "corrected_agent": "specialist-1",
         "reason": "logic_error"
       }
     ]
   }
   ```

**Implementation Approach**:

- **Option 1 (Explicit)**: Add correction markers to agent prompts/framework
  - Instruct agents to emit structured correction signals
  - Tag messages with correction metadata

- **Option 2 (Inferred)**: Post-hoc semantic analysis
  - Analyze conversation logs with NLP model
  - Detect correction patterns heuristically
  - Less accurate but requires no framework changes

- **Recommended**: Hybrid approach with explicit markers for known corrections + semantic analysis for edge cases

---

### 5. Iterations to Success (T4 - Hierarchy)

**Status**: Partially computable (num_turns is rough proxy)

**Formula**:

```
Iterations_to_Success = number_of_self_correction_loops
```

**Current Data Gap**:

- `num_turns` from `agent/result.json` counts all conversation turns, not self-correction loops
- No explicit loop counter for retry/correction cycles
- Cannot distinguish linear progress (A→B→C) from iterative refinement (A→B→A'→B'→success)
- Need to track when agent returns to previous state vs. advances forward

**Required Instrumentation**:

1. **Explicit loop tracking**:
   - Counter increments when agent revisits previous task/state
   - Detect retry attempts (same task, different approach)
   - Track convergence to success vs. abandonment

2. **Task state tracking**:
   - Mark task attempts (attempt 1, 2, 3...)
   - Distinguish new tasks from retries
   - Track success/failure per attempt

3. **Data schema extension** in `agent/result.json`:

   ```json
   "iterationMetrics": {
     "total_attempts": 3,
     "successful_iteration": 3,
     "failed_iterations": 2,
     "iteration_details": [
       {
         "iteration": 1,
         "turns": 8,
         "outcome": "failure",
         "failure_reason": "logic_error"
       },
       {
         "iteration": 2,
         "turns": 6,
         "outcome": "failure",
         "failure_reason": "incomplete_implementation"
       },
       {
         "iteration": 3,
         "turns": 10,
         "outcome": "success",
         "failure_reason": null
       }
     ],
     "total_turns": 24
   }
   ```

**Implementation Approach**:

- **Option 1 (Framework-level)**: Add iteration tracking to evaluation harness
  - Detect task restart/retry events
  - Increment loop counter on retry
  - Track attempt outcomes

- **Option 2 (Semantic-level)**: Infer from conversation analysis
  - Detect patterns indicating retry (similar prompts, revisited code)
  - Cluster turns into iteration cycles
  - Less precise but requires no framework changes

- **Recommended**: Framework-level tracking with explicit retry events for accuracy

---

## Summary of Instrumentation Priorities

| Metric | Complexity | Value | Priority | Approach |
|--------|------------|-------|----------|----------|
| Tool Call Success Rate | Low | High | **P0** | API wrapper modification |
| Tool Utilization | Low | High | **P0** | Task metadata + flag |
| Iterations to Success | Medium | High | **P1** | Framework loop counter |
| Task Distribution Efficiency | High | Medium | **P2** | Per-agent state tracking |
| Correction Frequency | High | Medium | **P2** | Semantic analysis pipeline |

**P0 (High Priority)**: Low implementation cost, high evaluation value
**P1 (Medium Priority)**: Medium implementation cost, high evaluation value
**P2 (Future Work)**: High implementation cost, can defer until advanced analysis

**Next Steps**:

1. Extend `agent/result.json` schema to accommodate new metrics
2. Implement P0 instrumentation (tool success tracking, tool utilization flags)
3. Validate data collection with small-scale pilot experiments
4. Implement P1/P2 instrumentation based on research needs

## Example Calculations

### Example 1: Single Run

```
Input:
  passed = True
  weighted_score = 0.85
  cost_usd = 0.50

Calculations:
  pass_rate = 1.0
  impl_rate = 0.85
  cost_of_pass = 0.50 / 1.0 = $0.50
  composite_score = (1.0 + 0.85) / 2 = 0.925
  grade = "A" (0.925 >= 0.95? No -> 0.925 >= 0.85? Yes -> "B")

Wait, 0.925 >= 0.85 but < 0.95, so grade = "B"
```

### Example 2: 10-Run Aggregation

```
Input (pass_rates):
  [1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0]

Calculations:
  sorted = [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
  median = (1.0 + 1.0) / 2 = 1.0
  mean = 8/10 = 0.8
  mode = 1.0
  min = 0.0
  max = 1.0
  std_dev = sqrt((2*(0.8)^2 + 8*(0.2)^2) / 10) = sqrt(0.16) = 0.4
```

### Example 3: Cross-Tier Analysis

```
Input:
  T0: composite_median = 0.70
  T1: composite_median = 0.80
  T2: composite_median = 0.85
  T3: composite_median = 0.90

Tier Uplifts (vs T0):
  T1: (0.80 - 0.70) / 0.70 = 0.143 (14.3%)
  T2: (0.85 - 0.70) / 0.70 = 0.214 (21.4%)
  T3: (0.90 - 0.70) / 0.70 = 0.286 (28.6%)

Variance:
  mean = (0.70 + 0.80 + 0.85 + 0.90) / 4 = 0.8125
  variance = ((0.70-0.8125)^2 + (0.80-0.8125)^2 +
              (0.85-0.8125)^2 + (0.90-0.8125)^2) / 4
           = (0.01266 + 0.00016 + 0.00141 + 0.00766) / 4
           = 0.00547
```

## Process Metrics

These metrics capture the quality of the agent's execution process, not just the final outcome.

### Fine-Grained Progress Rate (R_Prog)

**STATUS: EXCLUDED FROM CURRENT STUDY** (See docs/research.md for rationale)

Captures incremental advancements through the execution trajectory.

```
r_prog = achieved_weighted_steps / expected_weighted_steps

# Simple version (equal weights):
r_prog = achieved_steps / expected_steps
```

**Interpretation**:

- 1.0 = all expected steps completed
- 0.5 = halfway through expected steps
- 0.0 = no progress

**Why R_Prog?** Diagnoses where agents fail in multi-step tasks.

**Exclusion Rationale:** Requires execution trajectory instrumentation (step tracking, progress monitoring) not present in current data collection infrastructure. Impl-Rate provides adequate requirement-level granularity without needing intermediate state analysis.

### Strategic Drift

Measures how much intermediate actions diverge from the intended goal.

```
strategic_drift = 1 - (sum(goal_alignment * weight) / sum(weight))

# Simple version (binary alignment):
strategic_drift = 1 - (goal_aligned_actions / total_actions)
```

**Interpretation**:

- 0.0 = perfect alignment (no drift)
- 1.0 = complete misalignment (all actions off-track)

### Change Fail Percentage (CFP)

DevOps stability metric: percentage of changes that cause service failures.

```
cfp = failed_changes / total_changes
```

**Interpretation**:

- 0.0 = no failures (stable output)
- 0.1 = 10% of changes cause failures
- High CFP indicates brittle solutions

### PR Revert Rate

Frequency of agent-generated changes rejected by human reviewers.

```
pr_revert_rate = reverted_changes / total_changes
```

## Token Tracking (T1 vs T2 Analysis)

These metrics analyze the "Token Efficiency Chasm" between T1 (Skills) and T2 (Tooling).

### Schema Overhead

Total tokens consumed by tool schemas (T2+).

```
schema_overhead = sum(tokens for component_type == TOOL_SCHEMA)
```

**Key insight**: T2 architectures load JSON schemas that can consume 50k+ tokens upfront.

### Skill Efficiency

Ratio of skill tokens to total (skill + schema) tokens.

```
skill_efficiency = skill_tokens / (skill_tokens + schema_overhead)
```

**Interpretation**:

- 1.0 = no schema overhead (pure T1)
- 0.2 = 80% of tokens are schema overhead

### Token Efficiency Ratio

Comparison of schema tokens to skill tokens.

```
token_efficiency_ratio = schema_tokens / skill_tokens
```

**Interpretation**:

- ratio > 1.0 = schemas use more tokens than skills
- ratio = 10.0 = schemas use 10x more tokens

### Component Cost Breakdown

Track costs at the component level:

| Component Type | Description |
|----------------|-------------|
| `SYSTEM_PROMPT` | Base system prompt |
| `SKILL_PROMPT` | T1 skill instructions |
| `DOMAIN_EXPERTISE` | T1 domain knowledge |
| `TOOL_SCHEMA` | T2 JSON tool definitions |
| `TOOL_CALL` | T2 tool invocations |
| `TOOL_RESPONSE` | T2 tool results |
| `ORCHESTRATOR` | T3/T4 coordination |
| `SUB_AGENT` | T3/T4 delegated agents |
| `MONITOR` | T4 error detection |
| `EVALUATOR` | T4 self-reflection |

```python
# Calculate per-component costs
distribution = tracker.calculate_distribution(
    input_price=3.0,   # $/1M input tokens
    output_price=15.0, # $/1M output tokens
)

# Get schema overhead percentage
schema_pct = distribution.get_type_percentage(ComponentType.TOOL_SCHEMA)
```

## Summary Table

| Metric | Formula | Range | Interpretation |
|--------|---------|-------|----------------|
| pass_rate | `1.0 if passed else 0.0` | [0, 1] | Higher = better |
| impl_rate | `weighted_score` | [0, 1] | Higher = better |
| cost_usd | `input*price + output*price` | [0, ∞) | Lower = better |
| cost_of_pass | `cost / pass_rate` | [0, ∞] | Lower = better |
| composite | `(pass + impl) / 2` | [0, 1] | Higher = better |
| tier_uplift | `(tier - t0) / t0` | (-∞, ∞) | Positive = improvement |
| variance | `Σ(x - μ)² / n` | [0, ∞) | Lower = more consistent |
| r_prog | `achieved / expected` | [0, 1] | Higher = more progress |
| strategic_drift | `1 - alignment` | [0, 1] | Lower = better alignment |
| cfp | `failed / total` | [0, 1] | Lower = more stable |
| schema_overhead | `sum(schema_tokens)` | [0, ∞) | Lower = more efficient |

## Related Documentation

- [Judge Protocol](../../docs/design/judge-protocol.md) - How judgments produce weighted_score
- [Evaluation Categories](../../docs/design/judge-protocol.md#evaluation-categories) - 10 quality categories
- [Research Methodology](../research.md) - Original metrics definitions
