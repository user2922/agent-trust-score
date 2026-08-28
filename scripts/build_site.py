"""Build the static report site.

Generates a real report for each demo target and an index that links them. The
HTML renderer already emits self-contained pages with no external requests, so
the output is a directory of static files and nothing else -- no build step, no
runtime, no server.

Usage:
    uv run python scripts/build_site.py site
"""

from __future__ import annotations

import sys
import tempfile
from html import escape
from pathlib import Path

from agent_trust.models import Report
from agent_trust.pipeline import audit
from agent_trust.render import render_html

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_fixtures import build_clean, build_ugly  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

INDEX_CSS = """
:root {
  color-scheme: light;
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --ink-3:#898781;
  --hairline:#e1e0d9; --rule:#c3c2b7; --ring:rgba(11,11,11,.10);
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --track:#e8e7e1;
  --shadow: 0 1px 2px rgba(11,11,11,.04), 0 8px 24px -12px rgba(11,11,11,.10);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --ink-3:#898781;
    --hairline:#2c2c2a; --rule:#383835; --ring:rgba(255,255,255,.10); --track:#2c2c2a;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }
}
*, *::before, *::after { box-sizing:border-box; }
body {
  margin:0; background:var(--plane); color:var(--ink);
  font:400 15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;
}
.wrap { max-width:52rem; margin:0 auto; padding:5rem 1.5rem 6rem; }
.eyebrow {
  font-size:.6875rem; font-weight:600; letter-spacing:.11em; text-transform:uppercase;
  color:var(--ink-3); margin:0 0 1.25rem;
}
h1 { font-size:2.25rem; font-weight:600; letter-spacing:-.032em;
     margin:0 0 1rem; line-height:1.12; }
.lede { color:var(--ink-2); font-size:1.0625rem; margin:0 0 1rem; max-width:44ch; }
.run {
  display:inline-block; margin:0 0 3.5rem; padding:.5rem .75rem;
  background:var(--surface); border:1px solid var(--ring); border-radius:6px;
  font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.8125rem; color:var(--ink-2);
}
.run b { color:var(--ink); font-weight:600; }

.section-label {
  font-size:.6875rem; font-weight:600; letter-spacing:.09em; text-transform:uppercase;
  color:var(--ink-3); margin:0 0 .75rem; padding-bottom:.625rem;
  border-bottom:1px solid var(--rule);
}
a.card {
  display:block; text-decoration:none; color:inherit;
  padding:1.5rem 0; border-bottom:1px solid var(--hairline);
}
a.card:hover .name { text-decoration:underline; text-underline-offset:3px; }
.row { display:flex; align-items:center; gap:1.25rem; }
.grade {
  font-size:2.5rem; font-weight:600; line-height:1; letter-spacing:-.04em;
  min-width:2.75rem;
}
.score { font-variant-numeric:tabular-nums; color:var(--ink-3);
         font-size:.875rem; margin-top:.3rem; }
.body { flex:1; min-width:0; }
.name { font-size:1.0625rem; font-weight:600; letter-spacing:-.015em; }
.note { color:var(--ink-2); font-size:.875rem; margin:.3rem 0 0; max-width:52ch; }
.axes { display:flex; gap:.375rem; margin-top:.75rem; }
.axes i { display:block; height:4px; flex:1; border-radius:999px;
          background:var(--track); overflow:hidden; }
.axes i > s { display:block; height:100%; background:currentColor; border-radius:999px; }
.A{color:var(--good)} .B{color:var(--good)} .C{color:var(--warning)}
.D{color:var(--serious)} .F{color:var(--critical)} .NA{color:var(--ink-3)}
footer {
  margin-top:3.5rem; padding-top:1.5rem; border-top:1px solid var(--hairline);
  color:var(--ink-3); font-size:.8125rem; line-height:1.7;
}
footer a { color:var(--ink-2); }
@media (max-width:34rem) { h1 { font-size:1.75rem; } .grade { font-size:2rem; } }
"""


def index(entries: list[tuple[str, str, Report, str]]) -> str:
    """The landing page linking every generated report."""
    cards = []
    for slug, title, report, note in entries:
        letter = report.overall.letter.value.replace("/", "")
        score = "N/A" if report.overall.score is None else str(report.overall.score)
        bars = "".join(
            f'<i class="{axis.letter.value.replace("/", "")}">'
            f'<s style="width:{axis.score or 0}%"></s></i>'
            for axis in report.axes
        )
        cards.append(
            f'<a class="card" href="{slug}.html">'
            f'<div class="row">'
            f'<div><div class="grade {letter}">{letter}</div>'
            f'<div class="score">{score}/100</div></div>'
            f'<div class="body">'
            f'<div class="name">{escape(title)}</div>'
            f'<p class="note">{escape(note)}</p>'
            f'<div class="axes">{bars}</div>'
            f"</div></div></a>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Trust Score</title>
<style>{INDEX_CSS}</style></head>
<body><div class="wrap">
<p class="eyebrow">Agent Trust Score</p>
<h1>How safely can an agent work in this repository?</h1>
<p class="lede">Five axes, 37 checks, evidence with file and line, and a fix list
ranked by points recovered per hour. Static analysis only &mdash; it reads
repositories, it never runs them.</p>
<p class="run"><b>uvx agent-trust-score</b> &lt;repo&gt;</p>

<p class="section-label">Reports</p>
{"".join(cards)}

<footer>
Each bar is one axis, in order: tool surface, blast radius, verifiability,
context quality, observability.<br>
<a href="https://github.com/user2922/agent-trust-score">Source on GitHub</a> &middot;
This grades repository structure. It is not a security audit and it certifies nothing.
</footer>
</div></body></html>
"""


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "site").resolve()
    destination.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[str, str, Report, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        targets = [
            (
                "clean",
                "A well-prepared repository",
                build_clean(Path(tmp)),
                "The fixture that shows what good looks like: an agent doc, a schema, "
                "guarded destructive operations, CI that actually runs the tests.",
            ),
            (
                "ugly",
                "A repository an agent should not touch",
                build_ugly(Path(tmp)),
                "A committed credential caps the grade on its own. Findings on every "
                "axis, each with the file and line that produced it.",
            ),
            (
                "self",
                "agent-trust-score itself",
                REPO_ROOT,
                "The tool graded by the tool. Its remaining findings are real and "
                "unfixed rather than hidden.",
            ),
        ]
        for slug, title, root, note in targets:
            report = audit(str(root), use_llm=False, use_cache=False, timeout=180)
            (destination / f"{slug}.html").write_text(
                render_html(report), encoding="utf-8", newline=""
            )
            entries.append((slug, title, report, note))
            score = "N/A" if report.overall.score is None else report.overall.score
            print(f"  {slug:<6} {report.overall.letter.value}  {score}")

    (destination / "index.html").write_text(index(entries), encoding="utf-8", newline="")
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
