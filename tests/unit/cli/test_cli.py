"""Tests for unified CLI commands."""

from click.testing import CliRunner

from scylla.cli.main import cli


class TestCliGroup:
    """Tests for the top-level CLI group."""

    def test_help(self) -> None:
        """--help prints usage text and exits 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Scylla" in result.output

    def test_version(self) -> None:
        """--version prints version and exits 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "scylla" in result.output


class TestStatusCommand:
    """Tests for the status subcommand."""

    def test_status_no_results(self) -> None:
        """Status with no results shows helpful message."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["status", "nonexistent-test"])
        assert result.exit_code == 0
        assert "No results found" in result.output

    def test_status_requires_test_id(self) -> None:
        """Status without test_id shows usage error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        assert result.exit_code != 0


class TestListTiersCommand:
    """Tests for the list-tiers subcommand."""

    def test_list_tiers(self) -> None:
        """list-tiers shows tier information."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list-tiers"])
        assert result.exit_code == 0
        assert "T0" in result.output
        assert "T6" in result.output


class TestListCommand:
    """Tests for the list subcommand."""

    def test_list_no_tests_dir(self) -> None:
        """List with no tests directory shows fallback list."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "Available tests" in result.output


class TestRunCommand:
    """Tests for the run subcommand."""

    def test_run_verbose_and_quiet_conflict(self) -> None:
        """--verbose and --quiet together produce a usage error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "test-001", "--verbose", "--quiet"])
        assert result.exit_code != 0
        assert "Cannot use --verbose and --quiet together" in result.output
