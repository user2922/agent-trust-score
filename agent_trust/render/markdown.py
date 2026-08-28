"""Markdown rendering.

Autoescaping is off here because markdown is plain text -- but the same content
goes through :mod:`agent_trust.render.html`, where autoescaping is on and
mandatory. Repository content appears in both.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from agent_trust.models import Report
from agent_trust.render.context import build

TEMPLATES = Path(__file__).parent / "templates"


def _environment(*, autoescape: bool) -> Environment:
    """A Jinja environment with deterministic whitespace handling.

    Private, and never called with a computed flag: markdown_environment and
    html_environment below are the only two callers, so the HTML renderer cannot
    be constructed with escaping off.
    """
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=autoescape,  # noqa: S701 - False only via markdown_environment()
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def markdown_environment() -> Environment:
    """Markdown is plain text: escaping would corrupt it into HTML entities."""
    return _environment(autoescape=False)


def html_environment() -> Environment:
    """Always escaping. Repository content lands in this page."""
    return _environment(autoescape=True)


def render_markdown(report: Report) -> str:
    """Render the markdown report. The same Report always yields the same bytes."""
    template = markdown_environment().get_template("report.md.j2")
    body = template.render(**build(report))
    # Collapse runs of blank lines so template block spacing cannot drift.
    lines = body.split("\n")
    out: list[str] = []
    blanks = 0
    for line in lines:
        stripped = line.rstrip()
        if stripped:
            blanks = 0
            out.append(stripped)
            continue
        blanks += 1
        if blanks <= 1:
            out.append("")
    return "\n".join(out).strip() + "\n"
