from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Callable

import pytest
from pydantic import ValidationError

import std.logging as std_logging
from std.logging import LoggingConfig, LoggingEnvironment, configure_logging


def _capture_configuration(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: io.StringIO | None = None,
    stderr: io.StringIO | None = None,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def basic_config(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(std_logging.logging, "basicConfig", basic_config)
    monkeypatch.setattr(std_logging, "_configured_logger_names", set())
    if stdout is not None:
        monkeypatch.setattr(std_logging.sys, "stdout", stdout)
    if stderr is not None:
        monkeypatch.setattr(std_logging.sys, "stderr", stderr)
    return captured


def _captured_handler(captured: dict[str, object]) -> logging.Handler:
    handlers = captured["handlers"]
    assert isinstance(handlers, list)
    assert len(handlers) == 1
    handler = handlers[0]
    assert isinstance(handler, logging.Handler)
    return handler


@pytest.mark.parametrize(
    ("environment", "expected_level", "expected_format"),
    [
        ("development", "DEBUG", "console"),
        ("test", "WARNING", "console"),
        ("staging", "INFO", "json"),
        ("production", "INFO", "json"),
        ("dev", "DEBUG", "console"),
        ("stage", "INFO", "json"),
        ("prod", "INFO", "json"),
    ],
)
def test_environment_selects_default_level_and_format(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    expected_level: str,
    expected_format: str,
) -> None:
    output = io.StringIO()
    captured = _capture_configuration(monkeypatch, stdout=output)

    configure_logging(environment=environment)

    assert captured["level"] == expected_level
    handler = _captured_handler(captured)
    rendered = handler.format(
        logging.LogRecord("example.module", logging.INFO, __file__, 12, "ready", (), None)
    )
    if expected_format == "json":
        assert json.loads(rendered)["message"] == "ready"
    else:
        assert "INFO" in rendered
        assert "example.module" in rendered
        assert "ready" in rendered


def test_json_output_has_service_environment_context_and_exception_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    captured = _capture_configuration(monkeypatch, stdout=output)
    configure_logging(
        {"format": "json", "include_source": True},
        environment="production",
        service_name="billing-api",
    )
    handler = _captured_handler(captured)

    try:
        raise ValueError("invalid invoice")
    except ValueError:
        record = logging.LogRecord(
            "billing.invoice",
            logging.ERROR,
            __file__,
            48,
            "invoice rejected: %s",
            (42,),
            sys.exc_info(),
            "create_invoice",
        )
    record.request_id = "req-123"

    payload = json.loads(handler.format(record))

    assert payload["timestamp"].endswith("Z")
    assert payload["level"] == "ERROR"
    assert payload["logger"] == "billing.invoice"
    assert payload["message"] == "invoice rejected: 42"
    assert payload["environment"] == "production"
    assert payload["service"] == "billing-api"
    assert payload["source"]["function"] == "create_invoice"
    assert payload["exception.type"] == "ValueError"
    assert payload["exception.message"] == "invalid invoice"
    assert "ValueError: invalid invoice" in payload["exception.stacktrace"]
    assert payload["request_id"] == "req-123"


@pytest.mark.parametrize(
    ("settings", "expected_level", "expected_format"),
    [
        ({"level": "ERROR"}, "ERROR", "json"),
        ({"format": "console", "level": "WARNING"}, "WARNING", "console"),
    ],
)
def test_explicit_level_and_format_override_environment_defaults(
    monkeypatch: pytest.MonkeyPatch,
    settings: dict[str, str],
    expected_level: str,
    expected_format: str,
) -> None:
    output = io.StringIO()
    captured = _capture_configuration(monkeypatch, stdout=output)

    configure_logging(settings, environment="production")

    assert captured["level"] == expected_level
    handler = _captured_handler(captured)
    rendered = handler.format(logging.LogRecord("app", logging.INFO, __file__, 1, "ok", (), None))
    if expected_format == "json":
        assert json.loads(rendered)["message"] == "ok"
    else:
        assert "app" in rendered


def test_custom_format_supports_standard_formatter_styles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    captured = _capture_configuration(monkeypatch, stdout=output)
    configure_logging(
        LoggingConfig(
            format="custom",
            custom_format="{levelname} {name}: {message}",
            custom_style="{",
        ),
        environment="staging",
    )
    handler = _captured_handler(captured)
    record = logging.LogRecord("payments", logging.WARNING, __file__, 8, "slow", (), None)

    assert handler.format(record) == "WARNING payments: slow"


def test_stream_and_color_overrides_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    error = io.StringIO()
    captured = _capture_configuration(monkeypatch, stdout=output, stderr=error)

    configure_logging({"format": "console", "stream": "stderr", "color": "always"})

    handler = _captured_handler(captured)
    record = logging.LogRecord("app", logging.ERROR, __file__, 1, "failed", (), None)
    assert handler.stream is error
    assert "\x1b[31m" in handler.format(record)


def test_named_logger_level_is_configurable_and_removed_override_is_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    captured = _capture_configuration(monkeypatch, stdout=output)
    logger = logging.getLogger("std.logging.test.named")
    original_level = logger.level
    calls: list[int | str] = []
    original_set_level: Callable[[int | str], None] = logger.setLevel
    monkeypatch.setattr(logger, "setLevel", lambda level: calls.append(level))

    try:
        configure_logging({"logger_levels": {"std.logging.test.named": "ERROR"}})
        configure_logging()
    finally:
        original_set_level(original_level)

    assert calls == ["ERROR", logging.NOTSET]
    assert "level" in captured


def test_unknown_environment_and_invalid_custom_configuration_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_configuration(monkeypatch, stdout=io.StringIO())

    with pytest.raises(ValueError, match="unsupported logging environment"):
        configure_logging(environment="qa")
    with pytest.raises(ValidationError, match="custom_format is required"):
        LoggingConfig(format="custom")
    with pytest.raises(ValidationError, match="may only be set"):
        LoggingConfig(format="json", custom_format="%(message)s")


def test_environment_aliases_normalize_to_canonical_profiles() -> None:
    assert LoggingEnvironment("local") is LoggingEnvironment.DEVELOPMENT
    assert LoggingEnvironment("stage") is LoggingEnvironment.STAGING
