import json
from pathlib import Path

import pandas as pd

from stock_research.simulation.virtual_portfolio import (
    build_virtual_portfolio_review,
    load_simulation_states,
    write_virtual_portfolio_review,
)


def _state(trade_date: str, *, drawdown: float, equity: float = 100000.0) -> dict:
    return {
        "trade_date": trade_date,
        "strategy_id": "portfolio:test",
        "cash": 40000.0,
        "market_value": 60000.0,
        "equity": equity,
        "drawdown": drawdown,
        "exposure_pct": 0.60,
        "open_position_count": 1,
        "risk_level": "warning" if drawdown <= -0.10 else "normal",
        "positions": [
            {
                "asset_id": "CN:SH:600001",
                "buy_date": trade_date,
                "buy_value": 60000.0,
                "position_weight": 0.60,
                "status": "open",
            }
        ],
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
    }


def _advice() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-05-28",
                "asset_id": "CN:SH:600001",
                "action": "consider_buy",
                "target_weight": 0.08,
                "target_value": 8000.0,
                "advice_status": "pending_human_review",
                "execution_status": "not_executed",
                "requires_human_confirmation": True,
                "auto_trade_enabled": False,
                "evidence_artifact_id": "agent:alpha",
            }
        ]
    )


def test_load_simulation_states_accepts_review_and_state_json(tmp_path):
    review_path = tmp_path / "portfolio_simulation_review.json"
    review_path.write_text(
        json.dumps({"states": [_state("2026-05-27", drawdown=-0.04)]}),
        encoding="utf-8",
    )
    state_path = tmp_path / "portfolio_simulation_state.json"
    state_path.write_text(json.dumps(_state("2026-05-28", drawdown=-0.12)), encoding="utf-8")

    states = load_simulation_states([review_path, state_path])

    assert [state["trade_date"] for state in states] == ["2026-05-27", "2026-05-28"]
    assert {state["source_artifact_path"] for state in states} == {
        str(review_path),
        str(state_path),
    }


def test_build_virtual_portfolio_review_rolls_history_risk_and_manual_advice():
    review = build_virtual_portfolio_review(
        trade_date="2026-05-28",
        portfolio_id="demo",
        states=[
            _state("2026-05-27", drawdown=-0.04, equity=101000.0),
            _state("2026-05-28", drawdown=-0.12, equity=98000.0),
        ],
        advice=_advice(),
    )

    assert review["status"] == "manual_review_required"
    assert review["auto_trade_enabled"] is False
    assert review["risk_summary"]["latest_risk_level"] == "warning"
    assert review["risk_summary"]["max_drawdown"] == -0.12
    assert review["risk_summary"]["warning_state_count"] == 1
    assert review["advice_summary"]["status"] == "manual_review_required"
    assert review["advice_summary"]["advice_count"] == 1
    assert review["advice_summary"]["target_exposure_pct"] == 0.08
    assert len(review["history_rows"]) == 2
    assert review["latest_positions"][0]["asset_id"] == "CN:SH:600001"


def test_write_virtual_portfolio_review_outputs_json_markdown_history_and_positions(tmp_path):
    review = build_virtual_portfolio_review(
        trade_date="2026-05-28",
        portfolio_id="demo",
        states=[
            _state("2026-05-27", drawdown=-0.04),
            _state("2026-05-28", drawdown=-0.12),
        ],
        advice=_advice(),
    )

    paths = write_virtual_portfolio_review(review, output_dir=tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    history = pd.read_csv(paths["history_csv_path"])
    positions = pd.read_csv(paths["positions_csv_path"])

    assert payload["status"] == "manual_review_required"
    assert "Virtual Portfolio Review" in markdown
    assert "不执行自动下单" in markdown
    assert history["trade_date"].tolist() == ["2026-05-27", "2026-05-28"]
    assert positions["asset_id"].tolist() == ["CN:SH:600001"]
