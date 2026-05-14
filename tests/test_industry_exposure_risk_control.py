from pathlib import Path

import pandas as pd

from stock_research import industry_exposure_risk_control as risk_control


def _score_rows(date: str, industry_prefix: str, start: int, end: int, base: float) -> list[dict]:
    return [
        {
            "trade_date": date,
            "asset_id": f"{industry_prefix}{idx:02d}",
            "score_total": base - idx,
        }
        for idx in range(start, end + 1)
    ]


def _membership_rows(date: str, industry: str, prefix: str, start: int, end: int) -> list[dict]:
    return [
        {
            "trade_date": date,
            "asset_id": f"{prefix}{idx:02d}",
            "industry_name": industry,
        }
        for idx in range(start, end + 1)
    ]


def test_single_industry_weight_cap_limits_selected_names():
    scores = pd.DataFrame(
        _score_rows("2026-01-01", "A", 1, 12, 200)
        + _score_rows("2026-01-01", "B", 1, 10, 150)
        + _score_rows("2026-01-01", "C", 1, 10, 120)
        + _score_rows("2026-01-01", "D", 1, 10, 100)
    )
    memberships = pd.DataFrame(
        _membership_rows("2026-01-01", "行业A", "A", 1, 12)
        + _membership_rows("2026-01-01", "行业B", "B", 1, 10)
        + _membership_rows("2026-01-01", "行业C", "C", 1, 10)
        + _membership_rows("2026-01-01", "行业D", "D", 1, 10)
    )

    selected = risk_control.select_exposure_capped_topn(
        scores,
        memberships,
        top_n=20,
        max_industry_count=5,
    )

    joined = selected.merge(memberships, on=["trade_date", "asset_id"])
    assert len(selected) == 20
    assert joined["industry_name"].value_counts()["行业A"] == 5
    assert joined["industry_name"].value_counts().max() <= 5


def test_top3_industry_cap_limits_combined_exposure():
    scores = pd.DataFrame(
        _score_rows("2026-01-01", "A", 1, 10, 300)
        + _score_rows("2026-01-01", "B", 1, 10, 280)
        + _score_rows("2026-01-01", "C", 1, 10, 260)
        + _score_rows("2026-01-01", "D", 1, 10, 180)
        + _score_rows("2026-01-01", "E", 1, 10, 160)
    )
    memberships = pd.DataFrame(
        _membership_rows("2026-01-01", "行业A", "A", 1, 10)
        + _membership_rows("2026-01-01", "行业B", "B", 1, 10)
        + _membership_rows("2026-01-01", "行业C", "C", 1, 10)
        + _membership_rows("2026-01-01", "行业D", "D", 1, 10)
        + _membership_rows("2026-01-01", "行业E", "E", 1, 10)
    )

    selected = risk_control.select_exposure_capped_topn(
        scores,
        memberships,
        top_n=20,
        max_top3_count=12,
    )

    joined = selected.merge(memberships, on=["trade_date", "asset_id"])
    counts = joined["industry_name"].value_counts().sort_values(ascending=False)
    assert len(selected) == 20
    assert counts.head(3).sum() <= 12


def test_risk_tag_light_downweight_never_adds_positive_weight():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "score_total": 100.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "score_total": 100.0},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "风险行业"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "中性行业"},
        ]
    )
    mainline = pd.DataFrame(
        [
            {"rebalance_date": "2026-01-01", "industry_name": "风险行业", "mainline_tag": "narrow_leader_only"},
            {"rebalance_date": "2026-01-01", "industry_name": "中性行业", "mainline_tag": "sustained_mainline"},
        ]
    )

    adjusted = risk_control.apply_risk_tag_light_downweight(scores, memberships, mainline, risk_multiplier=0.9)

    multipliers = adjusted.set_index("asset_id")["industry_risk_multiplier"]
    assert multipliers.max() <= 1.0
    assert multipliers["A1"] == 0.9
    assert multipliers["B1"] == 1.0


def test_exposure_cap_plus_risk_downweight_does_not_use_future_return():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "score_total": 100.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "score_total": 99.0},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "行业B"},
        ]
    )
    mainline = pd.DataFrame(
        [
            {"rebalance_date": "2026-01-01", "industry_name": "行业A", "mainline_tag": "neutral"},
            {"rebalance_date": "2026-01-01", "industry_name": "行业B", "mainline_tag": "overheated_mainline"},
        ]
    )
    diagnostics_a = pd.DataFrame(
        [{"rebalance_date": "2026-01-01", "industry_name": "行业A", "future_20d_return": -0.5}]
    )
    diagnostics_b = diagnostics_a.assign(future_20d_return=0.5)

    selected_a = risk_control.build_exposure_cap_plus_risk_downweight_scores(
        scores,
        memberships,
        mainline,
        diagnostics=diagnostics_a,
        top_n=2,
    )
    selected_b = risk_control.build_exposure_cap_plus_risk_downweight_scores(
        scores,
        memberships,
        mainline,
        diagnostics=diagnostics_b,
        top_n=2,
    )

    pd.testing.assert_frame_equal(selected_a, selected_b)


def test_turnover_smooth_keeps_previous_holdings_and_reduces_jump():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "score_total": 100.0},
            {"trade_date": "2026-01-01", "asset_id": "A2", "score_total": 99.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "B2", "score_total": 79.0},
            {"trade_date": "2026-01-02", "asset_id": "B1", "score_total": 100.0},
            {"trade_date": "2026-01-02", "asset_id": "B2", "score_total": 99.0},
            {"trade_date": "2026-01-02", "asset_id": "A1", "score_total": 98.0},
            {"trade_date": "2026-01-02", "asset_id": "A2", "score_total": 97.0},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": date, "asset_id": asset, "industry_name": asset[0]}
            for date in ["2026-01-01", "2026-01-02"]
            for asset in ["A1", "A2", "B1", "B2"]
        ]
    )

    raw = risk_control.select_exposure_capped_topn(scores, memberships, top_n=2)
    smooth = risk_control.select_exposure_capped_topn(
        scores,
        memberships,
        top_n=2,
        smooth_turnover=True,
        keep_candidate_rank=4,
    )

    raw_kept = risk_control.count_kept_assets(raw, "2026-01-02")
    smooth_kept = risk_control.count_kept_assets(smooth, "2026-01-02")
    assert smooth_kept > raw_kept


def test_write_outputs_has_required_files_and_report(tmp_path: Path):
    summary = pd.DataFrame([{"strategy": "baseline_top20", "cumulative_return_after_cost": 0.01}])
    annual = pd.DataFrame([{"year": 2026, "strategy": "baseline_top20"}])
    monthly = pd.DataFrame([{"rebalance_month": "2026-01", "strategy": "baseline_top20"}])
    exposure = pd.DataFrame([{"rebalance_date": "2026-01-01", "strategy": "baseline_top20"}])
    turnover = pd.DataFrame([{"rebalance_date": "2026-01-01", "strategy": "baseline_top20"}])

    paths = risk_control.write_exposure_risk_control_outputs(
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
    assert "Industry Exposure Risk Control v1 报告" in Path(paths["markdown_report"]).read_text(encoding="utf-8")
