"""Canonical home for the TokenStats value object.

Shared by adapters, e2e, executor, metrics, and analysis — lives in
``scylla.core`` so no higher-level package needs to import from ``e2e``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TokenStats(BaseModel):
    """Detailed token usage statistics.

    Tracks all token types including cache operations for
    accurate cost analysis and efficiency metrics.

    Attributes:
        input_tokens: Fresh input tokens (not from cache)
        output_tokens: Generated output tokens
        cache_creation_tokens: Tokens written to cache
        cache_read_tokens: Tokens read from cache (cheaper)

    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_input(self) -> int:
        """Total input tokens including cache reads."""
        return self.input_tokens + self.cache_read_tokens

    @property
    def total_tokens(self) -> int:
        """Total all tokens processed."""
        return self.total_input + self.output_tokens + self.cache_creation_tokens

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenStats:
        """Create from dictionary."""
        return cls(
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_creation_tokens=data.get("cache_creation_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
        )

    def __add__(self, other: TokenStats) -> TokenStats:
        """Enable summing TokenStats."""
        return TokenStats(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )
