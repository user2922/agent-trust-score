"""Generate docs/CHECKS.md from the CheckSpec tables.

Generated, never hand-written: a reference that is typed by hand drifts from the
code the first time a weight changes, and then it is worse than no reference.
`tests/test_docs.py` asserts the committed file matches what this produces.

Usage:
    uv run python scripts/generate_checks_doc.py          # write the file
    uv run python scripts/generate_checks_doc.py --check  # exit 1 if stale
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_trust.analyzers import (
    blast_radius,
    context_quality,
    observability,
    tool_surface,
    verifiability,
)
from agent_trust.models import AXES
from agent_trust.scoring.effort import EFFORT_MINUTES
from agent_trust.scoring.findings import WHY
from agent_trust.scoring.fixes import STEPS

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "CHECKS.md"

MODULES = {
    "tool_surface": tool_surface,
    "blast_radius": blast_radius,
    "verifiability": verifiability,
    "context_quality": context_quality,
    "observability": observability,
}

HEADER = """# The checks

Generated from the `CheckSpec` tables by `scripts/generate_checks_doc.py`.
Do not edit by hand — run the script.

Every axis totals 100 points, asserted at import time. The overall grade is the
mean of the scored axes, except that any axis below 40 caps the overall at 70,
and a committed secret forces `blast_radius` to at most 39.

A check that cannot apply to a repository returns `not_applicable` and leaves
the axis denominator, so it is never scored as a failure.
"""


def render() -> str:
    """The full reference document."""
    lines = [HEADER]
    total = 0

    for key, name, _weight in AXES:
        module = MODULES[key]
        specs = module.SPECS
        total += len(specs)
        lines.append(f"\n## {name}\n")
        lines.append("| ID | Check | Weight | Effort | Why it matters |")
        lines.append("|---|---|---:|---:|---|")
        for spec in specs:
            minutes = EFFORT_MINUTES[spec.id]
            effort = f"{minutes}m" if minutes < 60 else f"{minutes // 60}h"
            lines.append(
                f"| `{spec.id}` | {spec.title} | {spec.weight} | {effort} | {WHY[spec.id]} |"
            )
        lines.append(f"\nAxis total: {sum(spec.weight for spec in specs)}.\n")
        lines.append("<details><summary>How to fix each one</summary>\n")
        for spec in specs:
            steps = "".join(f"\n  - {step}" for step in STEPS[spec.id])
            lines.append(f"- **{spec.id}**{steps}")
        lines.append("\n</details>")

    lines.append(f"\n---\n\n{total} checks across {len(AXES)} axes.\n")
    return "\n".join(lines)


def main() -> int:
    document = render()
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != document:
            print("docs/CHECKS.md is stale; run scripts/generate_checks_doc.py", file=sys.stderr)
            return 1
        print("docs/CHECKS.md is current")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(document, encoding="utf-8", newline="")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
