"""DATA-R3-P1d.3 — controlled V2 migration rehearsal tests.

Covers the emit_v2_flags guard contract, the loader status_table
parameter (gray read-path), and the four-state qualification_state
mapping (verified / rule_unknown / data_insufficient /
qualification_missing).
"""

import os

import pandas as pd
import pytest


def _db_available() -> bool:
    try:
        from stock_research.config import SETTINGS
        from stock_research.db import connect
        with connect(SETTINGS.research_service):
            pass
        return True
    except Exception:
        return False


NEEDS_DB = pytest.mark.skipif(not _db_available(),
                              reason="research DB unreachable")


# --- qualification_state: four explicit states ------------------------------

def _flags_frame(state_rows):
    return pd.DataFrame(state_rows)


def test_apply_pit_flags_four_states():
    from stock_research.tradeability import apply_pit_flags
    prices = pd.DataFrame({
        "asset_id": ["a1", "a2", "a3", "a4"],
        "trade_date": ["2024-01-02"] * 4,
        "close": [10.0] * 4,
    })
    flags = _flags_frame([
        {"asset_id": "a1", "trade_date": "2024-01-02",
         "shadow_limit_up": False, "shadow_limit_down": False,
         "shadow_rule_unknown": False, "shadow_rule_id": "r1",
         "shadow_state": 1},
        {"asset_id": "a2", "trade_date": "2024-01-02",
         "shadow_limit_up": False, "shadow_limit_down": False,
         "shadow_rule_unknown": True, "shadow_rule_id": "rule_unknown",
         "shadow_state": 2},
        {"asset_id": "a3", "trade_date": "2024-01-02",
         "shadow_limit_up": False, "shadow_limit_down": False,
         "shadow_rule_unknown": True, "shadow_rule_id": "r1",
         "shadow_state": 3},
        # a4 deliberately absent -> qualification_missing
    ])
    out = apply_pit_flags(prices, flags)
    st = dict(zip(out["asset_id"], out["qualification_state"]))
    assert st["a1"] == "verified"
    assert st["a2"] == "rule_unknown"
    assert st["a3"] == "data_insufficient"
    assert st["a4"] == "qualification_missing"
    for a in ("a2", "a3", "a4"):
        row = out[out.asset_id == a].iloc[0]
        assert row["limit_state_missing"] is True or row["limit_state_missing"]
        assert bool(row["is_limit_up"]) and bool(row["is_limit_down"])
    a1 = out[out.asset_id == "a1"].iloc[0]
    assert not bool(a1["is_limit_up"]) and not bool(a1["is_limit_down"])
    assert a1["limit_rule_id"] == "r1"


# --- emit_v2_flags guard contract --------------------------------------------

@NEEDS_DB
def test_emit_v2_flags_refuses_unmigrated_table():
    from stock_research.config import SETTINGS
    from stock_research.db import connect, execute
    from stock_research.core_data import emit_v2_flags
    with connect(SETTINGS.research_service) as conn:
        execute(conn, "DROP TABLE IF EXISTS p1d3_test.no_v2_table")
        execute(conn, "CREATE SCHEMA IF NOT EXISTS p1d3_test")
        execute(conn, """CREATE TABLE p1d3_test.no_v2_table (
            trade_date date, asset_id text,
            PRIMARY KEY (trade_date, asset_id))""")
        with pytest.raises(RuntimeError, match="lacks v2 contract"):
            emit_v2_flags(conn, "2024-06-03", "2024-06-03",
                          "p1d3_test.no_v2_table")
        # production table (no v2 columns yet) must also refuse
        with pytest.raises(RuntimeError, match="lacks v2 contract"):
            emit_v2_flags(conn, "2024-06-03", "2024-06-03",
                          "core.asset_status_daily")
        execute(conn, "DROP TABLE p1d3_test.no_v2_table")


def test_emit_v2_flags_rejects_bad_identifier():
    from stock_research.core_data import emit_v2_flags
    with pytest.raises(ValueError):
        emit_v2_flags(None, "2024-01-01", "2024-01-02",
                      "core.asset_status_daily; DROP TABLE x")


# --- loader status_table parameter -------------------------------------------

def test_status_table_validation():
    from stock_research.vectorized_topn_backtest import (
        load_vectorized_topn_inputs)
    with pytest.raises(ValueError, match="status_table"):
        load_vectorized_topn_inputs(
            "2024-01-01", "2024-01-02",
            status_table="core.asset_status_daily;--")
    with pytest.raises(ValueError, match="status_table"):
        load_vectorized_topn_inputs(
            "2024-01-01", "2024-01-02", status_table="asset_status_daily")


@NEEDS_DB
def test_shadow_migration_log_all_done():
    """Full-scale rehearsal completed: every year batch checkpointed."""
    from stock_research.config import SETTINGS
    from stock_research.db import connect, fetch_all
    with connect(SETTINGS.research_service) as conn:
        r = fetch_all(conn, """
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE status='done') AS done,
                   sum(rows_total) AS rows
            FROM p1d3_shadow.migration_log""")
    assert int(r[0]["done"]) >= 37
    assert int(r[0]["rows"]) >= 17_000_000


@NEEDS_DB
def test_emit_updates_only_no_insert_on_prodshape():
    """Pure-UPDATE emit must not insert rows — keys absent from target stay
    absent (production shape contract)."""
    from stock_research.config import SETTINGS
    from stock_research.db import connect, execute, fetch_all
    from stock_research.core_data import emit_v2_flags
    with connect(SETTINGS.research_service) as conn:
        execute(conn, "DROP TABLE IF EXISTS p1d3_test.emit_update_only")
        execute(conn, "CREATE SCHEMA IF NOT EXISTS p1d3_test")
        execute(conn, """CREATE TABLE p1d3_test.emit_update_only (
            trade_date date NOT NULL, asset_id text NOT NULL,
            is_limit_up boolean NOT NULL DEFAULT false,
            is_limit_down boolean NOT NULL DEFAULT false,
            is_suspended boolean NOT NULL DEFAULT false,
            is_limit_up_v2 boolean, is_limit_down_v2 boolean,
            limit_state_v2 smallint, limit_rule_id_v2 text,
            limit_flags_version text,
            PRIMARY KEY (trade_date, asset_id))""")
        n = emit_v2_flags(conn, "2024-06-03", "2024-06-03",
                          "p1d3_test.emit_update_only")
        cnt = fetch_all(conn, """SELECT count(*) AS n
            FROM p1d3_test.emit_update_only""")[0]["n"]
        execute(conn, "DROP TABLE p1d3_test.emit_update_only")
        conn.commit()
    assert int(cnt) == 0  # zero pre-existing rows -> zero updates, no insert


@NEEDS_DB
def test_verified_v2_gray_read_on_shadow_table():
    """Shadow rehearsal table must drive verified_v2 identically to
    corrected_shadow on verified keys (gray read-path proof)."""
    from stock_research.config import SETTINGS
    from stock_research.db import connect, fetch_all
    from stock_research.vectorized_topn_backtest import (
        load_vectorized_topn_inputs)
    exists = False
    try:
        with connect(SETTINGS.research_service) as conn:
            r = fetch_all(conn, """SELECT count(*) AS n,
                count(*) FILTER (WHERE limit_state_v2 IS NOT NULL) AS v2
                FROM p1d3_shadow.asset_status_daily_v2
                WHERE trade_date BETWEEN '2024-06-01' AND '2024-06-30'""")
            exists = r[0]["v2"] > 0
    except Exception:
        pass
    if not exists:
        pytest.skip("p1d3 shadow table not populated yet")
    scores_v2, prices_v2 = load_vectorized_topn_inputs(
        "2024-06-03", "2024-06-05", score_version="manual_v1",
        qualification_mode="verified_v2",
        status_table="p1d3_shadow.asset_status_daily_v2")
    scores_cs, prices_cs = load_vectorized_topn_inputs(
        "2024-06-03", "2024-06-05", score_version="manual_v1",
        qualification_mode="corrected_shadow")
    for df in (prices_v2, prices_cs):
        df["trade_date"] = df["trade_date"].astype(str)
    merged = prices_v2.merge(
        prices_cs[["asset_id", "trade_date", "is_limit_up",
                   "is_limit_down", "qualification_state"]],
        on=["asset_id", "trade_date"], suffixes=("_v2", "_cs"))
    ok = merged[~merged["limit_state_missing"]]
    assert len(ok) > 0, "expected some verified rows in window"
    mism = ok[(ok["is_limit_up_v2"] != ok["is_limit_up_cs"]) |
              (ok["is_limit_down_v2"] != ok["is_limit_down_cs"])]
    assert len(mism) == 0, f"v2/corrected flag mismatch: {mism.head()}"
    # every missing row must be a state != verified on corrected side
    missing_rows = merged[merged["limit_state_missing"]]
    bad = missing_rows[missing_rows["qualification_state"] == "verified"]
    assert len(bad) == 0
