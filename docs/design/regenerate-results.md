# Regenerate Results and Reports

The `manage_experiment.py regenerate` subcommand rebuilds `results.json` and all report files from existing `run_result.json` files without re-running agents or judges.

## Use Cases

1. **Fix corrupted results.json**: When the aggregation logic produces incorrect results, regenerate from source data
2. **Re-judge failed runs**: Selectively re-run judges for runs that are missing judge results
3. **Update report formats**: Regenerate reports after updating report templates
4. **Recover from interruptions**: Rebuild results after experiment interruptions

## Usage

### Basic Regeneration

Regenerate results from existing run data (no re-judging):

```bash
uv run python scripts/manage_experiment.py regenerate /path/to/experiment/
```

### Re-judge Missing Runs

Re-run judges for runs that are missing valid judge results, then regenerate:

```bash
uv run python scripts/manage_experiment.py regenerate /path/to/experiment/ --rejudge
```

### Override Judge Model

Specify a different judge model for re-judging:

```bash
uv run python scripts/manage_experiment.py regenerate /path/to/experiment/ \
    --rejudge --judge-model claude-opus-4-5-20251101
```

### Dry Run

Preview what would be done without modifying files:

```bash
uv run python scripts/manage_experiment.py regenerate /path/to/experiment/ \
    --rejudge --dry-run --verbose
```

## Options

- `experiment_dir`: Path to experiment directory (required)
- `--rejudge`: Re-run judges for runs missing valid judge results
- `--judge-model MODEL`: Override judge model (default: from config)
- `--dry-run`: Show what would be done without modifying files
- `-v, --verbose`: Enable verbose logging

## How It Works

### Scanning

1. Recursively scans experiment directory for `run_result.json` files
2. Skips `.failed/` directories (already invalidated runs)
3. Parses directory structure: `T0/00-subtest/run_01/run_result.json`
4. Validates each run result (checks for required fields, incomplete executions)

### Re-judging (Optional)

If `--rejudge` is specified:

1. For each run, checks if valid judge result exists
2. If judge is missing but agent result exists:
   - Loads agent output from `agent/output.txt`
   - Loads task prompt from `experiment_dir/prompt.md`
   - Runs LLM judge using the same logic as the main pipeline
   - Saves judge results to `judge/result.json` and `judge_NN/judgment.json`
   - Updates `run_result.json` with new judge scores
   - Backs up old `run_result.json` as `.pre-rejudge`

### Aggregation

1. Groups runs by tier and subtest
2. Computes aggregated statistics (mean, median, stdev, pass_rate, grades)
3. Selects best subtest per tier using existing selection algorithm
4. Computes tier-level and experiment-level results
5. Finds frontier tier (best cost-of-pass)

### Saving

1. Backs up existing `result.json` to `result.json.backup`
2. Saves experiment-level results: `result.json`, `report.md`, `summary.md`
3. Saves tier-level results: `T0/result.json`, `T0/report.md`, `T0/summary.md`
4. Saves subtest-level results: `T0/00-subtest/report.md`, `T0/00-subtest/report.json`

## Edge Cases

- **Missing workspace**: Cannot re-judge if `run_dir/workspace/` doesn't exist
- **Corrupted run_result.json**: Skips with warning (same as `manage_experiment.py repair`)
- **Runs in .failed/ directories**: Automatically skipped
- **Non-tier directories**: Skips entries that don't start with "T"
- **Empty experiment**: Exits gracefully if no valid runs found

## Examples

### Example 1: Regenerate After Manual Fix

After manually fixing a `run_result.json` file:

```bash
# Edit the file
vim ~/fullruns/experiment/T0/00-test/run_01/run_result.json

# Regenerate all results
uv run python scripts/manage_experiment.py regenerate ~/fullruns/experiment/
```

### Example 2: Re-judge Failed Judges

After a judge timeout or failure:

```bash
# Re-run judges and regenerate
uv run python scripts/manage_experiment.py regenerate ~/fullruns/experiment/ \
    --rejudge --verbose
```

### Example 3: Preview Re-judging

Check what would be re-judged without making changes:

```bash
uv run python scripts/manage_experiment.py regenerate ~/fullruns/experiment/ \
    --rejudge --dry-run --verbose
```

## Related Tools

- **`manage_experiment.py repair`**: Repairs checkpoint.json from run_result.json files
- **`manage_experiment.py`**: Main experiment management CLI

## Implementation

The regeneration logic is implemented in two files:

- **scylla/e2e/regenerate.py**: Core regeneration logic (testable module)
- **scripts/manage_experiment.py regenerate**: CLI wrapper (~80 lines)

All aggregation logic reuses existing functions from the main pipeline to ensure consistency.
