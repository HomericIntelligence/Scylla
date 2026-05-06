#!/usr/bin/env python3
"""Compose CLAUDE.md from selected blocks.

Usage:
    python compose_claude_md.py B02 B07 B18 --output config/CLAUDE.md
    python compose_claude_md.py --preset minimal --output config/CLAUDE.md
    python compose_claude_md.py --preset core-seven --output config/CLAUDE.md
    python compose_claude_md.py --list  # List available blocks and presets

Presets:
    critical-only: B02 (~55 lines) - Just safety rules
    minimal:       B02, B07, B18 (~260 lines) - Minimum viable
    core-seven:    B02, B05, B07, B09, B12, B16, B18 (~400 lines) - Critical blocks
    no-examples:   All blocks with code examples stripped (~900 lines)
    full:          All 18 blocks (1787 lines)
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# Directory containing the extracted blocks (test inputs live under tests/claude-code/shared/)
REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCKS_DIR = REPO_ROOT / "tests" / "claude-code" / "shared" / "blocks"

# Block metadata
BLOCKS: dict[str, Any] = {
    "B01": {"file": "B01-project-overview.md", "desc": "Project Overview", "lines": 11},
    "B02": {"file": "B02-critical-rules.md", "desc": "Critical Rules (Safety)", "lines": 55},
    "B03": {"file": "B03-quick-links.md", "desc": "Quick Links", "lines": 17},
    "B04": {"file": "B04-agent-hierarchy-intro.md", "desc": "Agent Hierarchy Intro", "lines": 23},
    "B05": {"file": "B05-skill-delegation.md", "desc": "Skill Delegation Patterns", "lines": 69},
    "B06": {"file": "B06-dev-principles.md", "desc": "Development Principles", "lines": 29},
    "B07": {"file": "B07-language-preference.md", "desc": "Language Preference", "lines": 48},
    "B08": {"file": "B08-extended-thinking.md", "desc": "Extended Thinking", "lines": 67},
    "B09": {"file": "B09-skills-vs-subagents.md", "desc": "Skills vs Sub-Agents", "lines": 69},
    "B10": {"file": "B10-hooks-best-practices.md", "desc": "Hooks Best Practices", "lines": 66},
    "B11": {"file": "B11-output-style.md", "desc": "Output Style Guidelines", "lines": 148},
    "B12": {"file": "B12-tool-use-optimization.md", "desc": "Tool Use Optimization", "lines": 103},
    "B13": {"file": "B13-agentic-loops.md", "desc": "Agentic Loop Patterns", "lines": 116},
    "B14": {"file": "B14-delegation-mojo.md", "desc": "Delegation + Mojo", "lines": 48},
    "B15": {"file": "B15-common-commands.md", "desc": "Common Commands", "lines": 218},
    "B16": {"file": "B16-repo-architecture.md", "desc": "Repository Architecture", "lines": 134},
    "B17": {"file": "B17-testing-strategy.md", "desc": "Testing Strategy", "lines": 112},
    "B18": {"file": "B18-github-git-workflow.md", "desc": "GitHub/Git Workflow", "lines": 438},
}

# Preset configurations
PRESETS: dict[str, Any] = {
    "critical-only": {
        "blocks": ["B02"],
        "desc": "Just safety rules (~55 lines)",
    },
    "minimal": {
        "blocks": ["B02", "B07", "B18"],
        "desc": "Minimum viable (~260 lines)",
    },
    "core-seven": {
        "blocks": ["B02", "B05", "B07", "B09", "B12", "B16", "B18"],
        "desc": "Critical blocks (~400 lines)",
    },
    "no-examples": {
        "blocks": [f"B{i:02d}" for i in range(1, 19)],
        "desc": "All blocks, code examples stripped (~900 lines)",
        "strip_examples": True,
    },
    "full": {
        "blocks": [f"B{i:02d}" for i in range(1, 19)],
        "desc": "All 18 blocks (1787 lines)",
    },
}


def strip_code_blocks(content: str) -> str:
    """Remove fenced code blocks from markdown content."""
    # Pattern matches ```language ... ```
    pattern = r"```[a-zA-Z]*\n.*?```"
    return re.sub(pattern, "", content, flags=re.DOTALL)


def compose(blocks: list[str], output: Path, strip_examples: bool = False) -> None:
    """Compose CLAUDE.md from selected blocks."""
    content_parts = []

    for block_id in blocks:
        if block_id not in BLOCKS:
            print(f"Warning: Unknown block {block_id}, skipping")
            continue

        block_file = BLOCKS_DIR / BLOCKS[block_id]["file"]
        if not block_file.exists():
            print(f"Warning: Block file not found: {block_file}")
            continue

        with open(block_file) as f:
            block_content = f.read()

        content_parts.append(block_content)

    # Join blocks with a blank line separator
    full_content = "\n".join(content_parts)

    # Strip code examples if requested
    if strip_examples:
        full_content = strip_code_blocks(full_content)
        # Clean up excessive blank lines
        full_content = re.sub(r"\n{3,}", "\n\n", full_content)

    # Write output
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        f.write(full_content)

    line_count = full_content.count("\n") + 1
    print(f"Composed {len(blocks)} blocks into {output} ({line_count} lines)")


def list_blocks_and_presets() -> None:
    """List all available blocks and presets."""
    print("Available Blocks:")
    print("-" * 60)
    for block_id, info in sorted(BLOCKS.items()):
        print(f"  {block_id}: {info['desc']} ({info['lines']} lines)")

    print("\nAvailable Presets:")
    print("-" * 60)
    for preset_name, config in PRESETS.items():
        blocks_str = ", ".join(config["blocks"])
        print(f"  {preset_name}: {config['desc']}")
        print(f"    Blocks: {blocks_str}")


def main() -> None:
    """Compose CLAUDE.md from command line arguments."""
    parser = argparse.ArgumentParser(
        description="Compose CLAUDE.md from selected blocks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("blocks", nargs="*", help="Block IDs to include (e.g., B02 B07 B18)")
    parser.add_argument("--preset", choices=PRESETS.keys(), help="Use a preset configuration")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("CLAUDE.md"),
        help="Output file path (default: CLAUDE.md)",
    )
    parser.add_argument(
        "--strip-examples", action="store_true", help="Remove code examples from output"
    )
    parser.add_argument(
        "--list", "-l", action="store_true", help="List available blocks and presets"
    )

    args = parser.parse_args()

    if args.list:
        list_blocks_and_presets()
        return

    # Determine which blocks to use
    if args.preset:
        preset_config = PRESETS[args.preset]
        blocks = preset_config["blocks"]
        strip_examples = preset_config.get("strip_examples", False) or args.strip_examples
    elif args.blocks:
        blocks = args.blocks
        strip_examples = args.strip_examples
    else:
        parser.print_help()
        print("\nError: Specify blocks or use --preset")
        sys.exit(1)

    compose(blocks, args.output, strip_examples)


if __name__ == "__main__":
    main()
