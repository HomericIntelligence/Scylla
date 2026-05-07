"""Tier configuration management with inheritance.

This module handles loading tier configurations, managing sub-tests,
and implementing the copy+extend inheritance pattern between tiers.

This module is a thin facade — its implementation lives in
:mod:`scylla.e2e.tier_manager_internals`. The public API
(:class:`TierManager`) is preserved for backward compatibility.
"""

from __future__ import annotations

from scylla.e2e.tier_manager_internals.base import TierManagerBase
from scylla.e2e.tier_manager_internals.baseline import BaselineMixin
from scylla.e2e.tier_manager_internals.resources import ResourcesMixin
from scylla.e2e.tier_manager_internals.workspace import WorkspaceMixin


class TierManager(WorkspaceMixin, ResourcesMixin, BaselineMixin, TierManagerBase):
    """Manages tier configurations and inheritance.

    Handles loading tier configs from the filesystem, discovering
    sub-tests, and preparing workspaces with inherited configurations.

    Example:
        >>> manager = TierManager(Path("tests/fixtures/tests/test-001"))
        >>> tier_config = manager.load_tier_config(TierID.T2)
        >>> manager.prepare_workspace(
        ...     workspace=Path(tempfile.gettempdir()) / "workspace",
        ...     tier_id=TierID.T3,
        ...     subtest_id="01",
        ...     baseline=previous_baseline,
        ... )

    """


__all__ = [
    "TierManager",
]
