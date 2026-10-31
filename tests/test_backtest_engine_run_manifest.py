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
             "calendar": tmp_path / "calendar.csv"}
    pd.DataFrame(targets).to_csv(paths["targets"], index=False)
    pd.DataFrame(bars).to_csv(paths["bars"], index=False)
    pd.DataFrame({"trade_date": days}).to_csv(paths["calendar"], index=False)
    return paths


def test_t10_same_manifest_inputs_give_identical_outputs(tmp_path):
    paths = _write_inputs(tmp_path)
    kwargs = dict(targets_path=paths["targets"], bars_path=paths["bars"],
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
    assert set(det["inputs"]) == {"targets", "bars", "calendar"}
    assert "git_commit" in manifest["runtime"]
