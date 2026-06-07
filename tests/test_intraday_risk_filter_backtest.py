import pandas as pd

import stock_research.intraday_risk_filter_backtest as intraday_backtest
from stock_research.intraday_risk_filter_backtest import (
    build_intraday_risk_flags,
    build_score_variants,
    classify_variant_recommendation,
    run_intraday_risk_filter_backtest_from_frames,
    write_intraday_risk_filter_report,
)


def test_build_intraday_risk_flags_uses_cross_sectional_quantiles():
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.01,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.02,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.03,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.04,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "E",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.05,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "E",
                "feature_name": "last_30m_return",
                "feature_value": -0.05,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "feature_name": "last_30m_return",
                "feature_value": 0.03,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "feature_name": "last_30m_return",
                "feature_value": 0.02,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "feature_name": "last_30m_return",
                "feature_value": 0.01,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D",
                "feature_name": "last_30m_return",
                "feature_value": 0.00,
            },
        ]
    )

    flags = build_intraday_risk_flags(features, quantile=0.2)

    row_e = flags.loc[flags["asset_id"].eq("E")].iloc[0]
    assert bool(row_e["high_intraday_volatility"]) is True
    assert bool(row_e["weak_last_30m"]) is True
    assert int(row_e["intraday_risk_flag_count"]) == 2
    assert row_e["intraday_risk_level"] == "high"
    row_a = flags.loc[flags["asset_id"].eq("A")].iloc[0]
    assert row_a["intraday_risk_level"] == "none"


def test_build_intraday_risk_flags_drops_missing_keys_before_normalizing_strings():
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.01,
            },
            {
                "trade_date": None,
                "asset_id": "B",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.99,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": pd.NA,
                "feature_name": "last_30m_return",
                "feature_value": -0.99,
            },
            {
                "trade_date": pd.NaT,
                "asset_id": "C",
                "feature_name": "last_30m_return",
                "feature_value": -0.98,
            },
        ]
    )

    flags = build_intraday_risk_flags(features)

    assert flags["trade_date"].tolist() == ["2026-01-02"]
    assert flags["asset_id"].tolist() == ["A"]
    assert not flags["trade_date"].isin(["None", "nan", "NaT"]).any()
    assert not flags["asset_id"].isin(["None", "nan", "NaT"]).any()


def test_build_intraday_risk_flags_empty_output_preserves_flag_dtypes():
    flags = build_intraday_risk_flags(
        pd.DataFrame(columns=["trade_date", "asset_id", "feature_name", "feature_value"])
    )

    for column in [
        "high_intraday_volatility",
        "high_front_loaded_amount",
        "weak_last_30m",
        "weak_afternoon",
        "weak_close_to_vwap",
    ]:
        assert flags[column].dtype == bool
    assert pd.api.types.is_integer_dtype(flags["intraday_risk_flag_count"])


def test_load_intraday_risk_filter_inputs_uses_literal_price_status_flags(monkeypatch):
    captured = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_connect(service):
        assert service == "test-service"
        return FakeConnection()

    def fake_fetch_all(conn, sql, params):
        captured.append((sql, params))
        return []

    monkeypatch.setattr(intraday_backtest, "connect", fake_connect)
    monkeypatch.setattr(intraday_backtest, "fetch_all", fake_fetch_all)

    intraday_backtest.load_intraday_risk_filter_inputs(
        "2026-01-02",
        "2026-01-05",
        service="test-service",
    )

    price_sql = captured[1][0]
    assert "false AS is_limit_up" in price_sql
    assert "false AS is_limit_down" in price_sql
    assert "false AS is_suspended" in price_sql
    assert "trade_status, is_limit_up" not in price_sql


def _score_rows():
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "rank": 1, "score_total": 100.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "rank": 2, "score_total": 95.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "rank": 3, "score_total": 90.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "rank": 4, "score_total": 85.0},
        ]
    )


def test_build_score_variants_excludes_high_risk_assets():
    flags = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "intraday_risk_level": "high",
                "intraday_risk_flag_count": 2,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "intraday_risk_level": "none",
                "intraday_risk_flag_count": 0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "intraday_risk_level": "none",
                "intraday_risk_flag_count": 0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D",
                "intraday_risk_level": "none",
                "intraday_risk_flag_count": 0,
            },
        ]
    )

    variants = build_score_variants(_score_rows(), flags)
    exclude = variants["exclude_high_risk"]

    assert exclude["asset_id"].tolist() == ["B", "C", "D"]
    assert exclude["rank"].tolist() == [1, 2, 3]
    assert exclude["score_total"].tolist() == [95.0, 90.0, 85.0]


def test_build_score_variants_penalizes_and_reranks_risk_assets():
    flags = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "intraday_risk_level": "high",
                "intraday_risk_flag_count": 2,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "intraday_risk_level": "watch",
                "intraday_risk_flag_count": 1,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "intraday_risk_level": "none",
                "intraday_risk_flag_count": 0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "D",
                "intraday_risk_level": "none",
                "intraday_risk_flag_count": 0,
            },
        ]
    )

    variants = build_score_variants(_score_rows(), flags, watch_penalty=5.0, high_penalty=15.0)
    penalty = variants["penalty_high_risk"]

    assert penalty["asset_id"].tolist() == ["B", "C", "A", "D"]
    assert penalty["score_total"].tolist() == [90.0, 90.0, 85.0, 85.0]
    assert penalty["rank"].tolist() == [1, 2, 3, 4]


def test_build_score_variants_drops_missing_score_and_flag_keys_before_merge():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "rank": 1, "score_total": 100.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "rank": 2, "score_total": 95.0},
            {"trade_date": None, "asset_id": "B", "rank": 3, "score_total": 90.0},
            {"trade_date": "2026-01-02", "asset_id": float("nan"), "rank": 4, "score_total": 85.0},
        ]
    )
    flags = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "intraday_risk_level": "none",
                "intraday_risk_flag_count": 0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": float("nan"),
                "intraday_risk_level": "high",
                "intraday_risk_flag_count": 2,
            },
            {
                "trade_date": None,
                "asset_id": "nan",
                "intraday_risk_level": "high",
                "intraday_risk_flag_count": 2,
            },
        ]
    )

    variants = build_score_variants(scores, flags)

    assert variants["baseline_topn"]["asset_id"].tolist() == ["A", "B"]
    assert variants["exclude_high_risk"]["asset_id"].tolist() == ["A", "B"]
    assert variants["penalty_high_risk"]["asset_id"].tolist() == ["A", "B"]


def test_classify_variant_recommendation_promotes_when_drawdown_improves_without_large_return_drag():
    recommendation = classify_variant_recommendation(
        baseline_total_return=0.10,
        variant_total_return=0.08,
        baseline_max_drawdown=-0.12,
        variant_max_drawdown=-0.10,
    )

    assert recommendation == "promote_for_shadow_review"


def test_classify_variant_recommendation_watches_when_return_drag_is_too_large():
    recommendation = classify_variant_recommendation(
        baseline_total_return=0.10,
        variant_total_return=0.075,
        baseline_max_drawdown=-0.12,
        variant_max_drawdown=-0.10,
    )

    assert recommendation == "watch_only"


def test_classify_variant_recommendation_rejects_when_drawdown_does_not_improve():
    recommendation = classify_variant_recommendation(
        baseline_total_return=0.10,
        variant_total_return=0.12,
        baseline_max_drawdown=-0.12,
        variant_max_drawdown=-0.13,
    )

    assert recommendation == "reject"


def test_classify_variant_recommendation_rejects_when_drawdown_improves_less_than_one_point():
    recommendation = classify_variant_recommendation(
        baseline_total_return=0.10,
        variant_total_return=0.10,
        baseline_max_drawdown=-0.12,
        variant_max_drawdown=-0.115,
    )

    assert recommendation == "reject"


class _FakeBacktestResult:
    def __init__(self, config, total_return, max_drawdown):
        self.config = config
        self.summary = {
            "final_equity": 1.0 + total_return,
            "total_return": total_return,
            "annualized_return": total_return * 2,
            "annualized_volatility": 0.20,
            "sharpe_ratio": total_return / 0.20,
            "max_drawdown": max_drawdown,
            "average_turnover": 0.30,
            "total_transaction_cost": 0.01,
        }
        self.equity_curve = pd.DataFrame(
            [
                {
                    "date": "2026-01-03",
                    "equity": 1.0 + total_return,
                    "holdings_count": config.top_n,
                }
            ]
        )
        self.positions = pd.DataFrame(
            [
                {
                    "rebalance_date": "2026-01-02",
                    "asset_id": f"A{config.top_n}",
                    "rank": 1,
                    "score_total": 100.0,
                    "weight": 1.0,
                }
            ]
        )
        self.trades = pd.DataFrame(
            [
                {
                    "rebalance_date": "2026-01-02",
                    "asset_id": f"A{config.top_n}",
                    "side": "buy",
                    "transaction_cost": 0.01,
                }
            ]
        )


def test_runner_calls_all_variants_for_each_top_n_and_summarizes_recommendations(monkeypatch):
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "rank": 1, "score_total": 100.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "rank": 2, "score_total": 95.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "rank": 3, "score_total": 90.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "close": 10.0},
            {"trade_date": "2026-01-03", "asset_id": "A", "close": 11.0},
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.05,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "feature_name": "last_30m_return",
                "feature_value": -0.05,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "feature_name": "intraday_volatility_5min",
                "feature_value": 0.01,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "feature_name": "last_30m_return",
                "feature_value": 0.01,
            },
        ]
    )
    metrics_by_variant_call = [
        (0.10, -0.12),
        (0.09, -0.10),
        (0.07, -0.11),
    ]
    calls = []

    def fake_run_vectorized_topn_backtest(scores_variant, prices_arg, config):
        calls.append((config.top_n, len(scores_variant), config.rebalance_frequency))
        total_return, max_drawdown = metrics_by_variant_call[(len(calls) - 1) % 3]
        return _FakeBacktestResult(config, total_return, max_drawdown)

    monkeypatch.setattr(
        intraday_backtest,
        "run_vectorized_topn_backtest",
        fake_run_vectorized_topn_backtest,
    )

    result = run_intraday_risk_filter_backtest_from_frames(
        scores=scores,
        prices=prices,
        features=features,
        start_date="2026-01-02",
        end_date="2026-01-03",
        top_n_values=[1, 2],
        rebalance_frequency="weekly",
        transaction_cost_bps=20.0,
    )

    assert calls == [
        (1, 3, "weekly"),
        (1, 2, "weekly"),
        (1, 3, "weekly"),
        (2, 3, "weekly"),
        (2, 2, "weekly"),
        (2, 3, "weekly"),
    ]
    summary = result["summary"].sort_values(["top_n", "variant_name"]).reset_index(drop=True)
    assert set(summary["variant_name"]) == {
        "baseline_topn",
        "exclude_high_risk",
        "penalty_high_risk",
    }
    assert summary.loc[
        summary["variant_name"].eq("exclude_high_risk"),
        "recommendation",
    ].tolist() == ["promote_for_shadow_review", "promote_for_shadow_review"]
    assert summary.loc[
        summary["variant_name"].eq("penalty_high_risk"),
        "recommendation",
    ].tolist() == ["watch_only", "watch_only"]
    risk_flagged_counts = summary.pivot(
        index="top_n",
        columns="variant_name",
        values="risk_flagged_candidate_count",
    )
    assert risk_flagged_counts["exclude_high_risk"].tolist() == risk_flagged_counts[
        "baseline_topn"
    ].tolist()
    assert risk_flagged_counts["baseline_topn"].tolist() == [1, 1]
    assert {"top_n", "variant_name"} <= set(result["positions"].columns)
    assert {"top_n", "variant_name"} <= set(result["trades"].columns)


def test_runner_writes_artifacts_when_scores_prices_and_features_are_empty_frames(tmp_path):
    result = run_intraday_risk_filter_backtest_from_frames(
        scores=pd.DataFrame(),
        prices=pd.DataFrame(),
        features=pd.DataFrame(),
        start_date="2026-01-02",
        end_date="2026-01-03",
        top_n_values=[1],
        output_dir=tmp_path,
    )

    summary = result["summary"]

    assert {
        "baseline_topn",
        "exclude_high_risk",
        "penalty_high_risk",
    } <= set(summary["variant_name"])
    assert (tmp_path / "intraday_risk_filter_variant_summary.csv").exists()
    assert (tmp_path / "intraday_risk_filter_report.md").exists()


def test_runner_writes_artifacts_when_scores_are_empty_with_expected_columns(tmp_path):
    result = run_intraday_risk_filter_backtest_from_frames(
        scores=pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"]),
        prices=pd.DataFrame(),
        features=pd.DataFrame(),
        start_date="2026-01-02",
        end_date="2026-01-03",
        top_n_values=[1],
        output_dir=tmp_path,
    )

    summary = result["summary"]

    assert {
        "baseline_topn",
        "exclude_high_risk",
        "penalty_high_risk",
    } <= set(summary["variant_name"])
    assert (tmp_path / "intraday_risk_filter_variant_summary.csv").exists()
    assert (tmp_path / "intraday_risk_filter_report.md").exists()


def test_write_intraday_risk_filter_report_writes_expected_artifacts(tmp_path):
    result = {
        "summary": pd.DataFrame(
            [
                {
                    "top_n": 1,
                    "variant_name": "baseline_topn",
                    "final_equity": 1.10,
                    "total_return": 0.10,
                    "annualized_return": 0.20,
                    "annualized_volatility": 0.15,
                    "sharpe_ratio": 1.30,
                    "max_drawdown": -0.12,
                    "average_turnover": 0.30,
                    "total_transaction_cost": 0.01,
                    "average_holdings_count": 1.0,
                    "minimum_holdings_count": 1,
                    "risk_flagged_candidate_count": 1,
                    "excluded_high_risk_count": 0,
                    "penalized_candidate_count": 0,
                    "total_return_delta_vs_baseline": 0.0,
                    "max_drawdown_delta_vs_baseline": 0.0,
                    "recommendation": "baseline",
                }
            ]
        ),
        "flags": pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-02",
                    "asset_id": "A",
                    "intraday_risk_level": "high",
                    "intraday_risk_flag_count": 2,
                }
            ]
        ),
        "positions": pd.DataFrame(
            [{"top_n": 1, "variant_name": "baseline_topn", "asset_id": "A"}]
        ),
        "trades": pd.DataFrame(
            [{"top_n": 1, "variant_name": "baseline_topn", "asset_id": "A"}]
        ),
    }

    paths = write_intraday_risk_filter_report(result, tmp_path)

    expected_names = {
        "intraday_risk_filter_variant_summary.csv",
        "intraday_risk_filter_daily_flags.csv",
        "intraday_risk_filter_variant_positions.csv",
        "intraday_risk_filter_variant_trades.csv",
        "intraday_risk_filter_report.md",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected_names
    assert set(paths) == {
        "summary",
        "flags",
        "positions",
        "trades",
        "report",
    }
    assert (tmp_path / "intraday_risk_filter_report.md").read_text().startswith(
        "# Intraday Risk Filter Backtest"
    )
