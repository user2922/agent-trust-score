"""The MCP surface -- a thin adapter over :func:`agent_trust.pipeline.audit`.

Written against the **mcp 2.x** SDK, where ``FastMCP`` was renamed ``MCPServer``.
Code recalled from the 1.x API will not import.

Two properties matter here more than anywhere else in the product:

* **Nothing but protocol frames reaches stdout.** The stdio transport *is*
  stdout. Logging goes to stderr (see :mod:`agent_trust.logging`), and the
  renderers are never called on this path.
* **No exception escapes as a traceback.** A calling agent gets a structured
  ``{"error": {"code", "message"}}`` payload it can act on, never a stack trace
  it will paste back to a user.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer

from agent_trust.config import get_settings
from agent_trust.errors import AgentTrustError
from agent_trust.logging import get_logger
from agent_trust.models import AXIS_ORDER, AxisKey, Report
from agent_trust.pipeline import audit

logger = get_logger("mcp")

# A calling agent should not wait longer than this for any one tool.
TOOL_TIMEOUT_SECONDS = 90

server = MCPServer(
    name="agent-trust-score",
    instructions=(
        "Scores a git repository on how safely an autonomous coding agent can "
        "operate inside it: tool surface, blast radius, verifiability, context "
        "quality and observability. Returns a letter grade per axis, evidence "
        "with file and line references, and fixes ranked by risk reduction per "
        "hour. It reads repositories; it never executes their code."
    ),
)


def _error(exc: Exception) -> dict[str, Any]:
    """Every failure crosses the boundary as data, never as a traceback."""
    if isinstance(exc, AgentTrustError):
        logger.info("tool failed", extra={"code": exc.code})
        return exc.as_payload()
    logger.info("tool failed", exc_info=True, extra={"code": "internal_error"})
    return {
        "error": {
            "code": "internal_error",
            "message": "The audit failed unexpectedly. Check the server log for detail.",
        }
    }


def _run_audit(source: str, axes: list[str] | None, use_llm: bool) -> Report:
    settings = get_settings()
    keys = [AxisKey(a) for a in axes] if axes else None
    return audit(
        source,
        axes=keys,
        use_llm=use_llm,
        timeout=TOOL_TIMEOUT_SECONDS,
        settings=settings,
    )


@server.tool()
def audit_repo(source: str, axes: list[str] | None = None, use_llm: bool = True) -> dict[str, Any]:
    """Grade a repository on all five agent-operability axes.

    Args:
        source: a repository URL (github.com, gitlab.com, bitbucket.org or
            codeberg.org) or a local path.
        axes: score only these axes. Valid keys: tool_surface, blast_radius,
            verifiability, context_quality, observability.
        use_llm: let the model write the explanation prose. Costs roughly
            $0.25 per uncached audit. Scores are identical either way.

    Returns:
        The full report: overall grade, per-axis scores, findings with evidence,
        and fixes ranked by points recovered per hour.
    """
    try:
        if axes:
            unknown = sorted(set(axes) - set(AXIS_ORDER))
            if unknown:
                raise AgentTrustError(f"unknown axes: {unknown}. Valid: {list(AXIS_ORDER)}")
        return _run_audit(source, axes, use_llm).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - the boundary converts everything to data
        return _error(exc)


@server.tool()
def get_axis(source: str, axis: str) -> dict[str, Any]:
    """Grade one axis of a repository.

    Args:
        source: a repository URL or local path.
        axis: one of tool_surface, blast_radius, verifiability, context_quality,
            observability.

    Returns:
        That axis: its score, letter, and every check behind them.
    """
    try:
        if axis not in AXIS_ORDER:
            raise AgentTrustError(f"unknown axis '{axis}'. Valid: {list(AXIS_ORDER)}")
        report = _run_audit(source, [axis], use_llm=False)
        scored = next(a for a in report.axes if a.key.value == axis)
        return scored.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@server.tool()
def suggest_fixes(source: str, max_items: int = 10) -> dict[str, Any]:
    """List what to fix first, ranked by risk reduction per hour of effort.

    Args:
        source: a repository URL or local path.
        max_items: how many fixes to return, highest ratio first.

    Returns:
        ``{"fixes": [...]}`` -- each with steps, points recovered, and effort.
    """
    try:
        if max_items < 1:
            raise AgentTrustError("max_items must be at least 1")
        report = _run_audit(source, None, use_llm=False)
        return {"fixes": [fix.model_dump(mode="json") for fix in report.fixes[:max_items]]}
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def main() -> None:  # pragma: no cover - process entry point
    """Serve over stdio. Nothing but protocol frames may reach stdout."""
    asyncio.run(server.run_stdio_async())
