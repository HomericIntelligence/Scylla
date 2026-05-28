"""Generic state machine abstraction for E2E execution flows.

This module provides a single, reusable `StateMachine[TState]` generic that
consolidates the cross-cutting concerns shared by the experiment-/tier-/
subtest-/run-level FSMs in :mod:`scylla.e2e`:

* a transition-table that defines the legal `(from_state -> to_state)` edges
* validation that rejects illegal transitions
* a persistence hook protocol invoked on every successful transition
* an event-emission hook protocol invoked on every successful transition
* an `advance_to_completion` driver with caller-supplied error-to-state
  mapping (so RateLimitError -> INTERRUPTED, ShutdownInterruptedError ->
  resumable, etc. can be customised per FSM without forking the driver)

Tier/subtest/run FSMs will be ported to use this generic in follow-up PRs;
see issue #1942 for the consolidation tracker.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)


# State enums used by the four E2E FSMs are all `str, Enum` subclasses, so
# bounding `TState` to `Enum` keeps the generic typed under strict mypy while
# remaining flexible across every concrete FSM.
TState = TypeVar("TState", bound=Enum)


# Hook type aliases. Defined as Callable types (rather than Protocols) so that
# any ordinary function with the right signature is accepted under strict mypy
# — Protocols require argument-name conformance, which is unnecessary noise
# for simple callbacks like these.
#
# PersistenceHook: runs after each transition to durably persist the new state
# (e.g. atomic checkpoint save). Exceptions propagate to the caller.
#
# EventHook: runs after persistence for observability (logging/metrics/tracing).
# Exceptions raised by event hooks are swallowed and logged; they never
# interrupt state-machine progress.
PersistenceHook = Callable[[TState], None]
EventHook = Callable[[TState, TState, str], None]


@dataclass(frozen=True)
class Transition(Generic[TState]):
    """A single edge in the state-machine transition table.

    Attributes:
        from_state: State the FSM is in before the transition.
        to_state: State the FSM enters when the transition succeeds.
        description: Human-readable label used for log lines.

    """

    from_state: TState
    to_state: TState
    description: str


@dataclass
class StateMachine(Generic[TState]):
    """Generic state machine with transition validation and hooks.

    Concrete FSMs construct a `StateMachine` by supplying:

    * the ordered transition table for their state enum
    * the terminal-state set (terminal states cannot be advanced from)
    * a callable that reads the current state from durable storage
    * an `apply_state` callable that updates durable storage with the new state
      (the in-memory mutation is the caller's responsibility — this lets the
      generic stay agnostic about how state is persisted)
    * optional `persistence_hook` / `event_hook`

    The generic itself does **not** own the state; it delegates reads and
    writes to the caller-supplied callables so that existing checkpoint
    objects can be reused without modification.

    Attributes:
        transitions: Ordered list of legal transitions.
        terminal_states: States that cannot be advanced from.
        get_state: Callable returning the current state.
        apply_state: Callable applying a new state (e.g. writing it back to
            the checkpoint object). It runs *after* the action succeeds.
        persistence_hook: Optional hook run after `apply_state` to persist
            state to durable storage (e.g. atomic checkpoint save).
        event_hook: Optional hook run for observability after persistence.
        label: Short label for log lines (e.g. ``"experiment"``).

    """

    transitions: list[Transition[TState]]
    terminal_states: frozenset[TState]
    get_state: Callable[[], TState]
    apply_state: Callable[[TState], None]
    persistence_hook: PersistenceHook[TState] | None = None
    event_hook: EventHook[TState] | None = None
    label: str = "state-machine"

    _by_from: dict[TState, Transition[TState]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build the from_state -> Transition lookup and reject duplicates."""
        # Duplicate from_states would silently lose transitions, so reject
        # them up-front.
        by_from: dict[TState, Transition[TState]] = {}
        for t in self.transitions:
            if t.from_state in by_from:
                raise ValueError(
                    f"Duplicate transition for from_state {t.from_state!r} in {self.label}"
                )
            by_from[t.from_state] = t
        self._by_from = by_from

    # ---------------------------------------------------------------- queries

    def is_terminal(self, state: TState) -> bool:
        """Return True if `state` is in the terminal-state set."""
        return state in self.terminal_states

    def is_complete(self) -> bool:
        """Return True if the current state is terminal."""
        return self.is_terminal(self.get_state())

    def get_next_transition(self, state: TState) -> Transition[TState] | None:
        """Return the legal outgoing transition from `state`, or None."""
        return self._by_from.get(state)

    def validate_transition(self, from_state: TState, to_state: TState) -> bool:
        """Return True if `from_state -> to_state` is a legal edge."""
        t = self._by_from.get(from_state)
        if t is None:
            return False
        return t.to_state == to_state

    # ---------------------------------------------------------------- advance

    def advance(self, actions: dict[TState, Callable[[], None]]) -> TState:
        """Execute the next transition.

        Reads the current state, looks up the next transition, runs the
        caller-supplied action (if any), updates state via `apply_state`,
        invokes the persistence and event hooks, and returns the new state.

        Args:
            actions: Map of `from_state -> callable`. Missing entries mean
                the transition is a no-op (state advances without side
                effects).

        Returns:
            The new state after the transition.

        Raises:
            RuntimeError: If the current state is terminal.
            ValueError: If no transition is registered for the current state.

        """
        current = self.get_state()

        if self.is_terminal(current):
            raise RuntimeError(f"Cannot advance {self.label} from terminal state {current.value!r}")

        transition = self._by_from.get(current)
        if transition is None:
            raise ValueError(f"No transition defined from {self.label} state {current.value!r}")

        logger.debug(
            f"[{self.label}] {current.value} -> {transition.to_state.value}: "
            f"{transition.description}"
        )

        action = actions.get(current)
        if action is not None:
            _t0 = time.monotonic()
            action()
            _elapsed = time.monotonic() - _t0
            logger.info(
                f"[{self.label}] {current.value} -> {transition.to_state.value}: "
                f"{transition.description} ({_elapsed:.1f}s)"
            )

        # Apply the new state, then run persistence + event hooks.
        self.apply_state(transition.to_state)

        if self.persistence_hook is not None:
            self.persistence_hook(transition.to_state)

        if self.event_hook is not None:
            try:
                self.event_hook(current, transition.to_state, transition.description)
            except Exception:
                logger.exception(
                    f"[{self.label}] event hook raised during "
                    f"{current.value} -> {transition.to_state.value}"
                )

        return transition.to_state

    def advance_to_completion(
        self,
        actions: dict[TState, Callable[[], None]],
        *,
        until_state: TState | None = None,
        error_state_map: list[tuple[type[BaseException], TState | None]] | None = None,
        failure_state: TState | None = None,
        swallow_types: tuple[type[BaseException], ...] = (),
    ) -> TState:
        """Drive the FSM until a terminal state, `until_state`, or exception.

        Exceptions are handled with the following precedence:
        1. `swallow_types`: Exception is caught, logged at info level, and the
           current state is returned normally without state change.
        2. `error_state_map`: If the exception matches an entry, the FSM is moved
           to the mapped `target_state`. If `target_state` is None, no state change
           occurs (the exception is re-raised unchanged). If `target_state` is
           concrete, it is applied and persisted before re-raising.
        3. `failure_state`: If no `error_state_map` entry matches, `failure_state`
           (if provided) is applied and persisted before re-raising.
        4. Unhandled exceptions propagate without state change.

        Args:
            actions: `from_state -> callable` map (see `advance`).
            until_state: Optional state at which to stop early (inclusive).
                The action that produces `until_state` runs, but no further
                transitions are executed. The FSM is *not* marked failed.
            error_state_map: Ordered list of `(exception_type, target_state)`
                pairs. When an exception of any listed type is raised during
                a transition, the FSM is moved to the associated target_state
                and persisted before the exception is re-raised. If
                target_state is None, the state is left unchanged. The first
                matching entry wins (so subclasses should appear before parents).
            failure_state: Optional fallback state to apply when an exception
                does not match any entry in `error_state_map`. If omitted,
                exceptions not in the map propagate without changing state.
            swallow_types: Tuple of exception types to catch and suppress
                without state change. These are checked before error_state_map,
                so swallowed exceptions never trigger the error map. Caught
                exceptions are logged at info level and the current state is
                returned normally.

        Returns:
            The final state on clean completion or `until_state` early exit.

        """
        try:
            while not self.is_complete():
                new_state = self.advance(actions)
                if until_state is not None and new_state == until_state:
                    logger.info(f"[{self.label}] Reached --until target state: {until_state.value}")
                    break
        except BaseException as exc:
            if swallow_types and isinstance(exc, swallow_types):
                logger.info(
                    f"[{self.label}] Swallowed {type(exc).__name__} at {self.get_state().value}"
                )
                return self.get_state()

            matched = False
            mapped: TState | None = None
            if error_state_map is not None:
                for exc_type, target in error_state_map:
                    if isinstance(exc, exc_type):
                        matched = True
                        mapped = target
                        break

            if not matched and failure_state is not None:
                mapped = failure_state

            if mapped is not None:
                logger.warning(
                    f"[{self.label}] {type(exc).__name__} during "
                    f"{self.get_state().value} -> applying {mapped.value}"
                )
                self.apply_state(mapped)
                if self.persistence_hook is not None:
                    self.persistence_hook(mapped)
            raise

        return self.get_state()


__all__ = [
    "EventHook",
    "PersistenceHook",
    "StateMachine",
    "TState",
    "Transition",
]
