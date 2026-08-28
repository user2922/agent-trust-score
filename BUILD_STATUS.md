# Build status

Read this, `CLAUDE.md` and `SPEC.md` at the start of every session.

| Prompt | Phase | Status |
|---|---|---|
| 1 | Spec validation & project setup | **DONE** — Checkpoint 1 passed 8/8 |
| 2a | Project setup & toolchain | next |
| 2b | Safety foundation | — |
| 3 | Report schema | — |
| 4 | Inventory & RepoContext | — |
| 5 | Scoring engine | — |
| 6 | Renderers | — |
| 7 | CLI, MCP server, cache | — |
| 8 | Analyzer framework + Tool Surface | — |
| 9 | Blast Radius: secrets | — |
| 10 | Blast Radius: destructive ops | — |
| 11 | Verifiability | — |
| 12 | Context Quality | — |
| 13 | Observability | — |
| 14 | LLM enrichment | — |
| 15 | Packaging, docs, polish | — |
| 16 | Testing, fixtures, CI | — |

## Decisions made in Prompt 1

- **37 checks, not 35.** The draft claimed 35 in five places; the tables always
  held 37 (TS 7, BR 7, VF 8, CQ 8, OB 7). Corrected everywhere. All five axes
  sum to 100, no duplicate ids, every id has a stated pass condition.
- **Determinism is asserted over `stable_payload()`**, not `report.json` bytes.
  `generated_at` and `run_ms` vary by design, so the original wording was
  unsatisfiable.
- **`--fix` is out of v1.** It was in the flag table but no prompt built it.
  Recorded under Stretch.
- **Cache key is commit SHA + schema version**, and a cached `--no-llm` report
  is a miss when enrichment is requested.
- **Empty repos, unclonable repos and oversized repos** now have defined
  behaviour — see the resolved-gaps table in `SPEC.md`.
- `spec.md` was renamed `SPEC_DRAFT.md`: on Windows it collided case-insensitively
  with the `SPEC.md` this prompt writes.

## Environment

Verified present: git 2.53.0 · Python 3.12.10 · uv 0.12.7 · node v25.8.1.
No `ANTHROPIC_API_KEY` configured — not needed until Prompt 14, and the tool
ships usable without one.
