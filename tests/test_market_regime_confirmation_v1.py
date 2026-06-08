from pathlib import Path
import subprocess
import sys

import pandas as pd

from stock_research.market_regime_confirmation_v1 import (
    REGIME_COLUMNS,
    build_segment_diagnostics,
    build_market_regime_confirmation_from_frames,
    run_market_regime_confirmation_v1_backtest,
    run_regime_confirmation_backtest_from_frames,
    write_market_regime_confirmation_outputs,
)


def _emotion_rows(scores: list[float], states: list[str] | None = None, risks: list[str] | None = None) -> pd.DataFrame:
    states = states or ["neutral"] * len(scores)
    risks = risks or ["medium"] * len(scores)
    return pd.DataFrame(
        [
            {
                "trade_date": f"2026-01-{index + 2:02d}",
                "emotion_score": score,
                "emotion_state": states[index],
                "risk_state": risks[index],
            }
            for index, score in enumerate(scores)
        ]
    )


def test_build_regime_features_smooths_daily_emotion_and_preserves_schema() -> None:
    emotion = _emotion_rows(
        [20, 30, 40, 50, 60, 70],
        states=["panic", "cold", "neutral", "neutral", "hot", "euphoria"],
        risks=["high", "high", "medium", "medium", "low", "low"],
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    assert result.columns.tolist() == REGIME_COLUMNS
    assert result["trade_date"].tolist() == [
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]
    last = result.iloc[-1]
    assert round(last["emotion_score_5d"], 2) == 50.00
    assert round(last["emotion_score_10d"], 2) == 45.00
    assert round(last["emotion_slope_5d"], 2) == 40.00
    assert int(last["risk_high_days_5d"]) == 1
    assert int(last["hot_or_euphoria_days_5d"]) == 2
    assert int(last["panic_or_cold_days_5d"]) == 1


def test_build_regime_features_normalizes_mixed_date_formats_and_drops_invalid_dates() -> None:
    emotion = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "emotion_score": 50},
            {"trade_date": "2026/01/03", "emotion_score": 55},
            {"trade_date": 20260104, "emotion_score": 60},
            {"trade_date": 20260105.0, "emotion_score": 62},
            {"trade_date": None, "emotion_score": 63},
            {"trade_date": "bad-date", "emotion_score": 65},
        ]
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    assert result["trade_date"].tolist() == ["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    assert "1970-01-01" not in result["trade_date"].tolist()


def test_policy_impulse_requires_market_response_and_accelerates_rerisk() -> None:
    emotion = _emotion_rows(
        [25, 26, 28, 32, 45, 58, 64],
        states=["panic", "cold", "cold", "neutral", "hot", "hot", "euphoria"],
        risks=["high", "high", "high", "medium", "medium", "low", "low"],
    )
    policy = pd.DataFrame(
        [
            {
                "event_date": "2026-01-05",
                "event_type": "financial_policy",
                "policy_strength": 0.9,
                "description": "liquidity support",
                "source": "manual",
            }
        ]
    )

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    candidate_response = result[result["trade_date"].isin(["2026-01-06", "2026-01-07"])]
    assert candidate_response["confirmed_regime_state"].tolist() == ["bull_impulse", "bull_impulse"]
    assert candidate_response["target_exposure"].tolist() == [1.0, 1.0]
    assert bool(result.loc[result["trade_date"] == "2026-01-05", "policy_impulse_candidate"].iloc[0]) is True


def test_policy_impulse_expiry_uses_downgrade_hysteresis_on_one_weak_day() -> None:
    emotion = _emotion_rows(
        [25, 26, 28, 32, 45, 58, 64],
        states=["panic", "cold", "cold", "neutral", "hot", "hot", "euphoria"],
        risks=["high", "high", "high", "medium", "medium", "low", "low"],
    )
    policy = pd.DataFrame([{"event_date": "2026-01-05", "policy_strength": 0.9}])

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    expired_day = result.loc[result["trade_date"] == "2026-01-08"].iloc[0]
    assert bool(expired_day["policy_impulse_candidate"]) is False
    assert expired_day["raw_regime_state"] in {"neutral", "weak_repair", "bear"}
    assert expired_day["confirmed_regime_state"] in {"bull_impulse", "bull_trend"}
    assert expired_day["transition_reason"] == "downgrade_wait_for_confirmation"


def test_policy_impulse_to_overheated_trend_transition_is_explicit() -> None:
    emotion = _emotion_rows(
        [60, 60, 60, 60, 90, 100, 100, 100, 100],
        states=["neutral", "neutral", "neutral", "neutral", "hot", "euphoria", "euphoria", "euphoria", "euphoria"],
        risks=["low", "low", "low", "low", "low", "low", "low", "low", "low"],
    )
    policy = pd.DataFrame([{"event_date": "2026-01-06", "policy_strength": 0.9}])

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    first_overheated = result.loc[result["trade_date"] == "2026-01-09"].iloc[0]
    confirmed_transition = result.loc[result["trade_date"] == "2026-01-10"].iloc[0]
    assert first_overheated["raw_regime_state"] == "overheated"
    assert first_overheated["confirmed_regime_state"] == "bull_impulse"
    assert first_overheated["transition_reason"] == "impulse_to_trend_wait_for_confirmation"
    assert confirmed_transition["raw_regime_state"] == "overheated"
    assert confirmed_transition["confirmed_regime_state"] == "bull_trend"
    assert confirmed_transition["target_exposure"] == 1.0
    assert confirmed_transition["transition_reason"] == "impulse_to_trend_confirmed"


def test_policy_impulse_trend_continuation_counts_bull_and_overheated_as_one_group() -> None:
    emotion = _emotion_rows(
        [60, 60, 60, 60, 90, 100, 100, 100, 70, 100, 70, 100],
        states=[
            "neutral",
            "neutral",
            "neutral",
            "neutral",
            "hot",
            "euphoria",
            "euphoria",
            "euphoria",
            "hot",
            "euphoria",
            "hot",
            "euphoria",
        ],
        risks=["low"] * 12,
    )
    policy = pd.DataFrame([{"event_date": "2026-01-06", "policy_strength": 0.9}])

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    alternating = result.loc[result["trade_date"].isin(["2026-01-09", "2026-01-10", "2026-01-11", "2026-01-12"])]
    assert alternating["raw_regime_state"].tolist() == ["overheated", "bull_trend", "overheated", "bull_trend"]
    confirmed_transition = result.loc[result["trade_date"] == "2026-01-10"].iloc[0]
    assert confirmed_transition["confirmed_regime_state"] == "bull_trend"
    assert confirmed_transition["transition_reason"] == "impulse_to_trend_confirmed"


def test_confirmed_regime_does_not_downgrade_on_one_bad_day() -> None:
    emotion = _emotion_rows(
        [70, 72, 74, 75, 73, 71, 30, 68, 67],
        states=["hot", "hot", "euphoria", "euphoria", "hot", "hot", "panic", "hot", "hot"],
        risks=["low", "low", "low", "low", "low", "low", "high", "low", "low"],
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    bad_day = result.loc[result["trade_date"] == "2026-01-08"].iloc[0]
    assert bad_day["raw_regime_state"] in {"neutral", "weak_repair", "bear"}
    assert bad_day["confirmed_regime_state"] in {"bull_trend", "overheated"}
    assert bad_day["transition_reason"] == "downgrade_wait_for_confirmation"


def test_write_outputs_includes_segment_diagnostics_transitions_and_markdown_report(tmp_path: Path) -> None:
    regime = build_market_regime_confirmation_from_frames(
        pd.DataFrame(
            [
                {"trade_date": "2024-09-23", "emotion_score": 30, "emotion_state": "cold", "risk_state": "high"},
                {"trade_date": "2024-09-24", "emotion_score": 45, "emotion_state": "neutral", "risk_state": "medium"},
                {"trade_date": "2024-09-25", "emotion_score": 60, "emotion_state": "hot", "risk_state": "low"},
                {"trade_date": "2024-11-11", "emotion_score": 55, "emotion_state": "neutral", "risk_state": "medium"},
            ]
        ),
        pd.DataFrame([{"event_date": "2024-09-24", "policy_strength": 0.9}]),
    )

    paths = write_market_regime_confirmation_outputs(regime, output_dir=tmp_path)

    assert paths["regime_path"].name == "market_regime_confirmation_daily.csv"
    assert paths["segment_diagnostics_path"].name == "market_regime_segment_diagnostics.csv"
    assert paths["transition_path"].name == "market_regime_transitions.csv"
    assert paths["report_path"].name == "market_regime_confirmation_v1_report.md"
    assert pd.read_csv(paths["regime_path"]).columns.tolist() == REGIME_COLUMNS

    segment = pd.read_csv(paths["segment_diagnostics_path"])
    assert {
        "segment_name",
        "start_date",
        "end_date",
        "days",
        "avg_target_exposure",
        "dominant_regime",
        "regime_changes",
        "state_distribution",
        "transition_dates",
        "strategy_performance",
        "raw_confirmed_disagree_days",
    }.issubset(segment.columns)
    assert segment["segment_name"].tolist() == [
        "pre_924_2024",
        "policy_rally_2024",
        "post_rally_2024",
        "post_2025",
        "full_period",
    ]
    assert int(segment.loc[segment["segment_name"] == "policy_rally_2024", "days"].iloc[0]) == 2

    transitions = pd.read_csv(paths["transition_path"])
    assert transitions.columns.tolist() == [
        "trade_date",
        "raw_regime_state",
        "confirmed_regime_state",
        "target_exposure",
        "style_bias",
        "transition_reason",
    ]
    assert transitions["trade_date"].iloc[0] == "2024-09-23"

    report = paths["report_path"].read_text(encoding="utf-8")
    assert report.startswith("# Market Regime Confirmation V1 Report")
    assert "## Segment Diagnostics" in report
    assert "## Confirmed Regime Distribution" in report
    assert "## Transitions" in report


def test_write_outputs_passes_equity_into_segment_strategy_performance(tmp_path: Path) -> None:
    regime = pd.DataFrame(
        [
            {
                "trade_date": "2024-09-24",
                "raw_regime_state": "bear",
                "confirmed_regime_state": "bear",
                "target_exposure": 0.2,
            },
            {
                "trade_date": "2024-09-25",
                "raw_regime_state": "bull_trend",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
            },
        ]
    )
    equity = pd.DataFrame(
        [
            {"trade_date": "2024-09-24", "strategy_family": "fixed_mid_trend", "daily_return": 0.10},
            {"trade_date": "2024-09-25", "strategy_family": "fixed_mid_trend", "daily_return": -0.05},
        ]
    )

    paths = write_market_regime_confirmation_outputs(regime, output_dir=tmp_path, equity=equity)

    segment = pd.read_csv(paths["segment_diagnostics_path"])
    performance = segment.loc[segment["segment_name"] == "policy_rally_2024", "strategy_performance"].iloc[0]
    assert "fixed_mid_trend:ret=0.045000" in performance
    assert "dd=-0.050000" in performance


def test_malformed_equity_without_date_columns_is_ignored_for_segment_performance(tmp_path: Path) -> None:
    regime = pd.DataFrame(
        [
            {
                "trade_date": "2024-09-24",
                "raw_regime_state": "bear",
                "confirmed_regime_state": "bear",
                "target_exposure": 0.2,
            }
        ]
    )
    malformed_equity = pd.DataFrame(
        [{"strategy_family": "fixed_mid_trend", "daily_return": 0.10, "some_other_date": "2024-09-24"}]
    )

    paths = write_market_regime_confirmation_outputs(regime, output_dir=tmp_path, equity=malformed_equity)

    segment = pd.read_csv(paths["segment_diagnostics_path"]).fillna("")
    performance = segment.loc[segment["segment_name"] == "policy_rally_2024", "strategy_performance"].iloc[0]
    assert performance == ""


def test_build_segment_diagnostics_serializes_state_transitions_and_optional_strategy_performance() -> None:
    regime = pd.DataFrame(
        [
            {
                "trade_date": "2024-09-24",
                "raw_regime_state": "bear",
                "confirmed_regime_state": "bear",
                "target_exposure": 0.2,
                "style_bias": "cash_defensive",
                "transition_reason": "unchanged",
            },
            {
                "trade_date": "2024-09-25",
                "raw_regime_state": "bull_trend",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "style_bias": "growth_mid_trend",
                "transition_reason": "upgrade_confirmed",
            },
            {
                "trade_date": "2024-09-26",
                "raw_regime_state": "bull_trend",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "style_bias": "growth_mid_trend",
                "transition_reason": "unchanged",
            },
        ]
    )
    equity = pd.DataFrame(
        [
            {"trade_date": "2024-09-24", "strategy_family": "fixed_mid_trend", "daily_return": 0.10},
            {"trade_date": "2024-09-25", "strategy_family": "fixed_mid_trend", "daily_return": -0.05},
            {"trade_date": "2024-09-26", "strategy_family": "fixed_mid_trend", "daily_return": 0.02},
            {"trade_date": "2024-09-24", "strategy_family": "regime_confirmed_exposure", "daily_return": 0.04},
            {"trade_date": "2024-09-25", "strategy_family": "regime_confirmed_exposure", "daily_return": 0.03},
        ]
    )

    segment = build_segment_diagnostics(regime, equity=equity)

    rally = segment.loc[segment["segment_name"] == "policy_rally_2024"].iloc[0]
    assert rally["state_distribution"] == "bull_trend:2;bear:1"
    assert rally["transition_dates"] == "2024-09-25"
    assert "fixed_mid_trend:ret=0.065900,dd=-0.050000,days=3" in rally["strategy_performance"]
    assert "regime_confirmed_exposure:ret=0.071200,dd=0.000000,days=2" in rally["strategy_performance"]
    assert "|" in rally["strategy_performance"]


def test_build_segment_diagnostics_leaves_strategy_performance_empty_without_equity() -> None:
    segment = build_segment_diagnostics(
        pd.DataFrame(
            [
                {
                    "trade_date": "2024-09-24",
                    "raw_regime_state": "bear",
                    "confirmed_regime_state": "bear",
                    "target_exposure": 0.2,
                }
            ]
        )
    )

    rally = segment.loc[segment["segment_name"] == "policy_rally_2024"].iloc[0]
    assert rally["strategy_performance"] == ""


def _funnel_for_dates(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date,
                "asset_id": "G1",
                "stock_name": "科技A",
                "industry_name": "软件",
                "mid_trend_funnel_score": 90,
                "shadow_top10_rank": 1,
                "volatility_20_score": 60,
                "max_drawdown_20_score": 60,
                "ma60_slope_score": 80,
                "score_total": 90,
            }
            for date in dates
        ]
    )


def test_regime_backtest_applies_confirmed_exposure_to_mid_trend_returns() -> None:
    emotion = _emotion_rows(
        [20, 20, 20, 70, 72],
        states=["panic", "panic", "panic", "hot", "hot"],
        risks=["high", "high", "high", "low", "low"],
    )
    dates = emotion["trade_date"].tolist()
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "G1", "close": 100.0},
            {"trade_date": "2026-01-03", "asset_id": "G1", "close": 90.0},
            {"trade_date": "2026-01-04", "asset_id": "G1", "close": 81.0},
            {"trade_date": "2026-01-05", "asset_id": "G1", "close": 89.1},
            {"trade_date": "2026-01-06", "asset_id": "G1", "close": 98.01},
            {"trade_date": "2026-01-07", "asset_id": "G1", "close": 107.811},
        ]
    )

    result = run_regime_confirmation_backtest_from_frames(
        emotion=emotion,
        funnel=_funnel_for_dates(dates),
        prices=prices,
        start_date="2026-01-02",
        end_date="2026-01-06",
        top_n=1,
    )

    summary = result["summary"].set_index("strategy_family")
    assert "fixed_mid_trend" in summary.index
    assert "regime_confirmed_exposure" in summary.index
    assert summary.loc["regime_confirmed_exposure", "max_drawdown"] > summary.loc["fixed_mid_trend", "max_drawdown"]


def test_regime_backtest_returns_style_switch_baselines_and_diagnostics(tmp_path: Path) -> None:
    emotion = pd.DataFrame(
        [
            {"trade_date": "2024-09-24", "emotion_score": 72, "emotion_state": "hot", "risk_state": "low"},
            {"trade_date": "2024-09-25", "emotion_score": 55, "emotion_state": "neutral", "risk_state": "medium"},
            {"trade_date": "2024-09-26", "emotion_score": 30, "emotion_state": "panic", "risk_state": "high"},
            {"trade_date": "2024-09-27", "emotion_score": 68, "emotion_state": "hot", "risk_state": "low"},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2024-09-24", "asset_id": "G1", "close": 100.0},
            {"trade_date": "2024-09-25", "asset_id": "G1", "close": 101.0},
            {"trade_date": "2024-09-26", "asset_id": "G1", "close": 102.0},
            {"trade_date": "2024-09-27", "asset_id": "G1", "close": 103.0},
            {"trade_date": "2024-09-30", "asset_id": "G1", "close": 104.0},
        ]
    )

    result = run_regime_confirmation_backtest_from_frames(
        emotion=emotion,
        funnel=_funnel_for_dates(emotion["trade_date"].tolist()),
        prices=prices,
        start_date="2024-09-24",
        end_date="2024-09-27",
        output_dir=tmp_path,
        top_n=1,
    )

    expected_families = {
        "fixed_mid_trend",
        "emotion_budget_only",
        "emotion_style_switch",
        "regime_confirmed_exposure",
    }
    assert set(result["summary"]["strategy_family"]) == expected_families
    assert set(result["equity"]["strategy_family"]) == expected_families

    segment = pd.read_csv(result["paths"]["segment_diagnostics_path"])
    performance = segment.loc[segment["segment_name"] == "policy_rally_2024", "strategy_performance"].iloc[0]
    for family in expected_families:
        assert f"{family}:ret=" in performance


def test_regime_confirmed_exposure_holds_weight_between_weekly_rebalances(monkeypatch) -> None:
    dates = [
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
        "2026-01-09",
        "2026-01-12",
    ]
    regime = pd.DataFrame(
        {
            "trade_date": dates,
            "target_exposure": [0.2, 1.0, 0.5, 0.7, 0.8, 0.3],
            "rebalance_allowed": [False, False, False, False, True, False],
            "emotion_state": ["neutral"] * len(dates),
            "risk_state": ["medium"] * len(dates),
            "emotion_score": [50] * len(dates),
        }
    )
    prices = pd.DataFrame(
        [{"trade_date": date, "asset_id": "G1", "close": 100.0 + index} for index, date in enumerate(dates)]
        + [{"trade_date": "2026-01-13", "asset_id": "G1", "close": 106.0}]
    )

    import stock_research.market_regime_confirmation_v1 as module

    monkeypatch.setattr(
        module,
        "build_market_regime_confirmation_from_frames",
        lambda emotion, policy_events=None: regime,
    )

    result = run_regime_confirmation_backtest_from_frames(
        emotion=regime[["trade_date", "emotion_score", "emotion_state", "risk_state"]],
        funnel=_funnel_for_dates(dates),
        prices=prices,
        start_date="2026-01-05",
        end_date="2026-01-12",
        top_n=1,
    )

    confirmed = result["equity"].loc[
        result["equity"]["strategy_family"] == "regime_confirmed_exposure",
        ["trade_date", "invested_weight"],
    ]
    assert confirmed["trade_date"].tolist() == dates
    assert confirmed["invested_weight"].tolist() == [0.2, 0.2, 0.2, 0.2, 0.8, 0.8]


def test_file_level_runner_reads_csvs_loads_prices_and_runs_backtest(tmp_path: Path, monkeypatch) -> None:
    emotion_path = tmp_path / "emotion.csv"
    funnel_path = tmp_path / "funnel.csv"
    policy_path = tmp_path / "policy.csv"
    output_dir = tmp_path / "out"
    _emotion_rows([50]).to_csv(emotion_path, index=False)
    _funnel_for_dates(["2026-01-02"]).to_csv(funnel_path, index=False)
    pd.DataFrame([{"event_date": "2026-01-02", "policy_strength": 0.8}]).to_csv(policy_path, index=False)
    prices = pd.DataFrame([{"trade_date": "2026-01-02", "asset_id": "G1", "close": 100.0}])
    captured: dict[str, object] = {}

    def fake_load_prices(start_date: str, end_date: str, *, adjust_type: str, service: str) -> pd.DataFrame:
        captured["load_prices"] = {
            "start_date": start_date,
            "end_date": end_date,
            "adjust_type": adjust_type,
            "service": service,
        }
        return prices

    def fake_run_backtest_from_frames(**kwargs):
        captured["backtest"] = kwargs
        return {
            "regime": pd.DataFrame([{"trade_date": "2026-01-02"}]),
            "equity": pd.DataFrame([{"trade_date": "2026-01-02"}]),
            "paths": {"regime_path": output_dir / "market_regime_confirmation_daily.csv"},
        }

    import stock_research.market_regime_confirmation_v1 as module

    monkeypatch.setattr(module, "load_style_switch_prices", fake_load_prices)
    monkeypatch.setattr(module, "run_regime_confirmation_backtest_from_frames", fake_run_backtest_from_frames)

    result = run_market_regime_confirmation_v1_backtest(
        start_date="2026-01-02",
        end_date="2026-01-03",
        emotion_path=emotion_path,
        funnel_detail_path=funnel_path,
        policy_event_path=policy_path,
        output_dir=output_dir,
        top_n=3,
        adjust_type="qfq",
        service="test_service",
    )

    assert result["paths"]["regime_path"].name == "market_regime_confirmation_daily.csv"
    assert captured["load_prices"] == {
        "start_date": "2026-01-02",
        "end_date": "2026-01-03",
        "adjust_type": "qfq",
        "service": "test_service",
    }
    backtest = captured["backtest"]
    assert backtest["start_date"] == "2026-01-02"
    assert backtest["end_date"] == "2026-01-03"
    assert backtest["top_n"] == 3
    assert backtest["output_dir"] == output_dir
    assert backtest["prices"].equals(prices)
    assert backtest["emotion"]["emotion_score"].tolist() == [50]
    assert backtest["funnel"]["asset_id"].tolist() == ["G1"]
    assert backtest["policy_events"]["policy_strength"].tolist() == [0.8]


def test_market_regime_confirmation_v1_backtest_cli_help_lists_required_inputs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_research.cli",
            "market-regime-confirmation-v1-backtest",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "market-regime-confirmation-v1-backtest" in result.stdout
    assert "--start-date" in result.stdout
    assert "--end-date" in result.stdout
    assert "--emotion-path" in result.stdout
    assert "--funnel-detail-path" in result.stdout
    assert "--policy-event-path" in result.stdout
    assert "--output-dir" in result.stdout
    assert "--top-n" in result.stdout
    assert "--adjust-type" in result.stdout


def test_market_regime_confirmation_v1_backtest_cli_dispatch_prints_summary_path(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    import stock_research.cli as cli
    import stock_research.market_regime_confirmation_v1 as module

    output_dir = tmp_path / "out"

    def fake_run_market_regime_confirmation_v1_backtest(**kwargs):
        assert kwargs["start_date"] == "2026-01-02"
        assert kwargs["end_date"] == "2026-01-03"
        assert kwargs["emotion_path"] == "emotion.csv"
        assert kwargs["funnel_detail_path"] == "funnel.csv"
        assert kwargs["policy_event_path"] == "policy.csv"
        assert kwargs["output_dir"] == str(output_dir)
        assert kwargs["top_n"] == 2
        assert kwargs["adjust_type"] == "qfq"
        return {
            "regime": pd.DataFrame([{"trade_date": "2026-01-02"}, {"trade_date": "2026-01-03"}]),
            "equity": pd.DataFrame([{"trade_date": "2026-01-02"}]),
            "paths": {
                "regime_path": output_dir / "regime.csv",
                "summary_path": output_dir / "summary.csv",
            },
        }

    monkeypatch.setattr(
        module,
        "run_market_regime_confirmation_v1_backtest",
        fake_run_market_regime_confirmation_v1_backtest,
    )

    result = cli.main_for_args(
        [
            "market-regime-confirmation-v1-backtest",
            "--start-date",
            "2026-01-02",
            "--end-date",
            "2026-01-03",
            "--emotion-path",
            "emotion.csv",
            "--funnel-detail-path",
            "funnel.csv",
            "--policy-event-path",
            "policy.csv",
            "--output-dir",
            str(output_dir),
            "--top-n",
            "2",
            "--adjust-type",
            "qfq",
        ]
    )

    assert result == 0
    assert capsys.readouterr().out.splitlines() == [
        f"market_regime_confirmation|summary|{output_dir / 'summary.csv'}",
        "market_regime_confirmation|regime_rows|2",
        "market_regime_confirmation|equity_rows|1",
        f"market_regime_confirmation|output_dir|{output_dir}",
    ]
