# File list — every file, by the prompt that creates it

Derived from `SPEC.md` § File Layout. A file appears exactly once. `redact.py`
lands at Prompt 2b, ahead of every module that reads repository content — that
ordering is a safety constraint, not a preference.

| Prompt | Files |
|---|---|
| **1** | `CLAUDE.md` · `SPEC.md` · `docs/FILE_LIST.md` · `BUILD_STATUS.md` |
| **2a** | `pyproject.toml` · `uv.lock` · `agent_trust/__init__.py` · `agent_trust/py.typed` · `agent_trust/config.py` · `agent_trust/logging.py` · `agent_trust/redact.py` · `agent_trust/errors.py` · `.env.example` · `.gitignore` · `LICENSE` · `scripts/check_secrets.sh` · `scripts/check_all.sh` · `Makefile` · `tests/test_config.py` · `tests/test_redact.py` |
| **2b** | `agent_trust/redact.py` (adds `snippet`) · `agent_trust/errors.py` (adds acquisition errors) · `agent_trust/acquire.py` · `agent_trust/limits.py` · `tests/test_acquire.py` |
| **3** | `agent_trust/models.py` · `tests/test_models.py` |
| **4** | `agent_trust/inventory.py` · `tests/test_inventory.py` |
| **5** | `agent_trust/scoring/__init__.py` · `grades.py` · `findings.py` · `effort.py` · `fixes.py` · `tests/test_scoring.py` |
| **6** | `agent_trust/render/terminal.py` · `markdown.py` · `html.py` · `render/templates/report.md.j2` · `report.html.j2` · `tests/fixtures/golden_report.json` · `tests/test_render.py` |
| **7** | `agent_trust/pipeline.py` · `agent_trust/cache.py` · `agent_trust/cli.py` · `agent_trust/mcp_server.py` · `tests/test_cli.py` · `tests/test_mcp.py` |
| **8** | `agent_trust/analyzers/__init__.py` · `patterns.py` · `tool_surface.py` · `tests/test_analyzers_tool_surface.py` |
| **9** | `agent_trust/analyzers/entropy.py` · `blast_radius.py` (BR-01/02/03) · `tests/test_analyzers_secrets.py` |
| **10** | `blast_radius.py` completed (BR-04/05/06/07) · `tests/test_analyzers_blast_radius.py` |
| **11** | `agent_trust/analyzers/verifiability.py` · `tests/test_analyzers_verifiability.py` |
| **12** | `agent_trust/analyzers/context_quality.py` · `tests/test_analyzers_context_quality.py` |
| **13** | `agent_trust/analyzers/observability.py` · `tests/test_analyzers_observability.py` |
| **14** | `agent_trust/enrich.py` · `tests/test_enrich.py` |
| **15** | `LICENSE` · `README.md` · `docs/PRIVACY.md` · `docs/CHECKS.md` |
| **16** | `tests/fixtures/clean-repo/**` · `tests/fixtures/ugly-repo/**` · `scripts/build_fixtures.py` · `tests/test_determinism.py` · `tests/test_acceptance.py` · `.github/workflows/ci.yml` |

## Ordering constraints that must hold

1. `redact.py` (2b) precedes `inventory.py` (4) and every analyzer (8–13).
2. `models.py` (3) precedes everything that constructs a `Report`.
3. `scoring/` (5) precedes `pipeline.py` (7) — the CLI cannot render without it.
4. `patterns.py` (8) precedes every analyzer that matches repo content.
5. `enrich.py` (14) is last of the runtime modules: nothing depends on it, which
   is what makes `--no-llm` a complete product rather than a degraded one.

## Files deliberately absent

No `auth/`, no `db/`, no migrations, no Stripe module, no cookie banner, no
`--fix` implementation. Each is recorded as N/A with its reason in `CLAUDE.md`
or as stretch in `SPEC.md`. An absent file with a stated reason is a decision; an
absent file with no reason is a gap.
