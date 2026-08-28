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

from agent_trust.inventory import RepoContext
from agent_trust.models import AXIS_ORDER, AxisKey, CheckResult

Analyzer = Callable[[RepoContext], Sequence[CheckResult]]

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


__all__ = ["REGISTRY", "Analyzer", "register", "registered_axes"]
