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
    # cross-batch shared-key conflicts checked for all three manifest tables
    assert src.count("shared factor keys") == 1 and src.count("shared action keys") == 1
    # pre-image existence checked for factor/action update/delete ops
    assert "factor manifest keys lack" in src and "action manifest keys lack" in src
    # post-rollback verification on all three tables
    assert "post-rollback factor diffs" in src and "post-rollback action diffs" in src
    # no-manifest batch refuses --apply
    assert "refusing to auto-apply" in src
    # post-rollback nonzero diffs abort the transaction
    assert 'fail(f"post-rollback verification failed' in src
    # dry-run default, explicit --apply to commit
    assert 'apply = "--apply" in sys.argv' in src
    assert "dry-run only" in src


# --- downstream rebuild checkpoint semantics (version-aware, incremental) ---

def _import_downstream():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "r2_downstream_rebuild",
        SCRIPTS / "r2_downstream_rebuild.py")
    mod = importlib.util.module_from_spec(spec)
    import sys as _s
    _s.path.insert(0, "src")
    spec.loader.exec_module(mod)
    return mod


def test_minute_pending_new_asset_and_sig_change():
    m = _import_downstream()
    groups = {"CN:A": [{"freq": "5min", "source": "baostock"}],
              "CN:B": [{"freq": "5min", "source": "baostock"}]}
    sigs = {"CN:A": "100:t1", "CN:B": "50:t2"}
    raw_sigs = {"CN:A|5min|baostock": "r1",
                "CN:B|5min|baostock": "r2"}
    # asset A done at old sig -> pending (repaired factors changed)
    # asset B never done -> pending
    ledger = {"CN:A|5min|baostock": {"factor_sig": "99:t0",
                                    "raw_sig": "r1"}}
    todo = m.decide_minute_pending(groups, sigs, raw_sigs, ledger)
    assert set(todo) == {"CN:A|5min|baostock", "CN:B|5min|baostock"}
    # A at current factor+raw sigs -> only B pending
    ledger["CN:A|5min|baostock"] = {"factor_sig": "100:t1",
                                    "raw_sig": "r1"}
    todo = m.decide_minute_pending(groups, sigs, raw_sigs, ledger)
    assert set(todo) == {"CN:B|5min|baostock"}
    # raw minute bars re-ingested for A (raw sig bump) -> A pending again
    raw_sigs["CN:A|5min|baostock"] = "r1b"
    todo = m.decide_minute_pending(groups, sigs, raw_sigs, ledger)
    assert set(todo) == {"CN:A|5min|baostock", "CN:B|5min|baostock"}
    # new asset C joins later -> enqueued despite prior completions
    raw_sigs["CN:A|5min|baostock"] = "r1"
    groups["CN:C"] = [{"freq": "5min", "source": "baostock"}]
    sigs["CN:C"] = "10:t3"
    raw_sigs["CN:C|5min|baostock"] = "r3"
    todo = m.decide_minute_pending(groups, sigs, raw_sigs, ledger)
    assert set(todo) == {"CN:B|5min|baostock", "CN:C|5min|baostock"}


def test_feature_pending_per_asset_date_not_date_scoped():
    m = _import_downstream()
    assets, dates = ["CN:A", "CN:B"], ["2026-10-19", "2026-10-20"]
    sigs = {"CN:A": "s1", "CN:B": "s2"}
    # date fully computed for A only -> B must still be pending on both dates
    ledger = {"2026-10-19|CN:A": {"factor_sig": "s1"},
              "2026-10-20|CN:A": {"factor_sig": "s1"}}
    todo = m.decide_feature_pending(assets, dates, sigs, ledger)
    assert set(todo) == {"2026-10-19|CN:B", "2026-10-20|CN:B"}
    # A's factors re-repaired (sig bump) -> A re-enters pending
    sigs["CN:A"] = "s1b"
    todo = m.decide_feature_pending(assets, dates, sigs, ledger)
    assert set(todo) == {"2026-10-19|CN:A", "2026-10-20|CN:A",
                        "2026-10-19|CN:B", "2026-10-20|CN:B"}


def test_window_merge_state_machine():
    src = (SCRIPTS / "r2_merge_sets.py").read_text()
    # atomic replace, disjoint check, reclassification + verdict moves
    assert "os.replace" in src and "AUTO_RELEASABLE" in src
    assert '"CONFIRMED_DIRTY", "review_verified"' in src
    assert "FATAL: sets overlap" in src
    win = (SCRIPTS / "r2_baostock_window.sh").read_text()
    # real child-process check before baostock use, then merge step
    assert "pgrep -f 'r2_repair_batch.py'" in win
    assert "r2_merge_sets.py" in win


def test_review_verify_date_coverage():
    src = (SCRIPTS / "r2_review_verify.py").read_text()
    # stored-vs-live date comparison for all three series
    assert "stored_dates - live_d" in src
    assert "live_date_sets_diverge_across_adjust_types" in src
    assert "extra_live" in src
