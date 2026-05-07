"""Type-coercing validators for JSON-loaded scalar fields."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def validate_numeric(value: Any, field_name: str, default: float = np.nan) -> float:
    """Validate and coerce numeric field from JSON.

    Args:
        value: Value from JSON (could be int, float, str, None, etc.)
        field_name: Field name for error messages
        default: Default value if validation fails

    Returns:
        Validated float value or default

    """
    # Handle None or missing
    if value is None:
        return default

    # Try to convert to float
    try:
        result = float(value)

        # Check for invalid values
        if np.isnan(result) or np.isinf(result):
            return default

        return result
    except (ValueError, TypeError):
        logger.warning(
            "Invalid type for %s: %s (value=%r), using default=%s",
            field_name,
            type(value).__name__,
            value,
            default,
        )
        return default


def validate_bool(value: Any, field_name: str, default: bool = False) -> bool:
    """Validate and coerce boolean field from JSON.

    Args:
        value: Value from JSON (could be bool, int, str, None, etc.)
        field_name: Field name for error messages
        default: Default value if validation fails

    Returns:
        Validated bool value or default

    """
    # Handle None or missing
    if value is None:
        return default

    # If already bool, return directly
    if isinstance(value, bool):
        return value

    # Try common string representations
    if isinstance(value, str):
        value_lower = value.lower()
        if value_lower in ("true", "yes", "1"):
            return True
        if value_lower in ("false", "no", "0"):
            return False

    # Try numeric conversion (0 = False, non-zero = True)
    try:
        return bool(int(value))
    except (ValueError, TypeError):
        logger.warning(
            "Invalid type for %s: %s (value=%r), using default=%s",
            field_name,
            type(value).__name__,
            value,
            default,
        )
        return default


def validate_int(value: Any, field_name: str, default: int = -1) -> int:
    """Validate and coerce integer field from JSON.

    Args:
        value: Value from JSON (could be int, float, str, None, etc.)
        field_name: Field name for error messages
        default: Default value if validation fails

    Returns:
        Validated int value or default

    """
    # Handle None or missing
    if value is None:
        return default

    # Try to convert to int
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(
            "Invalid type for %s: %s (value=%r), using default=%s",
            field_name,
            type(value).__name__,
            value,
            default,
        )
        return default
