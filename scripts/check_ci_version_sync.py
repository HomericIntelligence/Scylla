#!/usr/bin/env python3
"""Detect CI tooling version drift across config files.

Checks for version consistency across:
1. setup-uv action SHA: consistent across all workflow and action files
2. Gitleaks version: consistent across pre-commit config and security workflow

Usage:
    python scripts/check_ci_version_sync.py
    python scripts/check_ci_version_sync.py --repo-root /path/to/repo
    python scripts/check_ci_version_sync.py --verbose

Exit codes:
    0: All versions are consistent
    1: One or more checks failed
"""

import argparse
import re
import sys
from pathlib import Path


def get_setup_uv_shas(repo_root: Path) -> list[str]:
    """Extract all astral-sh/setup-uv@SHA references.

    Scans:
    1. All .github/**/*.yml files
    2. .github/actions/*/action.yml files

    Args:
        repo_root: Root directory of the repository.

    Returns:
        List of SHAs found (may be empty).

    """
    shas = []

    # Check workflows
    workflows_dir = repo_root / ".github" / "workflows"
    if workflows_dir.is_dir():
        for workflow_file in sorted(workflows_dir.glob("*.yml")):
            content = workflow_file.read_text()
            matches = re.findall(r"astral-sh/setup-uv@(\S+)", content)
            shas.extend(matches)

    # Check composite actions
    actions_dir = repo_root / ".github" / "actions"
    if actions_dir.is_dir():
        for action_file in sorted(actions_dir.glob("*/action.yml")):
            content = action_file.read_text()
            matches = re.findall(r"astral-sh/setup-uv@(\S+)", content)
            shas.extend(matches)

    return shas


def validate_setup_uv_sha_consistency(repo_root: Path, verbose: bool = False) -> int:
    """Validate setup-uv action SHA consistency across all config files.

    Checks that all astral-sh/setup-uv@SHA references use the same SHA.

    Args:
        repo_root: Root directory of the repository.
        verbose: If True, print detailed validation messages.

    Returns:
        0 if all SHAs match (or none found), 1 if drift is found.

    """
    shas = get_setup_uv_shas(repo_root)

    if not shas:
        if verbose:
            print("OK: No setup-uv SHA usage found")
        return 0

    unique_shas = set(shas)
    if len(unique_shas) > 1:
        print(
            f"ERROR: setup-uv action SHA inconsistency detected:\n"
            f"  Found {len(unique_shas)} different SHAs: {unique_shas}",
            file=sys.stderr,
        )
        return 1

    if verbose:
        sha = next(iter(unique_shas))
        print(f"OK: setup-uv SHA consistent ({sha})")
    return 0


def get_gitleaks_versions(repo_root: Path) -> list[str]:
    """Extract gitleaks version from all known locations.

    Scans:
    1. .pre-commit-config.yaml (gitleaks repo rev field)
    2. .github/workflows/security.yml (GITLEAKS_VERSION env var)

    Args:
        repo_root: Root directory of the repository.

    Returns:
        List of version strings found (may be empty).

    """
    versions = []

    # Check pre-commit config
    precommit_file = repo_root / ".pre-commit-config.yaml"
    if precommit_file.is_file():
        content = precommit_file.read_text()
        # Find gitleaks section and extract rev field
        match = re.search(
            r"repo:\s*https://github\.com/gitleaks/gitleaks\s*\n\s*rev:\s*(\S+)", content
        )
        if match:
            versions.append(match.group(1))

    # Check security workflow
    security_workflow = repo_root / ".github" / "workflows" / "security.yml"
    if security_workflow.is_file():
        content = security_workflow.read_text()
        # Find GITLEAKS_VERSION env var
        match = re.search(r'GITLEAKS_VERSION:\s*"?([^"\n]+)"?', content)
        if match:
            versions.append(match.group(1))

    return versions


def validate_gitleaks_consistency(repo_root: Path, verbose: bool = False) -> int:
    """Validate gitleaks version consistency across all config files.

    Checks that all gitleaks version references are identical (after normalizing
    the 'v' prefix).

    Args:
        repo_root: Root directory of the repository.
        verbose: If True, print detailed validation messages.

    Returns:
        0 if all versions match, 1 if drift is found.

    """
    versions = get_gitleaks_versions(repo_root)

    if not versions:
        if verbose:
            print("OK: No gitleaks version usage found")
        return 0

    # Normalize by removing leading 'v'
    normalized = [v.lstrip("v") for v in versions]
    unique = set(normalized)

    if len(unique) > 1:
        print(
            f"ERROR: Gitleaks version inconsistency detected:\n"
            f"  Found {len(unique)} different versions: {unique}",
            file=sys.stderr,
        )
        return 1

    if verbose:
        version = next(iter(unique))
        print(f"OK: Gitleaks version consistent ({version})")
    return 0


def check_ci_version_sync(repo_root: Path, verbose: bool = False) -> int:
    """Run all CI version sync checks.

    Returns:
        0 if all checks pass, 1 if any check fails.

    """
    results = [
        validate_setup_uv_sha_consistency(repo_root, verbose=verbose),
        validate_gitleaks_consistency(repo_root, verbose=verbose),
    ]

    return 1 if any(results) else 0


def main() -> int:
    """CLI entry point for CI version sync checking.

    Returns:
        Exit code (0 if all consistent, 1 if any mismatch or parse error).

    """
    parser = argparse.ArgumentParser(
        description="Detect CI tooling version drift across config files",
        epilog="Example: %(prog)s --repo-root /path/to/repo --verbose",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root directory (default: parent of this script's directory)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed validation messages",
    )

    args = parser.parse_args()
    return check_ci_version_sync(args.repo_root, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
