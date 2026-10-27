"""DATA-R3-M1 — implementation-layer tests (isolated shadow objects)."""
import json
import sys

import pytest

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import p21_forensics_v2 as fx  # noqa: E402
import stock_research.financial_version_store as fvs  # noqa: E402
from stock_research.data_integrity_gate import combine  # noqa: E402
from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.eod_v2_writer import (  # noqa: E402
    _check_target, emit_eod_v2_flags)
from stock_research.financial_pit import financial_pit_at  # noqa: E402

S = "m1_shadow"
T = f"{S}.asset_status_daily"


@pytest.fixture(scope="module")
def conn():
    with connect(SETTINGS.research_service) as c:
        yield c


# ---- M1-B gate ----

def test_check_target_passes_on_shadow(conn):
    assert _check_target(conn, T) == []


def test_check_target_fails_on_prod_shape(conn):
    missing = _check_target(conn, "core.asset_status_daily")
    assert "is_limit_up_v2" in missing


def test_switch_off_blocks(conn):
    r = emit_eod_v2_flags(conn, "2026-10-20", T, "vX", enabled=False)
    assert r["status"] == "blocked"
    conn.rollback()


def test_version_conflict_blocks(conn):
    r = emit_eod_v2_flags(conn, "2026-10-21", T, "pit_rules_vX",
                          enabled=True)
    assert r["status"] == "blocked"
    assert any("version conflict" in x for x in r["reasons"])
    conn.rollback()


def test_missing_base_blocks(conn):
    r = emit_eod_v2_flags(conn, "2026-10-25", T, "pit_rules_v1",
                          enabled=True)
    assert r["status"] == "blocked"
    conn.rollback()


def test_bad_identifier_rejected(conn):
    with pytest.raises(ValueError):
        emit_eod_v2_flags(conn, "2026-10-20", "x; drop table y", "v",
                          enabled=True)


# ---- M1-C version store helpers ----

def test_fingerprint_stable_and_sensitive():
    a = {"NETPROFIT": 100.0, "OPERATE_INCOME": 500}
    b = dict(a)
    c = dict(a, NETPROFIT=100.00001)   # inside precision tolerance
    d = dict(a, NETPROFIT=250.0)
    assert fvs.fingerprint(a) == fvs.fingerprint(b)
    assert fvs.fingerprint(a) == fvs.fingerprint(c)
    assert fvs.fingerprint(a) != fvs.fingerprint(d)


def test_field_class_levels():
    a = {"X": 100.0, "Y": 1}
    assert fvs.field_class(a, dict(a)) == "identical"
    assert fvs.field_class(a, {**a, "X": 100.00001}) == "precision_only"
    assert fvs.field_class(a, {**a, "X": 250.0}) == "metrics_changed"
    assert fvs.field_class(a, {**a, "Y": None}) == "null_asymmetry"
    assert fvs.field_class(a, {**a, "Z": 9}) == "field_missing"


def test_ddl_idempotent_and_safe(conn):
    for stmt in fvs.ddl(S).split(";"):
        if stmt.strip():
            from stock_research.db import execute
            execute(conn, stmt)  # second application must not error
    conn.rollback()
    with pytest.raises(ValueError):
        fvs.ddl("bad;injection")


def test_finver_chain_in_shadow(conn):
    rows = fetch_all(conn, f"""
        SELECT c.n_versions, count(e.version_event_id) ev
        FROM {S}.finver_key_chain c
        JOIN {S}.finver_event e
          ON e.asset_id=c.asset_id AND e.statement_type=c.statement_type
         AND e.endpoint=c.endpoint AND e.report_period=c.report_period
         AND e.report_type=c.report_type
        GROUP BY c.asset_id, c.statement_type, c.endpoint,
                 c.report_period, c.report_type, c.n_versions""")
    if not rows:
        pytest.skip("finver shadow not populated — run m1_finver_drills")
    for r in rows:
        assert r["ev"] == r["n_versions"]


def test_no_initial_marked_verified(conn):
    rows = fetch_all(conn, f"""
        SELECT count(*) n FROM {S}.finver_event
        WHERE announcement_evidence='unknown'
          AND announcement_date IS NOT NULL""")
    assert rows[0]["n"] == 0


# ---- M1-D credibility tiers ----

def test_evidence_levels(conn):
    r = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    assert r.version_evidence_level in ("VERIFIED", "INFERRED",
                                        "UNKNOWN")
    assert r.data_version == r.selected_statement_version


def test_initial_unverifiable_not_verified(conn):
    rows = fetch_all(conn, """
        SELECT asset_id, report_period::text rp
        FROM finance.income_statement
        WHERE announcement_date > report_period + interval '240 days'
        GROUP BY 1,2,source
        HAVING count(DISTINCT announcement_date)=1 LIMIT 1""")
    if not rows:
        pytest.skip("no re-announcement rows")
    r = financial_pit_at(conn, rows[0]["asset_id"], "2027-01-01",
                         "income", report_period=rows[0]["rp"],
                         version_policy="initial_public")
    assert r.version_evidence_level == "UNKNOWN"
    assert r.missing_reason


# ---- M1-E gate combine ----

def test_gate_combine_never_promotes_blocked():
    assert combine("READY", "BLOCKED") == "BLOCKED"
    assert combine("READY", "DEGRADED") == "DEGRADED"
    assert combine("READY", "READY") == "READY"
    assert combine() == "READY"


# ---- parser regression (re-used P2.1 final) ----

def test_parser_still_expands_lists():
    pl = [{"REPORT_DATE": "2025-12-31", "NETPROFIT": 1},
          {"REPORT_DATE": "2025-09-30", "NETPROFIT": 2}]
    assert len(fx.to_rows(pl)) == 2
    assert [fx.pkey(r) for r in fx.to_rows(pl)] == \
        ["2025-12-31", "2025-09-30"]
