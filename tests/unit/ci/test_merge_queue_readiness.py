"""Regression coverage for required-check parity on merge-queue commits."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS = _PROJECT_ROOT / ".github" / "workflows"
_REQUIRED_WORKFLOW = _WORKFLOWS / "_required.yml"
_CONCURRENCY_GROUP = (
    "${{ github.workflow }}-${{ github.event_name }}-"
    "${{ github.event.pull_request.number || github.sha }}"
)
_CI_IMAGE_HELPER = "ci/patch_precommit_node_tar.py"

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
_REQUIRED_CONTEXTS = frozenset(_REQUIRED_JOBS.values())

_CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
_CACHE = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
_UPLOAD_ARTIFACT = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
_DOWNLOAD_ARTIFACT = "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
_SETUP_UV = "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9"
_SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
_CODECOV = "codecov/codecov-action@fb8b3582c8e4def4969c97caa2f19720cb33a72f"
_PINNED_ACTION = re.compile(r"[^@\s]+@[0-9a-f]{40}")

_BUILD_IMAGE = ("podman build -f ci/Containerfile -t scylla-ci:local .",)
_CACHE_INPUTS = {
    "path": "~/.local/share/containers/storage",
    "key": (
        "podman-scylla-${{ runner.os }}-"
        "${{ hashFiles('pyproject.toml', 'uv.lock', '.pre-commit-config.yaml') }}"
    ),
    "restore-keys": "podman-scylla-${{ runner.os }}-\n",
}
_SETUP_UV_INPUTS = {"enable-cache": "true"}

_EXPECTED_NEEDS: dict[str, list[str] | None] = {
    "lint": None,
    "unit-tests": None,
    "integration-tests": None,
    "security-dependency-scan": None,
    "security-secrets-scan": None,
    "build": None,
    "schema-validation": None,
    "deps-version-sync": None,
    "test": ["unit-tests", "integration-tests"],
    "package": ["build"],
    "install": ["build"],
}

# Every run step in each required job is bound by name and by its complete
# normalized payload. This rejects extra, removed, relocated, or fail-open
# shell commands rather than accepting a validator substring.
_EXPECTED_RUN_STEPS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "lint": (
        ("Build CI image (podman)", _BUILD_IMAGE),
        ("Lint (in container)", ("bash scripts/run_ci_local.sh lint",)),
    ),
    "unit-tests": (
        ("Build CI image (podman)", _BUILD_IMAGE),
        ("Unit tests (in container)", ("bash scripts/run_ci_local.sh unit",)),
    ),
    "integration-tests": (
        ("Build CI image (podman)", _BUILD_IMAGE),
        (
            "Integration tests (in container)",
            ("bash scripts/run_ci_local.sh integration",),
        ),
    ),
    "security-dependency-scan": (
        ("Build CI image (podman)", _BUILD_IMAGE),
        ("Run pip-audit (in container)", ("bash scripts/run_ci_local.sh security",)),
        (
            "Post pip-audit summary",
            (
                "{",
                'echo "## pip-audit Security Scan"',
                'echo ""',
                'if [ "$AUDIT_OUTCOME" = "success" ]; then',
                'echo "No HIGH/CRITICAL vulnerabilities found."',
                "else",
                'echo "Vulnerabilities detected — see job logs for details."',
                "fi",
                '} >> "$GITHUB_STEP_SUMMARY"',
            ),
        ),
    ),
    "security-secrets-scan": (
        ("Build CI image (podman)", _BUILD_IMAGE),
        ("Run Gitleaks (in container)", ("bash scripts/run_ci_local.sh secrets",)),
    ),
    "build": (
        (
            "Validate Dockerfile syntax",
            (
                "# Validate all Dockerfiles in the repo using docker build --check "
                "(BuildKit dry-run)",
                'find . -name "Dockerfile*" \\',
                '-not -path "./.venv/*" \\',
                '-not -path "./docker/*" \\',
                "| sort | while read -r df; do",
                'echo "Checking $df ..."',
                'docker build --check -f "$df" . || exit 1',
                "done",
                "# Also check docker/ subdirectory Dockerfiles independently",
                'find ./docker -name "Dockerfile*" 2>/dev/null | sort | while read -r df; do',
                'echo "Checking $df ..."',
                'docker build --check -f "$df" ./docker || exit 1',
                "done",
            ),
        ),
        (
            "Install locked build environment",
            (
                "# The 'build' frontend and hatchling backend are in [dependency-groups].dev;",
                "# --no-isolation then builds against the synced environment.",
                "uv sync --all-groups --all-extras --locked",
            ),
        ),
        (
            "Build Python package (sdist + wheel)",
            ("uv run python -m build --no-isolation", "ls -lh dist/"),
        ),
    ),
    "schema-validation": (
        ("Build CI image (podman)", _BUILD_IMAGE),
        ("Validate schemas (in container)", ("bash scripts/run_ci_local.sh schema",)),
    ),
    "deps-version-sync": (
        ("Build CI image (podman)", _BUILD_IMAGE),
        ("Check version sync (in container)", ("bash scripts/run_ci_local.sh deps",)),
    ),
    "test": (
        (
            "Aggregate test result",
            ('echo "All required test suites (unit-tests, integration-tests) passed."',),
        ),
    ),
    "package": (
        (
            "Install locked project environment",
            ("uv sync --all-groups --all-extras --locked",),
        ),
        ("Validate distribution metadata (twine check)", ("uv run twine check dist/*",)),
    ),
    "install": (
        (
            "Install wheel into clean venv",
            (
                "python -m venv /tmp/scylla-install-venv",
                "/tmp/scylla-install-venv/bin/pip install --upgrade pip",
                "# Install the built wheel (not the source tree) to prove the package",
                "# installs from its distributable artifact.",
                "wheel=$(ls dist/*.whl | head -1)",
                'echo "Installing ${wheel}"',
                '/tmp/scylla-install-venv/bin/pip install "${wheel}"',
            ),
        ),
        (
            "Smoke-test console entry point",
            (
                "/tmp/scylla-install-venv/bin/scylla --help",
                '/tmp/scylla-install-venv/bin/python -c "import scylla; '
                "print('scylla', getattr(scylla, '__version__', 'imported'))\"",
            ),
        ),
    ),
}

# Action steps are also exact, ordered contracts. Full input mappings make
# artifact identity, interpreter versions, cache identity, and diagnostic
# behavior fail closed instead of accepting a merely pinned action.
_EXPECTED_ACTION_STEPS: dict[str, tuple[tuple[str, dict[str, str]], ...]] = {
    "lint": (
        (_CHECKOUT, {"fetch-depth": "0"}),
        (_CACHE, _CACHE_INPUTS),
        (
            _UPLOAD_ARTIFACT,
            {
                "name": "pre-commit-diffs",
                "retention-days": "7",
                "path": ".git/pre-commit-*\n",
            },
        ),
    ),
    "unit-tests": (
        (_CHECKOUT, {}),
        (_CACHE, _CACHE_INPUTS),
        (
            _CODECOV,
            {
                "files": "./coverage.xml",
                "flags": "unit",
                "token": "${{ secrets.CODECOV_TOKEN }}",
                "fail_ci_if_error": "false",
            },
        ),
        (
            _UPLOAD_ARTIFACT,
            {
                "name": "test-results-unit",
                "path": "coverage.xml\njunit-unit.xml\n",
                "retention-days": "7",
            },
        ),
    ),
    "integration-tests": (
        (_CHECKOUT, {}),
        (_CACHE, _CACHE_INPUTS),
        (
            _UPLOAD_ARTIFACT,
            {
                "name": "test-results-integration",
                "path": "coverage.xml\njunit-integration.xml\n",
                "retention-days": "7",
            },
        ),
    ),
    "security-dependency-scan": ((_CHECKOUT, {}), (_CACHE, _CACHE_INPUTS)),
    "security-secrets-scan": (
        (_CHECKOUT, {"fetch-depth": "0"}),
        (_CACHE, _CACHE_INPUTS),
    ),
    "build": (
        (_CHECKOUT, {}),
        (_SETUP_UV, _SETUP_UV_INPUTS),
        (
            _UPLOAD_ARTIFACT,
            {
                "name": "python-package",
                "path": "dist/",
                "if-no-files-found": "error",
                "retention-days": "7",
            },
        ),
    ),
    "schema-validation": ((_CHECKOUT, {}), (_CACHE, _CACHE_INPUTS)),
    "deps-version-sync": ((_CHECKOUT, {}), (_CACHE, _CACHE_INPUTS)),
    "test": (),
    "package": (
        (_CHECKOUT, {}),
        (_SETUP_UV, _SETUP_UV_INPUTS),
        (_DOWNLOAD_ARTIFACT, {"name": "python-package", "path": "dist/"}),
    ),
    "install": (
        (_SETUP_PYTHON, {"python-version": "3.13"}),
        (_DOWNLOAD_ARTIFACT, {"name": "python-package", "path": "dist/"}),
    ),
}

# These steps only upload diagnostics or write a summary. The real validator
# steps remain unconditional, and no continue-on-error form is allowed.
_ALLOWED_STEP_CONDITIONS = {
    ("lint", "Upload pre-commit diff"): "failure()",
    ("unit-tests", "Upload test artifacts on failure"): "failure()",
    ("integration-tests", "Upload test artifacts on failure"): "failure()",
    ("security-dependency-scan", "Post pip-audit summary"): "always()",
}


class _UniqueKeyBaseLoader(yaml.BaseLoader):
    """Load scalar values as strings while rejecting duplicate YAML keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyBaseLoader, node: yaml.MappingNode, *, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        assert key not in mapping, f"duplicate YAML key: {key!r}"
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyBaseLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _workflow_paths() -> tuple[Path, ...]:
    """Return every GitHub workflow, including both supported YAML suffixes."""
    paths = tuple(sorted((*_WORKFLOWS.glob("*.yml"), *_WORKFLOWS.glob("*.yaml"))))
    assert paths, "no GitHub workflows found"
    return paths


def _load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow without YAML 1.1 coercing the ``on`` key to Boolean."""
    workflow = yaml.load(path.read_text(), Loader=_UniqueKeyBaseLoader)
    assert isinstance(workflow, dict), f"{path.name} must contain a YAML mapping"
    assert isinstance(workflow.get("on"), dict), f"{path.name} must declare event triggers"
    assert isinstance(workflow.get("jobs"), dict), f"{path.name} must declare jobs"
    return workflow


def _job_context(job_id: str, job: Any, *, workflow_name: str) -> str:
    assert isinstance(job, dict), f"{workflow_name}:{job_id} must be a job mapping"
    context = job.get("name", job_id)
    assert isinstance(context, str) and context, f"{workflow_name}:{job_id} has no check name"
    return context


def _concurrency_key(
    *, workflow: str, event_name: str, pull_request_number: int | None, sha: str
) -> str:
    """Model the required Actions concurrency expression for collision checks."""
    run_identity = str(pull_request_number) if pull_request_number is not None else sha
    return f"{workflow}-{event_name}-{run_identity}"


def _has_write_permission(permissions: Any, *, owner: str) -> bool:
    if permissions is None:
        return False
    if isinstance(permissions, str):
        assert permissions in {"read-all", "write-all"}, f"{owner} has invalid permissions"
        return permissions == "write-all"
    assert isinstance(permissions, dict), f"{owner} permissions must be a mapping"
    return any(level == "write" for level in permissions.values())


def _normalize_run_payload(value: Any) -> tuple[str, ...]:
    """Normalize layout while retaining every executable and comment line."""
    assert isinstance(value, str), f"run payload must be a string, got {value!r}"
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return tuple(line.strip() for line in normalized.splitlines() if line.strip())


def _assert_required_job_contracts(workflow: dict[str, Any]) -> None:
    """Validate the executable contract for every ruleset-required job."""
    assert set(_EXPECTED_NEEDS) == set(_REQUIRED_JOBS)
    assert set(_EXPECTED_RUN_STEPS) == set(_REQUIRED_JOBS)
    assert set(_EXPECTED_ACTION_STEPS) == set(_REQUIRED_JOBS)
    assert "defaults" not in workflow, "workflow run defaults can change validator semantics"

    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "required workflow jobs must be a mapping"
    seen_conditions: dict[tuple[str, str], str] = {}

    for job_id, expected_context in _REQUIRED_JOBS.items():
        job = jobs.get(job_id)
        assert isinstance(job, dict), f"required job {job_id!r} is missing"
        assert job.get("name") == expected_context, (
            f"{job_id} must emit the static context {expected_context!r}"
        )
        assert "${{" not in expected_context
        assert "strategy" not in job, f"{job_id} must not expand into matrix contexts"
        assert "if" not in job, f"{job_id} must use the implicit success result gate"
        assert "continue-on-error" not in job, f"{job_id} must fail closed"
        assert "defaults" not in job, f"{job_id} run defaults can change validator semantics"
        assert "env" not in job, f"{job_id} job-level env can change validator semantics"

        runs_on = job.get("runs-on")
        assert isinstance(runs_on, str) and runs_on and "${{" not in runs_on, (
            f"{job_id} must use one static runner"
        )

        expected_needs = _EXPECTED_NEEDS[job_id]
        if expected_needs is None:
            assert "needs" not in job, f"{job_id} gained an undeclared dependency"
        else:
            assert job.get("needs") == expected_needs, (
                f"{job_id} must require exactly {expected_needs!r}; the implicit success() "
                "gate binds each dependency result"
            )

        steps = job.get("steps")
        assert isinstance(steps, list) and steps, f"{job_id} must execute real validation steps"
        actual_runs: list[tuple[str, tuple[str, ...]]] = []
        actual_actions: list[tuple[str, dict[str, str]]] = []

        for index, step in enumerate(steps):
            assert isinstance(step, dict), f"{job_id}:step-{index} must be a mapping"
            assert "continue-on-error" not in step, (
                f"{job_id}:step-{index} must not suppress failures"
            )

            step_name = step.get("name")
            if "if" in step:
                assert isinstance(step_name, str), f"{job_id}:step-{index} condition is unnamed"
                condition_key = (job_id, step_name)
                assert condition_key in _ALLOWED_STEP_CONDITIONS, (
                    f"{job_id}:{step_name} has an unapproved condition"
                )
                expected_condition = _ALLOWED_STEP_CONDITIONS[condition_key]
                assert step["if"] == expected_condition, (
                    f"{job_id}:{step_name} condition must be {expected_condition!r}"
                )
                seen_conditions[condition_key] = step["if"]

            executable_fields = {field for field in ("run", "uses") if field in step}
            assert len(executable_fields) == 1, (
                f"{job_id}:step-{index} must execute exactly one command or action"
            )

            if "run" in step:
                assert isinstance(step_name, str) and step_name, (
                    f"{job_id}:step-{index} run contract must have a stable name"
                )
                assert "shell" not in step and "working-directory" not in step, (
                    f"{job_id}:{step_name} must keep default shell and working directory"
                )
                actual_runs.append((step_name, _normalize_run_payload(step["run"])))
                continue

            uses = step["uses"]
            assert isinstance(uses, str) and _PINNED_ACTION.fullmatch(uses), (
                f"{job_id}:step-{index} action must use one exact 40-hex commit"
            )
            inputs = step.get("with", {})
            assert isinstance(inputs, dict), f"{job_id}:step-{index} inputs must be a mapping"
            assert all(
                isinstance(key, str) and isinstance(value, str) for key, value in inputs.items()
            )
            actual_actions.append((uses, inputs))

        assert tuple(actual_runs) == _EXPECTED_RUN_STEPS[job_id], (
            f"{job_id} run-step contract changed: {actual_runs!r}"
        )
        assert tuple(actual_actions) == _EXPECTED_ACTION_STEPS[job_id], (
            f"{job_id} action/input contract changed: {actual_actions!r}"
        )

    assert seen_conditions == _ALLOWED_STEP_CONDITIONS, (
        f"conditional diagnostic-step allowlist changed: {seen_conditions!r}"
    )


def _required_step(workflow: dict[str, Any], job_id: str, step_name: str) -> dict[str, Any]:
    steps = workflow["jobs"][job_id]["steps"]
    assert isinstance(steps, list)
    matches: list[dict[str, Any]] = []
    for step in steps:
        assert isinstance(step, dict)
        if step.get("name") == step_name:
            matches.append(step)
    assert len(matches) == 1
    return matches[0]


def _checkout_only(workflow: dict[str, Any]) -> None:
    workflow["jobs"]["lint"]["steps"] = [workflow["jobs"]["lint"]["steps"][0]]


def _echo_validator(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "lint", "Lint (in container)")["run"] = (
        "echo 'bash scripts/run_ci_local.sh lint'"
    )


def _remove_validator(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["lint"]
    job["steps"] = [step for step in job["steps"] if step.get("name") != "Lint (in container)"]


def _move_validator(workflow: dict[str, Any]) -> None:
    source = workflow["jobs"]["lint"]["steps"]
    validator = _required_step(workflow, "lint", "Lint (in container)")
    source.remove(validator)
    workflow["jobs"]["unit-tests"]["steps"].append(validator)


def _early_success(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "lint", "Lint (in container)")["run"] = (
        "exit 0\nbash scripts/run_ci_local.sh lint"
    )


def _disable_errexit(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "lint", "Lint (in container)")["run"] = (
        "set +e\nbash scripts/run_ci_local.sh lint\necho pass"
    )


def _successful_fallback(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "lint", "Lint (in container)")["run"] = (
        "bash scripts/run_ci_local.sh lint || echo pass"
    )


def _job_condition(workflow: dict[str, Any]) -> None:
    workflow["jobs"]["lint"]["if"] = "github.event_name != 'merge_group'"


def _step_condition(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "lint", "Lint (in container)")["if"] = (
        "github.event_name != 'merge_group'"
    )


def _job_continue_on_error(workflow: dict[str, Any]) -> None:
    workflow["jobs"]["lint"]["continue-on-error"] = "true"


def _step_continue_on_error(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "lint", "Lint (in container)")["continue-on-error"] = "true"


def _dependency_suppression(workflow: dict[str, Any]) -> None:
    workflow["jobs"]["test"]["needs"] = ["unit-tests"]


def _dependency_result_bypass(workflow: dict[str, Any]) -> None:
    workflow["jobs"]["test"]["if"] = "always()"


def _matrix_strategy(workflow: dict[str, Any]) -> None:
    workflow["jobs"]["lint"]["strategy"] = {"matrix": {"python": ["3.13"]}}


def _dynamic_context(workflow: dict[str, Any]) -> None:
    workflow["jobs"]["lint"]["name"] = "lint (${{ matrix.python }})"


def _unpinned_action(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "package", "Download built distributions")["uses"] = (
        "actions/download-artifact@v8"
    )


def _unsafe_action_input(workflow: dict[str, Any]) -> None:
    _required_step(workflow, "package", "Download built distributions")["with"]["name"] = (
        "other-package"
    )


def test_required_producer_has_pull_request_and_merge_group_parity() -> None:
    """Every live required context must be reachable on PR and merge-group SHAs."""
    workflow = _load_workflow(_REQUIRED_WORKFLOW)

    assert workflow["on"] == {
        "pull_request": "",
        "push": {"branches": ["main"]},
        "merge_group": {"types": ["checks_requested"]},
    }
    assert workflow["permissions"] == {"contents": "read"}

    contexts_by_event: dict[str, set[str]] = {}
    for event_name in ("pull_request", "merge_group"):
        contexts: set[str] = set()
        for job_id, expected_context in _REQUIRED_JOBS.items():
            job = workflow["jobs"][job_id]
            assert "if" not in job, (
                f"{job_id} has an event/job condition that can suppress {expected_context!r}"
            )
            contexts.add(_job_context(job_id, job, workflow_name=_REQUIRED_WORKFLOW.name))
        contexts_by_event[event_name] = contexts

    assert contexts_by_event == {
        "pull_request": set(_REQUIRED_CONTEXTS),
        "merge_group": set(_REQUIRED_CONTEXTS),
    }


def test_required_jobs_execute_exact_validator_contracts() -> None:
    """Every protected context must remain backed by its real validation."""
    _assert_required_job_contracts(_load_workflow(_REQUIRED_WORKFLOW))


@pytest.mark.parametrize(
    "mutate",
    [
        _checkout_only,
        _echo_validator,
        _remove_validator,
        _move_validator,
        _early_success,
        _disable_errexit,
        _successful_fallback,
        _job_condition,
        _step_condition,
        _job_continue_on_error,
        _step_continue_on_error,
        _dependency_suppression,
        _dependency_result_bypass,
        _matrix_strategy,
        _dynamic_context,
        _unpinned_action,
        _unsafe_action_input,
    ],
    ids=[
        "checkout-only",
        "echo-validator",
        "removed-validator",
        "moved-validator",
        "early-exit-success",
        "set-plus-e",
        "successful-or-fallback",
        "job-if",
        "step-if",
        "job-continue-on-error",
        "step-continue-on-error",
        "dependency-suppression",
        "dependency-result-bypass",
        "matrix-strategy",
        "dynamic-context",
        "unpinned-action",
        "unsafe-action-input",
    ],
)
def test_required_contract_oracle_rejects_false_green_mutations(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """The oracle must fail for suppressed, hollow, or replaced validators."""
    workflow = deepcopy(_load_workflow(_REQUIRED_WORKFLOW))
    mutate(workflow)

    with pytest.raises(AssertionError):
        _assert_required_job_contracts(workflow)


def test_live_required_contexts_have_one_owner_across_all_workflow_suffixes() -> None:
    """No .yml or .yaml workflow may duplicate a ruleset-required context."""
    owners_by_event: dict[str, dict[str, list[tuple[str, str]]]] = {
        event_name: {context: [] for context in _REQUIRED_CONTEXTS}
        for event_name in ("pull_request", "merge_group")
    }

    for path in _workflow_paths():
        workflow = _load_workflow(path)
        for event_name, owners in owners_by_event.items():
            if event_name not in workflow["on"]:
                continue
            for job_id, job in workflow["jobs"].items():
                context = _job_context(job_id, job, workflow_name=path.name)
                if context in owners:
                    owners[context].append((path.name, job_id))

    expected_owners = {
        context: [("_required.yml", job_id)] for job_id, context in _REQUIRED_JOBS.items()
    }
    assert owners_by_event == {
        "pull_request": expected_owners,
        "merge_group": expected_owners,
    }


def test_required_concurrency_is_event_scoped_and_fork_safe() -> None:
    """Fork PRs and synthetic queue runs must not cancel unrelated validations."""
    workflow = _load_workflow(_REQUIRED_WORKFLOW)
    assert workflow["concurrency"] == {
        "group": _CONCURRENCY_GROUP,
        "cancel-in-progress": "true",
    }

    fork_a = _concurrency_key(
        workflow="Required Checks",
        event_name="pull_request",
        pull_request_number=2100,
        sha="shared-fork-head-sha",
    )
    fork_b = _concurrency_key(
        workflow="Required Checks",
        event_name="pull_request",
        pull_request_number=2101,
        sha="shared-fork-head-sha",
    )
    refreshed_fork_a = _concurrency_key(
        workflow="Required Checks",
        event_name="pull_request",
        pull_request_number=2100,
        sha="new-head-sha",
    )
    merge_group = _concurrency_key(
        workflow="Required Checks",
        event_name="merge_group",
        pull_request_number=None,
        sha="shared-fork-head-sha",
    )

    assert fork_a != fork_b
    assert fork_a == refreshed_fork_a
    assert merge_group not in {fork_a, fork_b}


def test_smoke_only_merge_queue_carrier_is_absent() -> None:
    """A smoke-only check must not stand in for the live required contexts."""
    assert not (_WORKFLOWS / "merge-queue-smoke.yml").exists()
    assert not (_WORKFLOWS / "merge-queue-smoke.yaml").exists()

    for path in _workflow_paths():
        workflow = _load_workflow(path)
        assert "merge-queue-smoke" not in workflow["jobs"]
        assert all(
            _job_context(job_id, job, workflow_name=path.name) != "merge-queue-smoke"
            for job_id, job in workflow["jobs"].items()
        )


def test_write_capable_workflows_never_run_for_merge_groups() -> None:
    """Merge-group validation must not widen image or release publish boundaries."""
    for path in _workflow_paths():
        workflow = _load_workflow(path)
        writes = _has_write_permission(workflow.get("permissions"), owner=path.name)
        writes = writes or any(
            _has_write_permission(job.get("permissions"), owner=f"{path.name}:{job_id}")
            for job_id, job in workflow["jobs"].items()
        )
        if writes:
            assert "merge_group" not in workflow["on"], (
                f"{path.name} can write repository state and must not run for merge groups"
            )


def test_ci_image_helper_changes_trigger_the_authoritative_image_scan() -> None:
    """Security-helper-only changes must run the CI image build and Trivy scan."""
    workflow = _load_workflow(_WORKFLOWS / "ci-image.yml")
    for event_name in ("push", "pull_request"):
        paths = workflow["on"][event_name]["paths"]
        assert paths.count(_CI_IMAGE_HELPER) == 1
