"""The analyzer registry -- the contract every axis analyzer implements.

An analyzer takes a :class:`~agent_trust.inventory.RepoContext` and returns check
results. It receives that object and nothing else: no config, no network, no
environment, no clock. An analyzer therefore *cannot* reach outside the
repository it was handed, which is what makes rule D (determinism) enforceable
rather than aspirational.

Prompt 7 defines the registry so the pipeline has something to iterate. Prompt 8
adds the CheckSpec tables and the first analyzer; 9 through 13 add the rest.
While the registry is empty an audit reports five N/A axes, which is honest --
an unmeasured axis is not a failing one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from agent_trust.inventory import RepoContext
from agent_trust.models import AXIS_ORDER, AxisKey, CheckResult, CheckStatus, Evidence
from agent_trust.redact import snippet

Analyzer = Callable[[RepoContext], Sequence[CheckResult]]

AXIS_TOTAL = 100


@dataclass(frozen=True)
class CheckSpec:
    """The identity of one check: what it is called and what it is worth."""

    id: str
    title: str
    weight: int


def assert_weights(axis: AxisKey, specs: Sequence[CheckSpec]) -> None:
    """Fail at import when an axis does not total 100.

    A mistyped weight would skew every grade on that axis silently, so this is
    checked when the module loads rather than when a report is rendered.
    """
    total = sum(spec.weight for spec in specs)
    if total != AXIS_TOTAL:
        raise ValueError(f"{axis.value} weights sum to {total}, expected {AXIS_TOTAL}")


def result(
    spec: CheckSpec,
    status: CheckStatus,
    detail: str = "",
    evidence: Sequence[Evidence] = (),
) -> CheckResult:
    """Build a CheckResult with the earned points implied by its status."""
    earned = {
        CheckStatus.PASS: float(spec.weight),
        CheckStatus.PARTIAL: spec.weight / 2,
        CheckStatus.FAIL: 0.0,
        CheckStatus.NOT_APPLICABLE: 0.0,
    }[status]
    return CheckResult(
        id=spec.id,
        title=spec.title,
        status=status,
        weight=spec.weight,
        earned=earned,
        detail=detail,
        evidence=tuple(evidence),
    )


def evidence_at(ctx: RepoContext, path: str, line_number: int, start: int, end: int) -> Evidence:
    """Evidence for a match, with the snippet built through the redactor."""
    lines = ctx.read_lines(path)
    line = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
    return Evidence(path=path, line=line_number, snippet=snippet(line, start, end))


def evidence_for_path(path: str, matcher: str = "") -> Evidence:
    """Evidence that names a file without quoting from it."""
    return Evidence(path=path, matcher=matcher)


def searched(*what: str) -> str:
    """The detail line for a failed check: say what was looked for.

    A finding with no statement of what was searched is an accusation rather
    than a finding, and the reader cannot tell whether to disagree with it.
    """
    return "Searched for: " + "; ".join(what) + "."


# Insertion order is canonical axis order; see register().
REGISTRY: dict[AxisKey, Analyzer] = {}


def register(key: AxisKey, analyzer: Analyzer) -> None:
    """Register the analyzer for one axis.

    Raises:
        ValueError: the axis already has an analyzer. Two analyzers for one axis
            would make the winner depend on import order.
    """
    if key in REGISTRY:
        raise ValueError(f"{key.value} already has a registered analyzer")
    REGISTRY[key] = analyzer
    # Keep iteration in AXES order regardless of which module imported first.
    for axis in AXIS_ORDER:
        existing = REGISTRY.pop(AxisKey(axis), None)
        if existing is not None:
            REGISTRY[AxisKey(axis)] = existing


def registered_axes() -> tuple[AxisKey, ...]:
    """The axes that currently have an analyzer, in canonical order."""
    return tuple(REGISTRY)


__all__ = [
    "AXIS_TOTAL",
    "REGISTRY",
    "Analyzer",
    "CheckSpec",
    "assert_weights",
    "evidence_at",
    "evidence_for_path",
    "register",
    "registered_axes",
    "result",
    "searched",
]


# Imported for their registration side effects. This sits at the BOTTOM of the
# module on purpose: each analyzer imports the helpers defined above, so moving
# these up turns the dependency into a cycle.
from agent_trust.analyzers import (  # noqa: E402, F401
    blast_radius,
    context_quality,
    observability,
    tool_surface,
    verifiability,
)
