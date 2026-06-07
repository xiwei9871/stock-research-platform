from __future__ import annotations

import pandas as pd
import pytest

from stock_research.factor_eval.report import generate_factor_eval_report
from stock_research.research_infra.factor_cards import (
    FactorCardValidationError,
    build_factor_evaluation_card,
    render_factor_evaluation_card_markdown,
)


def test_build_factor_evaluation_card_wraps_existing_factor_eval_report() -> None:
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "D", "factor_value": 4.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "factor_value": 4.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "D", "forward_return_5d": 0.04},
            {"trade_date": "2026-01-02", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-02", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "D", "forward_return_5d": 0.04},
        ]
    )
    eval_report = generate_factor_eval_report(
        factors,
        returns,
        factor_name="demo_factor",
        return_col="forward_return_5d",
        quantiles=2,
        top_n=2,
    )

    card = build_factor_evaluation_card(
        eval_report,
        sample_window={"start_date": "2026-01-01", "end_date": "2026-01-02"},
        universe={"name": "toy_universe", "asset_count": 4},
        label_definition={"name": "forward_return_5d", "horizon_days": 5},
        regime_breakdown={"all": {"mean_ic": 1.0}},
        industry_exposure={"max_industry_weight": 0.25},
        drawdown_notes=["toy sample has no drawdown analysis"],
        warnings=["toy sample only"],
    )

    assert card["factor_name"] == "demo_factor"
    assert card["sample_window"]["start_date"] == "2026-01-01"
    assert card["universe"]["name"] == "toy_universe"
    assert card["label_definition"]["horizon_days"] == 5
    assert card["ic_summary"]["mean_ic"] == pytest.approx(1.0)
    assert card["rank_ic_summary"]["mean_ic"] == pytest.approx(1.0)
    assert card["quantile_return_summary"]["row_count"] == 4
    assert card["quantile_return_summary"]["mean_top_bottom_spread"] == pytest.approx(0.02)
    assert card["turnover_summary"]["mean_turnover"] == pytest.approx(0.0)
    assert card["topn_hit_summary"]["status"] == "not_provided"
    assert card["warnings"] == ["toy sample only"]


def test_build_factor_evaluation_card_requires_sample_universe_and_label() -> None:
    with pytest.raises(FactorCardValidationError) as exc:
        build_factor_evaluation_card(
            {"factor_name": "demo_factor", "ic_summary": {}, "rank_ic_summary": {}},
            sample_window={},
            universe={},
            label_definition={},
        )

    message = str(exc.value)
    assert "sample_window" in message
    assert "universe" in message
    assert "label_definition" in message


def test_render_factor_evaluation_card_markdown_includes_review_sections() -> None:
    card = {
        "factor_name": "demo_factor",
        "sample_window": {"start_date": "2026-01-01", "end_date": "2026-01-02"},
        "universe": {"name": "toy_universe", "asset_count": 4},
        "label_definition": {"name": "forward_return_5d", "horizon_days": 5},
        "ic_summary": {"mean_ic": 1.0, "ic_count": 2},
        "rank_ic_summary": {"mean_ic": 1.0, "ic_count": 2},
        "quantile_return_summary": {"row_count": 4, "mean_top_bottom_spread": 0.02},
        "topn_hit_summary": {"status": "not_provided"},
        "turnover_summary": {"mean_turnover": 0.0, "row_count": 1},
        "regime_breakdown": {},
        "industry_exposure": {},
        "drawdown_notes": [],
        "warnings": ["toy sample only"],
    }

    markdown = render_factor_evaluation_card_markdown(card)

    assert markdown.startswith("# Factor Evaluation Card: demo_factor")
    assert "## Sample" in markdown
    assert "## IC Summary" in markdown
    assert "## Turnover" in markdown
    assert "- toy sample only" in markdown
