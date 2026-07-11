# Rerun Agents Guide

## Overview

The `manage_experiment.py rerun-agents` subcommand provides fine-grained control over re-running failed, partial, or incomplete experiment runs. Unlike `manage_experiment.py regenerate` which only rebuilds results from existing data, this subcommand actually re-executes agents.

## Run Status Classification

The script classifies each run into one of five categories:

| Status | Symbol | Description | Action |
|--------|--------|-------------|--------|
| `completed` | ✓ | Agent + judge + run_result.json all exist | No action (skip) |
| `results` | ⚠ | Agent finished, but run_result.json or agent/result.json missing | Regenerate only (fast) |
| `failed` | ✗ | Agent ran but failed (stderr, no valid output) | Re-run agent + judge |
| `partial` | ⋯ | Agent started but incomplete execution | Re-run agent + judge |
| `missing` | ○ | Run directory doesn't exist | Run agent + judge |

## Basic Usage

### Scan and classify all runs (dry run)

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ --dry-run
```

This shows:

- Classification of all runs by status
- How many runs would be rerun vs regenerated
- Summary statistics

### Re-run all incomplete runs

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/
```

This will:

1. Re-run agent+judge for failed, partial, and never-started runs
2. Regenerate run_result.json for agent-complete-missing-results
3. Rebuild all tier and experiment results

## Selective Re-running by Status

### Only regenerate runs with deleted results (no agent execution)

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ \
    --status results
```

**Use case**: Agent completed successfully but `agent/result.json` files are missing. This regenerates them from existing logs (stdout.log, command_log.json) **without running agents or judges**. Fast!

### Only re-run failed agents

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ \
    --status failed
```

**Use case**: Agent failures due to rate limits or temporary errors. Leave partial and missing runs alone.

### Re-run partial and missing runs

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ \
    --status partial --status missing
```

**Use case**: Experiment was interrupted mid-execution. Only complete the runs that didn't start or didn't finish.

### Exclude specific statuses (inverse filter)

To exclude certain statuses, you must explicitly list the ones you want:

```bash
# Re-run everything except missing
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ \
    --status failed --status partial --status results
```

## Combining Filters

### Re-run failed runs in T0 only

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ \
    --tier T0 --status failed
```

### Re-run specific runs across all tiers

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ \
    --runs 1,2,3 --status failed
```

### Re-run failed and partial runs in T0/00

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001-nothinking-haiku/ \
    --tier T0 --subtest 00 --status failed --status partial
```

## Common Scenarios

### Scenario 1: Experiment interrupted by Ctrl+C

**Problem**: Experiment was killed mid-execution. Some runs started but didn't complete.

**Solution**:

```bash
# Dry run to see what needs completion
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001/ --dry-run

# Complete partial and missing runs
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001/ \
    --status partial --status missing
```

### Scenario 2: Rate limit caused failures

**Problem**: Multiple runs failed due to API rate limits. Want to retry just the failures.

**Solution**:

```bash
# Re-run only failed agents
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001/ \
    --status failed
```

### Scenario 3: Manually deleted run_result.json to force re-judging

**Problem**: You deleted some `run_result.json` files to force re-judging, but agents ran successfully.

**Solution**:

```bash
# Regenerate without re-running agents (fast)
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001/ \
    --status results
```

### Scenario 4: Cherry-pick specific runs to re-run

**Problem**: Runs 1, 5, and 7 in T0/00 had issues. Want to re-run just those.

**Solution**:

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001/ \
    --tier T0 --subtest 00 --runs 1,5,7
```

## Advanced Options

### Skip the final regenerate step

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001/ \
    --status failed --skip-regenerate
```

**Use case**: You want to re-run agents but delay result rebuilding until later.

### Verbose logging for debugging

```bash
pixi run python scripts/manage_experiment.py rerun-agents ~/fullruns/test001/ \
    --status failed -v
```

Shows detailed logs of agent execution, file operations, and checkpoint updates.

## Output Interpretation

### Dry Run Output

```
=== DRY RUN MODE - No changes will be made ===

AGENT FAILED (3 runs):
  - T0/00/run_01: Agent ran but failed
  - T0/01/run_02: Agent ran but failed
  - T1/00/run_05: Agent ran but failed

AGENT COMPLETE MISSING RESULTS (5 runs):
  - T0/00/run_03: Agent finished, run_result.json deleted
  - T0/00/run_04: Agent finished, run_result.json deleted
  ...

======================================================================
RUN STATUS CLASSIFICATION
======================================================================
Total expected runs:                100
  ✓ Complete:                        85
  ⚠ Agent complete, missing results: 5
  ✗ Agent failed:                    3
  ⋯ Agent partial:                   2
  ○ Never started:                   5
  - Skipped by filter:               0

RERUN RESULTS
======================================================================
Successfully rerun:                  0
Failed rerun:                        0
Regenerated (missing results):       0
======================================================================
```

### Actual Run Output

After completion, you'll see:

```
RUN STATUS CLASSIFICATION
======================================================================
Total expected runs:                100
  ✓ Complete:                        90
  ⚠ Agent complete, missing results: 0
  ✗ Agent failed:                    0
  ⋯ Agent partial:                   0
  ○ Never started:                   0
  - Skipped by filter:               0

RERUN RESULTS
======================================================================
Successfully rerun:                  8
Failed rerun:                        2
Regenerated (missing results):       5
======================================================================
```

## Implementation Details

### File Classification Logic

The script examines the following files to determine run status:

- `run_dir/agent/output.txt` - Agent stdout (must exist and be non-empty)
- `run_dir/agent/result.json` - Agent execution metadata (token stats, cost, exit code)
- `run_dir/agent/stderr.log` - Agent stderr (existence indicates potential failure)
- `run_dir/agent/timing.json` - Agent completion marker
- `run_dir/agent/command_log.json` - Agent command execution log
- `run_dir/judge/` - Judge directory existence
- `run_dir/run_result.json` - Final run result

**Important**: If `agent/result.json` is missing but the agent completed successfully (output.txt, timing.json, command_log.json exist), the file can be regenerated from the logs without re-running the agent. The script will classify this as `agent-complete-missing-results`.

### Failed Run Handling

When re-running, old run data is moved to `.failed/`:

```
T0/00/
├── run_01/                    # Fresh rerun
└── .failed/
    ├── run_01/                # Original failed attempt
    └── run_01_failed_1/       # Second failed attempt (if rerun also failed)
```

### Checkpoint Integration

The script updates the experiment checkpoint after each successful re-run, allowing you to interrupt and resume the rerun process itself.

## Troubleshooting

### "Base repository not found"

**Error**: `Base repository not found: /path/to/experiment/repo/`

**Cause**: The experiment's git repository was deleted.

**Solution**: Cannot rerun without the base repo. You can only regenerate from existing agent outputs.

### "Could not auto-detect tiers directory"

**Error**: `Could not auto-detect tiers directory`

**Cause**: Script couldn't find the test fixture directory.

**Solution**: Run the script from within the Scylla repository, or ensure the experiment was created with a valid fixture directory.

### Re-runs still failing

If re-runs continue to fail:

1. Check rate limits: `--status agent-failed` may hit rate limits if too many runs failed
2. Add `--verbose` to see detailed error logs
3. Try re-running just one run to debug: `--tier T0 --subtest 00 --runs 1`
4. Check the `.failed/` directory for error logs from previous attempts

## Related Commands

- `scripts/manage_experiment.py regenerate` - Rebuild results without re-running agents
- `scripts/manage_experiment.py` - Run a fresh experiment
- `scripts/manage_experiment.py repair` - Fix corrupted checkpoints

## See Also

- [E2E Evaluation Guidelines](/.claude/shared/evaluation-guidelines.md)
- [PR Workflow](/.claude/shared/pr-workflow.md)
- [GitHub Issue Workflow](/.claude/shared/github-issue-workflow.md)
