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


def test_build_watchlist_diagnostics_infers_weak_to_strong_and_break_then_reversal_from_windows():
    top_scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-20", "asset_id": "B", "rank": 2, "score_total": 88.0},
        ]
    )
    factor_frame = pd.DataFrame(
        [
            {"asset_id": "A", "amount_vs_20d": 1.3, "high_to_close_drawdown": 0.012, "volatility_5d": 0.028},
            {"asset_id": "B", "amount_vs_20d": 1.4, "high_to_close_drawdown": 0.010, "volatility_5d": 0.020},
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
                "entry_window_v2": "acceleration_entry",
            },
            {
                "asset_id": "B",
                "dragon_risk_score": 0.05,
                "overheat_avoid": False,
                "crowded_late_entry": False,
                "entry_window": "early_setup",
                "entry_window_v2": "breakout_entry",
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
    assert full.loc["A", "event_structure"] == "weak_to_strong_candidate"
    assert full.loc["B", "event_structure"] == "break_then_reversal_candidate"


def test_build_watchlist_diagnostics_prioritizes_failure_risk_ahead_of_generic_risk():
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
            {"asset_id": "B", "amount_vs_20d": 4.8, "high_to_close_drawdown": 0.02, "volatility_5d": 0.05},
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
        lhb_frame=pd.DataFrame(),
        event_frame=event_frame,
        market_frame=pd.DataFrame(),
        risk_watch_n=10,
        opportunity_watch_n=10,
    )

    must_watch = result["must_watch"]
    risk_ids = must_watch[must_watch["watch_group"] == "risk_watch"]["asset_id"].tolist()
    assert risk_ids == ["A", "C", "B"]


def test_build_watchlist_diagnostics_prioritizes_second_wave_over_trend_continuation():
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
    assert opp_ids == ["A", "B", "C", "D"]
