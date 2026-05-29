"""Tier configuration management with inheritance.

This module handles loading tier configurations, managing sub-tests,
and implementing the copy+extend inheritance pattern between tiers.

This module is a thin facade over three collaborator objects
(:class:`WorkspaceHandler`, :class:`ResourcesHandler`,
:class:`BaselineHandler`).  The public API (:class:`TierManager`) is
preserved for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scylla.e2e.models import SubTestConfig, TierBaseline, TierConfig, TierID
from scylla.e2e.subtest_provider import SubtestProvider
from scylla.e2e.tier_manager_internals.base import TierManagerBase
from scylla.e2e.tier_manager_internals.baseline import BaselineHandler
from scylla.e2e.tier_manager_internals.resources import ResourcesHandler
from scylla.e2e.tier_manager_internals.workspace import WorkspaceHandler


class TierManager:
    """Manages tier configurations and inheritance.

    Handles loading tier configs from the filesystem, discovering
    sub-tests, and preparing workspaces with inherited configurations.

    Composed of three collaborators (WorkspaceHandler, ResourcesHandler,
    BaselineHandler) that each own a focused slice of the logic.

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

    def __init__(
        self,
        tiers_dir: Path,
        shared_dir: Path | None = None,
        config_dir: Path | None = None,
        subtest_provider: SubtestProvider | None = None,
    ) -> None:
        """Initialize TierManager with collaborator objects.

        Args:
            tiers_dir: Path to the test-specific tiers directory
            shared_dir: Path to shared resources directory. If None, auto-detected
                       from tiers_dir (tiers_dir/../../claude-code/shared)
            config_dir: Path to config directory. If None, auto-detected
                       (repo_root/config)
            subtest_provider: Provider for discovering subtests. If None, uses
                             FileSystemSubtestProvider with shared_dir

        """
        base = TierManagerBase(tiers_dir, shared_dir, config_dir, subtest_provider)

        # Expose shared state on self for callers that access them directly
        self.tiers_dir = base.tiers_dir
        self.tier_config_loader = base.tier_config_loader
        self.subtest_provider = base.subtest_provider
        self._shared_dir = base._shared_dir

        # Collaborators (composition over inheritance)
        self._resources_handler = ResourcesHandler(self._shared_dir)
        self._baseline_handler = BaselineHandler(
            tier_config_loader=self.tier_config_loader,
            subtest_provider=self.subtest_provider,
            shared_dir=self._shared_dir,
            tiers_dir=self.tiers_dir,
        )
        self._workspace_handler = WorkspaceHandler(
            shared_dir=self._shared_dir,
            resources=self._resources_handler,
            baseline=self._baseline_handler,
        )

    # ------------------------------------------------------------------
    # WorkspaceHandler delegation
    # ------------------------------------------------------------------

    def prepare_workspace(
        self,
        workspace: Path,
        tier_id: TierID,
        subtest_id: str,
        baseline: TierBaseline | None = None,
        merged_resources: dict[str, Any] | None = None,
        thinking_enabled: bool = False,
    ) -> None:
        """Prepare a workspace with tier configuration.

        Delegates to :class:`WorkspaceHandler`.

        Args:
            workspace: Path to the workspace directory
            tier_id: The tier being prepared
            subtest_id: The sub-test identifier
            baseline: Previous tier's winning baseline (if any)
            merged_resources: Pre-merged resources from multiple tiers (T5 only)
            thinking_enabled: Whether to enable extended thinking mode

        """
        self._workspace_handler.prepare_workspace(
            workspace=workspace,
            tier_id=tier_id,
            subtest_id=subtest_id,
            baseline=baseline,
            merged_resources=merged_resources,
            thinking_enabled=thinking_enabled,
        )

    # ------------------------------------------------------------------
    # ResourcesHandler delegation
    # ------------------------------------------------------------------

    def build_resource_suffix(self, subtest: SubTestConfig) -> str:
        """Build prompt suffix based on configured resources.

        Delegates to :class:`ResourcesHandler`.

        Args:
            subtest: SubTestConfig with resources specification

        Returns:
            Prompt suffix string with resource hints

        """
        return self._resources_handler.build_resource_suffix(subtest)

    def build_merged_baseline(
        self,
        inherit_from_tiers: list[TierID],
        experiment_dir: Path,
    ) -> dict[str, Any]:
        """Build merged resources from multiple tier results.

        Delegates to :class:`ResourcesHandler`.

        Args:
            inherit_from_tiers: List of tier IDs to inherit from
            experiment_dir: Path to experiment directory

        Returns:
            Merged resources dictionary.

        Raises:
            ValueError: If all required tiers failed.

        """
        return self._resources_handler.build_merged_baseline(inherit_from_tiers, experiment_dir)

    def _merge_tier_resources(
        self,
        merged_resources: dict[str, Any],
        new_resources: dict[str, Any],
        source_tier: TierID,
    ) -> None:
        """Merge resources from a tier into the accumulated merged resources.

        Delegates to :class:`ResourcesHandler`.

        Args:
            merged_resources: Accumulated resources to merge into (modified in place)
            new_resources: Resources from the source tier to merge
            source_tier: The tier ID being merged

        """
        self._resources_handler._merge_tier_resources(
            merged_resources, new_resources, source_tier
        )

    # ------------------------------------------------------------------
    # BaselineHandler delegation
    # ------------------------------------------------------------------

    def load_tier_config(self, tier_id: TierID, skip_agent_teams: bool = False) -> TierConfig:
        """Load configuration for a specific tier.

        Delegates to :class:`BaselineHandler`.

        Args:
            tier_id: The tier to load configuration for
            skip_agent_teams: Skip agent teams sub-tests (default: False)

        Returns:
            TierConfig with all sub-tests for the tier.

        """
        return self._baseline_handler.load_tier_config(tier_id, skip_agent_teams)

    def get_baseline_for_subtest(
        self,
        tier_id: TierID,
        subtest_id: str,
        results_dir: Path,
    ) -> TierBaseline:
        """Create a baseline reference from a completed sub-test.

        Delegates to :class:`BaselineHandler`.

        Args:
            tier_id: The tier of the winning sub-test
            subtest_id: The winning sub-test ID
            results_dir: Directory containing the sub-test's results

        Returns:
            TierBaseline that can be passed to the next tier.

        """
        return self._baseline_handler.get_baseline_for_subtest(tier_id, subtest_id, results_dir)

    def save_resource_manifest(
        self,
        results_dir: Path,
        tier_id: TierID,
        subtest: SubTestConfig,
        workspace: Path,
        baseline: TierBaseline | None = None,
    ) -> None:
        """Save resource manifest for reproducibility.

        Delegates to :class:`BaselineHandler`.

        Args:
            results_dir: Directory to save manifest to
            tier_id: The tier identifier
            subtest: The subtest configuration
            workspace: Workspace with the composed configuration
            baseline: Previous tier's baseline (for inheritance chain)

        """
        self._baseline_handler.save_resource_manifest(
            results_dir, tier_id, subtest, workspace, baseline
        )


__all__ = [
    "TierManager",
]
