import pandas as pd

from stock_research.watchlist.diagnostics import build_watchlist_diagnostics


def test_build_watchlist_diagnostics_builds_full_and_must_watch_outputs():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 91.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 82.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "amount_vs_20d": 1.4,
                "volatility_5d": 0.05,
                "high_to_close_drawdown": 0.02,
            },
            {
                "asset_id": "B",
                "stock_name": "Beta",
                "amount_vs_20d": 4.8,
                "volatility_5d": 0.14,
                "high_to_close_drawdown": 0.11,
            },
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=pd.DataFrame(),
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    assert set(result) == {"full", "must_watch"}
    assert list(result["full"]["asset_id"]) == ["A", "B"]
    assert list(result["must_watch"]["asset_id"]) == ["B"]
    assert list(result["must_watch"]["watch_group"]) == ["risk_watch"]


def test_build_watchlist_diagnostics_assigns_risk_and_opportunity_groups():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 88.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "amount_vs_20d": 1.3,
                "volatility_5d": 0.04,
                "high_to_close_drawdown": 0.02,
            },
            {
                "asset_id": "B",
                "stock_name": "Beta",
                "amount_vs_20d": 5.5,
                "volatility_5d": 0.16,
                "high_to_close_drawdown": 0.12,
            },
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.20, "overheat_avoid": False, "crowded_late_entry": False},
            {"asset_id": "B", "dragon_risk_score": 0.82, "overheat_avoid": True, "crowded_late_entry": True},
        ]
    )
    event_frame = pd.DataFrame(
        [
            {"asset_id": "A", "event_structure": "second_wave_candidate", "failure_flag": False},
            {"asset_id": "B", "event_structure": "a_kill_failure", "failure_flag": True},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=event_frame,
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    must_watch = result["must_watch"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "opportunity_watch"
    assert full.loc["B", "watch_group"] == "risk_watch"
    assert must_watch.loc["A", "watch_group"] == "opportunity_watch"
    assert must_watch.loc["B", "watch_group"] == "risk_watch"


def test_build_watchlist_diagnostics_merges_lhb_shortline_watch_groups():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 88.0},
            {"trade_date": "2026-05-20", "asset_id": "C", "rank": 3, "score_total": 86.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 1.0, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
            {"asset_id": "B", "amount_vs_20d": 1.0, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
            {"asset_id": "C", "amount_vs_20d": 1.0, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
        ]
    )
    lhb_shortline_frame = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "watch_group": "follow_watch",
                "watch_reason": "positive_follow_effectiveness",
                "exit_signal": "",
                "exit_reason": "",
            },
            {
                "asset_id": "B",
                "watch_group": "high_elasticity_watch",
                "watch_reason": "positive_elasticity_with_controlled_drawdown",
                "exit_signal": "",
                "exit_reason": "",
            },
            {
                "asset_id": "C",
                "watch_group": "avoid_watch",
                "watch_reason": "withdrawal_lhb",
                "exit_signal": "hard_exit",
                "exit_reason": "withdrawal_lhb,failure_structure",
            },
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=pd.DataFrame(),
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        lhb_shortline_frame=lhb_shortline_frame,
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "opportunity_watch"
    assert full.loc["A", "lhb_shortline_watch_group"] == "follow_watch"
    assert "positive_follow_effectiveness" in full.loc["A", "opportunity_note"]
    assert full.loc["B", "watch_group"] == "high_odds_burst_watch"
    assert full.loc["B", "lhb_shortline_watch_group"] == "high_elasticity_watch"
    assert full.loc["C", "watch_group"] == "risk_watch"
    assert "lhb_shortline:avoid_watch" in full.loc["C", "risk_note"]
    assert "withdrawal_lhb" in full.loc["C", "lhb_shortline_exit_reason"]
    assert set(result["must_watch"]["asset_id"]) == {"A", "B", "C"}


def test_build_watchlist_diagnostics_uses_latest_enriched_event_fields_for_grouping():
    top_scores = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "asset_id": "CN:SZ:000017",
                "rank": 1,
                "score_total": 91.0,
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
            },
            {
                "trade_date": "2026-05-20",
                "asset_id": "CN:SH:600118",
                "rank": 2,
                "score_total": 88.0,
                "ts_code": "600118.SH",
                "stock_name": "中国卫星",
            },
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.03, "volatility_5d": 0.07},
            {"asset_id": "CN:SH:600118", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.02, "volatility_5d": 0.04},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "dragon_risk_score": 0.20, "overheat_avoid": False, "crowded_late_entry": False},
            {"asset_id": "CN:SH:600118", "dragon_risk_score": 0.20, "overheat_avoid": False, "crowded_late_entry": False},
        ]
    )
    lhb_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "lhb_risk_score": 0.10, "lhb_negative_net_buy": False, "lhb_institution_selling": False},
            {"asset_id": "CN:SH:600118", "lhb_risk_score": 0.10, "lhb_negative_net_buy": False, "lhb_institution_selling": False},
        ]
    )
    event_frame = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000017",
                "event_date": "2026-05-06",
                "event_structure": "second_wave_candidate",
                "failure_flag": False,
            },
            {
                "asset_id": "CN:SZ:000017",
                "event_date": "2026-05-19",
                "event_structure": "failed_second_wave",
                "failure_flag": True,
            },
            {
                "asset_id": "CN:SH:600118",
                "event_date": "2026-05-18",
                "event_structure": "second_wave_candidate",
                "failure_flag": False,
            },
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=event_frame,
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    must_watch = result["must_watch"].set_index("asset_id")
    assert full.loc["CN:SZ:000017", "ts_code"] == "000017.SZ"
    assert full.loc["CN:SZ:000017", "stock_name"] == "深中华A"
    assert full.loc["CN:SZ:000017", "watch_group"] == "risk_watch"
    assert full.loc["CN:SH:600118", "watch_group"] == "opportunity_watch"
    assert must_watch.loc["CN:SZ:000017", "watch_group"] == "risk_watch"
    assert must_watch.loc["CN:SH:600118", "watch_group"] == "opportunity_watch"


def test_build_watchlist_diagnostics_preserves_volatility_and_identity_fields_when_enriched():
    top_scores = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "asset_id": "CN:SZ:000017",
                "rank": 1,
                "score_total": 91.0,
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
            },
            {
                "trade_date": "2026-05-20",
                "asset_id": "CN:SH:600118",
                "rank": 2,
                "score_total": 88.0,
                "ts_code": "600118.SH",
                "stock_name": "中国卫星",
            },
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "amount_vs_20d": 4.5, "high_to_close_drawdown": 0.10, "volatility_5d": 0.12},
            {"asset_id": "CN:SH:600118", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.02, "volatility_5d": 0.04},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "dragon_risk_score": 0.80, "overheat_avoid": True, "crowded_late_entry": True},
            {"asset_id": "CN:SH:600118", "dragon_risk_score": 0.20, "overheat_avoid": False, "crowded_late_entry": False},
        ]
    )
    lhb_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "lhb_risk_score": 0.70, "lhb_negative_net_buy": True, "lhb_institution_selling": True},
            {"asset_id": "CN:SH:600118", "lhb_risk_score": 0.10, "lhb_negative_net_buy": False, "lhb_institution_selling": False},
        ]
    )
    event_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000017", "event_structure": "failed_second_wave", "failure_flag": True},
            {"asset_id": "CN:SH:600118", "event_structure": "second_wave_candidate", "failure_flag": False},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=event_frame,
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    must_watch = result["must_watch"].set_index("asset_id")

    assert full.loc["CN:SZ:000017", "ts_code"] == "000017.SZ"
    assert full.loc["CN:SZ:000017", "stock_name"] == "深中华A"
    assert full.loc["CN:SZ:000017", "volatility_5d"] == 0.12
    assert full.loc["CN:SH:600118", "ts_code"] == "600118.SH"
    assert full.loc["CN:SH:600118", "stock_name"] == "中国卫星"
    assert full.loc["CN:SH:600118", "volatility_5d"] == 0.04
    assert must_watch.loc["CN:SZ:000017", "ts_code"] == "000017.SZ"
    assert must_watch.loc["CN:SZ:000017", "stock_name"] == "深中华A"
    assert must_watch.loc["CN:SZ:000017", "volatility_5d"] == 0.12
    assert must_watch.loc["CN:SH:600118", "ts_code"] == "600118.SH"
    assert must_watch.loc["CN:SH:600118", "stock_name"] == "中国卫星"
    assert must_watch.loc["CN:SH:600118", "volatility_5d"] == 0.04


def test_build_watchlist_diagnostics_infers_opportunity_structure_from_dragon_windows():
    top_scores = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "asset_id": "CN:SZ:000029",
                "rank": 1,
                "score_total": 90.0,
                "ts_code": "000029.SZ",
                "stock_name": "深深房A",
            },
            {
                "trade_date": "2026-05-20",
                "asset_id": "CN:SZ:001211",
                "rank": 2,
                "score_total": 88.0,
                "ts_code": "001211.SZ",
                "stock_name": "双枪科技",
            },
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "CN:SZ:000029", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.03},
            {"asset_id": "CN:SZ:001211", "amount_vs_20d": 1.0, "high_to_close_drawdown": 0.02, "volatility_5d": 0.04},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000029",
                "dragon_risk_score": 0.21,
                "overheat_avoid": False,
                "crowded_late_entry": False,
                "entry_window": "early_setup",
                "entry_window_v2": "low_congestion_opportunity",
            },
            {
                "asset_id": "CN:SZ:001211",
                "dragon_risk_score": 0.18,
                "overheat_avoid": False,
                "crowded_late_entry": False,
                "entry_window": "early_setup",
                "entry_window_v2": "recovery_or_repair",
            },
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["CN:SZ:000029", "event_structure"] == "second_wave_candidate"
    assert full.loc["CN:SZ:000029", "watch_group"] == "opportunity_watch"
    assert full.loc["CN:SZ:001211", "event_structure"] == "break_then_reversal_candidate"
    assert full.loc["CN:SZ:001211", "watch_group"] == "opportunity_watch"


def test_build_watchlist_diagnostics_filters_acceleration_trend_and_keeps_breakout_narrow():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 88.0},
            {"trade_date": "2026-05-20", "asset_id": "C", "rank": 3, "score_total": 84.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 1.3, "high_to_close_drawdown": 0.012, "volatility_5d": 0.028},
            {"asset_id": "B", "amount_vs_20d": 1.4, "high_to_close_drawdown": 0.010, "volatility_5d": 0.020},
            {"asset_id": "C", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.010, "volatility_5d": 0.020},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "dragon_risk_score": 0.08,
                "overheat_avoid": False,
                "crowded_late_entry": False,
                "entry_window": "early_setup",
                "entry_window_v2": "breakout_entry",
            },
            {
                "asset_id": "B",
                "dragon_risk_score": 0.05,
                "overheat_avoid": False,
                "crowded_late_entry": False,
                "entry_window": "early_setup",
                "entry_window_v2": "early_setup",
            },
            {
                "asset_id": "C",
                "dragon_risk_score": 0.05,
                "overheat_avoid": False,
                "crowded_late_entry": False,
                "entry_window": "early_setup",
                "entry_window_v2": "acceleration_entry",
            },
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "event_structure"] == "trend_continuation_candidate"
    assert full.loc["B", "event_structure"] == "weak_to_strong_candidate"
    assert full.loc["C", "event_structure"] == ""
    assert full.loc["C", "watch_group"] == "candidate"


def test_build_watchlist_diagnostics_prioritizes_failure_risk_ahead_of_hard_risk():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 3, "score_total": 80.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "C", "rank": 2, "score_total": 85.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.02, "volatility_5d": 0.04},
            {"asset_id": "B", "amount_vs_20d": 4.8, "high_to_close_drawdown": 0.09, "volatility_5d": 0.05},
            {"asset_id": "C", "amount_vs_20d": 1.4, "high_to_close_drawdown": 0.02, "volatility_5d": 0.04},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.10, "overheat_avoid": False, "crowded_late_entry": False},
            {"asset_id": "B", "dragon_risk_score": 0.10, "overheat_avoid": False, "crowded_late_entry": False},
            {"asset_id": "C", "dragon_risk_score": 0.78, "overheat_avoid": True, "crowded_late_entry": False},
        ]
    )
    lhb_frame = pd.DataFrame(
        [
            {"asset_id": "C", "lhb_risk_score": 0.76, "lhb_negative_net_buy": False},
        ]
    )
    event_frame = pd.DataFrame(
        [
            {"asset_id": "A", "event_structure": "failed_second_wave", "failure_flag": True},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=event_frame,
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    must_watch = result["must_watch"]
    risk_ids = must_watch[must_watch["watch_group"] == "risk_watch"]["asset_id"].tolist()
    assert risk_ids == ["A", "C", "B"]


def test_build_watchlist_diagnostics_prioritizes_weak_to_strong_then_break_then_reversal():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 2, "score_total": 85.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "C", "rank": 3, "score_total": 80.0},
            {"trade_date": "2026-05-20", "asset_id": "D", "rank": 4, "score_total": 78.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.03},
            {"asset_id": "B", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.03},
            {"asset_id": "C", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.03},
            {"asset_id": "D", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.03},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.12, "overheat_avoid": False, "crowded_late_entry": False, "entry_window_v2": "low_congestion_opportunity"},
            {"asset_id": "B", "dragon_risk_score": 0.12, "overheat_avoid": False, "crowded_late_entry": False, "entry_window_v2": "recovery_or_repair"},
            {"asset_id": "C", "dragon_risk_score": 0.12, "overheat_avoid": False, "crowded_late_entry": False, "entry_window_v2": "early_setup"},
            {"asset_id": "D", "dragon_risk_score": 0.12, "overheat_avoid": False, "crowded_late_entry": False, "entry_window_v2": "acceleration_entry"},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    must_watch = result["must_watch"]
    opp_ids = must_watch[must_watch["watch_group"] == "opportunity_watch"]["asset_id"].tolist()
    assert opp_ids == ["C", "B", "A"]


def test_build_watchlist_diagnostics_only_keeps_top_ranked_breakout_trend_candidates():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 5, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 10, "score_total": 88.0},
            {"trade_date": "2026-05-20", "asset_id": "C", "rank": 25, "score_total": 82.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
            {"asset_id": "B", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
            {"asset_id": "C", "amount_vs_20d": 1.1, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.10, "entry_window_v2": "early_setup"},
            {"asset_id": "B", "dragon_risk_score": 0.10, "entry_window_v2": "breakout_entry"},
            {"asset_id": "C", "dragon_risk_score": 0.10, "entry_window_v2": "breakout_entry"},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "event_structure"] == "weak_to_strong_candidate"
    assert full.loc["A", "watch_group"] == "opportunity_watch"
    assert full.loc["B", "event_structure"] == "trend_continuation_candidate"
    assert full.loc["B", "watch_group"] == "opportunity_watch"
    assert full.loc["C", "event_structure"] == ""
    assert full.loc["C", "watch_group"] == "candidate"


def test_build_watchlist_diagnostics_separates_high_odds_burst_from_low_risk_opportunity():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 8, "score_total": 93.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 9, "score_total": 92.0},
            {"trade_date": "2026-05-20", "asset_id": "C", "rank": 10, "score_total": 91.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 3.2, "high_to_close_drawdown": 0.03, "volatility_5d": 0.07},
            {"asset_id": "B", "amount_vs_20d": 3.2, "high_to_close_drawdown": 0.09, "volatility_5d": 0.07},
            {"asset_id": "C", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.02, "volatility_5d": 0.02},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.30, "entry_window_v2": "breakout_entry"},
            {"asset_id": "B", "dragon_risk_score": 0.30, "entry_window_v2": "breakout_entry"},
            {"asset_id": "C", "dragon_risk_score": 0.10, "entry_window_v2": "early_setup"},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "high_odds_burst_watch"
    assert full.loc["A", "risk_note"] == "high_odds_burst"
    assert full.loc["B", "watch_group"] == "risk_watch"
    assert "intraday_fade" in full.loc["B", "risk_note"]
    assert full.loc["C", "watch_group"] == "opportunity_watch"
    assert result["must_watch"]["watch_group"].tolist() == [
        "risk_watch",
        "high_odds_burst_watch",
        "opportunity_watch",
    ]


def test_build_watchlist_diagnostics_keeps_amount_only_burst_out_of_hard_risk():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 6, "score_total": 93.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 7, "score_total": 92.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 5.0, "high_to_close_drawdown": 0.03, "volatility_5d": 0.04},
            {"asset_id": "B", "amount_vs_20d": 5.0, "high_to_close_drawdown": 0.09, "volatility_5d": 0.04},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.20, "entry_window_v2": "breakout_entry"},
            {"asset_id": "B", "dragon_risk_score": 0.20, "entry_window_v2": "breakout_entry"},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "high_odds_burst_watch"
    assert "extreme_amount" in full.loc["A", "risk_note"]
    assert full.loc["B", "watch_group"] == "risk_watch"
    assert "intraday_fade" in full.loc["B", "risk_note"]


def test_build_watchlist_diagnostics_requires_dragon_lhb_confluence_for_score_only_hard_risk():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 5, "score_total": 94.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 6, "score_total": 93.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 3.0, "high_to_close_drawdown": 0.02, "volatility_5d": 0.06},
            {"asset_id": "B", "amount_vs_20d": 3.0, "high_to_close_drawdown": 0.02, "volatility_5d": 0.06},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.76, "entry_window_v2": "breakout_entry"},
            {"asset_id": "B", "dragon_risk_score": 0.76, "entry_window_v2": "breakout_entry"},
        ]
    )
    lhb_frame = pd.DataFrame(
        [
            {"asset_id": "A", "lhb_risk_score": 0.20, "lhb_negative_net_buy": False},
            {"asset_id": "B", "lhb_risk_score": 0.74, "lhb_negative_net_buy": False},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "high_odds_burst_watch"
    assert full.loc["B", "watch_group"] == "risk_watch"
    assert "dragon_lhb_risk_confluence" in full.loc["B", "risk_note"]


def test_build_watchlist_diagnostics_treats_negative_lhb_as_hard_risk():
    top_scores = pd.DataFrame(
        [{"trade_date": "2026-05-20", "asset_id": "A", "rank": 4, "score_total": 94.0}]
    )
    factor_frame = pd.DataFrame(
        [{"asset_id": "A", "amount_vs_20d": 3.0, "high_to_close_drawdown": 0.02, "volatility_5d": 0.06}]
    )
    dragon_frame = pd.DataFrame(
        [{"asset_id": "A", "dragon_risk_score": 0.20, "entry_window_v2": "breakout_entry"}]
    )
    lhb_frame = pd.DataFrame(
        [{"asset_id": "A", "lhb_risk_score": 0.20, "lhb_negative_net_buy": True}]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "risk_watch"
    assert "lhb_negative_net_buy" in full.loc["A", "risk_note"]


def test_build_watchlist_diagnostics_keeps_standalone_lhb_high_pump_as_high_odds_burst():
    top_scores = pd.DataFrame(
        [{"trade_date": "2026-05-20", "asset_id": "A", "rank": 4, "score_total": 94.0}]
    )
    factor_frame = pd.DataFrame(
        [{"asset_id": "A", "amount_vs_20d": 3.0, "high_to_close_drawdown": 0.02, "volatility_5d": 0.06}]
    )
    dragon_frame = pd.DataFrame(
        [{"asset_id": "A", "dragon_risk_score": 0.20, "entry_window_v2": "breakout_entry"}]
    )
    lhb_frame = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "lhb_risk_score": 0.45,
                "lhb_negative_net_buy": False,
                "lhb_institution_selling": False,
                "lhb_high_pump_risk": True,
            }
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=lhb_frame,
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    full = result["full"].set_index("asset_id")
    assert full.loc["A", "watch_group"] == "high_odds_burst_watch"
    assert "lhb_high_pump_risk" in full.loc["A", "risk_note"]


def test_build_watchlist_diagnostics_prioritizes_trend_continuation_before_weak_to_strong():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 3, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 4, "score_total": 88.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
            {"asset_id": "B", "amount_vs_20d": 1.2, "high_to_close_drawdown": 0.01, "volatility_5d": 0.02},
        ]
    )
    dragon_frame = pd.DataFrame(
        [
            {"asset_id": "A", "dragon_risk_score": 0.10, "entry_window_v2": "early_setup"},
            {"asset_id": "B", "dragon_risk_score": 0.10, "entry_window_v2": "breakout_entry"},
        ]
    )

    result = build_watchlist_diagnostics(
        trade_date="2026-05-20",
        top_scores=top_scores,
        factor_frame=factor_frame,
        dragon_frame=dragon_frame,
        lhb_frame=pd.DataFrame(),
        event_frame=pd.DataFrame(),
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    opp_ids = result["must_watch"][result["must_watch"]["watch_group"] == "opportunity_watch"]["asset_id"].tolist()
    assert opp_ids == ["B", "A"]
