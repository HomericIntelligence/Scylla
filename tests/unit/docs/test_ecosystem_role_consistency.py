"""Drift-detection tests for Scylla's ecosystem role description.

Ensures that documentation does not reintroduce stale claims about chaos
engineering, failure injection, or NATS/ProjectHermes integration that do
not match the actual implementation (ablation benchmarking framework).

See ADR: docs/dev/adr/ecosystem-role-reconciliation.md
See issue #1503 for context.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[3]

# Documentation files that describe Scylla's role
DOC_FILES = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "docs" / "design" / "architecture.md",
]

# Phrases that indicate stale chaos-engineering claims
FORBIDDEN_PHRASES = [
    r"chaos\s+(?:engineering|testing)",
    r"inject\s+failures",
    r"failure\s+injection",
    r"NATS\s+events?\s+from\s+ProjectHermes",
    r"resilience\s+testing",
]


@pytest.mark.parametrize(
    "doc_path",
    [p for p in DOC_FILES if p.exists()],
    ids=lambda p: str(p.relative_to(PROJECT_ROOT)),
)
@pytest.mark.parametrize(
    "pattern",
    FORBIDDEN_PHRASES,
    ids=[
        "chaos-engineering",
        "inject-failures",
        "failure-injection",
        "nats-hermes",
        "resilience-testing",
    ],
)
def test_no_stale_chaos_claims(doc_path: Path, pattern: str) -> None:
    """Documentation must not contain stale chaos/resilience testing claims."""
    content = doc_path.read_text()
    matches = re.findall(pattern, content, re.IGNORECASE)
    assert not matches, (
        f"{doc_path.relative_to(PROJECT_ROOT)} contains forbidden phrase "
        f"matching /{pattern}/: {matches}"
    )


@pytest.mark.parametrize(
    "doc_path",
    [p for p in DOC_FILES if p.exists()],
    ids=lambda p: str(p.relative_to(PROJECT_ROOT)),
)
def test_canonical_role_description_present(doc_path: Path) -> None:
    """Key docs must contain the canonical role description."""
    content = doc_path.read_text().lower()
    has_testing = "testing" in content and "measurement" in content
    has_ablation = "ablation" in content
    has_benchmarking = "benchmark" in content
    assert has_testing or has_ablation or has_benchmarking, (
        f"{doc_path.relative_to(PROJECT_ROOT)} does not contain any canonical "
        f"role keywords (testing+measurement, ablation, benchmark)"
    )
