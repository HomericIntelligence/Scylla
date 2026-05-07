"""Unit tests for :mod:`scylla.utils.json_logging`."""

from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from scylla.utils.json_logging import (
    JsonFormatter,
    configure_json_logging,
    is_json_logging_enabled,
)


@pytest.fixture
def reset_root_logger() -> Iterator[None]:
    """Snapshot and restore root logger state around each test."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    # Detach existing handlers so configure_json_logging starts clean.
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


def _make_record(
    *,
    name: str = "scylla.test",
    level: int = logging.INFO,
    msg: str = "hello",
    extra: dict[str, Any] | None = None,
    exc_info: tuple[Any, ...] | None = None,
) -> logging.LogRecord:
    """Build a LogRecord for formatter testing."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=10,
        msg=msg,
        args=None,
        exc_info=exc_info,
    )
    if extra:
        for key, value in extra.items():
            setattr(record, key, value)
    return record


def test_formatter_emits_required_fields() -> None:
    """Formatter must emit timestamp/level/name/message in valid JSON."""
    formatter = JsonFormatter()
    record = _make_record(msg="hi there")

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["name"] == "scylla.test"
    assert payload["message"] == "hi there"
    assert "timestamp" in payload
    # Timestamp must be parseable and tz-aware.
    assert payload["timestamp"].endswith("+00:00")


def test_formatter_includes_extras() -> None:
    """Extras passed via record attributes must appear in the JSON payload."""
    formatter = JsonFormatter()
    record = _make_record(extra={"tier": "T2", "subtest_id": "abc-123"})

    payload = json.loads(formatter.format(record))

    assert payload["tier"] == "T2"
    assert payload["subtest_id"] == "abc-123"


def test_formatter_includes_traceback_on_exception() -> None:
    """When exc_info is set, formatted output must include a traceback field."""
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record(level=logging.ERROR, exc_info=sys.exc_info())

    payload = json.loads(formatter.format(record))

    assert "traceback" in payload
    assert "ValueError" in payload["traceback"]
    assert "boom" in payload["traceback"]


def test_configure_json_logging_is_idempotent(reset_root_logger: None) -> None:
    """Repeated configure calls must not stack handlers."""
    stream = io.StringIO()
    configure_json_logging(stream=stream)
    configure_json_logging(stream=stream)
    configure_json_logging(stream=stream)

    root = logging.getLogger()
    json_handlers = [
        h for h in root.handlers if getattr(h, "_scylla_json_logging_configured", False)
    ]
    assert len(json_handlers) == 1
    assert isinstance(json_handlers[0].formatter, JsonFormatter)


def test_configure_json_logging_emits_json(reset_root_logger: None) -> None:
    """End-to-end: configure then log produces a JSON line on the stream."""
    stream = io.StringIO()
    configure_json_logging(level="DEBUG", stream=stream)

    logger = logging.getLogger("scylla.cfg.test")
    logger.info("structured", extra={"run_id": "r1"})

    output = stream.getvalue().strip()
    assert output, "expected JSON line on stream"
    payload = json.loads(output.splitlines()[-1])
    assert payload["message"] == "structured"
    assert payload["run_id"] == "r1"
    assert payload["level"] == "INFO"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("nope", False),
    ],
)
def test_is_json_logging_enabled(
    value: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SCYLLA_JSON_LOGS env var must be parsed for common truthy/falsy spellings."""
    monkeypatch.setenv("SCYLLA_JSON_LOGS", value)
    assert is_json_logging_enabled() is expected


def test_is_json_logging_enabled_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SCYLLA_JSON_LOGS is unset, JSON logging must be disabled."""
    monkeypatch.delenv("SCYLLA_JSON_LOGS", raising=False)
    assert is_json_logging_enabled() is False
