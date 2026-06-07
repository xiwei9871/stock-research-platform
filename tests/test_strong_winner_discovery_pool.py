from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.strong_winner_discovery_pool import (
    build_strong_winner_discovery_pool_from_frames,
    load_score_rows_for_discovery_pool,
)


def _scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "Alpha",
                "rank": 25,
                "score_total": 90.0,
                "score_components": {"ret_20_score": 95, "volatility_20_score": 20},
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Beta",
                "rank": 120,
                "score_total": 80.0,
                "score_components": {"ret_20_score": 92, "volatility_20_score": 15},
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "C",
                "ts_code": "000003.SZ",
                "stock_name": "Gamma",
                "rank": 420,
                "score_total": 70.0,
                "score_components": {"ret_20_score": 90, "volatility_20_score": 5},
            },
        ]
    )


def _bars() -> pd.DataFrame:
    rows = []
    closes = {
        "A": [10, 11, 12, 13, 14, 15, 16],
        "B": [10, 10.5, 11, 12, 13, 16, 21],
        "C": [10, 9, 8, 7, 7.5, 8, 8.5],
    }
    dates = pd.date_range("2025-01-02", periods=7, freq="D")
    for asset_id, values in closes.items():
        for date, close in zip(dates, values):
            rows.append(
                {
                    "trade_date": date.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "close": close,
                    "high": close * 1.02,
                    "low": close * 0.98,
                }
            )
    return pd.DataFrame(rows)


def _taxonomy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "winner_id": "W1",
                "winner_type": "double_60d",
                "asset_id": "B",
                "window_start": "2025-01-02",
                "window_end": "2025-01-08",
            },
            {
                "winner_id": "W2",
                "winner_type": "burst_20d",
                "asset_id": "C",
                "window_start": "2025-01-02",
                "window_end": "2025-01-08",
            },
        ]
    )


def test_discovery_pool_builds_cumulative_topn_layers_and_forward_metrics():
    result = build_strong_winner_discovery_pool_from_frames(
        score_rows=_scores(),
        market_bars=_bars(),
        strong_winner_taxonomy=_taxonomy(),
        topn_thresholds=[50, 200, 500],
    )

    detail = result["detail"].set_index("asset_id")
    assert detail.loc["A", "score_top50_pool"]
    assert not detail.loc["B", "score_top50_pool"]
    assert detail.loc["B", "score_top200_pool"]
    assert detail.loc["C", "score_top500_pool"]
    assert round(float(detail.loc["B", "future_5d_return"]), 6) == 0.6
    assert detail.loc["B", "winner_type_hits"] == "double_60d"


def test_discovery_pool_summarizes_capture_by_winner_type():
    result = build_strong_winner_discovery_pool_from_frames(
        score_rows=_scores(),
        market_bars=_bars(),
        strong_winner_taxonomy=_taxonomy(),
        topn_thresholds=[50, 200, 500],
    )

    capture = result["capture_by_type"].set_index(["winner_type", "pool_name"])
    assert capture.loc[("double_60d", "score_top200_pool"), "captured_winner_count"] == 1
    assert capture.loc[("burst_20d", "score_top200_pool"), "captured_winner_count"] == 0
    assert capture.loc[("burst_20d", "score_top500_pool"), "captured_winner_count"] == 1


def test_discovery_pool_writes_outputs(tmp_path: Path):
    result = build_strong_winner_discovery_pool_from_frames(
        score_rows=_scores(),
        market_bars=_bars(),
        strong_winner_taxonomy=_taxonomy(),
        topn_thresholds=[50, 200],
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["pool_effectiveness"]).exists()
    assert Path(result["paths"]["capture_by_type"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_strong_winner_discovery_pool(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "detail": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "pool_effectiveness": str(tmp_path / "effectiveness.csv"),
                "capture_by_type": str(tmp_path / "capture.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_strong_winner_discovery_pool", fake_run)

    cli.main_for_args(
        [
            "build-strong-winner-discovery-pool",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-05-01",
            "--score-version",
            "manual_v1",
            "--topn-thresholds",
            "50,200,500",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["topn_thresholds"] == [50, 200, 500]
    out = capsys.readouterr().out
    assert "strong_winner_discovery_pool|detail|" in out
    assert "strong_winner_discovery_pool|rows|1" in out


def test_score_loader_uses_existing_stock_score_daily_columns(monkeypatch):
    captured = {}

    class FakeConn:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    class FakeConnect:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{"trade_date": "2025-01-02", "asset_id": "A", "rank": 1, "score_total": 90}]

    monkeypatch.setattr("stock_research.strong_winner_discovery_pool.connect", fake_connect)
    monkeypatch.setattr("stock_research.strong_winner_discovery_pool.fetch_all", fake_fetch_all)

    rows = load_score_rows_for_discovery_pool(
        start_date="2025-01-01",
        end_date="2025-01-31",
        score_version="manual_v1",
        max_top_n=500,
    )

    assert "ts_code" not in captured["sql"]
    assert "stock_name" not in captured["sql"]
    assert captured["params"] == ["manual_v1", "2025-01-01", "2025-01-31", 500]
    assert rows.iloc[0]["asset_id"] == "A"
