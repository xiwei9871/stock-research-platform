import json
import math

import pandas as pd

from stock_research.backtest_engine import RealisticExecutionConfig, execute_target_weights
from stock_research.backtest_engine.adapters import signal_schedule
from stock_research.backtest_engine.snapshot import RAW_FILES, build_engine_bars

DAYS = ["2023-08-24", "2023-08-25", "2023-08-28", "2023-08-29"]


def _raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    bars, status = [], []
    spec = {"CN:SH:600000": [10.0, 10.5, 10.4, 10.6],   # main board 10%
            "CN:SZ:300001": [20.0, 21.0, 25.2, 25.0],   # chinext 20%
            "CN:SH:600002": [5.0, 5.1, 5.0, 5.2]}       # ST 5%
    for asset, closes in spec.items():
        prev = closes[0]
        for k, (day, close) in enumerate(zip(DAYS, closes)):
            bars.append({"asset_id": asset, "trade_date": day, "open": close, "high": close,
                         "low": close, "close": close,
                         "preclose": None if (asset == "CN:SH:600000" and k == 1) else prev,
                         "volume": 1e6, "amount": 1e7, "trade_status": "1", "adjust_type": "raw"})
            if not (asset == "CN:SZ:300001" and k == 3):          # one missing status row
                status.append({"asset_id": asset, "trade_date": day, "is_trade": True,
                               "is_st": asset == "CN:SH:600002", "is_suspended": False})
            prev = close
    pd.DataFrame(bars).to_csv(raw / "bars_raw.csv", index=False)
    pd.DataFrame(status).to_csv(raw / "asset_status.csv", index=False)
    pd.DataFrame([
        {"asset_id": "CN:SH:600000", "symbol": "600000", "exchange": "SH", "board": "main",
         "is_star": False, "is_chinext": False, "is_beijing": False, "list_date": "1999-11-10",
         "delist_date": None},
        {"asset_id": "CN:SZ:300001", "symbol": "300001", "exchange": "SZ", "board": "chinext",
         "is_star": False, "is_chinext": True, "is_beijing": False, "list_date": "2009-10-30",
         "delist_date": None},
        {"asset_id": "CN:SH:600002", "symbol": "600002", "exchange": "SH", "board": "main",
         "is_star": False, "is_chinext": False, "is_beijing": False, "list_date": "2000-01-01",
         "delist_date": None},
    ]).to_csv(raw / "asset_master.csv", index=False)
    pd.DataFrame([{"asset_id": a, "trade_date": d, "hfq_factor": 1.0, "source_version": "v"}
                  for a in spec for d in DAYS]).to_csv(raw / "adjustment_factor.csv", index=False)
    pd.DataFrame([{"exchange": ex, "trade_date": d} for ex in ("SH", "SZ") for d in DAYS]
                 ).to_csv(raw / "trading_calendar.csv", index=False)
    return raw


def test_build_engine_bars_derives_limits_with_tradeability_rules(tmp_path):
    raw = _raw(tmp_path)
    manifest = build_engine_bars(raw, tmp_path / "snap")
    bars = pd.read_csv(tmp_path / "snap" / "bars.csv", dtype={"asset_id": str}).set_index(
        ["asset_id", "trade_date"])
    assert bars.loc[("CN:SH:600000", DAYS[2]), "limit_up_price"] == round(10.5 * 1.1, 2)
    assert bars.loc[("CN:SZ:300001", DAYS[2]), "limit_up_price"] == round(21.0 * 1.2, 2)
    # 5.1 * 1.05 = 5.355 -> exchange rounds half up to 5.36 (Python round() gives 5.35
    # only because of binary float representation)
    assert bars.loc[("CN:SH:600002", DAYS[2]), "limit_up_price"] == 5.36
    assert math.isnan(bars.loc[("CN:SH:600000", DAYS[1]), "limit_up_price"])   # no preclose
    assert pd.isna(bars.loc[("CN:SZ:300001", DAYS[3]), "is_suspended"])       # no status row
    q = manifest["quality"]
    assert q["preclose_missing_rows"] == 1 and q["status_missing_rows"] == 1
    assert set(manifest["raw_inputs"]) == set(RAW_FILES)
    assert manifest["snapshot_id"].startswith("bars:")
    saved = json.loads((tmp_path / "snap" / "snapshot_manifest.json").read_text())
    assert saved["outputs"] == manifest["outputs"]


def test_prepared_bars_feed_engine_and_fail_closed(tmp_path):
    raw = _raw(tmp_path)
    build_engine_bars(raw, tmp_path / "snap")
    bars = pd.read_csv(tmp_path / "snap" / "bars.csv", dtype={"asset_id": str})
    cal = pd.read_csv(tmp_path / "snap" / "calendar.csv")["trade_date"].tolist()
    tw = pd.DataFrame([{"signal_date": DAYS[0], "asset_id": "CN:SH:600000", "target_weight": 0.3,
                        "strategy_id": "t"},
                       {"signal_date": DAYS[1], "asset_id": "CN:SZ:300001", "target_weight": 0.3,
                        "strategy_id": "t"},
                       {"signal_date": DAYS[2], "asset_id": "CN:SZ:300001", "target_weight": 0.6,
                        "strategy_id": "t"}])
    res = execute_target_weights(tw, bars, cal, RealisticExecutionConfig(),
                                 signal_schedule=signal_schedule(DAYS[:3]))
    t = res["trades"].set_index(["execution_date", "asset_id", "side"])
    assert t.loc[(DAYS[1], "CN:SH:600000", "buy"), "rejection_reason"] == "preclose_missing"
    assert t.loc[(DAYS[2], "CN:SZ:300001", "buy"), "rejection_reason"] == "limit_up_at_fill"
    assert t.loc[(DAYS[3], "CN:SZ:300001", "buy"), "rejection_reason"] == "suspension_state_missing"


def test_ipo_window_only_when_calendar_covers_listing(tmp_path):
    from stock_research.backtest_engine.snapshot import limit_prices_for_row
    import datetime as dt
    row = {"trade_date": "2023-08-28", "preclose": 10.0, "exchange": "SH", "symbol": "600999",
           "board": "main", "is_star": False, "is_chinext": False, "is_beijing": False,
           "is_st": False, "list_date": "2023-08-24"}
    days = [dt.date.fromisoformat(d) for d in DAYS]
    up, down, rule = limit_prices_for_row(row, {"SH": days})       # 3rd session -> no limit
    assert math.isinf(up) and down == 0.0
    old = dict(row, list_date="2000-01-01")
    up, _, _ = limit_prices_for_row(old, {"SH": days})             # calendar starts later
    assert up == 11.0
