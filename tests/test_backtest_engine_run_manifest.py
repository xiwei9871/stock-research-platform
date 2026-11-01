import json

import pandas as pd

from stock_research.backtest_engine.config import RealisticExecutionConfig
from stock_research.backtest_engine.run import DETERMINISTIC_FILES, run_and_write


def _write_inputs(tmp_path):
    days = ["2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06"]
    bars = []
    for asset, closes in (("A", [10, 10.2, 10.1, 10.4]), ("B", [8, 7.9, 8.1, 8.3])):
        prev = closes[0]
        for day, close in zip(days, closes):
            bars.append({"trade_date": day, "asset_id": asset, "open": close, "high": close,
                         "low": close, "close": close, "volume": 1e6, "preclose": prev,
                         "is_suspended": False, "limit_up_price": round(prev * 1.1, 2),
                         "limit_down_price": round(prev * 0.9, 2), "adj_factor": 1.0,
                         "adjust_type": "raw"})
            prev = close
    targets = [{"signal_date": days[0], "asset_id": "A", "target_weight": 0.5, "strategy_id": "demo"},
               {"signal_date": days[0], "asset_id": "B", "target_weight": 0.4, "strategy_id": "demo"},
               {"signal_date": days[2], "asset_id": "A", "target_weight": 0.9, "strategy_id": "demo"}]
    paths = {"targets": tmp_path / "targets.csv", "bars": tmp_path / "bars.csv",
             "calendar": tmp_path / "calendar.csv", "schedule": tmp_path / "schedule.csv",
             "benchmark": tmp_path / "benchmark.csv"}
    pd.DataFrame({"signal_date": [days[0], days[2]],
                  "signal_ts": [f"{days[0]}T15:00:00+08:00", f"{days[2]}T15:00:00+08:00"]}
                 ).to_csv(paths["schedule"], index=False)
    pd.DataFrame({"date": days[1:], "benchmark_return": [0.001, -0.002, 0.003]}
                 ).to_csv(paths["benchmark"], index=False)
    pd.DataFrame(targets).to_csv(paths["targets"], index=False)
    pd.DataFrame(bars).to_csv(paths["bars"], index=False)
    pd.DataFrame({"trade_date": days}).to_csv(paths["calendar"], index=False)
    return paths


def test_t10_same_manifest_inputs_give_identical_outputs(tmp_path):
    paths = _write_inputs(tmp_path)
    kwargs = dict(targets_path=paths["targets"], bars_path=paths["bars"],
                  schedule_path=paths["schedule"], benchmark_path=paths["benchmark"],
                  signal_provenance="FROZEN_SIGNAL_REPLAY", universe_label="fixture",
                  calendar_path=paths["calendar"], config=RealisticExecutionConfig(),
                  strategy_id="demo", data_snapshot_id="fixture:test")
    m1 = run_and_write(output_dir=tmp_path / "run1", **kwargs)
    m2 = run_and_write(output_dir=tmp_path / "run2", **kwargs)
    assert m1["deterministic"] == m2["deterministic"]
    for name in DETERMINISTIC_FILES:
        assert (tmp_path / "run1" / name).read_bytes() == (tmp_path / "run2" / name).read_bytes()
    manifest = json.loads((tmp_path / "run1" / "run_manifest.json").read_text())
    det = manifest["deterministic"]
    assert det["execution_mode"] == "REALISTIC_A_SHARE"
    assert len(det["config_hash"]) == 64
    assert set(det["inputs"]) == {"targets", "bars", "calendar", "schedule", "benchmark"}
    assert det["signal_provenance"] == "FROZEN_SIGNAL_REPLAY"
    assert det["model"]["corporate_action_model"] == "TOTAL_RETURN_APPROX_FACTOR_REINVEST"
    summary = json.loads((tmp_path / "run1" / "summary.json").read_text())
    assert summary["benchmark_days"] == 3 and "information_ratio" in summary
    assert "git_commit" in manifest["runtime"]
