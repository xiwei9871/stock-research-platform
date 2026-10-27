"""M1-E — lightweight DATA integrity gate.

Machine states per domain:
  READY    contract + evidence + coverage hold
  DEGRADED data present but evidence/coverage uncertain
  BLOCKED  required source/version/evidence missing — result must not
           be consumed as trusted

combine(): a strategy needing both domains can never be promoted by a
READY domain covering a BLOCKED one.
"""
from __future__ import annotations

STATES = ("READY", "DEGRADED", "BLOCKED")


def combine(*states: str) -> str:
    if "BLOCKED" in states:
        return "BLOCKED"
    if "DEGRADED" in states:
        return "DEGRADED"
    return "READY"


def evaluate_tradeability(conn, status_table="core.asset_status_daily",
                          require_v2=False) -> dict:
    """Tradeability domain gate (read-only checks)."""
    from stock_research.db import fetch_all
    sch, rel = status_table.split(".")
    out = {"domain": "tradeability", "table": status_table,
           "checks": {}, "state": "READY", "reasons": []}
    cols = {r["column_name"] for r in fetch_all(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s""", [sch, rel])}
    v2 = {"is_limit_up_v2", "is_limit_down_v2", "limit_state_v2",
          "limit_rule_id_v2", "limit_flags_version"}
    out["checks"]["v2_columns"] = sorted(v2 & cols)
    if require_v2 and not v2 <= cols:
        out["state"] = "BLOCKED"
        out["reasons"].append("v2 contract columns absent")
        return out
    if v2 <= cols:
        ver = fetch_all(conn, f"""
            SELECT count(DISTINCT limit_flags_version) n FROM
            {status_table}""")[0]["n"]
        out["checks"]["flags_versions"] = ver
        if ver > 1:
            out["state"] = "DEGRADED"
            out["reasons"].append(f"{ver} flag versions mixed")
    rows = fetch_all(conn, f"SELECT count(*) n FROM {status_table}")[0]
    out["checks"]["rows"] = rows["n"]
    if rows["n"] == 0:
        out["state"] = "BLOCKED"
        out["reasons"].append("status table empty")
    return out


def evaluate_financial(conn, universe_limit=None) -> dict:
    """Financial PIT domain gate (read-only checks)."""
    from stock_research.db import fetch_all
    out = {"domain": "financial_pit", "checks": {},
           "state": "READY", "reasons": []}
    sent = fetch_all(conn, """
        SELECT (SELECT count(*) FROM finance.balance_sheet
                 WHERE announcement_date='1900-01-01'
                    OR announcement_date IS NULL) b,
               (SELECT count(*) FROM finance.cash_flow
                 WHERE announcement_date='1900-01-01'
                    OR announcement_date IS NULL) c""")[0]
    out["checks"]["sentinel_rows"] = sent
    if sent["b"] or sent["c"]:
        out["state"] = "DEGRADED"
        out["reasons"].append(
            f"sentinel announcement rows b={sent['b']} c={sent['c']}")
    raw = fetch_all(conn, "SELECT count(*) n FROM "
                    "raw_akshare.finance_payload")[0]["n"]
    out["checks"]["raw_payload_rows"] = raw
    if raw == 0:
        out["state"] = "DEGRADED"
        out["reasons"].append("no raw payload evidence accumulated")
    mv = fetch_all(conn, """
        SELECT count(*) n FROM (SELECT 1 FROM finance.balance_sheet
        GROUP BY asset_id, report_period, report_type, source
        HAVING count(DISTINCT announcement_date)>1) x""")[0]["n"]
    out["checks"]["versioned_keys"] = mv
    out["reasons"].append(
        "normalized tables overwrite same-key versions; versioned "
        "evidence lives in finver/raw layers only")
    if out["state"] == "READY":
        out["state"] = "DEGRADED"  # versioning layer not yet deployed
    return out


def evaluate(conn, require_v2=False,
             status_table="core.asset_status_daily") -> dict:
    t = evaluate_tradeability(conn, status_table, require_v2)
    f = evaluate_financial(conn)
    return {"tradeability": t, "financial_pit": f,
            "combined": combine(t["state"], f["state"])}
