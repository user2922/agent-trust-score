"""Rule B: the model writes prose, never numbers.

Every test here answers one of two questions -- did the merge change anything it
may not change, and does every failure mode degrade rather than raise?
"""

from __future__ import annotations

from typing import Any

# anthropic 1.x is built on httpx2, not httpx. Constructing the SDK's error
# types needs the same library the SDK itself uses.
import httpx2
import pytest
from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    NotFoundError,
    RateLimitError,
)
from golden import golden_report

from agent_trust.config import Settings
from agent_trust.enrich import SYSTEM_PROMPT, Enrichment, _cost, _payload, enrich
from agent_trust.errors import EnrichmentError
from agent_trust.models import ExplanationSource


class StubUsage:
    def __init__(self, input_tokens: int = 12_000, output_tokens: int = 900) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class StubResponse:
    def __init__(self, parsed: Any, stop_reason: str = "end_turn") -> None:
        self.parsed_output = parsed
        self.stop_reason = stop_reason
        self.usage = StubUsage()


class StubMessages:
    """Records the request and returns whatever the test configured."""

    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class StubClient:
    def __init__(self, outcome: Any) -> None:
        self.messages = StubMessages(outcome)


def settings_with_key() -> Settings:
    return Settings(ANTHROPIC_API_KEY="sk-ant-not-a-real-key-for-tests")  # type: ignore[call-arg]


def settings_without_key() -> Settings:
    return Settings(ANTHROPIC_API_KEY=None)  # type: ignore[call-arg]


def full_enrichment(report: Any) -> Enrichment:
    return Enrichment(
        summary="A model-written summary.",
        explanations={finding.id: f"Model prose for {finding.id}." for finding in report.findings},
        fix_steps={fix.id: ["Model step one.", "Model step two."] for fix in report.fixes},
    )


def _status_error(code: int) -> APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(code, request=request)
    return APIStatusError("boom", response=response, body=None)


# ── the happy path changes prose and nothing else ───────────────────────────


def test_merge_changes_only_prose() -> None:
    report = golden_report()
    client = StubClient(StubResponse(full_enrichment(report)))
    enriched = enrich(report, settings_with_key(), client=client)

    assert enriched.llm.used is True
    assert enriched.overall == report.overall
    assert enriched.axes == report.axes
    assert [f.severity for f in enriched.findings] == [f.severity for f in report.findings]
    assert [f.id for f in enriched.fixes] == [f.id for f in report.fixes]
    assert [f.ratio for f in enriched.fixes] == [f.ratio for f in report.fixes]


def test_explanations_are_replaced_and_marked_as_model_written() -> None:
    report = golden_report()
    enriched = enrich(
        report, settings_with_key(), client=StubClient(StubResponse(full_enrichment(report)))
    )
    for finding in enriched.findings:
        assert finding.explanation == f"Model prose for {finding.id}."
        assert finding.explanation_source is ExplanationSource.LLM


def test_scores_are_identical_with_and_without_the_model() -> None:
    report = golden_report()
    enriched = enrich(
        report, settings_with_key(), client=StubClient(StubResponse(full_enrichment(report)))
    )
    assert enriched.overall.score == report.overall.score
    assert [a.score for a in enriched.axes] == [a.score for a in report.axes]


def test_usage_and_cost_are_recorded() -> None:
    enriched = enrich(
        golden_report(),
        settings_with_key(),
        client=StubClient(StubResponse(full_enrichment(golden_report()))),
    )
    assert enriched.llm.input_tokens == 12_000
    assert enriched.llm.output_tokens == 900
    # 12k input at $5/MTok + 900 output at $25/MTok.
    assert enriched.llm.cost_usd == pytest.approx(0.0825, abs=1e-6)
    assert _cost(1_000_000, 1_000_000) == pytest.approx(30.0)


# ── ids the model invents are discarded ─────────────────────────────────────


def test_unknown_ids_are_dropped_not_merged() -> None:
    report = golden_report()
    rogue = Enrichment(
        summary="s",
        explanations={"F-DOES-NOT-EXIST": "invented"},
        fix_steps={"FIX-NOPE": ["invented"]},
    )
    enriched = enrich(report, settings_with_key(), client=StubClient(StubResponse(rogue)))

    assert all(f.explanation_source is ExplanationSource.TEMPLATE for f in enriched.findings)
    assert "invented" not in enriched.model_dump_json()


def test_partial_coverage_keeps_templates_for_the_rest() -> None:
    report = golden_report()
    first = report.findings[0]
    partial = Enrichment(summary="s", explanations={first.id: "Only this one."}, fix_steps={})
    enriched = enrich(report, settings_with_key(), client=StubClient(StubResponse(partial)))

    by_id = {f.id: f for f in enriched.findings}
    assert by_id[first.id].explanation_source is ExplanationSource.LLM
    for finding in enriched.findings:
        if finding.id != first.id:
            assert finding.explanation_source is ExplanationSource.TEMPLATE


# ── every failure degrades ──────────────────────────────────────────────────


def test_no_api_key_degrades() -> None:
    enriched = enrich(golden_report(), settings_without_key())
    assert enriched.llm.used is False
    assert "ANTHROPIC_API_KEY" in (enriched.llm.fallback_reason or "")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (APITimeoutError(request=httpx2.Request("POST", "https://x")), "APITimeoutError"),
        (
            APIConnectionError(request=httpx2.Request("POST", "https://x")),
            "APIConnectionError",
        ),
        (_status_error(500), "API error 500"),
    ],
)
def test_transport_failures_degrade(error: Exception, expected: str) -> None:
    enriched = enrich(golden_report(), settings_with_key(), client=StubClient(error))
    assert enriched.llm.used is False
    assert expected in (enriched.llm.fallback_reason or "")


def test_rate_limit_degrades() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    error = RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None)
    enriched = enrich(golden_report(), settings_with_key(), client=StubClient(error))
    assert enriched.llm.used is False
    assert "rate limited" in (enriched.llm.fallback_reason or "")


def test_refusal_degrades() -> None:
    response = StubResponse(full_enrichment(golden_report()), stop_reason="refusal")
    enriched = enrich(golden_report(), settings_with_key(), client=StubClient(response))
    assert enriched.llm.used is False
    assert "declined" in (enriched.llm.fallback_reason or "")


def test_malformed_response_degrades() -> None:
    enriched = enrich(
        golden_report(), settings_with_key(), client=StubClient(StubResponse({"nope": 1}))
    )
    assert enriched.llm.used is False
    assert "schema" in (enriched.llm.fallback_reason or "")


def test_missing_structured_output_degrades() -> None:
    enriched = enrich(golden_report(), settings_with_key(), client=StubClient(StubResponse(None)))
    assert enriched.llm.used is False


def test_every_degraded_path_keeps_the_template_text() -> None:
    report = golden_report()
    enriched = enrich(report, settings_with_key(), client=StubClient(_status_error(503)))
    assert [f.explanation for f in enriched.findings] == [f.explanation for f in report.findings]
    assert enriched.stable_payload() == report.stable_payload()


# ── the one failure that raises ─────────────────────────────────────────────


def test_unknown_model_raises_and_names_the_model() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    error = NotFoundError("no", response=httpx2.Response(404, request=request), body=None)
    settings = Settings(  # type: ignore[call-arg]
        ANTHROPIC_API_KEY="sk-ant-not-a-real-key", llm_model="claude-retired-9"
    )
    with pytest.raises(EnrichmentError) as excinfo:
        enrich(golden_report(), settings, client=StubClient(error))
    assert "claude-retired-9" in str(excinfo.value)


# ── the request itself ──────────────────────────────────────────────────────


def test_request_uses_the_configured_model_and_a_cached_stable_prefix() -> None:
    report = golden_report()
    client = StubClient(StubResponse(full_enrichment(report)))
    enrich(report, settings_with_key(), client=client)

    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"]["effort"] == "medium"
    assert call["output_format"] is Enrichment
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_the_cached_prefix_is_identical_across_repositories() -> None:
    # Any repo-specific byte above the breakpoint means the cache never hits.
    first = golden_report()
    second = first.model_copy(update={"repo": first.repo.model_copy(update={"source": "other"})})

    calls = []
    for report in (first, second):
        client = StubClient(StubResponse(full_enrichment(report)))
        enrich(report, settings_with_key(), client=client)
        calls.append(client.messages.calls[0]["system"][0]["text"])

    assert calls[0] == calls[1] == SYSTEM_PROMPT


def test_the_prompt_carries_no_unredacted_secret() -> None:
    # The payload is built from evidence snippets, which are already redacted.
    report = golden_report()
    payload = _payload(report, docs="")
    assert "AKIA" in payload  # the redacted prefix survives
    assert "AKIAIOSFODNN7EXAMPLE" not in payload


def test_system_prompt_forbids_safety_claims() -> None:
    assert "secure" in SYSTEM_PROMPT
    assert "certified" in SYSTEM_PROMPT


def test_a_report_with_nothing_to_explain_skips_the_call() -> None:
    report = golden_report().model_copy(update={"findings": (), "fixes": ()})
    client = StubClient(StubResponse(full_enrichment(report)))
    enriched = enrich(report, settings_with_key(), client=client)
    assert client.messages.calls == []
    assert enriched.llm.used is False
