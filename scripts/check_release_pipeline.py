#!/usr/bin/env python3
"""Validate the release pipeline is well-formed WITHOUT publishing.

Backs the canonical ``release`` check-run emitted by ``_required.yml`` on
every PR / main push. Publishing itself remains tag-only in
``.github/workflows/release.yml``; this guard makes that convention
executable by asserting:

1. ``release.yml`` triggers include ``on.push.tags: v*``.
2. Every publishing/releasing job (``release``, ``build``, ``publish-pypi``)
   is gated by the tag-push condition; ``publish-testpypi`` is gated on
   ``workflow_dispatch`` — nothing can publish from a PR / main push.
3. The publish jobs declare ``permissions.id-token: write`` and the
   ``pypi`` / ``testpypi`` environments (OIDC Trusted Publishing contract).
4. Every ``pypa/gh-action-pypi-publish`` usage is pinned to a full 40-hex SHA.
5. With ``--dist-dir``: the directory is non-empty, contains at least one
   wheel and one sdist, and every artifact filename version equals the
   canonical ``[project].version`` from ``pyproject.toml``.

Usage:
    python scripts/check_release_pipeline.py [--repo-root PATH] [--dist-dir PATH] [--verbose]

Exit codes:
    0: Release pipeline is well-formed (and dist artifacts match, if --dist-dir given)
    1: One or more invariants violated
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Publish action must be pinned to a full commit SHA (no branch/tag refs).
_SHA_PIN_RE = re.compile(r"^pypa/gh-action-pypi-publish@[0-9a-f]{40}$")

# Exact tag-gate expression required on every publishing/releasing job.
_TAG_GATE = "startsWith(github.ref, 'refs/tags/v')"

_TAG_GATED_JOBS = ("release", "build", "publish-pypi")

_PUBLISH_ACTION_PREFIX = "pypa/gh-action-pypi-publish@"


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


def load_release_workflow(repo_root: Path) -> dict[str, Any]:
    """Load and parse ``.github/workflows/release.yml``.

    Args:
        repo_root: Repository root directory.

    Returns:
        The parsed workflow as a dictionary.

    Raises:
        SystemExit: If the file is missing or unparseable.

    """
    path = repo_root / ".github" / "workflows" / "release.yml"
    if not path.is_file():
        print(f"ERROR: release workflow not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: Could not parse {path}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(workflow, dict):
        print(f"ERROR: {path} did not parse to a mapping", file=sys.stderr)
        sys.exit(1)

    return workflow


def get_triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return the workflow ``on:`` triggers.

    PyYAML parses the bare YAML 1.1 key ``on:`` as boolean ``True``; handle
    both the raw-string and coerced-key spellings.

    Args:
        workflow: Parsed workflow dictionary.

    Returns:
        The triggers mapping (empty if none found).

    """
    triggers: Any = workflow.get("on") or workflow.get(True) or {}  # type: ignore[call-overload]
    return triggers if isinstance(triggers, dict) else {}


def check_tag_trigger(workflow: dict[str, Any]) -> list[str]:
    """Check that ``on.push.tags`` contains the ``v*`` release-tag pattern.

    Args:
        workflow: Parsed workflow dictionary.

    Returns:
        List of error strings (empty if the check passes).

    """
    push = get_triggers(workflow).get("push") or {}
    tags = push.get("tags", []) if isinstance(push, dict) else []
    if isinstance(tags, str):
        tags = [tags]
    if "v*" not in tags:
        return [f"release.yml: on.push.tags must include 'v*' (found: {tags or 'none'})"]
    return []


def check_publish_gating(workflow: dict[str, Any]) -> list[str]:
    """Check that publishing/releasing jobs cannot run outside tag pushes.

    ``release``, ``build``, and ``publish-pypi`` must be gated by the exact
    tag-push condition; ``publish-testpypi`` must be gated on
    ``workflow_dispatch``.

    Args:
        workflow: Parsed workflow dictionary.

    Returns:
        List of error strings (empty if the check passes).

    """
    errors: list[str] = []
    jobs = workflow.get("jobs") or {}

    for job_name in _TAG_GATED_JOBS:
        job = jobs.get(job_name)
        if job is None:
            errors.append(f"release.yml: required job '{job_name}' is missing")
            continue
        job_if = str((job or {}).get("if", ""))
        if _TAG_GATE not in job_if:
            errors.append(
                f"release.yml: job '{job_name}' must gate on the tag-push condition "
                f"'github.event_name == 'push' && {_TAG_GATE}' — publishing must stay "
                "tag-only. Edit release.yml (not this check); scripts/"
                "check_release_pipeline.py enforces the documented convention."
            )

    testpypi_job = jobs.get("publish-testpypi")
    if testpypi_job is None:
        errors.append("release.yml: required job 'publish-testpypi' is missing")
    elif "workflow_dispatch" not in str((testpypi_job or {}).get("if", "")):
        errors.append("release.yml: job 'publish-testpypi' must gate on 'workflow_dispatch'")

    return errors


def _environment_name(job: dict[str, Any]) -> str | None:
    """Extract an effective environment name from a job definition.

    Args:
        job: Job definition dictionary.

    Returns:
        The environment name, or None if the job declares no environment.

    """
    env = job.get("environment")
    if isinstance(env, dict):
        return env.get("name")
    if isinstance(env, str):
        return env
    return None


def check_oidc_permissions(workflow: dict[str, Any]) -> list[str]:
    """Check the OIDC Trusted Publishing contract on the publish jobs.

    ``publish-pypi`` and ``publish-testpypi`` must declare
    ``permissions.id-token: write`` and use the ``pypi`` / ``testpypi``
    environments respectively.

    Args:
        workflow: Parsed workflow dictionary.

    Returns:
        List of error strings (empty if the check passes).

    """
    errors: list[str] = []
    jobs = workflow.get("jobs") or {}

    expectations = {
        "publish-pypi": "pypi",
        "publish-testpypi": "testpypi",
    }
    for job_name, expected_env in expectations.items():
        job = jobs.get(job_name)
        if job is None:
            # Missing-job error already reported by check_publish_gating.
            continue
        job = job or {}
        perms = job.get("permissions") or {}
        if not isinstance(perms, dict) or perms.get("id-token") != "write":
            errors.append(
                f"release.yml: job '{job_name}' must declare "
                "'permissions: id-token: write' (OIDC Trusted Publishing)"
            )
        env_name = _environment_name(job)
        if env_name != expected_env:
            errors.append(
                f"release.yml: job '{job_name}' must use environment "
                f"'{expected_env}' (found: {env_name!r})"
            )

    return errors


def check_action_pins(workflow: dict[str, Any]) -> list[str]:
    """Check every publish-action usage is pinned to a full 40-hex SHA.

    Args:
        workflow: Parsed workflow dictionary.

    Returns:
        List of error strings (empty if the check passes).

    """
    errors: list[str] = []
    jobs = workflow.get("jobs") or {}

    for job_name, job in sorted(jobs.items()):
        steps = (job or {}).get("steps") or []
        for step in steps:
            uses = str((step or {}).get("uses", ""))
            if not uses.startswith(_PUBLISH_ACTION_PREFIX):
                continue
            if not _SHA_PIN_RE.match(uses):
                errors.append(
                    f"release.yml: '{uses}' in job '{job_name}' must pin "
                    f"{_PUBLISH_ACTION_PREFIX}<full 40-hex commit SHA>"
                )
    return errors


def check_dist_matches_version(repo_root: Path, dist_dir: Path) -> list[str]:
    """Check built artifacts exist and carry exactly the pyproject version.

    Refuses an empty or missing dist directory (no vacuous pass), requires at
    least one wheel and one sdist, and requires every artifact filename to
    carry the canonical ``[project].version``.

    Args:
        repo_root: Repository root directory (for ``pyproject.toml``).
        dist_dir: Directory containing built distributions.

    Returns:
        List of error strings (empty if the check passes).

    """
    errors: list[str] = []
    version = get_canonical_version(repo_root / "pyproject.toml")

    if not dist_dir.is_dir():
        return [f"dist directory not found: {dist_dir}"]

    files = sorted(p.name for p in dist_dir.iterdir() if p.is_file())
    if not files:
        return [f"dist directory is empty: {dist_dir} (refusing vacuous pass)"]

    wheels = [f for f in files if f.endswith(".whl")]
    sdists = [f for f in files if f.endswith(".tar.gz")]

    if not wheels:
        errors.append(f"dist contains no wheel (.whl): {files}")
    if not sdists:
        errors.append(f"dist contains no sdist (.tar.gz): {files}")

    wheel_prefix = f"scylla-{version}-"
    sdist_name = f"scylla-{version}.tar.gz"

    for wheel in wheels:
        if not wheel.startswith(wheel_prefix):
            errors.append(
                f"wheel '{wheel}' does not match expected version prefix "
                f"'{wheel_prefix}<tags>.whl' (pyproject.toml version: {version})"
            )
    for sdist in sdists:
        if sdist != sdist_name:
            errors.append(
                f"sdist '{sdist}' does not match expected name "
                f"'{sdist_name}' (pyproject.toml version: {version})"
            )

    return errors


def check_release_pipeline(
    repo_root: Path,
    dist_dir: Path | None = None,
    verbose: bool = False,
) -> int:
    """Run all release-pipeline validation checks.

    Args:
        repo_root: Repository root directory.
        dist_dir: Optional directory of built distributions to validate
            against the canonical version.
        verbose: If True, print passing check names.

    Returns:
        0 if all checks pass, 1 if any fail.

    """
    workflow = load_release_workflow(repo_root)

    checks: list[tuple[str, list[str]]] = [
        ("tag trigger", check_tag_trigger(workflow)),
        ("publish gating", check_publish_gating(workflow)),
        ("OIDC permissions", check_oidc_permissions(workflow)),
        ("action pins", check_action_pins(workflow)),
    ]
    if dist_dir is not None:
        checks.append(("dist/version match", check_dist_matches_version(repo_root, dist_dir)))

    all_errors: list[str] = []
    for name, errors in checks:
        if errors:
            all_errors.extend(errors)
        elif verbose:
            print(f"PASS: {name}")

    if all_errors:
        for error in all_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"\nFound {len(all_errors)} release pipeline violation(s).",
            file=sys.stderr,
        )
        return 1

    if verbose:
        print("\nOK: Release pipeline is well-formed (dry-run, nothing published)")
    return 0


def main() -> int:
    """CLI entry point for release pipeline validation.

    Returns:
        Exit code (0 if well-formed, 1 if violations or errors).

    """
    parser = argparse.ArgumentParser(
        description=(
            "Validate the release pipeline is well-formed WITHOUT publishing "
            "(canonical `release` check)"
        ),
        epilog="Example: %(prog)s --dist-dir dist/ --verbose",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root directory (default: parent of this script's directory)",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory of built distributions (sdist + wheel) to "
            "validate against the pyproject.toml version"
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print passing check names",
    )

    args = parser.parse_args()
    return check_release_pipeline(
        args.repo_root,
        dist_dir=args.dist_dir,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
