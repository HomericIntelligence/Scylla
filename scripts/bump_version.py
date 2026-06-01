#!/usr/bin/env python3
"""Bump the project version in pyproject.toml and pixi.toml atomically.

Reads the current version from ``pyproject.toml``, computes the new version
by incrementing the specified part (major, minor, or patch), and writes the
updated version to both ``pyproject.toml`` and ``pixi.toml``. After writing,
validates consistency via ``check_version_consistency``.

Usage:
    python scripts/bump_version.py patch
    python scripts/bump_version.py minor --dry-run
    python scripts/bump_version.py major --repo-root /path/to/repo --verbose

Exit codes:
    0: Version bumped successfully (or dry-run completed)
    1: Error reading/writing files or post-bump consistency check failed
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from scripts.check_version_consistency import check_version_consistency

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Regex to match version = "X.Y.Z" lines in TOML files
_PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
# Matches only the version line within the [workspace] section of pixi.toml.
# The pattern anchors to [workspace], then looks for the version = "..." line
# that follows (before any subsequent section header).
_PIXI_WORKSPACE_VERSION_RE = re.compile(
    r'(\[workspace\][^\[]*?version\s*=\s*")([^"]+)(")',
    re.DOTALL,
)


def get_current_version(repo_root: Path) -> tuple[int, int, int]:
    """Parse the current version from pyproject.toml.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        A tuple of ``(major, minor, patch)`` integers.

    Raises:
        SystemExit: With code 1 if the file is missing, malformed, or has
            no ``version`` field in ``[project]``.

    """
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.is_file():
        print(f"ERROR: pyproject.toml not found: {pyproject_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        print(f"ERROR: Could not parse {pyproject_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    project = data.get("project")
    if project is None:
        print(
            f"ERROR: No [project] section found in {pyproject_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    version_str = project.get("version")
    if version_str is None:
        print(
            f"ERROR: No version field in [project] section of {pyproject_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    parts = str(version_str).split(".")
    if len(parts) != 3:
        print(
            f"ERROR: Version '{version_str}' is not in X.Y.Z format",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        print(
            f"ERROR: Version '{version_str}' contains non-integer parts",
            file=sys.stderr,
        )
        sys.exit(1)
        return (0, 0, 0)  # unreachable, satisfies mypy


def compute_new_version(current: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    """Compute the new version by incrementing the specified part.

    Args:
        current: The current ``(major, minor, patch)`` version.
        part: Which part to bump — ``"major"``, ``"minor"``, or ``"patch"``.

    Returns:
        The new ``(major, minor, patch)`` version.

    Raises:
        ValueError: If ``part`` is not one of ``"major"``, ``"minor"``, ``"patch"``.

    """
    major, minor, patch = current
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    if part == "patch":
        return (major, minor, patch + 1)
    msg = f"Invalid part '{part}': must be 'major', 'minor', or 'patch'"
    raise ValueError(msg)


def update_pyproject_version(repo_root: Path, old: str, new: str) -> None:
    """Replace the version string in pyproject.toml.

    Args:
        repo_root: Root directory of the repository.
        old: The old version string to find.
        new: The new version string to write.

    Raises:
        SystemExit: With code 1 if the file is missing or the version line
            cannot be found.

    """
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.is_file():
        print(f"ERROR: pyproject.toml not found: {pyproject_path}", file=sys.stderr)
        sys.exit(1)

    content = pyproject_path.read_text()
    new_content, count = _PYPROJECT_VERSION_RE.subn(rf"\g<1>{new}\g<3>", content, count=1)
    if count == 0:
        print(
            f"ERROR: Could not find version line in {pyproject_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    pyproject_path.write_text(new_content)


def update_pixi_version(repo_root: Path, old: str, new: str) -> None:
    """Replace the version string in pixi.toml.

    Args:
        repo_root: Root directory of the repository.
        old: The old version string to find.
        new: The new version string to write.

    Raises:
        SystemExit: With code 1 if the file is missing or the version line
            cannot be found.

    """
    pixi_path = repo_root / "pixi.toml"
    if not pixi_path.is_file():
        print(f"ERROR: pixi.toml not found: {pixi_path}", file=sys.stderr)
        sys.exit(1)

    content = pixi_path.read_text()
    new_content, count = _PIXI_WORKSPACE_VERSION_RE.subn(rf"\g<1>{new}\g<3>", content, count=1)
    if count == 0:
        print(
            f"ERROR: Could not find version line in {pixi_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    pixi_path.write_text(new_content)


def create_git_tag(version: str, repo_root: Path, verbose: bool = False) -> int:
    """Create a git tag for the given version.

    Args:
        version: The version string (e.g. ``"0.2.0"``).
        repo_root: Root directory of the repository.
        verbose: If True, print additional details.

    Returns:
        0 on success, 1 on failure.

    """
    tag = f"v{version}"
    try:
        subprocess.run(
            ["git", "tag", tag],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Could not create git tag {tag}: {exc.stderr.strip()}", file=sys.stderr)
        return 1

    if verbose:
        print(f"Created git tag: {tag}")
    return 0


def bump_version(
    repo_root: Path,
    part: str,
    dry_run: bool = False,
    verbose: bool = False,
    tag: bool = False,
) -> int:
    """Bump the project version atomically across pyproject.toml and pixi.toml.

    Args:
        repo_root: Root directory of the repository.
        part: Which part to bump — ``"major"``, ``"minor"``, or ``"patch"``.
        dry_run: If True, print what would change without writing.
        verbose: If True, print additional details.
        tag: If True, create a git tag ``v<new_version>`` after bumping.

    Returns:
        0 on success, 1 on failure.

    """
    current = get_current_version(repo_root)
    old_str = f"{current[0]}.{current[1]}.{current[2]}"

    try:
        new = compute_new_version(current, part)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    new_str = f"{new[0]}.{new[1]}.{new[2]}"

    if dry_run:
        print(f"Would bump version: {old_str} -> {new_str}")
        return 0

    if verbose:
        print(f"Bumping version: {old_str} -> {new_str}")

    update_pyproject_version(repo_root, old_str, new_str)
    update_pixi_version(repo_root, old_str, new_str)

    # Validate consistency after writing
    result = check_version_consistency(repo_root, verbose=verbose)
    if result != 0:
        print(
            "ERROR: Post-bump consistency check failed. Files may be in an inconsistent state.",
            file=sys.stderr,
        )
        return 1

    # Optionally create a git tag for the new version
    if tag:
        tag_result = create_git_tag(new_str, repo_root, verbose=verbose)
        if tag_result != 0:
            return 1

    print(f"Version bumped: {old_str} -> {new_str}")
    print()
    print("Next steps:")
    print("  1. pixi lock")
    print("  2. git add pyproject.toml pixi.toml pixi.lock")
    print(f'  3. git commit -m "feat(release): bump version to {new_str}"')
    print("  4. git push --tags")
    return 0


def main() -> int:
    """CLI entry point for version bumping.

    Returns:
        Exit code (0 on success, 1 on failure).

    """
    parser = argparse.ArgumentParser(
        description="Bump project version in pyproject.toml and pixi.toml atomically",
        epilog="Example: %(prog)s patch --verbose",
    )
    parser.add_argument(
        "part",
        choices=["major", "minor", "patch"],
        help="Which version part to bump",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing",
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
        help="Print additional details",
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create a git tag v<new_version> after bumping",
    )

    args = parser.parse_args()
    return bump_version(
        repo_root=args.repo_root,
        part=args.part,
        dry_run=args.dry_run,
        verbose=args.verbose,
        tag=args.tag,
    )


if __name__ == "__main__":
    sys.exit(main())
