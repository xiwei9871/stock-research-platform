import pandas as pd
import pytest

from stock_research.dashboard import strategy_backtest_adapters as adapters
from stock_research.dashboard.strategy_backtest_adapters import (
    LHBShortlineAdapter,
    MidTrendAdapter,
    PositionControlAdapter,
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
    TechBottleneckAdapter,
    build_lhb_shortline_scores_from_frames,
    build_manual_v1_scores_from_frame,
    build_mid_trend_scores_from_frames,
    build_position_control_scores_from_frames,
    build_tech_bottleneck_scores_from_frames,
    normalize_strategy_scores,
)


def test_registry_contains_all_backtest_lab_strategies():
    assert set(STRATEGY_BACKTEST_REGISTRY) == {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }


def test_normalize_strategy_scores_ranks_high_scores_first():
    raw = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 90.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "score_total": 70.0},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert list(scores["trade_date"]) == ["2026-01-01", "2026-01-01", "2026-01-02"]
    assert list(scores["asset_id"]) == ["A", "B", "A"]
    assert list(scores["rank"]) == [1, 2, 1]
    assert list(scores["strategy_id"].unique()) == ["unit_strategy"]


def test_normalize_strategy_scores_rejects_empty_signal_set():
    with pytest.raises(ValueError, match="no unit_strategy strategy scores found"):
        normalize_strategy_scores(pd.DataFrame(), strategy_id="unit_strategy")


def test_normalize_strategy_scores_drops_missing_values_before_formatting_dates():
    raw = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2026-01-01"),
                "asset_id": "A",
                "score_total": 90.0,
            },
            {"trade_date": None, "asset_id": "B", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": None, "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "score_total": float("nan")},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert len(scores) == 1
    assert scores.loc[0, "trade_date"] == "2026-01-01"
    assert scores.loc[0, "asset_id"] == "A"


def test_strategy_backtest_params_defaults():
    params = StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08")

    assert params.score_version == "manual_v1"
    assert params.adjust_type == "hfq"


def test_manual_v1_builder_preserves_manual_score_order():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 1, "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 2, "score_total": 90.0},
        ]
    )

    scores = build_manual_v1_scores_from_frame(manual)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert list(scores["rank"]) == [1, 2]


def test_manual_v1_builder_deduplicates_date_asset_rows_before_ranking():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 2, "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 3, "score_total": 70.0},
        ]
    )

    scores = build_manual_v1_scores_from_frame(manual)

    assert len(scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")]) == 1
    assert scores.duplicated(subset=["trade_date", "asset_id"]).sum() == 0
    a_score = scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")].iloc[0]
    assert a_score["rank"] == 1
    assert a_score["score_total"] == 90.0


def test_manual_v1_builder_rejects_empty_frame_with_value_error():
    with pytest.raises(ValueError, match="no manual_v1_topn_rotation strategy scores found"):
        build_manual_v1_scores_from_frame(pd.DataFrame())


def test_lhb_shortline_builder_ranks_positive_support_above_risky_rows():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.22,
                "lhb_net_buy_amount": 80_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "on_lhb": True,
                "lhb_net_buy_ratio": -0.05,
                "lhb_net_buy_amount": -5_000_000,
                "institution_net_buy": -2_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "B", "amount_vs_20d": 0.3, "high_to_close_drawdown": 0.16},
        ]
    )

    scores = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]
    assert scores.iloc[1]["eligibility"] is False
    assert "pump_risk" in scores.iloc[1]["eligibility_reason"]


def test_lhb_shortline_builder_deduplicates_date_asset_rows_before_scoring():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.10,
                "lhb_net_buy_amount": 20_000_000,
                "institution_net_buy": 5_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.30,
                "lhb_net_buy_amount": 60_000_000,
                "institution_net_buy": 15_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.40,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.8, "high_to_close_drawdown": 0.08},
        ]
    )

    scores = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert len(scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")]) == 1


def test_lhb_shortline_adapter_returns_only_eligible_scores(monkeypatch):
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.22,
                "lhb_net_buy_amount": 80_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "on_lhb": True,
                "lhb_net_buy_ratio": -0.05,
                "lhb_net_buy_amount": -5_000_000,
                "institution_net_buy": -2_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "B", "amount_vs_20d": 0.3, "high_to_close_drawdown": 0.16},
        ]
    )

    def fake_fetch_frame(sql, params):
        if "factor.lhb_event_features_daily" in sql:
            return lhb
        return technical

    monkeypatch.setattr(adapters, "_fetch_frame", fake_fetch_frame)

    scores = LHBShortlineAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["A"]
    assert scores.iloc[0]["eligibility"] is True


def test_mid_trend_builder_prefers_stronger_trend_and_penalizes_risk():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 78.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.18,
                "high_to_close_drawdown": 0.02,
                "amount_vs_20d": 1.2,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": -0.03,
                "high_to_close_drawdown": 0.18,
                "amount_vs_20d": 0.5,
            },
        ]
    )
    factors = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "factor_name": "trend_r2_20",
                "factor_value": 0.85,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "factor_name": "trend_r2_20",
                "factor_value": 0.25,
            },
        ]
    )

    scores = build_mid_trend_scores_from_frames(manual, technical, factors)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]


@pytest.mark.parametrize(
    "builder",
    [
        build_mid_trend_scores_from_frames,
        build_tech_bottleneck_scores_from_frames,
        build_position_control_scores_from_frames,
    ],
)
def test_manual_technical_builders_deduplicate_date_asset_rows_before_scoring(builder):
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 2, "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 1, "score_total": 88.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 3, "score_total": 75.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.04,
                "amount_vs_20d": 1.1,
                "close_position_in_day": 0.60,
                "high_to_close_drawdown": 0.03,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.12,
                "amount_vs_20d": 1.8,
                "close_position_in_day": 0.82,
                "high_to_close_drawdown": 0.08,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": 0.03,
                "amount_vs_20d": 1.0,
                "close_position_in_day": 0.50,
                "high_to_close_drawdown": 0.02,
            },
        ]
    )

    scores = builder(manual, technical)

    assert len(scores[(scores["trade_date"] == "2026-01-01") & (scores["asset_id"] == "A")]) == 1


@pytest.mark.parametrize(
    ("builder", "strategy_id"),
    [
        (build_mid_trend_scores_from_frames, "mid_trend"),
        (build_tech_bottleneck_scores_from_frames, "tech_bottleneck"),
        (build_position_control_scores_from_frames, "position_control"),
    ],
)
def test_manual_technical_builders_reject_empty_manual_data_with_value_error(builder, strategy_id):
    with pytest.raises(ValueError, match=f"no {strategy_id} strategy scores found"):
        builder(pd.DataFrame(), pd.DataFrame())


def test_factor_pivot_uses_max_factor_value_for_duplicate_rows():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 70.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "ret_20d": 0.0, "amount_vs_20d": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "ret_20d": 0.0, "amount_vs_20d": 1.0},
        ]
    )
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "trend_r2_20", "factor_value": 0.90},
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "trend_r2_20", "factor_value": 0.20},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "trend_r2_20", "factor_value": 0.50},
        ]
    )

    scores = build_mid_trend_scores_from_frames(manual, technical, factors)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_components"]["trend_r2_20"] == 0.90


def test_mid_trend_adapter_returns_only_eligible_scores(monkeypatch):
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 70.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "ret_20d": 0.04, "amount_vs_20d": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "ret_20d": -0.04, "amount_vs_20d": 1.0},
        ]
    )
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "trend_r2_20", "factor_value": 0.60},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "trend_r2_20", "factor_value": 0.10},
        ]
    )
    monkeypatch.setattr(adapters, "_load_manual_scores", lambda params: manual)
    monkeypatch.setattr(adapters, "_load_technical_features", lambda params: technical)
    monkeypatch.setattr(adapters, "_load_factor_values", lambda params, factor_names: factors)

    scores = MidTrendAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["A"]
    assert scores.iloc[0]["eligibility"] is True


def test_tech_bottleneck_adapter_returns_only_eligible_scores(monkeypatch):
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 90.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.08,
                "amount_vs_20d": 1.0,
                "close_position_in_day": 0.70,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": 0.08,
                "amount_vs_20d": 0.2,
                "close_position_in_day": 0.70,
            },
        ]
    )
    monkeypatch.setattr(adapters, "_load_manual_scores", lambda params: manual)
    monkeypatch.setattr(adapters, "_load_technical_features", lambda params: technical)

    scores = TechBottleneckAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["A"]
    assert scores.iloc[0]["eligibility"] is True


def test_position_control_adapter_applies_eligibility_filter(monkeypatch):
    raw_scores = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "rank": 1,
                "score_total": 90.0,
                "score_components": {},
                "strategy_id": "position_control",
                "eligibility": True,
                "eligibility_reason": "risk_scaled",
                "exposure_scale": 1.0,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "rank": 2,
                "score_total": 80.0,
                "score_components": {},
                "strategy_id": "position_control",
                "eligibility": False,
                "eligibility_reason": "risk_excluded",
                "exposure_scale": 0.0,
            },
        ]
    )
    monkeypatch.setattr(adapters, "_load_manual_scores", lambda params: pd.DataFrame())
    monkeypatch.setattr(adapters, "_load_technical_features", lambda params: pd.DataFrame())
    monkeypatch.setattr(adapters, "build_position_control_scores_from_frames", lambda manual, technical: raw_scores)

    scores = PositionControlAdapter().load_scores(
        StrategyBacktestParams(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert list(scores["asset_id"]) == ["A"]
    assert scores.iloc[0]["eligibility"] is True


def test_tech_bottleneck_builder_prefers_continuation_and_volume_confirmation():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 65.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 86.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ret_20d": 0.16,
                "amount_vs_20d": 2.4,
                "close_position_in_day": 0.86,
                "high_to_close_drawdown": 0.02,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "ret_20d": 0.01,
                "amount_vs_20d": 0.7,
                "close_position_in_day": 0.45,
                "high_to_close_drawdown": 0.12,
            },
        ]
    )

    scores = build_tech_bottleneck_scores_from_frames(manual, technical)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]


def test_position_control_builder_reranks_risky_base_candidates():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 88.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "high_to_close_drawdown": 0.22,
                "amount_vs_20d": 3.0,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "high_to_close_drawdown": 0.02,
                "amount_vs_20d": 1.0,
            },
        ]
    )

    scores = build_position_control_scores_from_frames(manual, technical)

    assert list(scores["asset_id"]) == ["B", "A"]
    assert scores.iloc[0]["exposure_scale"] == 1.0
    assert scores.iloc[1]["exposure_scale"] < 1.0
