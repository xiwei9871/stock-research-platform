import pandas as pd

from stock_research.tech_bottleneck_strict_dimension_performance import (
    build_strict_dimension_performance_review,
)


def test_build_strict_dimension_performance_uses_first_hit_and_close_drawdown():
    quality_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "stock_name": "Alpha",
                "trade_date": "2025-01-03",
                "primary_chain_id": "ai_compute_chips",
                "primary_chain_name": "AI芯片",
                "matched_bottleneck_dimensions": "国产替代",
            },
            {
                "asset_id": "CN:SZ:000001",
                "stock_name": "Alpha",
                "trade_date": "2025-01-10",
                "primary_chain_id": "ai_compute_chips",
                "primary_chain_name": "AI芯片",
                "matched_bottleneck_dimensions": "国产替代",
            },
            {
                "asset_id": "CN:SZ:000002",
                "stock_name": "Beta",
                "trade_date": "2025-01-03",
                "primary_chain_id": "",
                "primary_chain_name": "",
                "matched_bottleneck_dimensions": "",
            },
        ]
    )
    bars = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000001", "trade_date": "2025-01-02", "close": 10.0, "trade_status": "1"},
            {"asset_id": "CN:SZ:000001", "trade_date": "2025-01-03", "close": 12.0, "trade_status": "1"},
            {"asset_id": "CN:SZ:000001", "trade_date": "2025-01-06", "close": 9.0, "trade_status": "1"},
            {"asset_id": "CN:SZ:000001", "trade_date": "2025-01-07", "close": 15.0, "trade_status": "1"},
            {"asset_id": "CN:SZ:000001", "trade_date": "2025-01-08", "close": 14.0, "trade_status": "1"},
        ]
    )

    review = build_strict_dimension_performance_review(
        quality_review=quality_review,
        bars=bars,
        start_date="2025-01-01",
        end_date="2025-01-08",
        horizons=[2],
    )

    details = review["details"]
    assert len(details) == 1
    row = details.iloc[0]
    assert row["asset_id"] == "CN:SZ:000001"
    assert row["first_hit_date"] == "2025-01-03"
    assert row["period_entry_date"] == "2025-01-02"
    assert row["hit_entry_date"] == "2025-01-03"
    assert row["period_return"] == 0.4
    assert row["period_max_drawdown"] == -0.25
    assert row["since_first_hit_return"] == 0.166667
    assert row["since_first_hit_max_drawdown"] == -0.25
    assert row["return_2d"] == 0.25
    assert row["max_drawdown_2d"] == -0.25
    assert row["horizon_2d_status"] == "complete"


def test_build_strict_dimension_performance_marks_missing_bars():
    quality_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "stock_name": "Alpha",
                "trade_date": "2025-01-03",
                "primary_chain_id": "ai_compute_chips",
                "primary_chain_name": "AI芯片",
                "matched_bottleneck_dimensions": "国产替代",
            }
        ]
    )

    review = build_strict_dimension_performance_review(
        quality_review=quality_review,
        bars=pd.DataFrame(columns=["asset_id", "trade_date", "close"]),
        start_date="2025-01-01",
        end_date="2025-01-08",
        horizons=[2],
    )

    row = review["details"].iloc[0]
    assert row["data_status"] == "missing_bars"
    assert pd.isna(row["period_return"])
    assert review["summary"].iloc[0]["asset_count"] == 1


def test_build_strict_dimension_performance_win_rate_ignores_partial_horizon_rows():
    quality_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "stock_name": "Alpha",
                "trade_date": "2025-01-03",
                "primary_chain_id": "ai_compute_chips",
                "primary_chain_name": "AI芯片",
                "matched_bottleneck_dimensions": "国产替代",
            },
            {
                "asset_id": "CN:SZ:000002",
                "stock_name": "Beta",
                "trade_date": "2025-01-03",
                "primary_chain_id": "ai_compute_chips",
                "primary_chain_name": "AI芯片",
                "matched_bottleneck_dimensions": "国产替代",
            },
        ]
    )
    bars = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000001", "trade_date": "2025-01-03", "close": 10.0},
            {"asset_id": "CN:SZ:000001", "trade_date": "2025-01-06", "close": 11.0},
            {"asset_id": "CN:SZ:000002", "trade_date": "2025-01-03", "close": 10.0},
        ]
    )

    review = build_strict_dimension_performance_review(
        quality_review=quality_review,
        bars=bars,
        start_date="2025-01-01",
        end_date="2025-01-08",
        horizons=[1],
    )

    summary = review["summary"].iloc[0]
    assert summary["complete_count_1d"] == 1
    assert summary["win_rate_1d"] == 1.0
