"""Context Quality: structural detection, never a model's judgment."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_trust.acquire import read_facts
from agent_trust.analyzers.context_quality import (
    SPECS,
    agent_doc,
    check_agent_doc,
    check_architecture,
    check_conventions,
    check_do_not_touch,
    check_paths_resolve,
    check_readme,
    check_run_and_test,
    check_setup_commands,
    prose_words,
)
from agent_trust.inventory import RepoContext, build_context
from agent_trust.limits import Budget
from agent_trust.models import CheckStatus

FULL_DOC = """# CLAUDE.md

## Setup

```
uv sync --extra dev
```

## Architecture

```
agent_trust/
  cli.py
```

## Run and test

```
uv run agent-trust .
uv run python -m pytest
```

## Conventions

Sorted output everywhere.

## Do not touch

Do not edit `uv.lock` by hand; it is generated.
"""


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


def make_repo(tmp_path: Path, files: dict[str, str]) -> RepoContext:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _git(["init", "-q", "-b", "master"], root)
        _git(["config", "user.email", "t@example.com"], root)
        _git(["config", "user.name", "t"], root)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(["add", "-A", "-f"], root)
    _git(["commit", "-qm", "fixture repository for the context quality tests"], root)
    return build_context(
        root=root,
        source=str(root),
        facts=read_facts(root),
        budget=Budget(max_files=20_000, max_bytes=209_715_200),
    )


# ── CQ-01 · the agent doc ───────────────────────────────────────────────────


def test_no_docs_at_all_scores_zero_with_findings(tmp_path: Path) -> None:
    from agent_trust.analyzers.context_quality import AXIS, run
    from agent_trust.scoring import score_axis

    ctx = make_repo(tmp_path, {"app.py": "x = 1\n"})
    checks = run(ctx)
    axis = score_axis(AXIS, "Context Quality", checks)
    assert axis.score == 0
    assert all(c.status is not CheckStatus.PASS for c in checks)


def test_empty_agent_doc_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"CLAUDE.md": "\n\n"})
    outcome = check_agent_doc(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "empty" in outcome.detail


def test_one_doc_is_chosen_when_several_exist(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"CLAUDE.md": FULL_DOC, "AGENTS.md": FULL_DOC})
    chosen = agent_doc(ctx)
    assert chosen == "CLAUDE.md"
    assert chosen in check_agent_doc(ctx).detail


def test_cursorrules_counts_as_an_agent_doc(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {".cursorrules": "Use tabs.\n"})
    assert check_agent_doc(ctx).status is CheckStatus.PASS


# ── CQ-02 · README prose, code excluded ─────────────────────────────────────


def test_a_readme_that_is_one_code_block_fails(tmp_path: Path) -> None:
    body = "# demo\n\n```\n" + "\n".join(f"line {i} of code" for i in range(200)) + "\n```\n"
    ctx = make_repo(tmp_path, {"README.md": body})
    outcome = check_readme(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert prose_words(body) < 100


def test_readme_word_thresholds(tmp_path: Path) -> None:
    prose = " ".join(["word"] * 320)
    full = make_repo(tmp_path / "f", {"README.md": f"# demo\n\n{prose}\n"})
    assert check_readme(full).status is CheckStatus.PASS

    partial = make_repo(tmp_path / "p", {"README.md": "# demo\n\n" + " ".join(["word"] * 150)})
    assert check_readme(partial).status is CheckStatus.PARTIAL

    thin = make_repo(tmp_path / "t", {"README.md": "# demo\n\nA project.\n"})
    assert check_readme(thin).status is CheckStatus.FAIL


def test_missing_readme_fails(tmp_path: Path) -> None:
    assert check_readme(make_repo(tmp_path, {"app.py": "x = 1\n"})).status is CheckStatus.FAIL


# ── CQ-03..CQ-07 · headings OR the commands themselves ──────────────────────


def test_a_full_doc_passes_every_section_check(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"CLAUDE.md": FULL_DOC})
    for check in (
        check_setup_commands,
        check_architecture,
        check_run_and_test,
        check_conventions,
        check_do_not_touch,
    ):
        assert check(ctx).status is CheckStatus.PASS, check.__name__


def test_commands_without_a_matching_heading_still_pass(tmp_path: Path) -> None:
    # A doc that shows `uv sync` under any heading has told an agent what to run.
    doc = "# demo\n\n## Beginnings\n\n```\nuv sync --extra dev\n```\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc})
    assert check_setup_commands(ctx).status is CheckStatus.PASS


def test_a_heading_without_commands_still_passes(tmp_path: Path) -> None:
    doc = "# demo\n\n## Installation\n\nAsk a teammate to set you up.\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc})
    assert check_setup_commands(ctx).status is CheckStatus.PASS


def test_run_without_test_is_partial(tmp_path: Path) -> None:
    doc = "# demo\n\n```\nnpm run dev\n```\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc})
    outcome = check_run_and_test(ctx)
    assert outcome.status is CheckStatus.PARTIAL
    assert "test command" in outcome.detail


def test_directory_tree_satisfies_architecture(tmp_path: Path) -> None:
    doc = "# demo\n\n```\nsrc/\n  app/\n  lib/\n```\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc})
    assert check_architecture(ctx).status is CheckStatus.PASS


def test_every_check_names_the_document_that_satisfied_it(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"AGENTS.md": FULL_DOC})
    for check in (check_setup_commands, check_architecture, check_conventions):
        assert "AGENTS.md" in check(ctx).detail


# ── CQ-08 · do the cited paths resolve ──────────────────────────────────────


def test_a_missing_cited_path_is_named(tmp_path: Path) -> None:
    doc = "See `src/app.py`, `src/lib.py`, `src/gone.py`, `src/also_gone.py`.\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc, "src/app.py": "x = 1\n", "src/lib.py": "y = 2\n"})
    outcome = check_paths_resolve(ctx)
    assert outcome.status is CheckStatus.PARTIAL
    assert "src/gone.py" in outcome.detail


def test_all_paths_resolving_passes(tmp_path: Path) -> None:
    doc = "See `src/app.py` and `src/lib.py`.\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc, "src/app.py": "x = 1\n", "src/lib.py": "y = 2\n"})
    assert check_paths_resolve(ctx).status is CheckStatus.PASS


def test_a_version_string_is_not_treated_as_a_path(tmp_path: Path) -> None:
    # Regression guard: `1.0` in backticks used to parse as a filename and then
    # be reported as a broken documentation link.
    doc = "Schema version is `1.0`. See `src/app.py`.\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc, "src/app.py": "x = 1\n"})
    outcome = check_paths_resolve(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "1.0" not in outcome.detail


def test_a_suffix_citation_resolves(tmp_path: Path) -> None:
    # Regression guard: a doc citing `analyzers/patterns.py` for a file at
    # `pkg/analyzers/patterns.py` is accurate, not stale.
    doc = "Every regex lives in `analyzers/patterns.py`.\n"
    ctx = make_repo(tmp_path, {"CLAUDE.md": doc, "pkg/analyzers/patterns.py": "x = 1\n"})
    assert check_paths_resolve(ctx).status is CheckStatus.PASS


def test_no_agent_doc_makes_the_check_not_applicable(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"README.md": "# demo\n"})
    assert check_paths_resolve(ctx).status is CheckStatus.NOT_APPLICABLE


def test_a_doc_citing_no_paths_is_not_applicable(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"CLAUDE.md": "Be careful.\n"})
    assert check_paths_resolve(ctx).status is CheckStatus.NOT_APPLICABLE


# ── the axis ────────────────────────────────────────────────────────────────


def test_weights_total_one_hundred_across_eight_checks() -> None:
    assert sum(spec.weight for spec in SPECS) == 100
    assert len(SPECS) == 8


def test_this_repo_scores_well_on_its_own_agent_doc() -> None:
    # Dogfooding. A tool that grades agent-operability must not have a bad
    # CLAUDE.md, and this is the check that keeps it honest.
    from agent_trust.acquire import read_facts as facts_of
    from agent_trust.analyzers.context_quality import AXIS, run
    from agent_trust.scoring import score_axis

    root = Path(__file__).resolve().parent.parent
    ctx = build_context(
        root=root,
        source=str(root),
        facts=facts_of(root),
        budget=Budget(max_files=20_000, max_bytes=209_715_200),
    )
    axis = score_axis(AXIS, "Context Quality", run(ctx))
    assert axis.score is not None and axis.score >= 80
