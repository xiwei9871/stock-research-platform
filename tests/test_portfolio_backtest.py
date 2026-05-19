import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import stock_research.cli as cli
import stock_research.portfolio_backtest as portfolio_backtest
from stock_research.backtest import BacktestSelection, LOW_LIQUIDITY_THRESHOLD
from stock_research.portfolio_backtest import (
    PortfolioConfig,
    PortfolioResult,
    run_portfolio_backtest,
    shares_for_budget,
    simulate_portfolio_config,
    summarize_portfolio_result,
    write_portfolio_report,
)
from stock_research.services.universe_service import (
    UniverseConfig,
    UniverseMember,
    UniverseResult,
)


def _features(selection_date: str, assets: list[tuple[str, float]]) -> pd.DataFrame:
    rows = []
    for asset_id, ret_20d in assets:
        values = {
            "ret_20d": ret_20d,
            "ret_60d": ret_20d / 2,
            "amount_20d_avg": 100000000.0,
            "volatility_20d": 0.02,
            "max_drawdown_20d": -0.03,
        }
        for feature_name, feature_value in values.items():
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": selection_date,
                    "feature_name": feature_name,
                    "feature_value": feature_value,
                }
            )
    return pd.DataFrame(rows)


def _bars(asset_prices: dict[str, dict[str, float]]) -> pd.DataFrame:
    rows = []
    for asset_id, prices_by_date in asset_prices.items():
        for trade_date, open_price in prices_by_date.items():
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "open": open_price,
                    "preclose": open_price,
                    "close": open_price,
                    "amount": 100000000.0,
                    "turnover_rate": 1.0,
                    "trade_status": "1",
                    "is_st": False,
                }
            )
    return pd.DataFrame(rows)


def _universe_result(
    included: list[tuple[str, str]],
    excluded: list[tuple[str, str]] | None = None,
) -> UniverseResult:
    members = [
        UniverseMember(
            trade_date="2026-05-07",
            asset_id=asset_id,
            stock_code=stock_code,
            stock_name=stock_code,
            board="main",
            listed_days=120,
            is_st=False,
            is_suspended=False,
            avg_turnover_amount=100000000.0,
            avg_volume=1000000.0,
            industry="industry",
            included=True,
            include_reasons=["universe"],
            exclude_reasons=[],
        )
        for asset_id, stock_code in included
    ]
    for asset_id, stock_code in excluded or []:
        members.append(
            UniverseMember(
                trade_date="2026-05-07",
                asset_id=asset_id,
                stock_code=stock_code,
                stock_name=stock_code,
                board="star",
                listed_days=10,
                is_st=True,
                is_suspended=True,
                avg_turnover_amount=1000.0,
                avg_volume=10.0,
                industry="industry",
                included=False,
                include_reasons=[],
                exclude_reasons=["universe_excluded"],
            )
        )
    return UniverseResult(
        config=UniverseConfig(as_of_date="2026-05-07"),
        as_of_date="2026-05-07",
        total_candidates=len(members),
        included_count=len(included),
        excluded_count=len(excluded or []),
        members=members,
        included_codes=[stock_code for _, stock_code in included],
        excluded_codes=[stock_code for _, stock_code in excluded or []],
        summary_by_reason={"include": {"universe": len(included)}, "exclude": {"universe_excluded": len(excluded or [])}},
        warnings=[],
    )


def test_shares_for_budget_rounds_down_to_integer_lots():
    assert shares_for_budget(100000, 37.0, lot_size=100) == 2700


def test_shares_for_budget_returns_zero_when_one_lot_is_unaffordable():
    assert shares_for_budget(5000, 83.0, lot_size=100) == 0


def test_simulate_portfolio_config_buys_affordable_lots_sells_after_holding_period_and_tracks_equity():
    feature_frame = _features(
        "2026-05-07",
        [
            ("CN:SH:600001", 0.30),
            ("CN:SH:600002", 0.20),
        ],
    )
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-07": 10.0,
                "2026-05-08": 10.0,
                "2026-05-11": 10.5,
                "2026-05-12": 11.0,
            },
            "CN:SH:600002": {
                "2026-05-07": 20.0,
                "2026-05-08": 20.0,
                "2026-05-11": 19.0,
                "2026-05-12": 18.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date="2026-05-07",
        end_date="2026-05-12",
        initial_cash=100000.0,
        top_k=2,
        holding_days=2,
        strategy_id="unit",
    )

    result = simulate_portfolio_config(feature_frame, bar_frame, config)

    assert isinstance(result.equity_curve, pd.DataFrame)
    assert list(result.equity_curve["date"]) == [
        "2026-05-07",
        "2026-05-08",
        "2026-05-11",
        "2026-05-12",
    ]
    final_equity = result.equity_curve.iloc[-1]
    assert final_equity["cash"] == pytest.approx(100100.0)
    assert final_equity["market_value"] == pytest.approx(0.0)
    assert final_equity["equity"] == pytest.approx(100100.0)
    assert final_equity["drawdown"] == pytest.approx(0.0)
    assert final_equity["open_positions"] == 0

    closed = result.trades[result.trades["status"] == "closed"].sort_values("asset_id")
    assert list(closed["asset_id"]) == ["CN:SH:600001", "CN:SH:600002"]
    assert list(closed["buy_date"]) == ["2026-05-08", "2026-05-08"]
    assert list(closed["sell_date"]) == ["2026-05-12", "2026-05-12"]
    assert list(closed["shares"]) == [2500, 1200]
    assert list(closed["buy_value"]) == [25000.0, 24000.0]
    assert list(closed["sell_value"]) == [27500.0, 21600.0]


def test_simulate_portfolio_config_continues_after_end_date_to_settle_existing_positions_only():
    feature_frame = pd.concat(
        [
            _features("2026-05-07", [("CN:SH:600001", 0.30)]),
            _features("2026-05-11", [("CN:SH:600002", 0.40)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-07": 10.0,
                "2026-05-08": 10.0,
                "2026-05-11": 12.0,
                "2026-05-12": 12.0,
            },
            "CN:SH:600002": {
                "2026-05-11": 20.0,
                "2026-05-12": 20.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date="2026-05-07",
        end_date="2026-05-08",
        initial_cash=1000.0,
        top_k=1,
        holding_days=1,
        strategy_id="unit",
    )

    result = simulate_portfolio_config(feature_frame, bar_frame, config)

    assert list(result.equity_curve["date"]) == [
        "2026-05-07",
        "2026-05-08",
        "2026-05-11",
    ]
    assert result.equity_curve.iloc[-1]["cash"] == pytest.approx(1200.0)
    assert result.equity_curve.iloc[-1]["market_value"] == pytest.approx(0.0)
    assert result.equity_curve.iloc[-1]["equity"] == pytest.approx(1200.0)

    assert result.trades.shape[0] == 1
    trade = result.trades.iloc[0]
    assert trade["asset_id"] == "CN:SH:600001"
    assert trade["buy_date"] == "2026-05-08"
    assert trade["sell_date"] == "2026-05-11"
    assert trade["sell_open"] == pytest.approx(12.0)
    assert trade["sell_value"] == pytest.approx(1200.0)
    assert trade["return_value"] == pytest.approx(0.2)
    assert trade["status"] == "closed"


def test_simulate_portfolio_config_does_not_open_positions_after_end_date():
    feature_frame = _features("2026-05-08", [("CN:SH:600001", 0.30)])
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-08": 10.0,
                "2026-05-11": 10.0,
                "2026-05-12": 12.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date="2026-05-08",
        end_date="2026-05-08",
        initial_cash=1000.0,
        top_k=1,
        holding_days=1,
        strategy_id="unit",
    )

    result = simulate_portfolio_config(feature_frame, bar_frame, config)

    assert list(result.equity_curve["date"]) == ["2026-05-08"]
    assert result.equity_curve.iloc[-1]["cash"] == pytest.approx(1000.0)
    assert result.equity_curve.iloc[-1]["open_positions"] == 0
    assert result.trades.empty


def test_simulate_portfolio_config_records_insufficient_lot_cash_when_budget_cannot_buy_one_lot():
    feature_frame = _features("2026-05-07", [("CN:SH:600001", 0.30)])
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-07": 83.0,
                "2026-05-08": 83.0,
                "2026-05-11": 84.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date="2026-05-07",
        end_date="2026-05-11",
        initial_cash=5000.0,
        top_k=1,
        holding_days=1,
        strategy_id="unit",
    )

    result = simulate_portfolio_config(feature_frame, bar_frame, config)

    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["status"] == "skipped"
    assert trade["skip_reason"] == "insufficient_lot_cash"
    assert trade["shares"] == 0
    assert result.equity_curve.iloc[-1]["equity"] == pytest.approx(5000.0)


def test_simulate_portfolio_config_reuses_same_day_sell_proceeds_for_rolling_daily_buys():
    feature_frame = pd.concat(
        [
            _features("2026-05-07", [("CN:SH:600001", 0.30)]),
            _features("2026-05-08", [("CN:SH:600002", 0.30)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-07": 10.0,
                "2026-05-08": 10.0,
                "2026-05-11": 10.0,
            },
            "CN:SH:600002": {
                "2026-05-08": 10.0,
                "2026-05-11": 10.0,
                "2026-05-12": 10.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date="2026-05-07",
        end_date="2026-05-12",
        initial_cash=1000.0,
        top_k=1,
        holding_days=1,
        lot_size=100,
        strategy_id="unit",
    )

    result = simulate_portfolio_config(feature_frame, bar_frame, config)

    bought = result.trades[result.trades["status"] == "closed"].sort_values("buy_date")
    assert list(bought["asset_id"]) == ["CN:SH:600001", "CN:SH:600002"]
    assert list(bought["buy_date"]) == ["2026-05-08", "2026-05-11"]
    assert list(bought["shares"]) == [100, 100]
    assert not (result.trades["skip_reason"] == "insufficient_lot_cash").any()


def test_simulate_portfolio_config_accepts_timestamp_and_date_bounds():
    feature_frame = _features("2026-05-07", [("CN:SH:600001", 0.30)])
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-07": 10.0,
                "2026-05-08": 10.0,
                "2026-05-11": 10.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date=pd.Timestamp("2026-05-07"),
        end_date=date(2026, 5, 11),
        initial_cash=1000.0,
        top_k=1,
        holding_days=1,
        strategy_id="unit",
    )

    result = simulate_portfolio_config(feature_frame, bar_frame, config)

    assert list(result.equity_curve["date"]) == [
        "2026-05-07",
        "2026-05-08",
        "2026-05-11",
    ]


def test_simulate_portfolio_config_carries_last_mark_when_current_open_is_missing():
    feature_frame = _features("2026-05-07", [("CN:SH:600001", 0.30)])
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-07": 10.0,
                "2026-05-08": 10.0,
                "2026-05-11": 12.0,
                "2026-05-12": None,
                "2026-05-13": 12.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date="2026-05-07",
        end_date="2026-05-13",
        initial_cash=3000.0,
        top_k=1,
        holding_days=3,
        strategy_id="unit",
    )

    result = simulate_portfolio_config(feature_frame, bar_frame, config)

    missing_open_day = result.equity_curve[
        result.equity_curve["date"] == "2026-05-12"
    ].iloc[0]
    assert missing_open_day["market_value"] == pytest.approx(1200.0)
    assert missing_open_day["equity"] == pytest.approx(3200.0)


def test_simulate_portfolio_config_filters_inputs_by_universe_result_before_selection(
    monkeypatch,
):
    feature_frame = pd.concat(
        [
            _features("2026-05-07", [("CN:SH:600001", 0.90)]),
            _features("2026-05-07", [("CN:SH:600002", 0.10)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-05-07": 10.0,
                "2026-05-08": 10.0,
            },
            "CN:SH:600002": {
                "2026-05-07": 11.0,
                "2026-05-08": 11.0,
            },
        }
    )
    config = PortfolioConfig(
        start_date="2026-05-07",
        end_date="2026-05-08",
        initial_cash=10000.0,
        top_k=1,
        holding_days=1,
        strategy_id="unit",
    )
    universe_result = _universe_result(
        included=[("CN:SH:600002", "600002")],
        excluded=[("CN:SH:600001", "600001")],
    )
    select_calls = []

    def fake_select_top_for_date(
        features,
        bars,
        selection_date,
        top_n=20,
        liquidity_threshold=LOW_LIQUIDITY_THRESHOLD,
    ):
        select_calls.append((features.copy(), bars.copy(), selection_date, top_n))
        return [
            BacktestSelection(
                selection_date=str(selection_date),
                asset_id="CN:SH:600002",
                rank=1,
                score=0.9,
                ret_20d=0.10,
                amount_20d_avg=100000000.0,
            )
        ]

    monkeypatch.setattr(portfolio_backtest, "select_top_for_date", fake_select_top_for_date)

    result = simulate_portfolio_config(
        feature_frame,
        bar_frame,
        config,
        universe_result=universe_result,
    )

    assert select_calls
    first_features, first_bars, _, _ = select_calls[0]
    assert sorted(first_features["asset_id"].unique()) == ["CN:SH:600002"]
    assert sorted(first_bars["asset_id"].unique()) == ["CN:SH:600002"]
    assert set(result.trades["asset_id"]) == {"CN:SH:600002"}


def test_run_portfolio_backtest_passes_universe_result_to_simulation(
    monkeypatch, tmp_path
):
    feature_frame = pd.DataFrame({"feature": [1]})
    bar_frame = pd.DataFrame({"bar": [1]})
    universe_result = _universe_result(included=[("A", "A")], excluded=[("B", "B")])
    calls = []

    def fake_load(start_date, end_date, future_buffer_days=30):
        return feature_frame, bar_frame

    def fake_simulate(features, bars, config, universe_result=None):
        calls.append(universe_result)
        return PortfolioResult(
            config=config,
            equity_curve=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "date": config.end_date,
                        "cash": config.initial_cash,
                        "market_value": 0.0,
                        "equity": config.initial_cash,
                        "drawdown": 0.0,
                        "open_positions": 0,
                    }
                ]
            ),
            trades=pd.DataFrame(columns=["status", "return_value", "skip_reason"]),
        )

    monkeypatch.setattr(portfolio_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(portfolio_backtest, "simulate_portfolio_config", fake_simulate)

    run_portfolio_backtest(
        "2026-04-01",
        "2026-05-07",
        initial_cash=123000.0,
        reports_dir=tmp_path,
        universe_result=universe_result,
    )

    assert calls
    assert all(call is universe_result for call in calls)


def test_run_portfolio_backtest_runs_all_top_k_and_holding_day_combinations(
    monkeypatch, tmp_path
):
    feature_frame = pd.DataFrame({"feature": [1]})
    bar_frame = pd.DataFrame({"bar": [1]})
    calls = []

    def fake_load(start_date, end_date, future_buffer_days=30):
        calls.append(("load", start_date, end_date, future_buffer_days))
        return feature_frame, bar_frame

    def fake_simulate(features, bars, config):
        calls.append(("simulate", features, bars, config))
        equity_curve = pd.DataFrame(
            [
                {
                    "strategy_id": config.strategy_id,
                    "date": config.end_date,
                    "cash": config.initial_cash + config.top_k + config.holding_days,
                    "market_value": 0.0,
                    "equity": config.initial_cash + config.top_k + config.holding_days,
                    "drawdown": 0.0,
                    "open_positions": 0,
                }
            ]
        )
        trades = pd.DataFrame(
            [
                {
                    "strategy_id": config.strategy_id,
                    "top_k": config.top_k,
                    "holding_days": config.holding_days,
                    "status": "closed",
                    "return_value": 0.01,
                    "skip_reason": None,
                }
            ]
        )
        return PortfolioResult(config=config, equity_curve=equity_curve, trades=trades)

    monkeypatch.setattr(portfolio_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(portfolio_backtest, "simulate_portfolio_config", fake_simulate)

    output = run_portfolio_backtest(
        "2026-04-01",
        "2026-05-07",
        initial_cash=123000.0,
        top_ks=(2, 3),
        holding_days=(4, 6),
        reports_dir=tmp_path,
    )

    assert calls[0] == ("load", "2026-04-01", "2026-05-07", 30)
    simulate_calls = [call for call in calls if call[0] == "simulate"]
    assert len(simulate_calls) == 4
    configs = [call[3] for call in simulate_calls]
    assert [(config.top_k, config.holding_days) for config in configs] == [
        (2, 4),
        (2, 6),
        (3, 4),
        (3, 6),
    ]
    assert len({id(config) for config in configs}) == 4
    for config in configs:
        assert config.start_date == "2026-04-01"
        assert config.end_date == "2026-05-07"
        assert config.initial_cash == 123000.0
        assert "2026-04-01" in config.strategy_id
        assert "2026-05-07" in config.strategy_id
        assert f"top{config.top_k}" in config.strategy_id
        assert f"h{config.holding_days}" in config.strategy_id
        assert "cash123000" in config.strategy_id

    assert set(output) >= {
        "results",
        "equity_curve",
        "trades",
        "summary",
        "report_path",
        "report_paths",
    }
    assert len(output["results"]) == 4
    assert output["equity_curve"].shape[0] == 4
    assert output["trades"].shape[0] == 4
    assert output["summary"].shape[0] == 4
    assert Path(output["report_path"]).exists()
    assert Path(output["run_card"]["run_card_json_path"]).exists()
    assert Path(output["run_card"]["run_card_md_path"]).exists()
    assert Path(output["run_card"]["metrics_json_path"]).exists()
    assert Path(output["run_card"]["config_snapshot_path"]).exists()
    assert Path(output["run_card"]["warnings_md_path"]).exists()
    assert Path(output["run_card"]["data_coverage_json_path"]).exists()
    coverage = json.loads(Path(output["run_card"]["data_coverage_json_path"]).read_text(encoding="utf-8"))
    assert coverage["coverage_ratio"] is None
    assert coverage["missing_dates"] is None
    assert coverage["missing_assets"] is None


def test_run_portfolio_backtest_uses_default_horizon_future_buffer(monkeypatch, tmp_path):
    calls = []

    def fake_load(start_date, end_date, future_buffer_days=30):
        calls.append(("load", start_date, end_date, future_buffer_days))
        return pd.DataFrame({"feature": [1]}), pd.DataFrame({"bar": [1]})

    monkeypatch.setattr(portfolio_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(
        portfolio_backtest,
        "simulate_portfolio_config",
        lambda features, bars, config: PortfolioResult(
            config=config,
            equity_curve=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "date": config.end_date,
                        "cash": config.initial_cash,
                        "market_value": 0.0,
                        "equity": config.initial_cash,
                        "drawdown": 0.0,
                        "open_positions": 0,
                    }
                ]
            ),
            trades=pd.DataFrame(columns=["status", "return_value", "skip_reason"]),
        ),
    )

    run_portfolio_backtest(
        "2026-04-01",
        "2026-05-07",
        initial_cash=123000.0,
        reports_dir=tmp_path,
    )

    assert calls == [("load", "2026-04-01", "2026-05-07", 90)]


def test_run_portfolio_backtest_creates_unique_run_card_directories(monkeypatch, tmp_path):
    def fake_load(start_date, end_date, future_buffer_days=30):
        return pd.DataFrame({"feature": [1]}), pd.DataFrame({"bar": [1]})

    def fake_simulate(features, bars, config):
        equity_curve = pd.DataFrame(
            [
                {
                    "strategy_id": config.strategy_id,
                    "date": config.end_date,
                    "cash": config.initial_cash,
                    "market_value": 0.0,
                    "equity": config.initial_cash,
                    "drawdown": 0.0,
                    "open_positions": 0,
                }
            ]
        )
        trades = pd.DataFrame(
            [
                {
                    "strategy_id": config.strategy_id,
                    "top_k": config.top_k,
                    "holding_days": config.holding_days,
                    "status": "closed",
                    "return_value": 0.01,
                    "skip_reason": None,
                }
            ]
        )
        return PortfolioResult(config=config, equity_curve=equity_curve, trades=trades)

    monkeypatch.setattr(portfolio_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(portfolio_backtest, "simulate_portfolio_config", fake_simulate)

    first = run_portfolio_backtest(
        "2026-04-01",
        "2026-05-07",
        initial_cash=123000.0,
        top_ks=(2, 3),
        holding_days=(4, 6),
        reports_dir=tmp_path,
    )
    first_path = Path(first["run_card"]["run_card_json_path"])
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))

    second = run_portfolio_backtest(
        "2026-04-01",
        "2026-05-07",
        initial_cash=123000.0,
        top_ks=(2, 3),
        holding_days=(4, 6),
        reports_dir=tmp_path,
    )
    second_path = Path(second["run_card"]["run_card_json_path"])

    assert first["run_card"]["run_card_dir"] != second["run_card"]["run_card_dir"]
    assert first["run_card"]["run_card_json_path"] != second["run_card"]["run_card_json_path"]
    assert first_path.exists()
    assert second_path.exists()
    assert json.loads(first_path.read_text(encoding="utf-8")) == first_payload


def test_run_portfolio_backtest_returns_stable_empty_summary_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(
        portfolio_backtest,
        "load_backtest_inputs",
        lambda start_date, end_date, future_buffer_days=30: (
            pd.DataFrame({"feature": [1]}),
            pd.DataFrame({"bar": [1]}),
        ),
    )

    output = run_portfolio_backtest(
        "2026-04-01",
        "2026-05-07",
        top_ks=(),
        holding_days=(5,),
        reports_dir=tmp_path,
    )

    assert output["results"] == []
    assert output["summary"].empty
    assert list(output["summary"].columns) == [
        "strategy_id",
        "top_k",
        "holding_days",
        "initial_cash",
        "final_equity",
        "total_return",
        "max_drawdown",
        "closed_trades",
        "open_trades",
        "skipped_trades",
        "win_rate",
        "mean_trade_return",
        "average_cash",
        "average_market_value",
        "average_capital_utilization",
        "insufficient_lot_cash_skips",
        "execution_skips",
    ]
    assert pd.read_csv(output["report_paths"]["summary_path"]).empty


def test_cli_parser_accepts_portfolio_backtest_arguments():
    args = cli.build_parser().parse_args(
        [
            "portfolio-backtest",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-05-07",
            "--initial-cash",
            "500000",
            "--top-ks",
            "5,10",
            "--holding-days",
            "5,10,15,20,30",
        ]
    )

    assert args.command == "portfolio-backtest"
    assert args.start_date == "2026-04-01"
    assert args.end_date == "2026-05-07"
    assert args.initial_cash == 500000.0
    assert args.top_ks == [5, 10]
    assert args.holding_days == [5, 10, 15, 20, 30]


def test_cli_parser_portfolio_defaults_are_not_shared_mutable_lists():
    parser = cli.build_parser()

    first = parser.parse_args(
        [
            "portfolio-backtest",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-05-07",
        ]
    )
    first.top_ks.append(99)
    first.holding_days.append(99)

    second = parser.parse_args(
        [
            "portfolio-backtest",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-05-07",
        ]
    )

    assert second.top_ks == [5, 10]
    assert second.holding_days == [5, 10, 15, 20, 30]


@pytest.mark.parametrize("value", ["", ",,", "5,a", "5,,10", "0", "-1", "5,"])
def test_cli_parser_rejects_invalid_top_ks(value):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(
            [
                "portfolio-backtest",
                "--start-date",
                "2026-04-01",
                "--end-date",
                "2026-05-07",
                "--top-ks",
                value,
            ]
        )

    assert exc.value.code == 2


def test_cli_main_runs_portfolio_backtest_and_prints_outputs(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_run_portfolio_backtest(
        start_date,
        end_date,
        initial_cash=500000.0,
        top_ks=(5, 10),
        holding_days=(5, 10, 15, 20, 30),
        reports_dir="/Users/xiwei/stock_research/reports",
    ):
        calls.append(
            (start_date, end_date, initial_cash, top_ks, holding_days, reports_dir)
        )
        summary = pd.DataFrame(
            [{"strategy_id": f"portfolio-{index}"} for index in range(10)]
        )
        return {
            "report_path": str(tmp_path / "portfolio.md"),
            "report_paths": {"summary_path": str(tmp_path / "portfolio_summary.csv")},
            "summary": summary,
        }

    monkeypatch.setattr(
        cli,
        "run_portfolio_backtest",
        fake_run_portfolio_backtest,
        raising=False,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "portfolio-backtest",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-05-07",
            "--initial-cash",
            "500000",
            "--top-ks",
            "5,10",
            "--holding-days",
            "5,10,15,20,30",
        ],
    )

    cli.main()

    assert calls == [
        (
            "2026-04-01",
            "2026-05-07",
            500000.0,
            [5, 10],
            [5, 10, 15, 20, 30],
            "/Users/xiwei/stock_research/reports",
        )
    ]
    assert capsys.readouterr().out.splitlines() == [
        f"portfolio_backtest_report|{tmp_path / 'portfolio.md'}",
        f"portfolio_backtest_summary|{tmp_path / 'portfolio_summary.csv'}",
        "portfolio_backtest_configs|10",
    ]


def test_write_portfolio_report_writes_markdown_and_equity_trades_summary_csv(tmp_path):
    result = PortfolioResult(
        config=PortfolioConfig(
            start_date="2026-04-01",
            end_date="2026-05-07",
            initial_cash=500000.0,
            top_k=5,
            holding_days=10,
            strategy_id="portfolio:2026-04-01:2026-05-07:top5:h10:cash500000",
        ),
        equity_curve=pd.DataFrame(
            [
                {
                    "strategy_id": "portfolio:2026-04-01:2026-05-07:top5:h10:cash500000",
                    "date": "2026-04-01",
                    "cash": 500000.0,
                    "market_value": 0.0,
                    "equity": 500000.0,
                    "drawdown": 0.0,
                    "open_positions": 0,
                },
                {
                    "strategy_id": "portfolio:2026-04-01:2026-05-07:top5:h10:cash500000",
                    "date": "2026-05-07",
                    "cash": 120000.0,
                    "market_value": 410000.0,
                    "equity": 530000.0,
                    "drawdown": -0.03,
                    "open_positions": 2,
                },
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "strategy_id": "portfolio:2026-04-01:2026-05-07:top5:h10:cash500000",
                    "top_k": 5,
                    "holding_days": 10,
                    "status": "closed",
                    "return_value": 0.08,
                    "skip_reason": None,
                },
                {
                    "strategy_id": "portfolio:2026-04-01:2026-05-07:top5:h10:cash500000",
                    "top_k": 5,
                    "holding_days": 10,
                    "status": "skipped",
                    "return_value": None,
                    "skip_reason": "insufficient_lot_cash",
                },
            ]
        ),
    )
    summary = pd.DataFrame([summarize_portfolio_result(result)])

    paths = write_portfolio_report(
        [result],
        summary,
        start_date="2026-04-01",
        end_date="2026-05-07",
        initial_cash=500000.0,
        top_ks=(5, 10),
        holding_days=(5, 10, 15, 20, 30),
        reports_dir=tmp_path,
    )

    expected_stem = "portfolio_2026-04-01_2026-05-07_cash500000_top5-10_h5-10-15-20-30"
    assert paths == {
        "report_path": str(tmp_path / f"{expected_stem}.md"),
        "equity_curve_path": str(tmp_path / f"{expected_stem}_equity.csv"),
        "trades_path": str(tmp_path / f"{expected_stem}_trades.csv"),
        "summary_path": str(tmp_path / f"{expected_stem}_summary.csv"),
    }

    markdown = (tmp_path / f"{expected_stem}.md").read_text(encoding="utf-8")
    assert "账户级模拟交易回测报告" in markdown
    assert "资金曲线" in markdown
    assert "最大回撤" in markdown
    assert "资金利用率" in markdown
    assert "仅作为研究验证，不构成交易指令" in markdown
    assert "买入建议" not in markdown
    assert "卖出建议" not in markdown
    assert "仓位建议" not in markdown
    assert "下单" not in markdown

    equity = pd.read_csv(paths["equity_curve_path"])
    trades = pd.read_csv(paths["trades_path"])
    written_summary = pd.read_csv(paths["summary_path"])
    assert list(equity["equity"]) == [500000.0, 530000.0]
    assert trades.shape[0] == 2
    expected_summary_columns = {
        "strategy_id",
        "top_k",
        "holding_days",
        "initial_cash",
        "final_equity",
        "total_return",
        "max_drawdown",
        "closed_trades",
        "open_trades",
        "skipped_trades",
        "win_rate",
        "mean_trade_return",
        "average_cash",
        "average_market_value",
        "average_capital_utilization",
        "insufficient_lot_cash_skips",
        "execution_skips",
    }
    assert expected_summary_columns.issubset(written_summary.columns)
    assert written_summary.iloc[0]["final_equity"] == pytest.approx(530000.0)
    assert written_summary.iloc[0]["average_capital_utilization"] == pytest.approx(0.41)
