import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.portfolio_backtest import PortfolioConfig, PortfolioResult
from stock_research.simulation.portfolio import (
    build_portfolio_simulation_state,
    write_portfolio_simulation_review,
    write_portfolio_simulation_state,
)


def _portfolio_result() -> PortfolioResult:
    config = PortfolioConfig(
        start_date="2026-05-01",
        end_date="2026-05-28",
        initial_cash=100000.0,
        top_k=2,
        holding_days=5,
        strategy_id="portfolio:test",
    )
    equity = pd.DataFrame(
        [
            {
                "strategy_id": "portfolio:test",
                "date": "2026-05-27",
                "cash": 40000.0,
                "market_value": 55000.0,
                "equity": 95000.0,
                "drawdown": -0.05,
                "open_positions": 2,
            },
            {
                "strategy_id": "portfolio:test",
                "date": "2026-05-28",
                "cash": 38000.0,
                "market_value": 56000.0,
                "equity": 94000.0,
                "drawdown": -0.12,
                "open_positions": 2,
            },
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "strategy_id": "portfolio:test",
                "asset_id": "CN:SH:600001",
                "shares": 1000,
                "buy_open": 20.0,
                "buy_value": 20000.0,
                "status": "open",
                "selection_date": "2026-05-27",
                "buy_date": "2026-05-28",
                "rank": 1,
                "score": 0.9,
            },
            {
                "strategy_id": "portfolio:test",
                "asset_id": "CN:SH:600002",
                "shares": 1200,
                "buy_open": 30.0,
                "buy_value": 36000.0,
                "status": "open",
                "selection_date": "2026-05-27",
                "buy_date": "2026-05-28",
                "rank": 2,
                "score": 0.8,
            },
            {
                "strategy_id": "portfolio:test",
                "asset_id": "CN:SH:600003",
                "shares": 100,
                "buy_open": 10.0,
                "buy_value": 1000.0,
                "status": "closed",
                "selection_date": "2026-05-20",
                "buy_date": "2026-05-21",
                "sell_date": "2026-05-28",
            },
        ]
    )
    return PortfolioResult(config=config, equity_curve=equity, trades=trades)


def test_build_portfolio_simulation_state_tracks_latest_equity_positions_and_risk():
    state = build_portfolio_simulation_state(_portfolio_result())

    assert state["trade_date"] == "2026-05-28"
    assert state["strategy_id"] == "portfolio:test"
    assert state["cash"] == pytest.approx(38000.0)
    assert state["market_value"] == pytest.approx(56000.0)
    assert state["equity"] == pytest.approx(94000.0)
    assert state["exposure_pct"] == pytest.approx(56000.0 / 94000.0)
    assert state["drawdown"] == pytest.approx(-0.12)
    assert state["risk_level"] == "warning"
    assert state["auto_trade_enabled"] is False
    assert state["human_confirmation_required"] is True
    assert [item["asset_id"] for item in state["positions"]] == [
        "CN:SH:600001",
        "CN:SH:600002",
    ]


def test_write_portfolio_simulation_state_outputs_json_csv_and_markdown(tmp_path):
    state = build_portfolio_simulation_state(_portfolio_result())

    paths = write_portfolio_simulation_state(state, output_dir=tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    positions = pd.read_csv(paths["positions_csv_path"])

    assert payload["auto_trade_enabled"] is False
    assert positions["asset_id"].tolist() == ["CN:SH:600001", "CN:SH:600002"]
    assert "仅作为模拟组合状态" in markdown
    assert "不执行自动下单" in markdown


def test_write_portfolio_simulation_review_writes_all_strategy_states(tmp_path):
    result = _portfolio_result()
    backtest_result = {
        "results": [result],
        "run_card": {"run_card_json_path": "outputs/run_card.json"},
    }

    paths = write_portfolio_simulation_review(
        backtest_result,
        output_dir=tmp_path,
    )

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["state_count"] == 1
    assert payload["states"][0]["source_run_card_path"] == "outputs/run_card.json"
    assert Path(paths["states_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
