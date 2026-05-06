#!/usr/bin/env python3
"""Generate all sub-tier configurations for testing.

This script generates the 27 unique configurations defined in the test plan,
using the compose_claude_md.py, compose_agents.py, and compose_skills.py scripts.

Usage:
    python generate_subtiers.py --model sonnet         # Generate for specific model
    python generate_subtiers.py --model all            # Generate for all models
    python generate_subtiers.py --tier T1              # Generate specific tier only
    python generate_subtiers.py --subtier T1/02-minimal-viable  # Generate specific subtier
    python generate_subtiers.py --list                 # List all configurations
    python generate_subtiers.py --dry-run              # Show what would be generated

Output Structure:
    tests/claude-code/<model>/<tier>/<subtier>/
        ├── config/
        │   ├── CLAUDE.md      # Composed from blocks
        │   ├── agents/        # Selected agents
        │   └── skills/        # Selected skills
        ├── test.yaml          # Test definition
        ├── prompt.md          # Task prompt (template)
        └── expected/          # Validation criteria
            ├── criteria.md
            └── rubric.yaml
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

# Base directory for tests; this script lives in scripts/claude_code_compose/, so we walk up to the
# repo root and into tests/claude-code/ where the generated subtier output trees live.
REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests" / "claude-code"
COMPOSE_DIR = Path(__file__).parent

# Models to generate for
MODELS = ["sonnet", "opus", "haiku"]

# Sub-tier configurations
# Format: tier -> subtier -> config
SUBTIERS: dict[str, dict[str, dict[str, Any]]] = {
    "T0-vanilla": {
        "00-baseline": {
            "desc": "Vanilla Claude - no CLAUDE.md, no agents, no skills",
            "claude_md": None,
            "agents": None,
            "skills": None,
        },
    },
    "T1-prompted": {
        "01-critical-rules-only": {
            "desc": "Just B02 Critical Rules (~55 lines)",
            "claude_md": "critical-only",
            "agents": None,
            "skills": None,
        },
        "02-minimal-viable": {
            "desc": "B02+B07+B18 (~260 lines)",
            "claude_md": "minimal",
            "agents": None,
            "skills": None,
        },
        "03-core-seven": {
            "desc": "7 critical blocks (~400 lines)",
            "claude_md": "core-seven",
            "agents": None,
            "skills": None,
        },
        "04-no-examples": {
            "desc": "Full prose, code examples stripped (~900 lines)",
            "claude_md": "no-examples",
            "agents": None,
            "skills": None,
        },
    },
    "T2-skills": {
        "01-github-skills-only": {
            "desc": "Minimal CLAUDE.md + GitHub skills",
            "claude_md": "minimal",
            "agents": None,
            "skills": "github-only",
        },
        "02-mojo-skills-only": {
            "desc": "Minimal CLAUDE.md + Mojo skills",
            "claude_md": "minimal",
            "agents": None,
            "skills": "mojo-only",
        },
        "03-workflow-skills-only": {
            "desc": "Minimal CLAUDE.md + Phase workflow skills",
            "claude_md": "minimal",
            "agents": None,
            "skills": "workflow-only",
        },
        "04-all-skills-minimal-md": {
            "desc": "Minimal CLAUDE.md + All 62 skills",
            "claude_md": "minimal",
            "agents": None,
            "skills": "full",
        },
        "05-critical-skills-only": {
            "desc": "Minimal CLAUDE.md + Top 10 critical skills",
            "claude_md": "minimal",
            "agents": None,
            "skills": "critical",
        },
    },
    "T3-agents": {
        "01-junior-only": {
            "desc": "Minimal CLAUDE.md + L5 Junior Engineers (3 agents)",
            "claude_md": "minimal",
            "agents": "junior-only",
            "skills": None,
        },
        "02-engineers-only": {
            "desc": "Minimal CLAUDE.md + L4+L5 Engineers (9 agents)",
            "claude_md": "minimal",
            "agents": "engineers-only",
            "skills": None,
        },
        "03-specialists-only": {
            "desc": "Minimal CLAUDE.md + L3 Specialists (24 agents)",
            "claude_md": "minimal",
            "agents": "specialists-only",
            "skills": None,
        },
        "04-orchestrators-only": {
            "desc": "Minimal CLAUDE.md + L0+L1 Orchestrators (7 agents)",
            "claude_md": "minimal",
            "agents": "orchestrators",
            "skills": None,
        },
        "05-review-agents-only": {
            "desc": "Minimal CLAUDE.md + Review specialists (13 agents)",
            "claude_md": "minimal",
            "agents": "review-agents",
            "skills": None,
        },
    },
    "T4-delegation": {
        "01-flat-no-hierarchy": {
            "desc": "Minimal CLAUDE.md + All agents (no delegation rules)",
            "claude_md": "minimal",
            "agents": "full",
            "skills": None,
        },
        "02-two-level": {
            "desc": "Minimal CLAUDE.md + L0→L4 only",
            "claude_md": "minimal",
            "agents": "two-level",
            "skills": None,
        },
        "03-three-level": {
            "desc": "Minimal CLAUDE.md + L0→L2→L4",
            "claude_md": "minimal",
            "agents": "three-level",
            "skills": None,
        },
        "04-skills-plus-agents": {
            "desc": "Minimal CLAUDE.md + All agents + All skills",
            "claude_md": "minimal",
            "agents": "full",
            "skills": "full",
        },
    },
    "T5-hierarchy": {
        "01-full-six-level": {
            "desc": "Core-seven CLAUDE.md + Full 6-level hierarchy + All skills",
            "claude_md": "core-seven",
            "agents": "full",
            "skills": "full",
        },
        "02-no-juniors": {
            "desc": "Core-seven CLAUDE.md + L0-L4 only (41 agents) + All skills",
            "claude_md": "core-seven",
            "agents": "no-juniors",
            "skills": "full",
        },
        "03-minimal-hierarchy": {
            "desc": "Core-seven CLAUDE.md + L0+L3+L5 + Dev-workflow skills",
            "claude_md": "core-seven",
            "agents": "minimal-hierarchy",
            "skills": "dev-workflow",
        },
        "04-orchestrators-plus-juniors": {
            "desc": "Core-seven CLAUDE.md + L0+L1+L5 + GitHub+Mojo skills",
            "claude_md": "core-seven",
            "agents": {"levels": [0, 1, 5]},
            "skills": "github-mojo",
        },
    },
    "T6-hybrid": {
        "01-full-system": {
            "desc": "Full CLAUDE.md + All agents + All skills (reference)",
            "claude_md": "full",
            "agents": "full",
            "skills": "full",
        },
        "02-optimized-core": {
            "desc": "Core-seven + Key agents (orchestrators+specialists) + Critical skills",
            "claude_md": "core-seven",
            "agents": {"levels": [0, 1, 3]},
            "skills": "critical",
        },
        "03-domain-optimized": {
            "desc": "Mojo-focused: Core blocks + Mojo agents + Mojo skills",
            "claude_md": "core-seven",
            "agents": "implementation",
            "skills": "mojo-only",
        },
    },
}


def run_compose_claude_md(preset: str, output: Path, dry_run: bool = False) -> None:
    """Run compose_claude_md.py with the given preset."""
    cmd = [
        sys.executable,
        str(COMPOSE_DIR / "compose_claude_md.py"),
        "--preset",
        preset,
        "--output",
        str(output / "CLAUDE.md"),
    ]
    if dry_run:
        print(f"  Would run: {' '.join(cmd)}")
    else:
        subprocess.run(cmd, check=True, capture_output=True)


def run_compose_agents(config: str | dict[str, Any], output: Path, dry_run: bool = False) -> None:
    """Run compose_agents.py with the given configuration."""
    cmd = [sys.executable, str(COMPOSE_DIR / "compose_agents.py")]

    if isinstance(config, str):
        cmd.extend(["--preset", config])
    elif isinstance(config, dict):
        if "levels" in config:
            levels_str = ",".join(str(level) for level in config["levels"])
            cmd.extend(["--levels", levels_str])
        if "pattern" in config:
            cmd.extend(["--pattern", config["pattern"]])

    cmd.extend(["--output", str(output / "agents")])

    if dry_run:
        print(f"  Would run: {' '.join(cmd)}")
    else:
        subprocess.run(cmd, check=True, capture_output=True)


def run_compose_skills(config: str | dict[str, Any], output: Path, dry_run: bool = False) -> None:
    """Run compose_skills.py with the given configuration."""
    cmd = [sys.executable, str(COMPOSE_DIR / "compose_skills.py")]

    if isinstance(config, str):
        cmd.extend(["--preset", config])
    elif isinstance(config, dict):
        if "categories" in config:
            cats_str = ",".join(config["categories"])
            cmd.extend(["--categories", cats_str])
        if "skills" in config:
            skills_str = ",".join(config["skills"])
            cmd.extend(["--skills", skills_str])

    cmd.extend(["--output", str(output / "skills")])

    if dry_run:
        print(f"  Would run: {' '.join(cmd)}")
    else:
        subprocess.run(cmd, check=True, capture_output=True)


def create_test_yaml(subtier_path: Path, tier: str, subtier: str, config: dict[str, Any]) -> None:
    """Create test.yaml file for the subtier."""
    test_id = f"{tier}-{subtier}".lower().replace("_", "-")
    content = f"""# Test configuration for {tier}/{subtier}
id: "{test_id}"
name: "{config["desc"]}"
description: |
  {config["desc"]}

  Configuration:
    - CLAUDE.md: {config.get("claude_md", "None")}
    - Agents: {config.get("agents", "None")}
    - Skills: {config.get("skills", "None")}

source:
  repo: "https://github.com/mvillmow/ProjectOdyssey"
  config_dir: "config/"

task:
  prompt_file: "prompt.md"
  timeout_seconds: 3600

validation:
  criteria_file: "expected/criteria.md"
  rubric_file: "expected/rubric.yaml"
"""
    (subtier_path / "test.yaml").write_text(content)


def create_prompt_template(subtier_path: Path) -> None:
    """Create a template prompt.md file."""
    content = """# Task Prompt

<!-- Replace this with the actual task prompt for evaluation -->

## Objective

[Describe the task objective]

## Requirements

- [ ] Requirement 1
- [ ] Requirement 2

## Constraints

- Constraint 1
- Constraint 2

## Expected Output

[Describe expected output format and criteria]
"""
    (subtier_path / "prompt.md").write_text(content)


def create_expected_files(subtier_path: Path) -> None:
    """Create template expected/ files."""
    expected_dir = subtier_path / "expected"
    expected_dir.mkdir(parents=True, exist_ok=True)

    # criteria.md
    criteria = """# Validation Criteria

## Functional Requirements

- [ ] Core functionality works correctly
- [ ] Edge cases handled appropriately
- [ ] No regressions introduced

## Quality Metrics

- [ ] Code follows project conventions
- [ ] Appropriate error handling
- [ ] Reasonable performance

## Process Metrics

- [ ] Task completed within timeout
- [ ] Minimal unnecessary operations
- [ ] Clear progress toward goal
"""
    (expected_dir / "criteria.md").write_text(criteria)

    # rubric.yaml
    rubric = """# Evaluation Rubric
version: "1.0"

metrics:
  pass_rate:
    description: "Task completion rate"
    weight: 0.4
    scale: [0, 1]

  impl_rate:
    description: "Requirement satisfaction rate"
    weight: 0.3
    scale: [0, 1]

  consistency:
    description: "Output stability across runs"
    weight: 0.2
    scale: [0, 1]

  efficiency:
    description: "Token/time efficiency"
    weight: 0.1
    scale: [0, 1]

thresholds:
  pass: 0.7
  good: 0.60
  excellent: 0.80
"""
    (expected_dir / "rubric.yaml").write_text(rubric)


def generate_subtier(
    model: str, tier: str, subtier: str, config: dict[str, Any], dry_run: bool = False
) -> None:
    """Generate a single subtier configuration."""
    subtier_path = TESTS_DIR / model / tier / subtier
    config_path = subtier_path / "config"

    if dry_run:
        print(f"\n{model}/{tier}/{subtier}:")
        print(f"  Description: {config['desc']}")
        config_path.mkdir(parents=True, exist_ok=True)  # Create for dry-run display
    else:
        # Create directories
        config_path.mkdir(parents=True, exist_ok=True)

    # Generate CLAUDE.md
    if config.get("claude_md"):
        run_compose_claude_md(config["claude_md"], config_path, dry_run)
    elif not dry_run:
        # Create empty marker for T0 baseline
        (config_path / "CLAUDE.md.empty").touch()

    # Generate agents
    if config.get("agents"):
        run_compose_agents(config["agents"], config_path, dry_run)

    # Generate skills
    if config.get("skills"):
        run_compose_skills(config["skills"], config_path, dry_run)

    # Create test files
    if not dry_run:
        create_test_yaml(subtier_path, tier, subtier, config)
        create_prompt_template(subtier_path)
        create_expected_files(subtier_path)
        print(f"  Generated: {model}/{tier}/{subtier}")


def list_configurations() -> None:
    """List all available configurations."""
    print("Sub-tier Configurations:")
    print("=" * 80)

    total = 0
    for tier, subtiers in SUBTIERS.items():
        print(f"\n{tier}:")
        print("-" * 40)
        for subtier, config in subtiers.items():
            total += 1
            print(f"  {subtier}:")
            print(f"    {config['desc']}")
            components = []
            if config.get("claude_md"):
                components.append(f"CLAUDE.md={config['claude_md']}")
            if config.get("agents"):
                components.append(f"agents={config['agents']}")
            if config.get("skills"):
                components.append(f"skills={config['skills']}")
            if components:
                print(f"    [{', '.join(components)}]")

    print(f"\nTotal: {total} configurations")
    print(f"Models: {', '.join(MODELS)}")
    print(f"Total test cases: {total * len(MODELS)}")


def main() -> None:  # CLI main with multiple tier generation modes
    """Generate sub-tier configurations from command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate sub-tier configurations for testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="all",
        help="Model to generate for (sonnet, opus, haiku, or 'all')",
    )
    parser.add_argument(
        "--tier", "-t", type=str, help="Specific tier to generate (e.g., T1-prompted)"
    )
    parser.add_argument(
        "--subtier",
        "-s",
        type=str,
        help="Specific subtier to generate (e.g., T1-prompted/02-minimal-viable)",
    )
    parser.add_argument("--list", "-l", action="store_true", help="List all configurations")
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be generated without creating files",
    )

    args = parser.parse_args()

    if args.list:
        list_configurations()
        return

    # Determine which models to generate for
    if args.model == "all":
        models = MODELS
    elif args.model in MODELS:
        models = [args.model]
    else:
        print(f"Error: Unknown model '{args.model}'. Use: {', '.join(MODELS)}")
        sys.exit(1)

    # Determine which tiers/subtiers to generate
    if args.subtier:
        # Parse subtier path (e.g., "T1-prompted/02-minimal-viable")
        parts = args.subtier.split("/")
        if len(parts) != 2:
            print("Error: Invalid subtier format. Use: tier/subtier")
            sys.exit(1)
        tier, subtier = parts
        if tier not in SUBTIERS:
            print(f"Error: Unknown tier '{tier}'")
            sys.exit(1)
        if subtier not in SUBTIERS[tier]:
            print(f"Error: Unknown subtier '{subtier}' in tier '{tier}'")
            sys.exit(1)
        tiers_to_generate = {tier: {subtier: SUBTIERS[tier][subtier]}}
    elif args.tier:
        if args.tier not in SUBTIERS:
            print(f"Error: Unknown tier '{args.tier}'")
            sys.exit(1)
        tiers_to_generate = {args.tier: SUBTIERS[args.tier]}
    else:
        tiers_to_generate = SUBTIERS

    # Generate configurations
    print("Generating configurations...")
    if args.dry_run:
        print("(Dry run - no files will be created)")

    count = 0
    for model in models:
        for tier, subtiers in tiers_to_generate.items():
            for subtier, config in subtiers.items():
                generate_subtier(model, tier, subtier, config, args.dry_run)
                count += 1

    print(f"\nGenerated {count} configurations")


if __name__ == "__main__":
    main()
