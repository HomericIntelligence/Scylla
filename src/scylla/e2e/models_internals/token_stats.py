"""Back-compat shim — canonical location is :mod:`scylla.core.token_stats`."""

from scylla.core.token_stats import TokenStats as TokenStats

__all__ = ["TokenStats"]
