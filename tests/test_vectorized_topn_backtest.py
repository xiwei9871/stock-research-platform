import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.backtest_constraints import BacktestExecutionConstraints
from stock_research.services.universe_service import (
    UniverseConfig,
    UniverseMember,
    UniverseResult,
)
import stock_research.vectorized_topn_backtest as vectorized_topn_backtest
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    load_vectorized_topn_inputs,
    run_vectorized_topn_backtest,
    write_vectorized_topn_run_card,
)


def _scores(rows: list[tuple[str, str, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "rank": rank,
                "score_total": score,
            }
            for trade_date, asset_id, rank, score in rows
        ]
    )


def _prices(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": trade_date, "asset_id": asset_id, "close": close}
            for trade_date, asset_id, close in rows
        ]
    )


def _universe_result(
    included: list[tuple[str, str]],
    excluded: list[tuple[str, str]] | None = None,
) -> UniverseResult:
    config = UniverseConfig(as_of_date="2026-01-01")
    members: list[UniverseMember] = []
    for asset_id, stock_code in included:
        members.append(
            UniverseMember(
                trade_date="2026-01-01",
                asset_id=asset_id,
                stock_code=stock_code,
                stock_name=stock_code,
                board="main",
                listed_days=1000,
                is_st=False,
                is_suspended=False,
                avg_turnover_amount=100_000_000.0,
                avg_volume=10_000_000.0,
                industry="Bank",
                included=True,
                include_reasons=["board_allowed:main"],
                exclude_reasons=[],
            )
        )
    for asset_id, stock_code in excluded or []:
        members.append(
            UniverseMember(
                trade_date="2026-01-01",
                asset_id=asset_id,
                stock_code=stock_code,
                stock_name=stock_code,
                board="main",
                listed_days=1000,
                is_st=False,
                is_suspended=False,
                avg_turnover_amount=100_000_000.0,
                avg_volume=10_000_000.0,
                industry="Bank",
                included=False,
                include_reasons=[],
                exclude_reasons=["manual_exclude"],
            )
        )
    return UniverseResult(
        config=config,
        as_of_date="2026-01-01",
        total_candidates=len(members),
        included_count=sum(1 for member in members if member.included),
        excluded_count=sum(1 for member in members if not member.included),
        members=members,
        included_codes=[member.stock_code for member in members if member.included],
        excluded_codes=[member.stock_code for member in members if not member.included],
        summary_by_reason={"include": {"board_allowed:main": len(included)}, "exclude": {}},
        warnings=[],
    )


def test_run_vectorized_topn_backtest_daily_rebalances_topn_with_costs():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
            ("2026-01-01", "C", 3, 70.0),
            ("2026-01-02", "B", 1, 95.0),
            ("2026-01-02", "C", 2, 85.0),
            ("2026-01-02", "A", 3, 75.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-01", "A", 10.0),
            ("2026-01-01", "B", 20.0),
            ("2026-01-01", "C", 30.0),
            ("2026-01-02", "A", 11.0),
            ("2026-01-02", "B", 18.0),
            ("2026-01-02", "C", 30.0),
            ("2026-01-03", "A", 11.0),
            ("2026-01-03", "B", 19.8),
            ("2026-01-03", "C", 30.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=2,
        rebalance_frequency="daily",
        transaction_cost_bps=10.0,
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.equity_curve["date"]) == ["2026-01-03"]
    assert list(result.equity_curve["turnover"]) == pytest.approx([1.0])
    assert list(result.equity_curve["gross_return"]) == pytest.approx([0.05])
    assert list(result.equity_curve["transaction_cost"]) == pytest.approx([0.001])
    assert list(result.equity_curve["net_return"]) == pytest.approx([0.049])
    assert result.equity_curve.iloc[-1]["equity"] == pytest.approx(1.049)

    positions = result.positions.sort_values(["rebalance_date", "asset_id"])
    assert list(positions["rebalance_date"]) == [
        "2026-01-01",
        "2026-01-01",
        "2026-01-02",
        "2026-01-02",
    ]
    assert list(positions["asset_id"]) == ["A", "B", "B", "C"]
    assert list(positions["weight"]) == pytest.approx([0.5, 0.5, 0.5, 0.5])
    assert result.summary["total_return"] == pytest.approx(0.049)


def test_run_vectorized_topn_backtest_skips_limit_up_buy_and_keeps_cash():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "open": 11.0,
                "close": 11.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": True,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "A",
                "open": 11.0,
                "close": 11.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "B",
                "open": 21.0,
                "close": 21.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=2,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.trades["skip_reason"].dropna()) == ["limit_up"]
    assert result.equity_curve.iloc[0]["holdings_count"] == 1


def test_run_vectorized_topn_backtest_applies_full_one_way_costs():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-02", "B", 1, 95.0),
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "open": 11.0,
                "close": 11.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "A",
                "open": 11.0,
                "close": 11.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "B",
                "open": 21.0,
                "close": 21.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=1,
        execution_constraints=BacktestExecutionConstraints(
            commission_bps=5.0,
            stamp_duty_bps=10.0,
            slippage_bps=5.0,
        ),
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert result.trades["transaction_cost"].sum() > 0
    assert result.equity_curve["transaction_cost"].sum() > 0


def test_run_vectorized_topn_backtest_retries_blocked_sell_until_later_executable_date():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 99.0),
            ("2026-01-01", "B", 2, 98.0),
            ("2026-01-02", "B", 1, 97.0),
            ("2026-01-02", "C", 2, 96.0),
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "open": 30.0,
                "close": 30.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": True,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "C",
                "open": 30.0,
                "close": 30.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-04",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-04",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-04",
                "asset_id": "C",
                "open": 30.0,
                "close": 30.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-05",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-05",
                "asset_id": "B",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-05",
                "asset_id": "C",
                "open": 30.0,
                "close": 30.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-05",
        top_n=2,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    a_sells = result.trades[(result.trades["asset_id"] == "A") & (result.trades["side"] == "sell")]
    assert list(a_sells["execution_date"]) == ["2026-01-03", "2026-01-04"]
    assert a_sells.iloc[0]["skip_reason"] == "limit_down"
    assert pd.isna(a_sells.iloc[1]["skip_reason"])
    assert result.equity_curve.iloc[-1]["holdings_count"] == 1


def test_run_vectorized_topn_backtest_weekly_rebalances_first_available_week_date():
    scores = _scores(
        [
            ("2026-01-05", "A", 1, 90.0),
            ("2026-01-05", "B", 2, 80.0),
            ("2026-01-06", "C", 1, 95.0),
            ("2026-01-06", "B", 2, 85.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-05", "A", 10.0),
            ("2026-01-05", "B", 20.0),
            ("2026-01-05", "C", 30.0),
            ("2026-01-06", "A", 11.0),
            ("2026-01-06", "B", 20.0),
            ("2026-01-06", "C", 60.0),
            ("2026-01-07", "A", 12.1),
            ("2026-01-07", "B", 20.0),
            ("2026-01-07", "C", 120.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-05",
        end_date="2026-01-07",
        top_n=1,
        rebalance_frequency="weekly",
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.positions["rebalance_date"]) == ["2026-01-05"]
    assert list(result.positions["asset_id"]) == ["A"]
    assert list(result.equity_curve["date"]) == ["2026-01-07"]
    assert list(result.equity_curve["gross_return"]) == pytest.approx([0.10])
    assert result.equity_curve.iloc[-1]["equity"] == pytest.approx(1.10)


def test_run_vectorized_topn_backtest_caps_holdings_with_max_positions():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
            ("2026-01-01", "C", 3, 70.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-01", "A", 10.0),
            ("2026-01-01", "B", 20.0),
            ("2026-01-01", "C", 30.0),
            ("2026-01-02", "A", 11.0),
            ("2026-01-02", "B", 22.0),
            ("2026-01-02", "C", 33.0),
            ("2026-01-03", "A", 11.0),
            ("2026-01-03", "B", 22.0),
            ("2026-01-03", "C", 33.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=3,
        max_positions=2,
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.positions["asset_id"]) == ["A", "B"]
    assert list(result.positions["weight"]) == pytest.approx([0.5, 0.5])
    assert result.equity_curve.iloc[0]["holdings_count"] == 2


def test_run_vectorized_topn_backtest_outputs_rebalance_trade_details():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
            ("2026-01-02", "B", 1, 95.0),
            ("2026-01-02", "C", 2, 85.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-01", "A", 10.0),
            ("2026-01-01", "B", 20.0),
            ("2026-01-01", "C", 30.0),
            ("2026-01-02", "A", 11.0),
            ("2026-01-02", "B", 18.0),
            ("2026-01-02", "C", 30.0),
            ("2026-01-03", "A", 11.0),
            ("2026-01-03", "B", 19.8),
            ("2026-01-03", "C", 30.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=2,
        transaction_cost_bps=10.0,
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    trades = result.trades.sort_values(["rebalance_date", "asset_id"]).reset_index(drop=True)
    assert list(trades["rebalance_date"]) == [
        "2026-01-01",
        "2026-01-01",
        "2026-01-02",
        "2026-01-02",
    ]
    assert list(trades["asset_id"]) == ["A", "B", "A", "C"]
    assert list(trades["side"]) == ["buy", "buy", "sell", "buy"]
    assert list(trades["previous_weight"]) == pytest.approx([0.0, 0.0, 0.5, 0.0])
    assert list(trades["target_weight"]) == pytest.approx([0.5, 0.5, 0.0, 0.5])
    assert list(trades["delta_weight"]) == pytest.approx([0.5, 0.5, -0.5, 0.5])
    assert list(trades["turnover_contribution"]) == pytest.approx([0.5, 0.5, 0.5, 0.5])
    assert list(trades["transaction_cost"]) == pytest.approx([0.0005, 0.0005, 0.0005, 0.0005])


def test_write_vectorized_topn_run_card_writes_expected_artifacts(tmp_path):
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-01", "A", 10.0),
            ("2026-01-01", "B", 20.0),
            ("2026-01-02", "A", 11.0),
            ("2026-01-02", "B", 21.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-02",
        top_n=2,
    )

    result = run_vectorized_topn_backtest(scores, prices, config)
    paths = write_vectorized_topn_run_card(result, tmp_path)

    run_dir = Path(paths["run_card_dir"])
    assert (run_dir / "run_card.json").exists()
    assert (run_dir / "run_card.md").exists()
    assert (run_dir / "evidence" / "manifest.json").exists()
    assert paths["run_card_json_path"].endswith("run_card.json")
    assert Path(paths["metrics_json_path"]).exists()
    assert Path(paths["config_snapshot_path"]).exists()
    assert Path(paths["warnings_md_path"]).exists()
    assert Path(paths["data_coverage_json_path"]).exists()
    coverage = json.loads(Path(paths["data_coverage_json_path"]).read_text(encoding="utf-8"))
    assert coverage["coverage_ratio"] is None
    assert coverage["missing_dates"] is None
    assert coverage["missing_assets"] is None


def test_run_vectorized_topn_backtest_filters_scores_and_prices_by_universe_result():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 99.0),
            ("2026-01-01", "B", 2, 90.0),
            ("2026-01-01", "C", 3, 80.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-01", "A", 10.0),
            ("2026-01-01", "B", 20.0),
            ("2026-01-01", "C", 30.0),
            ("2026-01-02", "A", 11.0),
            ("2026-01-02", "B", 21.0),
            ("2026-01-02", "C", 31.0),
            ("2026-01-03", "A", 11.0),
            ("2026-01-03", "B", 21.0),
            ("2026-01-03", "C", 31.0),
        ]
    )
    universe_result = _universe_result(
        included=[("B", "B"), ("C", "C")],
        excluded=[("A", "A")],
    )

    result = run_vectorized_topn_backtest(
        scores,
        prices,
        VectorizedTopNConfig(start_date="2026-01-01", end_date="2026-01-03", top_n=2),
        universe_result=universe_result,
    )

    assert list(result.positions["asset_id"]) == ["B", "C"]
    assert result.equity_curve.iloc[0]["holdings_count"] == 2


def test_load_vectorized_topn_inputs_filters_loaded_rows_by_universe_result(monkeypatch):
    calls = []
    universe_result = _universe_result(
        included=[("CN:SH:600002", "600002.SH")],
        excluded=[("CN:SH:600001", "600001.SH")],
    )

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "factor.stock_score_daily" in sql:
            return [
                {
                    "trade_date": "2026-01-01",
                    "asset_id": "CN:SH:600001",
                    "rank": 1,
                    "score_total": 90.0,
                },
                {
                    "trade_date": "2026-01-01",
                    "asset_id": "CN:SH:600002",
                    "rank": 2,
                    "score_total": 80.0,
                },
            ]
        return [
            {
                "trade_date": "2026-01-01",
                "asset_id": "CN:SH:600001",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "CN:SH:600002",
                "open": 20.0,
                "close": 20.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
        ]

    monkeypatch.setattr(
        vectorized_topn_backtest,
        "connect",
        lambda service: _context(object()),
    )
    monkeypatch.setattr(vectorized_topn_backtest, "fetch_all", fake_fetch_all)

    scores, prices = load_vectorized_topn_inputs(
        start_date="2026-01-01",
        end_date="2026-01-31",
        score_version="manual_v1",
        adjust_type="hfq",
        universe_result=universe_result,
    )

    assert scores["asset_id"].tolist() == ["CN:SH:600002"]
    assert prices["asset_id"].tolist() == ["CN:SH:600002"]
    assert {
        "open",
        "close",
        "amount",
        "trade_status",
        "is_limit_up",
        "is_limit_down",
        "is_suspended",
    }.issubset(prices.columns)


def test_load_vectorized_topn_inputs_queries_scores_and_prices(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "factor.stock_score_daily" in sql:
            return [
                {
                    "trade_date": "2026-01-01",
                    "asset_id": "A",
                    "rank": 1,
                    "score_total": 90.0,
                }
            ]
        return [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "open": 10.0,
                "close": 10.0,
                "amount": 100000000.0,
                "trade_status": "1",
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            }
        ]

    monkeypatch.setattr(
        vectorized_topn_backtest,
        "connect",
        lambda service: _context(object()),
    )
    monkeypatch.setattr(vectorized_topn_backtest, "fetch_all", fake_fetch_all)

    scores, prices = load_vectorized_topn_inputs(
        start_date="2026-01-01",
        end_date="2026-01-31",
        score_version="manual_v1",
        adjust_type="hfq",
    )

    assert scores.iloc[0]["score_total"] == 90.0
    assert prices.iloc[0]["close"] == 10.0
    assert "FROM factor.stock_score_daily" in calls[0][0]
    assert calls[0][1] == ["manual_v1", "2026-01-01", "2026-01-31"]
    assert "FROM market_daily_bar" in calls[1][0]
    assert calls[1][1] == ["hfq", "2026-01-01", "2026-01-31"]
    assert "open" in calls[1][0]
    assert "is_limit_up" in calls[1][0]


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
