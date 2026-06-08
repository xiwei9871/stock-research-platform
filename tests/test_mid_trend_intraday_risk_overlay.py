import pandas as pd

from stock_research import mid_trend_intraday_risk_overlay as overlay
from stock_research.mid_trend_intraday_risk_overlay import (
    apply_intraday_risk_filter_to_shadow_candidates,
    apply_intraday_risk_high_only_new_entry_filter,
)


def test_apply_intraday_risk_filter_to_shadow_candidates_reranks_risky_names() -> None:
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "shadow_top10_rank": 1},
            {"trade_date": "2026-01-05", "asset_id": "B", "shadow_top10_rank": 2},
            {"trade_date": "2026-01-05", "asset_id": "C", "shadow_top10_rank": 3},
            {"trade_date": "2026-01-05", "asset_id": "D", "shadow_top10_rank": 4},
            {"trade_date": "2026-01-05", "asset_id": "E", "shadow_top10_rank": 5},
            {"trade_date": "2026-01-05", "asset_id": "F", "shadow_top10_rank": 6},
        ]
    )
    states = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "midtrend_risk_level": "high"},
            {"trade_date": "2026-01-05", "asset_id": "B", "midtrend_risk_level": "watch"},
            {"trade_date": "2026-01-05", "asset_id": "C", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "D", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "E", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "F", "midtrend_risk_level": "none"},
        ]
    )

    filtered = apply_intraday_risk_filter_to_shadow_candidates(
        candidates,
        states,
        watch_rank_penalty=3.0,
        high_rank_penalty=8.0,
    )

    assert filtered["asset_id"].tolist()[:5] == ["C", "D", "B", "E", "F"]
    assert filtered.loc[filtered["asset_id"].eq("A"), "intraday_risk_adjusted_rank"].iloc[0] == 9.0
    assert filtered.loc[filtered["asset_id"].eq("B"), "midtrend_risk_level"].iloc[0] == "watch"


def test_high_only_new_entry_filter_ignores_watch_and_demotes_top_high_risk() -> None:
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "shadow_top10_rank": 1},
            {"trade_date": "2026-01-05", "asset_id": "B", "shadow_top10_rank": 2},
            {"trade_date": "2026-01-05", "asset_id": "C", "shadow_top10_rank": 3},
            {"trade_date": "2026-01-05", "asset_id": "D", "shadow_top10_rank": 4},
            {"trade_date": "2026-01-05", "asset_id": "E", "shadow_top10_rank": 5},
            {"trade_date": "2026-01-05", "asset_id": "F", "shadow_top10_rank": 6},
        ]
    )
    states = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "midtrend_risk_level": "watch"},
            {"trade_date": "2026-01-05", "asset_id": "B", "midtrend_risk_level": "high"},
            {"trade_date": "2026-01-05", "asset_id": "C", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "D", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "E", "midtrend_risk_level": "none"},
            {"trade_date": "2026-01-05", "asset_id": "F", "midtrend_risk_level": "none"},
        ]
    )

    filtered = apply_intraday_risk_high_only_new_entry_filter(
        candidates,
        states,
        top_n=5,
        high_rank_penalty=8.0,
    )

    assert filtered["asset_id"].tolist()[:5] == ["A", "C", "D", "E", "F"]
    assert filtered.loc[filtered["asset_id"].eq("A"), "intraday_risk_rank_penalty"].iloc[0] == 0.0
    assert filtered.loc[filtered["asset_id"].eq("B"), "intraday_risk_adjusted_rank"].iloc[0] == 10.0


def test_high_only_new_entry_filter_can_veto_top_high_risk_to_buffer_end() -> None:
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "shadow_top10_rank": 1},
            {"trade_date": "2026-01-05", "asset_id": "B", "shadow_top10_rank": 2},
            {"trade_date": "2026-01-05", "asset_id": "C", "shadow_top10_rank": 3},
            {"trade_date": "2026-01-05", "asset_id": "D", "shadow_top10_rank": 4},
            {"trade_date": "2026-01-05", "asset_id": "E", "shadow_top10_rank": 5},
            {"trade_date": "2026-01-05", "asset_id": "F", "shadow_top10_rank": 6},
            {"trade_date": "2026-01-05", "asset_id": "G", "shadow_top10_rank": 7},
        ]
    )
    states = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "B", "midtrend_risk_level": "high"},
            {"trade_date": "2026-01-05", "asset_id": "C", "midtrend_risk_level": "watch"},
        ]
    )

    filtered = apply_intraday_risk_high_only_new_entry_filter(
        candidates,
        states,
        top_n=5,
        high_risk_action="veto",
    )

    assert filtered["asset_id"].tolist() == ["A", "C", "D", "E", "F", "G", "B"]
    assert filtered.loc[filtered["asset_id"].eq("B"), "intraday_risk_rank_penalty"].iloc[0] == 6.0
    assert filtered.loc[filtered["asset_id"].eq("C"), "intraday_risk_rank_penalty"].iloc[0] == 0.0


def test_overlay_backtest_passes_hard_exclusions_to_weekly_simulation(monkeypatch) -> None:
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "asset_id": "A",
                "shadow_top10_rank": 1,
                "shadow_rule_version": "base",
            }
        ]
    )
    captured_hard_exclusions = []

    monkeypatch.setattr(overlay, "resolve_intraday_risk_control_v2_preset", lambda _name: {})
    monkeypatch.setattr(
        overlay,
        "build_intraday_risk_signals_v2",
        lambda *_args, **_kwargs: pd.DataFrame(
            [{"trade_date": "2026-01-05", "asset_id": "A", "midtrend_risk_level": "none"}]
        ),
    )
    monkeypatch.setattr(
        overlay,
        "build_midtrend_risk_states",
        lambda *_args, **_kwargs: pd.DataFrame(
            [{"trade_date": "2026-01-05", "asset_id": "A", "midtrend_risk_level": "none"}]
        ),
    )
    monkeypatch.setattr(
        overlay,
        "build_mid_trend_shadow_top10_from_frame",
        lambda *_args, **_kwargs: {"top10": candidates.copy()},
    )
    monkeypatch.setattr(overlay, "_prices_for_shadow", lambda prices, _signals: prices)

    def fake_simulate(*_args, **kwargs):
        captured_hard_exclusions.append(kwargs.get("hard_exclusions"))
        variant_name = kwargs["variant_name"]
        return {
            "summary": {
                "variant_name": variant_name,
                "total_return": 0.0,
                "max_drawdown": 0.0,
            },
            "equity_curve": pd.DataFrame([{"variant_name": variant_name}]),
            "positions": pd.DataFrame([{"variant_name": variant_name}]),
            "trades": pd.DataFrame([{"variant_name": variant_name}]),
        }

    monkeypatch.setattr(overlay, "_simulate_variant", fake_simulate)
    funnel_detail = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "asset_id": "A",
                "mid_trend_funnel_score": 80,
                "score_rank": 1,
                "is_st": True,
            }
        ]
    )

    overlay.build_mid_trend_intraday_risk_overlay_backtest_from_frames(
        funnel_detail=funnel_detail,
        prices=pd.DataFrame([{"trade_date": "2026-01-05", "asset_id": "A", "close": 10.0}]),
        intraday_features=pd.DataFrame(),
        start_date="2026-01-05",
        end_date="2026-01-05",
    )

    assert len(captured_hard_exclusions) == 2
    for hard_exclusions in captured_hard_exclusions:
        assert hard_exclusions is not None
        assert hard_exclusions.to_dict("records") == [{"trade_date": "2026-01-05", "asset_id": "A"}]
