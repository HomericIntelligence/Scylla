"""Base class for :class:`scylla.e2e.tier_manager.TierManager`.

Holds construction-time state shared by all mixin modules.
"""

from __future__ import annotations

import logging
from pathlib import Path

from scylla.e2e.models import TierID
from scylla.e2e.subtest_provider import FileSystemSubtestProvider, SubtestProvider
from scylla.executor.tier_config import TierConfigLoader

logger = logging.getLogger(__name__)


class TierManagerBase:
    """Shared state for :class:`TierManager` mixins."""

    tiers_dir: Path
    tier_config_loader: TierConfigLoader
    subtest_provider: SubtestProvider
    _shared_dir: Path

    def __init__(
        self,
        tiers_dir: Path,
        shared_dir: Path | None = None,
        config_dir: Path | None = None,
        subtest_provider: SubtestProvider | None = None,
    ) -> None:
        """Initialize the tier manager.

        Args:
            tiers_dir: Path to the test-specific tiers directory
            shared_dir: Path to shared resources directory. If None, auto-detected
                       from tiers_dir (tiers_dir/../../claude-code/shared)
            config_dir: Path to config directory. If None, auto-detected
                       (repo_root/config)
            subtest_provider: Provider for discovering subtests. If None, uses
                             FileSystemSubtestProvider with shared_dir

        """
        self.tiers_dir = tiers_dir

        # Auto-detect config_dir if not provided
        if config_dir is None:
            config_dir = (
                Path(__file__).parent.parent.parent.parent.parent
                / "tests"
                / "claude-code"
                / "shared"
            )

        # Initialize global tier config loader from tests/claude-code/shared/
        self.tier_config_loader = TierConfigLoader(config_dir)

        # Auto-detect shared_dir if not provided
        if shared_dir is None:
            shared_dir = self._get_shared_dir()
        self._shared_dir = shared_dir

        # Initialize subtest provider
        if subtest_provider is None:
            subtest_provider = FileSystemSubtestProvider(self._shared_dir)
        self.subtest_provider = subtest_provider

    def _get_shared_dir(self) -> Path:
        """Get path to the shared resources directory (auto-detection).

        Returns:
            Path to tests/claude-code/shared/ directory.

        Note:
            This is called during __init__ if shared_dir is not provided.
            The hardcoded path computation can be overridden via the constructor.

        """
        # Navigate from tiers_dir (tests/fixtures/tests/test-XXX) to shared
        # tiers_dir -> tests/fixtures/tests -> tests/fixtures -> tests -> claude-code/shared
        return self.tiers_dir.parent.parent.parent / "claude-code" / "shared"

    def _get_fixture_config_path(self, tier_id: TierID, subtest_id: str) -> Path:
        """Get path to the fixture's config file in shared directory.

        Args:
            tier_id: The tier identifier
            subtest_id: The subtest identifier

        Returns:
            Path to config.yaml in the shared subtests directory.

        """
        shared_subtests_dir = self._shared_dir / "subtests" / tier_id.value.lower()
        # Find config file starting with subtest_id (e.g., "00-empty.yaml")
        for config_file in shared_subtests_dir.glob(f"{subtest_id}-*.yaml"):
            return config_file
        # Fallback if exact match not found
        return shared_subtests_dir / f"{subtest_id}.yaml"
