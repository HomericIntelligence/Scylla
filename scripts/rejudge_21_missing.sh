#!/bin/bash
# Re-judge 21 runs that have agent data but empty judge dirs
# ============================================================
# test-001: T3/06/run_01, T4/01-14/run_01, T5/01-06/run_01
# Agent completed successfully but judge step never ran.
# Checkpoint has these as "pending" — patch to judge_pipeline_run first.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

EXPERIMENT_DIR="/home/mvillmow/fullruns/haiku-rewrite/test-001/2026-03-30T04-09-50-test-001"

echo "=== Step 1: Patch checkpoint for 21 unjudged runs ==="
uv run python3 -c "
import json
from pathlib import Path

cp_path = Path('$EXPERIMENT_DIR/checkpoint.json')
cp = json.loads(cp_path.read_text())

runs = [
    ('T3', '06', '1'),
    *[('T4', f'{s:02d}', '1') for s in range(1, 15)],
    *[('T5', f'{s:02d}', '1') for s in range(1, 7)],
]

affected_tiers = set()
affected_subtests = set()

for tier, sub, run_num in runs:
    current = cp['run_states'].get(tier, {}).get(sub, {}).get(run_num, 'MISSING')
    print(f'  {tier}/{sub}/run_{run_num}: {current} -> judge_pipeline_run')
    cp['run_states'].setdefault(tier, {}).setdefault(sub, {})[run_num] = 'judge_pipeline_run'
    # Remove from completed_runs if present
    completed = cp.get('completed_runs', {}).get(tier, {}).get(sub, [])
    if int(run_num) in completed:
        completed.remove(int(run_num))
    affected_tiers.add(tier)
    affected_subtests.add((tier, sub))

# Reset affected subtest/tier states
for tier, sub in affected_subtests:
    cp.setdefault('subtest_states', {}).setdefault(tier, {})[sub] = 'pending'
for tier in affected_tiers:
    cp.setdefault('tier_states', {})[tier] = 'pending'
cp['experiment_state'] = 'tiers_running'

cp_path.write_text(json.dumps(cp, indent=2))
print(f'\nPatched {len(runs)} runs. Checkpoint saved.')
"

echo ""
echo "=== Step 2: Run judge pipeline for the 21 patched runs ==="
uv run python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --experiment-id test-001 \
    --results-dir /home/mvillmow/fullruns/haiku-rewrite/test-001 \
    --tiers T3 T4 T5 \
    --from judge_pipeline_run \
    --filter-tier T3 --filter-tier T4 --filter-tier T5 \
    --filter-run 1

echo ""
echo "=== Step 3: Regenerate analysis artifacts ==="
uv run python scripts/generate_all_results.py \
    --data-dir /home/mvillmow/fullruns/haiku-rewrite \
    --output-dir docs/arxiv/haiku

echo ""
echo "=== Done ==="
echo "Verify: check that runs.csv now has 1080 rows"
uv run python3 -c "
import csv
from pathlib import Path
rows = sum(1 for _ in csv.reader(open('docs/arxiv/haiku/data/runs.csv'))) - 1
print(f'runs.csv: {rows} rows (expected 1080)')
"
