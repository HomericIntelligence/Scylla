"""Unit tests for scylla/e2e/log_context.py.

Tests cover:
- set_log_context + ContextFilter injects fields into log records
- Default empty strings when no context is set
- Thread-local isolation (context set in one thread is not visible in another)
- End-to-end integration with configure_json_logging
"""

from __future__ import annotations

import io
import json
import logging
import threading
from collections.abc import Iterator

import pytest

from scylla.e2e.log_context import ContextFilter, clear_log_context, set_log_context
from scylla.utils.json_logging import configure_json_logging


class TestContextFilterDefaults:
    """Tests that ContextFilter produces correct defaults when no context is set."""

    def test_default_empty_strings_when_no_context_set(self) -> None:
        """ContextFilter injects empty strings when set_log_context has not been called."""
        # Ensure context is cleared on this thread
        clear_log_context()

        filt = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )

        result = filt.filter(record)

        assert result is True
        assert record.tier_id == ""  # type: ignore[attr-defined]
        assert record.subtest_id == ""  # type: ignore[attr-defined]
        assert record.run_num == ""  # type: ignore[attr-defined]


class TestSetLogContextInjection:
    """Tests that set_log_context + ContextFilter injects fields into log records."""

    def test_injects_tier_id_and_subtest_id(self) -> None:
        """set_log_context values appear on the log record after filtering."""
        set_log_context(tier_id="T3", subtest_id="05", run_num=2)

        filt = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )

        filt.filter(record)

        assert record.tier_id == "T3"  # type: ignore[attr-defined]
        assert record.subtest_id == "05"  # type: ignore[attr-defined]
        assert record.run_num == "2"  # type: ignore[attr-defined]

        # Clean up
        clear_log_context()

    def test_run_num_none_becomes_empty_string(self) -> None:
        """When run_num is None, ContextFilter sets record.run_num to empty string."""
        set_log_context(tier_id="T0", subtest_id="00", run_num=None)

        filt = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )

        filt.filter(record)

        assert record.run_num == ""  # type: ignore[attr-defined]

        # Clean up
        clear_log_context()


class TestThreadLocalIsolation:
    """Tests that log context is thread-local (set in thread A, not visible in thread B)."""

    def test_context_not_visible_across_threads(self) -> None:
        """Context set in thread A is not visible in thread B."""
        # Set context in main thread
        set_log_context(tier_id="T5", subtest_id="10", run_num=3)

        observed: dict[str, str] = {}
        error_holder: list[Exception] = []

        def worker() -> None:
            """Read log context fields in a separate thread."""
            try:
                filt = ContextFilter()
                record = logging.LogRecord(
                    name="test",
                    level=logging.INFO,
                    pathname="",
                    lineno=0,
                    msg="worker",
                    args=(),
                    exc_info=None,
                )
                filt.filter(record)
                observed["tier_id"] = record.tier_id  # type: ignore[attr-defined]
                observed["subtest_id"] = record.subtest_id  # type: ignore[attr-defined]
                observed["run_num"] = record.run_num  # type: ignore[attr-defined]
            except Exception as exc:
                error_holder.append(exc)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5.0)

        assert not error_holder, f"Worker thread raised: {error_holder[0]}"

        # Thread B should see empty defaults, NOT thread A's values
        assert observed["tier_id"] == "", (
            f"Expected empty tier_id in thread B, got {observed['tier_id']!r}"
        )
        assert observed["subtest_id"] == "", (
            f"Expected empty subtest_id in thread B, got {observed['subtest_id']!r}"
        )
        assert observed["run_num"] == "", (
            f"Expected empty run_num in thread B, got {observed['run_num']!r}"
        )

        # Clean up main thread
        clear_log_context()


class TestHandlerFormatterIntegration:
    """Tests that ContextFilter works through the full handler+formatter pipeline.

    Catches the KeyError regression where %(tier_id)s in a format string
    fails if the filter is added to the logger instead of the handler.
    Uses handler.handle() which mirrors the real logging pipeline:
    handle() → filter() → emit() → format().
    """

    def test_format_with_context_fields_does_not_raise(self) -> None:
        """Handler with ContextFilter formats %(tier_id)s without KeyError."""
        clear_log_context()

        # Build a handler+formatter that uses the context placeholders
        handler = logging.StreamHandler()
        handler.addFilter(ContextFilter())
        captured: list[str] = []

        class _CapturingFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                result = super().format(record)
                captured.append(result)
                return result

        handler.setFormatter(
            _CapturingFormatter("[%(tier_id)s/%(subtest_id)s/%(run_num)s] %(message)s")
        )

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="pipeline test",
            args=(),
            exc_info=None,
        )

        # handle() runs filter() before emit()/format() — the real pipeline
        handler.handle(record)

        assert len(captured) == 1
        assert "[//]" in captured[0]  # defaults: empty/empty/empty
        assert "pipeline test" in captured[0]

    def test_format_with_set_context(self) -> None:
        """Handler with ContextFilter formats set context values correctly."""
        set_log_context(tier_id="T2", subtest_id="03", run_num=1)

        handler = logging.StreamHandler()
        handler.addFilter(ContextFilter())
        captured: list[str] = []

        class _CapturingFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                result = super().format(record)
                captured.append(result)
                return result

        handler.setFormatter(
            _CapturingFormatter("[%(tier_id)s/%(subtest_id)s/%(run_num)s] %(message)s")
        )

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="context test",
            args=(),
            exc_info=None,
        )

        handler.handle(record)

        assert len(captured) == 1
        assert "[T2/03/1]" in captured[0]
        assert "context test" in captured[0]

        clear_log_context()


@pytest.fixture
def reset_root_logger() -> Iterator[None]:
    """Snapshot and restore root logger state around the JSON integration test."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    for handler in original_handlers:
        root.removeHandler(handler)
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


class TestJsonLoggingIntegration:
    """End-to-end: configure_json_logging + set_log_context surface in JSON."""

    def test_context_fields_appear_in_json_output(self, reset_root_logger: None) -> None:
        """All three context fields must appear in the JSON log line."""
        stream = io.StringIO()
        configure_json_logging(stream=stream)
        set_log_context(tier_id="T4", subtest_id="07", run_num=3)
        try:
            logging.getLogger("scylla.integration").info("e2e ctx")
        finally:
            clear_log_context()

        payload = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert payload["tier_id"] == "T4"
        assert payload["subtest_id"] == "07"
        assert payload["run_num"] == "3"
        assert payload["message"] == "e2e ctx"
