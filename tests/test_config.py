"""Configuration loads, validates, and fails legibly."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from agent_trust import __version__
from agent_trust.config import DEFAULT_MODEL, Settings, get_settings
from agent_trust.errors import ConfigError
from agent_trust.logging import JsonFormatter, get_logger


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_settings.cache_clear()


def test_boots_with_empty_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "AGENT_TRUST_MAX_FILES", "AGENT_TRUST_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    assert settings.max_files == 20_000
    assert settings.llm_model == DEFAULT_MODEL
    assert settings.llm_available is False


def test_api_key_present_enables_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    assert get_settings().llm_available is True


def test_malformed_integer_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TRUST_MAX_FILES", "abc")
    with pytest.raises(ConfigError) as excinfo:
        get_settings()
    assert "AGENT_TRUST_MAX_FILES" in str(excinfo.value)
    assert "Traceback" not in str(excinfo.value)


def test_zero_budget_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TRUST_MAX_BYTES", "0")
    with pytest.raises(ConfigError):
        get_settings()


def test_settings_are_frozen() -> None:
    settings = Settings()
    with pytest.raises(Exception):  # noqa: B017 - pydantic raises ValidationError
        settings.max_files = 5  # type: ignore[misc]


def test_config_is_the_only_environment_reader() -> None:
    root = Path(__file__).resolve().parent.parent / "agent_trust"
    offenders = [
        path.name
        for path in root.rglob("*.py")
        if path.name != "config.py" and ("os.environ" in path.read_text(encoding="utf-8")
                                         or "getenv" in path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_log_lines_are_json_on_stderr() -> None:
    record = logging.LogRecord("agent_trust", logging.INFO, __file__, 1, "hello", None, None)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello"
    assert payload["level"] == "info"


def test_log_strips_ansi_escapes() -> None:
    record = logging.LogRecord(
        "agent_trust", logging.INFO, __file__, 1, "\x1b[31mred\x1b[0m", None, None
    )
    assert json.loads(JsonFormatter().format(record))["message"] == "red"


def test_logger_writes_to_stderr_not_stdout() -> None:
    code = (
        "from agent_trust.logging import get_logger;"
        "get_logger().info('marker-line');"
        "print('stdout-line')"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert "marker-line" in result.stderr
    assert "marker-line" not in result.stdout
    assert "stdout-line" in result.stdout


def test_version_is_a_single_source() -> None:
    assert __version__.count(".") == 2
    get_logger("test").debug("version %s", __version__)
