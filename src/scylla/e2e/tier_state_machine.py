"""State machine for tier-level execution in E2E testing.

This module provides a state machine that advances a single tier through
discrete, resumable states. Each transition saves a checkpoint, enabling
resume from any point after a crash or kill signal.

State flow for a single tier (6 sequential states):
  PENDING
    -> CONFIG_LOADED      (load tier config YAML)
    -> SUBTESTS_RUNNING   (start subtest execution)
    -> SUBTESTS_COMPLETE  (all subtests finished)
    -> BEST_SELECTED      (select best subtest by CoP)
    -> REPORTS_GENERATED  (generate tier reports)
  Terminal: COMPLETE

"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.core.state_machine import StateMachine, Transition
from scylla.e2e.models import TierState

if TYPE_CHECKING:
    from scylla.persistence.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)


# Ordered sequence of states for a normal tier run
_TIER_STATE_SEQUENCE: list[TierState] = [
    TierState.PENDING,
    TierState.CONFIG_LOADED,
    TierState.SUBTESTS_RUNNING,
    TierState.SUBTESTS_COMPLETE,
    TierState.BEST_SELECTED,
    TierState.REPORTS_GENERATED,
    TierState.COMPLETE,
]

# Terminal states — do not advance further
_TIER_TERMINAL_STATES: frozenset[TierState] = frozenset([TierState.COMPLETE, TierState.FAILED])

# Type alias for tier transitions using the generic Transition
TierTransition = Transition[TierState]

# Registry of all valid tier transitions
TIER_TRANSITION_REGISTRY: list[TierTransition] = [
    Transition(
        from_state=TierState.PENDING,
        to_state=TierState.CONFIG_LOADED,
        description="Load tier config YAML",
    ),
    Transition(
        from_state=TierState.CONFIG_LOADED,
        to_state=TierState.SUBTESTS_RUNNING,
        description="Start subtest execution",
    ),
    Transition(
        from_state=TierState.SUBTESTS_RUNNING,
        to_state=TierState.SUBTESTS_COMPLETE,
        description="Execute all subtests",
    ),
    Transition(
        from_state=TierState.SUBTESTS_COMPLETE,
        to_state=TierState.BEST_SELECTED,
        description="Select best subtest by CoP",
    ),
    Transition(
        from_state=TierState.BEST_SELECTED,
        to_state=TierState.REPORTS_GENERATED,
        description="Generate tier reports",
    ),
    Transition(
        from_state=TierState.REPORTS_GENERATED,
        to_state=TierState.COMPLETE,
        description="Mark tier complete",
    ),
]

# Build lookup: from_state -> transition
_TIER_TRANSITION_BY_FROM: dict[TierState, TierTransition] = {
    t.from_state: t for t in TIER_TRANSITION_REGISTRY
}


def get_next_tier_transition(current_state: TierState) -> TierTransition | None:
    """Get the next transition from the current tier state.

    Args:
        current_state: The current TierState

    Returns:
        TierTransition to execute next, or None if in a terminal/complete state.

    """
    return _TIER_TRANSITION_BY_FROM.get(current_state)


def is_tier_terminal_state(state: TierState) -> bool:
    """Return True if this tier state requires no further transitions."""
    return state in _TIER_TERMINAL_STATES


def validate_tier_transition(from_state: TierState, to_state: TierState) -> bool:
    """Validate that a tier state transition is legal.

    Args:
        from_state: Current state
        to_state: Proposed next state

    Returns:
        True if transition is valid

    """
    transition = _TIER_TRANSITION_BY_FROM.get(from_state)
    if transition is None:
        return False
    return transition.to_state == to_state


@dataclass
class TierStateMachine:
    """Manages state transitions for a single tier with checkpoint persistence.

    Delegates to the generic StateMachine[TierState] for each tier, constructing
    a transient instance per call via _sm_for(tier_id).

    Usage:
        tsm = TierStateMachine(checkpoint, checkpoint_path)
        while not tsm.is_complete(tier_id):
            new_state = tsm.advance(
                tier_id,
                actions={TierState.PENDING: load_config_fn, ...}
            )

    Attributes:
        checkpoint: The experiment checkpoint (mutated in place)
        checkpoint_path: Path to checkpoint file for atomic saves

    """

    checkpoint: E2ECheckpoint
    checkpoint_path: Path

    def get_state(self, tier_id: str) -> TierState:
        """Get the current TierState for a tier.

        Args:
            tier_id: Tier identifier

        Returns:
            Current TierState enum value

        """
        state_str = self.checkpoint.get_tier_state(tier_id)
        try:
            return TierState(state_str)
        except ValueError:
            logger.warning(f"Unknown tier state '{state_str}', treating as PENDING")
            return TierState.PENDING

    def is_complete(self, tier_id: str) -> bool:
        """Return True if the tier is in a terminal state.

        Args:
            tier_id: Tier identifier

        Returns:
            True if no further transitions are needed

        """
        return is_tier_terminal_state(self.get_state(tier_id))

    def _sm_for(self, tier_id: str) -> StateMachine[TierState]:
        """Construct a transient StateMachine instance for a tier.

        Each call creates a fresh instance with closures capturing tier_id,
        so state access is correctly scoped to the specific tier.

        Args:
            tier_id: Tier identifier

        Returns:
            A StateMachine[TierState] configured for this tier

        """
        from scylla.persistence.checkpoint import save_checkpoint

        def apply(state: TierState) -> None:
            self.checkpoint.set_tier_state(tier_id, state.value)

        def persist(_state: TierState) -> None:
            save_checkpoint(self.checkpoint, self.checkpoint_path)

        return StateMachine[TierState](
            transitions=TIER_TRANSITION_REGISTRY,
            terminal_states=_TIER_TERMINAL_STATES,
            get_state=lambda: self.get_state(tier_id),
            apply_state=apply,
            persistence_hook=persist,
            label=f"tier[{tier_id}]",
        )

    def advance(
        self,
        tier_id: str,
        actions: dict[TierState, Callable[[], None]],
    ) -> TierState:
        """Advance the tier by one state transition.

        Delegates to the generic StateMachine.advance().

        Args:
            tier_id: Tier identifier
            actions: Map of from_state -> callable to execute for that transition.
                     If a state is not in the map, the transition is a no-op
                     (state is advanced without side effects).

        Returns:
            The new TierState after the transition.

        Raises:
            RuntimeError: If already in a terminal state
            ValueError: If no transition is defined for the current state

        """
        sm = self._sm_for(tier_id)
        return sm.advance(actions)

    def advance_to_completion(
        self,
        tier_id: str,
        actions: dict[TierState, Callable[[], None]],
        until_state: TierState | None = None,
    ) -> TierState:
        """Advance the tier through all states until COMPLETE is reached.

        Delegates to the generic StateMachine.advance_to_completion() with
        tier-specific error handling.

        On exception, the tier is marked as FAILED in the checkpoint before the
        exception re-raises, enabling the experiment level to detect and continue
        with remaining tiers (partial-failure semantics).

        Args:
            tier_id: Tier identifier
            actions: Map of from_state -> callable
            until_state: Optional state at which to stop early (inclusive).
                The machine stops after transitioning into this state, without
                error, preserving state for future resume.

        Returns:
            Final TierState (COMPLETE or until_state)

        """
        from scylla.e2e.rate_limit import RateLimitError
        from scylla.e2e.shutdown import ShutdownInterruptedError

        sm = self._sm_for(tier_id)
        return sm.advance_to_completion(
            actions,
            until_state=until_state,
            error_state_map=[
                (ShutdownInterruptedError, TierState.CONFIG_LOADED),
                (RateLimitError, TierState.FAILED),
            ],
            failure_state=TierState.FAILED,
        )
