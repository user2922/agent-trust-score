"""Self-contained HTML rendering.

Two properties are non-negotiable:

* **Autoescape is on.** Repository content -- README prose, file paths, evidence
  snippets -- lands in this page. A repo whose README contains a script tag must
  render as visible text.
* **No external requests.** All CSS is inline, there are no scripts, no fonts and
  no images. The page must open correctly from a file:// URL with no network.
"""

from __future__ import annotations

from agent_trust.models import Report
from agent_trust.render.context import build
from agent_trust.render.markdown import html_environment


def render_html(report: Report) -> str:
    """Render the single-file HTML report."""
    template = html_environment().get_template("report.html.j2")
    return template.render(**build(report))
