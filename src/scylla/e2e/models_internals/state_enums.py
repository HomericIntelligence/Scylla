"""State enums and tier identifiers for the E2E testing framework."""

from __future__ import annotations

from enum import Enum

# Grade ordering for min/max calculations (F=worst, S=best)
GRADE_ORDER: list[str] = ["F", "D", "C", "B", "A", "S"]


class RunState(str, Enum):
    """Fine-grained states for a single run within a subtest.

    Each state represents a discrete, resumable checkpoint in the run lifecycle.
    The state machine advances through these states sequentially, saving the
    checkpoint after each transition to enable resume from any point.

    Sequential states (16):
      PENDING -> DIR_STRUCTURE_CREATED -> WORKTREE_CREATED -> SYMLINKS_APPLIED
      -> CONFIG_COMMITTED -> BASELINE_CAPTURED -> PROMPT_WRITTEN -> REPLAY_GENERATED
      -> AGENT_COMPLETE -> AGENT_CHANGES_COMMITTED
      -> DIFF_CAPTURED -> PROMOTED_TO_COMPLETED -> JUDGE_PIPELINE_RUN -> JUDGE_PROMPT_BUILT
      -> JUDGE_COMPLETE -> RUN_FINALIZED -> REPORT_WRITTEN -> CHECKPOINTED -> WORKTREE_CLEANED
    Terminal (2): FAILED | RATE_LIMITED
    """

    PENDING = "pending"
    DIR_STRUCTURE_CREATED = "dir_structure_created"  # run_dir, agent/, judge/ created
    WORKTREE_CREATED = "worktree_created"  # git worktree created
    SYMLINKS_APPLIED = "symlinks_applied"  # tier resources symlinked to workspace
    CONFIG_COMMITTED = "config_committed"  # CLAUDE.md, settings.json, git commit
    BASELINE_CAPTURED = "baseline_captured"  # build pipeline baseline (first run only)
    PROMPT_WRITTEN = "prompt_written"  # task_prompt.md written, thinking keyword injected
    REPLAY_GENERATED = "replay_generated"  # adapter command built, replay.sh generated
    AGENT_COMPLETE = "agent_complete"  # agent executed, outputs saved
    AGENT_CHANGES_COMMITTED = "agent_changes_committed"  # agent changes committed to branch
    DIFF_CAPTURED = "diff_captured"  # git diff captured, workspace state saved
    PROMOTED_TO_COMPLETED = "promoted_to_completed"  # run dir moved to completed/
    JUDGE_PIPELINE_RUN = "judge_pipeline_run"  # build pipeline run on agent-modified workspace
    JUDGE_PROMPT_BUILT = "judge_prompt_built"  # full judge prompt assembled
    JUDGE_COMPLETE = "judge_complete"  # judge executed, consensus computed, results saved
    RUN_FINALIZED = "run_finalized"  # E2ERunResult built, run_result.json saved
    REPORT_WRITTEN = "report_written"  # report.md and report.json generated
    CHECKPOINTED = "checkpointed"  # checkpoint saved with this run's state
    WORKTREE_CLEANED = "worktree_cleaned"  # git worktree removed
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


class SubtestState(str, Enum):
    """States for a single subtest's lifecycle."""

    PENDING = "pending"
    RUNS_IN_PROGRESS = "runs_in_progress"
    RUNS_COMPLETE = "runs_complete"
    AGGREGATED = "aggregated"
    FAILED = "failed"


class TierState(str, Enum):
    """States for a single tier's lifecycle."""

    PENDING = "pending"
    CONFIG_LOADED = "config_loaded"
    SUBTESTS_RUNNING = "subtests_running"
    SUBTESTS_COMPLETE = "subtests_complete"
    BEST_SELECTED = "best_selected"
    REPORTS_GENERATED = "reports_generated"
    COMPLETE = "complete"
    FAILED = "failed"


class ExperimentState(str, Enum):
    """States for the overall experiment lifecycle."""

    INITIALIZING = "initializing"
    DIR_CREATED = "dir_created"  # Experiment directory tree created
    REPO_CLONED = "repo_cloned"
    TIERS_RUNNING = "tiers_running"
    TIERS_COMPLETE = "tiers_complete"
    REPORTS_GENERATED = "reports_generated"
    COMPLETE = "complete"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class TierID(Enum):
    """Tier identifiers for the evaluation framework.

    Tiers represent increasing levels of agent capability:
    - T0: Prompts - System prompt ablation (empty → full CLAUDE.md)
    - T1: Skills - Domain expertise via installed skills
    - T2: Tooling - External tools and MCP servers
    - T3: Delegation - Flat multi-agent with specialist agents
    - T4: Hierarchy - Nested orchestration with orchestrators
    - T5: Hybrid - Best combinations and permutations
    - T6: Super - Everything enabled at maximum capability
    """

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"

    @classmethod
    def from_string(cls, value: str) -> TierID:
        """Create TierID from string value."""
        return cls(value.upper())

    def __lt__(self, other: TierID) -> bool:
        """Enable sorting of tiers."""
        order = list(TierID)
        return order.index(self) < order.index(other)


# Tier dependency map for parallel execution
# T0-T4 are independent (can run in parallel)
# T5 depends on T0-T4 (inherits from best result)
# T6 depends on T5 (inherits from T5)
TIER_DEPENDENCIES: dict[TierID, list[TierID]] = {
    TierID.T0: [],
    TierID.T1: [],
    TierID.T2: [],
    TierID.T3: [],
    TierID.T4: [],
    TierID.T5: [TierID.T0, TierID.T1, TierID.T2, TierID.T3, TierID.T4],
    TierID.T6: [TierID.T5],
}
