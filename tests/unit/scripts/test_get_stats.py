"""Tests for scripts/get_stats.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from get_stats import get_commits_stats, get_issues_stats, get_prs_stats


class TestGetIssuesStats:
    """Tests for get_issues_stats()."""

    def test_returns_counts_on_success(self) -> None:
        """Returns dict with total/open/closed when gh CLI succeeds."""
        mock_total = MagicMock()
        mock_total.returncode = 0
        mock_total.stdout = "10\n"

        mock_open = MagicMock()
        mock_open.returncode = 0
        mock_open.stdout = "3\n"

        with patch("get_stats.subprocess.run", side_effect=[mock_total, mock_open]):
            result = get_issues_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        assert result["total"] == 10
        assert result["open"] == 3
        assert result["closed"] == 7

    def test_returns_zeros_on_gh_failure(self) -> None:
        """Returns all-zero dict when gh CLI fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("get_stats.subprocess.run", return_value=mock_result):
            result = get_issues_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        assert result == {"total": 0, "open": 0, "closed": 0}

    def test_includes_author_filter_in_query(self) -> None:
        """Adds author filter to gh CLI query when author is specified."""
        mock_total = MagicMock()
        mock_total.returncode = 0
        mock_total.stdout = "5\n"

        mock_open = MagicMock()
        mock_open.returncode = 0
        mock_open.stdout = "2\n"

        with patch("get_stats.subprocess.run", side_effect=[mock_total, mock_open]) as mock_run:
            get_issues_stats("2026-01-01", "2026-01-31", "alice", "owner/repo")

        # Check that the query passed to gh includes author filter
        first_call_args = mock_run.call_args_list[0][0][0]
        query_arg = next((a for a in first_call_args if "author:alice" in str(a)), None)
        assert query_arg is not None


class TestGetPrsStats:
    """Tests for get_prs_stats()."""

    def test_returns_counts_on_success(self) -> None:
        """Returns dict with total/merged/open/closed when gh CLI succeeds.

        hephaestus 0.9.9 (#811) batches total/merged/open into a SINGLE
        ``gh api graphql`` call routed through ``gh_call`` (not three serial
        ``subprocess.run`` calls), and the ``--jq`` returns a JSON array
        ``[total, merged, open]`` that the function json-decodes. Mock that
        single ``gh_call`` (patched where it is looked up, in
        ``hephaestus.github.stats``) with an array-shaped stdout.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[20, 15, 3]\n"

        with patch(
            "hephaestus.github.stats.gh_call",
            return_value=mock_result,
        ):
            result = get_prs_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        assert result["total"] == 20
        assert result["merged"] == 15
        assert result["open"] == 3
        assert result["closed"] == 2

    def test_returns_zeros_on_gh_failure(self) -> None:
        """Returns all-zero dict when gh CLI fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("get_stats.subprocess.run", return_value=mock_result):
            result = get_prs_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        assert result == {"total": 0, "merged": 0, "open": 0, "closed": 0}

    def test_no_author_filter_by_default(self) -> None:
        """Does not add author filter when author is None."""
        mock_total = MagicMock()
        mock_total.returncode = 0
        mock_total.stdout = "0\n"

        mock_merged = MagicMock()
        mock_merged.returncode = 0
        mock_merged.stdout = "0\n"

        mock_open = MagicMock()
        mock_open.returncode = 0
        mock_open.stdout = "0\n"

        with patch(
            "get_stats.subprocess.run",
            side_effect=[mock_total, mock_merged, mock_open],
        ) as mock_run:
            get_prs_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        first_call_args = mock_run.call_args_list[0][0][0]
        assert not any("author:" in str(a) for a in first_call_args)


class TestGetCommitsStats:
    """Tests for get_commits_stats()."""

    def test_returns_total_on_success(self) -> None:
        """Returns dict with total commit count when gh CLI succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "42\n"

        with patch("get_stats.subprocess.run", return_value=mock_result):
            result = get_commits_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        assert result == {"total": 42}

    def test_returns_zero_on_gh_failure(self) -> None:
        """Returns all-zero dict when gh CLI fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("get_stats.subprocess.run", return_value=mock_result):
            result = get_commits_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        assert result == {"total": 0}

    def test_includes_author_param_when_specified(self) -> None:
        """Adds author filter parameter to gh CLI call when author is provided."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "5\n"

        with patch("get_stats.subprocess.run", return_value=mock_result) as mock_run:
            get_commits_stats("2026-01-01", "2026-01-31", "alice", "owner/repo")

        call_args = mock_run.call_args[0][0]
        assert any("author=alice" in str(a) for a in call_args)

    def test_no_author_param_when_none(self) -> None:
        """Does not add author parameter when author is None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0\n"

        with patch("get_stats.subprocess.run", return_value=mock_result) as mock_run:
            get_commits_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        call_args = mock_run.call_args[0][0]
        assert not any("author=" in str(a) for a in call_args)

    def test_sums_multiple_paginated_pages(self) -> None:
        """Sums counts across multiple paginated pages returned by gh CLI."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "30\n30\n10\n"

        with patch("get_stats.subprocess.run", return_value=mock_result):
            result = get_commits_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        assert result == {"total": 70}

    def test_uses_since_and_until_date_params(self) -> None:
        """Passes since and until timestamps derived from start/end dates."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1\n"

        with patch("get_stats.subprocess.run", return_value=mock_result) as mock_run:
            get_commits_stats("2026-01-01", "2026-01-31", None, "owner/repo")

        call_args = mock_run.call_args[0][0]
        assert any("2026-01-01T00:00:00Z" in str(a) for a in call_args)
        assert any("2026-01-31T23:59:59Z" in str(a) for a in call_args)

    def test_uses_correct_repo_owner_and_name(self) -> None:
        """Constructs the API path using the owner and repo name from the repo argument."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "3\n"

        with patch("get_stats.subprocess.run", return_value=mock_result) as mock_run:
            get_commits_stats("2026-01-01", "2026-01-31", None, "myorg/myrepo")

        call_args = mock_run.call_args[0][0]
        assert any("repos/myorg/myrepo/commits" in str(a) for a in call_args)
