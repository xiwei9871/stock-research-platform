"""M1-B v2 — guarded EOD V2 incremental write (deployment-safety).

Status contract (callers MUST honor):
  blocked      — precondition failed, zero writes; caller must not
                 mark EOD success nor advance any frontier
  incomplete   — some base rows lack a valid v2 flag; writes happened
                 inside the txn but the caller must NOT report success
                 (the caller should rollback unless it can tolerate and
                 explicitly quarantine the missing keys)
  idempotent   — every base row already carries THIS version with
                 complete, valid fields
  written      — all base rows updated with complete valid flags

The function never commits; everything is inside the caller's txn.
"""
from __future__ import annotations

import re

from stock_research.db import execute, fetch_all

V2_COLUMNS = ("is_limit_up_v2", "is_limit_down_v2",
              "limit_state_v2", "limit_rule_id_v2", "limit_flags_version")
_IDENT = re.compile(r"[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*")
VALID_STATES = (0, 1, 2, 3)  # normal / limit / rule_unknown / insufficient


def _check_target(conn, target_table):
    if not _IDENT.fullmatch(target_table):
        raise ValueError(f"bad target_table: {target_table!r}")
    sch, rel = target_table.split(".")
    have = {r["column_name"] for r in fetch_all(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s""", [sch, rel])}
    return sorted((set(V2_COLUMNS) | {"asset_id", "trade_date"}) - have)


def _validity_report(conn, target_table, trade_date, flags_version):
    """Rows carrying the version but with invalid/incomplete fields."""
    return fetch_all(conn, f"""
      SELECT
        count(*) FILTER (WHERE limit_state_v2 IS NULL
                          OR limit_state_v2 NOT IN (0,1,2,3)
                          OR is_limit_up_v2 IS NULL
                          OR is_limit_down_v2 IS NULL
                          OR limit_rule_id_v2 IS NULL
                          OR btrim(limit_rule_id_v2)='') bad,
        count(*) n
      FROM {target_table}
      WHERE trade_date=%s AND limit_flags_version=%s""",
                     [trade_date, flags_version])[0]


def emit_eod_v2_flags(conn, trade_date: str, target_table: str,
                      flags_version: str, enabled: bool = False) -> dict:
    res = {"status": "blocked", "trade_date": trade_date,
           "target": target_table, "flags_version": flags_version,
           "computed_keys": 0, "matched_rows": 0, "invalid_rows": 0,
           "state_dist": {}, "missing_keys": 0, "reasons": []}
    if not enabled:
        res["reasons"].append("v2 eod switch is OFF (default)")
        return res
    missing = _check_target(conn, target_table)
    if missing:
        res["reasons"].append(f"target lacks v2 columns {missing}")
        return res
    base = fetch_all(conn, f"""
        SELECT count(*) n FROM {target_table} WHERE trade_date=%s""",
                     [trade_date])[0]["n"]
    if base == 0:
        res["reasons"].append("base status rows absent for date — "
                              "build_asset_status_daily must commit first")
        return res
    res["base_rows"] = base

    # version consistency across NULL / mixed / expected
    ver = fetch_all(conn, f"""
        SELECT COALESCE(limit_flags_version,'<NULL>') v, count(*) n
        FROM {target_table} WHERE trade_date=%s GROUP BY 1""",
                    [trade_date])
    others = [r for r in ver
              if r["v"] not in (flags_version, "<NULL>")]
    if others:
        res["reasons"].append(
            f"version conflict: existing rows carry {others}")
        return res

    done = next((r["n"] for r in ver if r["v"] == flags_version), 0)
    if done:
        vr = _validity_report(conn, target_table, trade_date,
                              flags_version)
        if vr["bad"] == 0 and done == base:
            res.update(status="idempotent", matched_rows=done)
            res["reasons"].append("all rows carry valid flags under "
                                  "this version")
            return res
        # partial or invalid rows under the version -> fall through to
        # a rewrite pass so coverage completes (still same version)
        res["reasons"].append(
            f"{base-done} unwritten + {vr['bad']} invalid under "
            f"{flags_version} — rewriting")

    from stock_research.core_data import emit_v2_flags
    computed = emit_v2_flags(conn, trade_date, trade_date,
                             target_table, flags_version=flags_version)
    res["computed_keys"] = computed

    after = fetch_all(conn, f"""
        SELECT limit_state_v2 st, count(*) n FROM {target_table}
        WHERE trade_date=%s AND limit_flags_version=%s GROUP BY 1""",
                      [trade_date, flags_version])
    res["matched_rows"] = sum(r["n"] for r in after)
    res["state_dist"] = {str(r["st"]): r["n"] for r in after}
    res["missing_keys"] = base - res["matched_rows"]
    vr = _validity_report(conn, target_table, trade_date, flags_version)
    res["invalid_rows"] = vr["bad"]
    if res["missing_keys"] or res["invalid_rows"]:
        res["status"] = "incomplete"
        res["reasons"].append(
            f"missing={res['missing_keys']} invalid={res['invalid_rows']}"
            " — caller must not report EOD success")
    else:
        res["status"] = "written"
    return res
