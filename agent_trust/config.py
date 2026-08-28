"""Configuration -- the only module in this project that reads the environment.

Standing rule 2 (CLAUDE.md): every value is validated at startup, a malformed
value fails immediately with a message naming the variable, and nothing else
anywhere reads ``os.environ``.

A missing ``ANTHROPIC_API_KEY`` is not an error. It sets ``llm_available`` to
False, and the tool behaves as if ``--no-llm`` were passed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_trust.errors import ConfigError

DEFAULT_MODEL = "claude-opus-5"

# Anthropic list price for the default model, USD per million tokens.
INPUT_COST_PER_MTOK = 5.0
OUTPUT_COST_PER_MTOK = 25.0


class Settings(BaseSettings):
    """Every ``AGENT_TRUST_*`` variable, plus the optional API key."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_TRUST_",
        frozen=True,
        extra="ignore",
        case_sensitive=False,
    )

    cache_dir: Path = Field(default=Path.home() / ".cache" / "agent-trust")
    max_files: int = Field(default=20_000, gt=0)
    max_bytes: int = Field(default=209_715_200, gt=0)
    clone_timeout: int = Field(default=30, gt=0)
    llm_timeout: int = Field(default=20, gt=0)
    llm_model: str = Field(default=DEFAULT_MODEL, min_length=1)

    # No AGENT_TRUST_ prefix: this is the provider's own conventional name.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    @property
    def llm_available(self) -> bool:
        """True when an enrichment call could actually be made."""
        return bool(self.anthropic_api_key)


def _describe(error: ValidationError) -> str:
    """Turn a pydantic error into one line naming the offending variable."""
    parts: list[str] = []
    for item in error.errors():
        field = str(item["loc"][0]) if item["loc"] else "?"
        # Report the name the user actually set, not the python attribute.
        name = "ANTHROPIC_API_KEY" if field == "anthropic_api_key" else f"AGENT_TRUST_{field.upper()}"
        parts.append(f"{name}: {item['msg']}")
    return "; ".join(parts)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and validate settings once per process.

    Raises:
        ConfigError: a variable is set but unusable. The message names the
            variable; the traceback is not shown to the user.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration -- {_describe(exc)}") from exc
