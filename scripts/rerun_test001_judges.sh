#!/bin/bash
# Rerun judge pipeline for test-001 rate-limited subtests
# ========================================================
# test-001 hit the Claude weekly usage limit during T3 (~subtest 15).
# All subsequent judges (T3/15/run3, T3/16-41, T5/07-15, T6) scored 0.0 silently.
# T3/16-41 run1 stalled at agent_complete (workspace present, no diff/judge ran).
# Agent runs completed successfully, so only diff+judge stages need rerunning.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "=== Patching checkpoint ==="
uv run python scripts/patch_checkpoint_for_rejudge.py

echo ""
echo "=== Step 1: Resume diff+judge for T3/16-41 run1 (agent done, workspace present) ==="
uv run python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --experiment-id test-001 \
    --results-dir results \
    --tiers T3 \
    --from agent_complete \
    --filter-tier T3 \
    --filter-subtest 16 --filter-subtest 17 --filter-subtest 18 \
    --filter-subtest 19 --filter-subtest 20 --filter-subtest 21 \
    --filter-subtest 22 --filter-subtest 23 --filter-subtest 24 \
    --filter-subtest 25 --filter-subtest 26 --filter-subtest 27 \
    --filter-subtest 28 --filter-subtest 29 --filter-subtest 30 \
    --filter-subtest 31 --filter-subtest 32 --filter-subtest 33 \
    --filter-subtest 34 --filter-subtest 35 --filter-subtest 36 \
    --filter-subtest 37 --filter-subtest 38 --filter-subtest 39 \
    --filter-subtest 40 --filter-subtest 41 \
    --filter-run 1

echo ""
echo "=== Step 2: Re-judge bad-judge runs (score=0.0 garbage) for T3/T5/T6 ==="
uv run python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --experiment-id test-001 \
    --results-dir results \
    --tiers T3 T5 T6 \
    --from judge_pipeline_run \
    --filter-tier T3 --filter-tier T5 --filter-tier T6

echo ""
echo "=== Step 3: Regenerate analysis artifacts ==="
uv run python scripts/generate_all_results.py \
    --data-dir "$HOME/fullruns/haiku-rewrite" \
    --output-dir docs/arxiv/haiku

echo ""
echo "=== Done ==="
