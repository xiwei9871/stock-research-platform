"""M1-E v2 — lightweight DATA integrity gate (deployment-safety rev).

States:
  V2_READY     v2 columns present AND all rows carry a single valid
               flags_version with complete valid fields
  LEGACY_READY healthy v1-only table (v2 absent is NOT downgraded —
               it is simply not v2)
  DEGRADED     present but uncertain (mixed versions, partial flags,
               sentinel/quality findings)
  BLOCKED      empty table, missing base contract, illegal states

combine(): BLOCKED always wins; a READY domain can never cover a
BLOCKED one.
"""
from __future__ import annotations

STATES = ("V2_READY", "LEGACY_READY", "READY", "DEGRADED", "BLOCKED")


def combine(*states: str) -> str:
    if "BLOCKED" in states:
        return "BLOCKED"
    if "DEGRADED" in states:
        return "DEGRADED"
    return "READY"


def evaluate_tradeability(conn, status_table="core.asset_status_daily",
                          require_v2=False) -> dict:
    from stock_research.db import fetch_all
    sch, rel = status_table.split(".")
    out = {"domain": "tradeability", "table": status_table,
           "checks": {}, "state": "BLOCKED", "reasons": []}
    cols = {r["column_name"] for r in fetch_all(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s""", [sch, rel])}
    rows = fetch_all(conn, f"SELECT count(*) n FROM {status_table}")[0]
    out["checks"]["rows"] = rows["n"]
    if rows["n"] == 0:
        out["reasons"].append("status table empty — never READY")
        return out
    v2 = {"is_limit_up_v2", "is_limit_down_v2", "limit_state_v2",
          "limit_rule_id_v2", "limit_flags_version"}
    has_v2 = v2 <= cols
    out["checks"]["v2_columns_present"] = sorted(v2 & cols)
    if not has_v2:
        out["state"] = "LEGACY_READY"
        out["reasons"].append("v2 contract absent — legacy v1 healthy; "
                              "NOT v2-ready")
        if require_v2:
            out["state"] = "BLOCKED"
            out["reasons"].append("require_v2=True")
        return out
    stat = fetch_all(conn, f"""
        SELECT count(DISTINCT limit_flags_version) nv,
          count(*) FILTER (WHERE limit_flags_version IS NULL) nullv,
          count(*) FILTER (WHERE limit_state_v2 IS NULL
                            OR limit_state_v2 NOT IN (0,1,2,3)) badst,
          count(*) FILTER (WHERE is_limit_up_v2 IS NULL
                            OR is_limit_down_v2 IS NULL) badflag,
          count(*) FILTER (WHERE limit_rule_id_v2 IS NULL
                            OR btrim(limit_rule_id_v2)='') badrule,
          count(*) FILTER (WHERE limit_flags_version IS NOT NULL)
            flagged
        FROM {status_table}""")[0]
    out["checks"]["v2"] = stat
    if stat["badst"] or stat["badflag"] or stat["badrule"]:
        out["state"] = "BLOCKED"
        out["reasons"].append(
            f"illegal/incomplete v2 fields: {stat}")
    elif stat["flagged"] == 0:
        out["state"] = "DEGRADED"
        out["reasons"].append("v2 columns exist but no flags written")
    elif stat["nv"] > 1:
        out["state"] = "DEGRADED"
        out["reasons"].append(f"{stat['nv']} flag versions mixed")
    elif stat["flagged"] < rows["n"]:
        out["state"] = "DEGRADED"
        out["reasons"].append(
            f"partial coverage {stat['flagged']}/{rows['n']}")
    else:
        out["state"] = "V2_READY"
    if require_v2 and out["state"] != "V2_READY":
        out["state"] = "BLOCKED"
        out["reasons"].append("require_v2=True unmet")
    return out


def evaluate_financial(conn) -> dict:
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
    finver = fetch_all(conn, """
        SELECT count(*) n FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog','information_schema')
          AND table_name='finver_event'""")[0]["n"]
    out["checks"]["finver_tables"] = finver
    if finver == 0:
        out["state"] = "DEGRADED"
        out["reasons"].append("no version-event layer deployed")
    if out["state"] == "READY":
        out["state"] = "DEGRADED"
        out["reasons"].append("version layer not yet on production")
    return out


def evaluate(conn, require_v2=False,
             status_table="core.asset_status_daily") -> dict:
    t = evaluate_tradeability(conn, status_table, require_v2)
    f = evaluate_financial(conn)
    return {"tradeability": t, "financial_pit": f,
            "combined": combine(t["state"], f["state"])}
