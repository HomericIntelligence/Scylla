#!/usr/bin/env python3
"""Enforce package version consistency across all version declaration sites.

Reads the canonical version from ``pyproject.toml`` ``[project].version`` and
validates that every other version declaration in the repository matches.

Checks (always run):
1. ``src/scylla/__init__.py`` ``__version__`` matches canonical version.

Check (opt-in via ``--scan-skills``):
2. Markdown files under ``.claude-plugin/skills/`` and ``.claude/`` do not
   reference version numbers higher than the canonical version.

Usage:
    python scripts/check_package_version_consistency.py
    python scripts/check_package_version_consistency.py --scan-skills
    python scripts/check_package_version_consistency.py --repo-root /path/to/repo --verbose

Exit codes:
    0: All checks pass
    1: One or more checks failed
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Matches semver-ish version strings: v1.5.0, 1.5.0, v2.0.0, 0.1.0, etc.
# Negative lookbehind excludes versions embedded in URL paths (e.g. /en/1.0.0/)
# and GitHub Action version pins (e.g. @v0.8.1).
_VERSION_RE = re.compile(r"(?<!/)(?<!@)\bv?(\d+\.\d+\.\d+)\b")

# Matches inline code spans: `...` or ``...`` (but not fenced code block markers).
_INLINE_CODE_RE = re.compile(r"``[^`]+``|`[^`]+`")


def _parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a ``"X.Y.Z"`` string into a tuple of ints for comparison.

    Args:
        version_str: A version string like ``"0.1.0"`` or ``"1.5.0"``.

    Returns:
        A tuple of integers, e.g. ``(0, 1, 0)``.

    """
    return tuple(int(part) for part in version_str.split("."))


def get_canonical_version(pyproject_path: Path) -> str:
    """Read the canonical package version from ``pyproject.toml``.

    Args:
        pyproject_path: Path to ``pyproject.toml``.

    Returns:
        The version string from ``[project].version``.

    Raises:
        SystemExit: If the file is missing, malformed, or lacks the version key.

    """
    if not pyproject_path.is_file():
        print(f"ERROR: pyproject.toml not found: {pyproject_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        print(f"ERROR: Could not parse {pyproject_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    version = data.get("project", {}).get("version")
    if not version:
        print(
            f"ERROR: No [project].version found in {pyproject_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    return str(version)


def check_init_version(repo_root: Path, canonical: str) -> list[str]:
    """Check that ``src/scylla/__init__.py`` ``__version__`` matches the canonical version.

    Args:
        repo_root: Repository root directory.
        canonical: The canonical version string from ``pyproject.toml``.

    Returns:
        List of error strings (empty if the check passes).

    """
    init_path = repo_root / "src" / "scylla" / "__init__.py"
    if not init_path.is_file():
        return [f"src/scylla/__init__.py not found at {init_path}"]

    content = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if not match:
        # Could be using importlib.metadata — that's fine
        return []

    init_version = match.group(1)
    if init_version != canonical:
        return [
            f"src/scylla/__init__.py: Version mismatch — "
            f"__version__ is '{init_version}', pyproject.toml has '{canonical}'"
        ]
    return []


def _strip_inline_code(line: str) -> str:
    """Replace inline code spans with whitespace so version matches inside them are ignored.

    Handles both single-backtick (``...``) and double-backtick (````...````) spans.

    Args:
        line: A single line of text.

    Returns:
        The line with inline code contents replaced by spaces.

    """
    return _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def find_aspirational_versions(
    file_path: Path,
    canonical_tuple: tuple[int, ...],
    label: str,
) -> list[str]:
    """Find version references in a file that are higher than the canonical version.

    Skips version references inside fenced code blocks (triple-backtick regions)
    and inline code spans (backtick-wrapped text), since these typically refer to
    external tool versions rather than the project's own version.

    Args:
        file_path: Path to the file to scan.
        canonical_tuple: The canonical version as a tuple of ints for comparison.
        label: Human-readable label for error messages (e.g. ``"SKILL.md"``).

    Returns:
        List of error strings for each aspirational version found.

    """
    content = file_path.read_text(encoding="utf-8")
    errors: list[str] = []
    in_code_block = False

    for line_num, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        # Toggle fenced code block state on ``` or ~~~ markers.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Strip inline code spans so versions inside backticks are ignored.
        scannable = _strip_inline_code(line)

        for match in _VERSION_RE.finditer(scannable):
            version_str = match.group(1)
            version_tuple = _parse_version_tuple(version_str)
            if version_tuple > canonical_tuple:
                errors.append(
                    f"{label}:{line_num}: Aspirational version reference "
                    f"'v{version_str}' exceeds canonical version "
                    f"'{'.'.join(str(p) for p in canonical_tuple)}'"
                )

    return errors


def check_skill_files(repo_root: Path, canonical: str) -> list[str]:
    """Scan skill template markdown files for aspirational version references.

    Scans ``*.md`` files under ``.claude-plugin/skills/`` and ``.claude/``
    for version numbers higher than the canonical version.

    Args:
        repo_root: Repository root directory.
        canonical: The canonical version string from ``pyproject.toml``.

    Returns:
        List of error strings (empty if all files pass).

    """
    canonical_tuple = _parse_version_tuple(canonical)
    errors: list[str] = []

    scan_dirs = [
        repo_root / ".claude-plugin" / "skills",
        repo_root / ".claude",
    ]

    # Directories to exclude from scanning (local-only worktrees, caches, etc.)
    skip_dirs = {"worktrees"}

    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for md_file in sorted(scan_dir.rglob("*.md")):
            # Skip files under excluded directories
            if any(part in skip_dirs for part in md_file.parts):
                continue
            rel_path = md_file.relative_to(repo_root)
            errors.extend(find_aspirational_versions(md_file, canonical_tuple, str(rel_path)))

    return errors


def check_package_version_consistency(
    repo_root: Path,
    scan_skills: bool = False,
    verbose: bool = False,
) -> int:
    """Run all package version consistency checks.

    Args:
        repo_root: Repository root directory.
        scan_skills: If True, also scan skill template files.
        verbose: If True, print passing check names.

    Returns:
        0 if all checks pass, 1 if any fail.

    """
    pyproject_path = repo_root / "pyproject.toml"
    canonical = get_canonical_version(pyproject_path)

    if verbose:
        print(f"Canonical version (pyproject.toml): {canonical}")

    all_errors: list[str] = []

    # Check 1: src/scylla/__init__.py
    init_errors = check_init_version(repo_root, canonical)
    if init_errors:
        all_errors.extend(init_errors)
    elif verbose:
        print(f"PASS: src/scylla/__init__.py __version__ matches ({canonical})")

    # Check 2: Skill files (opt-in)
    if scan_skills:
        skill_errors = check_skill_files(repo_root, canonical)
        if skill_errors:
            all_errors.extend(skill_errors)
        elif verbose:
            print("PASS: Skill template files have no aspirational version references")

    if all_errors:
        for error in all_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"\nFound {len(all_errors)} package version consistency violation(s).",
            file=sys.stderr,
        )
        return 1

    if verbose:
        print(f"\nOK: All package version checks passed ({canonical})")
    return 0


def main() -> int:
    """CLI entry point for package version consistency checking.

    Returns:
        Exit code (0 if consistent, 1 if mismatch or error).

    """
    parser = argparse.ArgumentParser(
        description="Enforce package version consistency across all version declaration sites",
        epilog="Example: %(prog)s --scan-skills --verbose",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root directory (default: parent of this script's directory)",
    )
    parser.add_argument(
        "--scan-skills",
        action="store_true",
        help=(
            "Also scan .claude-plugin/skills/ and .claude/ markdown files for aspirational versions"
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print passing check names and canonical version",
    )

    args = parser.parse_args()
    return check_package_version_consistency(
        args.repo_root,
        scan_skills=args.scan_skills,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
