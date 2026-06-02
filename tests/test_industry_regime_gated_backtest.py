from pathlib import Path

import pandas as pd
import pytest

from stock_research import industry_regime_gated_backtest as gated


def _inputs():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "score_total": 100},
            {"trade_date": "2026-01-01", "asset_id": "B1", "score_total": 100},
            {"trade_date": "2026-01-02", "asset_id": "A1", "score_total": 100},
            {"trade_date": "2026-01-02", "asset_id": "B1", "score_total": 100},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "强行业"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "弱行业"},
            {"trade_date": "2026-01-02", "asset_id": "A1", "industry_name": "强行业"},
            {"trade_date": "2026-01-02", "asset_id": "B1", "industry_name": "弱行业"},
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "rebalance_date": "2026-01-01",
                "industry_name": "强行业",
                "industry_focus_score_v2": 0.8,
                "future_20d_return": -0.9,
            },
            {
                "rebalance_date": "2026-01-01",
                "industry_name": "弱行业",
                "industry_focus_score_v2": -0.2,
                "future_20d_return": 0.9,
            },
            {
                "rebalance_date": "2026-01-02",
                "industry_name": "强行业",
                "industry_focus_score_v2": 0.8,
                "future_20d_return": -0.9,
            },
            {
                "rebalance_date": "2026-01-02",
                "industry_name": "弱行业",
                "industry_focus_score_v2": -0.2,
                "future_20d_return": 0.9,
            },
        ]
    )
    regimes = pd.DataFrame(
        [
            {"rebalance_date": "2026-01-01", "market_regime": "mainline"},
            {"rebalance_date": "2026-01-02", "market_regime": "rotation"},
        ]
    )
    mainline = pd.DataFrame(
        [
            {
                "rebalance_date": "2026-01-01",
                "industry_name": "强行业",
                "industry_mainline_score_v1": 0.9,
                "mainline_tag": "sustained_mainline",
            },
            {
                "rebalance_date": "2026-01-01",
                "industry_name": "弱行业",
                "industry_mainline_score_v1": 0.1,
                "mainline_tag": "neutral",
            },
            {
                "rebalance_date": "2026-01-02",
                "industry_name": "强行业",
                "industry_mainline_score_v1": 0.9,
                "mainline_tag": "sustained_mainline",
            },
            {
                "rebalance_date": "2026-01-02",
                "industry_name": "弱行业",
                "industry_mainline_score_v1": 0.1,
                "mainline_tag": "neutral",
            },
        ]
    )
    return scores, memberships, diagnostics, regimes, mainline


def test_mainline_regime_allows_positive_industry_weight():
    _, _, diagnostics, regimes, mainline = _inputs()

    panel = gated.build_industry_weight_panel(
        diagnostics,
        regimes,
        mainline,
        strategy="regime_gated_soft_weight",
    )

    row = panel[(panel["rebalance_date"] == "2026-01-01") & (panel["industry_name"] == "强行业")].iloc[0]
    assert row["positive_weight_allowed"] is True
    assert row["industry_score_multiplier"] > 1.0


def test_rotation_regime_blocks_positive_industry_weight():
    _, _, diagnostics, regimes, mainline = _inputs()

    panel = gated.build_industry_weight_panel(
        diagnostics,
        regimes,
        mainline,
        strategy="regime_gated_soft_weight",
    )

    row = panel[(panel["rebalance_date"] == "2026-01-02") & (panel["industry_name"] == "强行业")].iloc[0]
    assert row["positive_weight_allowed"] is False
    assert row["industry_score_multiplier"] <= 1.0


def test_risk_tags_trigger_downweight():
    _, _, diagnostics, regimes, mainline = _inputs()
    risky = mainline.copy()
    risky.loc[risky["industry_name"] == "强行业", "mainline_tag"] = "narrow_leader_only"

    panel = gated.build_industry_weight_panel(
        diagnostics,
        regimes,
        risky,
        strategy="regime_gated_risk_downweight",
    )

    row = panel[(panel["rebalance_date"] == "2026-01-01") & (panel["industry_name"] == "强行业")].iloc[0]
    assert row["risk_downweighted"] is True
    assert row["industry_score_multiplier"] < 1.0


def test_overheated_mainline_triggers_downweight():
    _, _, diagnostics, regimes, mainline = _inputs()
    risky = mainline.copy()
    risky.loc[risky["industry_name"] == "强行业", "mainline_tag"] = "overheated_mainline"

    panel = gated.build_industry_weight_panel(
        diagnostics,
        regimes,
        risky,
        strategy="regime_gated_risk_downweight",
    )

    row = panel[(panel["rebalance_date"] == "2026-01-01") & (panel["industry_name"] == "强行业")].iloc[0]
    assert row["risk_downweighted"] is True
    assert row["industry_score_multiplier"] < 1.0


def test_smooth_weight_reduces_industry_weight_jump():
    raw = pd.DataFrame(
        [
            {"rebalance_date": "2026-01-01", "industry_name": "行业A", "industry_weight_adjustment": 0.15},
            {"rebalance_date": "2026-01-02", "industry_name": "行业A", "industry_weight_adjustment": -0.10},
        ]
    )

    smooth = gated.smooth_industry_weight_panel(raw, max_step=0.05)

    jump = abs(smooth["industry_weight_adjustment"].iloc[1] - smooth["industry_weight_adjustment"].iloc[0])
    assert jump <= 0.0500001


def test_weight_calculation_does_not_use_future_return():
    _, _, diagnostics, regimes, mainline = _inputs()
    changed_future = diagnostics.copy()
    changed_future["future_20d_return"] = changed_future["future_20d_return"] * -1

    panel_a = gated.build_industry_weight_panel(
        diagnostics,
        regimes,
        mainline,
        strategy="regime_gated_soft_weight",
    )
    panel_b = gated.build_industry_weight_panel(
        changed_future,
        regimes,
        mainline,
        strategy="regime_gated_soft_weight",
    )

    assert panel_a["industry_score_multiplier"].tolist() == pytest.approx(
        panel_b["industry_score_multiplier"].tolist()
    )


def test_write_outputs_has_required_files(tmp_path: Path):
    summary = pd.DataFrame([{"strategy": "baseline_top20", "cumulative_return_after_cost": 0.1}])
    annual = pd.DataFrame([{"year": 2026, "strategy": "baseline_top20"}])
    monthly = pd.DataFrame([{"rebalance_month": "2026-01", "strategy": "baseline_top20"}])
    exposure = pd.DataFrame([{"rebalance_date": "2026-01-01", "strategy": "baseline_top20"}])
    turnover = pd.DataFrame([{"rebalance_date": "2026-01-01", "strategy": "baseline_top20"}])

    paths = gated.write_regime_gated_backtest_outputs(
        output_dir=tmp_path,
        summary=summary,
        annual_metrics=annual,
        monthly_metrics=monthly,
        industry_exposure=exposure,
        turnover_detail=turnover,
    )

    assert Path(paths["summary"]).exists()
    assert Path(paths["annual_metrics"]).exists()
    assert Path(paths["monthly_metrics"]).exists()
    assert Path(paths["industry_exposure"]).exists()
    assert Path(paths["turnover_detail"]).exists()
    assert Path(paths["markdown_report"]).exists()
    assert "Industry Regime Gated Backtest v1 报告" in Path(paths["markdown_report"]).read_text(encoding="utf-8")
