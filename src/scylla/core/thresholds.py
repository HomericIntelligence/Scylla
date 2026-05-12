"""Cross-cutting numeric thresholds for ProjectScylla.

This module hosts threshold constants that are referenced by multiple
top-level packages (e.g. ``config`` and ``metrics``). Placing them in
``scylla.core`` keeps the dependency direction strictly downward and
prevents circular imports between feature packages.

See docs/design/grading-scale.md for the grading-scale specification.
"""

from __future__ import annotations

# Default pass threshold (Good grade - B).
#
# A run is considered "passing" when its composite score is at or above
# this threshold. Promoted from ``scylla.metrics.grading`` to break the
# ``config`` <-> ``metrics`` import cycle (issue #1937, edge 1 of 3).
DEFAULT_PASS_THRESHOLD: float = 0.60

__all__ = ["DEFAULT_PASS_THRESHOLD"]
