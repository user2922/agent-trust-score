"""The single Claude call.

Standing rule B governs this whole module: **the model writes prose, never
numbers.** Delete the API key and the wording of a report changes; nothing else
does. The merge asserts that rather than trusting it.

Failure here is a normal path, not an exception. A missing key, a timeout, a
connection error, a schema violation and a refusal all degrade to the template
text that :mod:`agent_trust.scoring.findings` already wrote. The one thing that
raises is a configured model that no longer exists, because silently grading with
a different model than the operator asked for is worse than stopping.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    NotFoundError,
    RateLimitError,
)
from anthropic.types import OutputConfigParam
from pydantic import BaseModel, Field, ValidationError

from agent_trust.config import INPUT_COST_PER_MTOK, OUTPUT_COST_PER_MTOK, Settings
from agent_trust.errors import EnrichmentError
from agent_trust.logging import get_logger
from agent_trust.models import ExplanationSource, LlmUsage, Report

logger = get_logger("enrich")

MAX_TOKENS = 8000
MAX_EVIDENCE_SNIPPETS = 40
MAX_DOC_CHARS = 24_000  # ~6k tokens across the agent doc and README combined
# Typed as a Literal so the SDK's TypedDict accepts it without a cast.
EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"


class Enrichment(BaseModel):
    """Everything the model is allowed to return."""

    summary: str = Field(description="Two or three sentences on what this repo's grade means.")
    explanations: dict[str, str] = Field(
        default_factory=dict,
        description="finding id -> one paragraph on why it matters for THIS repo.",
    )
    fix_steps: dict[str, list[str]] = Field(
        default_factory=dict,
        description="fix id -> imperative steps specific to this repo.",
    )


# The stable prefix. Nothing repo-specific may appear here: a timestamp, a repo
# name or a commit SHA above the cache breakpoint means the cache never hits.
SYSTEM_PROMPT = """You explain the results of a static repository audit.

The audit scores a repository on how safely an autonomous coding agent can
operate inside it, across five axes: tool surface, blast radius, verifiability,
context quality and observability.

Your job is to write prose. You are given a report whose scores, statuses,
severities and ordering are already final and were computed deterministically.
You may not dispute them, recompute them, or suggest they are wrong. Write only:

1. summary: two or three sentences on what this grade means in practice for
   someone about to point a coding agent at this repository.
2. explanations: for each finding id, one short paragraph on why it matters for
   THIS repository, referring to the evidence you were given. Be concrete and
   avoid restating the finding title.
3. fix_steps: for each fix id, imperative steps a competent engineer can follow.

Rules:
- Never claim the repository is secure, certified, or safe. The audit grades
  structure, and saying more than that is false.
- Never invent a file path, a line number or a finding. Use only what you are
  given.
- If evidence is thin, say what is unknown rather than guessing.
- Return an id only if it appeared in the input. Unknown ids are discarded."""


def _payload(report: Report, docs: str) -> str:
    """The volatile half of the prompt: this repo's scored report."""
    findings = [
        {
            "id": finding.id,
            "check": finding.check_id,
            "axis": finding.axis.value,
            "severity": finding.severity.value,
            "title": finding.title,
            "evidence": [
                {"path": item.path, "line": item.line, "snippet": item.snippet}
                for item in finding.evidence
            ],
        }
        for finding in report.findings
    ]
    # Cap the evidence rather than the findings: every finding keeps its entry so
    # the model can explain all of them, but the bytes stay bounded.
    seen = 0
    for finding in findings:
        remaining = max(0, MAX_EVIDENCE_SNIPPETS - seen)
        finding["evidence"] = finding["evidence"][:remaining]
        seen += len(finding["evidence"])

    return json.dumps(
        {
            "overall": {
                "score": report.overall.score,
                "letter": report.overall.letter.value,
                "capped": report.overall.capped,
                "cap_reason": report.overall.cap_reason,
            },
            "axes": [
                {"key": axis.key.value, "score": axis.score, "letter": axis.letter.value}
                for axis in report.axes
            ],
            "findings": findings,
            "fixes": [
                {
                    "id": fix.id,
                    "title": fix.title,
                    "axis": fix.axis.value,
                    "points": fix.risk_reduction,
                    "effort_minutes": fix.effort_minutes,
                }
                for fix in report.fixes
            ],
            "repo_docs_excerpt": docs[:MAX_DOC_CHARS],
        },
        sort_keys=True,
    )


def _cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
        + output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK,
        6,
    )


def _merge(report: Report, enrichment: Enrichment, usage: LlmUsage) -> Report:
    """Apply prose by id, then assert nothing else moved.

    This assertion is the enforcement of rule B. It is not a comment about the
    rule; it is the rule.
    """
    findings = tuple(
        finding.model_copy(
            update={
                "explanation": enrichment.explanations[finding.id],
                "explanation_source": ExplanationSource.LLM,
            }
        )
        if finding.id in enrichment.explanations
        else finding
        for finding in report.findings
    )
    fixes = tuple(
        fix.model_copy(update={"steps": tuple(enrichment.fix_steps[fix.id])})
        if fix.id in enrichment.fix_steps
        else fix
        for fix in report.fixes
    )

    enriched = report.model_copy(update={"findings": findings, "fixes": fixes, "llm": usage})

    before = report.model_copy(update={"llm": usage}).stable_payload()
    after = enriched.stable_payload()
    for section in ("overall", "axes", "repo"):
        if before[section] != after[section]:
            raise EnrichmentError(f"enrichment altered {section}; refusing to use the result")
    if [f["severity"] for f in before["findings"]] != [f["severity"] for f in after["findings"]]:
        raise EnrichmentError("enrichment altered a severity; refusing to use the result")
    if [f["id"] for f in before["fixes"]] != [f["id"] for f in after["fixes"]]:
        raise EnrichmentError("enrichment reordered the fixes; refusing to use the result")

    return enriched


def _fallback(report: Report, reason: str, model: str | None = None) -> Report:
    """Keep the template text and record why the model did not write."""
    logger.info("enrichment fell back", extra={"reason": reason})
    return report.model_copy(
        update={"llm": LlmUsage(used=False, model=model, fallback_reason=reason)}
    )


def enrich(
    report: Report,
    settings: Settings,
    docs: str = "",
    client: Any | None = None,
) -> Report:
    """Add model-written prose to ``report``, or return it unchanged.

    Args:
        report: the scored report. Its numbers are final.
        settings: configuration, including the model id and the timeout.
        docs: the agent doc and README, already truncated by the caller.
        client: injected for tests. A real Anthropic client is built when omitted.

    Raises:
        EnrichmentError: the configured model does not exist, or the merge
            detected that the model changed something it may not change.
    """
    if not settings.llm_available:
        return _fallback(report, "no ANTHROPIC_API_KEY configured")
    if not report.findings and not report.fixes:
        return _fallback(report, "nothing to explain")

    api = client or Anthropic(api_key=settings.anthropic_api_key, timeout=settings.llm_timeout)

    try:
        response = api.messages.parse(
            model=settings.llm_model,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            # The SDK takes the response model through output_format; effort is
            # the only thing output_config carries here.
            output_format=Enrichment,
            output_config=OutputConfigParam(effort=EFFORT),
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": _payload(report, docs)}],
        )
    except NotFoundError as exc:
        # A configured model that no longer exists must surface, not silently
        # become "the report has template text today".
        raise EnrichmentError(
            f"model '{settings.llm_model}' was not found. Set AGENT_TRUST_LLM_MODEL "
            f"to a current model id."
        ) from exc
    except (APITimeoutError, APIConnectionError) as exc:
        return _fallback(report, f"{type(exc).__name__}", settings.llm_model)
    except RateLimitError:
        return _fallback(report, "rate limited", settings.llm_model)
    except APIStatusError as exc:
        return _fallback(report, f"API error {exc.status_code}", settings.llm_model)

    if getattr(response, "stop_reason", None) == "refusal":
        return _fallback(report, "the model declined to answer", settings.llm_model)

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        return _fallback(report, "no structured output returned", settings.llm_model)
    try:
        enrichment = parsed if isinstance(parsed, Enrichment) else Enrichment.model_validate(parsed)
    except ValidationError:
        return _fallback(report, "response did not match the schema", settings.llm_model)

    input_tokens = getattr(response.usage, "input_tokens", 0)
    output_tokens = getattr(response.usage, "output_tokens", 0)
    usage = LlmUsage(
        used=True,
        model=settings.llm_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_cost(input_tokens, output_tokens),
    )
    return _merge(report, enrichment, usage)
