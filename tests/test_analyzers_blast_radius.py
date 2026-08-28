"""BR-04..BR-07: the judgment-adjacent checks.

Detection stays static and deterministic. The model may later explain a finding
(rule B); it may not create, remove or re-grade one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_trust.acquire import read_facts
from agent_trust.analyzers.blast_radius import (
    check_admin_credential_reach,
    check_destructive_ops_guarded,
    check_ownership_config,
    check_side_effect_switch,
    scan_destructive_ops,
)
from agent_trust.analyzers.patterns import GUARD_WINDOW_LINES
from agent_trust.inventory import RepoContext, build_context
from agent_trust.limits import Budget
from agent_trust.models import CheckStatus


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


def make_repo(tmp_path: Path, files: dict[str, str]) -> RepoContext:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _git(["init", "-q", "-b", "master"], root)
        _git(["config", "user.email", "t@example.com"], root)
        _git(["config", "user.name", "t"], root)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(["add", "-A", "-f"], root)
    _git(["commit", "-qm", "fixture repository for the blast radius tests"], root)
    return build_context(
        root=root,
        source=str(root),
        facts=read_facts(root),
        budget=Budget(max_files=20_000, max_bytes=209_715_200),
    )


# ── BR-04 · one case per operation family ───────────────────────────────────

UNGUARDED = {
    "SQL DROP": "cursor.execute('DROP TABLE users')\n",
    "SQL TRUNCATE": "cursor.execute('TRUNCATE TABLE sessions')\n",
    "unqualified DELETE": "cursor.execute('DELETE FROM accounts;')\n",
    "migration runner": "subprocess.run(['prisma', 'migrate', 'deploy'])\n",
    "recursive delete": "shutil.rmtree(target)\n",
    "bulk delete": "await prisma.user.deleteMany()\n",
    "payment capture": "stripe.charges.create(amount=100)\n",
    "outbound email": "resend.emails.send(payload)\n",
}


@pytest.mark.parametrize(("family", "code"), sorted(UNGUARDED.items()))
def test_every_operation_family_is_detected(tmp_path: Path, family: str, code: str) -> None:
    ctx = make_repo(tmp_path / family.replace(" ", "_"), {"task.py": code})
    hits = scan_destructive_ops(ctx)
    assert hits, f"{family} was not detected"
    assert hits[0].family == family
    assert hits[0].guard is None


# ── BR-04 · one case per guard kind ─────────────────────────────────────────

GUARDS = {
    "dry-run flag": "if args.dry_run:\n    return\nshutil.rmtree(target)\n",
    "force flag": "if not args.force:\n    return\nshutil.rmtree(target)\n",
    "confirmation prompt": "if not typer.confirm('Delete?'):\n    return\nshutil.rmtree(target)\n",
    "environment gate": (
        "if os.environ['ALLOW_DESTRUCTIVE'] != '1':\n    return\nshutil.rmtree(x)\n"
    ),
}


@pytest.mark.parametrize(("guard", "code"), sorted(GUARDS.items()))
def test_every_guard_kind_is_recognised(tmp_path: Path, guard: str, code: str) -> None:
    ctx = make_repo(tmp_path / guard.replace(" ", "_"), {"task.py": code})
    outcome = check_destructive_ops_guarded(ctx)
    assert outcome.status is CheckStatus.PASS, f"{guard} was not recognised"
    assert guard in outcome.detail


def test_unguarded_operation_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"task.py": "shutil.rmtree(target)\n"})
    outcome = check_destructive_ops_guarded(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert outcome.evidence
    assert "dry-run" in outcome.detail


def test_removing_the_guard_flips_the_result(tmp_path: Path) -> None:
    guarded = make_repo(
        tmp_path / "g", {"t.py": "if args.dry_run:\n    return\nshutil.rmtree(x)\n"}
    )
    bare = make_repo(tmp_path / "b", {"t.py": "shutil.rmtree(x)\n"})
    assert check_destructive_ops_guarded(guarded).status is CheckStatus.PASS
    assert check_destructive_ops_guarded(bare).status is CheckStatus.FAIL


def test_some_guarded_some_not_is_partial(tmp_path: Path) -> None:
    code = (
        "def safe():\n    if args.dry_run:\n        return\n    shutil.rmtree(a)\n\n"
        + "\n" * (GUARD_WINDOW_LINES + 5)
        + "def risky():\n    prisma.user.deleteMany()\n"
    )
    ctx = make_repo(tmp_path, {"task.py": code})
    outcome = check_destructive_ops_guarded(ctx)
    assert outcome.status is CheckStatus.PARTIAL
    assert "1 of 2" in outcome.detail


def test_a_guard_beyond_the_window_does_not_count(tmp_path: Path) -> None:
    inside = "if args.dry_run:\n    pass\n" + "\n" * (GUARD_WINDOW_LINES - 4) + "shutil.rmtree(x)\n"
    outside = (
        "if args.dry_run:\n    pass\n" + "\n" * (GUARD_WINDOW_LINES + 4) + "shutil.rmtree(x)\n"
    )

    near = make_repo(tmp_path / "near", {"t.py": inside})
    far = make_repo(tmp_path / "far", {"t.py": outside})
    assert check_destructive_ops_guarded(near).status is CheckStatus.PASS
    assert check_destructive_ops_guarded(far).status is CheckStatus.FAIL


def test_a_repo_with_no_destructive_operations_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"a.py": "def add(x, y):\n    return x + y\n"})
    assert check_destructive_ops_guarded(ctx).status is CheckStatus.PASS


def test_delete_with_a_where_clause_is_not_flagged(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"q.py": "db.execute('DELETE FROM sessions WHERE id = ?', [i])\n"})
    assert scan_destructive_ops(ctx) == []


# ── BR-05 · admin credentials by path ───────────────────────────────────────


def test_admin_key_in_a_component_fails_and_states_the_method(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"src/components/Panel.tsx": "const k = SUPABASE_SERVICE_ROLE_KEY\n"})
    outcome = check_admin_credential_reach(ctx)
    assert outcome.status is CheckStatus.FAIL
    assert "path convention" in outcome.detail


def test_the_same_reference_in_scripts_does_not_fail(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"scripts/seed.py": "key = SUPABASE_SERVICE_ROLE_KEY\n"})
    assert check_admin_credential_reach(ctx).status is CheckStatus.PASS


def test_clean_repo_passes_and_still_states_the_method(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"src/components/Panel.tsx": "const k = props.token\n"})
    outcome = check_admin_credential_reach(ctx)
    assert outcome.status is CheckStatus.PASS
    assert "path convention" in outcome.detail


# ── BR-06 · side effects behind a switch ────────────────────────────────────


def test_unswitched_payment_call_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"pay.py": "stripe.charges.create(amount=100)\n"})
    assert check_side_effect_switch(ctx).status is CheckStatus.FAIL


def test_env_gated_payment_call_passes(tmp_path: Path) -> None:
    ctx = make_repo(
        tmp_path,
        {
            "pay.py": (
                "import os\n\nkey = os.environ['STRIPE_KEY']\nstripe.charges.create(amount=1)\n"
            )
        },
    )
    assert check_side_effect_switch(ctx).status is CheckStatus.PASS


def test_no_side_effects_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"a.py": "x = 1\n"})
    assert check_side_effect_switch(ctx).status is CheckStatus.PASS


# ── BR-07 · ownership ───────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["CODEOWNERS", ".github/CODEOWNERS"])
def test_codeowners_passes(tmp_path: Path, path: str) -> None:
    ctx = make_repo(tmp_path / path.replace("/", "_"), {path: "* @team\n"})
    assert check_ownership_config(ctx).status is CheckStatus.PASS


def test_protection_config_passes(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {".mergify.yml": "pull_request_rules: []\n"})
    assert check_ownership_config(ctx).status is CheckStatus.PASS


def test_no_ownership_config_fails(tmp_path: Path) -> None:
    ctx = make_repo(tmp_path, {"a.py": "x = 1\n"})
    assert check_ownership_config(ctx).status is CheckStatus.FAIL


# ── the axis is complete ────────────────────────────────────────────────────


def test_all_seven_checks_run_and_none_raise(tmp_path: Path) -> None:
    from agent_trust.analyzers.blast_radius import run

    ctx = make_repo(tmp_path, {"a.py": "x = 1\n"})
    outcomes = run(ctx)
    assert [outcome.id for outcome in outcomes] == [
        "BR-01",
        "BR-02",
        "BR-03",
        "BR-04",
        "BR-05",
        "BR-06",
        "BR-07",
    ]
    assert sum(outcome.weight for outcome in outcomes) == 100
