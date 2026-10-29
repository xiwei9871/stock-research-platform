"""Tests for the read-only Market Monitor V2 regime-state service."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.dashboard import market_regime_service as svc  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REAL_DIR = REPO / "docs/market_monitor_v2/data"


def _mini_snapshot(tmp_path: Path) -> str:
    dates = pd.date_range("2026-10-01", periods=6, freq="B")
    snap = pd.DataFrame(index=dates)
    for o in ("alla", "sse", "szse", "cyb"):
        snap[f"{o}_dd120"] = -0.12
        snap[f"{o}_ret20"] = -0.05
        snap[f"{o}_ret60"] = -0.08
        snap[f"{o}_vol60"] = 0.3
        snap[f"{o}_trend"] = -0.5
        snap[f"{o}_regime"] = "DECLINE"
        snap[f"{o}_regime_days"] = 3.0
    snap["amt"] = 1e9
    snap["amt_ratio_5_20"] = 0.9
    snap["amt_ratio_20_60"] = 0.8
    snap["lowvol_streak"] = 5.0
    snap["lowvol20"] = 0.4
    snap["pct_ma60"] = 0.3
    snap["pct_ma60_20"] = 0.3
    snap["pct_ma60_d20"] = -0.1
    snap["up_share"] = 0.4
    snap["emotion"] = 42.0
    snap["breadth_bad_streak"] = 2.0
    snap["mcc_osc"] = -10.0
    snap.index.name = "trade_date"
    snap.to_parquet(tmp_path / "market_regime_snapshot.parquet")

    etf = pd.DataFrame({
        "trade_date": dates[:-1].repeat(3),
        "gkey": ["g1", "g2", "g3"] * (len(dates) - 1),
        "group": ["G1_all_equity", "G2_hs300_head", "G3_other_broad"]
        * (len(dates) - 1),
        "pcyc": "C06",
        "pstate": "WITHDRAWING",
        "flow": -10.0,
        "cum_flow": -100.0,
        "aum": 80.0,
        "pdepth": 1.25,
        "cum_depth_pct": 125.0,
        "ddur": 30.0,
        "eelap": 40.0,
        "vel5": -0.5,
        "vel20": -0.3,
        "outshare20": 0.7,
        "breadth_out": np.nan,
        "idx_level": 5000.0,
        "cum_withdrawal_pct_aum0": 125.0,
    })
    etf.to_parquet(tmp_path / "etf_flow_history.parquet")
    (tmp_path / "etf_cycles.json").write_text(json.dumps(
        {"g1": {"max_depth_pct": 130.0}}))
    return str(tmp_path)


@pytest.fixture()
def snap_dir(tmp_path):
    d = _mini_snapshot(tmp_path)
    svc.clear_snapshot_caches()
    yield d
    svc.clear_snapshot_caches()


def test_payload_shape_and_statuses(snap_dir):
    p = svc.regime_state("2026-10-09", "alla", 30, snapshot_dir=snap_dir)
    assert p["trade_date"] == "2026-10-08"
    mods = p["modules"]
    assert mods["regime"]["regime"] == "DECLINE"
    assert mods["continuity"]["status"] == "READY"
    assert mods["emotion"]["status"] == "READY"
    etf = mods["etf_flow"]
    # etf data ends 2026-10-07, one day before request -> STALE
    assert etf["latest_etf_date"] == "2026-10-07"
    assert etf["status"] == "STALE"
    g1 = etf["groups"]["g1"]
    assert g1["cum_depth_pct"] == 125.0  # >100% reported honestly
    assert g1["inflow_diffusion"] == "DATA_MISSING"
    assert p["boundaries"]["advance_warning"] == "NOT_EVALUATED"


def test_non_trading_date_resolves_prior(snap_dir):
    p = svc.regime_state("2026-10-11", "alla", 10, snapshot_dir=snap_dir)
    assert p["trade_date"] == "2026-10-08"


def test_before_range_missing(snap_dir):
    p = svc.regime_state("2020-01-01", "alla", 10, snapshot_dir=snap_dir)
    assert p["status"] == "DATA_MISSING"


def test_history_rows_are_pit(snap_dir):
    p = svc.regime_state("2026-10-05", "alla", 3, snapshot_dir=snap_dir)
    rows = p["modules"]["history"]["rows"]
    assert len(rows) <= 3
    assert all(r["date"] <= "2026-10-05" for r in rows)


def test_nulls_not_faked_to_zero(snap_dir):
    p = svc.regime_state("2026-10-09", "alla", 10, snapshot_dir=snap_dir)
    g1 = p["modules"]["etf_flow"]["groups"]["g1"]
    assert g1["outflow_diffusion"] == "DATA_MISSING"
    assert g1["outflow_diffusion"] != 0


@pytest.mark.skipif(not REAL_DIR.exists(), reason="snapshot not built")
def test_reconcile_with_m21_frozen_state():
    """Snapshot endpoint must reproduce M2.1 frozen 2026-10-28 state."""
    svc.clear_snapshot_caches()
    p = svc.regime_state("2026-10-28", "alla", 0,
                         snapshot_dir=str(REAL_DIR))
    svc.clear_snapshot_caches()
    frozen = json.loads((REPO / "docs/research/market_risk_m21"
                         / "MARKET_STATE_2026_10_28.json").read_text())
    r = p["modules"]["regime"]
    # alla dd120 -23.75% crosses the -20% DEEP_DECLINE threshold
    assert r["regime"] == "DEEP_DECLINE"
    assert abs(r["dd120"] - frozen["indices"]["alla"]["dd120"]) < 5e-4
    expect = {"sse": "DECLINE", "szse": "DEEP_DECLINE",
              "cyb": "DEEP_DECLINE"}
    for mkt, key in [("sse", "sse"), ("szse", "szse"), ("cyb", "cyb")]:
        pp = svc.regime_state("2026-10-28", mkt, 0,
                              snapshot_dir=str(REAL_DIR))
        svc.clear_snapshot_caches()
        assert pp["modules"]["regime"]["regime"] == expect[mkt]
        assert abs(pp["modules"]["regime"]["dd120"]
                   - frozen["indices"][key]["dd120"]) < 5e-4


@pytest.mark.skipif(not REAL_DIR.exists(), reason="snapshot not built")
def test_pit_etf_depth_replay():
    """ETF depth at a historical date must not change with later data."""
    svc.clear_snapshot_caches()
    p1 = svc.regime_state("2026-06-30", "alla", 0,
                          snapshot_dir=str(REAL_DIR))
    depth_a = (p1["modules"]["etf_flow"]["groups"]["g2"]
               ["cum_withdrawal_pct_aum0"])
    p2 = svc.regime_state("2026-10-28", "alla", 0,
                          snapshot_dir=str(REAL_DIR))
    depth_b = (p2["modules"]["etf_flow"]["groups"]["g2"]
               ["cum_withdrawal_pct_aum0"])
    svc.clear_snapshot_caches()
    assert depth_a is not None and depth_b is not None
    # G2 fixed-denominator withdrawal ~103% of cycle-start AUM in June per
    # R3.1 ledger; ~86% by late October after replenishment
    assert depth_a > depth_b
    assert 95 < depth_a < 115
    assert 75 < depth_b < 95
