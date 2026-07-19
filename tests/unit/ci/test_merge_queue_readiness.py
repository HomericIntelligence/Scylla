"""Regression coverage for the staged merge-queue workflow readiness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS = _PROJECT_ROOT / ".github" / "workflows"
_REQUIRED_WORKFLOW = _WORKFLOWS / "_required.yml"
_SMOKE_WORKFLOW = _WORKFLOWS / "merge-queue-smoke.yml"

_REQUIRED_JOBS = {
    "lint": "lint",
    "unit-tests": "unit-tests",
    "integration-tests": "integration-tests",
    "security-dependency-scan": "security/dependency-scan",
    "security-secrets-scan": "security/secrets-scan",
    "build": "build",
    "schema-validation": "schema-validation",
    "deps-version-sync": "deps/version-sync",
    "test": "test",
    "package": "package",
    "install": "install",
}


def _load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow without YAML 1.1 coercing the ``on`` key to boolean."""
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    return workflow


def test_merge_group_runs_only_the_smoke_workflow() -> None:
    """The merge queue must run exactly one fast smoke job (one runner slot)."""
    required = _load_workflow(_REQUIRED_WORKFLOW)
    assert "merge_group" not in required["on"], (
        "_required.yml must not run for merge_group — merge-queue-smoke.yml owns that "
        "event so the queue consumes a single runner slot"
    )

    smoke = _load_workflow(_SMOKE_WORKFLOW)
    assert smoke["on"] == {"merge_group": {"types": ["checks_requested"]}}
    assert list(smoke["jobs"]) == ["merge-queue-smoke"]
    assert smoke["jobs"]["merge-queue-smoke"]["name"] == "merge-queue-smoke"
    assert smoke["jobs"]["merge-queue-smoke"]["timeout-minutes"] == "5"


def test_existing_required_check_triggers_and_contexts_are_preserved() -> None:
    """Queue readiness must not change existing PR/push gates or check names."""
    workflow = _load_workflow(_REQUIRED_WORKFLOW)

    assert workflow["on"]["pull_request"] == ""
    assert workflow["on"]["push"] == {"branches": ["main"]}
    assert workflow["permissions"] == {"contents": "read"}
    emitted_required_jobs = {job_id: workflow["jobs"][job_id]["name"] for job_id in _REQUIRED_JOBS}
    assert emitted_required_jobs == _REQUIRED_JOBS


def test_merge_group_does_not_expand_publish_or_release_workflows() -> None:
    """Merge groups must not gain package-publish or release side effects."""
    for workflow_name in ("ci-image.yml", "release.yml"):
        workflow = _load_workflow(_WORKFLOWS / workflow_name)
        assert "merge_group" not in workflow["on"]
