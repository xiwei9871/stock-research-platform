"""Focused checks for R2 v3/v4 scripts: state machine semantics and
manifest-ownership SQL (no baostock / DB needed)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "r2_revision"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


def test_repair_state_machine_gates():
    """OK / OK_ALREADY_REPAIRED must both continue; UNCERTAIN/NO_ROWS must not."""
    src = (SCRIPTS / "r2_repair_batch.py").read_text()
    assert 'if gate not in ("OK", "OK_ALREADY_REPAIRED")' in src
    assert "OK_ALREADY_REPAIRED" in src
    # setdefaulttimeout must run before baostock login
    assert src.index("socket.setdefaulttimeout") < src.index("login = bs.login()")


def test_repair_writes_manifest_in_same_transaction():
    src = (SCRIPTS / "r2_repair_batch.py").read_text()
    assert "backup.r2_write_manifest" in src
    assert "INSERT INTO backup.r2_write_manifest" in src
    # op labels distinguish pre-existing keys from new rows
    assert '"update" if' in src and '"insert"' in src


def test_rollback_manifest_ownership():
    src = (SCRIPTS / "r2_rollback_batch.py").read_text()
    # conflict guards before any write
    assert "CONFLICT" in src and "sys.exit(1)" in src
    # manifest-owned restore + delete, not asset-wide
    assert "m.op='update'" in src and "m.op='insert'" in src
    # factor/action manifests also enforced
    assert "r2_write_manifest_factor" in src and "r2_write_manifest_action" in src
    # no-manifest batch refuses --apply
    assert "refusing to auto-apply" in src
    # post-rollback nonzero diffs abort the transaction
    assert 'fail(f"post-rollback verification failed' in src
    # dry-run default, explicit --apply to commit
    assert 'apply = "--apply" in sys.argv' in src
    assert "dry-run only" in src


def test_review_verify_date_coverage():
    src = (SCRIPTS / "r2_review_verify.py").read_text()
    # stored-vs-live date comparison for all three series
    assert "stored_dates - live_d" in src
    assert "live_date_sets_diverge_across_adjust_types" in src
    assert "extra_live" in src
