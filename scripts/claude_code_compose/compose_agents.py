#!/usr/bin/env python3
"""Compose agent configuration from selected levels/categories.

Usage:
    python compose_agents.py --levels 0,1,5 --output config/agents/
    python compose_agents.py --category review --output config/agents/
    python compose_agents.py --preset junior-only --output config/agents/
    python compose_agents.py --list  # List available agents and presets

Presets:
    junior-only:       L5 (3 agents) - Junior engineers
    engineers-only:    L4+L5 (9 agents) - All engineers
    specialists-only:  L3 (24 agents) - Specialists only
    orchestrators:     L0+L1 (7 agents) - Top-level orchestrators
    design-only:       L2 (4 agents) - Design agents
    review-agents:     13 review specialists (pattern match)
    implementation:    Implementation-focused agents
    full:              All 44 agents
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# Directory containing the organized agents (test inputs live under tests/claude-code/shared/)
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "tests" / "claude-code" / "shared" / "agents"

# Preset configurations
PRESETS: dict[str, Any] = {
    "junior-only": {
        "levels": [5],
        "desc": "L5 Junior Engineers (3 agents)",
    },
    "engineers-only": {
        "levels": [4, 5],
        "desc": "L4+L5 Engineers (9 agents)",
    },
    "specialists-only": {
        "levels": [3],
        "desc": "L3 Specialists (24 agents)",
    },
    "orchestrators": {
        "levels": [0, 1],
        "desc": "L0+L1 Orchestrators (7 agents)",
    },
    "design-only": {
        "levels": [2],
        "desc": "L2 Design Agents (4 agents)",
    },
    "review-agents": {
        "pattern": r".*-review-.*\.md$",
        "desc": "Review specialists (13 agents)",
    },
    "implementation": {
        "pattern": r"(implementation|engineer).*\.md$",
        "desc": "Implementation-focused agents",
    },
    "two-level": {
        "levels": [0, 4],
        "desc": "L0 → L4 only (flat delegation)",
    },
    "three-level": {
        "levels": [0, 2, 4],
        "desc": "L0 → L2 → L4 (intermediate design)",
    },
    "no-juniors": {
        "levels": [0, 1, 2, 3, 4],
        "desc": "L0-L4 (exclude juniors)",
    },
    "minimal-hierarchy": {
        "levels": [0, 3, 5],
        "desc": "L0+L3+L5 (orchestrators + specialists + juniors)",
    },
    "full": {
        "levels": [0, 1, 2, 3, 4, 5],
        "desc": "All 44 agents (complete hierarchy)",
    },
}


def get_agents_by_level(level: int) -> list[Path]:
    """Get all agent files at a specific level."""
    level_dir = AGENTS_DIR / f"L{level}"
    if not level_dir.exists():
        return []
    return list(level_dir.glob("*.md"))


def get_agents_by_pattern(pattern: str) -> list[Path]:
    """Get all agent files matching a regex pattern."""
    regex = re.compile(pattern)
    agents = []
    for level in range(6):
        level_dir = AGENTS_DIR / f"L{level}"
        if level_dir.exists():
            for agent_file in level_dir.glob("*.md"):
                if regex.match(agent_file.name):
                    agents.append(agent_file)
    return agents


def compose(
    levels: list[int] | None,
    pattern: str | None,
    output: Path,
) -> None:
    """Compose agents from selected levels or pattern to output directory."""
    agents = []

    if levels:
        for level in levels:
            agents.extend(get_agents_by_level(level))

    if pattern:
        agents.extend(get_agents_by_pattern(pattern))

    # Remove duplicates while preserving order
    seen = set()
    unique_agents = []
    for agent in agents:
        if agent not in seen:
            seen.add(agent)
            unique_agents.append(agent)

    if not unique_agents:
        print("Warning: No agents matched the criteria")
        return

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)

    # Copy agents to output
    for agent_file in unique_agents:
        dest = output / agent_file.name
        shutil.copy2(agent_file, dest)

    print(f"Composed {len(unique_agents)} agents into {output}")
    for agent in sorted(unique_agents, key=lambda x: x.name):
        print(f"  - {agent.name}")


def list_agents_and_presets() -> None:
    """List all available agents and presets."""
    print("Available Agents by Level:")
    print("-" * 60)

    total = 0
    for level in range(6):
        agents = get_agents_by_level(level)
        total += len(agents)
        print(f"\n  L{level}: {len(agents)} agents")
        for agent in sorted(agents, key=lambda x: x.name):
            print(f"    - {agent.name}")

    print(f"\n  Total: {total} agents")

    print("\n\nAvailable Presets:")
    print("-" * 60)
    for preset_name, config in PRESETS.items():
        print(f"\n  {preset_name}: {config['desc']}")
        if "levels" in config:
            levels_str = ", ".join(f"L{level}" for level in config["levels"])
            print(f"    Levels: {levels_str}")
        if "pattern" in config:
            print(f"    Pattern: {config['pattern']}")


def main() -> None:
    """Compose agent configuration from command line arguments."""
    parser = argparse.ArgumentParser(
        description="Compose agent configuration from selected levels/categories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--levels", "-l", type=str, help="Comma-separated list of levels (e.g., 0,1,5)"
    )
    parser.add_argument("--pattern", "-p", type=str, help="Regex pattern to match agent filenames")
    parser.add_argument("--preset", choices=PRESETS.keys(), help="Use a preset configuration")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("agents"),
        help="Output directory (default: agents)",
    )
    parser.add_argument("--list", action="store_true", help="List available agents and presets")

    args = parser.parse_args()

    if args.list:
        list_agents_and_presets()
        return

    # Determine configuration
    levels = None
    pattern = None

    if args.preset:
        preset_config = PRESETS[args.preset]
        levels = preset_config.get("levels")
        pattern = preset_config.get("pattern")
    else:
        if args.levels:
            levels = [int(level.strip()) for level in args.levels.split(",")]
        pattern = args.pattern

    if levels is None and pattern is None:
        parser.print_help()
        print("\nError: Specify --levels, --pattern, or --preset")
        sys.exit(1)

    compose(levels, pattern, args.output)


if __name__ == "__main__":
    main()
