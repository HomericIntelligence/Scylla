"""Workspace preparation collaborator for :class:`TierManager`.

Methods that materialize tier configuration onto a workspace directory:
copying baselines, overlaying subtest configs, creating symlinks/settings.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import yaml

from scylla.e2e.models import SubTestConfig, TierBaseline, TierID

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class _ResourceProtocol(Protocol):
    """Protocol for methods WorkspaceHandler needs from ResourcesHandler."""

    def build_resource_suffix(self, subtest: SubTestConfig) -> str: ...

    def _merge_tier_resources(
        self,
        merged_resources: dict[str, Any],
        new_resources: dict[str, Any],
        source_tier: TierID,
    ) -> None: ...


class _BaselineProtocol(Protocol):
    """Protocol for methods WorkspaceHandler needs from BaselineHandler."""

    def load_tier_config(self, tier_id: TierID, skip_agent_teams: bool = False) -> Any: ...


class WorkspaceHandler:
    """Workspace preparation methods for :class:`TierManager`."""

    def __init__(
        self,
        shared_dir: Path,
        resources: _ResourceProtocol,
        baseline: _BaselineProtocol,
    ) -> None:
        """Initialize workspace handler with collaborators.

        Args:
            shared_dir: Path to shared resources directory
            resources: ResourcesHandler collaborator
            baseline: BaselineHandler collaborator

        """
        self._shared_dir = shared_dir
        self._resources = resources
        self._baseline = baseline

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

        Implements the copy+extend inheritance pattern:
        1. If baseline provided and sub-test extends_previous, copy baseline
        2. Overlay the sub-test's specific configuration

        For T5 sub-tests with inherit_best_from:
        1. Apply merged resources from completed lower tiers first
        2. Overlay the sub-test's own resources on top (e.g., tools: enabled: all)

        For T0 sub-tests, special handling applies:
        - 00-empty: Remove all CLAUDE.md and .claude (no system prompt)
        - 01-vanilla: Use tool defaults (no changes)
        - 02+: Apply the sub-test's CLAUDE.md configuration

        Args:
            workspace: Path to the workspace directory
            tier_id: The tier being prepared
            subtest_id: The sub-test identifier
            baseline: Previous tier's winning baseline (if any)
            merged_resources: Pre-merged resources from multiple tiers (T5 only)
            thinking_enabled: Whether to enable extended thinking mode

        """
        tier_config = self._baseline.load_tier_config(tier_id)
        subtest = next((s for s in tier_config.subtests if s.id == subtest_id), None)

        if not subtest:
            raise ValueError(f"Sub-test {subtest_id} not found for tier {tier_id.value}")

        if tier_id == TierID.T0:
            self._handle_t0_workspace(workspace, subtest, subtest_id, thinking_enabled)
            return

        resource_suffix = self._compute_resource_suffix(
            workspace, tier_id, subtest, baseline, merged_resources
        )

        # Step 2: Overlay sub-test configuration (skip for T5 with merged_resources)
        if not (merged_resources and tier_id == TierID.T5):
            self._overlay_subtest(workspace, subtest, resource_suffix)

        # Create settings.json with thinking configuration
        self._create_settings_json(workspace, subtest, thinking_enabled)

    def _handle_t0_workspace(
        self,
        workspace: Path,
        subtest: SubTestConfig,
        subtest_id: str,
        thinking_enabled: bool,
    ) -> None:
        """Handle special T0 workspace setup (empty/vanilla/custom).

        Args:
            workspace: Target workspace directory
            subtest: SubTestConfig for this subtest
            subtest_id: The subtest ID string
            thinking_enabled: Whether extended thinking is enabled

        """
        claude_md = workspace / "CLAUDE.md"
        claude_dir = workspace / ".claude"

        if subtest_id in ("00", "01"):
            # 00-empty: Remove all configuration (no system prompt)
            # 01-vanilla: Use tool defaults (no changes needed)
            if claude_md.exists():
                claude_md.unlink()
            if claude_dir.exists():
                shutil.rmtree(claude_dir)
            self._create_settings_json(workspace, subtest, thinking_enabled)
            return

        # 02+: Fall through to normal overlay logic
        resource_suffix = self._resources.build_resource_suffix(subtest)
        self._overlay_subtest(workspace, subtest, resource_suffix)
        self._create_settings_json(workspace, subtest, thinking_enabled)

    def _compute_resource_suffix(
        self,
        workspace: Path,
        tier_id: TierID,
        subtest: SubTestConfig,
        baseline: TierBaseline | None,
        merged_resources: dict[str, Any] | None,
    ) -> str | None:
        """Compute resource suffix and apply resources to the workspace.

        Args:
            workspace: Target workspace directory
            tier_id: Current tier identifier
            subtest: Sub-test configuration
            baseline: Previous tier baseline (if any)
            merged_resources: Pre-merged resources for T5 (if any)

        Returns:
            Resource suffix string, or None.

        """
        if merged_resources and tier_id == TierID.T5:
            return self._apply_merged_resources(workspace, subtest, merged_resources, tier_id)

        if baseline and subtest.extends_previous:
            return self._apply_baseline_resources(workspace, subtest, baseline)

        return self._resources.build_resource_suffix(subtest)

    def _apply_merged_resources(
        self,
        workspace: Path,
        subtest: SubTestConfig,
        merged_resources: dict[str, Any],
        tier_id: TierID,
    ) -> str:
        """Apply merged T5 resources and return suffix.

        Args:
            workspace: Target workspace directory
            subtest: Sub-test configuration
            merged_resources: Pre-merged resources from multiple tiers
            tier_id: Current tier identifier

        Returns:
            Resource suffix string.

        """
        final_merged = merged_resources.copy()
        if subtest.resources:
            for resource_type, resource_spec in subtest.resources.items():
                if resource_type not in final_merged:
                    final_merged[resource_type] = resource_spec
                else:
                    temp_merged = final_merged.copy()
                    temp_new = {resource_type: resource_spec}
                    self._resources._merge_tier_resources(temp_merged, temp_new, tier_id)
                    final_merged = temp_merged

        temp_subtest = subtest.model_copy(update={"resources": final_merged})
        resource_suffix = self._resources.build_resource_suffix(temp_subtest)
        self._create_symlinks(workspace, final_merged, resource_suffix)
        return resource_suffix

    def _apply_baseline_resources(
        self,
        workspace: Path,
        subtest: SubTestConfig,
        baseline: TierBaseline,
    ) -> str:
        """Apply baseline resources to workspace and return suffix.

        Args:
            workspace: Target workspace directory
            subtest: Sub-test configuration
            baseline: Previous tier's winning baseline

        Returns:
            Resource suffix string.

        """
        temp_subtest = subtest.model_copy(update={"resources": baseline.resources})
        resource_suffix = self._resources.build_resource_suffix(temp_subtest)
        self._apply_baseline(workspace, baseline, resource_suffix)
        return resource_suffix

    def _apply_baseline(
        self, workspace: Path, baseline: TierBaseline, resource_suffix: str | None = None
    ) -> None:
        """Apply baseline configuration to workspace using resources.

        NEW: Uses resource specification to recreate config via symlinks,
        instead of copying files. Falls back to legacy copy for old baselines.

        Args:
            workspace: Target workspace directory
            baseline: Baseline configuration to apply
            resource_suffix: Optional resource usage instructions to append to CLAUDE.md

        """
        # NEW: Use resources to recreate via symlinks (no file copying)
        if baseline.resources:
            self._create_symlinks(workspace, baseline.resources, resource_suffix)
            return

        # LEGACY fallback: Copy from paths (for old baselines without resources)
        if baseline.claude_md_path and baseline.claude_md_path.exists():
            dest = workspace / "CLAUDE.md"
            shutil.copy(baseline.claude_md_path, dest)

        if baseline.claude_dir_path and baseline.claude_dir_path.exists():
            dest = workspace / ".claude"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(baseline.claude_dir_path, dest)

    def _overlay_subtest(
        self, workspace: Path, subtest: SubTestConfig, resource_suffix: str | None = None
    ) -> None:
        """Overlay sub-test configuration onto workspace.

        Uses symlinks to shared resources based on the resources spec.
        All fixtures must use symlink-based configuration (no legacy copy mode).

        Args:
            workspace: Target workspace directory
            subtest: Sub-test configuration to overlay
            resource_suffix: Optional resource usage instructions to append to CLAUDE.md

        """
        # Use symlinks if resources are specified
        if subtest.resources:
            self._create_symlinks(workspace, subtest.resources, resource_suffix)
            return

        # Empty resources is valid (e.g., T0 empty/vanilla subtests)
        # No action needed - workspace will have no CLAUDE.md or .claude

    def _merge_directories(self, src: Path, dest: Path) -> None:
        """Recursively merge source directory into destination.

        Files from source overwrite destination files on conflict.
        Directories are merged recursively.

        Args:
            src: Source directory
            dest: Destination directory

        """
        dest.mkdir(parents=True, exist_ok=True)

        for item in src.iterdir():
            dest_item = dest / item.name
            if item.is_dir():
                self._merge_directories(item, dest_item)
            else:
                shutil.copy(item, dest_item)

    def _resolve_resources(self, config_path: Path) -> dict[str, Any]:
        """Parse resources section from config.yaml.

        Args:
            config_path: Path to the config.yaml file

        Returns:
            Dictionary with resources specification (skills, agents, claude_md)

        """
        if not config_path.exists():
            return {}

        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        return cast(dict[str, Any], config.get("resources", {}))

    def _create_symlinks(
        self,
        workspace: Path,
        resources: dict[str, Any],
        resource_suffix: str | None = None,
    ) -> None:
        """Create symlinks to shared resources at runtime.

        Args:
            workspace: Target workspace directory
            resources: Resource specification from config.yaml
            resource_suffix: Optional resource usage instructions to append to CLAUDE.md

        """
        shared_dir = self._shared_dir

        self._link_skills(workspace, resources, shared_dir)
        self._link_agents(workspace, resources, shared_dir)
        self._write_claude_md(workspace, resources, shared_dir, resource_suffix)

    def _link_skills_by_category(
        self, skills_dir: Path, shared_dir: Path, categories: list[str]
    ) -> None:
        """Symlink all skills from each requested category into skills_dir."""
        for category in categories:
            category_dir = shared_dir / "skills" / category
            if not category_dir.exists():
                continue
            for skill in category_dir.iterdir():
                if skill.is_dir():
                    link_path = skills_dir / skill.name
                    if not link_path.exists():
                        os.symlink(skill.resolve(), link_path)

    def _link_skills_by_name(
        self, skills_dir: Path, shared_dir: Path, names: list[str]
    ) -> None:
        """Search all skill categories to symlink individually-named skills."""
        for skill_name in names:
            for category_dir in (shared_dir / "skills").iterdir():
                if not category_dir.is_dir():
                    continue
                skill_path = category_dir / skill_name
                if skill_path.exists():
                    link_path = skills_dir / skill_name
                    if not link_path.exists():
                        os.symlink(skill_path.resolve(), link_path)
                    break

    def _link_skills(
        self, workspace: Path, resources: dict[str, Any], shared_dir: Path
    ) -> None:
        """Symlink skill directories into the workspace.

        Args:
            workspace: Target workspace directory
            resources: Resource specification
            shared_dir: Path to shared resources

        """
        if "skills" not in resources:
            return

        skills_spec = resources["skills"]
        skills_dir = workspace / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        self._link_skills_by_category(skills_dir, shared_dir, skills_spec.get("categories", []))
        self._link_skills_by_name(skills_dir, shared_dir, skills_spec.get("names", []))

    def _link_agents_by_level(
        self, agents_dir: Path, shared_dir: Path, levels: list[int]
    ) -> None:
        """Symlink all agent files from each requested level into agents_dir."""
        for level in levels:
            level_dir = shared_dir / "agents" / f"L{level}"
            if not level_dir.exists():
                continue
            for agent in level_dir.iterdir():
                if agent.is_file() and agent.suffix == ".md":
                    link_path = agents_dir / agent.name
                    if not link_path.exists():
                        os.symlink(agent.resolve(), link_path)

    def _link_agents_by_name(
        self, agents_dir: Path, shared_dir: Path, names: list[str]
    ) -> None:
        """Search all agent levels to symlink individually-named agents."""
        for agent_name in names:
            for level_dir in (shared_dir / "agents").iterdir():
                if not (level_dir.is_dir() and level_dir.name.startswith("L")):
                    continue
                agent_path = level_dir / agent_name
                if agent_path.exists():
                    link_path = agents_dir / agent_name
                    if not link_path.exists():
                        os.symlink(agent_path.resolve(), link_path)
                    break

    def _link_agents(
        self, workspace: Path, resources: dict[str, Any], shared_dir: Path
    ) -> None:
        """Symlink agent files into the workspace.

        Args:
            workspace: Target workspace directory
            resources: Resource specification
            shared_dir: Path to shared resources

        """
        if "agents" not in resources:
            return

        agents_spec = resources["agents"]
        agents_dir = workspace / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        self._link_agents_by_level(agents_dir, shared_dir, agents_spec.get("levels", []))
        self._link_agents_by_name(agents_dir, shared_dir, agents_spec.get("names", []))

    def _write_claude_md(
        self,
        workspace: Path,
        resources: dict[str, Any],
        shared_dir: Path,
        resource_suffix: str | None,
    ) -> None:
        """Write CLAUDE.md from blocks and resource suffix.

        Args:
            workspace: Target workspace directory
            resources: Resource specification
            shared_dir: Path to shared resources
            resource_suffix: Optional suffix to append

        """
        if "claude_md" in resources:
            claude_md_spec = resources["claude_md"]
            self._compose_claude_md(workspace, claude_md_spec, shared_dir, resource_suffix)
        elif resource_suffix:
            # No claude_md blocks, but we have a resource suffix - create minimal CLAUDE.md
            claude_md = workspace / "CLAUDE.md"
            claude_md.write_text(resource_suffix)

    def _compose_claude_md(
        self,
        workspace: Path,
        spec: dict[str, Any],
        shared_dir: Path,
        resource_suffix: str | None = None,
    ) -> None:
        """Compose CLAUDE.md from blocks at runtime.

        Args:
            workspace: Target workspace directory
            spec: CLAUDE.md specification (preset or blocks list)
            shared_dir: Path to shared resources directory
            resource_suffix: Optional resource usage instructions to append

        """
        blocks_dir = shared_dir / "blocks"
        if not blocks_dir.exists():
            return

        # Get block IDs from spec
        block_ids = spec.get("blocks", [])

        # If no blocks but we have a resource suffix, create CLAUDE.md anyway
        if not block_ids and not resource_suffix:
            return

        content_parts = []
        for block_id in block_ids:
            # Find block file matching pattern like "B02-critical-rules.md"
            matches = list(blocks_dir.glob(f"{block_id}-*.md"))
            if matches:
                content_parts.append(matches[0].read_text())

        # Compose final content
        content = "\n\n".join(content_parts) if content_parts else ""

        # Append resource suffix if provided
        if resource_suffix:
            content = f"{content}\n\n{resource_suffix}" if content else resource_suffix

        # Write CLAUDE.md if we have any content
        if content:
            claude_md = workspace / "CLAUDE.md"
            claude_md.write_text(content)

    def _create_settings_json(
        self,
        workspace: Path,
        subtest: SubTestConfig,
        thinking_enabled: bool = False,
    ) -> None:
        """Create .claude/settings.json for workspace configuration.

        Includes thinking mode, tool permissions, and MCP server registrations.

        Args:
            workspace: Target workspace directory
            subtest: SubTest configuration with resources specification
            thinking_enabled: Whether to enable thinking mode

        """
        settings: dict[str, Any] = {
            "alwaysThinkingEnabled": thinking_enabled,
        }

        resources = subtest.resources or {}

        # Add tool permissions for T2+ tiers
        if "tools" in resources:
            tools_spec = resources["tools"]
            if isinstance(tools_spec, dict):
                enabled_tools = tools_spec.get("enabled", [])
                if enabled_tools and enabled_tools != "all":
                    # Restrict to specific tools
                    settings["allowedTools"] = enabled_tools
                # If enabled_tools == "all", don't add restriction (all tools allowed)

        # Add MCP server configurations
        if "mcp_servers" in resources:
            mcp_servers = resources["mcp_servers"]
            if mcp_servers:
                settings["mcpServers"] = {}
                for server in mcp_servers:
                    if isinstance(server, dict):
                        name = server["name"]
                        source = server.get("source", "modelcontextprotocol/servers")
                        settings["mcpServers"][name] = {
                            "command": "npx",
                            "args": ["-y", f"@{source}/{name}"],
                        }
                    else:
                        # Simple string format
                        settings["mcpServers"][server] = {
                            "command": "npx",
                            "args": ["-y", f"@modelcontextprotocol/servers/{server}"],
                        }

        # Add experimental agent teams environment variable
        if subtest.agent_teams:
            if "env" not in settings:
                settings["env"] = {}
            settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"

        settings_dir = workspace / ".claude"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / "settings.json"
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
