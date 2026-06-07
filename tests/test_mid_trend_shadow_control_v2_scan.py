from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_shadow_control_v2_scan import (
    build_mid_trend_shadow_control_v2_scan_from_frames,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-03", "2025-01-06", "2025-01-13", "2025-01-20"]
    for day_index, trade_date in enumerate(dates):
        ranking = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        if day_index >= 1:
            ranking = ["F", "A", "B", "C", "D", "E", "G", "H", "I", "J"]
        if day_index >= 2:
            ranking = ["G", "F", "A", "B", "C", "D", "E", "H", "I", "J"]
        for rank, asset_id in enumerate(ranking, start=1):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "ts_code": f"000{rank:03d}.SZ",
                    "industry_name": "计算机、通信和其他电子设备制造业",
                    "market_regime": "mainline",
                    "mainline_status": "sustained_mainline",
                    "mainline_context": "mainline",
                    "industry_mainline_score_v1": 0.7,
                    "mid_trend_layer": "stable_trend_watch",
                    "mid_trend_funnel_score": 100 - rank,
                    "score_rank": rank,
                    "volatility_20_score": 40,
                    "trend_r2_20_score": 90,
                    "ret_20_score": 80,
                    "max_drawdown_20_score": 70,
                }
            )
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-02-14", freq="B")
    for i, trade_date in enumerate(dates):
        for asset_id in list("ABCDEFGHIJ"):
            close = 10 + i * 0.1
            if asset_id == "F":
                close = 12 + i * 0.05
            rows.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "open": close,
                    "close": close,
                    "amount": 1000000,
                    "trade_status": "1",
                }
            )
    return pd.DataFrame(rows)


def test_control_v2_scan_outputs_baseline_buffer_and_freeze_variants(tmp_path: Path):
    result = build_mid_trend_shadow_control_v2_scan_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-02-14",
        output_dir=tmp_path,
    )

    summary = result["summary"]
    assert {
        "baseline_max2",
        "sell_buffer_top8",
        "sell_buffer_top10",
        "drawdown_freeze_to_1",
        "drawdown_freeze_to_0",
        "sell_buffer_top10_freeze_to_1",
    }.issubset(set(summary["variant_name"]))
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_control_v2_scan(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": pd.DataFrame([{"variant_name": "baseline_max2"}]),
            "paths": {
                "summary": str(tmp_path / "summary.csv"),
                "equity_curve": str(tmp_path / "equity.csv"),
                "positions": str(tmp_path / "positions.csv"),
                "trades": str(tmp_path / "trades.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_shadow_control_v2_scan", fake_run)

    cli.main_for_args(
        [
            "scan-mid-trend-shadow-control-v2",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-02-14",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["drawdown_threshold"] == 0.08
    assert captured["transaction_cost_bps"] == 20.0
    out = capsys.readouterr().out
    assert "mid_trend_shadow_control_v2|summary|" in out
