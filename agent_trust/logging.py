"""Structured logging.

One JSON object per line, to **stderr only**. stdout carries report data and the
MCP stdio protocol framing; a stray log line there corrupts both.

Every message passes through :mod:`agent_trust.redact` so no log line can carry
raw repository content or a secret (standing rule R).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from agent_trust.redact import strip_control

_LOGGER_NAME = "agent_trust"
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render a record as one line of JSON with sorted keys."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": strip_control(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = strip_control(value) if isinstance(value, str) else value
        if record.exc_info:
            # The class name only. A traceback is detail for the developer, and
            # this stream is user-visible.
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "unknown"
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def configure(level: int = logging.INFO) -> logging.Logger:
    """Attach a single stderr handler to the package logger and return it."""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


def get_logger(suffix: str | None = None) -> logging.Logger:
    """Return the package logger, or a named child of it."""
    configure()
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}" if suffix else _LOGGER_NAME)
