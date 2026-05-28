"""Unit tests for the generic StateMachine[TState] in scylla.core.state_machine.

These tests exercise the generic itself with a synthetic state enum, so they
are independent of any concrete FSM. The experiment-level port is covered by
``tests/unit/e2e/test_experiment_state_machine.py``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import pytest

from scylla.core.state_machine import StateMachine, Transition


class _S(str, Enum):
    """Synthetic state enum used by these tests."""

    A = "a"
    B = "b"
    C = "c"
    DONE = "done"
    FAILED = "failed"


def _build(
    state_ref: list[_S],
    *,
    persistence_calls: list[_S] | None = None,
    event_calls: list[tuple[_S, _S, str]] | None = None,
) -> StateMachine[_S]:
    """Build a 3-edge StateMachine wired against `state_ref` as a single-cell store."""
    transitions = [
        Transition(from_state=_S.A, to_state=_S.B, description="a->b"),
        Transition(from_state=_S.B, to_state=_S.C, description="b->c"),
        Transition(from_state=_S.C, to_state=_S.DONE, description="c->done"),
    ]

    def apply(s: _S) -> None:
        state_ref[0] = s

    def persist(s: _S) -> None:
        if persistence_calls is not None:
            persistence_calls.append(s)

    def emit(f: _S, t: _S, d: str) -> None:
        if event_calls is not None:
            event_calls.append((f, t, d))

    return StateMachine[_S](
        transitions=transitions,
        terminal_states=frozenset({_S.DONE, _S.FAILED}),
        get_state=lambda: state_ref[0],
        apply_state=apply,
        persistence_hook=persist,
        event_hook=emit,
        label="test",
    )


class TestStateMachineValidation:
    """Construction-time and query-side validation behavior."""

    def test_rejects_duplicate_from_state(self) -> None:
        """Duplicate from_state in the transition table is rejected at __post_init__."""
        with pytest.raises(ValueError, match="Duplicate transition"):
            StateMachine[_S](
                transitions=[
                    Transition(_S.A, _S.B, "a"),
                    Transition(_S.A, _S.C, "dup"),
                ],
                terminal_states=frozenset({_S.DONE}),
                get_state=lambda: _S.A,
                apply_state=lambda _s: None,
            )

    def test_validate_transition_accepts_legal(self) -> None:
        """Legal edges return True."""
        sm = _build([_S.A])
        assert sm.validate_transition(_S.A, _S.B)

    def test_validate_transition_rejects_skip(self) -> None:
        """Edges that skip states return False."""
        sm = _build([_S.A])
        assert not sm.validate_transition(_S.A, _S.C)

    def test_validate_transition_rejects_terminal(self) -> None:
        """No edges out of terminal states are legal."""
        sm = _build([_S.A])
        assert not sm.validate_transition(_S.DONE, _S.A)

    def test_get_next_transition(self) -> None:
        """get_next_transition returns the registered edge or None."""
        sm = _build([_S.A])
        t = sm.get_next_transition(_S.A)
        assert t is not None
        assert t.to_state == _S.B
        assert sm.get_next_transition(_S.DONE) is None


class TestStateMachineAdvance:
    """Behavior of advance() — single-step transitions."""

    def test_advance_runs_action_and_transitions(self) -> None:
        """advance() runs the registered action then applies the new state."""
        state = [_S.A]
        sm = _build(state)
        called: list[str] = []
        new = sm.advance({_S.A: lambda: called.append("a")})
        assert new == _S.B
        assert called == ["a"]
        assert state[0] == _S.B

    def test_advance_without_action_still_transitions(self) -> None:
        """A missing action entry advances state silently (no-op transition)."""
        state = [_S.A]
        sm = _build(state)
        assert sm.advance({}) == _S.B
        assert state[0] == _S.B

    def test_advance_from_terminal_raises(self) -> None:
        """Advancing from a terminal state raises RuntimeError."""
        state = [_S.DONE]
        sm = _build(state)
        with pytest.raises(RuntimeError, match="terminal"):
            sm.advance({})

    def test_advance_unknown_state_raises_value_error(self) -> None:
        """Advancing from a non-terminal state with no outgoing edge raises ValueError."""
        sm = StateMachine[_S](
            transitions=[Transition(_S.A, _S.B, "a")],
            terminal_states=frozenset(),  # nothing is terminal
            get_state=lambda: _S.C,  # no edge from C
            apply_state=lambda _s: None,
        )
        with pytest.raises(ValueError, match="No transition"):
            sm.advance({})

    def test_advance_action_exception_does_not_apply_state(self) -> None:
        """If the action raises, the state is NOT advanced and persistence is NOT called."""
        state = [_S.A]
        persisted: list[_S] = []
        sm = _build(state, persistence_calls=persisted)

        def boom() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            sm.advance({_S.A: boom})

        assert state[0] == _S.A
        assert persisted == []

    def test_advance_invokes_persistence_and_event_hooks(self) -> None:
        """Both hooks fire once per successful transition, after apply_state."""
        state = [_S.A]
        persisted: list[_S] = []
        events: list[tuple[_S, _S, str]] = []
        sm = _build(state, persistence_calls=persisted, event_calls=events)
        sm.advance({})
        assert persisted == [_S.B]
        assert events == [(_S.A, _S.B, "a->b")]

    def test_event_hook_exception_does_not_break_advance(self) -> None:
        """Event-hook exceptions are swallowed; advance still returns the new state."""
        state = [_S.A]

        def bad_event(_f: _S, _t: _S, _d: str) -> None:
            raise RuntimeError("event broken")

        sm = StateMachine[_S](
            transitions=[Transition(_S.A, _S.B, "a")],
            terminal_states=frozenset({_S.DONE}),
            get_state=lambda: state[0],
            apply_state=lambda s: state.__setitem__(0, s),
            event_hook=bad_event,
        )
        assert sm.advance({}) == _S.B


class TestStateMachineAdvanceToCompletion:
    """Behavior of advance_to_completion() — driver loop and error mapping."""

    def test_runs_to_terminal(self) -> None:
        """The driver walks through every edge until reaching a terminal state."""
        state = [_S.A]
        sm = _build(state)
        assert sm.advance_to_completion({}) == _S.DONE

    def test_stops_at_until_state(self) -> None:
        """until_state stops the driver as soon as that state is entered."""
        state = [_S.A]
        sm = _build(state)
        assert sm.advance_to_completion({}, until_state=_S.C) == _S.C
        assert state[0] == _S.C

    def test_error_state_map_first_match_wins(self) -> None:
        """The first entry matching the exception type wins; failure_state is ignored."""
        state = [_S.A]
        sm = _build(state)

        class _MyError(RuntimeError):
            """Custom error used to exercise error_state_map ordering."""

        def boom() -> None:
            raise _MyError("x")

        with pytest.raises(_MyError):
            sm.advance_to_completion(
                {_S.A: boom},
                error_state_map=[(_MyError, _S.FAILED)],
                failure_state=_S.DONE,  # should NOT win (subclass listed first)
            )
        assert state[0] == _S.FAILED

    def test_failure_state_used_when_no_map_match(self) -> None:
        """When no entry in error_state_map matches, failure_state is applied."""
        state = [_S.A]
        sm = _build(state)

        def boom() -> None:
            raise RuntimeError("unmapped")

        with pytest.raises(RuntimeError):
            sm.advance_to_completion(
                {_S.A: boom},
                error_state_map=[(ValueError, _S.DONE)],
                failure_state=_S.FAILED,
            )
        assert state[0] == _S.FAILED

    def test_no_mapping_propagates_without_state_change(self) -> None:
        """Without error_state_map / failure_state, exceptions propagate as-is."""
        state = [_S.A]
        sm = _build(state)

        def boom() -> None:
            raise RuntimeError("unmapped")

        with pytest.raises(RuntimeError):
            sm.advance_to_completion({_S.A: boom})
        # No failure_state -> state untouched at last successful checkpoint.
        assert state[0] == _S.A

    def test_already_terminal_is_noop(self) -> None:
        """Calling advance_to_completion on a terminal state is a no-op."""
        state = [_S.DONE]
        sm = _build(state)
        called: list[Any] = []
        final = sm.advance_to_completion({_S.A: lambda: called.append("x")})
        assert final == _S.DONE
        assert called == []


class TestAdvanceToCompletionNewBehaviors:
    """Tests for the new swallow_types and target=None features."""

    def test_advance_to_completion_swallow_type_returns_current_state_unchanged(self) -> None:
        """swallow_types exceptions are caught, logged, and return current state unchanged."""
        state = [_S.A]
        persistence_calls: list[_S] = []
        sm = _build(state, persistence_calls=persistence_calls)

        class _SwallowMe(RuntimeError):
            """Custom error to be swallowed."""

        def boom() -> None:
            raise _SwallowMe("swallow me")

        final = sm.advance_to_completion(
            {_S.A: boom},
            swallow_types=(_SwallowMe,),
        )
        # Swallowed exception returns current state without state change.
        assert final == _S.A
        assert state[0] == _S.A
        # No persistence hook called.
        assert persistence_calls == []

    def test_advance_to_completion_swallow_type_takes_precedence_over_error_map(
        self,
    ) -> None:
        """swallow_types takes precedence over error_state_map."""
        state = [_S.A]
        persistence_calls: list[_S] = []
        sm = _build(state, persistence_calls=persistence_calls)

        class _SwallowMe(RuntimeError):
            """Custom error that matches both swallow_types and error_state_map."""

        def boom() -> None:
            raise _SwallowMe("swallow me")

        final = sm.advance_to_completion(
            {_S.A: boom},
            swallow_types=(_SwallowMe,),
            error_state_map=[(_SwallowMe, _S.FAILED)],
        )
        # swallow_types takes precedence; no state change, no error_state_map application.
        assert final == _S.A
        assert state[0] == _S.A
        assert persistence_calls == []

    def test_advance_to_completion_error_state_map_target_none_re_raises_without_state_change(
        self,
    ) -> None:
        """error_state_map with target=None re-raises without changing state."""
        state = [_S.A]
        persistence_calls: list[_S] = []
        sm = _build(state, persistence_calls=persistence_calls)

        def boom() -> None:
            raise RuntimeError("no state change")

        # target=None in the error_state_map means "matched but don't apply state".
        with pytest.raises(RuntimeError, match="no state change"):
            sm.advance_to_completion(
                {_S.A: boom},
                error_state_map=[(RuntimeError, None)],
                failure_state=_S.FAILED,
            )
        # Exception matched with target=None: state untouched, no persistence.
        assert state[0] == _S.A
        assert persistence_calls == []

    def test_advance_to_completion_error_state_map_target_concrete_applies_state_then_re_raises(
        self,
    ) -> None:
        """error_state_map with concrete target applies state and persistence before re-raising."""
        state = [_S.A]
        persistence_calls: list[_S] = []
        sm = _build(state, persistence_calls=persistence_calls)

        def boom() -> None:
            raise RuntimeError("apply state")

        # target=_S.FAILED in the error_state_map means "matched, apply state, then re-raise".
        with pytest.raises(RuntimeError, match="apply state"):
            sm.advance_to_completion(
                {_S.A: boom},
                error_state_map=[(RuntimeError, _S.FAILED)],
            )
        # Exception matched with concrete target: state applied, persistence called.
        assert state[0] == _S.FAILED
        assert persistence_calls == [_S.FAILED]
