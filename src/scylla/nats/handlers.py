"""NATS event routing and handler registration for Scylla.

Provides the EventRouter that dispatches NATSEvent messages to verb-specific
handler callbacks. Default stub handlers log task lifecycle events.
OrchestratorHandlers wires live handlers to an EvalOrchestrator instance.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from scylla.nats.events import NATSEvent, parse_subject

if TYPE_CHECKING:
    from scylla.e2e.orchestrator import EvalOrchestrator

logger = logging.getLogger(__name__)


class EventRouter:
    """Dispatch NATS events to registered verb-specific handlers.

    Example:
        >>> router = EventRouter()
        >>> router.register("created", handle_task_created)
        >>> router.dispatch(event)

    """

    def __init__(self) -> None:
        """Initialize the router with an empty handler registry."""
        self._handlers: dict[str, Callable[[NATSEvent], None]] = {}

    def register(self, verb: str, handler: Callable[[NATSEvent], None]) -> None:
        """Register a handler for a specific verb.

        Args:
            verb: The action verb to handle (e.g., ``created``).
            handler: Callback invoked when an event with this verb arrives.

        """
        self._handlers[verb] = handler

    def dispatch(self, event: NATSEvent) -> None:
        """Parse the event subject and route to the registered handler.

        If the subject cannot be parsed or no handler is registered for the
        verb, a warning is logged. Handler exceptions are caught and logged
        so that one failing handler does not crash the router.

        Args:
            event: The incoming NATS event.

        """
        try:
            parts = parse_subject(event.subject)
        except ValueError:
            logger.warning("Unparseable subject: %s", event.subject)
            return

        handler = self._handlers.get(parts.verb)
        if handler is None:
            logger.debug("No handler registered for verb: %s", parts.verb)
            return

        try:
            handler(event)
        except Exception:
            logger.exception(
                "Handler for verb %r raised an exception on event seq=%d",
                parts.verb,
                event.sequence,
            )


# ---------------------------------------------------------------------------
# Default stub handlers — log task lifecycle events.
# Full integration with EvalOrchestrator is a follow-up.
# ---------------------------------------------------------------------------


def handle_task_created(event: NATSEvent) -> None:
    """Log a task creation event."""
    logger.info("Task created: %s (seq=%d)", event.subject, event.sequence)


def handle_task_updated(event: NATSEvent) -> None:
    """Log a task update event."""
    logger.info("Task updated: %s (seq=%d)", event.subject, event.sequence)


def handle_task_completed(event: NATSEvent) -> None:
    """Log a task completion event."""
    logger.info("Task completed: %s (seq=%d)", event.subject, event.sequence)


def create_default_router() -> EventRouter:
    """Create an EventRouter pre-loaded with default stub handlers.

    Returns:
        EventRouter with created/updated/completed handlers registered.

    """
    router = EventRouter()
    router.register("created", handle_task_created)
    router.register("updated", handle_task_updated)
    router.register("completed", handle_task_completed)
    return router


# ---------------------------------------------------------------------------
# Orchestrator-wired handlers — delegate NATS events to EvalOrchestrator.
# ---------------------------------------------------------------------------

# Required keys in event.data for handler dispatch
_REQUIRED_CREATED_KEYS = ("test_id", "model_id")


class OrchestratorHandlers:
    """NATS event handlers wired to an injected EvalOrchestrator.

    Each handler method matches the ``Callable[[NATSEvent], None]`` signature
    expected by :class:`EventRouter`.

    Args:
        orchestrator: A pre-configured EvalOrchestrator instance (injected,
            not constructed here).

    Example:
        >>> from scylla.e2e.orchestrator import EvalOrchestrator
        >>> orch = EvalOrchestrator()
        >>> handlers = OrchestratorHandlers(orch)
        >>> router = create_orchestrator_router(orch)

    """

    def __init__(self, orchestrator: EvalOrchestrator) -> None:
        """Initialize with an injected EvalOrchestrator instance."""
        self._orchestrator = orchestrator

    def handle_task_created(self, event: NATSEvent) -> None:
        """Start an experiment run when a task-created event arrives.

        Expects ``event.data`` to contain at minimum ``test_id`` and
        ``model_id``.  Optional keys: ``tier_id`` (default ``"T0"``),
        ``run_number`` (default ``1``).

        If required keys are missing the event is logged and skipped.
        """
        data = event.data
        missing = [k for k in _REQUIRED_CREATED_KEYS if k not in data]
        if missing:
            logger.warning(
                "Skipping task-created event seq=%d: missing keys %s",
                event.sequence,
                missing,
            )
            return

        test_id: str = data["test_id"]
        model_id: str = data["model_id"]
        tier_id: str = data.get("tier_id", "T0")
        run_number: int = int(data.get("run_number", 1))

        logger.info(
            "Starting experiment run: test=%s model=%s tier=%s run=%d (seq=%d)",
            test_id,
            model_id,
            tier_id,
            run_number,
            event.sequence,
        )

        self._orchestrator.run_single(
            test_id=test_id,
            model_id=model_id,
            tier_id=tier_id,
            run_number=run_number,
        )

    def handle_task_updated(self, event: NATSEvent) -> None:
        """Log intermediate state from a task-updated event.

        Updates progress tracking on the orchestrator when ``status`` is
        present in ``event.data``.
        """
        parts = parse_subject(event.subject)
        status = event.data.get("status", "unknown")
        logger.info(
            "Task updated: task=%s status=%s (seq=%d)",
            parts.task_id,
            status,
            event.sequence,
        )

    def handle_task_completed(self, event: NATSEvent) -> None:
        """Record experiment completion from a task-completed event.

        Logs the result and updates progress tracking.  The actual run
        lifecycle is driven by ``run_single`` (triggered by the *created*
        event), so the *completed* handler only records the outcome.
        """
        parts = parse_subject(event.subject)
        passed = event.data.get("passed")
        cost_usd = event.data.get("cost_usd")
        logger.info(
            "Task completed: task=%s passed=%s cost=$%s (seq=%d)",
            parts.task_id,
            passed,
            cost_usd,
            event.sequence,
        )


def create_orchestrator_router(orchestrator: EvalOrchestrator) -> EventRouter:
    """Create an EventRouter wired to an EvalOrchestrator.

    Args:
        orchestrator: Pre-configured EvalOrchestrator instance.

    Returns:
        EventRouter with created/updated/completed handlers registered
        to the given orchestrator.

    """
    handlers = OrchestratorHandlers(orchestrator)
    router = EventRouter()
    router.register("created", handlers.handle_task_created)
    router.register("updated", handlers.handle_task_updated)
    router.register("completed", handlers.handle_task_completed)
    return router
