"""The command-line surface. A thin adapter over :func:`agent_trust.pipeline.audit`.

Exit codes, and never collapse them:

* ``0`` graded successfully
* ``1`` operational error -- clone failed, not a git repo, timed out
* ``2`` graded, but worse than ``--min-grade`` (the CI gate)

An operational error prints one line to stderr and no traceback. The traceback
goes to the log, where a developer can find it; the user gets a sentence.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agent_trust import __version__
from agent_trust.config import get_settings
from agent_trust.errors import AgentTrustError
from agent_trust.logging import get_logger
from agent_trust.models import AXIS_ORDER, AxisKey, Letter
from agent_trust.pipeline import audit, write_reports
from agent_trust.render import render_terminal
from agent_trust.scoring.grades import BANDS

logger = get_logger("cli")

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Score a git repository on how safely an autonomous coding agent can operate inside it.",
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BELOW_GRADE = 2

_LETTER_RANK = {letter: rank for rank, (_score, letter) in enumerate(BANDS)}


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(EXIT_OK)


def _fail(message: str) -> None:
    """One line to stderr, no traceback, exit 1."""
    Console(stderr=True).print(f"[red]error[/red] {message}")
    raise typer.Exit(EXIT_ERROR)


@app.command()
def main(
    source: Annotated[str, typer.Argument(help="Repository URL or local path to audit.")] = ".",
    axis: Annotated[
        list[str] | None,
        typer.Option("--axis", help="Score only this axis. Repeatable."),
    ] = None,
    output_format: Annotated[
        list[str] | None,
        typer.Option("--format", help="Report format to write: md, json or html. Repeatable."),
    ] = None,
    out: Annotated[Path, typer.Option("--out", help="Directory for report files.")] = Path("."),
    no_llm: Annotated[
        bool, typer.Option("--no-llm", help="Skip the enrichment call entirely.")
    ] = False,
    min_grade: Annotated[
        str | None,
        typer.Option("--min-grade", help="Exit 2 if the overall grade is worse than this."),
    ] = None,
    allow_any_host: Annotated[
        bool, typer.Option("--allow-any-host", help="Permit clone hosts off the allowlist.")
    ] = False,
    timeout: Annotated[int, typer.Option("--timeout", help="Whole-run budget, seconds.")] = 60,
    use_cache: Annotated[
        bool, typer.Option("--cache/--no-cache", help="Reuse a cached report for this commit.")
    ] = True,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Suppress the summary; still writes files.")
    ] = False,
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Print version."),
    ] = False,
) -> None:
    """Grade a repository and write its report."""
    settings = get_settings()
    formats = output_format or ["md"]

    for fmt in formats:
        if fmt not in {"md", "json", "html"}:
            _fail(f"unknown --format '{fmt}'. Use md, json or html.")

    axes: list[AxisKey] | None = None
    if axis:
        for key in axis:
            if key not in AXIS_ORDER:
                _fail(f"unknown --axis '{key}'. Choose from: {', '.join(AXIS_ORDER)}.")
        axes = [AxisKey(key) for key in axis]

    floor: Letter | None = None
    if min_grade is not None:
        try:
            floor = Letter(min_grade.upper())
        except ValueError:
            _fail(f"unknown --min-grade '{min_grade}'. Use A, B, C, D or F.")

    if not settings.llm_available and not no_llm and not quiet:
        Console(stderr=True).print(
            "[dim]No ANTHROPIC_API_KEY configured — using template explanations. "
            "Set the key, or pass --no-llm to silence this.[/dim]"
        )

    try:
        report = audit(
            source,
            axes=axes,
            use_llm=not no_llm,
            allow_any_host=allow_any_host,
            timeout=timeout,
            settings=settings,
            use_cache=use_cache,
        )
    except AgentTrustError as exc:
        logger.info("audit failed", exc_info=True, extra={"code": exc.code})
        _fail(exc.message)
        return
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        _fail("interrupted")
        return

    written = write_reports(report, out, formats)
    render_terminal(report, quiet=quiet)
    if not quiet:
        Console().print("[dim]" + "  ".join(str(path) for path in written) + "[/dim]")

    if floor is not None:
        if report.overall.letter is Letter.NA:
            # A gate must never read "could not measure" as "passed".
            Console(stderr=True).print(
                "[yellow]no axis could be scored, so --min-grade cannot be satisfied[/yellow]"
            )
            raise typer.Exit(EXIT_BELOW_GRADE)
        if _LETTER_RANK[report.overall.letter] > _LETTER_RANK[floor]:
            Console(stderr=True).print(
                f"[yellow]grade {report.overall.letter.value} is below "
                f"--min-grade {floor.value}[/yellow]"
            )
            raise typer.Exit(EXIT_BELOW_GRADE)

    raise typer.Exit(EXIT_OK)


def run() -> None:  # pragma: no cover - console-script shim
    sys.exit(app())
