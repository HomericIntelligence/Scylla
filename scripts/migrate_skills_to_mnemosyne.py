#!/usr/bin/env python3
"""Migrate skills from Scylla flat format to ProjectMnemosyne plugin format.

This script handles:
- Format conversion from .claude-plugin/skills/<name>/ to plugins/<category>/<name>/
- Category resolution with normalization and fallbacks
- Author/date field normalization
- YAML frontmatter injection to SKILL.md
- plugin.json restructuring
- Overlap handling (merge newer, skip if target newer)
- Auto-validation and marketplace generation
- Cleanup of source skills after successful migration

Usage:
    python3 scripts/migrate_skills_to_mnemosyne.py [--dry-run] [--no-delete] [--skip-validation]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

# Category normalization map
CATEGORY_NORMALIZATION = {
    "metrics": "evaluation",
    "reporting": "evaluation",
}

# Category assignment fallback heuristics
CATEGORY_HEURISTICS = {
    "fix-": "debugging",
    "test": "testing",
    "ci-": "ci-cd",
    "refactor": "architecture",
    "parallel": "optimization",
    "paper-": "documentation",
    "publication-": "documentation",
    "arxiv-": "documentation",
    "latex-": "documentation",
    "academic-": "documentation",
}

# Hardcoded category assignments for specific skills
CATEGORY_ASSIGNMENTS = {
    "add-analysis-metric": "evaluation",
    "add-json-links-to-reports": "evaluation",
    "analysis-pipeline-code-review": "evaluation",
    "containerize-e2e-experiments": "evaluation",
    "dryrun-validation": "evaluation",
    "evaluation-report-fixes": "evaluation",
    "experimental-feature-subtests": "evaluation",
    "granular-scoring-systems": "evaluation",
    "parallel-metrics-integration": "evaluation",
    "processpool-rate-limit-recovery": "evaluation",
    "publication-pipeline-enhancement": "evaluation",
    "vega-lite-analysis-pipeline": "evaluation",
    "verify-experiment-completion": "evaluation",
    "defensive-analysis-patterns": "testing",
    "pytest-real-io-testing": "testing",
    "fix-ci-test-failures": "testing",
    "fix-pydantic-required-fields": "testing",
    "fix-tests-after-config-refactor": "testing",
    "refactor-for-extensibility": "architecture",
    "unify-config-structure": "architecture",
    "ci-test-failure-diagnosis": "ci-cd",
    "rescue-broken-prs": "ci-cd",
    "experiment-recovery-tools": "tooling",
    "review-task-orchestration": "tooling",
    "parallel-io-executor": "optimization",
    # Debugging category
    "checkpoint-config-mismatch": "debugging",
    "claude-code-settings-config": "debugging",
    "e2e-framework-bug-fixes": "debugging",
    "e2e-path-resolution-fix": "debugging",
    "fix-directory-not-created-before-write": "debugging",
    "fix-evaluation-framework-bugs": "debugging",
    "fix-judge-file-access": "debugging",
    "fix-rerun-completion": "debugging",
    "fix-rerun-script-errors": "debugging",
    "fix-yaml-config-propagation": "debugging",
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Migrate skills to ProjectMnemosyne")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Don't delete source skills after migration",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation and marketplace generation",
    )
    return parser.parse_args()


def resolve_category(skill_name: str, plugin_data: dict[str, Any]) -> str:
    """Resolve category for a skill using multiple strategies.

    Priority:
    1. Hardcoded assignment
    2. JSON category field (normalized)
    3. Heuristic based on skill name prefix
    4. Default to "tooling"
    """
    # 1. Hardcoded assignment
    if skill_name in CATEGORY_ASSIGNMENTS:
        return CATEGORY_ASSIGNMENTS[skill_name]

    # 2. JSON category (normalized)
    if "category" in plugin_data:
        category = plugin_data["category"]
        if category in CATEGORY_NORMALIZATION:
            return CATEGORY_NORMALIZATION[category]
        return cast(str, category)

    # 3. Heuristic
    for prefix, category in CATEGORY_HEURISTICS.items():
        if skill_name.startswith(prefix):
            return category

    # 4. Default
    return "tooling"


def normalize_author(author_field: Any) -> dict[str, Any]:
    """Normalize author field to dict format."""
    if isinstance(author_field, str):
        return {"name": author_field}
    return cast(dict[Any, Any], author_field)


def normalize_date(plugin_data: dict[str, Any]) -> str | None:
    """Normalize date field (created -> date)."""
    if "date" in plugin_data:
        return cast(str, plugin_data["date"])
    if "created" in plugin_data:
        return cast(str, plugin_data["created"])
    return None


def inject_yaml_frontmatter(
    skill_md_content: str, skill_name: str, plugin_data: dict[str, Any]
) -> str:
    """Inject YAML frontmatter to SKILL.md if missing.

    If frontmatter exists, return content as-is.
    Otherwise, add frontmatter with user-invocable: false.
    """
    if skill_md_content.startswith("---"):
        return skill_md_content

    # Extract first heading as name
    name_match = re.search(r"^#\s+(.+)$", skill_md_content, re.MULTILINE)
    name = name_match.group(1) if name_match else skill_name

    # Build frontmatter
    frontmatter = ["---"]
    frontmatter.append(f'name: "{name}"')

    if "description" in plugin_data:
        frontmatter.append(f'description: "{plugin_data["description"]}"')

    category = resolve_category(skill_name, plugin_data)
    frontmatter.append(f"category: {category}")

    date = normalize_date(plugin_data)
    if date:
        frontmatter.append(f"date: {date}")

    frontmatter.append("user-invocable: false")
    frontmatter.append("---")
    frontmatter.append("")

    return "\n".join(frontmatter) + skill_md_content


def restructure_plugin_json(plugin_data: dict[str, Any], skill_name: str) -> dict[str, Any]:
    """Restructure plugin.json to target format.

    Target format:
    {
      "name": "...",
      "version": "1.0.0",
      "description": "...",
      "skills": "./skills"
    }

    Remove: category, date, tags, keywords, triggers, outcomes, related_skills, etc.
    """
    result = {
        "name": plugin_data.get("name", skill_name),
        "version": plugin_data.get("version", "1.0.0"),
        "description": plugin_data.get("description", ""),
        "skills": "./skills",
    }

    return result


def get_skill_timestamp(skill_path: Path) -> float:
    """Get timestamp of most recently modified file in skill directory."""
    timestamps = []
    for f in skill_path.rglob("*"):
        if f.is_file():
            timestamps.append(f.stat().st_mtime)
    return max(timestamps) if timestamps else 0


def should_skip_migration(
    skill_name: str, source_path: Path, target_path: Path
) -> tuple[bool, str]:
    """Determine if skill migration should be skipped.

    Returns: (should_skip, reason)
    """
    if not target_path.exists():
        return False, ""

    source_time = get_skill_timestamp(source_path)
    target_time = get_skill_timestamp(target_path)

    if target_time > source_time:
        src_date = datetime.fromtimestamp(source_time)
        tgt_date = datetime.fromtimestamp(target_time)
        return (True, f"Target is newer ({tgt_date} > {src_date})")

    return False, ""


def extract_metadata_from_skill_md(skill_md_path: Path, skill_name: str) -> dict[str, Any]:
    """Extract metadata from SKILL.md for skills without plugin.json.

    Extracts:
    - First heading as name
    - Overview table for date/objective
    - Category from frontmatter or heuristic
    """
    content = skill_md_path.read_text()

    metadata = {
        "name": skill_name,
        "version": "1.0.0",
        "description": f"Skill for {skill_name.replace('-', ' ')}",
    }

    # Check for YAML frontmatter
    if content.startswith("---"):
        frontmatter_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            # Extract description
            desc_match = re.search(r'^description:\s*["\']?(.+?)["\']?$', frontmatter, re.MULTILINE)
            if desc_match:
                metadata["description"] = desc_match.group(1)
            # Extract date
            date_match = re.search(r"^date:\s*(.+)$", frontmatter, re.MULTILINE)
            if date_match:
                metadata["date"] = date_match.group(1)
            # Extract category
            cat_match = re.search(r"^category:\s*(.+)$", frontmatter, re.MULTILINE)
            if cat_match:
                metadata["category"] = cat_match.group(1)

    # Extract first heading as name
    name_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if name_match:
        heading = name_match.group(1)
        # Use heading for description if no frontmatter
        if (
            "description" not in metadata
            or metadata["description"] == f"Skill for {skill_name.replace('-', ' ')}"
        ):
            metadata["description"] = heading

    # Extract date from Overview table
    if "date" not in metadata:
        date_match = re.search(r"\|\s*\*\*Date\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})", content)
        if date_match:
            metadata["date"] = date_match.group(1)

    return metadata


def migrate_skill(
    skill_name: str,
    source_dir: Path,
    mnemosyne_dir: Path,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Migrate a single skill from source to target format.

    Returns: (success, message)
    """
    source_path = source_dir / skill_name

    # Read source plugin.json or skill.json
    plugin_json_path = source_path / "plugin.json"
    skill_json_path = source_path / "skill.json"
    skill_md_path = source_path / "SKILL.md"

    if plugin_json_path.exists():
        with open(plugin_json_path) as f:
            plugin_data = json.load(f)
    elif skill_json_path.exists():
        with open(skill_json_path) as f:
            plugin_data = json.load(f)
    elif skill_md_path.exists():
        # Generate plugin_data from SKILL.md
        plugin_data = extract_metadata_from_skill_md(skill_md_path, skill_name)
    else:
        return False, f"No plugin.json, skill.json, or SKILL.md found in {source_path}"

    # Resolve category
    category = resolve_category(skill_name, plugin_data)

    # Target path
    target_path = mnemosyne_dir / "plugins" / category / skill_name

    # Check if target exists before we modify it
    was_existing = target_path.exists() and any(target_path.iterdir())

    # Check if should skip
    should_skip, skip_reason = should_skip_migration(skill_name, source_path, target_path)
    if should_skip:
        return False, f"SKIP: {skip_reason}"

    if dry_run:
        action = "UPDATE" if was_existing else "CREATE"
        return True, f"[DRY-RUN] {action} {category}/{skill_name}"

    # Create target structure
    target_path.mkdir(parents=True, exist_ok=True)
    (target_path / ".claude-plugin").mkdir(exist_ok=True)
    (target_path / "skills" / skill_name).mkdir(parents=True, exist_ok=True)
    (target_path / "references").mkdir(exist_ok=True)

    # Copy and transform SKILL.md (handle both flat and nested formats)
    skill_md_source = source_path / "SKILL.md"
    skill_md_nested = source_path / "skills" / skill_name / "SKILL.md"

    if skill_md_source.exists():
        skill_md_content = skill_md_source.read_text()
        skill_md_content = inject_yaml_frontmatter(skill_md_content, skill_name, plugin_data)
        skill_md_target = target_path / "skills" / skill_name / "SKILL.md"
        skill_md_target.write_text(skill_md_content)
    elif skill_md_nested.exists():
        # Already in nested format, copy directly
        skill_md_content = skill_md_nested.read_text()
        skill_md_content = inject_yaml_frontmatter(skill_md_content, skill_name, plugin_data)
        skill_md_target = target_path / "skills" / skill_name / "SKILL.md"
        skill_md_target.write_text(skill_md_content)
    else:
        return False, f"No SKILL.md found in {source_path}"

    # Copy references/ directory if exists
    references_source = source_path / "references"
    if references_source.exists():
        references_target = target_path / "references"
        if references_target.exists():
            shutil.rmtree(references_target)
        shutil.copytree(references_source, references_target)
    else:
        # Create empty notes.md
        (target_path / "references" / "notes.md").write_text("# Notes\n\nNo additional notes.\n")

    # Write restructured plugin.json
    plugin_json_target = target_path / ".claude-plugin" / "plugin.json"
    restructured_data = restructure_plugin_json(plugin_data, skill_name)
    with open(plugin_json_target, "w") as f:
        json.dump(restructured_data, f, indent=2)
        f.write("\n")

    action = "UPDATED" if was_existing else "CREATED"
    return True, f"{action} {category}/{skill_name}"


def cleanup_flat_skills(mnemosyne_dir: Path, dry_run: bool = False) -> None:
    """Clean up flat skills/ directory in ProjectMnemosyne."""
    flat_skills_dir = mnemosyne_dir / "skills"
    if not flat_skills_dir.exists():
        return

    # Skills that exist in both flat and plugins/
    cleanup_candidates = [
        "checkpoint-config-mismatch",
        "claude-code-settings-config",
        "containerize-e2e-experiments",
        "experimental-feature-subtests",
        "fix-pydantic-required-fields",
        "fix-rerun-script-errors",
        "granular-scoring-systems",
        "preserve-workspace-reruns",
    ]

    for skill_name in cleanup_candidates:
        skill_path = flat_skills_dir / skill_name
        if skill_path.exists():
            if dry_run:
                print(f"[DRY-RUN] Would remove flat skills/{skill_name}/")
            else:
                shutil.rmtree(skill_path)
                print(f"Removed flat skills/{skill_name}/")


def main() -> int:  # CLI dispatch with many command branches
    """Execute the migration workflow."""
    args = parse_args()

    # Paths
    project_root = Path(__file__).parent.parent
    source_dir = project_root / ".claude-plugin" / "skills"
    mnemosyne_dir = project_root / "build" / "ProjectMnemosyne"

    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}")
        return 1

    if not mnemosyne_dir.exists():
        print(f"ProjectMnemosyne not found: {mnemosyne_dir}")
        print("Clone it to build/ProjectMnemosyne first")
        return 1

    # Get all skills
    skills = [d.name for d in source_dir.iterdir() if d.is_dir()]
    print(f"Found {len(skills)} skills to migrate\n")

    # Migrate each skill
    success_count = 0
    skip_count = 0
    error_count = 0

    for skill_name in sorted(skills):
        success, message = migrate_skill(skill_name, source_dir, mnemosyne_dir, args.dry_run)
        print(f"  {message}")

        if success:
            success_count += 1
        elif "SKIP" in message:
            skip_count += 1
        else:
            error_count += 1

    print("\nMigration Summary:")
    print(f"  Migrated: {success_count}")
    print(f"  Skipped: {skip_count}")
    print(f"  Errors: {error_count}")

    # Cleanup flat skills
    if not args.dry_run:
        print("\nCleaning up flat skills/ directory...")
        cleanup_flat_skills(mnemosyne_dir, args.dry_run)

    # Run validation
    if not args.skip_validation and not args.dry_run:
        print("\nRunning validation...")
        validate_script = mnemosyne_dir / "scripts" / "validate_plugins.py"
        plugins_dir = mnemosyne_dir / "plugins"

        result = subprocess.run(
            [sys.executable, str(validate_script), str(plugins_dir)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print("Validation failed:")
            print(result.stdout)
            print(result.stderr)
            return 1

        print("✅ Validation passed")

        # Generate marketplace
        print("\nGenerating marketplace...")
        generate_script = mnemosyne_dir / "scripts" / "generate_marketplace.py"
        marketplace_path = mnemosyne_dir / ".claude-plugin" / "marketplace.json"

        result = subprocess.run(
            [sys.executable, str(generate_script), str(plugins_dir), str(marketplace_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print("Marketplace generation failed:")
            print(result.stdout)
            print(result.stderr)
            return 1

        print("✅ Marketplace generated")

    # Delete source skills
    if not args.no_delete and not args.dry_run and error_count == 0:
        print("\nDeleting source skills...")
        for skill_name in sorted(skills):
            skill_path = source_dir / skill_name
            if skill_path.exists():
                shutil.rmtree(skill_path)
        print(f"✅ Deleted {len(skills)} source skills")

    return 0


if __name__ == "__main__":
    sys.exit(main())
