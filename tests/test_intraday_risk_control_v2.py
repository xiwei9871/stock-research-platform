from pathlib import Path

import pandas as pd

from stock_research.intraday_risk_control_v2 import (
    build_intraday_risk_signals_v2,
    build_midtrend_score_variants_v2,
    build_midtrend_risk_states,
)


def test_build_intraday_risk_signals_v2_uses_stock_history_not_daily_rank_only() -> None:
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "feature_name": "amount_front_1h_ratio",
                "feature_value": 0.20,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "feature_name": "amount_front_1h_ratio",
                "feature_value": 0.21,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "A",
                "feature_name": "amount_front_1h_ratio",
                "feature_value": 0.80,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "feature_name": "afternoon_return",
                "feature_value": 0.01,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "feature_name": "afternoon_return",
                "feature_value": 0.00,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "A",
                "feature_name": "afternoon_return",
                "feature_value": -0.04,
            },
        ]
    )

    signals = build_intraday_risk_signals_v2(features, lookback=2, zscore_threshold=1.0)

    row = signals[signals["trade_date"].eq("2026-01-03") & signals["asset_id"].eq("A")].iloc[0]
    assert bool(row["front_loaded_failure"]) is True
    assert row["lhb_risk_level"] == "watch"


def test_tail_confirmation_failure_requires_tail_and_vwap_significantly_weak() -> None:
    features = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "asset_id": "A",
                "feature_name": feature_name,
                "feature_value": feature_value,
            }
            for trade_date, last_30m, close_to_vwap in [
                ("2026-01-01", -0.10, -0.10),
                ("2026-01-02", -0.10, -0.10),
                ("2026-01-03", -0.01, -0.01),
            ]
            for feature_name, feature_value in [
                ("last_30m_return", last_30m),
                ("close_to_vwap", close_to_vwap),
            ]
        ]
    )

    signals = build_intraday_risk_signals_v2(features, lookback=2, zscore_threshold=1.0)

    row = signals[signals["trade_date"].eq("2026-01-03") & signals["asset_id"].eq("A")].iloc[0]
    assert bool(row["tail_confirmation_failure"]) is False
    assert row["lhb_risk_level"] == "none"


def test_morning_to_afternoon_reversal_requires_obvious_reversal() -> None:
    features = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "asset_id": "A",
                "feature_name": feature_name,
                "feature_value": feature_value,
            }
            for trade_date, morning, afternoon in [
                ("2026-01-01", 0.02, -0.02),
                ("2026-01-02", 0.02, -0.02),
                ("2026-01-03", 0.001, -0.001),
            ]
            for feature_name, feature_value in [
                ("morning_return", morning),
                ("afternoon_return", afternoon),
            ]
        ]
    )

    signals = build_intraday_risk_signals_v2(features, lookback=2, zscore_threshold=1.0)

    row = signals[signals["trade_date"].eq("2026-01-03") & signals["asset_id"].eq("A")].iloc[0]
    assert bool(row["morning_to_afternoon_reversal"]) is False
    assert row["lhb_risk_level"] == "none"


def test_build_midtrend_risk_states_keeps_repeated_watch_from_escalating_to_high() -> None:
    signals = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "structural_risk_count": 1},
            {"trade_date": "2026-01-02", "asset_id": "A", "structural_risk_count": 0},
            {"trade_date": "2026-01-03", "asset_id": "A", "structural_risk_count": 1},
            {"trade_date": "2026-01-04", "asset_id": "A", "structural_risk_count": 1},
        ]
    )

    states = build_midtrend_risk_states(signals, watch_5d_count=2, high_5d_count=3)

    assert states.iloc[0]["midtrend_risk_level"] == "none"
    assert states.iloc[2]["midtrend_risk_level"] == "watch"
    assert states.iloc[3]["midtrend_risk_level"] == "watch"


def test_build_midtrend_risk_states_escalates_repeated_severe_structural_triggers() -> None:
    signals = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "structural_risk_count": 2},
            {"trade_date": "2026-01-02", "asset_id": "A", "structural_risk_count": 0},
            {"trade_date": "2026-01-03", "asset_id": "A", "structural_risk_count": 2},
            {"trade_date": "2026-01-04", "asset_id": "A", "structural_risk_count": 2},
        ]
    )

    states = build_midtrend_risk_states(signals, watch_5d_count=2, high_5d_count=3)

    assert states.iloc[0]["midtrend_risk_level"] == "none"
    assert states.iloc[2]["midtrend_risk_level"] == "watch"
    assert states.iloc[3]["midtrend_risk_level"] == "high"


def test_build_midtrend_score_variants_penalizes_risky_candidates_but_not_baseline() -> None:
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "rank": 1, "score_total": 100.0},
            {"trade_date": "2026-01-05", "asset_id": "B", "rank": 2, "score_total": 95.0},
        ]
    )
    states = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "asset_id": "A",
                "midtrend_risk_level": "high",
                "midtrend_risk_trigger_count_5d": 3,
                "midtrend_risk_trigger_count_10d": 3,
            },
            {
                "trade_date": "2026-01-05",
                "asset_id": "B",
                "midtrend_risk_level": "none",
                "midtrend_risk_trigger_count_5d": 0,
                "midtrend_risk_trigger_count_10d": 0,
            },
        ]
    )

    variants = build_midtrend_score_variants_v2(
        scores,
        states,
        watch_penalty=3.0,
        high_penalty=8.0,
    )

    assert variants["baseline_topn"].iloc[0]["asset_id"] == "A"
    assert variants["trend_new_entry_penalty"].iloc[0]["asset_id"] == "B"
    assert variants["trend_confirmed_reduce"].iloc[0]["asset_id"] == "B"
