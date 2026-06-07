from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_shadow_replacement_scan import (
    build_mid_trend_shadow_replacement_scan_from_frames,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-03", "2025-01-06", "2025-01-07", "2025-01-13", "2025-01-14"]
    industries = [
        "计算机、通信和其他电子设备制造业",
        "电气机械和器材制造业",
        "有色金属冶炼和压延加工业",
        "专用设备制造业",
        "通用设备制造业",
        "医药制造业",
        "仪器仪表制造业",
        "金属制品业",
    ]
    for day_index, trade_date in enumerate(dates):
        ranking = ["A", "B", "C", "D", "E", "F", "G", "H"]
        if trade_date >= "2025-01-13":
            ranking = ["F", "A", "B", "C", "D", "E", "G", "H"]
        for rank, asset_id in enumerate(ranking, start=1):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "ts_code": f"{rank:06d}.SZ",
                    "stock_name": f"Stock{asset_id}",
                    "industry_name": industries[(rank - 1) % len(industries)],
                    "market_regime": "mainline",
                    "mainline_status": "sustained_mainline",
                    "mainline_context": "mainline",
                    "industry_mainline_score_v1": 0.7,
                    "mid_trend_layer": "stable_trend_watch",
                    "mid_trend_funnel_score": 100 - rank + day_index,
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
    dates = pd.date_range("2025-01-03", "2025-01-31", freq="B")
    for day_index, trade_date in enumerate(dates):
        for asset_index, asset_id in enumerate(["A", "B", "C", "D", "E", "F", "G", "H"], start=1):
            close = 10.0 + day_index * (0.10 + asset_index * 0.01)
            if asset_id == "F" and trade_date >= pd.Timestamp("2025-01-13"):
                close = 13.0 - (day_index - 6) * 0.6
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


def test_replacement_scan_builds_topn_replacement_cost_grid(tmp_path: Path):
    result = build_mid_trend_shadow_replacement_scan_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-01-31",
        top_n_values=[5, 8],
        max_weekly_replacement_values=[1, 2, 3],
        transaction_cost_bps_values=[10.0, 20.0],
        output_dir=tmp_path,
    )

    summary = result["summary"]
    assert len(summary) == 12
    assert set(summary["top_n"]) == {5, 8}
    assert set(summary["max_weekly_replacements"]) == {1, 2, 3}
    assert set(summary["transaction_cost_bps"]) == {10.0, 20.0}
    assert summary["variant_name"].str.contains("max_replacements").all()
    assert summary["scan_rank"].tolist() == sorted(summary["scan_rank"].tolist())
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_replacement_scan(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": pd.DataFrame([{"top_n": 5, "max_weekly_replacements": 2}]),
            "paths": {
                "summary": str(tmp_path / "summary.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_shadow_replacement_scan", fake_run)

    cli.main_for_args(
        [
            "scan-mid-trend-shadow-replacements",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--top-n-values",
            "5,8",
            "--max-weekly-replacements-values",
            "1,2,3",
            "--transaction-cost-bps-values",
            "10,20",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["top_n_values"] == [5, 8]
    assert captured["max_weekly_replacement_values"] == [1, 2, 3]
    assert captured["transaction_cost_bps_values"] == [10.0, 20.0]
    out = capsys.readouterr().out
    assert "mid_trend_shadow_replacement_scan|summary|" in out
