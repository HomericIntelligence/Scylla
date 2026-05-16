"""State machine for fine-grained run execution in E2E testing.

This module provides a state machine that advances a single run through
discrete, resumable states. Each transition saves a checkpoint, enabling
resume from any point after a crash or kill signal.

State flow for a single run (18 sequential states):
  PENDING
    -> DIR_STRUCTURE_CREATED    (create run_NN/, agent/, judge/ dirs)
    -> WORKTREE_CREATED          (git worktree add)
    -> SYMLINKS_APPLIED          (tier resources symlinked to workspace)
    -> CONFIG_COMMITTED          (CLAUDE.md, settings.json, git commit)
    -> BASELINE_CAPTURED         (build pipeline baseline, first run only)
    -> PROMPT_WRITTEN            (task_prompt.md written, thinking keyword injected)
    -> REPLAY_GENERATED          (adapter command built, replay.sh generated)
    -> AGENT_COMPLETE            (agent executed, outputs saved)
    -> AGENT_CHANGES_COMMITTED   (agent changes committed to worktree branch)
    -> DIFF_CAPTURED             (git diff captured, workspace state saved)
    -> PROMOTED_TO_COMPLETED     (run dir moved from in_progress/ to completed/)
    -> JUDGE_PIPELINE_RUN        (build pipeline run on agent-modified workspace)
    -> JUDGE_PROMPT_BUILT        (full judge prompt assembled)
    -> JUDGE_COMPLETE            (judge executed, consensus, results saved)
    -> RUN_FINALIZED             (RunResult built, run_result.json saved)
    -> REPORT_WRITTEN            (report.md and report.json generated)
    -> CHECKPOINTED              (checkpoint saved)
    -> WORKTREE_CLEANED          (worktree removed)
  Terminal: FAILED | RATE_LIMITED
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.models import RunState

if TYPE_CHECKING:
    from scylla.persistence.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)


# Ordered sequence of states for a normal (non-failed) run
_RUN_STATE_SEQUENCE: list[RunState] = [
    RunState.PENDING,
    RunState.DIR_STRUCTURE_CREATED,
    RunState.WORKTREE_CREATED,
    RunState.SYMLINKS_APPLIED,
    RunState.CONFIG_COMMITTED,
    RunState.BASELINE_CAPTURED,
    RunState.PROMPT_WRITTEN,
    RunState.REPLAY_GENERATED,
    RunState.AGENT_COMPLETE,
    RunState.AGENT_CHANGES_COMMITTED,
    RunState.DIFF_CAPTURED,
    RunState.PROMOTED_TO_COMPLETED,
    RunState.JUDGE_PIPELINE_RUN,
    RunState.JUDGE_PROMPT_BUILT,
    RunState.JUDGE_COMPLETE,
    RunState.RUN_FINALIZED,
    RunState.REPORT_WRITTEN,
    RunState.CHECKPOINTED,
    RunState.WORKTREE_CLEANED,
]

# Terminal states — do not advance further
_TERMINAL_STATES: frozenset[RunState] = frozenset(
    [RunState.WORKTREE_CLEANED, RunState.FAILED, RunState.RATE_LIMITED]
)

# Precompute index map for O(1) ordering lookups
_RUN_STATE_INDEX: dict[RunState, int] = {
    state: idx for idx, state in enumerate(_RUN_STATE_SEQUENCE)
}


def is_at_or_past_state(current: RunState, target: RunState) -> bool:
    """Return True if current is at or past target in the run sequence.

    States not in the normal sequence (FAILED, RATE_LIMITED) return False.
    """
    cur_idx = _RUN_STATE_INDEX.get(current)
    tgt_idx = _RUN_STATE_INDEX.get(target)
    if cur_idx is None or tgt_idx is None:
        return False
    return cur_idx >= tgt_idx


@dataclass
class StateTransition:
    """Describes a single state transition in the run state machine.

    Attributes:
        from_state: State before this transition
        to_state: State after this transition completes successfully
        description: Human-readable description for logging

    """

    from_state: RunState
    to_state: RunState
    description: str


# Registry of all valid transitions.
# Actions (the callables that perform the work) are injected at runtime
# by callers who hold references to the appropriate stage functions.
TRANSITION_REGISTRY: list[StateTransition] = [
    StateTransition(
        from_state=RunState.PENDING,
        to_state=RunState.DIR_STRUCTURE_CREATED,
        description="Create run_NN/, agent/, judge/ directories",
    ),
    StateTransition(
        from_state=RunState.DIR_STRUCTURE_CREATED,
        to_state=RunState.WORKTREE_CREATED,
        description="Create git worktree",
    ),
    StateTransition(
        from_state=RunState.WORKTREE_CREATED,
        to_state=RunState.SYMLINKS_APPLIED,
        description="Symlink tier resources to workspace",
    ),
    StateTransition(
        from_state=RunState.SYMLINKS_APPLIED,
        to_state=RunState.CONFIG_COMMITTED,
        description="Write CLAUDE.md and settings.json, git commit",
    ),
    StateTransition(
        from_state=RunState.CONFIG_COMMITTED,
        to_state=RunState.BASELINE_CAPTURED,
        description="Capture pipeline baseline (compileall, ruff, pytest, pre-commit)",
    ),
    StateTransition(
        from_state=RunState.BASELINE_CAPTURED,
        to_state=RunState.PROMPT_WRITTEN,
        description="Write task_prompt.md, inject thinking keyword if configured",
    ),
    StateTransition(
        from_state=RunState.PROMPT_WRITTEN,
        to_state=RunState.REPLAY_GENERATED,
        description="Build adapter command, generate replay.sh",
    ),
    StateTransition(
        from_state=RunState.REPLAY_GENERATED,
        to_state=RunState.AGENT_COMPLETE,
        description="Execute agent in isolated workspace",
    ),
    StateTransition(
        from_state=RunState.AGENT_COMPLETE,
        to_state=RunState.AGENT_CHANGES_COMMITTED,
        description="Commit agent changes to worktree branch",
    ),
    StateTransition(
        from_state=RunState.AGENT_CHANGES_COMMITTED,
        to_state=RunState.DIFF_CAPTURED,
        description="Capture git diff and workspace state",
    ),
    StateTransition(
        from_state=RunState.DIFF_CAPTURED,
        to_state=RunState.PROMOTED_TO_COMPLETED,
        description="Move run directory from in_progress/ to completed/",
    ),
    StateTransition(
        from_state=RunState.PROMOTED_TO_COMPLETED,
        to_state=RunState.JUDGE_PIPELINE_RUN,
        description="Run build pipeline on agent-modified workspace",
    ),
    StateTransition(
        from_state=RunState.JUDGE_PIPELINE_RUN,
        to_state=RunState.JUDGE_PROMPT_BUILT,
        description="Assemble judge prompt with all context",
    ),
    StateTransition(
        from_state=RunState.JUDGE_PROMPT_BUILT,
        to_state=RunState.JUDGE_COMPLETE,
        description="Execute Claude CLI judge(s), compute consensus",
    ),
    StateTransition(
        from_state=RunState.JUDGE_COMPLETE,
        to_state=RunState.RUN_FINALIZED,
        description="Build E2ERunResult, save run_result.json",
    ),
    StateTransition(
        from_state=RunState.RUN_FINALIZED,
        to_state=RunState.REPORT_WRITTEN,
        description="Generate report.md and report.json",
    ),
    StateTransition(
        from_state=RunState.REPORT_WRITTEN,
        to_state=RunState.CHECKPOINTED,
        description="Save checkpoint (no-op — auto-saved after each transition)",
    ),
    StateTransition(
        from_state=RunState.CHECKPOINTED,
        to_state=RunState.WORKTREE_CLEANED,
        description="Remove worktree for passed runs",
    ),
]

# Build lookup: from_state -> transition
_TRANSITION_BY_FROM: dict[RunState, StateTransition] = {
    t.from_state: t for t in TRANSITION_REGISTRY
}


def get_next_transition(current_state: RunState) -> StateTransition | None:
    """Get the next transition from the current state.

    Args:
        current_state: The current RunState

    Returns:
        StateTransition to execute next, or None if in a terminal/complete state.

    """
    return _TRANSITION_BY_FROM.get(current_state)


def is_terminal_state(state: RunState) -> bool:
    """Return True if this state requires no further transitions."""
    return state in _TERMINAL_STATES


def validate_transition(from_state: RunState, to_state: RunState) -> bool:
    """Validate that a state transition is legal.

    Args:
        from_state: Current state
        to_state: Proposed next state

    Returns:
        True if transition is valid

    """
    transition = _TRANSITION_BY_FROM.get(from_state)
    if transition is None:
        return False
    return transition.to_state == to_state


@dataclass
class StateMachine:
    """Manages state transitions for a single run with checkpoint persistence.

    Each call to advance() executes the next action, updates the run state
    in the checkpoint, and saves the checkpoint atomically.

    Usage:
        sm = StateMachine(checkpoint, checkpoint_path)
        while not sm.is_complete(tier_id, subtest_id, run_num):
            new_state = sm.advance(
                tier_id, subtest_id, run_num,
                actions={RunState.PENDING: create_dir_structure_fn, ...}
            )

    Attributes:
        checkpoint: The experiment checkpoint (mutated in place)
        checkpoint_path: Path to checkpoint file for atomic saves

    """

    checkpoint: E2ECheckpoint
    checkpoint_path: Path

    def get_state(self, tier_id: str, subtest_id: str, run_num: int) -> RunState:
        """Get the current RunState for a run.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            run_num: Run number (1-based)

        Returns:
            Current RunState enum value

        """
        state_str = self.checkpoint.get_run_state(tier_id, subtest_id, run_num)
        try:
            return RunState(state_str)
        except ValueError:
            logger.warning(f"Unknown run state '{state_str}', treating as PENDING")
            return RunState.PENDING

    def is_complete(self, tier_id: str, subtest_id: str, run_num: int) -> bool:
        """Return True if the run is in a terminal state.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            run_num: Run number (1-based)

        Returns:
            True if no further transitions are needed

        """
        return is_terminal_state(self.get_state(tier_id, subtest_id, run_num))

    def advance(
        self,
        tier_id: str,
        subtest_id: str,
        run_num: int,
        actions: dict[RunState, Callable[[], None]],
    ) -> RunState:
        """Advance the run by one state transition.

        1. Reads the current state from the checkpoint.
        2. Looks up the next transition in the registry.
        3. Executes the transition action (if provided).
        4. Updates the checkpoint state.
        5. Saves the checkpoint atomically.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            run_num: Run number (1-based)
            actions: Map of from_state -> callable to execute for that transition.
                     If a state is not in the map, the transition is a no-op
                     (state is advanced without side effects).

        Returns:
            The new RunState after the transition.

        Raises:
            RuntimeError: If already in a terminal state
            ValueError: If no transition is defined for the current state

        """
        from scylla.persistence.checkpoint import save_checkpoint

        current = self.get_state(tier_id, subtest_id, run_num)

        if is_terminal_state(current):
            raise RuntimeError(
                f"Cannot advance run {tier_id}/{subtest_id}/run_{run_num:02d} "
                f"from terminal state {current.value}"
            )

        transition = get_next_transition(current)
        if transition is None:
            raise ValueError(
                f"No transition defined from state {current.value} "
                f"for run {tier_id}/{subtest_id}/run_{run_num:02d}"
            )

        logger.debug(
            f"[{tier_id}/{subtest_id}/run_{run_num:02d}] "
            f"{current.value} -> {transition.to_state.value}: {transition.description}"
        )

        # Execute the action if provided
        action = actions.get(current)
        if action is not None:
            _t0 = time.monotonic()
            action()
            _elapsed = time.monotonic() - _t0
            logger.info(
                f"[{tier_id}/{subtest_id}/run_{run_num:02d}] "
                f"{current.value} -> {transition.to_state.value}: "
                f"{transition.description} ({_elapsed:.1f}s)"
            )

        # Update state in checkpoint
        self.checkpoint.set_run_state(tier_id, subtest_id, run_num, transition.to_state.value)

        # Save checkpoint atomically
        save_checkpoint(self.checkpoint, self.checkpoint_path)

        return transition.to_state

    def advance_to_completion(
        self,
        tier_id: str,
        subtest_id: str,
        run_num: int,
        actions: dict[RunState, Callable[[], None]],
        until_state: RunState | None = None,
    ) -> RunState:
        """Advance the run through all states until a terminal state is reached.

        Useful for running a complete run from start or resuming from any state.
        On exception, the run is marked as FAILED in the checkpoint.

        If until_state is specified, the run stops cleanly once that state is
        reached (inclusive): the action that transitions INTO until_state IS
        executed, but no further transitions run.  The run is not marked FAILED.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            run_num: Run number (1-based)
            actions: Map of from_state -> callable
            until_state: Optional state at which to stop early (inclusive).
                The machine stops after transitioning into this state, without
                marking FAILED, preserving state for future resume.

        Returns:
            Final RunState (WORKTREE_CLEANED, FAILED, RATE_LIMITED, or until_state)

        """
        from scylla.e2e.rate_limit import RateLimitError
        from scylla.e2e.shutdown import ShutdownInterruptedError
        from scylla.persistence.checkpoint import save_checkpoint

        # Early return if already at or past the --until target state
        if until_state is not None:
            current = self.get_state(tier_id, subtest_id, run_num)
            if is_at_or_past_state(current, until_state):
                logger.info(
                    f"[{tier_id}/{subtest_id}/run_{run_num:02d}] "
                    f"Already at or past --until target state: {until_state.value} "
                    f"(current: {current.value})"
                )
                return current

        try:
            while not self.is_complete(tier_id, subtest_id, run_num):
                new_state = self.advance(tier_id, subtest_id, run_num, actions)
                if until_state is not None and new_state == until_state:
                    logger.info(
                        f"[{tier_id}/{subtest_id}/run_{run_num:02d}] "
                        f"Reached --until target state: {until_state.value}"
                    )
                    break
        except RateLimitError:
            self.checkpoint.set_run_state(tier_id, subtest_id, run_num, RunState.RATE_LIMITED.value)
            save_checkpoint(self.checkpoint, self.checkpoint_path)
            raise
        except ShutdownInterruptedError:
            # Ctrl+C interrupted this run mid-stage — leave it at its last successfully
            # checkpointed state so it can be cleanly resumed on the next invocation.
            current = self.get_state(tier_id, subtest_id, run_num)
            logger.warning(
                f"[{tier_id}/{subtest_id}/run_{run_num:02d}] "
                f"Shutdown interrupted at {current.value} — run left resumable (not FAILED)"
            )
            raise
        except Exception as e:
            logger.error(
                f"Run {tier_id}/{subtest_id}/run_{run_num:02d} failed in state "
                f"{self.get_state(tier_id, subtest_id, run_num).value}: {e}"
            )
            self.checkpoint.set_run_state(tier_id, subtest_id, run_num, RunState.FAILED.value)
            save_checkpoint(self.checkpoint, self.checkpoint_path)
            raise

        return self.get_state(tier_id, subtest_id, run_num)
