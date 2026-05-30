"""Tier-config / baseline collaborator for :class:`TierManager`.

Methods that read tier configuration, derive baselines from completed
sub-tests, and persist resource manifests for reproducibility.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from scylla.e2e.models import (
    ResourceManifest,
    SubTestConfig,
    TierBaseline,
    TierConfig,
    TierID,
)
from scylla.e2e.subtest_provider import SubtestProvider
from scylla.executor.tier_config import TierConfigLoader

logger = logging.getLogger(__name__)


class BaselineHandler:
    """Tier-config and baseline methods for :class:`TierManager`."""

    def __init__(
        self,
        tier_config_loader: TierConfigLoader,
        subtest_provider: SubtestProvider,
        shared_dir: Path,
        tiers_dir: Path,
    ) -> None:
        """Initialize baseline handler.

        Args:
            tier_config_loader: Loader for tier configurations
            subtest_provider: Provider for discovering subtests
            shared_dir: Path to shared resources directory
            tiers_dir: Path to the test-specific tiers directory

        """
        self._tier_config_loader = tier_config_loader
        self._subtest_provider = subtest_provider
        self._shared_dir = shared_dir
        self._tiers_dir = tiers_dir

    def load_tier_config(self, tier_id: TierID, skip_agent_teams: bool = False) -> TierConfig:
        """Load configuration for a specific tier.

        Loads tier-level config from tests/claude-code/shared/ and discovers sub-tests.

        Args:
            tier_id: The tier to load configuration for
            skip_agent_teams: Skip agent teams sub-tests (default: False)

        Returns:
            TierConfig with all sub-tests for the tier.

        """
        # Load global tier configuration from tests/claude-code/shared/
        global_tier_config = self._tier_config_loader.get_tier(tier_id.value)

        # Discover sub-tests using the provider
        subtests = self._subtest_provider.discover_subtests(tier_id, skip_agent_teams)

        # Create TierConfig with both global settings and subtests
        # Note: system_prompt_mode is determined per-subtest, not per-tier
        return TierConfig(
            tier_id=tier_id,
            subtests=subtests,
            tools_enabled=global_tier_config.tools_enabled,
            delegation_enabled=global_tier_config.delegation_enabled,
        )

    def get_baseline_for_subtest(
        self,
        tier_id: TierID,
        subtest_id: str,
        results_dir: Path,
    ) -> TierBaseline:
        """Create a baseline reference from a completed sub-test.

        NEW: Reads resource manifest instead of looking for copied files.
        Falls back to legacy config/ directory for old results.

        Args:
            tier_id: The tier of the winning sub-test
            subtest_id: The winning sub-test ID
            results_dir: Directory containing the sub-test's results

        Returns:
            TierBaseline that can be passed to the next tier.

        """
        # NEW: Read from manifest (no file copying)
        manifest_path = results_dir / "config_manifest.json"
        if manifest_path.exists():
            manifest = ResourceManifest.load(manifest_path)
            return TierBaseline(
                tier_id=tier_id,
                subtest_id=subtest_id,
                claude_md_path=None,  # No longer used with manifest
                claude_dir_path=None,  # No longer used with manifest
                resources=manifest.resources,
            )

        # LEGACY fallback: Read from config/ directory (for old results)
        config_dir = results_dir / "config"
        return TierBaseline(
            tier_id=tier_id,
            subtest_id=subtest_id,
            claude_md_path=config_dir / "CLAUDE.md"
            if (config_dir / "CLAUDE.md").exists()
            else None,
            claude_dir_path=config_dir / ".claude" if (config_dir / ".claude").exists() else None,
        )

    def save_resource_manifest(
        self,
        results_dir: Path,
        tier_id: TierID,
        subtest: SubTestConfig,
        workspace: Path,
        baseline: TierBaseline | None = None,
    ) -> None:
        """Save resource manifest for reproducibility.

        Instead of copying CLAUDE.md and .claude/ to results, saves a
        manifest that records what resources were used. This enables
        reproducibility without file duplication.

        Args:
            results_dir: Directory to save manifest to
            tier_id: The tier identifier
            subtest: The subtest configuration
            workspace: Workspace with the composed configuration
            baseline: Previous tier's baseline (for inheritance chain)

        """
        # Compute hash of composed CLAUDE.md for verification
        claude_md = workspace / "CLAUDE.md"
        claude_md_hash = None
        if claude_md.exists():
            claude_md_hash = hashlib.sha256(claude_md.read_bytes()).hexdigest()

        # Record inherited resources for the chain
        inherited_from = None
        if baseline and baseline.resources:
            inherited_from = baseline.resources

        manifest = ResourceManifest(
            tier_id=tier_id.value,
            subtest_id=subtest.id,
            fixture_config_path=str(self._get_fixture_config_path(tier_id, subtest.id)),
            resources=subtest.resources,
            composed_at=datetime.now(timezone.utc).isoformat(),
            claude_md_hash=claude_md_hash,
            inherited_from=inherited_from,
        )

        manifest.save(results_dir / "config_manifest.json")

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
