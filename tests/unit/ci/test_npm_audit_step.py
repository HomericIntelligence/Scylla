"""Regression tests for the npm audit CI step in docker-test.yml.

Verifies that the Docker validation workflow contains a non-blocking npm audit
step that checks for high/critical vulnerabilities and reports via annotations.
Issue: #1592
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_TEST_WORKFLOW = _PROJECT_ROOT / ".github" / "workflows" / "docker-test.yml"


def test_npm_audit_step_exists() -> None:
    """docker-test.yml must contain an npm audit step."""
    content = _DOCKER_TEST_WORKFLOW.read_text()
    assert "npm audit" in content, "docker-test.yml is missing the npm audit step (issue #1592)"


def test_npm_audit_uses_high_level() -> None:
    """Npm audit step must use --audit-level=high."""
    content = _DOCKER_TEST_WORKFLOW.read_text()
    assert "--audit-level=high" in content, (
        "npm audit step must use --audit-level=high to filter noise"
    )


def test_npm_audit_is_non_blocking() -> None:
    """Npm audit step must be non-blocking — the step never fails the workflow.

    Historically this was achieved with ``continue-on-error: true`` on the
    step itself. That approach silently swallowed *any* failure in the step
    (not just an npm-audit non-zero exit), so it was replaced by capturing
    the audit command's exit code in-script:

        AUDIT_OUTPUT=$(docker run ... npm audit ...) || AUDIT_EXIT=$?
        AUDIT_EXIT=${AUDIT_EXIT:-0}

    Either mechanism keeps PRs unblocked, so accept whichever is present.
    """
    content = _DOCKER_TEST_WORKFLOW.read_text()
    lines = content.splitlines()

    in_audit_step = False
    step_body: list[str] = []
    for line in lines:
        if "npm audit" in line and "name:" in line.lower():
            in_audit_step = True
            continue
        if in_audit_step and line.strip().startswith("- name:"):
            break
        if in_audit_step:
            step_body.append(line)

    body = "\n".join(step_body)

    has_continue_on_error = "continue-on-error: true" in body
    # In-script capture pattern: "|| AUDIT_EXIT=$?" followed by a default
    # assignment that swallows the exit code so the step itself succeeds.
    has_inline_capture = "|| AUDIT_EXIT=$?" in body and "AUDIT_EXIT:-0" in body

    assert has_continue_on_error or has_inline_capture, (
        "npm audit step must be non-blocking: either set "
        "'continue-on-error: true' on the step or capture the audit exit "
        "code in-script (|| AUDIT_EXIT=$? + AUDIT_EXIT=${AUDIT_EXIT:-0}) "
        "so the step itself never fails."
    )


def test_npm_audit_emits_warning_annotation() -> None:
    """Npm audit step must emit a ::warning:: annotation on findings."""
    content = _DOCKER_TEST_WORKFLOW.read_text()
    assert "::warning" in content and "npm audit" in content, (
        "npm audit step must emit ::warning:: annotations for visibility"
    )
