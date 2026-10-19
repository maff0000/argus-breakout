"""Structured JSON logging to stdout with secret redaction (PID 8.3)."""

import logging
import re
import sys
from collections.abc import Iterable
from typing import Any

import structlog
from pydantic import SecretStr

from argus.settings import Settings

_REDACTED = "***REDACTED***"
_PATTERN = re.compile(r"(?i)((?:api[_-]?key|token|secret)=)\S+")


def _configured_secrets() -> list[str]:
    try:
        settings = Settings()
    except Exception:
        return []
    values = []
    for name in type(settings).model_fields:
        value = getattr(settings, name)
        if isinstance(value, SecretStr) and value.get_secret_value():
            values.append(value.get_secret_value())
    return values


def make_redactor(secrets: Iterable[str] = ()) -> Any:
    secret_values = [s for s in secrets if s]

    def _redact_value(value: Any) -> Any:
        if isinstance(value, str):
            if value in secret_values:
                return _REDACTED
            return _PATTERN.sub(lambda m: m.group(1) + _REDACTED, value)
        return value

    def processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return {key: _redact_value(val) for key, val in event_dict.items()}

    return processor


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog: JSON lines on stdout, UTC ISO timestamps."""
    numeric = logging.getLevelName(level.upper())
    if not isinstance(numeric, int):
        numeric = logging.INFO
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            make_redactor(_configured_secrets()),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
