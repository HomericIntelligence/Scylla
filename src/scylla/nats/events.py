"""NATS event models for Scylla.

Defines the data structures for incoming NATS JetStream messages
and subject parsing utilities for the ``hi.tasks.*`` hierarchy.
"""

from typing import Any, NamedTuple

from pydantic import BaseModel, Field


class SubjectParts(NamedTuple):
    """Parsed components of a ``hi.tasks.{team}.{task_id}.{verb}`` subject.

    Attributes:
        team: Team or service identifier (e.g., ``scylla``).
        task_id: Task identifier.
        verb: Action verb (e.g., ``created``, ``updated``, ``completed``).

    """

    team: str
    task_id: str
    verb: str


class NATSEvent(BaseModel):
    """Incoming NATS JetStream message payload.

    Attributes:
        subject: Full NATS subject string.
        data: Decoded JSON message body.
        timestamp: ISO-8601 timestamp of the message.
        sequence: JetStream sequence number.

    """

    subject: str = Field(..., description="Full NATS subject string")
    data: dict[str, Any] = Field(..., description="Decoded JSON message body")
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    sequence: int = Field(..., ge=0, description="JetStream sequence number")


def parse_subject(subject: str) -> SubjectParts:
    """Parse a ``hi.tasks.{team}.{task_id}.{verb}`` subject into components.

    Args:
        subject: Full NATS subject string.

    Returns:
        SubjectParts with team, task_id, and verb.

    Raises:
        ValueError: If the subject does not have exactly 5 dot-separated parts.

    """
    parts = subject.split(".")
    if len(parts) != 5:
        raise ValueError(
            f"Expected subject with 5 parts (hi.tasks.<team>.<task_id>.<verb>), "
            f"got {len(parts)} parts: {subject!r}"
        )
    return SubjectParts(team=parts[2], task_id=parts[3], verb=parts[4])
