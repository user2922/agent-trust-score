"""The only module permitted to touch a raw secret value.

Standing rule R (CLAUDE.md): a matched secret is truncated at the moment of
capture, before it enters any object. Nothing downstream may see the full value
-- not the report, the cache, the LLM prompt, stdout, the HTML page, or a log
line.

Prompt 2a defines ``redact`` because ``logging`` depends on it. Prompt 2b adds
``snippet``, which builds the redacted evidence lines analyzers attach to
findings.
"""

from __future__ import annotations

import re

# A value short enough that showing any of it would leak most of it.
_MIN_LENGTH_TO_SHOW_EDGES = 8

_ELLIPSIS = "…"
_MASKED = "[redacted]"

# ANSI escape sequences and control characters. A crafted repository must not be
# able to push escape codes into our terminal output or HTML.
#
# Order matters: the full escape sequence must be tried BEFORE the bare-control
# class, which also contains \x1b. Listed the other way round the engine strips
# the ESC alone and leaves "[31m" as visible text.
_CONTROL = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")


def redact(value: str) -> str:
    """Return ``value`` reduced to its first 4 and last 2 characters.

    Anything shorter than 8 characters is masked entirely: showing 4 of 6
    characters leaks most of the secret.

    >>> redact("sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV")
    'sk-a…UV'
    >>> redact("short")
    '[redacted]'
    """
    cleaned = strip_control(value)
    if len(cleaned) < _MIN_LENGTH_TO_SHOW_EDGES:
        return _MASKED
    return f"{cleaned[:4]}{_ELLIPSIS}{cleaned[-2:]}"


def strip_control(text: str) -> str:
    """Remove control characters and ANSI escapes from repository-sourced text."""
    return _CONTROL.sub("", text)
