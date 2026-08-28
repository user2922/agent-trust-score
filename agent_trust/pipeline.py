"""The one audit function both delivery surfaces call.

The CLI and the MCP server are thin adapters over :func:`audit`. Neither has
logic of its own, so the two cannot drift apart in what they report.

Stage order: acquire -> inventory -> analyzers -> score -> enrich -> render.
The analyzer registry starts empty; Prompt 8 defines how analyzers register into
it. Until then an audit honestly reports five N/A axes rather than inventing a
score.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from agent_trust import cache
from agent_trust.acquire import acquire, peek_commit_sha, read_facts
from agent_trust.analyzers import REGISTRY
from agent_trust.config import Settings, get_settings
from agent_trust.enrich import enrich
from agent_trust.inventory import RepoContext, build_context
from agent_trust.limits import Budget, Deadline
from agent_trust.logging import get_logger
from agent_trust.models import AxisKey, CheckResult, LlmUsage, RepoInfo, Report
from agent_trust.scoring import score

logger = get_logger("pipeline")


def _run_analyzers(
    ctx: RepoContext, axes: Sequence[AxisKey] | None
) -> dict[AxisKey, Sequence[CheckResult]]:
    """Run each registered analyzer, in canonical axis order.

    An axis with no registered analyzer contributes nothing, which scores as
    N/A rather than as a failure.
    """
    wanted = set(axes) if axes else None
    results: dict[AxisKey, Sequence[CheckResult]] = {}
    for key, run in REGISTRY.items():
        if wanted is not None and key not in wanted:
            continue
        results[key] = run(ctx)
    return results


def audit(
    source: str,
    *,
    axes: Sequence[AxisKey] | None = None,
    use_llm: bool = True,
    allow_any_host: bool = False,
    timeout: int = 60,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> Report:
    """Audit ``source`` and return a Report.

    Args:
        source: a repository URL or a local path.
        axes: score only these axes; None means all five.
        use_llm: run the enrichment call. Ignored when no API key is configured.
        allow_any_host: permit clone hosts outside the allowlist.
        timeout: whole-run wall-clock budget in seconds.
        settings: injected configuration; loaded from the environment if omitted.
        use_cache: reuse a cached report for this commit when one exists. The
            SHA is read with ``git ls-remote``, so a hit skips the clone.

    Raises:
        AgentTrustError: the repository could not be acquired, or the run
            exceeded its deadline.
    """
    config = settings or get_settings()
    deadline = Deadline(seconds=timeout)
    started = time.monotonic()

    want_llm = use_llm and config.llm_available
    if use_cache:
        sha = peek_commit_sha(source, allow_any_host=allow_any_host, timeout=config.clone_timeout)
        cached = cache.read(config.cache_dir, sha, want_llm=want_llm)
        if cached is not None:
            logger.info("cache hit", extra={"commit": (sha or "")[:12]})
            return cached

    with acquire(source, allow_any_host=allow_any_host, timeout=config.clone_timeout) as root:
        deadline.check("clone")
        facts = read_facts(root)
        budget = Budget(max_files=config.max_files, max_bytes=config.max_bytes)
        ctx = build_context(root=root, source=source, facts=facts, budget=budget)
        deadline.check("inventory")

        results = _run_analyzers(ctx, axes)
        deadline.check("analysis")

        axis_scores, overall, findings, fixes = score(results)

        report = Report(
            generated_at=datetime.now(UTC),
            run_ms=int((time.monotonic() - started) * 1000),
            repo=_repo_info(ctx),
            overall=overall,
            axes=axis_scores,
            findings=findings,
            fixes=fixes,
            llm=LlmUsage(used=False, fallback_reason="--no-llm"),
        )

        if use_llm:
            deadline.check("enrichment")
            report = enrich(report, config, docs=_docs_excerpt(ctx))

        if use_cache:
            cache.write(config.cache_dir, report)
        return report


def _repo_info(ctx: RepoContext) -> RepoInfo:
    return RepoInfo(
        source=ctx.source,
        commit_sha=ctx.commit_sha,
        default_branch=ctx.default_branch,
        file_count=ctx.file_count,
        analyzed_file_count=ctx.analyzed_file_count,
        bytes_scanned=ctx.bytes_scanned,
        languages=dict(ctx.languages),
        truncated=ctx.truncated,
        skipped=dict(ctx.skipped),
    )


def _docs_excerpt(ctx: RepoContext) -> str:
    """The agent doc and README, for the model to ground its prose in."""
    from agent_trust.analyzers.context_quality import agent_doc, readme

    parts = []
    for path in (agent_doc(ctx), readme(ctx)):
        if path:
            parts.append(f"--- {path} ---\n{ctx.read_text(path)}")
    return "\n\n".join(parts)


def write_reports(report: Report, out_dir: Path, formats: Sequence[str]) -> list[Path]:
    """Write the requested report files and return their paths, sorted."""
    from agent_trust.render import render_html, render_markdown

    out_dir.mkdir(parents=True, exist_ok=True)
    renderers: Mapping[str, tuple[str, str]] = {
        "md": ("report.md", render_markdown(report)),
        "json": ("report.json", report.to_json() + "\n"),
        "html": ("report.html", render_html(report)),
    }

    written: list[Path] = []
    for fmt in sorted(set(formats)):
        name, body = renderers[fmt]
        path = out_dir / name
        path.write_text(body, encoding="utf-8", newline="")
        written.append(path)
    return sorted(written)
