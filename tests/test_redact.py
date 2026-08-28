"""Standing rule R: no caller can obtain a full secret through this module."""

from __future__ import annotations

import pytest

from agent_trust.redact import redact, strip_control

# Every fixture carries the marker EXAMPLE so the repo's own secret scanner
# suppresses it by VALUE. That is the same rule SPEC.md specifies for the
# product, and it is why tests/ stays inside the scan rather than excluded.
REAL_SHAPED = [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_EXAMPLE7890abcdefghijklmnopqrstuvwxyzAB",
    "sk_live_EXAMPLE1H8xYzAbCdEfGhIjKlMnOpQr",
    "sk-ant-EXAMPLE-ZYXWVUTSRQPONMLKJIHGFEDCBA0987654321",
    "xoxb-EXAMPLE789012-abcdefghijklmnop",
]


@pytest.mark.parametrize("secret", REAL_SHAPED)
def test_middle_never_survives(secret: str) -> None:
    out = redact(secret)
    assert out.startswith(secret[:4])
    assert out.endswith(secret[-2:])
    # Everything between the shown edges is gone.
    assert secret[4:-2] not in out
    assert len(out) == 7


@pytest.mark.parametrize("short", ["", "a", "abc", "1234567"])
def test_short_values_are_masked_entirely(short: str) -> None:
    # No edges are shown at all: 4 of 6 characters would leak most of the value.
    assert redact(short) == "[redacted]"


def test_ansi_escapes_cannot_reach_output() -> None:
    assert redact("\x1b[31mAKIAIOSFODNN7EXAMPLE\x1b[0m").startswith("AKIA")
    assert "\x1b" not in redact("\x1b[31mAKIAIOSFODNN7EXAMPLE\x1b[0m")


def test_strip_control_removes_control_characters() -> None:
    assert strip_control("a\x00b\x07c") == "abc"
    assert strip_control("keep\ttabs\nand\nnewlines") == "keep\ttabs\nand\nnewlines"
