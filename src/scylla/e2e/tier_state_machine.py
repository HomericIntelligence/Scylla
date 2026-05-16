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
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

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


@dataclass
class TierTransition:
    """Describes a single state transition in the tier state machine.

    Attributes:
        from_state: State before this transition
        to_state: State after this transition completes successfully
        description: Human-readable description for logging

    """

    from_state: TierState
    to_state: TierState
    description: str


# Registry of all valid tier transitions
TIER_TRANSITION_REGISTRY: list[TierTransition] = [
    TierTransition(
        from_state=TierState.PENDING,
        to_state=TierState.CONFIG_LOADED,
        description="Load tier config YAML",
    ),
    TierTransition(
        from_state=TierState.CONFIG_LOADED,
        to_state=TierState.SUBTESTS_RUNNING,
        description="Start subtest execution",
    ),
    TierTransition(
        from_state=TierState.SUBTESTS_RUNNING,
        to_state=TierState.SUBTESTS_COMPLETE,
        description="Execute all subtests",
    ),
    TierTransition(
        from_state=TierState.SUBTESTS_COMPLETE,
        to_state=TierState.BEST_SELECTED,
        description="Select best subtest by CoP",
    ),
    TierTransition(
        from_state=TierState.BEST_SELECTED,
        to_state=TierState.REPORTS_GENERATED,
        description="Generate tier reports",
    ),
    TierTransition(
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

    Each call to advance() executes the next action, updates the tier state
    in the checkpoint, and saves the checkpoint atomically.

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

    def advance(
        self,
        tier_id: str,
        actions: dict[TierState, Callable[[], None]],
    ) -> TierState:
        """Advance the tier by one state transition.

        1. Reads the current state from the checkpoint.
        2. Looks up the next transition in the registry.
        3. Executes the transition action (if provided).
        4. Updates the checkpoint state.
        5. Saves the checkpoint atomically.

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
        from scylla.persistence.checkpoint import save_checkpoint

        current = self.get_state(tier_id)

        if is_tier_terminal_state(current):
            raise RuntimeError(f"Cannot advance tier {tier_id} from terminal state {current.value}")

        transition = get_next_tier_transition(current)
        if transition is None:
            raise ValueError(
                f"No transition defined from tier state {current.value} for tier {tier_id}"
            )

        logger.debug(
            f"[{tier_id}] {current.value} -> {transition.to_state.value}: {transition.description}"
        )

        # Execute the action if provided
        action = actions.get(current)
        if action is not None:
            _t0 = time.monotonic()
            action()
            _elapsed = time.monotonic() - _t0
            logger.info(
                f"[{tier_id}] {current.value} -> {transition.to_state.value}: "
                f"{transition.description} ({_elapsed:.1f}s)"
            )

        # Update state in checkpoint
        self.checkpoint.set_tier_state(tier_id, transition.to_state.value)

        # Save checkpoint atomically
        save_checkpoint(self.checkpoint, self.checkpoint_path)

        return transition.to_state

    def advance_to_completion(
        self,
        tier_id: str,
        actions: dict[TierState, Callable[[], None]],
        until_state: TierState | None = None,
    ) -> TierState:
        """Advance the tier through all states until COMPLETE is reached.

        Useful for running a complete tier from start or resuming from any state.
        On exception, the tier is marked as FAILED in the checkpoint before the
        exception re-raises, enabling the experiment level to detect and continue
        with remaining tiers (partial-failure semantics).

        If until_state is specified, the tier stops cleanly once that state is
        reached (inclusive): the action that transitions INTO until_state IS
        executed, but no further transitions run.

        Args:
            tier_id: Tier identifier
            actions: Map of from_state -> callable
            until_state: Optional state at which to stop early (inclusive).
                The machine stops after transitioning into this state, without
                error, preserving state for future resume.

        Returns:
            Final TierState (COMPLETE or until_state)

        """
        try:
            while not self.is_complete(tier_id):
                new_state = self.advance(tier_id, actions)
                if until_state is not None and new_state == until_state:
                    logger.info(
                        f"[{tier_id}] Reached --until-tier target state: {until_state.value}"
                    )
                    break
        except Exception as e:
            from scylla.e2e.rate_limit import RateLimitError
            from scylla.e2e.shutdown import ShutdownInterruptedError
            from scylla.persistence.checkpoint import save_checkpoint

            if isinstance(e, ShutdownInterruptedError):
                # Ctrl+C interrupted this tier — leave it at CONFIG_LOADED (resumable)
                # rather than FAILED so the next invocation can continue where we left off.
                current = self.get_state(tier_id)
                logger.warning(
                    f"[{tier_id}] Shutdown interrupted at {current.value} "
                    "— tier left at config_loaded (not FAILED)"
                )
                self.checkpoint.set_tier_state(tier_id, TierState.CONFIG_LOADED.value)
                save_checkpoint(self.checkpoint, self.checkpoint_path)
                raise

            if isinstance(e, RateLimitError):
                # Rate limits propagate to experiment level by design;
                # TierState has no INTERRUPTED state.
                logger.warning(
                    f"[{tier_id}] Rate limit encountered in tier state machine: {e}. "
                    "Marking tier as FAILED — rate limit handling occurs at experiment level."
                )
            self.checkpoint.set_tier_state(tier_id, TierState.FAILED.value)
            save_checkpoint(self.checkpoint, self.checkpoint_path)
            raise

        return self.get_state(tier_id)
