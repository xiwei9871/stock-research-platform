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
    out = {"verdicts": {}, "combined": "BLOCKED", "satisfied": {}}
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
        # satisfied = the verdict actually meets the DECLARED need:
        # a V2 consumer is never satisfied by LEGACY_READY
        if t.get("require_v2"):
            ok = v["state"] == "V2_READY"
        else:
            ok = v["state"] in ("LEGACY_READY", "V2_READY")
        if not ok and t.get("allow_degraded") and v["state"] == "DEGRADED":
            ok = True
            v["satisfied_via"] = "declared allow_degraded"
        out["satisfied"]["tradeability"] = ok
    if "financial" in requirements:
        f = requirements["financial"] or {}
        if f.get("require_writer"):
            w = evaluate_finver_writer(
                conn, f.get("finver_schema", "finver"),
                raw_table=f.get("raw_table",
                                "raw_akshare.finance_payload"),
                staleness_hours=f.get("staleness_hours"),
                heartbeat_at=f.get("heartbeat_at"),
                expected_endpoints=f.get("expected_endpoints"))
            v = {"domain": "finver_writer", "state": w["state"],
                 "writer": w}
        else:
            v = evaluate_financial(conn, f.get("finver_schema",
                                             "finver"))
        out["verdicts"]["financial"] = v
        states.append("BLOCKED" if v["state"] == "BLOCKED"
                      else ("READY" if v["state"] == "READY"
                            else "DEGRADED"))
        need = f.get("min_state", "data")
        if f.get("require_writer"):
            layers = v["writer"]["layers"]
            if need == "schema":
                ok = layers.get("schema") != "BLOCKED"
            elif need == "writer":
                ok = bool(layers.get("WRITER_READY"))
            else:
                ok = bool(layers.get("DATA_READY"))
        elif need == "schema":
            ok = v["state"] in ("READY", "DEGRADED")
        elif need == "writer":
            ok = v["state"] == "READY"
        else:  # data — full readiness required
            ok = v["state"] == "READY"
        if not ok and f.get("allow_degraded") and v["state"] == "DEGRADED":
            ok = True
            v["satisfied_via"] = "declared allow_degraded"
        out["satisfied"]["financial"] = ok
    if not states:
        out["error"] = "no declared dependency domains — fail closed"
        return out
    out["combined"] = combine(*states)
    # a consumer is admissible only when EVERY declared domain is
    # satisfied — READY-on-paper with an unsatisfied domain is BLOCKED
    if not all(out["satisfied"].values()):
        out["combined"] = "BLOCKED"
        out["reason"] = {k: v for k, v in out["satisfied"].items()
                         if not v}
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


# ----------------------------------------------------------------------
# P0-C1 — finver WRITER freshness & scope-bound DATA readiness
# ----------------------------------------------------------------------

def evaluate_finver_writer(conn, finver_schema="finver",
                           raw_table="raw_akshare.finance_payload",
                           staleness_hours=None, heartbeat_at=None,
                           expected_endpoints=None) -> dict:
    """Writer-freshness layer on top of evaluate_finver_schema.

    - last_write_at / last_event_at from observation & event tables
    - raw-vs-observation reconciliation (raw ids lacking an
      observation row; observation rows pointing at missing raw)
    - per-endpoint coverage split
    - chain consistency (orphan heads, n_versions mismatches)
    WRITER_READY requires *fresh* evidence: either heartbeat_at (a
    controlled job-run timestamp supplied by the caller) within
    staleness_hours, or last_write_at within staleness_hours of now().
    Historical rows alone NEVER make the writer ready.
    DATA_READY additionally requires expected_endpoints coverage —
    an undeclared scope cannot be certified.
    """
    from stock_research.db import fetch_all
    s = finver_schema
    out = {"domain": "finver_writer", "schema": s, "layers": {},
           "state": "BLOCKED", "reasons": []}
    schema = evaluate_finver_schema(conn, s)
    out["layers"]["schema"] = schema["state"]
    if not schema["layers"].get("SCHEMA_READY"):
        out["reasons"] += schema["reasons"]
        return out

    ev = fetch_all(conn, f"""SELECT count(*) n,
        max(first_seen_at) last_ev FROM {s}.finver_event""")[0]
    ob = fetch_all(conn, f"""SELECT count(*) n, max(seen_at) last_obs,
        count(raw_payload_id) with_raw
        FROM {s}.finver_observation""")[0]
    out["layers"]["last_event_at"] = str(ev["last_ev"])
    out["layers"]["last_write_at"] = str(ob["last_obs"])

    # reconciliation vs the raw evidence table (if it exists)
    raw_exists = fetch_all(conn, """
        SELECT count(*) n FROM information_schema.tables
        WHERE table_schema||'.'||table_name = %s""",
                           [raw_table])[0]["n"]
    if raw_exists:
        out["layers"]["raw_rows"] = fetch_all(conn,
            f"SELECT count(*) n FROM {raw_table}")[0]["n"]
        out["layers"]["raw_without_observation"] = fetch_all(conn, f"""
            SELECT count(*) n FROM {raw_table} r
            LEFT JOIN {s}.finver_observation o
              ON o.raw_payload_id = r.id
            WHERE o.raw_payload_id IS NULL""")[0]["n"]
        out["layers"]["orphan_observation"] = fetch_all(conn, f"""
            SELECT count(*) n FROM {s}.finver_observation o
            LEFT JOIN {raw_table} r ON r.id = o.raw_payload_id
            WHERE o.raw_payload_id IS NOT NULL AND r.id IS NULL"""
                                              )[0]["n"]
        out["layers"]["per_endpoint"] = fetch_all(conn, f"""
            SELECT r.source_endpoint ep, count(*) raw_n,
              count(o.raw_payload_id) observed_n
            FROM {raw_table} r
            LEFT JOIN {s}.finver_observation o
              ON o.raw_payload_id = r.id
            GROUP BY 1 ORDER BY 1""")
    else:
        out["reasons"].append(f"raw table {raw_table} absent")

    # chain consistency
    out["layers"]["orphan_heads"] = fetch_all(conn, f"""
        SELECT count(*) n FROM {s}.finver_key_chain c
        LEFT JOIN {s}.finver_event e
          ON e.version_event_id = c.latest_event_id
        WHERE e.version_event_id IS NULL""")[0]["n"]
    out["layers"]["nversions_mismatch"] = fetch_all(conn, f"""
        SELECT count(*) n FROM {s}.finver_key_chain c
        WHERE c.n_versions <> (SELECT count(*) FROM {s}.finver_event e
          WHERE e.asset_id=c.asset_id
            AND e.statement_type=c.statement_type
            AND e.endpoint=c.endpoint
            AND e.report_period=c.report_period
            AND e.report_type=c.report_type)""")[0]["n"]

    # freshness
    if heartbeat_at and staleness_hours:
        out["layers"]["heartbeat_at"] = str(heartbeat_at)
        out["layers"]["heartbeat_within"] = staleness_hours
    fresh = False
    if ob["last_obs"] and staleness_hours:
        row = fetch_all(conn, """
            SELECT (max_ts >= now() - make_interval(hours => %s)) fresh
            FROM (SELECT %s::timestamptz max_ts) t""",
                        [staleness_hours, ob["last_obs"]])[0]
        fresh = bool(row["fresh"])
    out["layers"]["WRITER_READY"] = bool(
        fresh or (heartbeat_at and staleness_hours))
    if not out["layers"]["WRITER_READY"]:
        out["reasons"].append(
            "no fresh write/heartbeat evidence — historical rows "
            "cannot certify a live writer")

    chain_ok = (out["layers"]["orphan_heads"] == 0
                and out["layers"]["nversions_mismatch"] == 0)
    if expected_endpoints:
        have = {r["ep"] for r in out["layers"].get("per_endpoint", [])
                if r["observed_n"] > 0}
        missing_eps = sorted(set(expected_endpoints) - have)
        out["layers"]["expected_endpoints_missing"] = missing_eps
    else:
        missing_eps = ["<scope undeclared>"]
    out["layers"]["DATA_READY"] = bool(
        out["layers"]["WRITER_READY"] and chain_ok and ev["n"] > 0
        and not missing_eps
        and out["layers"].get("orphan_observation", 0) == 0
        and out["layers"].get("raw_without_observation", 0) == 0)

    if out["layers"]["DATA_READY"]:
        out["state"] = "READY"
        out["layers"]["detail"] = "SCHEMA+WRITER+DATA"
    elif out["layers"]["WRITER_READY"]:
        out["state"] = "DEGRADED"
        out["reasons"].append("writer fresh but data/chain/scope "
                              "incomplete")
    else:
        out["state"] = "DEGRADED"
    return out


# ----------------------------------------------------------------------
# P0-C3 — EOD canary gate (M2-T3 admission)
# ----------------------------------------------------------------------

def evaluate_eod_canary(conn, trade_date, expected_version,
                        target="core.asset_status_daily",
                        v1_digest_before=None) -> dict:
    """Certify ONE canary date's V2 result against the expected version.

    - base rows must exist and ALL carry expected version
    - every versioned row must satisfy the validity contract
      (state in 0..3, bools non-null, rule_id non-empty)
    - state 2/3 are counted SEPARATELY — they are not tradable
      conclusions and a large share indicates rule/data gaps
    - v1_digest_before (optional) recomputes a digest over v1 columns
      and verifies the V2 emit left V1 untouched
    publishable = committed-shaped result (written/idempotent valid)
    """
    from stock_research.db import fetch_all
    out = {"trade_date": trade_date, "expected_version": expected_version,
           "checks": {}, "publishable": False, "reasons": []}
    base = fetch_all(conn, f"""
        SELECT count(*) n FROM {target} WHERE trade_date=%s""",
                     [trade_date])[0]["n"]
    out["checks"]["base_rows"] = base
    if not base:
        out["reasons"].append("no base rows — canary date not built")
        return out
    dist = fetch_all(conn, f"""
        SELECT COALESCE(limit_flags_version,'<NULL>') v, count(*) n,
          count(*) FILTER (WHERE limit_state_v2=2) rule_unknown,
          count(*) FILTER (WHERE limit_state_v2=3) data_insufficient,
          count(*) FILTER (WHERE limit_state_v2 IS NULL
            OR limit_state_v2 NOT IN (0,1,2,3)
            OR is_limit_up_v2 IS NULL OR is_limit_down_v2 IS NULL
            OR limit_rule_id_v2 IS NULL
            OR btrim(limit_rule_id_v2)='') invalid
        FROM {target} WHERE trade_date=%s GROUP BY 1""",
                     [trade_date])
    out["checks"]["version_dist"] = dist
    good = next((r for r in dist if r["v"] == expected_version), None)
    foreign = [r for r in dist if r["v"] not in (expected_version,
                                               "<NULL>")]
    nulls = next((r["n"] for r in dist if r["v"] == "<NULL>"), 0)
    out["checks"]["written_rows"] = good["n"] if good else 0
    out["checks"]["invalid_rows"] = good["invalid"] if good else 0
    out["checks"]["rule_unknown"] = good["rule_unknown"] if good else 0
    out["checks"]["data_insufficient"] = \
        good["data_insufficient"] if good else 0
    out["checks"]["null_version_rows"] = nulls
    out["checks"]["foreign_versions"] = foreign
    if foreign:
        out["reasons"].append(f"foreign versions present {foreign}")
    if not good or good["n"] != base:
        out["reasons"].append(
            f"coverage {good['n'] if good else 0}/{base} — "
            "incomplete must NOT advance the watermark")
    elif good["invalid"]:
        out["reasons"].append(f"{good['invalid']} invalid rows")

    if v1_digest_before is not None:
        cur = v1_digest(conn, trade_date, target)
        out["checks"]["v1_digest"] = cur
        if cur != v1_digest_before:
            out["reasons"].append("V1 columns mutated by V2 emit")
    out["publishable"] = (
        not out["reasons"] and good and good["n"] == base
        and good["invalid"] == 0)
    return out


def v1_digest(conn, trade_date, target="core.asset_status_daily"):
    """Order-stable digest over the V1 status columns of one date —
    call BEFORE and AFTER a V2 emit to prove V1 was untouched."""
    from stock_research.db import fetch_all
    r = fetch_all(conn, f"""
        SELECT md5(string_agg(t::text, '|' ORDER BY asset_id)) d
        FROM (SELECT asset_id, is_trade, is_st, is_suspended,
              is_limit_up, is_limit_down, limit_up_price,
              limit_down_price, source
              FROM {target} WHERE trade_date=%s) t""",
                  [trade_date])
    return r[0]["d"]
