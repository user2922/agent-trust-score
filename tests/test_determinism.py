"""Rule D: the same commit yields the same numbers.

Asserted over ``stable_payload()``, never over ``report.json`` bytes --
``generated_at`` and ``run_ms`` vary every run by design, and comparing the file
would fail for reasons that have nothing to do with determinism.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from agent_trust.config import Settings
from agent_trust.enrich import Enrichment
from agent_trust.models import Report
from agent_trust.pipeline import audit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_fixtures import build_clean, build_ugly  # noqa: E402


class StubUsage:
    input_tokens = 1000
    output_tokens = 200


class StubResponse:
    stop_reason = "end_turn"
    usage = StubUsage()

    def __init__(self, parsed: Enrichment) -> None:
        self.parsed_output = parsed


class StubClient:
    """Returns model prose for every finding and fix in the report."""

    def __init__(self, report: Report) -> None:
        enrichment = Enrichment(
            summary="Stubbed summary.",
            explanations={f.id: f"Stubbed prose for {f.id}." for f in report.findings},
            fix_steps={fix.id: ["Stubbed step."] for fix in report.fixes},
        )
        self.messages = _StubMessages(StubResponse(enrichment))


class _StubMessages:
    def __init__(self, response: StubResponse) -> None:
        self.response = response

    def parse(self, **_kwargs: Any) -> StubResponse:
        return self.response


@pytest.fixture(params=[build_clean, build_ugly], ids=["clean", "ugly"])
def fixture_repo(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return request.param(tmp_path_factory.mktemp("det"))


def audit_twice(root: Path) -> tuple[Report, Report]:
    first = audit(str(root), use_llm=False, use_cache=False, timeout=120)
    second = audit(str(root), use_llm=False, use_cache=False, timeout=120)
    return first, second


def test_two_runs_produce_identical_stable_payloads(fixture_repo: Path) -> None:
    first, second = audit_twice(fixture_repo)
    assert first.stable_json() == second.stable_json()


def test_the_volatile_fields_really_do_vary(fixture_repo: Path) -> None:
    """The other half of the claim.

    If generated_at were constant the payload comparison above would be trivially
    true, and determinism would be untested.
    """
    first, second = audit_twice(fixture_repo)
    payload = first.stable_payload()
    assert "generated_at" not in payload
    assert "run_ms" not in payload
    assert "llm" not in payload
    # The serialized files DO differ, which is what makes the payload
    # comparison above a real assertion rather than a tautology.
    assert first.to_json() != second.to_json()


def test_findings_and_fixes_keep_their_order(fixture_repo: Path) -> None:
    first, second = audit_twice(fixture_repo)
    assert [f.id for f in first.findings] == [f.id for f in second.findings]
    assert [f.id for f in first.fixes] == [f.id for f in second.fixes]
    assert [f.ratio for f in first.fixes] == [f.ratio for f in second.fixes]


def test_the_model_changes_prose_and_nothing_else(fixture_repo: Path) -> None:
    """With and without enrichment, every number is identical."""
    from agent_trust.enrich import enrich

    plain = audit(str(fixture_repo), use_llm=False, use_cache=False, timeout=120)
    settings = Settings(ANTHROPIC_API_KEY="sk-ant-not-a-real-key")  # type: ignore[call-arg]
    enriched = enrich(plain, settings, client=StubClient(plain))

    assert enriched.stable_payload()["overall"] == plain.stable_payload()["overall"]
    assert enriched.stable_payload()["axes"] == plain.stable_payload()["axes"]
    assert [f.severity for f in enriched.findings] == [f.severity for f in plain.findings]
    assert [f.id for f in enriched.fixes] == [f.id for f in plain.fixes]

    if plain.findings:
        assert enriched.findings[0].explanation != plain.findings[0].explanation


def test_evidence_line_numbers_are_stable(fixture_repo: Path) -> None:
    first, second = audit_twice(fixture_repo)

    def locations(report: Report) -> list[tuple[str, int | None]]:
        return [(e.path, e.line) for f in report.findings for e in f.evidence]

    assert locations(first) == locations(second)
