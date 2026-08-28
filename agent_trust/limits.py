"""Wall-clock and size budgets for a single run.

A budget being exhausted is not an error: the inventory stops and the report
carries ``truncated``. A *deadline* being exhausted is an error, because the
caller asked for an answer within a time and cannot have one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agent_trust.errors import TimeoutExceeded


@dataclass(frozen=True)
class Deadline:
    """A wall-clock budget checked between pipeline stages."""

    seconds: float
    started: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        """Seconds left; negative once the budget is spent."""
        return self.seconds - (time.monotonic() - self.started)

    def expired(self) -> bool:
        return self.remaining() <= 0

    def check(self, stage: str) -> None:
        """Raise if the budget is spent.

        Args:
            stage: named in the message so the user learns where time went.
        """
        if self.expired():
            raise TimeoutExceeded(
                f"Run exceeded its {self.seconds:g}s budget during {stage}. "
                f"Raise it with --timeout."
            )


@dataclass
class Budget:
    """File-count and byte-count ceilings for the inventory.

    Mutable by design: the inventory consumes it as it walks. Exceeding either
    ceiling sets ``truncated`` and records why files were skipped, so a partial
    audit can never be presented as a complete one.
    """

    max_files: int
    max_bytes: int
    files_used: int = 0
    bytes_used: int = 0
    truncated: bool = False
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        """Record one skipped file under a named reason."""
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def accept(self, size: int) -> bool:
        """Claim room for one file of ``size`` bytes.

        Returns:
            True if the file fits and was charged to the budget. False if a
            ceiling was reached, in which case ``truncated`` is set.
        """
        if self.files_used >= self.max_files:
            self.truncated = True
            self.skip("budget_files")
            return False
        if self.bytes_used + size > self.max_bytes:
            self.truncated = True
            self.skip("budget_bytes")
            return False
        self.files_used += 1
        self.bytes_used += size
        return True
