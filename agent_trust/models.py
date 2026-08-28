"""The Report schema -- the shared foundation of the build.

This module owns every shape. No later prompt redefines a field, and no other
module encodes a grade band, an axis order, or a severity rule.

Two invariants are enforced here rather than documented and hoped for:

* An ``Evidence`` snippet that did not come through :mod:`agent_trust.redact`
  fails construction. A caller cannot ship a secret by forgetting to redact.
* Determinism (standing rule D) is asserted over :meth:`Report.stable_payload`,
  which excludes the three fields that vary by design: ``generated_at``,
  ``run_ms`` and ``llm``.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The snippet ceiling lives with the redactor; imported, never retyped.
from agent_trust.redact import MAX_SNIPPET

SCHEMA_VERSION = "1.0"

# The ordering authority for every axis list, table row and report section.
AXES: tuple[tuple[str, str, float], ...] = (
    ("tool_surface", "Tool Surface", 0.2),
    ("blast_radius", "Blast Radius", 0.2),
    ("verifiability", "Verifiability", 0.2),
    ("context_quality", "Context Quality", 0.2),
    ("observability", "Observability", 0.2),
)

AXIS_ORDER: tuple[str, ...] = tuple(key for key, _, _ in AXES)


class AxisKey(StrEnum):
    TOOL_SURFACE = "tool_surface"
    BLAST_RADIUS = "blast_radius"
    VERIFIABILITY = "verifiability"
    CONTEXT_QUALITY = "context_quality"
    OBSERVABILITY = "observability"


class CheckStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - a check status, not a credential
    PARTIAL = "partial"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Letter(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"
    NA = "N/A"


class ExplanationSource(StrEnum):
    LLM = "llm"
    TEMPLATE = "template"


class Frozen(BaseModel):
    """Every model in this schema: immutable, and a typo is an error."""

    model_config = ConfigDict(frozen=True, extra="forbid")


_CONTROL_CHARS = frozenset(chr(c) for c in [*range(0, 9), *range(11, 32), 127])


class Evidence(Frozen):
    """One redacted pointer into the audited repository."""

    path: str
    line: int | None = Field(default=None, ge=1)
    snippet: str = ""
    matcher: str = ""

    @model_validator(mode="after")
    def _snippet_is_safe(self) -> Self:
        if len(self.snippet) > MAX_SNIPPET:
            raise ValueError(
                f"snippet is {len(self.snippet)} chars (max {MAX_SNIPPET}); "
                "build it with redact.snippet()"
            )
        if any(ch in _CONTROL_CHARS for ch in self.snippet):
            raise ValueError("snippet contains a control character; build it with redact.snippet()")
        return self


class CheckResult(Frozen):
    """The outcome of one of the 37 checks."""

    id: str
    title: str
    status: CheckStatus
    weight: int = Field(ge=0, le=100)
    earned: float = Field(ge=0)
    detail: str = ""
    evidence: tuple[Evidence, ...] = ()

    @model_validator(mode="after")
    def _earned_matches_status(self) -> Self:
        if self.earned > self.weight:
            raise ValueError(f"{self.id}: earned {self.earned} exceeds weight {self.weight}")
        expected = {
            CheckStatus.PASS: float(self.weight),
            CheckStatus.PARTIAL: self.weight / 2,
            CheckStatus.FAIL: 0.0,
            CheckStatus.NOT_APPLICABLE: 0.0,
        }[self.status]
        if self.earned != expected:
            raise ValueError(
                f"{self.id}: status {self.status} requires earned {expected}, got {self.earned}"
            )
        return self


class AxisScore(Frozen):
    """One axis: its score, its letter, and the checks behind them."""

    key: AxisKey
    name: str
    score: int | None = Field(default=None, ge=0, le=100)
    letter: Letter
    weight: float
    checks: tuple[CheckResult, ...] = ()

    @model_validator(mode="after")
    def _null_score_is_not_applicable(self) -> Self:
        if self.score is None and self.letter is not Letter.NA:
            raise ValueError(f"{self.key}: a null score requires letter N/A, got {self.letter}")
        if self.score is not None and self.letter is Letter.NA:
            raise ValueError(f"{self.key}: letter N/A requires a null score, got {self.score}")
        return self


class Overall(Frozen):
    """The headline grade, after the cap rule."""

    score: int | None = Field(default=None, ge=0, le=100)
    letter: Letter
    mean: int | None = Field(default=None, ge=0, le=100)
    capped: bool = False
    cap_reason: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.score is None and self.letter is not Letter.NA:
            raise ValueError("a null overall score requires letter N/A")
        if self.capped and not self.cap_reason:
            raise ValueError("capped requires a cap_reason naming the axis")
        return self


class Finding(Frozen):
    """One thing wrong, with evidence a human can go look at."""

    id: str
    check_id: str
    axis: AxisKey
    severity: Severity
    title: str
    evidence: tuple[Evidence, ...] = ()
    explanation: str = ""
    explanation_source: ExplanationSource = ExplanationSource.TEMPLATE


class Fix(Frozen):
    """One remediation, ranked by risk reduction per hour."""

    id: str
    finding_ids: tuple[str, ...]
    axis: AxisKey
    title: str
    steps: tuple[str, ...] = ()
    risk_reduction: int = Field(ge=0)
    effort_minutes: int = Field(gt=0)
    ratio: float = Field(ge=0)
    patch: str | None = None


class LlmUsage(Frozen):
    """What the enrichment call cost, or why it did not happen."""

    used: bool = False
    model: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    fallback_reason: str | None = None


class RepoInfo(Frozen):
    """What was audited, and how much of it."""

    source: str
    commit_sha: str | None = None
    default_branch: str | None = None
    file_count: int = Field(default=0, ge=0)
    analyzed_file_count: int = Field(default=0, ge=0)
    bytes_scanned: int = Field(default=0, ge=0)
    languages: dict[str, int] = Field(default_factory=dict)
    truncated: bool = False
    skipped: dict[str, int] = Field(default_factory=dict)


class Report(Frozen):
    """A complete audit."""

    schema_version: str = SCHEMA_VERSION
    generated_at: datetime
    run_ms: int = Field(ge=0)
    repo: RepoInfo
    overall: Overall
    axes: Annotated[tuple[AxisScore, ...], Field(min_length=5, max_length=5)]
    findings: tuple[Finding, ...] = ()
    fixes: tuple[Fix, ...] = ()
    llm: LlmUsage = LlmUsage()

    @model_validator(mode="after")
    def _axes_in_canonical_order(self) -> Self:
        keys = tuple(axis.key.value for axis in self.axes)
        if keys != AXIS_ORDER:
            raise ValueError(f"axes must be in AXES order {AXIS_ORDER}, got {keys}")
        return self

    @model_validator(mode="after")
    def _fixes_reference_real_findings(self) -> Self:
        known = {finding.id for finding in self.findings}
        for fix in self.fixes:
            unknown = set(fix.finding_ids) - known
            if unknown:
                raise ValueError(f"fix {fix.id} references unknown finding(s): {sorted(unknown)}")
        return self

    def stable_payload(self) -> dict[str, Any]:
        """The report minus everything that varies between identical runs.

        Determinism (rule D) is asserted over this, never over ``report.json``
        bytes: ``generated_at`` and ``run_ms`` change every run by design, and
        ``llm`` changes when enrichment is on.
        """
        data = self.model_dump(mode="json")
        for volatile in ("generated_at", "run_ms", "llm"):
            data.pop(volatile, None)
        return data

    def to_json(self) -> str:
        """Serialize with sorted keys and a fixed datetime format."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, indent=2)

    def stable_json(self) -> str:
        """The stable payload as canonical JSON -- what determinism tests compare."""
        return json.dumps(self.stable_payload(), sort_keys=True, indent=2)


def load_report(document: str) -> Report:
    """Parse a serialized report, refusing a version this build cannot read.

    Raises:
        ValueError: the document declares a different ``schema_version``.
            Coercing a mismatched version would silently mis-grade a repo.
    """
    data = json.loads(document)
    found = data.get("schema_version")
    if found != SCHEMA_VERSION:
        raise ValueError(f"schema_version {found!r} is not {SCHEMA_VERSION!r}; refusing to coerce")
    return Report.model_validate(data)
