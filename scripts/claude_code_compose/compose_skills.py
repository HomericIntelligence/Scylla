#!/usr/bin/env python3
"""Compose skill configuration from selected categories.

Usage:
    python compose_skills.py --categories github,mojo --output config/skills/
    python compose_skills.py --preset critical --output config/skills/
    python compose_skills.py --skills gh-create-pr-linked,mojo-format --output config/skills/
    python compose_skills.py --list  # List available skills and presets

Presets:
    github-only:   10 gh-* skills
    mojo-only:     10 mojo-* skills
    workflow-only: 5 phase-* skills
    quality-only:  5 quality-* skills
    worktree-only: 4 worktree-* skills
    cicd-only:     8 CI/CD skills
    critical:      Top 10 most-used skills
    full:          All 62 skills
"""

import argparse
import shutil
import sys
from pathlib import Path

# Directory containing the organized skills (test inputs live under tests/claude-code/shared/)
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "tests" / "claude-code" / "shared" / "skills"

# Available categories
CATEGORIES = [
    "github",
    "mojo",
    "workflow",
    "quality",
    "worktree",
    "documentation",
    "agent",
    "cicd",
    "other",
]

# Critical skills (top 10 most-used based on workflow analysis)
CRITICAL_SKILLS = [
    "gh-create-pr-linked",
    "gh-review-pr",
    "gh-check-ci-status",
    "mojo-format",
    "mojo-test-runner",
    "run-precommit",
    "phase-implement",
    "worktree-create",
    "quality-fix-formatting",
    "verify-pr-ready",
]

# Preset configurations
PRESETS = {
    "github-only": {
        "categories": ["github"],
        "desc": "GitHub skills (10 skills)",
    },
    "mojo-only": {
        "categories": ["mojo"],
        "desc": "Mojo language skills (10 skills)",
    },
    "workflow-only": {
        "categories": ["workflow"],
        "desc": "Phase workflow skills (5 skills)",
    },
    "quality-only": {
        "categories": ["quality"],
        "desc": "Quality/linting skills (5 skills)",
    },
    "worktree-only": {
        "categories": ["worktree"],
        "desc": "Git worktree skills (4 skills)",
    },
    "documentation-only": {
        "categories": ["documentation"],
        "desc": "Documentation skills (4 skills)",
    },
    "agent-only": {
        "categories": ["agent"],
        "desc": "Agent system skills (5 skills)",
    },
    "cicd-only": {
        "categories": ["cicd"],
        "desc": "CI/CD skills (8 skills)",
    },
    "critical": {
        "skills": CRITICAL_SKILLS,
        "desc": "Top 10 most-used skills",
    },
    "github-mojo": {
        "categories": ["github", "mojo"],
        "desc": "GitHub + Mojo skills (20 skills)",
    },
    "dev-workflow": {
        "categories": ["github", "worktree", "quality", "cicd"],
        "desc": "Development workflow skills (27 skills)",
    },
    "full": {
        "categories": CATEGORIES,
        "desc": "All 62 skills (complete set)",
    },
}


def get_skills_by_category(category: str) -> list[Path]:
    """Get all skill directories in a category."""
    category_dir = SKILLS_DIR / category
    if not category_dir.exists():
        return []
    return [d for d in category_dir.iterdir() if d.is_dir()]


def get_skill_by_name(skill_name: str) -> Path | None:
    """Find a skill directory by name across all categories."""
    for category in CATEGORIES:
        skill_path = SKILLS_DIR / category / skill_name
        if skill_path.exists() and skill_path.is_dir():
            return skill_path
    return None


def compose(  # skill composition with many conditional branches
    categories: list[str] | None,
    skills: list[str] | None,
    output: Path,
) -> None:
    """Compose skills from selected categories or skill names to output directory."""
    skill_dirs = []

    if categories:
        for category in categories:
            skill_dirs.extend(get_skills_by_category(category))

    if skills:
        for skill_name in skills:
            skill_path = get_skill_by_name(skill_name)
            if skill_path:
                skill_dirs.append(skill_path)
            else:
                print(f"Warning: Skill not found: {skill_name}")

    # Remove duplicates while preserving order
    seen = set()
    unique_skills = []
    for skill_dir in skill_dirs:
        if skill_dir not in seen:
            seen.add(skill_dir)
            unique_skills.append(skill_dir)

    if not unique_skills:
        print("Warning: No skills matched the criteria")
        return

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)

    # Copy skill directories to output
    for skill_dir in unique_skills:
        dest = output / skill_dir.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)

    print(f"Composed {len(unique_skills)} skills into {output}")

    # Group by category for display
    by_category: dict[str, list[str]] = {}
    for skill in unique_skills:
        category = skill.parent.name
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(skill.name)

    for category in sorted(by_category.keys()):
        print(f"\n  {category}:")
        for skill_name in sorted(by_category[category]):
            print(f"    - {skill_name}")


def list_skills_and_presets() -> None:
    """List all available skills and presets."""
    print("Available Skills by Category:")
    print("-" * 60)

    total = 0
    for category in CATEGORIES:
        skills = get_skills_by_category(category)
        total += len(skills)
        print(f"\n  {category}: {len(skills)} skills")
        for skill in sorted(skills, key=lambda x: x.name):
            print(f"    - {skill.name}")

    print(f"\n  Total: {total} skills")

    print("\n\nAvailable Presets:")
    print("-" * 60)
    for preset_name, config in PRESETS.items():
        print(f"\n  {preset_name}: {config['desc']}")
        if "categories" in config:
            cats_str = ", ".join(config["categories"])
            print(f"    Categories: {cats_str}")
        if "skills" in config:
            skills_str = ", ".join(config["skills"][:5])
            if len(config["skills"]) > 5:
                skills_str += f", ... (+{len(config['skills']) - 5} more)"
            print(f"    Skills: {skills_str}")


def main() -> None:
    """Compose skill configuration from command line arguments."""
    parser = argparse.ArgumentParser(
        description="Compose skill configuration from selected categories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--categories",
        "-c",
        type=str,
        help="Comma-separated list of categories (e.g., github,mojo)",
    )
    parser.add_argument("--skills", "-s", type=str, help="Comma-separated list of skill names")
    parser.add_argument("--preset", choices=PRESETS.keys(), help="Use a preset configuration")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("skills"),
        help="Output directory (default: skills)",
    )
    parser.add_argument(
        "--list", "-l", action="store_true", help="List available skills and presets"
    )

    args = parser.parse_args()

    if args.list:
        list_skills_and_presets()
        return

    # Determine configuration
    categories = None
    skills = None

    if args.preset:
        preset_config = PRESETS[args.preset]
        _cats = preset_config.get("categories")
        categories = list(_cats) if _cats is not None else None
        _skills = preset_config.get("skills")
        skills = list(_skills) if _skills is not None else None
    else:
        if args.categories:
            categories = [c.strip() for c in args.categories.split(",")]
        if args.skills:
            skills = [s.strip() for s in args.skills.split(",")]

    if categories is None and skills is None:
        parser.print_help()
        print("\nError: Specify --categories, --skills, or --preset")
        sys.exit(1)

    compose(categories, skills, args.output)


if __name__ == "__main__":
    main()
