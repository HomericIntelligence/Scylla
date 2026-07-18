#!/usr/bin/env python3
"""Patch checkpoint to reset bad-judge runs so they can be re-judged.

Two categories of broken runs:

1. BAD_JUDGE: agent ran, run_result.json exists, but judge returned 0.0 in <30s
   (rate-limited judge that silently returned garbage).
   State on disk: run_result.json present, agent/result.json present.
   Fix: set checkpoint to judge_pipeline_run → resume with --from judge_pipeline_run.

2. AGENT_COMPLETE_NO_JUDGE: agent ran, workspace still on disk, but rate limit hit
   before diff/judge stage — no run_result.json at all.
   State on disk: agent/result.json present, workspace/ present, no run_result.json.
   Fix: set checkpoint to agent_complete → resume with --from agent_complete.

After this patch, run both commands below in sequence.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project src to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scylla.e2e.checkpoint import E2ECheckpoint, load_checkpoint, save_checkpoint  # noqa: E402

CHECKPOINT = repo_root / "results/2026-03-30T04-09-50-test-001/checkpoint.json"

# Category 1: bad judge (score=0.0, jdur<30s, run_result.json exists)
# Set to judge_pipeline_run so --from judge_pipeline_run re-judges them.
BAD_JUDGE_RUNS: list[tuple[str, str, int]] = [
    # T3/15: run3 (run1=good, run2=long stall but already has run_result.json)
    ("T3", "15", 3),
    # T3/16-41: run2 and run3
    *[("T3", f"{s:02d}", r) for s in range(16, 42) for r in (2, 3)],
    # T5/07-15: run2 and run3
    *[("T5", f"{s:02d}", r) for s in range(7, 16) for r in (2, 3)],
    # T6/01: run2 and run3
    ("T6", "01", 2),
    ("T6", "01", 3),
]

# Category 2: agent complete, workspace present, no run_result.json
# (T3/16-41 run1: rate_limited + agent_complete in checkpoint, workspace still on disk)
# Set to agent_complete so --from agent_complete resumes from diff→judge.
AGENT_COMPLETE_RUNS: list[tuple[str, str, int]] = [
    *[("T3", f"{s:02d}", 1) for s in range(16, 42)],
]


def _patch_runs(
    checkpoint: E2ECheckpoint,
    runs: list[tuple[str, str, int]],
    target_state: str,
    affected_tiers: set[str],
    affected_subtests: set[tuple[str, str]],
) -> int:
    """Set each run's checkpoint state to target_state and clear its completed entry."""
    patched = 0
    for tier_id, subtest_id, run_num in runs:
        run_num_str = str(run_num)
        current_state = (
            checkpoint.run_states.get(tier_id, {}).get(subtest_id, {}).get(run_num_str, "MISSING")
        )
        print(f"  {tier_id}/{subtest_id}/run{run_num}: {current_state} -> {target_state}")
        checkpoint.set_run_state(tier_id, subtest_id, run_num, target_state)
        checkpoint.unmark_run_completed(tier_id, subtest_id, run_num)
        affected_tiers.add(tier_id)
        affected_subtests.add((tier_id, subtest_id))
        patched += 1
    return patched


def main() -> None:
    """Patch the test-001 checkpoint and print resume commands."""
    if not CHECKPOINT.exists():
        print(f"ERROR: checkpoint not found at {CHECKPOINT}")
        sys.exit(1)

    checkpoint = load_checkpoint(CHECKPOINT)

    affected_tiers: set[str] = set()
    affected_subtests: set[tuple[str, str]] = set()
    total = 0

    print("=== Category 1: bad judge runs -> judge_pipeline_run ===")
    total += _patch_runs(
        checkpoint, BAD_JUDGE_RUNS, "judge_pipeline_run", affected_tiers, affected_subtests
    )

    print("\n=== Category 2: agent_complete runs -> agent_complete ===")
    total += _patch_runs(
        checkpoint, AGENT_COMPLETE_RUNS, "agent_complete", affected_tiers, affected_subtests
    )

    # Cascade subtest/tier/experiment states
    for tier_id, subtest_id in affected_subtests:
        checkpoint.set_subtest_state(tier_id, subtest_id, "pending")
    for tier_id in affected_tiers:
        checkpoint.set_tier_state(tier_id, "pending")
    checkpoint.experiment_state = "tiers_running"

    save_checkpoint(checkpoint, CHECKPOINT)

    print(f"\nPatched {total} runs across tiers {sorted(affected_tiers)}")
    print("Checkpoint saved. Run these two commands in sequence:\n")
    print(
        "# Step 1: Resume diff+judge for T3/16-41 run1 (agent done, workspace present)\n"
        "uv run python scripts/manage_experiment.py run \\\n"
        "    --config tests/fixtures/tests/test-001 \\\n"
        "    --experiment-id test-001 \\\n"
        "    --results-dir results \\\n"
        "    --tiers T3 \\\n"
        "    --from agent_complete \\\n"
        "    --filter-tier T3 \\\n"
        "    --filter-subtest 16 --filter-subtest 17 --filter-subtest 18 \\\n"
        "    --filter-subtest 19 --filter-subtest 20 --filter-subtest 21 \\\n"
        "    --filter-subtest 22 --filter-subtest 23 --filter-subtest 24 \\\n"
        "    --filter-subtest 25 --filter-subtest 26 --filter-subtest 27 \\\n"
        "    --filter-subtest 28 --filter-subtest 29 --filter-subtest 30 \\\n"
        "    --filter-subtest 31 --filter-subtest 32 --filter-subtest 33 \\\n"
        "    --filter-subtest 34 --filter-subtest 35 --filter-subtest 36 \\\n"
        "    --filter-subtest 37 --filter-subtest 38 --filter-subtest 39 \\\n"
        "    --filter-subtest 40 --filter-subtest 41 \\\n"
        "    --filter-run 1\n"
    )
    print(
        "# Step 2: Re-judge all bad-judge runs (run_result.json exists but score=0.0)\n"
        "uv run python scripts/manage_experiment.py run \\\n"
        "    --config tests/fixtures/tests/test-001 \\\n"
        "    --experiment-id test-001 \\\n"
        "    --results-dir results \\\n"
        "    --tiers T3 T5 T6 \\\n"
        "    --from judge_pipeline_run \\\n"
        "    --filter-tier T3 --filter-tier T5 --filter-tier T6"
    )


if __name__ == "__main__":
    main()
