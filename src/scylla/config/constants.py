"""Shared constants for Scylla configuration.

This module is the single source of truth for default model IDs.
Import from here rather than hardcoding model strings at call sites.

No ``scylla.*`` imports allowed — this module must be safe to import
from any layer without triggering circular dependencies.
"""

DEFAULT_AGENT_MODEL: str = "claude-sonnet-4-6"
DEFAULT_JUDGE_MODEL: str = "claude-opus-4-6"

# Mapping of short aliases and legacy dot-notation IDs to canonical full IDs.
MODEL_ID_ALIASES: dict[str, str] = {
    # Short aliases
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
    # Legacy dot-notation (pre-8717d9ba)
    "opus-4.6": "claude-opus-4-6",
    "sonnet-4.6": "claude-sonnet-4-6",
    "haiku-4.5": "claude-haiku-4-5",
    "opus-4.5": "claude-opus-4-5",
    "sonnet-4.5": "claude-sonnet-4-5",
}


def normalize_model_id(model_id: str) -> str:
    """Normalize a model ID to the canonical full form.

    Handles short aliases (e.g., ``'sonnet'``), old dot-notation
    (e.g., ``'opus-4.6'``), and passes through full IDs unchanged.

    Args:
        model_id: Raw model identifier from CLI or saved config.

    Returns:
        Canonical model ID (e.g., ``'claude-sonnet-4-6'``).

    """
    normalized = model_id.strip().lower()
    return MODEL_ID_ALIASES.get(normalized, model_id)
