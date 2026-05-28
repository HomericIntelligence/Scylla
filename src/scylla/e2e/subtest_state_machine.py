"""State machine for subtest-level execution in E2E testing.

This module provides a state machine that advances a single subtest through
discrete, resumable states. Each transition saves a checkpoint, enabling
resume from any point after a crash or kill signal.

State flow for a single subtest (3 sequential states):
  PENDING
    -> RUNS_IN_PROGRESS  (start subtest runs)
    -> RUNS_COMPLETE     (all runs finished)
  Terminal: AGGREGATED | FAILED

"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.core.state_machine import StateMachine, Transition
from scylla.e2e.models import SubtestState

if TYPE_CHECKING:
    from scylla.persistence.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)


class UntilHaltError(Exception):
    """Sentinel raised when --until stops run execution before runs reach a terminal state.

    SubtestStateMachine.advance_to_completion catches this and leaves the subtest
    in RUNS_IN_PROGRESS (preserving state for future resume) without marking FAILED.
    """


# Ordered sequence of states for a normal subtest run
_SUBTEST_STATE_SEQUENCE: list[SubtestState] = [
    SubtestState.PENDING,
    SubtestState.RUNS_IN_PROGRESS,
    SubtestState.RUNS_COMPLETE,
    SubtestState.AGGREGATED,
]

# Terminal states — do not advance further
_SUBTEST_TERMINAL_STATES: frozenset[SubtestState] = frozenset(
    [SubtestState.AGGREGATED, SubtestState.FAILED]
)

# Type alias for subtest transitions using the generic Transition
SubtestTransition = Transition[SubtestState]

# Registry of all valid subtest transitions
SUBTEST_TRANSITION_REGISTRY: list[SubtestTransition] = [
    Transition(
        from_state=SubtestState.PENDING,
        to_state=SubtestState.RUNS_IN_PROGRESS,
        description="Start subtest runs",
    ),
    Transition(
        from_state=SubtestState.RUNS_IN_PROGRESS,
        to_state=SubtestState.RUNS_COMPLETE,
        description="All runs finished",
    ),
    Transition(
        from_state=SubtestState.RUNS_COMPLETE,
        to_state=SubtestState.AGGREGATED,
        description="Aggregate run results",
    ),
]

# Build lookup: from_state -> transition
_SUBTEST_TRANSITION_BY_FROM: dict[SubtestState, SubtestTransition] = {
    t.from_state: t for t in SUBTEST_TRANSITION_REGISTRY
}


def get_next_subtest_transition(current_state: SubtestState) -> SubtestTransition | None:
    """Get the next transition from the current subtest state.

    Args:
        current_state: The current SubtestState

    Returns:
        SubtestTransition to execute next, or None if in a terminal/complete state.

    """
    return _SUBTEST_TRANSITION_BY_FROM.get(current_state)


def is_subtest_terminal_state(state: SubtestState) -> bool:
    """Return True if this subtest state requires no further transitions."""
    return state in _SUBTEST_TERMINAL_STATES


def validate_subtest_transition(from_state: SubtestState, to_state: SubtestState) -> bool:
    """Validate that a subtest state transition is legal.

    Args:
        from_state: Current state
        to_state: Proposed next state

    Returns:
        True if transition is valid

    """
    transition = _SUBTEST_TRANSITION_BY_FROM.get(from_state)
    if transition is None:
        return False
    return transition.to_state == to_state


@dataclass
class SubtestStateMachine:
    """Manages state transitions for a single subtest with checkpoint persistence.

    Delegates to the generic StateMachine[SubtestState] for each subtest, constructing
    a transient instance per call via _sm_for(tier_id, subtest_id).

    Usage:
        ssm = SubtestStateMachine(checkpoint, checkpoint_path)
        while not ssm.is_complete(tier_id, subtest_id):
            new_state = ssm.advance(
                tier_id,
                subtest_id,
                actions={SubtestState.PENDING: start_runs_fn, ...}
            )

    Attributes:
        checkpoint: The experiment checkpoint (mutated in place)
        checkpoint_path: Path to checkpoint file for atomic saves

    """

    checkpoint: E2ECheckpoint
    checkpoint_path: Path

    def get_state(self, tier_id: str, subtest_id: str) -> SubtestState:
        """Get the current SubtestState for a subtest.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier

        Returns:
            Current SubtestState enum value

        """
        state_str = self.checkpoint.get_subtest_state(tier_id, subtest_id)
        try:
            return SubtestState(state_str)
        except ValueError:
            logger.warning(f"Unknown subtest state '{state_str}', treating as PENDING")
            return SubtestState.PENDING

    def is_complete(self, tier_id: str, subtest_id: str) -> bool:
        """Return True if the subtest is in a terminal state.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier

        Returns:
            True if no further transitions are needed

        """
        return is_subtest_terminal_state(self.get_state(tier_id, subtest_id))

    def _sm_for(self, tier_id: str, subtest_id: str) -> StateMachine[SubtestState]:
        """Construct a transient StateMachine instance for a subtest.

        Each call creates a fresh instance with closures capturing tier_id and subtest_id,
        so state access is correctly scoped to the specific subtest.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier

        Returns:
            A StateMachine[SubtestState] configured for this subtest

        """
        from scylla.persistence.checkpoint import save_checkpoint

        def apply(state: SubtestState) -> None:
            self.checkpoint.set_subtest_state(tier_id, subtest_id, state.value)

        def persist(_state: SubtestState) -> None:
            save_checkpoint(self.checkpoint, self.checkpoint_path)

        return StateMachine[SubtestState](
            transitions=SUBTEST_TRANSITION_REGISTRY,
            terminal_states=_SUBTEST_TERMINAL_STATES,
            get_state=lambda: self.get_state(tier_id, subtest_id),
            apply_state=apply,
            persistence_hook=persist,
            label=f"subtest[{tier_id}/{subtest_id}]",
        )

    def advance(
        self,
        tier_id: str,
        subtest_id: str,
        actions: dict[SubtestState, Callable[[], None]],
    ) -> SubtestState:
        """Advance the subtest by one state transition.

        Delegates to the generic StateMachine.advance(), wrapping actions to
        intercept UntilHaltError and force RUNS_IN_PROGRESS state before re-raising.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            actions: Map of from_state -> callable to execute for that transition.
                     If a state is not in the map, the transition is a no-op
                     (state is advanced without side effects).

        Returns:
            The new SubtestState after the transition.

        Raises:
            RuntimeError: If already in a terminal state
            ValueError: If no transition is defined for the current state
            UntilHaltError: If the action raises UntilHaltError (state is advanced to next)

        """
        from scylla.persistence.checkpoint import save_checkpoint

        current = self.get_state(tier_id, subtest_id)

        if is_subtest_terminal_state(current):
            raise RuntimeError(
                f"Cannot advance subtest {tier_id}/{subtest_id} from terminal state {current.value}"
            )

        transition = get_next_subtest_transition(current)
        if transition is None:
            raise ValueError(
                f"No transition defined from subtest state {current.value} "
                f"for {tier_id}/{subtest_id}"
            )

        logger.debug(
            f"[{tier_id}/{subtest_id}] {current.value} -> "
            f"{transition.to_state.value}: {transition.description}"
        )

        halt_error: UntilHaltError | None = None
        action = actions.get(current)
        if action is not None:
            try:
                action()
            except UntilHaltError as _e:
                halt_error = _e
                logger.info(
                    f"[{tier_id}/{subtest_id}] {current.value} -> {transition.to_state.value}: "
                    f"{transition.description} (UntilHaltError)"
                )
            else:
                logger.info(
                    f"[{tier_id}/{subtest_id}] {current.value} -> {transition.to_state.value}: "
                    f"{transition.description}"
                )

        if halt_error is not None:
            saved_state = SubtestState.RUNS_IN_PROGRESS
        else:
            saved_state = transition.to_state

        self.checkpoint.set_subtest_state(tier_id, subtest_id, saved_state.value)
        save_checkpoint(self.checkpoint, self.checkpoint_path)

        if halt_error is not None:
            raise halt_error

        return transition.to_state

    def advance_to_completion(
        self,
        tier_id: str,
        subtest_id: str,
        actions: dict[SubtestState, Callable[[], None]],
        until_state: SubtestState | None = None,
    ) -> SubtestState:
        """Advance the subtest through all states until AGGREGATED is reached.

        Handles UntilHaltError specially: caught and logged without marking FAILED.
        ShutdownInterruptedError leaves state unchanged and re-raises.

        If until_state is specified, the subtest stops cleanly once that state is
        reached (inclusive): the action that transitions INTO until_state IS
        executed, but no further transitions run.

        Args:
            tier_id: Tier identifier
            subtest_id: Subtest identifier
            actions: Map of from_state -> callable
            until_state: Optional state at which to stop early (inclusive).
                The machine stops after transitioning into this state, without
                marking FAILED, preserving state for future resume.

        Returns:
            Final SubtestState (AGGREGATED, FAILED, or until_state)

        """
        from scylla.e2e.shutdown import ShutdownInterruptedError
        from scylla.persistence.checkpoint import save_checkpoint

        try:
            while not self.is_complete(tier_id, subtest_id):
                new_state = self.advance(tier_id, subtest_id, actions)
                if until_state is not None and new_state == until_state:
                    logger.info(
                        f"[{tier_id}/{subtest_id}] Reached --until target state: "
                        f"{until_state.value}"
                    )
                    break
        except UntilHaltError as e:
            logger.info(f"[{tier_id}/{subtest_id}] {e}")
        except ShutdownInterruptedError:
            current = self.get_state(tier_id, subtest_id)
            logger.warning(
                f"[{tier_id}/{subtest_id}] Shutdown interrupted at {current.value} "
                "— subtest left resumable (not FAILED)"
            )
            raise
        except Exception:
            self.checkpoint.set_subtest_state(tier_id, subtest_id, SubtestState.FAILED.value)
            save_checkpoint(self.checkpoint, self.checkpoint_path)
            raise

        return self.get_state(tier_id, subtest_id)
