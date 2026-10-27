"""M2-0-B — final DATA integrity gate (production-readiness rev).

Requirement-driven: a consumer declares *what it needs* (domain, v2
contract, expected flags_version, date window); the gate answers only
that requirement — never a blanket READY.

Tradeability states:
  LEGACY_READY  v1 healthy, v2 contract absent
  V2_READY      v2 cols + full valid coverage of EXPECTED version on
                EVERY requested date
  DEGRADED      present but uncertain (partial coverage, mixed ver)
  BLOCKED       empty/missing contract/illegal fields/wrong version

Financial states (per layer):
  SCHEMA_READY  finver tables+PKs+FKs exist in the TARGET schema
  WRITER_READY  recent write evidence (observation freshness)
  DATA_READY    events>0 AND chain pointers consistent
  plus DEGRADED / BLOCKED.

Shadow/test objects NEVER promote production verdicts — the target
schema/table is an explicit parameter.
"""
from __future__ import annotations

VALID_STATES = ("V2_READY", "LEGACY_READY", "READY", "DEGRADED",
                "BLOCKED", "SCHEMA_READY", "WRITER_READY",
                "DATA_READY")

V2_COLS = ("is_limit_up_v2", "is_limit_down_v2", "limit_state_v2",
           "limit_rule_id_v2", "limit_flags_version")
# v2 limit_state enum (tradeability.py):
#   0 not_computed | 1 verified | 2 rule_unknown | 3 data_insufficient
LEGAL_LIMIT_STATES = (0, 1, 2, 3)
# states that can support a *deterministic tradable/not-tradable*
# conclusion; 2/3 must never be consumed as such
VERIFIED_TRADE_STATES = (0, 1)

FINVER_TABLES = ("finver_event", "finver_observation",
                 "finver_key_chain")


def _bad(reasons: list[str], msg: str) -> str:
    reasons.append(msg)
    return "BLOCKED"


def combine(*states: str) -> str:
    """Fail-closed merge. No input -> BLOCKED. Unknown token -> BLOCKED.
    """
    if not states:
        return "BLOCKED"
    if any(s not in VALID_STATES for s in states):
        return "BLOCKED"
    if "BLOCKED" in states:
        return "BLOCKED"
    if "DEGRADED" in states:
        return "DEGRADED"
    return "READY"


# ----------------------------------------------------------------------
# tradeability
# ----------------------------------------------------------------------

def evaluate_tradeability(conn, status_table="core.asset_status_daily",
                          require_v2=False, expected_version=None,
                          trade_dates=None) -> dict:
    """Requirement-scoped tradeability verdict.

    require_v2        consumer needs the v2 contract
    expected_version  explicit flags_version to compare (e.g.
                      'pit_rules_v1'); required when require_v2
    trade_dates       list of dates (or {'start','end'}) the consumer
                      will read — version/validity verified PER DATE,
                      not as a table-wide blob
    """
    import re
    if not re.fullmatch(r"[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*",
                        status_table):
        raise ValueError(f"bad table: {status_table!r}")
    from stock_research.db import fetch_all
    sch, rel = status_table.split(".")
    out = {"domain": "tradeability", "table": status_table,
           "checks": {}, "state": "BLOCKED", "reasons": [],
           "requirement": {"require_v2": require_v2,
                           "expected_version": expected_version,
                           "trade_dates": trade_dates}}
    if require_v2 and not expected_version:
        out["reasons"].append(
            "require_v2 without expected_version — refusing to guess")
        return out
    cols = {r["column_name"] for r in fetch_all(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s""", [sch, rel])}
    base_ok = {"trade_date", "asset_id", "is_limit_up",
               "is_limit_down"} <= cols
    if not base_ok:
        out["reasons"].append(f"base contract missing cols "
                              f"{sorted({'trade_date','asset_id','is_limit_up','is_limit_down'}-cols)}")
        return out

    # date scoping
    if trade_dates is None:
        where, params = "true", []
    elif isinstance(trade_dates, dict):
        where, params = "trade_date BETWEEN %s AND %s", [
            trade_dates["start"], trade_dates["end"]]
    else:
        where, params = "trade_date = ANY(%s::date[])", [list(trade_dates)]

    scope = fetch_all(conn, f"""
        SELECT count(*) n, count(DISTINCT trade_date) nd
        FROM {status_table} WHERE {where}""", params)[0]
    out["checks"]["scoped_rows"] = scope
    if scope["n"] == 0:
        out["reasons"].append("no rows in requested scope — never READY")
        return out

    has_v2 = set(V2_COLS) <= cols
    out["checks"]["v2_columns_present"] = sorted(set(V2_COLS) & cols)
    if not has_v2:
        out["state"] = "LEGACY_READY"
        out["reasons"].append("v2 contract absent — legacy v1 healthy")
        if require_v2:
            out["state"] = _bad(out["reasons"],
                                "require_v2 unmet (no v2 columns)")
        return out

    # per-date version & validity — table-wide averages hide breakage
    per_date = fetch_all(conn, f"""
        SELECT trade_date::text d, count(*) n,
          count(DISTINCT limit_flags_version) nv,
          count(*) FILTER (WHERE limit_flags_version IS NULL) nullv,
          count(*) FILTER (WHERE limit_flags_version <> %s) wrongv,
          count(*) FILTER (WHERE limit_flags_version=%s
                            AND (limit_state_v2 IS NULL
                              OR limit_state_v2 NOT IN (0,1,2,3))) badst,
          count(*) FILTER (WHERE limit_flags_version=%s
                            AND (is_limit_up_v2 IS NULL
                              OR is_limit_down_v2 IS NULL)) badflag,
          count(*) FILTER (WHERE limit_flags_version=%s
                            AND (limit_rule_id_v2 IS NULL
                              OR btrim(limit_rule_id_v2)='')) badrule,
          count(*) FILTER (WHERE limit_state_v2 IN (2,3)) unver,
          count(*) FILTER (WHERE limit_flags_version = %s) ok
        FROM {status_table} WHERE {where}
        GROUP BY trade_date ORDER BY trade_date""",
                         [expected_version or "",
                          expected_version or "",
                          expected_version or "",
                          expected_version or "",
                          expected_version or "", *params])
    out["checks"]["per_date"] = per_date
    if not per_date:
        out["reasons"].append("no v2 rows in scope")
        return out if not require_v2 else out

    bad_dates = []
    mixed, wrong_ver, partial, invalid = [], [], [], []
    unver_rows = 0
    for r in per_date:
        unver_rows += r["unver"]
        if r["nv"] > 1:
            mixed.append(r["d"])
        # foreign-version verdict needs an EXPECTED version to compare
        # against; without one any real tag reads as foreign
        if expected_version and r["wrongv"]:
            wrong_ver.append({"date": r["d"], "n": r["wrongv"]})
        if r["nullv"]:
            partial.append({"date": r["d"], "missing": r["nullv"]})
        if r["badst"] or r["badflag"] or r["badrule"]:
            invalid.append({"date": r["d"], "badst": r["badst"],
                            "badflag": r["badflag"],
                            "badrule": r["badrule"]})
    flagged = sum(r["ok"] for r in per_date)
    out["checks"].update(
        flagged=flagged, total=scope["n"],
        unverifiable_rows=unver_rows,
        note="unverifiable_rows (rule_unknown/data_insufficient) may "
             "NOT be consumed as deterministic tradable verdicts")
    if invalid:
        out["state"] = _bad(out["reasons"],
                            f"illegal v2 fields on {len(invalid)} dates:"
                            f" {invalid[:3]}")
    elif wrong_ver:
        out["state"] = _bad(out["reasons"],
                            f"foreign flags_version present: "
                            f"{wrong_ver[:3]}")
    elif flagged == 0:
        out["state"] = "DEGRADED"
        out["reasons"].append("v2 columns exist, zero coverage in scope")
    elif mixed:
        out["state"] = "DEGRADED"
        out["reasons"].append(f"mixed flag versions on {mixed[:5]}")
    elif partial:
        out["state"] = "DEGRADED"
        out["reasons"].append(f"partial coverage {partial[:3]}")
    else:
        out["state"] = "V2_READY"
    if require_v2 and out["state"] != "V2_READY":
        out["state"] = _bad(out["reasons"], "require_v2 unmet")
    return out


# ----------------------------------------------------------------------
# financial PIT / finver
# ----------------------------------------------------------------------

_FINVER_EXPECTED_COLS = {
    "finver_event": {"version_event_id", "asset_id", "statement_type",
                     "endpoint", "report_period", "report_type",
                     "version_seq", "metric_fingerprint", "metrics",
                     "first_seen_at"},
    "finver_observation": {"observation_id", "version_event_id",
                           "seen_at", "change_class"},
    "finver_key_chain": {"asset_id", "statement_type", "endpoint",
                         "report_period", "report_type", "n_versions",
                         "latest_event_id"},
}


def evaluate_finver_schema(conn, finver_schema: str) -> dict:
    """Layered finver readiness for an EXPLICIT schema only.

    A shadow schema can reach its own verdicts but can never satisfy a
    production requirement (the caller passes the production schema).
    """
    import re
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", finver_schema):
        raise ValueError(f"bad schema: {finver_schema!r}")
    from stock_research.db import fetch_all
    out = {"domain": "finver", "schema": finver_schema,
           "layers": {}, "state": "BLOCKED", "reasons": []}
    tables = {r["table_name"] for r in fetch_all(conn, """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema=%s""", [finver_schema])}
    missing = [t for t in FINVER_TABLES if t not in tables]
    out["layers"]["tables_missing"] = missing
    if missing:
        out["reasons"].append(f"{missing} absent in {finver_schema}")
        return out
    col_ok, col_bad = {}, {}
    for t in FINVER_TABLES:
        have = {r["column_name"] for r in fetch_all(conn, """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s""",
                                                [finver_schema, t])}
        need = _FINVER_EXPECTED_COLS[t]
        col_bad[t] = sorted(need - have)
        col_ok[t] = not col_bad[t]
    out["layers"]["columns"] = col_bad
    if not all(col_ok.values()):
        out["reasons"].append(f"column gaps {col_bad}")
        return out
    # PK / FK structure
    pk = fetch_all(conn, """
        SELECT c.relname, count(*) n FROM pg_constraint ct
        JOIN pg_class c ON c.oid=ct.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND ct.contype='p'
          AND c.relname = ANY(%s)
        GROUP BY 1""", [finver_schema, list(FINVER_TABLES)])
    fk = fetch_all(conn, """
        SELECT count(*) n FROM pg_constraint ct
        JOIN pg_class c ON c.oid=ct.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND ct.contype='f'""", [finver_schema])[0]["n"]
    out["layers"]["pks"] = {r["relname"]: r["n"] for r in pk}
    out["layers"]["fk_count"] = fk
    if len(pk) < 3 or fk < 2:
        out["reasons"].append("PK/FK contract incomplete")
        return out
    out["layers"]["SCHEMA_READY"] = True

    # DATA layer: events exist + chain pointers consistent
    ev = fetch_all(conn, f"""SELECT count(*) n,
        max(first_seen_at)::text last_ev FROM
        {finver_schema}.finver_event""")[0]
    obs = fetch_all(conn, f"""SELECT count(*) n,
        max(seen_at)::text last_obs FROM
        {finver_schema}.finver_observation""")[0]
    out["layers"]["events"] = ev
    out["layers"]["observations"] = obs
    orphans = fetch_all(conn, f"""
        SELECT count(*) n FROM {finver_schema}.finver_key_chain c
        LEFT JOIN {finver_schema}.finver_event e
          ON e.version_event_id = c.latest_event_id
        WHERE e.version_event_id IS NULL""")[0]["n"]
    out["layers"]["orphan_heads"] = orphans
    out["layers"]["WRITER_READY"] = obs["n"] > 0
    out["layers"]["DATA_READY"] = (
        ev["n"] > 0 and obs["n"] > 0 and orphans == 0)
    if out["layers"]["DATA_READY"]:
        out["state"] = "READY"
        out["layers"]["detail"] = (
            "SCHEMA_READY+WRITER_READY+DATA_READY")
    elif out["layers"]["WRITER_READY"]:
        out["state"] = "DEGRADED"
        out["reasons"].append("observations but chain/event integrity "
                              "incomplete")
    else:
        out["state"] = "DEGRADED"
        out["reasons"].append("schema present, zero write evidence — "
                              "tables != deployed pipeline")
    return out


def evaluate_financial(conn, finver_schema="finver") -> dict:
    """Financial PIT domain: statement quality + finver readiness."""
    from stock_research.db import fetch_all
    out = {"domain": "financial_pit", "finver_schema": finver_schema,
           "checks": {}, "state": "DEGRADED", "reasons": []}
    sent = fetch_all(conn, """
        SELECT (SELECT count(*) FROM finance.balance_sheet
                 WHERE announcement_date='1900-01-01'
                    OR announcement_date IS NULL) b,
               (SELECT count(*) FROM finance.cash_flow
                 WHERE announcement_date='1900-01-01'
                    OR announcement_date IS NULL) c""")[0]
    out["checks"]["sentinel_rows"] = sent
    raw = fetch_all(conn, "SELECT count(*) n FROM "
                    "raw_akshare.finance_payload")[0]["n"]
    out["checks"]["raw_payload_rows"] = raw
    fv = evaluate_finver_schema(conn, finver_schema)
    out["checks"]["finver"] = fv
    if sent["b"] or sent["c"]:
        out["reasons"].append(
            f"sentinel announcement rows b={sent['b']} c={sent['c']}")
    if fv["state"] == "BLOCKED":
        out["state"] = "BLOCKED"
        out["reasons"].append(f"finver {finver_schema}: "
                              + "; ".join(fv["reasons"]))
    elif fv["state"] == "DEGRADED":
        out["state"] = "DEGRADED"
        out["reasons"].extend(fv["reasons"])
    elif sent["b"] == 0 and sent["c"] == 0 and raw > 0:
        out["state"] = "READY"
    else:
        out["state"] = "DEGRADED"
    return out


# ----------------------------------------------------------------------
# consumer-declared requirements
# ----------------------------------------------------------------------

def evaluate_requirements(conn, requirements: dict) -> dict:
    """Answer exactly what a consumer declared it needs.

    requirements = {
      "tradeability": {"require_v2": True,
                       "expected_version": "pit_rules_v1",
                       "trade_dates": [...] | {"start":..,"end":..},
                       "table": "core.asset_status_daily"},
      "financial": {"finver_schema": "finver"}
    }
    Any domain required-but-absent -> that domain BLOCKED.
    """
    out = {"verdicts": {}, "combined": "BLOCKED"}
    if not requirements:
        out["error"] = "empty requirement set — fail closed"
        return out
    states = []
    if "tradeability" in requirements:
        t = requirements["tradeability"] or {}
        v = evaluate_tradeability(
            conn, t.get("table", "core.asset_status_daily"),
            require_v2=bool(t.get("require_v2")),
            expected_version=t.get("expected_version"),
            trade_dates=t.get("trade_dates"))
        out["verdicts"]["tradeability"] = v
        states.append(v["state"])
    if "financial" in requirements:
        f = requirements["financial"] or {}
        v = evaluate_financial(conn, f.get("finver_schema", "finver"))
        out["verdicts"]["financial"] = v
        states.append("BLOCKED" if v["state"] == "BLOCKED"
                      else ("READY" if v["state"] == "READY"
                            else "DEGRADED"))
    if not states:
        out["error"] = "no declared dependency domains — fail closed"
        return out
    out["combined"] = combine(*states)
    return out


def evaluate(conn, require_v2=False,
             status_table="core.asset_status_daily",
             expected_version=None, trade_dates=None,
             finver_schema="finver") -> dict:
    t = evaluate_tradeability(conn, status_table, require_v2,
                              expected_version, trade_dates)
    f = evaluate_financial(conn, finver_schema)
    return {"tradeability": t, "financial_pit": f,
            "combined": combine(t["state"], f["state"])}
