from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_rebalance_attribution import (
    build_mid_trend_rebalance_attribution_from_frames,
)


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2025-01-06",
                "asset_id": "OLD",
                "side": "sell",
                "previous_weight": 0.2,
                "target_weight": 0.0,
                "delta_weight": -0.2,
                "reason": "weekly_rebalance",
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2025-01-06",
                "asset_id": "NEW",
                "side": "buy",
                "previous_weight": 0.0,
                "target_weight": 0.2,
                "delta_weight": 0.2,
                "reason": "weekly_rebalance",
            },
        ]
    )


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-06", periods=25, freq="B")
    for i, date in enumerate(dates):
        rows.append({"trade_date": date.date().isoformat(), "asset_id": "OLD", "close": 10.0 + i * 0.2})
        rows.append({"trade_date": date.date().isoformat(), "asset_id": "NEW", "close": 10.0 - i * 0.1})
    return pd.DataFrame(rows)


def _equity() -> pd.DataFrame:
    dates = pd.date_range("2025-01-06", periods=25, freq="B")
    rows = []
    for i, date in enumerate(dates):
        equity = 1.0 - i * 0.01
        rows.append(
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "date": date.date().isoformat(),
                "equity": equity,
                "drawdown": equity - 1.0,
                "net_return": -0.01,
            }
        )
    return pd.DataFrame(rows)


def test_rebalance_attribution_flags_sell_fly_and_buy_underperformance(tmp_path: Path):
    result = build_mid_trend_rebalance_attribution_from_frames(
        trades=_trades(),
        prices=_prices(),
        equity=_equity(),
        start_date="2025-01-01",
        end_date="2025-02-28",
        output_dir=tmp_path,
    )

    detail = result["detail"]
    assert len(detail) == 1
    row = detail.iloc[0]
    assert row["sold_asset_id"] == "OLD"
    assert row["bought_asset_id"] == "NEW"
    assert row["replacement_alpha_10d"] < 0
    assert row["bad_rebalance_flag"] is True
    assert "sell_fly" in row["bad_rebalance_reasons"]
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_rebalance_attribution_includes_adaptive_rebalance_reason():
    trades = _trades().copy()
    trades["variant_name"] = "top5_adaptive_daily_check_max2_v1"
    trades["reason"] = "adaptive_rebalance"
    equity = _equity().copy()
    equity["variant_name"] = "top5_adaptive_daily_check_max2_v1"

    result = build_mid_trend_rebalance_attribution_from_frames(
        trades=trades,
        prices=_prices(),
        equity=equity,
        start_date="2025-01-01",
        end_date="2025-02-28",
        variant_name="top5_adaptive_daily_check_max2_v1",
    )

    assert len(result["detail"]) == 1
    assert result["summary"].set_index("metric").loc["rebalance_pair_count", "value"] == 1


def test_cli_dispatches_rebalance_attribution(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "detail": pd.DataFrame([{"trade_date": "2025-01-06"}]),
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_rebalance_attribution", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-rebalance-attribution",
            "--trades-path",
            "outputs/research/mid_trend_shadow_weekly_control_v1/mid_trend_shadow_weekly_control_trades.csv",
            "--equity-path",
            "outputs/research/mid_trend_shadow_weekly_control_v1/mid_trend_shadow_weekly_control_equity.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-05-19",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["start_date"] == "2025-01-01"
    out = capsys.readouterr().out
    assert "mid_trend_rebalance_attribution|detail|" in out
