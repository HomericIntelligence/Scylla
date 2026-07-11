"""Core types and base classes for Scylla.

This module provides foundational types used across the codebase.
"""

from hephaestus.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)

from scylla.core.results import (
    ExecutionInfoBase,
    GradingInfoBase,
    JudgmentInfoBase,
    MetricsInfoBase,
    RunMetricsBase,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "ExecutionInfoBase",
    "GradingInfoBase",
    "JudgmentInfoBase",
    "MetricsInfoBase",
    "RunMetricsBase",
    "get_circuit_breaker",
    "reset_all_circuit_breakers",
]
