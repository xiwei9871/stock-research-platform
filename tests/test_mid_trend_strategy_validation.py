from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.current_mid_trend_strategy_v1 import (
    build_current_mid_trend_strategy_v1_from_frames,
)
from stock_research.mid_trend_shadow_backtest import (
    build_mid_trend_shadow_backtest_from_frames,
)
import stock_research.mid_trend_strategy_validation as mid_trend_strategy_validation
from stock_research.mid_trend_strategy_validation import (
    build_mid_trend_validation_scorecard,
    discover_mid_trend_strategy_candidates,
    execute_mid_trend_candidate,
    filter_complete_mid_trend_candidates,
    rank_mid_trend_validation_scorecard,
    run_mid_trend_strategy_validation,
)


def test_discover_mid_trend_strategy_candidates_returns_known_complete_entries() -> None:
    candidates = discover_mid_trend_strategy_candidates()

    ids = {item["strategy_id"] for item in candidates}
    assert "current_mid_trend_strategy_v1" in ids
    assert "mid_trend_shadow_backtest" in ids


def test_known_mid_trend_candidates_expose_importable_runner_names() -> None:
    candidates = {
        item["strategy_id"]: item
        for item in discover_mid_trend_strategy_candidates()
    }

    expected_runners = {
        "current_mid_trend_strategy_v1": (
            "stock_research.current_mid_trend_strategy_v1",
            "run_current_mid_trend_strategy_v1_backtest",
        ),
        "mid_trend_shadow_backtest": (
            "stock_research.mid_trend_shadow_backtest",
            "run_mid_trend_shadow_backtest",
        ),
    }

    for strategy_id, (module_name, runner_name) in expected_runners.items():
        candidate = candidates[strategy_id]
        module = import_module(module_name)

        assert candidate["runner_name"] == runner_name
        assert hasattr(module, runner_name)
        assert callable(getattr(module, runner_name))


def test_known_mid_trend_candidates_result_keys_match_actual_payloads() -> None:
    candidates = {
        item["strategy_id"]: item
        for item in discover_mid_trend_strategy_candidates()
    }

    current_result = build_current_mid_trend_strategy_v1_from_frames(
        regime=_current_regime_frame(),
        funnel=_current_funnel_frame(),
        prices=_current_prices_frame(),
        asset_names=_current_asset_names_frame(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n=2,
    )
    shadow_result = build_mid_trend_shadow_backtest_from_frames(
        shadow_top10=_shadow_top10_frame(),
        prices=_shadow_prices_frame(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n=2,
        transaction_cost_bps=10.0,
    )

    assert candidates["current_mid_trend_strategy_v1"]["result_keys"] <= current_result.keys()
    assert candidates["mid_trend_shadow_backtest"]["result_keys"] <= shadow_result.keys()


def test_filter_complete_mid_trend_candidates_keeps_only_complete_portfolio_versions() -> None:
    candidates = [
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "group": "portfolio",
            "result_keys": {"holdings", "trades", "equity", "summary"},
        },
        {
            "strategy_id": "mid_trend_incomplete_portfolio",
            "group": "portfolio",
            "result_keys": {"holdings", "trades", "equity"},
        },
        {
            "strategy_id": "mid_trend_portfolio_review",
            "group": "review",
            "result_keys": {"review_rows", "portfolio_summary"},
        },
    ]

    filtered = filter_complete_mid_trend_candidates(candidates)

    assert [item["strategy_id"] for item in filtered] == ["current_mid_trend_strategy_v1"]


def test_mid_trend_validation_module_exposes_only_task2_scorecard_api() -> None:
    assert hasattr(mid_trend_strategy_validation, "build_mid_trend_validation_scorecard")
    assert hasattr(mid_trend_strategy_validation, "rank_mid_trend_validation_scorecard")
    assert not hasattr(mid_trend_strategy_validation, "normalize_mid_trend_validation_result")


def test_build_mid_trend_validation_scorecard_consumes_real_candidate_outputs() -> None:
    current_result = build_current_mid_trend_strategy_v1_from_frames(
        regime=_current_regime_frame(),
        funnel=_current_funnel_frame(),
        prices=_current_prices_frame(),
        asset_names=_current_asset_names_frame(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n=2,
    )
    shadow_result = build_mid_trend_shadow_backtest_from_frames(
        shadow_top10=_shadow_top10_frame(),
        prices=_shadow_prices_frame(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n=2,
        transaction_cost_bps=10.0,
    )

    scorecard = build_mid_trend_validation_scorecard(
        [
            {"strategy_id": "current_mid_trend_strategy_v1", **current_result},
            {"strategy_id": "mid_trend_shadow_backtest", **shadow_result},
        ]
    )

    assert set(scorecard["strategy_id"]) == {
        "current_mid_trend_strategy_v1",
        "mid_trend_shadow_backtest",
    }
    current_row = scorecard.loc[
        scorecard["strategy_id"] == "current_mid_trend_strategy_v1"
    ].iloc[0]
    shadow_row = scorecard.loc[
        scorecard["strategy_id"] == "mid_trend_shadow_backtest"
    ].iloc[0]
    assert current_row["total_return"] > 0
    assert current_row["max_drawdown"] == 0.0
    assert pd.isna(current_row["turnover_penalized_stability"])
    assert shadow_row["total_return"] > 0
    assert shadow_row["max_drawdown"] == 0.0


def test_build_mid_trend_validation_scorecard_extracts_five_metrics() -> None:
    scorecard = build_mid_trend_validation_scorecard(
        [
            {
                "strategy_id": "a",
                "summary_frame": pd.DataFrame(
                    [
                        {"metric": "total_return", "value": 0.50},
                        {"metric": "max_drawdown", "value": -0.10},
                        {"metric": "average_turnover", "value": 0.15},
                    ]
                ),
                "equity_frame": pd.DataFrame(
                    [
                        {"date": "2025-01-31", "equity": 1.02},
                        {"date": "2025-02-28", "equity": 1.05},
                    ]
                ),
            }
        ]
    )

    row = scorecard.iloc[0]
    assert row["strategy_id"] == "a"
    assert row["total_return"] == 0.50
    assert row["max_drawdown"] == -0.10
    assert row["return_drawdown_ratio"] == 5.0
    assert row["monthly_win_rate"] == 1.0
    assert row["turnover_penalized_stability"] > 0


def test_build_mid_trend_validation_scorecard_does_not_default_missing_turnover_to_zero() -> None:
    scorecard = build_mid_trend_validation_scorecard(
        [
            {
                "strategy_id": "current_mid_trend_strategy_v1",
                "summary": pd.DataFrame(
                    [
                        {
                            "strategy_family": "current_mid_trend_strategy_v1",
                            "total_return": 0.50,
                            "annualized_return": 0.40,
                            "max_drawdown": -0.10,
                            "days": 40,
                        }
                    ]
                ),
                "equity": pd.DataFrame(
                    [
                        {"trade_date": "2025-01-31", "equity": 1.02},
                        {"trade_date": "2025-02-28", "equity": 1.05},
                    ]
                ),
            }
        ]
    )

    row = scorecard.iloc[0]
    assert row["monthly_win_rate"] == 1.0
    assert pd.isna(row["turnover_penalized_stability"])


def test_build_mid_trend_validation_scorecard_sorts_equity_before_monthly_aggregation() -> None:
    scorecard = build_mid_trend_validation_scorecard(
        [
            {
                "strategy_id": "unsorted_equity",
                "summary_frame": pd.DataFrame(
                    [
                        {"metric": "total_return", "value": 0.20},
                        {"metric": "max_drawdown", "value": -0.10},
                        {"metric": "average_turnover", "value": 0.25},
                    ]
                ),
                "equity_frame": pd.DataFrame(
                    [
                        {"date": "2025-02-28", "equity": 1.20},
                        {"date": "2025-01-31", "equity": 1.00},
                        {"date": "2025-01-15", "equity": 0.90},
                        {"date": "2025-02-15", "equity": 0.80},
                    ]
                ),
            }
        ]
    )

    row = scorecard.iloc[0]
    assert row["monthly_win_rate"] == 1.0
    assert row["turnover_penalized_stability"] == 0.75


def test_rank_mid_trend_validation_scorecard_prefers_better_drawdown_efficiency_and_stability() -> None:
    ranked = rank_mid_trend_validation_scorecard(
        pd.DataFrame(
            [
                {
                    "strategy_id": "low_drawdown_but_weak",
                    "total_return": 0.08,
                    "max_drawdown": -0.04,
                    "return_drawdown_ratio": 2.0,
                    "monthly_win_rate": 0.45,
                    "turnover_penalized_stability": 0.30,
                },
                {
                    "strategy_id": "better_ratio",
                    "total_return": 0.42,
                    "max_drawdown": -0.14,
                    "return_drawdown_ratio": 3.0,
                    "monthly_win_rate": 0.60,
                    "turnover_penalized_stability": 0.35,
                },
                {
                    "strategy_id": "better_win_rate",
                    "total_return": 0.48,
                    "max_drawdown": -0.16,
                    "return_drawdown_ratio": 3.0,
                    "monthly_win_rate": 0.80,
                    "turnover_penalized_stability": 0.25,
                },
                {
                    "strategy_id": "best_stability",
                    "total_return": 0.44,
                    "max_drawdown": -0.18,
                    "return_drawdown_ratio": 3.0,
                    "monthly_win_rate": 0.80,
                    "turnover_penalized_stability": 0.70,
                },
                {
                    "strategy_id": "severe_drawdown",
                    "total_return": 0.90,
                    "max_drawdown": -0.35,
                    "return_drawdown_ratio": 2.57,
                    "monthly_win_rate": 0.90,
                    "turnover_penalized_stability": 0.85,
                },
            ]
        )
    )

    assert list(ranked["strategy_id"])[:4] == [
        "best_stability",
        "better_win_rate",
        "better_ratio",
        "low_drawdown_but_weak",
    ]
    assert ranked.iloc[-1]["strategy_id"] == "severe_drawdown"


def test_rank_mid_trend_validation_scorecard_prefers_zero_drawdown_when_other_metrics_are_strong() -> None:
    scorecard = build_mid_trend_validation_scorecard(
        [
            {
                "strategy_id": "zero_drawdown",
                "summary_frame": pd.DataFrame(
                    [
                        {"metric": "total_return", "value": 0.30},
                        {"metric": "max_drawdown", "value": 0.0},
                        {"metric": "average_turnover", "value": 0.10},
                    ]
                ),
                "equity_frame": pd.DataFrame(
                    [
                        {"date": "2025-01-31", "equity": 1.05},
                        {"date": "2025-02-28", "equity": 1.08},
                    ]
                ),
            },
            {
                "strategy_id": "solid_but_lower",
                "summary_frame": pd.DataFrame(
                    [
                        {"metric": "total_return", "value": 0.24},
                        {"metric": "max_drawdown", "value": -0.10},
                        {"metric": "average_turnover", "value": 0.30},
                    ]
                ),
                "equity_frame": pd.DataFrame(
                    [
                        {"date": "2025-01-31", "equity": 1.04},
                        {"date": "2025-02-28", "equity": 1.06},
                    ]
                ),
            },
        ]
    )
    zero_drawdown_row = scorecard.loc[scorecard["strategy_id"] == "zero_drawdown"].iloc[0]
    assert zero_drawdown_row["return_drawdown_ratio"] == float("inf")

    ranked = rank_mid_trend_validation_scorecard(scorecard)

    assert ranked.iloc[0]["strategy_id"] == "zero_drawdown"


def test_run_mid_trend_strategy_validation_returns_ranked_winner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.discover_mid_trend_strategy_candidates",
        lambda: [
            {
                "strategy_id": "winner",
                "group": "portfolio",
                "runner_name": "unused",
                "result_keys": {"holdings", "trades", "equity", "summary"},
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.execute_mid_trend_candidate",
        lambda candidate, start_date, end_date, output_dir, **kwargs: {
            "strategy_id": candidate["strategy_id"],
            "summary_frame": pd.DataFrame(
                [
                    {"metric": "total_return", "value": 0.25},
                    {"metric": "max_drawdown", "value": -0.05},
                    {"metric": "average_turnover", "value": 0.10},
                ]
            ),
            "equity_frame": pd.DataFrame(
                [
                    {"date": "2025-01-31", "equity": 1.05},
                    {"date": "2025-02-28", "equity": 1.25},
                ]
            ),
            "holdings_frame": pd.DataFrame(),
            "trades_frame": pd.DataFrame(),
        },
    )

    result = run_mid_trend_strategy_validation(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
    )

    assert result["winner"]["strategy_id"] == "winner"
    assert Path(result["paths"]["scorecard"]).exists()
    assert result["effective_end_date"] == "2025-01-31"


def test_execute_mid_trend_candidate_forwards_current_strategy_config_and_repo_root_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return {
            "summary": pd.DataFrame(),
            "equity": pd.DataFrame(),
            "holdings": pd.DataFrame(),
            "trades": pd.DataFrame(),
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "stock_research.current_mid_trend_strategy_v1.run_current_mid_trend_strategy_v1_backtest",
        fake_runner,
    )

    execute_mid_trend_candidate(
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "module_name": "stock_research.current_mid_trend_strategy_v1",
            "runner_name": "run_current_mid_trend_strategy_v1_backtest",
        },
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir="validation",
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["start_date"] == "2025-01-01"
    assert call["end_date"] == "2025-01-31"
    assert call["top_n"] == 5
    assert call["adjust_type"] == "hfq"
    assert Path(call["regime_path"]).is_absolute()
    assert Path(call["funnel_detail_path"]).is_absolute()
    assert Path(call["output_dir"]) == (
        Path(mid_trend_strategy_validation.__file__).resolve().parents[2]
        / "validation/current_mid_trend_strategy_v1"
    )
    assert Path(call["regime_path"]) == mid_trend_strategy_validation.resolve_default_current_regime_path()


def test_execute_mid_trend_candidate_uses_explicit_module_name(monkeypatch) -> None:
    calls: list[str] = []

    class FakeModule:
        @staticmethod
        def run_current_mid_trend_strategy_v1_backtest(**kwargs):
            return {
                "summary": pd.DataFrame(),
                "equity": pd.DataFrame(),
                "holdings": pd.DataFrame(),
                "trades": pd.DataFrame(),
            }

    monkeypatch.setattr(
        mid_trend_strategy_validation,
        "import_module",
        lambda module_name: calls.append(module_name) or FakeModule,
    )

    execute_mid_trend_candidate(
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "module_name": "stock_research.explicit_module",
            "runner_name": "run_current_mid_trend_strategy_v1_backtest",
        },
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir="validation",
    )

    assert calls == ["stock_research.explicit_module"]


def test_run_mid_trend_strategy_validation_handles_empty_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.discover_mid_trend_strategy_candidates",
        lambda: [],
    )

    result = run_mid_trend_strategy_validation(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
    )

    assert result["candidates"] == []
    assert result["winner"] == {}
    assert result["effective_end_date"] is None
    assert Path(result["paths"]["scorecard"]).exists()
    assert "none" in Path(result["paths"]["report"]).read_text(encoding="utf-8")


def test_run_mid_trend_strategy_validation_uses_shared_effective_end_date(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.discover_mid_trend_strategy_candidates",
        lambda: [
            {
                "strategy_id": "current_mid_trend_strategy_v1",
                "module_name": "stock_research.current_mid_trend_strategy_v1",
                "group": "portfolio",
                "runner_name": "run_current_mid_trend_strategy_v1_backtest",
                "result_keys": {"holdings", "trades", "equity", "summary"},
            },
            {
                "strategy_id": "mid_trend_shadow_backtest",
                "module_name": "stock_research.mid_trend_shadow_backtest",
                "group": "portfolio",
                "runner_name": "run_mid_trend_shadow_backtest",
                "result_keys": {"positions", "trades", "equity_curve", "summary"},
            },
        ],
    )
    monkeypatch.setattr(
        mid_trend_strategy_validation,
        "_resolve_validation_effective_end_date",
        lambda **kwargs: "2025-01-15",
    )
    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.execute_mid_trend_candidate",
        lambda candidate, start_date, end_date, output_dir, **kwargs: calls.append(
            {
                "strategy_id": candidate["strategy_id"],
                "start_date": start_date,
                "end_date": end_date,
                "output_dir": output_dir,
            }
        )
        or {
            "strategy_id": candidate["strategy_id"],
            "summary_frame": pd.DataFrame(
                [
                    {"metric": "total_return", "value": 0.25},
                    {"metric": "max_drawdown", "value": -0.05},
                    {"metric": "average_turnover", "value": 0.10},
                ]
            ),
            "equity_frame": pd.DataFrame(
                [
                    {"date": "2025-01-31", "equity": 1.05},
                    {"date": "2025-02-28", "equity": 1.25},
                ]
            ),
        },
    )

    result = run_mid_trend_strategy_validation(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
    )

    assert result["effective_end_date"] == "2025-01-15"
    assert [call["end_date"] for call in calls] == ["2025-01-15", "2025-01-15"]


def test_select_latest_artifact_path_prefers_newest_coverage_end(tmp_path: Path) -> None:
    research_dir = tmp_path / "outputs/research"
    older_dir = research_dir / "market_regime_confirmation_v1_old"
    newer_dir = research_dir / "market_regime_confirmation_v1_new"
    older_dir.mkdir(parents=True)
    newer_dir.mkdir(parents=True)

    pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "value": 1},
            {"trade_date": "2025-01-15", "value": 2},
        ]
    ).to_csv(older_dir / "market_regime_confirmation_daily.csv", index=False)
    pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "value": 1},
            {"trade_date": "2025-02-20", "value": 2},
        ]
    ).to_csv(newer_dir / "market_regime_confirmation_daily.csv", index=False)

    selected = mid_trend_strategy_validation._select_latest_artifact_path(
        "market_regime_confirmation_daily.csv",
        base_dir=research_dir,
    )

    assert selected == newer_dir / "market_regime_confirmation_daily.csv"


def test_cli_dispatches_mid_trend_strategy_validation(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.run_mid_trend_strategy_validation",
        lambda **kwargs: calls.append(kwargs) or {
            "winner": {"strategy_id": "winner"},
            "paths": {
                "scorecard": str(tmp_path / "scorecard.csv"),
                "report": str(tmp_path / "report.md"),
            },
        },
    )

    args = cli.build_parser().parse_args(
        [
            "validate-mid-trend-strategies",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path),
            "--current-regime-path",
            str(tmp_path / "regime.csv"),
            "--funnel-detail-path",
            str(tmp_path / "funnel.csv"),
            "--shadow-top10-path",
            str(tmp_path / "shadow.csv"),
        ]
    )

    assert args.command == "validate-mid-trend-strategies"

    cli.main_for_args(
        [
            "validate-mid-trend-strategies",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path),
            "--current-regime-path",
            str(tmp_path / "regime.csv"),
            "--funnel-detail-path",
            str(tmp_path / "funnel.csv"),
            "--shadow-top10-path",
            str(tmp_path / "shadow.csv"),
        ]
    )
    out = capsys.readouterr().out
    assert calls == [
        {
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "output_dir": str(tmp_path),
            "current_regime_path": str(tmp_path / "regime.csv"),
            "funnel_detail_path": str(tmp_path / "funnel.csv"),
            "shadow_top10_path": str(tmp_path / "shadow.csv"),
        }
    ]
    assert "mid_trend_validation|winner|winner" in out


def _current_regime_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-01",
                "confirmed_regime_state": "weak_repair",
                "target_exposure": 0.2,
                "rebalance_allowed": True,
                "emotion_score": 45,
                "emotion_state": "neutral",
                "risk_state": "medium",
            },
            {
                "trade_date": "2025-01-02",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
                "emotion_score": 70,
                "emotion_state": "hot",
                "risk_state": "low",
            },
            {
                "trade_date": "2025-01-03",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
                "emotion_score": 72,
                "emotion_state": "hot",
                "risk_state": "low",
            },
        ]
    )


def _current_funnel_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _candidate("2025-01-01", "A", 1, 95),
            _candidate("2025-01-01", "B", 2, 94),
            _candidate("2025-01-02", "A", 1, 96),
            _candidate("2025-01-02", "C", 2, 93),
            _candidate("2025-01-03", "C", 1, 96),
            _candidate("2025-01-03", "D", 2, 92),
        ]
    )


def _current_prices_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0},
            {"trade_date": "2025-01-01", "asset_id": "B", "high": 20.5, "low": 19.5, "close": 20.0},
            {"trade_date": "2025-01-01", "asset_id": "C", "high": 30.5, "low": 29.5, "close": 30.0},
            {"trade_date": "2025-01-01", "asset_id": "D", "high": 40.5, "low": 39.5, "close": 40.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 11.5, "low": 10.5, "close": 11.0},
            {"trade_date": "2025-01-02", "asset_id": "B", "high": 19.5, "low": 18.5, "close": 19.0},
            {"trade_date": "2025-01-02", "asset_id": "C", "high": 33.5, "low": 32.5, "close": 33.0},
            {"trade_date": "2025-01-02", "asset_id": "D", "high": 39.5, "low": 38.5, "close": 39.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 12.5, "low": 11.5, "close": 12.0},
            {"trade_date": "2025-01-03", "asset_id": "B", "high": 18.5, "low": 17.5, "close": 18.0},
            {"trade_date": "2025-01-03", "asset_id": "C", "high": 34.5, "low": 33.5, "close": 34.0},
            {"trade_date": "2025-01-03", "asset_id": "D", "high": 42.5, "low": 41.5, "close": 42.0},
        ]
    )


def _current_asset_names_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha"},
            {"asset_id": "B", "stock_name": "Beta"},
            {"asset_id": "C", "stock_name": "Gamma"},
            {"asset_id": "D", "stock_name": "Delta"},
        ]
    )


def _shadow_top10_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "shadow_top10_rank": 1, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-01", "asset_id": "B", "shadow_top10_rank": 2, "mid_trend_funnel_score": 80},
            {"trade_date": "2025-01-02", "asset_id": "B", "shadow_top10_rank": 1, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "C", "shadow_top10_rank": 2, "mid_trend_funnel_score": 80},
        ]
    )


def _shadow_prices_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "close": 10.0},
            {"trade_date": "2025-01-01", "asset_id": "B", "close": 20.0},
            {"trade_date": "2025-01-01", "asset_id": "C", "close": 30.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "close": 11.0},
            {"trade_date": "2025-01-02", "asset_id": "B", "close": 18.0},
            {"trade_date": "2025-01-02", "asset_id": "C", "close": 30.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "close": 11.0},
            {"trade_date": "2025-01-03", "asset_id": "B", "close": 19.8},
            {"trade_date": "2025-01-03", "asset_id": "C", "close": 33.0},
        ]
    )


def _candidate(trade_date: str, asset_id: str, score_rank: int, score: float) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "asset_id": asset_id,
        "score_rank": score_rank,
        "score_total": score,
        "rank": score_rank,
        "mid_trend_funnel_score": score,
        "mid_trend_layer": "stable_trend_watch",
        "industry_name": "Tech",
        "mainline_status": "sustained_mainline",
        "industry_mainline_score_v1": 0.6,
        "ret_20_score": 80,
        "ret_60_score": 80,
        "trend_r2_20_score": 80,
        "max_drawdown_20_score": 80,
        "volatility_20_score": 80,
    }
