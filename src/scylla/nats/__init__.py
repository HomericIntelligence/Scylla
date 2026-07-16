"""NATS JetStream event subscription for Scylla.

Provides NATS subscriber infrastructure for receiving task events
from ProjectHermes over the ``hi.tasks.*`` subject hierarchy.

Uses ``import X as X`` pattern for explicit re-export (mypy implicit_reexport=false).
"""

from scylla.nats.config import NATSConfig as NATSConfig
from scylla.nats.config import load_nats_config as load_nats_config
from scylla.nats.events import NATSEvent as NATSEvent
from scylla.nats.events import SubjectParts as SubjectParts
from scylla.nats.events import parse_subject as parse_subject
from scylla.nats.handlers import EventRouter as EventRouter
from scylla.nats.handlers import OrchestratorHandlers as OrchestratorHandlers
from scylla.nats.handlers import create_default_router as create_default_router
from scylla.nats.handlers import create_orchestrator_router as create_orchestrator_router
from scylla.nats.subscriber import NATSSubscriberThread as NATSSubscriberThread
