#!/usr/bin/env python3
"""Replace vulnerable npm-bundled tar copies in a pre-commit cache."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MINIMUM_FIXED_VERSION = (7, 5, 21)
TARGET_PATTERN = "repo*/node_env-*/lib/node_modules/npm/node_modules/tar"
MARKDOWNLINT_PATTERN = "repo*/node_env-*/bin/markdownlint-cli2"


class PatchError(RuntimeError):
    """Report an invalid or incomplete Node tar patch."""


def _parse_version(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdecimal() for part in parts):
        raise PatchError(f"invalid tar version: {value!r}")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _package_version(directory: Path) -> str:
    manifest = directory / "package.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise PatchError(f"tar package manifest is not a regular file: {manifest}")

    try:
        package = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PatchError(f"cannot read tar package manifest {manifest}: {error}") from error

    if not isinstance(package, dict) or package.get("name") != "tar":
        raise PatchError(f"unexpected npm package manifest: {manifest}")
    version = package.get("version")
    if not isinstance(version, str):
        raise PatchError(f"tar package version is missing: {manifest}")
    _parse_version(version)
    return version


def _find_targets(cache_root: Path) -> list[Path]:
    targets = sorted(cache_root.glob(TARGET_PATTERN))
    if not targets:
        raise PatchError(f"no npm-bundled tar package found under {cache_root}")
    for target in targets:
        if target.is_symlink() or not target.is_dir():
            raise PatchError(f"tar patch target is not a regular directory: {target}")
    return targets


def _require_active_cache(cache_root: Path) -> Path:
    configured = os.environ.get("PRE_COMMIT_HOME")
    if configured is None:
        raise PatchError("PRE_COMMIT_HOME is not set")

    active_root = Path(configured).resolve(strict=True)
    requested_root = cache_root.resolve(strict=True)
    if active_root != requested_root:
        raise PatchError(
            f"cache root {requested_root} does not match PRE_COMMIT_HOME {active_root}"
        )
    return active_root


def _find_markdownlint(cache_root: Path) -> Path:
    executables = sorted(cache_root.glob(MARKDOWNLINT_PATTERN))
    if len(executables) != 1:
        raise PatchError(
            f"expected one markdownlint-cli2 under {cache_root}; found {len(executables)}"
        )
    executable = executables[0]
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise PatchError(f"markdownlint-cli2 is not executable: {executable}")
    return executable


def _run_markdownlint_smoke(executable: Path) -> None:
    environment = os.environ.copy()
    existing_path = environment.get("PATH")
    environment["PATH"] = (
        f"{executable.parent}{os.pathsep}{existing_path}"
        if existing_path
        else str(executable.parent)
    )
    with tempfile.TemporaryDirectory(prefix="scylla-markdownlint-") as directory:
        document = Path(directory) / "README.md"
        document.write_text("# CI image smoke test\n", encoding="utf-8")
        try:
            result = subprocess.run(
                [str(executable), str(document)],
                check=False,
                capture_output=True,
                cwd=directory,
                env=environment,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as error:
            raise PatchError("markdownlint-cli2 smoke test timed out") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise PatchError(f"markdownlint-cli2 smoke test failed: {detail}")


def patch_precommit_node_tar(cache_root: Path, source: Path, expected_version: str) -> int:
    """Replace each npm-bundled tar directory and return the patched count."""
    expected = _parse_version(expected_version)
    if expected < MINIMUM_FIXED_VERSION:
        raise PatchError(f"tar {expected_version} is below the CVE-2026-73566 fix floor 7.5.21")
    if source.is_symlink() or not source.is_dir():
        raise PatchError(f"tar patch source is not a regular directory: {source}")
    source_version = _package_version(source)
    if source_version != expected_version:
        raise PatchError(f"tar patch source is {source_version}; expected {expected_version}")

    targets = _find_targets(cache_root)

    for target in targets:
        staging = target.with_name(f".tar-{expected_version}-staging")
        if staging.exists() or staging.is_symlink():
            raise PatchError(f"tar patch staging path already exists: {staging}")
        shutil.copytree(source, staging)
        shutil.rmtree(target)
        staging.replace(target)

    for target in targets:
        installed_version = _package_version(target)
        if installed_version != expected_version:
            raise PatchError(f"tar patch verification failed for {target}: {installed_version}")

    return len(targets)


def verify_precommit_node_tar(cache_root: Path, minimum_version: str) -> int:
    """Verify the active cache's tar versions and execute its Markdown hook."""
    minimum = _parse_version(minimum_version)
    if minimum < MINIMUM_FIXED_VERSION:
        raise PatchError(f"tar verification floor {minimum_version} is below 7.5.21")

    active_root = _require_active_cache(cache_root)
    targets = _find_targets(active_root)
    for target in targets:
        installed_version = _package_version(target)
        if _parse_version(installed_version) < minimum:
            raise PatchError(
                f"tar verification failed for {target}: {installed_version} < {minimum_version}"
            )

    _run_markdownlint_smoke(_find_markdownlint(active_root))
    return len(targets)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    patch = commands.add_parser("patch", help="replace npm-bundled tar packages")
    patch.add_argument("--cache-root", type=Path, required=True)
    patch.add_argument("--source", type=Path, required=True)
    patch.add_argument("--expected-version", required=True)

    verify = commands.add_parser("verify", help="validate the active pre-commit cache")
    verify.add_argument("--cache-root", type=Path, required=True)
    verify.add_argument("--minimum-version", required=True)
    return parser.parse_args()


def main() -> int:
    """Run the command-line patch operation."""
    args = _parse_args()
    try:
        if args.command == "patch":
            count = patch_precommit_node_tar(
                args.cache_root,
                args.source,
                args.expected_version,
            )
            message = f"patched {count} npm-bundled tar package(s) to {args.expected_version}"
        else:
            count = verify_precommit_node_tar(args.cache_root, args.minimum_version)
            message = (
                f"verified {count} npm-bundled tar package(s) at or above "
                f"{args.minimum_version}; markdownlint-cli2 passed"
            )
    except (OSError, PatchError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1

    sys.stdout.write(f"{message}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
