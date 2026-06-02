import json
from pathlib import Path

import pandas as pd

from stock_research.trade_advice.advice import (
    TradeAdvicePolicy,
    generate_trade_advice,
    validate_trade_advice,
    write_trade_advice,
)


def _simulation_state() -> dict:
    return {
        "trade_date": "2026-05-28",
        "strategy_id": "portfolio:test",
        "cash": 80000.0,
        "market_value": 20000.0,
        "equity": 100000.0,
        "drawdown": -0.12,
        "risk_level": "warning",
        "positions": [],
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
    }


def test_generate_trade_advice_caps_exposure_and_requires_human_confirmation():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Alpha",
                "industry": "bank",
                "decision_label": "候选",
                "score": 0.91,
                "evidence_artifact_id": "agent:alpha",
            },
            {
                "asset_id": "CN:SH:600002",
                "stock_code": "600002.SH",
                "stock_name": "Beta",
                "industry": "bank",
                "decision_label": "候选",
                "score": 0.89,
                "evidence_artifact_id": "agent:beta",
            },
        ]
    )

    advice = generate_trade_advice(
        trade_date="2026-05-28",
        simulation_state=_simulation_state(),
        candidates=candidates,
        policy=TradeAdvicePolicy(
            max_single_position_pct=0.10,
            max_industry_position_pct=0.15,
            target_total_exposure_pct=0.60,
            drawdown_defensive_threshold=-0.10,
            defensive_exposure_multiplier=0.5,
        ),
    )

    assert advice["auto_trade_enabled"].eq(False).all()
    assert advice["execution_status"].eq("not_executed").all()
    assert advice["advice_status"].eq("pending_human_review").all()
    assert advice["requires_human_confirmation"].eq(True).all()
    assert advice["target_weight"].sum() <= 0.15
    assert advice["target_value"].sum() <= 15000.0


def test_validate_trade_advice_blocks_executed_or_evidence_free_rows():
    advice = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600001",
                "execution_status": "submitted",
                "auto_trade_enabled": False,
                "evidence_artifact_id": "agent:alpha",
            },
            {
                "asset_id": "CN:SH:600002",
                "execution_status": "not_executed",
                "auto_trade_enabled": True,
                "evidence_artifact_id": "",
            },
        ]
    )

    issues = validate_trade_advice(advice)

    assert {issue["code"] for issue in issues} == {
        "execution_not_allowed",
        "auto_trade_not_allowed",
        "missing_evidence",
    }


def test_write_trade_advice_outputs_artifacts_without_execution_language(tmp_path):
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Alpha",
                "industry": "bank",
                "decision_label": "候选",
                "score": 0.91,
                "evidence_artifact_id": "agent:alpha",
            }
        ]
    )
    advice = generate_trade_advice(
        trade_date="2026-05-28",
        simulation_state=_simulation_state(),
        candidates=candidates,
    )

    paths = write_trade_advice(
        trade_date="2026-05-28",
        advice=advice,
        output_dir=tmp_path,
    )

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")

    assert payload["issue_count"] == 0
    assert Path(paths["csv_path"]).exists()
    assert "待人工确认" in markdown
    assert "不执行自动下单" in markdown
