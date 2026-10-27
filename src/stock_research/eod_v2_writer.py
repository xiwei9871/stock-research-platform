"""M1-B — guarded EOD V2 incremental write for tradeability flags.

Wraps core_data.emit_v2_flags with the safety contract required before
production dual-write can ever be enabled. DEFAULT OFF.

Rules enforced:
  1. switch must be explicitly enabled;
  2. target table must carry the v2 column contract;
  3. base status rows for the date must already exist (emit is a pure
     UPDATE — flags never fabricate rows);
  4. a pinned flags_version is required and must not conflict with a
     different version already present on the date;
  5. metrics are reported: computed keys, matched rows, shadow_state
     distribution, missing keys;
  6. everything runs in the caller's transaction — a mid-write failure
     rolls the day back atomically; the caller must not mark EOD
     success unless this returns status=written.
"""
from __future__ import annotations

import re

from stock_research.db import execute, fetch_all

V2_COLUMNS = ("is_limit_up_v2", "is_limit_down_v2",
              "limit_state_v2", "limit_rule_id_v2", "limit_flags_version")
_IDENT = re.compile(r"[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*")


def _check_target(conn, target_table):
    if not _IDENT.fullmatch(target_table):
        raise ValueError(f"bad target_table: {target_table!r}")
    sch, rel = target_table.split(".")
    have = {r["column_name"] for r in fetch_all(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s""", [sch, rel])}
    missing = sorted((set(V2_COLUMNS) | {"asset_id", "trade_date"})
                     - have)
    return missing


def emit_eod_v2_flags(conn, trade_date: str, target_table: str,
                      flags_version: str, enabled: bool = False) -> dict:
    """Emit V2 flags for ONE trade date under the M1-B gate."""
    res = {"status": "blocked", "trade_date": trade_date,
           "target": target_table, "flags_version": flags_version,
           "computed_keys": 0, "matched_rows": 0, "state_dist": {},
           "missing_keys": 0, "reasons": []}
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
    prior = fetch_all(conn, f"""
        SELECT DISTINCT limit_flags_version v, count(*) n
        FROM {target_table} WHERE trade_date=%s
          AND limit_flags_version IS NOT NULL GROUP BY 1""", [trade_date])
    others = [r for r in prior if r["v"] != flags_version]
    if others:
        res["reasons"].append(
            f"version conflict: existing rows carry {others}")
        return res
    if prior and prior[0]["n"] == base:
        res["status"] = "idempotent"
        res["matched_rows"] = base
        res["reasons"].append("all rows already carry this version")
        return res

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
    res["status"] = "written"
    if res["missing_keys"]:
        res["reasons"].append(
            f"{res['missing_keys']} base rows had no computed flag")
    return res
