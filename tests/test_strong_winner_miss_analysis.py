from pathlib import Path

import pandas as pd

from stock_research.strong_winner_miss_analysis import (
    build_strong_winner_miss_analysis_from_frames,
    scan_strong_winner_60d,
)


def _bars() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=8, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame(
        [
            *[
                {
                    "asset_id": "A",
                    "ts_code": "000001.SZ",
                    "trade_date": date,
                    "open": 10 + index,
                    "high": [10.5, 11, 13, 16, 20.2, 21, 19, 18][index],
                    "low": [10, 10.2, 11, 12, 13, 14, 15, 16][index],
                    "close": [10.2, 10.8, 12, 15, 19, 20, 18, 17][index],
                    "preclose": None,
                    "volume": 1000,
                    "amount": 100000,
                    "turnover_rate": 1.0,
                    "pct_chg": 0.0,
                    "is_st": False,
                    "trade_status": "1",
                }
                for index, date in enumerate(dates)
            ],
            *[
                {
                    "asset_id": "B",
                    "ts_code": "000002.SZ",
                    "trade_date": date,
                    "open": 10,
                    "high": 12,
                    "low": 10,
                    "close": 11,
                    "preclose": None,
                    "volume": 1000,
                    "amount": 100000,
                    "turnover_rate": 1.0,
                    "pct_chg": 0.0,
                    "is_st": False,
                    "trade_status": "1",
                }
                for date in dates
            ],
        ]
    )


def test_scan_strong_winner_60d_detects_low_to_future_high_double():
    winners = scan_strong_winner_60d(_bars(), window_days=5, threshold=1.0)

    assert winners["asset_id"].tolist() == ["A"]
    row = winners.iloc[0]
    assert row["segment_start_date"] == "2025-01-01"
    assert row["double_confirm_date"] == "2025-01-05"
    assert row["segment_peak_date"] == "2025-01-06"
    assert row["days_to_double"] == 4
    assert row["low_to_peak_return"] >= 1.0


def test_build_strong_winner_miss_analysis_classifies_capture_and_miss_reasons():
    bars = _bars()
    diagnostics = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "Alpha",
                "score_rank": 8,
                "watch_group": "high_odds_burst_watch",
                "event_structure": "trend_continuation_candidate",
                "diagnostic_reason": "high_odds_burst_watch:trend_continuation_candidate",
                "risk_note": "",
                "opportunity_note": "trend_continuation_candidate",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Beta",
                "score_rank": 4,
                "watch_group": "candidate",
                "event_structure": "",
                "diagnostic_reason": "candidate:unknown",
                "risk_note": "",
                "opportunity_note": "",
            },
        ]
    )
    must_watch = diagnostics.iloc[[0]].copy()

    result = build_strong_winner_miss_analysis_from_frames(
        bars=bars,
        diagnostics_rows=diagnostics,
        must_watch_rows=must_watch,
        start_date="2025-01-01",
        end_date="2025-01-08",
        window_days=5,
        threshold=1.0,
    )

    winners = result["strong_winners"]
    analysis = result["miss_analysis"]
    summary = result["summary"]

    assert len(winners) == 1
    assert analysis.iloc[0]["capture_status"] == "captured_pre_double"
    assert analysis.iloc[0]["first_watch_group"] == "high_odds_burst_watch"
    assert summary.loc[summary["metric"].eq("strong_winner_count"), "value"].iloc[0] == 1


def test_build_strong_winner_miss_analysis_separates_missing_diagnostics_window_from_topn_miss():
    bars = _bars()
    bars.loc[(bars["asset_id"] == "A") & (bars["trade_date"].isin(["2025-01-01", "2025-01-02"])), "low"] = 30
    bars.loc[(bars["asset_id"] == "A") & (bars["trade_date"] == "2025-01-03"), "low"] = 10
    diagnostics = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-01",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Beta",
                "score_rank": 1,
                "watch_group": "candidate",
            },
            {
                "trade_date": "2025-01-08",
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Beta",
                "score_rank": 1,
                "watch_group": "candidate",
            }
        ]
    )

    result = build_strong_winner_miss_analysis_from_frames(
        bars=bars,
        diagnostics_rows=diagnostics,
        must_watch_rows=pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        window_days=5,
        threshold=1.0,
    )

    assert result["miss_analysis"].iloc[0]["capture_status"] == "missed"
    assert result["miss_analysis"].iloc[0]["miss_reason"] == "outside_diagnostics_date_range"


def test_build_strong_winner_miss_analysis_writes_outputs(tmp_path: Path):
    result = build_strong_winner_miss_analysis_from_frames(
        bars=_bars(),
        diagnostics_rows=pd.DataFrame(),
        must_watch_rows=pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        window_days=5,
        threshold=1.0,
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["strong_winners"]).exists()
    assert Path(result["paths"]["miss_analysis"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()
    assert result["miss_analysis"].iloc[0]["capture_status"] == "missed"


def test_analyze_strong_winner_misses_cli_prints_outputs(monkeypatch, capsys, tmp_path: Path):
    from stock_research import cli

    def fake_runner(**kwargs):
        return {
            "paths": {
                "strong_winners": tmp_path / "strong.csv",
                "miss_analysis": tmp_path / "miss.csv",
                "summary": tmp_path / "summary.csv",
                "report": tmp_path / "report.md",
            },
            "miss_analysis": pd.DataFrame({"asset_id": ["A", "B"]}),
        }

    monkeypatch.setattr(cli, "run_strong_winner_miss_analysis", fake_runner)
    cli.main_for_args(
        [
            "analyze-strong-winner-misses",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-31",
            "--diagnostics-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path),
        ]
    )

    out = capsys.readouterr().out
    assert "strong_winner_miss_analysis|strong_winners|" in out
    assert "strong_winner_miss_analysis|miss_analysis|" in out
    assert "strong_winner_miss_analysis|rows|2" in out
