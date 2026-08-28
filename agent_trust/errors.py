"""Exception hierarchy.

Every error carries a machine-readable ``code`` and a ``message`` that is safe to
show a user: no traceback, no absolute path outside the audited repository, no
repository content. See CLAUDE.md, "What a report must never contain".

Prompt 2a defines the base and the configuration error. Prompt 2b adds the
acquisition errors; Prompt 14 adds the enrichment error.
"""

from __future__ import annotations


class AgentTrustError(Exception):
    """Base for every error this tool raises deliberately."""

    code = "agent_trust_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def as_payload(self) -> dict[str, dict[str, str]]:
        """The structured form returned across the MCP boundary."""
        return {"error": {"code": self.code, "message": self.message}}


class ConfigError(AgentTrustError):
    """An environment variable is present but unusable."""

    code = "config_error"
