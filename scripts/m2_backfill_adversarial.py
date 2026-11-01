#!/usr/bin/env python3
"""B5 adversarial acceptance for the hardened backfill executor.

Runs entirely on stock_m2_test (independent local PG16 instance).
Cases: A1 unknown-DSN refused / A1b prod-identity double-permit gate /
A2 non-test db refused / A3 out-of-scope table refused /
A4 checkpoint missing -> blocked / A5 wrong-version rework /
A6 missing+running ckpt detected / A7 kill-resume /
A8 txn-failure rollback / A9 idempotent rerun /
A10 stop-file / A11 disk watermark / A12 data-vs-ckpt audit.
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import m2_testdb_fixtures as fx  # noqa: E402
import m2_t_backfill as bf  # noqa: E402
from m2_t_backfill import run_backfill  # noqa: E402

DSN = fx.TEST_DSN
T = "core.asset_status_daily"
VER = "pit_rules_v1"
D0, D1, D2 = "2026-10-20", "2026-10-21", "2026-10-22"
CKPT = "ops_m2.v2_backfill_checkpoint"
OUT = "docs/research_upgrade/implementation/m2/prelaunch/" \
      "BACKFILL_ADVERSARIAL_TESTS.json"
R = {}

CKPT_SQL = """
CREATE SCHEMA IF NOT EXISTS ops_m2;
CREATE TABLE IF NOT EXISTS ops_m2.v2_backfill_checkpoint (
  target_table text NOT NULL, trade_date date NOT NULL,
  flags_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('running','done','failed')),
  row_count integer, checksum text, run_id text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  PRIMARY KEY (target_table, trade_date))"""


def conn():
    return psycopg.connect(DSN, row_factory=dict_row)


def reset(ckpt=True):
    from stock_research.core_data import build_asset_status_daily
    c = conn()
    fx.reset(c)
    c.execute("DROP SCHEMA IF EXISTS ops_m2 CASCADE")
    fx.seed(c)
    build_asset_status_daily(c, D0, D2, "hfq")
    if ckpt:
        c.execute(CKPT_SQL)
    c.commit()
    c.close()


def run(**kw):
    kw.setdefault("dsn", DSN)
    kw.setdefault("target", T)
    kw.setdefault("flags_version", VER)
    kw.setdefault("start", D0)
    kw.setdefault("end", D2)
    return run_backfill(**kw)


# ---------- A1: arbitrary local DSN (non-test db) refused ----------
reset()
out = run(dsn="host=127.0.0.1 dbname=postgres user=xiwei",
          mode="write")
R["A1_unknown_dsn_refused"] = out["state"] == "refused" and \
    out["identity"]["kind"] == "unknown"

# ---------- A1b: prod identity requires double permit (mocked) ----------
orig = bf._identify
bf._identify = lambda c: {"host": "192.168.3.187", "port": 5432,
                          "dbname": "stock_research", "kind": "prod",
                          "is_local": False}
no_permit = run(mode="write")
wrong_confirm = run(mode="write", allow_prod=True,
                    prod_confirm="wrong:0:db")
wrong_table = run(mode="write", allow_prod=True,
                  prod_confirm="192.168.3.187:5432:stock_research",
                  target="core.asset_status_evil")
ok_permit = run(mode="write", allow_prod=True,
                prod_confirm="192.168.3.187:5432:stock_research")
bf._identify = orig
# with valid double permit the run must get PAST the identity gate —
# any later refusal must be resource/checkpoint, not identity/scope
ok_reason = ok_permit.get("reason", "")
R["A1b_prod_double_permit"] = (
    no_permit["state"] == "refused"
    and wrong_confirm["state"] == "refused"
    and wrong_table["state"] == "refused"
    and "prod needs" not in ok_reason
    and "unrecognized" not in ok_reason
    and "scope" not in ok_reason)
# dry-run on prod needs no permit but still refuses nothing else
bf._identify = lambda c: {"host": "192.168.3.187", "port": 5432,
                          "dbname": "stock_research", "kind": "prod",
                          "is_local": False}
dry = run(mode="dry-run")
bf._identify = orig
R["A1c_prod_dryrun_no_permit_needed"] = dry["state"] != "refused" or \
    "checkpoint" in dry.get("reason", "")

# ---------- A2: non-test local db refused ----------
out = run(dsn="host=127.0.0.1 dbname=watersaas user=xiwei",
          mode="write")
R["A2_nontest_db_refused"] = out["state"] == "refused"

# ---------- A3: out-of-scope table refused ----------
out = run(target="ops.users", mode="write")
R["A3_out_of_scope_table"] = out["state"] == "refused" and \
    "scope" in out.get("reason", "")

# ---------- A4: checkpoint schema missing -> blocked ----------
reset(ckpt=False)
out = run(mode="write")
R["A4_ckpt_missing_blocked"] = out["state"] == "blocked" and \
    "checkpoint" in out.get("reason", "")

# ---------- A5/A6: plan detects wrong-version + missing + running ----
reset()
c = conn()
c.execute(f"""INSERT INTO {CKPT}
  (target_table,trade_date,flags_version,status) VALUES
  ('{T}','{D0}','bogus_v9','done'),
  ('{T}','{D1}','{VER}','running')""")
c.commit(); c.close()
out = run(mode="dry-run")
p = out["plan"]
R["A5_wrong_version_flagged"] = p["wrong_version"] == 1
R["A6_pending_and_running_detected"] = p["pending"] == 1 and \
    p["retry_running"] == 1 and p["expected_dates"] == 3

# ---------- A7: simulated kill mid-run -> resume completes ----------
reset()
holder = {}
def worker():
    holder["r"] = run(mode="write", throttle_ms=0)
t = threading.Thread(target=worker, daemon=True)
t.start()
time.sleep(0.02)
bf._STOP["flag"] = True
t.join(15)
bf._STOP["flag"] = False
r1 = holder.get("r", {"state": "hung"})
o2 = run(mode="write")
R["A7_kill_resume"] = r1["state"] in ("stopped", "done") and \
    o2["coverage_ok"] is True

# ---------- A8: emit crash -> batch rolled back ----------
reset()
def bad_emit(c_, d, t_, v, enabled=True):
    c_.execute(f"UPDATE {T} SET limit_state_v2=1 WHERE trade_date=%s",
               [d])
    if d == D1:
        raise RuntimeError("injected crash")
    return {"status": "written", "matched_rows": 8,
            "missing_keys": 0, "invalid_rows": 0, "base_rows": 8}
try:
    run(mode="write", emit_fn=bad_emit)
except RuntimeError:
    pass
c = conn()
row = c.execute(f"""SELECT status FROM {CKPT}
  WHERE target_table='{T}' AND trade_date='{D1}'""").fetchone()
dirty = c.execute(f"""SELECT count(*) n FROM {T}
  WHERE trade_date='{D1}' AND limit_state_v2 IS NOT NULL""").fetchone()
c.close()
R["A8_txn_rollback_on_crash"] = (
    (row is None or row["status"] != "done") and dirty["n"] == 0)

# ---------- A9: full run then rerun -> nothing left, still ok -------
reset()
run(mode="write")
o2 = run(mode="write")
R["A9_idempotent_rerun"] = o2["coverage_ok"] is True and \
    o2["batches"] == []

# ---------- A10: stop-file prevents first batch; resume works -------
reset()
sf = "/tmp/m2_backfill_stop"
open(sf, "w").write("x")
out = run(mode="write", stop_file=sf)
os.remove(sf)
R["A10_stop_file_halts"] = out["state"] == "stopped" and \
    out["batches"] == []
o2 = run(mode="write")
R["A10b_resume_after_stop"] = o2["coverage_ok"] is True

# ---------- A11: disk watermark blocks ----------
reset()
out = run(mode="write", min_free_mb=10**12)
R["A11_disk_watermark"] = out["state"] == "blocked" and \
    "disk" in out.get("reason", "")

# ---------- A12: ckpt says done but data wiped -> audit catches ------
reset()
run(mode="write")
c = conn()
c.execute(f"""UPDATE {T} SET limit_state_v2=NULL,
  limit_flags_version=NULL, limit_rule_id_v2=NULL,
  is_limit_up_v2=NULL, is_limit_down_v2=NULL
  WHERE trade_date='{D2}'""")
c.commit(); c.close()
out = run(mode="write")
R["A12_data_gap_caught"] = out["coverage_ok"] is False and \
    any(g["issue"] == "data_incomplete" for g in
        out.get("audit_gaps", []))

res = {"cases": R, "passed": sum(1 for v in R.values() if v),
       "total": len(R), "all_pass": all(R.values())}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps(res, indent=1))
