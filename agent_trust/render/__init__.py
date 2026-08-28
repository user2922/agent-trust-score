"""Renderers: Report in, text out. None of them computes a number.

A renderer that recalculated a score could disagree with ``report.json``, and
the JSON is what a CI gate reads. Every value comes from
:mod:`agent_trust.render.context`.
"""

from __future__ import annotations

from agent_trust.render.html import render_html
from agent_trust.render.markdown import render_markdown
from agent_trust.render.terminal import render_terminal

__all__ = ["render_html", "render_markdown", "render_terminal"]
