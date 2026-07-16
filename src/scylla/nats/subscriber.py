"""NATS JetStream subscriber thread for Scylla.

Provides NATSSubscriberThread, a daemon thread that connects to NATS,
subscribes to JetStream subjects via a durable consumer, and dispatches
incoming messages to a handler callback.

The thread follows the HeartbeatThread pattern from scylla.e2e.health,
using a threading.Event for clean shutdown and an isolated asyncio event
loop for the async nats-py client.
"""

import asyncio
import json
import logging
import threading
import warnings
from collections.abc import Callable
from typing import Any

from scylla.nats.config import NATSConfig
from scylla.nats.events import NATSEvent

# Suppress nats-py DeprecationWarning for asyncio.iscoroutinefunction (Python 3.11+)
warnings.filterwarnings(
    "ignore", message=".*asyncio.iscoroutinefunction.*", category=DeprecationWarning, module="nats"
)

logger = logging.getLogger(__name__)

# Backoff constants (matching scylla/e2e/rate_limit.py patterns)
_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 60.0
_BACKOFF_MULTIPLIER = 2.0


class NATSSubscriberThread(threading.Thread):
    """Daemon thread that subscribes to NATS JetStream and dispatches events.

    The thread creates an isolated asyncio event loop internally. The NATS
    connection and JetStream subscription live entirely within that loop.

    Example:
        >>> from scylla.nats.config import NATSConfig
        >>> subscriber = NATSSubscriberThread(
        ...     config=NATSConfig(enabled=True),
        ...     handler=lambda event: print(event.subject),
        ... )
        >>> subscriber.start()
        >>> # ... do work ...
        >>> subscriber.stop()

    """

    def __init__(
        self,
        config: NATSConfig,
        handler: Callable[[NATSEvent], None],
    ) -> None:
        """Initialize the subscriber thread.

        Args:
            config: NATS connection configuration.
            handler: Callback invoked for each received NATSEvent.

        """
        super().__init__(daemon=True, name="NATSSubscriberThread")
        self._config = config
        self._handler = handler
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Run the subscriber loop with reconnection backoff."""
        logger.info(
            "NATSSubscriberThread started (url=%s, stream=%s, durable=%s)",
            self._config.url,
            self._config.stream,
            self._config.durable_name,
        )

        backoff = _INITIAL_BACKOFF_SECONDS

        while not self._stop_event.is_set():
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._subscribe_loop())
                finally:
                    loop.close()
                # If subscribe_loop returns without error, reset backoff
                backoff = _INITIAL_BACKOFF_SECONDS
            except Exception:
                if self._stop_event.is_set():
                    break
                logger.exception(
                    "NATS connection error, retrying in %.1fs",
                    backoff,
                )
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * _BACKOFF_MULTIPLIER, _MAX_BACKOFF_SECONDS)

        logger.info("NATSSubscriberThread stopped")

    async def _dispatch_msg(self, msg: Any) -> None:
        """Parse a raw NATS message and dispatch it to the handler.

        Args:
            msg: A NATS JetStream message object.

        """
        try:
            data: dict[str, Any] = json.loads(msg.data.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "Failed to decode message on %s (seq=%d)",
                msg.subject,
                msg.metadata.sequence.stream if msg.metadata else 0,
            )
            await msg.ack()
            return

        event = NATSEvent(
            subject=msg.subject,
            data=data,
            timestamp=(msg.headers.get("Nats-Time-Stamp", "") if msg.headers else ""),
            sequence=msg.metadata.sequence.stream if msg.metadata else 0,
        )

        self._handler(event)
        await msg.ack()

    async def _subscribe_loop(self) -> None:
        """Connect to NATS JetStream and process messages until stop is requested."""
        nats_client = self._import_nats()
        if nats_client is None:
            return

        nc = await nats_client.connect(self._config.url)
        try:
            js = nc.jetstream()
            subjects = self._config.subjects or ["hi.tasks.>"]
            subscriptions = await self._create_subscriptions(js, subjects)
            logger.info(
                "Subscribed to %d NATS JetStream subject(s) on stream=%s: %s",
                len(subscriptions),
                self._config.stream,
                subjects,
            )
            await self._run_message_loop(subscriptions)
        finally:
            await nc.drain()

    def _import_nats(self) -> Any:
        """Import nats-py, setting stop event if unavailable.

        Returns:
            The nats module, or None if not installed.

        """
        try:
            import nats as nats_client

            return nats_client
        except ImportError:
            logger.error("nats-py is not installed. Install with: pip install 'scylla[nats]'")
            # Set stop event so we don't retry endlessly
            self._stop_event.set()
            return None

    async def _create_subscriptions(self, js: Any, subjects: list[str]) -> list[Any]:
        """Subscribe to all subjects, rolling back on partial failure.

        Args:
            js: The JetStream context.
            subjects: List of subject strings to subscribe to.

        Returns:
            List of active subscription objects.

        Raises:
            Exception: Re-raises any subscription error after cleaning up.

        """
        subscriptions: list[Any] = []
        for i, subject in enumerate(subjects):
            durable = (
                self._config.durable_name
                if len(subjects) == 1
                else f"{self._config.durable_name}-{i}"
            )
            try:
                sub = await js.subscribe(
                    subject=subject,
                    durable=durable,
                    stream=self._config.stream,
                    deliver_policy=self._config.deliver_policy,
                )
            except Exception:
                logger.warning(
                    "Failed to subscribe to subject %r (index %d); "
                    "unsubscribing %d already-subscribed subject(s) before re-raising",
                    subject,
                    i,
                    len(subscriptions),
                )
                await self._cleanup_subscriptions(subscriptions)
                raise
            subscriptions.append(sub)
        return subscriptions

    async def _cleanup_subscriptions(self, subscriptions: list[Any]) -> None:
        """Unsubscribe from all subscriptions, logging errors as debug.

        Args:
            subscriptions: List of subscription objects to unsubscribe.

        """
        for prev_sub in subscriptions:
            try:
                await prev_sub.unsubscribe()
            except Exception:
                logger.debug("Error unsubscribing during cleanup", exc_info=True)

    async def _run_message_loop(self, subscriptions: list[Any]) -> None:
        """Poll subscriptions and dispatch messages until stop is requested.

        Args:
            subscriptions: Active JetStream subscription objects.

        """
        # Build initial pending tasks — one next_msg per subscription.
        # We map each task back to its subscription so completed tasks
        # can be replaced without cancelling/recreating the rest.
        pending: dict[asyncio.Task[Any], Any] = {}
        for sub in subscriptions:
            task = asyncio.ensure_future(sub.next_msg(timeout=1.0))
            pending[task] = sub

        while not self._stop_event.is_set() and pending:
            done, _ = await asyncio.wait(
                pending.keys(),
                timeout=1.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                sub = pending.pop(task)
                await self._handle_task_result(task, sub, pending)

        # Cancel any remaining pending tasks on shutdown
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _handle_task_result(
        self,
        task: asyncio.Task[Any],
        sub: Any,
        pending: dict[asyncio.Task[Any], Any],
    ) -> None:
        """Process a completed next_msg task and re-enqueue for the subscription.

        Args:
            task: The completed asyncio Task.
            sub: The subscription the task belongs to.
            pending: Mapping of active tasks to their subscriptions; updated in-place.

        """
        try:
            msg = task.result()
        except (asyncio.TimeoutError, TimeoutError):
            # Subscription poll timed out — re-enqueue
            new_task = asyncio.ensure_future(sub.next_msg(timeout=1.0))
            pending[new_task] = sub
            return

        await self._dispatch_msg(msg)

        # Re-enqueue a next_msg task for this subscription
        new_task = asyncio.ensure_future(sub.next_msg(timeout=1.0))
        pending[new_task] = sub

    def stop(self) -> None:
        """Signal the subscriber to stop and wait for the thread to finish."""
        self._stop_event.set()
        self.join(timeout=5.0)
