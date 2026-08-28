"""Renderers show what the Report says -- no arithmetic, no escapes, no network."""

from __future__ import annotations

import io
import re
from pathlib import Path

from golden import HOSTILE, golden_report
from rich.console import Console

from agent_trust.models import Report, load_report
from agent_trust.render import render_html, render_markdown, render_terminal
from agent_trust.render.context import NO_FINDINGS, NO_FIXES, build, format_effort

FIXTURES = Path(__file__).parent / "fixtures"


def plain_terminal(report: Report, **kwargs: object) -> str:
    """Render the terminal summary with colour and width pinned, as a string."""
    buffer = io.StringIO()
    console = Console(
        file=buffer, width=100, no_color=True, force_terminal=False, legacy_windows=False
    )
    render_terminal(report, console=console, **kwargs)  # type: ignore[arg-type]
    return buffer.getvalue()


# ── golden files ────────────────────────────────────────────────────────────


def test_markdown_matches_the_golden_file() -> None:
    expected = (FIXTURES / "report.golden.md").read_text(encoding="utf-8")
    assert render_markdown(golden_report()) == expected


def test_html_matches_the_golden_file() -> None:
    expected = (FIXTURES / "report.golden.html").read_text(encoding="utf-8")
    assert render_html(golden_report()) == expected


def test_golden_json_round_trips() -> None:
    document = (FIXTURES / "golden_report.json").read_text(encoding="utf-8")
    assert load_report(document).stable_json() == golden_report().stable_json()


def test_rendering_twice_is_byte_identical() -> None:
    report = golden_report()
    assert render_markdown(report) == render_markdown(report)
    assert render_html(report) == render_html(report)


# ── untrusted repository content ────────────────────────────────────────────


def test_repo_script_tag_renders_as_text_not_markup() -> None:
    html = render_html(golden_report())
    assert HOSTILE not in html, "repository content reached the page unescaped"
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in html


def test_html_makes_no_external_requests() -> None:
    html = render_html(golden_report())
    # Resource references, not URLs appearing as text: the audited repo's own
    # URL is legitimately printed on the page.
    assert re.search(r"(?:src|href)\s*=", html) is None
    assert "<script" not in html.replace("&lt;script", "")


# ── what the reader must not miss ───────────────────────────────────────────


def test_cap_reason_appears_directly_under_the_grade_in_every_renderer() -> None:
    report = golden_report()
    reason = report.overall.cap_reason
    assert reason

    lines = [line for line in plain_terminal(report).splitlines() if line.strip()]
    grade_index = next(i for i, line in enumerate(lines) if line.startswith("Grade"))
    assert reason in lines[grade_index + 1]

    markdown = render_markdown(report).splitlines()
    grade_line = next(i for i, line in enumerate(markdown) if line.startswith("**Grade"))
    assert any(reason in line for line in markdown[grade_line : grade_line + 4])

    assert reason in render_html(report)


def test_truncation_is_stated_in_every_renderer() -> None:
    report = golden_report()
    assert "truncated" in render_markdown(report).lower()
    assert "Truncated" in render_html(report)
    assert "Truncated" in plain_terminal(report)


def test_axis_order_is_the_canonical_order_everywhere() -> None:
    # Measured on the axis rows themselves. A plain first-occurrence search finds
    # "Blast Radius" in the cap reason above the table and reports false drift.
    report = golden_report()
    names = [axis.name for axis in report.axes]

    markdown_rows = [
        name
        for line in render_markdown(report).splitlines()
        for name in names
        if line.startswith(f"| {name} |")
    ]
    html_cells = [
        name
        for line in render_html(report).splitlines()
        for name in names
        if f"<td>{name}</td>" in line
    ]
    # The cap reason also begins with an axis name, so a row must be the name
    # followed by its score column.
    terminal_rows = [
        name
        for line in plain_terminal(report).splitlines()
        for name in names
        if re.match(rf"^{re.escape(name)}\s+(\d+|N/A)\b", line.strip())
    ]

    assert markdown_rows == names
    assert html_cells == names
    assert terminal_rows == names


def test_findings_show_path_and_line() -> None:
    markdown = render_markdown(golden_report())
    assert "config/settings.py:12" in markdown


def test_na_axis_shows_na_not_zero() -> None:
    report = golden_report()
    observability = next(a for a in report.axes if a.key.value == "observability")
    assert observability.score is None

    markdown = render_markdown(report)
    row = next(line for line in markdown.splitlines() if line.startswith("| Observability"))
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[1] == "N/A", f"score column should be N/A, got {cells[1]!r}"
    assert cells[2] == "N/A", f"grade column should be N/A, got {cells[2]!r}"


# ── empty states ────────────────────────────────────────────────────────────


def _clean_report() -> Report:
    report = golden_report()
    return report.model_copy(update={"findings": (), "fixes": ()})


def test_empty_states_render_a_real_line_in_all_three() -> None:
    report = _clean_report()
    markdown = render_markdown(report)
    html = render_html(report)
    terminal = plain_terminal(report)

    assert markdown.count(NO_FINDINGS) == len(report.axes)
    assert html.count(NO_FINDINGS) == len(report.axes)
    assert NO_FIXES in markdown
    assert NO_FIXES in html
    assert NO_FIXES in terminal


# ── terminal specifics ──────────────────────────────────────────────────────


def test_piped_output_carries_no_escape_codes() -> None:
    assert "\x1b" not in plain_terminal(golden_report())


def test_quiet_suppresses_the_summary() -> None:
    assert plain_terminal(golden_report(), quiet=True) == ""


def test_terminal_shows_at_most_three_fixes() -> None:
    text = plain_terminal(golden_report())
    assert "  1. " in text and "  3. " in text
    assert "  4. " not in text


# ── the view model does no arithmetic ───────────────────────────────────────


def test_context_copies_scores_rather_than_recomputing() -> None:
    report = golden_report()
    view = build(report)
    assert view["overall"]["score"] == report.overall.score
    for rendered, axis in zip(view["axes"], report.axes, strict=True):
        assert rendered["score"] == axis.score


def test_effort_formatting() -> None:
    assert format_effort(15) == "15m"
    assert format_effort(60) == "1h"
    assert format_effort(90) == "1h30m"
    assert format_effort(480) == "8h"
