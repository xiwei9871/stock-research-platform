from pathlib import Path

import pandas as pd

from stock_research.watchlist.effectiveness import (
    build_watchlist_diagnostics_effectiveness_detail,
    build_watchlist_diagnostics_effectiveness_summary,
    run_watchlist_diagnostics_effectiveness_review,
)


def test_build_watchlist_diagnostics_effectiveness_detail_computes_future_returns_and_drawdown():
    diagnostics = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-19",
                "asset_id": "A",
                "watch_group": "opportunity_watch",
                "event_structure": "second_wave_candidate",
            }
        ]
    )
    bars = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-05-19", "close": 10.0, "low": 9.9},
            {"asset_id": "A", "trade_date": "2026-05-20", "close": 10.5, "low": 10.1},
            {"asset_id": "A", "trade_date": "2026-05-21", "close": 10.2, "low": 10.0},
            {"asset_id": "A", "trade_date": "2026-05-22", "close": 10.8, "low": 10.4},
            {"asset_id": "A", "trade_date": "2026-05-25", "close": 11.0, "low": 10.7},
            {"asset_id": "A", "trade_date": "2026-05-26", "close": 11.5, "low": 11.1},
        ]
    )

    detail = build_watchlist_diagnostics_effectiveness_detail(
        diagnostics_rows=diagnostics,
        bars=bars,
    )

    row = detail.iloc[0]
    assert round(float(row["future_1d_return"]), 6) == 0.05
    assert round(float(row["future_3d_return"]), 6) == 0.08
    assert round(float(row["future_5d_return"]), 6) == 0.15
    assert round(float(row["future_5d_max_drawdown"]), 6) == 0.0


def test_build_watchlist_diagnostics_effectiveness_detail_computes_strong_winner_horizons():
    diagnostics = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "watch_group": "candidate",
                "event_structure": "trend_continuation_candidate",
            }
        ]
    )
    bars = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trade_date": (pd.Timestamp("2026-01-01") + pd.Timedelta(days=index)).strftime("%Y-%m-%d"),
                "close": 10.0 + index * 0.1,
                "high": 10.0 + index * 0.1,
                "low": 9.5 + index * 0.05,
            }
            for index in range(61)
        ]
    )
    bars.loc[60, "close"] = 18.0
    bars.loc[60, "high"] = 21.0

    detail = build_watchlist_diagnostics_effectiveness_detail(
        diagnostics_rows=diagnostics,
        bars=bars,
    )

    row = detail.iloc[0]
    assert round(float(row["future_20d_return"]), 6) == 0.2
    assert round(float(row["future_30d_return"]), 6) == 0.3
    assert round(float(row["future_60d_return"]), 6) == 0.8
    assert round(float(row["max_return_within_60d"]), 6) == 1.1
    assert bool(row["hit_double_within_60d"]) is True


def test_build_watchlist_diagnostics_effectiveness_summary_groups_by_watch_group_and_structure():
    detail = pd.DataFrame(
        [
            {
                "watch_group": "risk_watch",
                "event_structure": "",
                "future_1d_return": -0.02,
                "future_3d_return": -0.05,
                "future_5d_return": -0.08,
                "future_5d_max_drawdown": -0.10,
            },
            {
                "watch_group": "opportunity_watch",
                "event_structure": "second_wave_candidate",
                "future_1d_return": 0.03,
                "future_3d_return": 0.05,
                "future_5d_return": 0.08,
                "future_5d_max_drawdown": -0.02,
            },
            {
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "future_1d_return": 0.01,
                "future_3d_return": 0.02,
                "future_5d_return": 0.03,
                "future_5d_max_drawdown": -0.03,
            },
        ]
    )

    summary = build_watchlist_diagnostics_effectiveness_summary(detail)

    watch_group_rows = summary[
        (summary["evaluation_layer"] == "short_horizon")
        & (summary["summary_level"] == "watch_group")
    ].set_index("watch_group")
    assert watch_group_rows.loc["risk_watch", "sample_count"] == 1
    assert watch_group_rows.loc["opportunity_watch", "sample_count"] == 2
    structure_rows = summary[
        (summary["evaluation_layer"] == "short_horizon")
        & (summary["summary_level"] == "event_structure")
    ].set_index("event_structure")
    assert structure_rows.loc["second_wave_candidate", "sample_count"] == 1
    assert structure_rows.loc["trend_continuation_candidate", "sample_count"] == 1


def test_build_watchlist_diagnostics_effectiveness_summary_has_two_evaluation_layers():
    detail = pd.DataFrame(
        [
            {
                "watch_group": "candidate",
                "event_structure": "trend_continuation_candidate",
                "future_1d_return": 0.01,
                "future_3d_return": 0.03,
                "future_5d_return": 0.05,
                "future_10d_return": 0.10,
                "future_20d_return": 0.20,
                "future_30d_return": 0.30,
                "future_40d_return": 0.40,
                "future_60d_return": 0.60,
                "future_5d_max_drawdown": -0.02,
                "future_20d_max_drawdown": -0.08,
                "future_30d_max_drawdown": -0.10,
                "future_60d_max_drawdown": -0.15,
                "max_return_within_60d": 1.2,
                "hit_double_within_60d": True,
            }
        ]
    )

    summary = build_watchlist_diagnostics_effectiveness_summary(detail)

    assert {"short_horizon", "strong_winner_horizon"} <= set(summary["evaluation_layer"])
    strong = summary[
        (summary["evaluation_layer"] == "strong_winner_horizon")
        & (summary["summary_level"] == "event_structure")
    ].iloc[0]
    assert strong["future_20d_return_mean"] == 0.20
    assert strong["future_30d_return_mean"] == 0.30
    assert strong["hit_double_within_60d_rate"] == 1.0


def test_run_watchlist_diagnostics_effectiveness_review_writes_artifacts(tmp_path, monkeypatch):
    diagnostics_dir = tmp_path / "diag"
    diagnostics_dir.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": "2026-05-19",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "Alpha",
                "watch_group": "opportunity_watch",
                "event_structure": "second_wave_candidate",
            }
        ]
    ).to_csv(diagnostics_dir / "watchlist_diagnostics_2026-05-19_diagnostics_v1.csv", index=False)

    bars = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-05-19", "close": 10.0, "low": 9.9},
            {"asset_id": "A", "trade_date": "2026-05-20", "close": 10.2, "low": 10.0},
            {"asset_id": "A", "trade_date": "2026-05-21", "close": 10.4, "low": 10.1},
            {"asset_id": "A", "trade_date": "2026-05-22", "close": 10.5, "low": 10.2},
            {"asset_id": "A", "trade_date": "2026-05-25", "close": 10.7, "low": 10.4},
            {"asset_id": "A", "trade_date": "2026-05-26", "close": 10.8, "low": 10.5},
        ]
    )
    monkeypatch.setattr(
        "stock_research.watchlist.effectiveness._load_market_bars_for_effectiveness",
        lambda **kwargs: bars.copy(),
    )

    result = run_watchlist_diagnostics_effectiveness_review(
        diagnostics_dir=diagnostics_dir,
        output_dir=tmp_path,
    )

    assert Path(result["detail_csv_path"]).exists()
    assert Path(result["summary_csv_path"]).exists()
    assert Path(result["short_horizon_summary_csv_path"]).exists()
    assert Path(result["strong_winner_horizon_summary_csv_path"]).exists()
    assert Path(result["markdown_path"]).exists()


def test_run_watchlist_diagnostics_effectiveness_review_filters_date_window(tmp_path, monkeypatch):
    diagnostics_dir = tmp_path / "diag"
    diagnostics_dir.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": "2026-05-18",
                "asset_id": "A",
                "watch_group": "risk_watch",
                "event_structure": "",
            },
            {
                "trade_date": "2026-05-19",
                "asset_id": "B",
                "watch_group": "opportunity_watch",
                "event_structure": "second_wave_candidate",
            },
        ]
    ).to_csv(diagnostics_dir / "watchlist_diagnostics_2026-05-19_diagnostics_v1.csv", index=False)
    bars = pd.DataFrame(
        [
            {"asset_id": "B", "trade_date": "2026-05-19", "close": 10.0, "low": 9.9},
            {"asset_id": "B", "trade_date": "2026-05-20", "close": 10.2, "low": 10.0},
        ]
    )
    monkeypatch.setattr(
        "stock_research.watchlist.effectiveness._load_market_bars_for_effectiveness",
        lambda **kwargs: bars.copy(),
    )

    result = run_watchlist_diagnostics_effectiveness_review(
        diagnostics_dir=diagnostics_dir,
        output_dir=tmp_path,
        start_date="2026-05-19",
        end_date="2026-05-19",
    )

    detail = pd.read_csv(result["detail_csv_path"])
    assert detail["asset_id"].tolist() == ["B"]


def test_run_watchlist_diagnostics_effectiveness_review_ignores_must_watch_csv_inputs(tmp_path, monkeypatch):
    diagnostics_dir = tmp_path / "diag"
    diagnostics_dir.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": "2026-05-19",
                "asset_id": "A",
                "watch_group": "candidate",
                "event_structure": "",
            }
        ]
    ).to_csv(diagnostics_dir / "watchlist_diagnostics_2026-05-19_diagnostics_v1.csv", index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-05-19",
                "asset_id": "A",
                "watch_group": "candidate",
                "event_structure": "",
            }
        ]
    ).to_csv(diagnostics_dir / "watchlist_diagnostics_must_watch_2026-05-19_diagnostics_v1.csv", index=False)
    bars = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-05-19", "close": 10.0, "low": 9.9},
            {"asset_id": "A", "trade_date": "2026-05-20", "close": 10.2, "low": 10.0},
        ]
    )
    monkeypatch.setattr(
        "stock_research.watchlist.effectiveness._load_market_bars_for_effectiveness",
        lambda **kwargs: bars.copy(),
    )

    result = run_watchlist_diagnostics_effectiveness_review(
        diagnostics_dir=diagnostics_dir,
        output_dir=tmp_path,
    )

    detail = pd.read_csv(result["detail_csv_path"])
    assert len(detail) == 1
