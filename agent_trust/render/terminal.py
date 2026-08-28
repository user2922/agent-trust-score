"""Terminal summary.

Writes to stdout; logs go to stderr (see :mod:`agent_trust.logging`). Degrades
to plain text when the stream is not a TTY or NO_COLOR is set, so piping the
output to a file produces no escape codes.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from agent_trust.models import Letter, Report
from agent_trust.render.context import build

_LETTER_COLOUR = {
    Letter.A.value: "green",
    Letter.B.value: "bright_green",
    Letter.C.value: "yellow",
    Letter.D.value: "dark_orange",
    Letter.F.value: "red",
    Letter.NA.value: "dim",
}

TOP_FIXES = 3


def render_terminal(report: Report, console: Console | None = None, quiet: bool = False) -> None:
    """Print the summary. ``quiet`` suppresses everything but still writes files."""
    if quiet:
        return

    view = build(report)
    out = console or Console()

    out.print()
    out.print(
        Text.assemble(
            ("Agent Trust Score  ", "bold"),
            (view["repo"]["source"], "dim"),
        )
    )

    letter = view["overall"]["letter"]
    out.print(
        Text.assemble(
            ("Grade ", ""),
            (letter, f"bold {_LETTER_COLOUR.get(letter, 'default')}"),
            (f"  {view['overall']['score_text']}/100", "dim"),
        )
    )
    # The cap reason goes directly under the grade: a C that is really a capped A
    # is the most important thing on the screen.
    if view["overall"]["capped"]:
        out.print(Text(view["overall"]["cap_reason"] or "", style="yellow"))
    if view["repo"]["truncated"]:
        out.print(
            Text(
                f"Truncated: analyzed {view['repo']['analyzed']} of "
                f"{view['repo']['total']} tracked files.",
                style="yellow",
            )
        )
    out.print()

    table = Table(show_edge=False, pad_edge=False, box=None)
    table.add_column("Axis")
    table.add_column("Score", justify="right")
    table.add_column("Grade", justify="center")
    table.add_column("Failed", justify="right")
    for axis in view["axes"]:
        table.add_row(
            axis["name"],
            axis["score_text"],
            Text(axis["letter"], style=_LETTER_COLOUR.get(axis["letter"], "default")),
            str(axis["failed"]),
        )
    out.print(table)
    out.print()

    fixes = view["fixes"][:TOP_FIXES]
    if fixes:
        out.print(Text("Fix these first", style="bold"))
        for index, fix in enumerate(fixes, start=1):
            out.print(
                f"  {index}. {fix['title']}  "
                f"[dim]{fix['effort']}, recovers {fix['points']} points[/dim]"
            )
    else:
        out.print(Text(view["no_fixes"], style="dim"))
    out.print()
