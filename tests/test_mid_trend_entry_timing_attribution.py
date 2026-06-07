from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_entry_timing_attribution import (
    build_mid_trend_entry_timing_attribution_from_frames,
)


def _attribution_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "variant_name": "top5_adaptive_daily_check_max2_v1",
                "trade_date": "2025-03-03",
                "bought_asset_id": "BAD",
                "sold_asset_id": "OLD",
                "bad_rebalance_reasons": "bad_buy",
                "bought_next_10d_return": -0.08,
                "replacement_alpha_10d": -0.12,
            },
            {
                "variant_name": "top5_adaptive_daily_check_max2_v1",
                "trade_date": "2025-03-03",
                "bought_asset_id": "GOOD",
                "sold_asset_id": "OLD2",
                "bad_rebalance_reasons": "",
                "bought_next_10d_return": 0.10,
                "replacement_alpha_10d": 0.07,
            },
        ]
    )


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-01", periods=62, freq="B")
    for idx, trade_date in enumerate(dates):
        rows.append({"trade_date": trade_date.date().isoformat(), "asset_id": "BAD", "close": 10.0 + idx * 0.28})
        rows.append({"trade_date": trade_date.date().isoformat(), "asset_id": "GOOD", "close": 20.0 + idx * 0.05})
    return pd.DataFrame(rows)


def _valuation() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-01", periods=62, freq="B")
    for idx, trade_date in enumerate(dates):
        rows.append({"trade_date": trade_date.date().isoformat(), "asset_id": "BAD", "pe_ttm": 20.0 + idx * 0.7})
        rows.append({"trade_date": trade_date.date().isoformat(), "asset_id": "GOOD", "pe_ttm": 18.0 + idx * 0.05})
    return pd.DataFrame(rows)


def test_entry_timing_attribution_flags_high_entry_and_pe_expansion(tmp_path: Path):
    result = build_mid_trend_entry_timing_attribution_from_frames(
        attribution_detail=_attribution_detail(),
        prices=_prices(),
        valuation=_valuation(),
        output_dir=tmp_path,
    )

    detail = result["entry_timing_detail"].set_index("bought_asset_id")
    assert detail.loc["BAD", "entry_ret_40d"] > 1.0
    assert detail.loc["BAD", "entry_up_100pct_60d"] is True
    assert detail.loc["BAD", "entry_pe_ttm"] > 50
    assert detail.loc["BAD", "entry_pe_ttm_change_40d"] > 1.0
    assert detail.loc["BAD", "entry_timing_risk_label"] == "extended_price_and_pe"
    assert detail.loc["GOOD", "entry_up_100pct_60d"] is False

    contrast = result["entry_timing_contrast"].set_index("group")
    assert {"adaptive_bad_buy", "adaptive_other_buys"}.issubset(set(contrast.index))
    assert contrast.loc["adaptive_bad_buy", "sample_count"] == 1
    assert Path(result["paths"]["entry_timing_detail"]).exists()
    assert Path(result["paths"]["entry_timing_contrast"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_entry_timing_attribution_can_derive_pe_from_fundamental_and_close():
    valuation = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "BAD", "total_share": 100.0, "np_parent_ttm": 1000.0},
            {"trade_date": "2025-03-03", "asset_id": "BAD", "total_share": 100.0, "np_parent_ttm": 1000.0},
        ]
    )

    result = build_mid_trend_entry_timing_attribution_from_frames(
        attribution_detail=_attribution_detail().head(1),
        prices=_prices(),
        valuation=valuation,
    )

    detail = result["entry_timing_detail"].iloc[0]
    assert detail["entry_pe_ttm"] > 2.0


def test_cli_dispatches_entry_timing_attribution(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "entry_timing_detail": pd.DataFrame([{"bought_asset_id": "BAD"}]),
            "paths": {
                "entry_timing_detail": str(tmp_path / "detail.csv"),
                "entry_timing_contrast": str(tmp_path / "contrast.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_entry_timing_attribution", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-entry-timing-attribution",
            "--attribution-detail-path",
            "outputs/research/mid_trend_adaptive_candidate_review_v1/mid_trend_adaptive_candidate_rebalance_attribution_detail.csv",
            "--prices-path",
            "prices.csv",
            "--valuation-path",
            "valuation.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-05-19",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["prices_path"] == "prices.csv"
    assert captured["valuation_path"] == "valuation.csv"
    out = capsys.readouterr().out
    assert "mid_trend_entry_timing_attribution|detail|" in out
