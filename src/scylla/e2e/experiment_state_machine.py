"""State machine for experiment-level execution in E2E testing.

This module provides a state machine that advances the overall experiment through
discrete, resumable states. Each transition saves a checkpoint, enabling resume
from any point after a crash or kill signal.

State flow for an experiment (6 sequential states):
  INITIALIZING
    -> DIR_CREATED        (create experiment directory tree)
    -> REPO_CLONED        (clone/setup base repository)
    -> TIERS_RUNNING      (begin tier group execution)
    -> TIERS_COMPLETE     (all tiers finished)
    -> REPORTS_GENERATED  (generate experiment reports)
  Terminal: COMPLETE | INTERRUPTED | FAILED

Implementation note: the transition table, hook plumbing, and
advance-to-completion driver live in :mod:`scylla.core.state_machine` as a
generic ``StateMachine[TState]``. This module composes the generic with the
experiment-specific state enum, terminal set, and checkpoint persistence;
the public API (``ExperimentStateMachine``, ``EXPERIMENT_TRANSITION_REGISTRY``,
``get_next_experiment_transition``, ``is_experiment_terminal_state``,
``validate_experiment_transition``) is unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.core.state_machine import StateMachine, Transition
from scylla.e2e.models import ExperimentState

if TYPE_CHECKING:
    from scylla.e2e.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)


# Ordered sequence of states for a normal experiment run
_EXPERIMENT_STATE_SEQUENCE: list[ExperimentState] = [
    ExperimentState.INITIALIZING,
    ExperimentState.DIR_CREATED,
    ExperimentState.REPO_CLONED,
    ExperimentState.TIERS_RUNNING,
    ExperimentState.TIERS_COMPLETE,
    ExperimentState.REPORTS_GENERATED,
    ExperimentState.COMPLETE,
]

# Terminal states — do not advance further
_EXPERIMENT_TERMINAL_STATES: frozenset[ExperimentState] = frozenset(
    [ExperimentState.COMPLETE, ExperimentState.INTERRUPTED, ExperimentState.FAILED]
)


# Backwards-compatible alias: pre-port code used ``ExperimentTransition`` as a
# dataclass. The generic ``Transition[ExperimentState]`` is a drop-in replacement
# (same field names and types). Keep the alias to avoid breaking importers.
ExperimentTransition = Transition[ExperimentState]


# Registry of all valid experiment transitions
EXPERIMENT_TRANSITION_REGISTRY: list[Transition[ExperimentState]] = [
    Transition(
        from_state=ExperimentState.INITIALIZING,
        to_state=ExperimentState.DIR_CREATED,
        description="Create experiment directory tree",
    ),
    Transition(
        from_state=ExperimentState.DIR_CREATED,
        to_state=ExperimentState.REPO_CLONED,
        description="Clone/setup base repository",
    ),
    Transition(
        from_state=ExperimentState.REPO_CLONED,
        to_state=ExperimentState.TIERS_RUNNING,
        description="Begin tier group execution",
    ),
    Transition(
        from_state=ExperimentState.TIERS_RUNNING,
        to_state=ExperimentState.TIERS_COMPLETE,
        description="Execute all tier groups",
    ),
    Transition(
        from_state=ExperimentState.TIERS_COMPLETE,
        to_state=ExperimentState.REPORTS_GENERATED,
        description="Generate experiment reports",
    ),
    Transition(
        from_state=ExperimentState.REPORTS_GENERATED,
        to_state=ExperimentState.COMPLETE,
        description="Mark experiment complete",
    ),
]

# Build lookup: from_state -> transition
_EXPERIMENT_TRANSITION_BY_FROM: dict[ExperimentState, Transition[ExperimentState]] = {
    t.from_state: t for t in EXPERIMENT_TRANSITION_REGISTRY
}


def get_next_experiment_transition(
    current_state: ExperimentState,
) -> Transition[ExperimentState] | None:
    """Get the next transition from the current experiment state.

    Args:
        current_state: The current ExperimentState

    Returns:
        Transition to execute next, or None if in a terminal/complete state.

    """
    return _EXPERIMENT_TRANSITION_BY_FROM.get(current_state)


def is_experiment_terminal_state(state: ExperimentState) -> bool:
    """Return True if this experiment state requires no further transitions."""
    return state in _EXPERIMENT_TERMINAL_STATES


def validate_experiment_transition(from_state: ExperimentState, to_state: ExperimentState) -> bool:
    """Validate that an experiment state transition is legal.

    Args:
        from_state: Current state
        to_state: Proposed next state

    Returns:
        True if transition is valid

    """
    transition = _EXPERIMENT_TRANSITION_BY_FROM.get(from_state)
    if transition is None:
        return False
    return transition.to_state == to_state


@dataclass
class ExperimentStateMachine:
    """Manages state transitions for the experiment with checkpoint persistence.

    Each call to advance() executes the next action, updates the experiment state
    in the checkpoint, and saves the checkpoint atomically.

    Usage:
        esm = ExperimentStateMachine(checkpoint, checkpoint_path)
        while not esm.is_complete():
            new_state = esm.advance(
                actions={ExperimentState.INITIALIZING: create_dirs_fn, ...}
            )

    Attributes:
        checkpoint: The experiment checkpoint (mutated in place)
        checkpoint_path: Path to checkpoint file for atomic saves

    """

    checkpoint: E2ECheckpoint
    checkpoint_path: Path
    _sm: StateMachine[ExperimentState] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Wire the generic StateMachine with experiment-specific config."""
        self._sm = StateMachine[ExperimentState](
            transitions=EXPERIMENT_TRANSITION_REGISTRY,
            terminal_states=_EXPERIMENT_TERMINAL_STATES,
            get_state=self.get_state,
            apply_state=self._apply_state,
            persistence_hook=self._persist,
            label="experiment",
        )

    # -- generic-state-machine adapters --------------------------------------

    def _apply_state(self, new_state: ExperimentState) -> None:
        """Write the new state into the in-memory checkpoint."""
        self.checkpoint.experiment_state = new_state.value

    def _persist(self, _new_state: ExperimentState) -> None:
        """Atomically save the checkpoint to disk after a transition."""
        from scylla.e2e.checkpoint import save_checkpoint

        save_checkpoint(self.checkpoint, self.checkpoint_path)

    # -- public API ----------------------------------------------------------

    def get_state(self) -> ExperimentState:
        """Get the current ExperimentState.

        Returns:
            Current ExperimentState enum value

        """
        state_str = self.checkpoint.experiment_state
        try:
            return ExperimentState(state_str)
        except ValueError:
            logger.warning(f"Unknown experiment state '{state_str}', treating as INITIALIZING")
            return ExperimentState.INITIALIZING

    def is_complete(self) -> bool:
        """Return True if the experiment is in a terminal state.

        Returns:
            True if no further transitions are needed

        """
        return is_experiment_terminal_state(self.get_state())

    def advance(
        self,
        actions: dict[ExperimentState, Callable[[], None]],
    ) -> ExperimentState:
        """Advance the experiment by one state transition.

        1. Reads the current state from the checkpoint.
        2. Looks up the next transition in the registry.
        3. Executes the transition action (if provided).
        4. Updates the checkpoint state.
        5. Saves the checkpoint atomically.

        Args:
            actions: Map of from_state -> callable to execute for that transition.
                     If a state is not in the map, the transition is a no-op
                     (state is advanced without side effects).

        Returns:
            The new ExperimentState after the transition.

        Raises:
            RuntimeError: If already in a terminal state
            ValueError: If no transition is defined for the current state

        """
        return self._sm.advance(actions)

    def advance_to_completion(
        self,
        actions: dict[ExperimentState, Callable[[], None]],
        until_state: ExperimentState | None = None,
    ) -> ExperimentState:
        """Advance the experiment through all states until COMPLETE is reached.

        On exception, marks experiment as FAILED in the checkpoint. RateLimitError
        and ShutdownInterruptedError mark the experiment as INTERRUPTED instead
        (resumable, not terminal failure).

        If until_state is specified, the experiment stops cleanly once that state
        is reached (inclusive): the action that transitions INTO until_state IS
        executed, but no further transitions run.

        Args:
            actions: Map of from_state -> callable
            until_state: Optional state at which to stop early (inclusive).
                The machine stops after transitioning into this state, without
                error, preserving state for future resume.

        Returns:
            Final ExperimentState (COMPLETE, FAILED, INTERRUPTED, or until_state)

        """
        from scylla.e2e.rate_limit import RateLimitError
        from scylla.e2e.shutdown import ShutdownInterruptedError

        return self._sm.advance_to_completion(
            actions,
            until_state=until_state,
            error_state_map=[
                (RateLimitError, ExperimentState.INTERRUPTED),
                (ShutdownInterruptedError, ExperimentState.INTERRUPTED),
            ],
            failure_state=ExperimentState.FAILED,
        )
