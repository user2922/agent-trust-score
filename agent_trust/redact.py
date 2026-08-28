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


# Every Evidence snippet in the product is built here. models.Evidence rejects a
# snippet longer than this or containing a control character, so a caller that
# bypasses this function fails loudly rather than shipping a secret.
MAX_SNIPPET = 200

_CONTEXT = 60


def snippet(line: str, match_start: int, match_end: int) -> str:
    """Return one line of evidence with the matched span redacted.

    ``line`` is raw repository content. The matched span is replaced with its
    redacted form, the surrounding text is trimmed to keep the result within
    ``MAX_SNIPPET`` characters, and control characters are removed.

    Args:
        line: the full source line the match was found on.
        match_start: index of the first character of the match.
        match_end: index one past the last character of the match.
    """
    if match_start < 0 or match_end > len(line) or match_start > match_end:
        raise ValueError("match span is outside the line")

    masked = redact(line[match_start:match_end])
    before = strip_control(line[:match_start])
    after = strip_control(line[match_end:])

    # Keep the match visible: trim the context around it, not the match itself.
    if len(before) > _CONTEXT:
        before = "…" + before[-_CONTEXT:]
    if len(after) > _CONTEXT:
        after = after[:_CONTEXT] + "…"

    out = f"{before}{masked}{after}".strip()
    if len(out) > MAX_SNIPPET:
        out = out[: MAX_SNIPPET - 1] + "…"
    return out
