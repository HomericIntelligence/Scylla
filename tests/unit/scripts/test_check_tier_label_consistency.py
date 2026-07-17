"""Tests for scripts/check_tier_label_consistency.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hephaestus.validation.tier_labels import (
    BAD_PATTERNS,
    TierLabelFinding,
    find_violations,
    format_json,
    format_report,
    scan_repository,
)


class TestFindViolations:
    """Tests for find_violations() — legacy API."""

    def test_returns_empty_for_clean_content(self) -> None:
        """Clean content with no bad patterns returns no violations."""
        content = "T2 Tooling\nT3 Delegation\nT4 Hierarchy\nT5 Hybrid\n"
        assert find_violations(content) == []

    @pytest.mark.parametrize(
        "bad_line, expected_pattern",
        [
            # Original set
            ("T3 Tooling tier", r"T3.*Tool"),
            ("T4 Delegation tier", r"T4.*Deleg"),
            ("T5 Hierarchy tier", r"T5.*Hier"),
            ("T2 Skills tier", r"T2.*Skill"),
            # Reverse/symmetric set
            ("T2 Delegation tier", r"T2.{0,10}Deleg"),
            ("T3 Hierarchy tier", r"T3.{0,10}Hier"),
            ("T4 Hybrid tier", r"T4.{0,10}Hybrid"),
            ("T1 Tooling tier", r"T1.{0,10}Tool"),
            ("T0 Skills tier", r"T0.{0,10}Skill"),
            ("T1 Prompts tier", r"T1.{0,10}Prompt"),
            ("T2 Prompts tier", r"T2.{0,10}Prompt"),
            ("T3 Skills tier", r"T3.{0,10}Skill"),
            ("T4 Tooling tier", r"T4.{0,10}Tool"),
            ("T5 Delegation tier", r"T5.{0,10}Deleg"),
            ("T6 Hierarchy tier", r"T6.{0,10}Hier"),
            ("T6 Hybrid tier", r"T6.{0,10}Hybrid"),
            ("T0 Tooling tier", r"T0.{0,10}Tool"),
            ("T0 Delegation tier", r"T0.{0,10}Deleg"),
            ("T5 Skills tier", r"T5.{0,10}Skill"),
            ("T6 Delegation tier", r"T6.{0,10}Deleg"),
        ],
    )
    def test_detects_each_bad_pattern(self, bad_line: str, expected_pattern: str) -> None:
        """Each known-bad pattern is detected."""
        violations = find_violations(bad_line)
        assert len(violations) == 1
        lineno, line, pattern, reason = violations[0]
        assert lineno == 1
        assert line == bad_line
        assert pattern == expected_pattern
        assert reason  # non-empty reason string

    def test_returns_line_number(self) -> None:
        """Violation includes the correct 1-based line number."""
        content = "clean line\nT3 Tooling bad\nclean line"
        violations = find_violations(content)
        assert len(violations) == 1
        assert violations[0][0] == 2

    def test_multiple_violations_on_different_lines(self) -> None:
        """Multiple bad lines produce multiple violations."""
        content = "T3 Tooling\nT4 Delegation\n"
        violations = find_violations(content)
        assert len(violations) == 2

    def test_single_line_matching_multiple_patterns(self) -> None:
        """A line matching multiple patterns produces one violation per pattern."""
        content = "T3 Tooling T4 Delegation"
        violations = find_violations(content)
        assert len(violations) == 2

    def test_empty_content_returns_no_violations(self) -> None:
        """Empty string produces no violations."""
        assert find_violations("") == []

    def test_correct_tier_names_not_flagged(self) -> None:
        """Correct tier names adjacent to tier numbers are not flagged."""
        content = (
            "T0 Prompts\nT1 Skills\nT2 Tooling\nT3 Delegation\nT4 Hierarchy\nT5 Hybrid\nT6 Super\n"
        )
        assert find_violations(content) == []

    def test_violation_tuple_has_four_elements(self) -> None:
        """Each violation tuple contains (lineno, line, pattern, reason)."""
        violations = find_violations("T3 Tooling")
        assert len(violations) == 1
        assert len(violations[0]) == 4


class TestBadPatterns:
    """Tests for the BAD_PATTERNS constant."""

    def test_bad_patterns_is_non_empty(self) -> None:
        """BAD_PATTERNS must contain at least one entry."""
        assert len(BAD_PATTERNS) > 0

    def test_bad_patterns_entries_are_tuples_of_two_strings(self) -> None:
        """Each entry in BAD_PATTERNS is a (pattern, reason) tuple of strings."""
        for pattern, reason in BAD_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(reason, str)
            assert pattern
            assert reason


class TestScanRepository:
    """Tests for scan_repository() — whole-repo scan API."""

    def test_clean_repo_returns_empty(self, tmp_path: Path) -> None:
        """A repository with no mismatch returns empty list."""
        (tmp_path / "docs.md").write_text("T3/Delegation\nT2/Tooling\n", encoding="utf-8")
        result = scan_repository(tmp_path)
        assert result == []

    def test_detects_mismatches_across_files(self, tmp_path: Path) -> None:
        """Mismatches in multiple files are all collected."""
        (tmp_path / "a.md").write_text("T3/Tooling bad\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("T4/Delegation bad\n", encoding="utf-8")
        result = scan_repository(tmp_path)
        assert len(result) == 2

    def test_excludes_default_dirs(self, tmp_path: Path) -> None:
        """Files under excluded directories are skipped."""
        build = tmp_path / "build"
        build.mkdir()
        (build / "report.md").write_text("T3/Tooling bad\n", encoding="utf-8")
        result = scan_repository(tmp_path)
        assert result == []

    def test_excludes_pixi_dir(self, tmp_path: Path) -> None:
        """Files under .pixi/ are excluded from scanning."""
        pixi = tmp_path / ".pixi"
        pixi.mkdir()
        (pixi / "readme.md").write_text("T5/Hierarchy bad\n", encoding="utf-8")
        result = scan_repository(tmp_path)
        assert result == []

    def test_custom_excludes(self, tmp_path: Path) -> None:
        """Custom exclude directory names are respected."""
        custom = tmp_path / "mydir"
        custom.mkdir()
        (custom / "doc.md").write_text("T3/Tooling bad\n", encoding="utf-8")
        # Without exclusion: detected
        assert len(scan_repository(tmp_path, excludes=set())) > 0
        # With exclusion: skipped
        assert scan_repository(tmp_path, excludes={"mydir"}) == []

    def test_relative_file_paths_in_findings(self, tmp_path: Path) -> None:
        """Finding.file is relative to repo_root."""
        (tmp_path / "readme.md").write_text("T2/Skills bad\n", encoding="utf-8")
        result = scan_repository(tmp_path)
        assert len(result) == 1
        assert not result[0].file.startswith(str(tmp_path))
        assert "readme.md" in result[0].file

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        """Empty repository directory returns empty list."""
        assert scan_repository(tmp_path) == []

    def test_custom_glob_pattern(self, tmp_path: Path) -> None:
        """Custom glob restricts which files are scanned."""
        (tmp_path / "readme.md").write_text("T3/Tooling bad\n", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("T3/Tooling bad\n", encoding="utf-8")
        # Only *.md files are matched by default.
        result = scan_repository(tmp_path, glob="**/*.md")
        assert len(result) == 1
        assert "readme.md" in result[0].file

    def test_nested_subdirectory_scanned(self, tmp_path: Path) -> None:
        """Files in subdirectories are discovered by **/*.md glob."""
        sub = tmp_path / "docs" / "api"
        sub.mkdir(parents=True)
        (sub / "guide.md").write_text("T4/Delegation bad\n", encoding="utf-8")
        result = scan_repository(tmp_path)
        assert len(result) == 1
        assert "guide.md" in result[0].file


class TestFormatReport:
    """Tests for format_report()."""

    def test_empty_findings_returns_clean_message(self) -> None:
        """Empty findings list returns the all-clear message."""
        msg = format_report([])
        assert "No tier label mismatches found" in msg

    def test_findings_included_in_report(self, tmp_path: Path) -> None:
        """Non-empty findings produce a report with mismatch details."""
        finding = TierLabelFinding(
            file="docs/README.md",
            line=5,
            tier="T3",
            found_name="Tooling",
            expected_name="Delegation",
            raw_text="T3/Tooling is used here",
        )
        report = format_report([finding])
        assert "T3" in report
        assert "Tooling" in report
        assert "Delegation" in report

    def test_finding_count_in_report(self) -> None:
        """Report header includes the total mismatch count."""
        findings = [
            TierLabelFinding(
                file="a.md",
                line=i,
                tier="T3",
                found_name="Tooling",
                expected_name="Delegation",
                raw_text="T3/Tooling",
            )
            for i in range(3)
        ]
        report = format_report(findings)
        assert "3" in report


class TestFormatJson:
    """Tests for format_json()."""

    def test_empty_findings_returns_empty_array(self) -> None:
        """Empty findings list serialises to a JSON empty array."""
        result = json.loads(format_json([]))
        assert result == []

    def test_findings_serialised_correctly(self) -> None:
        """Finding fields appear in the JSON output."""
        finding = TierLabelFinding(
            file="docs/README.md",
            line=10,
            tier="T4",
            found_name="Delegation",
            expected_name="Hierarchy",
            raw_text="T4/Delegation is wrong",
        )
        result = json.loads(format_json([finding]))
        assert len(result) == 1
        obj = result[0]
        assert obj["file"] == "docs/README.md"
        assert obj["line"] == 10
        assert obj["tier"] == "T4"
        assert obj["found_name"] == "Delegation"
        assert obj["expected_name"] == "Hierarchy"
        assert obj["raw_text"] == "T4/Delegation is wrong"
