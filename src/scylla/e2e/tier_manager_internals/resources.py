"""Resource composition mixin for :class:`TierManager`.

Methods that build prompt suffixes from resource specs and merge resources
across multiple tiers (used by T5 inherit_best_from logic).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scylla.e2e.models import SubTestConfig, TierID

if TYPE_CHECKING:
    from scylla.e2e.tier_manager_internals.base import TierManagerBase

    _Base = TierManagerBase
else:
    _Base = object

logger = logging.getLogger(__name__)


class ResourcesMixin(_Base):
    """Resource composition methods for :class:`TierManager`."""

    def build_resource_suffix(  # noqa: C901  # config with many conditional suffix rules
        self, subtest: SubTestConfig
    ) -> str:
        """Build prompt suffix based on configured resources.

        Uses bullet list format for resources:
        - skill1
        - skill2

        If no resources configured, returns generic hint.

        Args:
            subtest: SubTestConfig with resources specification

        Returns:
            Prompt suffix string with resource hints

        """
        suffixes = []
        resources = subtest.resources or {}
        has_any_resources = False

        # Sub-agents
        if "agents" in resources:
            agents_spec = resources["agents"]
            agent_names = []
            for level in agents_spec.get("levels", []):
                level_dir = self._shared_dir / "agents" / f"L{level}"
                if level_dir.exists():
                    for f in level_dir.glob("*.md"):
                        agent_names.append(f.stem)
            agent_names.extend(n.replace(".md", "") for n in agents_spec.get("names", []))
            if agent_names:
                has_any_resources = True
                bullet_list = "\n".join(f"- {name}" for name in sorted(set(agent_names)))
                if len(agent_names) > 1:
                    prefix = "Maximize usage of the following sub-agents to solve this task:"
                else:
                    prefix = "Use the following sub-agent to solve this task:"
                suffixes.append(f"{prefix}\n\n{bullet_list}")

        # Skills
        if "skills" in resources:
            skills_spec = resources["skills"]
            skill_names: list[str] = []
            for cat in skills_spec.get("categories", []):
                cat_dir = self._shared_dir / "skills" / cat
                if cat_dir.exists():
                    skill_names.extend(d.name for d in cat_dir.iterdir() if d.is_dir())
            skill_names.extend(skills_spec.get("names", []))
            if skill_names:
                has_any_resources = True
                bullet_list = "\n".join(f"- {name}" for name in sorted(set(skill_names)))
                if len(skill_names) > 1:
                    prefix = "Maximize usage of the following skills to complete this task:"
                else:
                    prefix = "Use the following skill to complete this task:"
                suffixes.append(f"{prefix}\n\n{bullet_list}")

        # MCP servers
        if "mcp_servers" in resources:
            mcp_names = [
                m.get("name", m) if isinstance(m, dict) else m for m in resources["mcp_servers"]
            ]
            if mcp_names:
                has_any_resources = True
                bullet_list = "\n".join(f"- {name}" for name in sorted(set(mcp_names)))
                if len(mcp_names) > 1:
                    prefix = "Maximize usage of the following MCP servers to complete this task:"
                else:
                    prefix = "Use the following MCP server to complete this task:"
                suffixes.append(f"{prefix}\n\n{bullet_list}")

        # Tools
        if "tools" in resources:
            tools_spec = resources["tools"]
            if isinstance(tools_spec, dict):
                if tools_spec.get("enabled") == "all":
                    suffixes.append("Maximize usage of all available tools to complete this task.")
                    has_any_resources = True
                elif "names" in tools_spec:
                    tool_names = tools_spec["names"]
                    if tool_names:
                        has_any_resources = True
                        bullet_list = "\n".join(f"- {name}" for name in sorted(tool_names))
                        if len(tool_names) > 1:
                            prefix = "Maximize usage of the following tools to complete this task:"
                        else:
                            prefix = "Use the following tool to complete this task:"
                        suffixes.append(f"{prefix}\n\n{bullet_list}")

        # If no resources configured, add generic hint
        if not has_any_resources:
            base_message = "Complete this task using available tools and your best judgment."
        else:
            base_message = "\n\n".join(suffixes)

        # Test environment constraints (always applied)
        test_constraints = (
            "\n\n## Test Environment Constraints\n\n"
            "**CRITICAL: This is a test environment. "
            "The following WRITE operations are FORBIDDEN:**\n\n"
            "- DO NOT run `git push` or push to any remote repository\n"
            "- DO NOT create pull requests (`gh pr create` or similar)\n"
            "- DO NOT comment on or modify GitHub issues or PRs\n"
            "- DO NOT delete remote branches (`git push origin --delete`)\n"
            "- All changes must remain LOCAL to this workspace - no remote writes\n"
            "- Read-only remote operations (`git fetch`, `git pull`) are permitted\n"
        )

        # Always add cleanup instructions (temporary files only)
        cleanup_instructions = (
            "\n\n## Cleanup Requirements\n\n"
            "- Remove any temporary files created during task completion "
            "(build artifacts, cache files, etc.)\n"
            "- Clean up after yourself - the workspace should contain only final deliverables\n"
        )

        return base_message + test_constraints + cleanup_instructions

    def build_merged_baseline(
        self,
        inherit_from_tiers: list[TierID],
        experiment_dir: Path,
    ) -> dict[str, Any]:
        """Build merged resources from multiple tier results.

        Used by T5 subtests to dynamically inherit the best-performing
        configuration from completed lower tiers (T0-T4).

        Args:
            inherit_from_tiers: List of tier IDs to inherit from (e.g., [T0, T1, T3])
            experiment_dir: Path to experiment directory containing tier results

        Returns:
            Merged resources dictionary with combined configurations from all tiers.

        Raises:
            ValueError: If any required tier result is missing or has no best_subtest.

        """
        merged_resources: dict[str, Any] = {}
        failed_tier_ids: list[str] = []

        for tier_id in inherit_from_tiers:
            # 1. Load tier result.json to get best_subtest (from completed/ phase dir)
            from scylla.e2e.paths import get_subtest_dir, get_tier_dir

            completed_tier_dir = get_tier_dir(experiment_dir, tier_id.value, completed=True)
            result_file = completed_tier_dir / "result.json"
            best_subtest_file = completed_tier_dir / "best_subtest.json"

            best_subtest_id = None
            if result_file.exists():
                with open(result_file) as f:
                    tier_result = json.load(f)
                best_subtest_id = tier_result.get("best_subtest")

            if not best_subtest_id and best_subtest_file.exists():
                with open(best_subtest_file) as f:
                    selection = json.load(f)
                best_subtest_id = selection.get("winning_subtest")

            if not best_subtest_id:
                logger.warning(
                    f"Cannot inherit from {tier_id.value}: no best subtest found "
                    f"(tier may have failed). Skipping inheritance from {tier_id.value}."
                )
                failed_tier_ids.append(tier_id.value)
                continue

            # 2. Load config_manifest.json from best subtest (under completed/ phase dir)
            manifest_file = (
                get_subtest_dir(experiment_dir, tier_id.value, best_subtest_id, completed=True)
                / "config_manifest.json"
            )
            if not manifest_file.exists():
                # Best subtest failed before manifest was written — find an alternative
                tier_dir = completed_tier_dir
                alternative = None
                for subdir in sorted(tier_dir.iterdir()):
                    candidate = subdir / "config_manifest.json"
                    if subdir.is_dir() and candidate.exists():
                        alternative = candidate
                        logger.warning(
                            f"Best subtest {tier_id.value}/{best_subtest_id} has no "
                            f"config_manifest.json; falling back to "
                            f"{tier_id.value}/{subdir.name}"
                        )
                        break
                if alternative is None:
                    logger.warning(
                        f"No subtest in {tier_id.value} has config_manifest.json; "
                        f"skipping inheritance from {tier_id.value}"
                    )
                    continue
                manifest_file = alternative

            with open(manifest_file) as f:
                manifest = json.load(f)

            # 3. Merge resources
            subtest_resources = manifest.get("resources", {})
            self._merge_tier_resources(merged_resources, subtest_resources, tier_id)

        if failed_tier_ids and len(failed_tier_ids) == len(inherit_from_tiers):
            raise ValueError(
                f"Cannot build merged baseline: all required tiers failed "
                f"({', '.join(failed_tier_ids)}). At least one must complete for T5."
            )

        return merged_resources

    def _merge_tier_resources(  # noqa: C901  # file discovery with many path patterns
        self,
        merged_resources: dict[str, Any],
        new_resources: dict[str, Any],
        source_tier: TierID,
    ) -> None:
        """Merge resources from a tier into the accumulated merged resources.

        Implements tier-specific merge strategies:
        - claude_md.blocks: Replace (T0 only provides this)
        - skills.categories/names: Union (combine lists, deduplicate)
        - tools.enabled: "all" wins, else union
        - mcp_servers: Union by server name
        - agents.levels/names: Union (T3 L2-L5 + T4 L0-L1)

        Args:
            merged_resources: Accumulated resources to merge into (modified in place)
            new_resources: Resources from the source tier to merge
            source_tier: The tier ID being merged (for logging/debugging)

        """
        # Merge claude_md blocks (replace - T0 only)
        if "claude_md" in new_resources:
            merged_resources["claude_md"] = new_resources["claude_md"]

        # Merge skills (union)
        if "skills" in new_resources:
            if "skills" not in merged_resources:
                merged_resources["skills"] = {}

            new_skills = new_resources["skills"]

            # Merge categories
            if "categories" in new_skills:
                merged_categories = merged_resources["skills"].get("categories", [])
                merged_categories.extend(new_skills["categories"])
                merged_resources["skills"]["categories"] = list(set(merged_categories))

            # Merge names
            if "names" in new_skills:
                merged_names = merged_resources["skills"].get("names", [])
                merged_names.extend(new_skills["names"])
                merged_resources["skills"]["names"] = list(set(merged_names))

        # Merge tools ("all" wins, else union)
        if "tools" in new_resources:
            if "tools" not in merged_resources:
                merged_resources["tools"] = {}

            new_tools = new_resources["tools"]

            # Check for "all" - it wins
            new_enabled = new_tools.get("enabled", [])
            existing_enabled = merged_resources["tools"].get("enabled", [])

            if new_enabled == "all" or existing_enabled == "all":
                merged_resources["tools"]["enabled"] = "all"
            elif isinstance(new_enabled, list) and isinstance(existing_enabled, list):
                merged_enabled = existing_enabled + new_enabled
                merged_resources["tools"]["enabled"] = list(set(merged_enabled))

        # Merge MCP servers (union by server name)
        if "mcp_servers" in new_resources:
            if "mcp_servers" not in merged_resources:
                merged_resources["mcp_servers"] = []

            existing_servers = {s["name"]: s for s in merged_resources["mcp_servers"]}
            for server in new_resources["mcp_servers"]:
                server_name = server["name"]
                if server_name not in existing_servers:
                    merged_resources["mcp_servers"].append(server)

        # Merge agents (union)
        if "agents" in new_resources:
            if "agents" not in merged_resources:
                merged_resources["agents"] = {}

            new_agents = new_resources["agents"]

            # Merge levels
            if "levels" in new_agents:
                merged_levels = merged_resources["agents"].get("levels", [])
                merged_levels.extend(new_agents["levels"])
                merged_resources["agents"]["levels"] = sorted(set(merged_levels))

            # Merge names
            if "names" in new_agents:
                merged_names = merged_resources["agents"].get("names", [])
                merged_names.extend(new_agents["names"])
                merged_resources["agents"]["names"] = list(set(merged_names))
