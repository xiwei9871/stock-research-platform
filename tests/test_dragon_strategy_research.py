from pathlib import Path

import pandas as pd
import pytest

from stock_research import cli
from stock_research.dragon_strategy_research import (
    assign_dragon_roles,
    assign_entry_windows,
    assign_entry_windows_v2,
    build_dragon_v1_1_outputs_from_diagnostics,
    build_dragon_v1_2_outputs_from_diagnostics,
    build_dragon_v1_3_outputs_from_diagnostics,
    build_dragon_diagnostics,
    build_low_bucket_audit,
    build_lifecycle_role_effectiveness,
    build_role_entry_cross_effectiveness,
    build_score_bucket_effectiveness,
    build_v1_3_entry_score_bucket_effectiveness,
    build_v1_3_entry_window_effectiveness,
    build_v1_3_follower_penalty_audit,
    build_v1_3_low_quality_split_audit,
    build_v1_3_role_entry_cross_effectiveness,
    build_v1_2_component_audit,
    build_weak_candidate_audit,
    compute_dragon_scores,
    compute_v1_2_scores,
    compute_v1_3_scores,
    effective_membership_for_dates,
    summarize_role_effectiveness,
    write_dragon_outputs,
)


def test_dragon_score_ignores_future_return_columns():
    base = _sample_feature_frame()
    with_future = base.assign(
        future_1d_return=[99.0, -99.0, 50.0, -50.0, 25.0, -25.0, 10.0, -10.0],
        future_20d_return=[99.0, -99.0, 50.0, -50.0, 25.0, -25.0, 10.0, -10.0],
    )

    scored_base = compute_dragon_scores(base)
    scored_future = compute_dragon_scores(with_future)

    assert scored_base["dragon_score"].tolist() == scored_future["dragon_score"].tolist()


def test_effective_membership_uses_trade_date_window():
    memberships = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "industry_name": "Old",
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
            },
            {
                "asset_id": "A",
                "industry_name": "New",
                "start_date": "2024-07-01",
                "end_date": None,
            },
        ]
    )
    dates = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2024-06-28"},
            {"asset_id": "A", "trade_date": "2024-07-02"},
        ]
    )

    result = effective_membership_for_dates(dates, memberships)

    assert result["industry_name"].tolist() == ["Old", "New"]


def test_assign_dragon_roles_for_representative_rows():
    scored = compute_dragon_scores(_sample_feature_frame())
    roles = assign_dragon_roles(scored)

    assert dict(zip(roles["asset_id"], roles["dragon_role"], strict=False)) == {
        "LEADER": "dragon_leader",
        "CORE": "core_middle",
        "HOT": "overheated_leader",
        "CATCH": "laggard_catchup",
        "EARLY": "early_potential",
        "FOLLOW": "follower",
        "COOL": "cooling_down",
        "WEAK": "weak_candidate",
    }


def test_early_potential_rule_is_independent_of_future_returns():
    base = _sample_feature_frame()
    with_future = base.assign(
        future_5d_return=[-0.9, -0.5, -0.4, -0.3, 9.0, -0.2, -0.1, 0.0],
        future_10d_return=[-0.9, -0.5, -0.4, -0.3, 9.0, -0.2, -0.1, 0.0],
    )

    base_roles = assign_dragon_roles(compute_dragon_scores(base))
    future_roles = assign_dragon_roles(compute_dragon_scores(with_future))

    assert base_roles["dragon_role"].tolist() == future_roles["dragon_role"].tolist()
    assert dict(zip(base_roles["asset_id"], base_roles["dragon_role"], strict=False))["EARLY"] == "early_potential"
    assert dict(zip(base_roles["asset_id"], base_roles["dragon_role"], strict=False))["WEAK"] == "weak_candidate"


def test_tightened_leader_excludes_overheated_terminal_move():
    frame = _sample_feature_frame()
    scored = assign_dragon_roles(compute_dragon_scores(frame))

    assert dict(zip(scored["asset_id"], scored["dragon_role"], strict=False))["HOT"] == "overheated_leader"
    hot = scored[scored["asset_id"] == "HOT"].iloc[0]
    assert hot["overheat_penalty"] >= 0.45


def test_overheat_penalty_rises_for_extreme_short_term_move():
    frame = _sample_feature_frame()
    normal = compute_dragon_scores(frame)
    extreme = frame.copy()
    extreme.loc[extreme["asset_id"] == "LEADER", "stock_return_5d"] = 0.35
    extreme.loc[extreme["asset_id"] == "LEADER", "stock_return_10d"] = 0.55
    extreme.loc[extreme["asset_id"] == "LEADER", "amount_vs_20d"] = 4.0

    heated = compute_dragon_scores(extreme)

    normal_penalty = normal.loc[
        normal["asset_id"] == "LEADER", "overheat_penalty"
    ].iloc[0]
    heated_penalty = heated.loc[
        heated["asset_id"] == "LEADER", "overheat_penalty"
    ].iloc[0]
    assert heated_penalty > normal_penalty


def test_follower_penalty_rises_when_stock_lags_hot_industry():
    scored = compute_dragon_scores(_sample_feature_frame())

    follower_penalty = scored.loc[
        scored["asset_id"] == "FOLLOW", "follower_penalty"
    ].iloc[0]
    leader_penalty = scored.loc[
        scored["asset_id"] == "LEADER", "follower_penalty"
    ].iloc[0]

    assert follower_penalty > leader_penalty


def test_role_effectiveness_statistics_are_correct():
    diagnostics = pd.DataFrame(
        [
            {
                "dragon_role": "dragon_leader",
                "future_1d_return": 0.01,
                "future_3d_return": 0.02,
                "future_5d_return": 0.03,
                "future_10d_return": 0.05,
                "future_20d_return": 0.08,
                "future_10d_max_drawdown": -0.04,
                "future_20d_max_drawdown": -0.06,
            },
            {
                "dragon_role": "dragon_leader",
                "future_1d_return": -0.01,
                "future_3d_return": 0.00,
                "future_5d_return": 0.05,
                "future_10d_return": -0.01,
                "future_20d_return": 0.02,
                "future_10d_max_drawdown": -0.08,
                "future_20d_max_drawdown": -0.10,
            },
            {
                "dragon_role": "follower",
                "future_1d_return": -0.02,
                "future_3d_return": -0.01,
                "future_5d_return": -0.03,
                "future_10d_return": -0.04,
                "future_20d_return": -0.06,
                "future_10d_max_drawdown": -0.12,
                "future_20d_max_drawdown": -0.16,
            },
        ]
    )

    summary = summarize_role_effectiveness(diagnostics)
    leader = summary[summary["role"] == "dragon_leader"].iloc[0]

    assert leader["sample_count"] == 2
    assert leader["avg_future_5d_return"] == pytest.approx(0.04)
    assert leader["median_future_10d_return"] == pytest.approx(0.02)
    assert leader["win_rate_10d"] == pytest.approx(0.5)
    assert leader["avg_future_20d_max_drawdown"] == pytest.approx(-0.08)


def test_score_bucket_effectiveness_statistics_are_correct():
    diagnostics = _scored_diagnostics_with_future()

    table = build_score_bucket_effectiveness(diagnostics, buckets=3)

    assert {"year", "score_bucket", "sample_count", "avg_future_10d_return"}.issubset(table.columns)
    all_years = table[table["year"] == "all"]
    assert int(all_years["sample_count"].sum()) == len(diagnostics)
    assert all_years["score_bucket"].nunique() == 3


def test_lifecycle_role_effectiveness_statistics_are_correct():
    diagnostics = _scored_diagnostics_with_future()

    table = build_lifecycle_role_effectiveness(diagnostics)

    assert {
        "trend_lifecycle_stage",
        "dragon_role",
        "sample_count",
        "avg_future_5d_return",
    }.issubset(table.columns)
    assert ("breakout", "dragon_leader") in set(
        zip(table["trend_lifecycle_stage"], table["dragon_role"], strict=False)
    )


def test_weak_candidate_audit_groups_quantile_structure():
    diagnostics = _scored_diagnostics_with_future()

    audit = build_weak_candidate_audit(diagnostics, buckets=3)

    assert {
        "year",
        "industry_name",
        "dragon_score_bucket",
        "sample_count",
        "avg_future_20d_return",
    }.issubset(audit.columns)
    assert audit["sample_count"].sum() >= 1


def test_build_diagnostics_appends_future_returns_after_scoring():
    bars = _sample_bars()
    memberships = pd.DataFrame(
        [
            {
                "asset_id": "LEADER",
                "industry_name": "Tech",
                "start_date": "2024-01-01",
                "end_date": None,
            },
            {
                "asset_id": "FOLLOW",
                "industry_name": "Tech",
                "start_date": "2024-01-01",
                "end_date": None,
            },
        ]
    )
    industry = pd.DataFrame(
        [
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_focus_score_v2": 0.9,
                "mainline_score": 0.9,
            }
        ]
    )

    diagnostics = build_dragon_diagnostics(
        bars=bars,
        memberships=memberships,
        industry_diagnostics=industry,
        start_date="2024-01-26",
        end_date="2024-01-26",
        hot_industry_top_n=1,
    )

    assert set(diagnostics["asset_id"]) == {"LEADER", "FOLLOW"}
    assert diagnostics["future_5d_return"].notna().all()
    rescored = compute_dragon_scores(
        diagnostics.drop(columns=["dragon_score", "dragon_rank_in_industry", "dragon_role"])
    )
    assert rescored["dragon_score"].tolist() == diagnostics["dragon_score"].tolist()


def test_markdown_report_can_be_generated(tmp_path):
    diagnostics = compute_dragon_scores(_sample_feature_frame())
    diagnostics = assign_dragon_roles(diagnostics)
    diagnostics = diagnostics.assign(
        future_1d_return=0.01,
        future_3d_return=0.02,
        future_5d_return=0.03,
        future_10d_return=0.04,
        future_20d_return=0.05,
        future_10d_max_drawdown=-0.04,
        future_20d_max_drawdown=-0.06,
    )

    result = write_dragon_outputs(
        diagnostics=diagnostics,
        output_dir=tmp_path,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )

    report = Path(result["paths"]["markdown_report"]).read_text()
    assert "# Dragon Strategy Research v1 诊断报告" in report
    assert "## 4. 角色有效性检验" in report
    assert "龙虎榜" in report
    assert Path(result["paths"]["diagnostics"]).exists()


def test_v1_1_outputs_and_report_can_be_generated(tmp_path):
    diagnostics = _scored_diagnostics_with_future()

    result = build_dragon_v1_1_outputs_from_diagnostics(
        diagnostics,
        output_dir=tmp_path,
        start_date="2024-01-01",
        end_date="2026-12-31",
    )

    paths = result["paths"]
    assert Path(paths["diagnostics"]).name == "dragon_strategy_v1_1_diagnostics.csv"
    assert Path(paths["weak_candidate_audit"]).exists()
    assert Path(paths["overheat_audit"]).exists()
    assert Path(paths["score_bucket_effectiveness"]).exists()
    assert Path(paths["lifecycle_role_effectiveness"]).exists()
    report = Path(paths["markdown_report"]).read_text()
    assert "# Dragon Strategy Research v1.1 角色校准报告" in report
    assert "early_potential" in report


def test_v1_2_scores_ignore_future_return_columns():
    base = assign_dragon_roles(compute_dragon_scores(_sample_feature_frame()))
    with_future = base.assign(
        future_1d_return=[9.0, -9.0, 8.0, -8.0, 7.0, -7.0, 6.0, -6.0],
        future_20d_return=[9.0, -9.0, 8.0, -8.0, 7.0, -7.0, 6.0, -6.0],
    )

    scored_base = compute_v1_2_scores(base)
    scored_future = compute_v1_2_scores(with_future)

    assert scored_base["dragon_status_score"].tolist() == scored_future["dragon_status_score"].tolist()
    assert scored_base["dragon_entry_score"].tolist() == scored_future["dragon_entry_score"].tolist()
    assert scored_base["dragon_risk_score"].tolist() == scored_future["dragon_risk_score"].tolist()


def test_entry_window_rules_classify_representative_rows():
    scored = assign_entry_windows(compute_v1_2_scores(assign_dragon_roles(compute_dragon_scores(_sample_feature_frame()))))
    windows = dict(zip(scored["asset_id"], scored["entry_window"], strict=False))

    assert windows["HOT"] == "overheat_avoid"
    assert windows["COOL"] == "cooling_avoid"
    assert windows["WEAK"] == "low_quality_ignore"
    assert windows["EARLY"] == "early_setup"
    assert windows["LEADER"] in {"breakout_entry", "acceleration_entry"}


def test_component_audit_bucket_statistics_and_signal_type():
    diagnostics = assign_entry_windows(compute_v1_2_scores(_scored_diagnostics_with_future()))

    audit = build_v1_2_component_audit(diagnostics, buckets=3)

    assert {
        "component_name",
        "bucket",
        "signal_type",
        "sample_count",
        "avg_future_10d_return",
    }.issubset(audit.columns)
    entry_rows = audit[audit["component_name"] == "dragon_entry_score"]
    assert int(entry_rows["sample_count"].sum()) == len(diagnostics)
    assert set(audit["signal_type"]).issubset(
        {"useful_signal", "risk_signal", "inverted_signal", "weak_signal"}
    )


def test_low_bucket_audit_outputs_grouped_explanation_rows():
    diagnostics = assign_entry_windows(compute_v1_2_scores(_scored_diagnostics_with_future()))

    audit = build_low_bucket_audit(diagnostics, buckets=3, low_bucket_max=1)

    assert {
        "year",
        "industry_name",
        "dragon_role",
        "sample_count",
        "avg_future_20d_return",
    }.issubset(audit.columns)
    assert audit["sample_count"].sum() >= 1


def test_role_entry_cross_effectiveness_statistics_are_correct():
    diagnostics = assign_entry_windows(compute_v1_2_scores(_scored_diagnostics_with_future()))

    table = build_role_entry_cross_effectiveness(diagnostics)

    assert {
        "dragon_role",
        "entry_window",
        "sample_count",
        "avg_future_10d_return",
    }.issubset(table.columns)
    assert ("dragon_leader", "breakout_entry") in set(
        zip(table["dragon_role"], table["entry_window"], strict=False)
    )


def test_v1_2_outputs_and_report_can_be_generated(tmp_path):
    diagnostics = _scored_diagnostics_with_future()

    result = build_dragon_v1_2_outputs_from_diagnostics(
        diagnostics,
        output_dir=tmp_path,
        start_date="2024-01-01",
        end_date="2026-12-31",
    )

    paths = result["paths"]
    assert Path(paths["diagnostics"]).name == "dragon_strategy_v1_2_diagnostics.csv"
    assert Path(paths["component_audit"]).exists()
    assert Path(paths["low_bucket_audit"]).exists()
    assert Path(paths["entry_window_effectiveness"]).exists()
    assert Path(paths["role_entry_cross_effectiveness"]).exists()
    report = Path(paths["markdown_report"]).read_text()
    assert "# Dragon Strategy Research v1.2 分数重构报告" in report
    assert "dragon_entry_score" in report


def test_entry_window_v2_splits_low_quality_ignore_cases():
    diagnostics = assign_entry_windows_v2(compute_v1_3_scores(_scored_diagnostics_with_future()))
    windows = dict(zip(diagnostics["asset_id"], diagnostics["entry_window_v2"], strict=False))

    assert windows["FOLLOW"] == "low_congestion_opportunity"
    assert windows["CATCH"] == "recovery_or_repair"
    assert windows["WEAK"] == "true_low_quality"
    assert windows["HOT"] == "overheat_avoid"
    assert windows["COOL"] == "cooling_avoid"


def test_dragon_entry_score_v2_ignores_future_returns_and_penalizes_high_risk():
    base = assign_entry_windows(compute_v1_2_scores(assign_dragon_roles(compute_dragon_scores(_sample_feature_frame()))))
    with_future = base.assign(
        future_5d_return=[9.0, -9.0, 8.0, -8.0, 7.0, -7.0, 6.0, -6.0],
        future_20d_return=[9.0, -9.0, 8.0, -8.0, 7.0, -7.0, 6.0, -6.0],
    )

    scored_base = compute_v1_3_scores(base)
    scored_future = compute_v1_3_scores(with_future)

    assert scored_base["dragon_entry_score_v2"].tolist() == scored_future["dragon_entry_score_v2"].tolist()
    hot_score = scored_base.loc[scored_base["asset_id"] == "HOT", "dragon_entry_score_v2"].iloc[0]
    early_score = scored_base.loc[scored_base["asset_id"] == "EARLY", "dragon_entry_score_v2"].iloc[0]
    assert hot_score < early_score
    assert hot_score < 0.45


def test_follower_penalty_high_with_hot_industry_can_be_low_congestion_opportunity():
    diagnostics = assign_entry_windows_v2(compute_v1_3_scores(_scored_diagnostics_with_future()))
    follow = diagnostics[diagnostics["asset_id"] == "FOLLOW"].iloc[0]

    assert follow["follower_penalty"] >= 0.35
    assert follow["dragon_risk_score"] < 0.35
    assert follow["entry_window_v2"] == "low_congestion_opportunity"


def test_v1_3_audits_and_bucket_statistics_are_correct():
    diagnostics = assign_entry_windows_v2(compute_v1_3_scores(_scored_diagnostics_with_future()))

    low_split = build_v1_3_low_quality_split_audit(diagnostics)
    follower_audit = build_v1_3_follower_penalty_audit(diagnostics, buckets=3)
    buckets = build_v1_3_entry_score_bucket_effectiveness(diagnostics, buckets=3)
    windows = build_v1_3_entry_window_effectiveness(diagnostics)
    cross = build_v1_3_role_entry_cross_effectiveness(diagnostics)

    assert {"entry_window_v2", "sample_count", "avg_future_10d_return"}.issubset(low_split.columns)
    assert {"follower_penalty_bucket", "entry_window_v2", "sample_count"}.issubset(follower_audit.columns)
    assert int(buckets["sample_count"].sum()) == len(diagnostics)
    assert "entry_window_v2" in windows.columns
    assert ("follower", "low_congestion_opportunity") in set(
        zip(cross["dragon_role"], cross["entry_window_v2"], strict=False)
    )


def test_v1_3_outputs_and_report_can_be_generated(tmp_path):
    diagnostics = _scored_diagnostics_with_future()

    result = build_dragon_v1_3_outputs_from_diagnostics(
        diagnostics,
        output_dir=tmp_path,
        start_date="2024-01-01",
        end_date="2026-12-31",
    )

    paths = result["paths"]
    assert Path(paths["diagnostics"]).name == "dragon_strategy_v1_3_diagnostics.csv"
    assert Path(paths["low_quality_split_audit"]).exists()
    assert Path(paths["entry_score_bucket_effectiveness"]).exists()
    assert Path(paths["follower_penalty_audit"]).exists()
    report = Path(paths["markdown_report"]).read_text()
    assert "# Dragon Strategy Research v1.3 低拥挤机会与买点重构报告" in report
    assert "dragon_entry_score_v2" in report


def test_dragon_research_v1_cli_prints_outputs(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["start_date"] == "2024-05-27"
        assert kwargs["end_date"] == "2026-05-12"
        return {
            "paths": {
                "diagnostics": "/tmp/dragon_strategy_v1_diagnostics.csv",
                "monthly_summary": "/tmp/dragon_strategy_v1_monthly_summary.csv",
                "role_effectiveness": "/tmp/dragon_strategy_v1_role_effectiveness.csv",
                "yearly_diagnosis": "/tmp/dragon_strategy_v1_yearly_diagnosis.csv",
                "markdown_report": "/tmp/dragon_strategy_v1_report.md",
            },
            "diagnostics": [1, 2],
            "role_effectiveness": [1],
            "yearly_diagnosis": [1],
        }

    monkeypatch.setattr(cli, "run_dragon_research_v1", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "dragon-research-v1",
            "--start-date",
            "2024-05-27",
            "--end-date",
            "2026-05-12",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "dragon_research_v1|diagnostics|/tmp/dragon_strategy_v1_diagnostics.csv" in out
    assert "dragon_research_v1|report|/tmp/dragon_strategy_v1_report.md" in out
    assert "dragon_research_v1|diagnostic_rows|2" in out


def _sample_feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "LEADER",
                "stock_name": "Leader",
                "close": 13.0,
                "stock_return_3d": 0.07,
                "stock_return_5d": 0.10,
                "stock_return_10d": 0.15,
                "stock_return_20d": 0.24,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": 0.06,
                "stock_excess_return_vs_industry_20d": 0.14,
                "amount": 300_000_000,
                "turnover_rate": 8.0,
                "amount_vs_20d": 1.8,
                "new_high_20d": True,
                "new_high_60d": True,
                "outperform_industry_days_5": 4,
                "return_rank_pct_in_industry": 1.0,
                "amount_rank_pct_in_industry": 0.95,
                "trend_lifecycle_stage": "breakout",
            },
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "CORE",
                "stock_name": "Core",
                "close": 11.0,
                "stock_return_3d": 0.03,
                "stock_return_5d": 0.05,
                "stock_return_10d": 0.08,
                "stock_return_20d": 0.12,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": 0.01,
                "stock_excess_return_vs_industry_20d": 0.02,
                "amount": 420_000_000,
                "turnover_rate": 4.0,
                "amount_vs_20d": 1.2,
                "new_high_20d": True,
                "new_high_60d": False,
                "outperform_industry_days_5": 3,
                "return_rank_pct_in_industry": 0.78,
                "amount_rank_pct_in_industry": 1.0,
                "trend_lifecycle_stage": "warming_up",
            },
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "EARLY",
                "stock_name": "Early",
                "close": 10.5,
                "stock_return_3d": 0.035,
                "stock_return_5d": 0.045,
                "stock_return_10d": 0.055,
                "stock_return_20d": 0.065,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": 0.005,
                "stock_excess_return_vs_industry_20d": -0.035,
                "amount": 100_000_000,
                "turnover_rate": 3.5,
                "amount_vs_20d": 1.15,
                "new_high_20d": True,
                "new_high_60d": False,
                "outperform_industry_days_5": 3,
                "return_rank_pct_in_industry": 0.72,
                "amount_rank_pct_in_industry": 0.55,
                "trend_lifecycle_stage": "warming_up",
            },
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "HOT",
                "stock_name": "Hot",
                "close": 20.0,
                "stock_return_3d": 0.20,
                "stock_return_5d": 0.36,
                "stock_return_10d": 0.55,
                "stock_return_20d": 0.90,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": 0.32,
                "stock_excess_return_vs_industry_20d": 0.80,
                "amount": 500_000_000,
                "turnover_rate": 28.0,
                "amount_vs_20d": 5.0,
                "new_high_20d": True,
                "new_high_60d": True,
                "outperform_industry_days_5": 5,
                "return_rank_pct_in_industry": 0.98,
                "amount_rank_pct_in_industry": 0.98,
                "trend_lifecycle_stage": "acceleration",
            },
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "CATCH",
                "stock_name": "Catch",
                "close": 10.0,
                "stock_return_3d": 0.06,
                "stock_return_5d": 0.08,
                "stock_return_10d": 0.04,
                "stock_return_20d": -0.02,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": 0.04,
                "stock_excess_return_vs_industry_20d": -0.12,
                "amount": 150_000_000,
                "turnover_rate": 5.0,
                "amount_vs_20d": 1.4,
                "new_high_20d": False,
                "new_high_60d": False,
                "outperform_industry_days_5": 3,
                "return_rank_pct_in_industry": 0.62,
                "amount_rank_pct_in_industry": 0.60,
                "trend_lifecycle_stage": "warming_up",
            },
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "FOLLOW",
                "stock_name": "Follow",
                "close": 9.0,
                "stock_return_3d": 0.01,
                "stock_return_5d": 0.02,
                "stock_return_10d": 0.03,
                "stock_return_20d": 0.04,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": -0.02,
                "stock_excess_return_vs_industry_20d": -0.06,
                "amount": 120_000_000,
                "turnover_rate": 3.0,
                "amount_vs_20d": 1.1,
                "new_high_20d": False,
                "new_high_60d": False,
                "outperform_industry_days_5": 1,
                "return_rank_pct_in_industry": 0.42,
                "amount_rank_pct_in_industry": 0.45,
                "trend_lifecycle_stage": "warming_up",
            },
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "COOL",
                "stock_name": "Cool",
                "close": 8.0,
                "stock_return_3d": -0.04,
                "stock_return_5d": -0.06,
                "stock_return_10d": -0.08,
                "stock_return_20d": 0.02,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": -0.10,
                "stock_excess_return_vs_industry_20d": -0.08,
                "amount": 160_000_000,
                "turnover_rate": 5.0,
                "amount_vs_20d": 0.8,
                "new_high_20d": False,
                "new_high_60d": False,
                "outperform_industry_days_5": 0,
                "return_rank_pct_in_industry": 0.25,
                "amount_rank_pct_in_industry": 0.50,
                "trend_lifecycle_stage": "cooling_down",
            },
            {
                "trade_date": "2024-01-26",
                "industry_name": "Tech",
                "industry_heat_score": 0.95,
                "industry_focus_score_v2": 0.95,
                "industry_rank": 1,
                "asset_id": "WEAK",
                "stock_name": "Weak",
                "close": 6.0,
                "stock_return_3d": -0.01,
                "stock_return_5d": -0.02,
                "stock_return_10d": -0.01,
                "stock_return_20d": 0.00,
                "industry_return_5d": 0.04,
                "industry_return_20d": 0.10,
                "market_return_5d": 0.01,
                "market_return_20d": 0.03,
                "stock_excess_return_vs_industry_5d": -0.06,
                "stock_excess_return_vs_industry_20d": -0.10,
                "amount": 10_000_000,
                "turnover_rate": 0.5,
                "amount_vs_20d": 0.6,
                "new_high_20d": False,
                "new_high_60d": False,
                "outperform_industry_days_5": 1,
                "return_rank_pct_in_industry": 0.10,
                "amount_rank_pct_in_industry": 0.10,
                "trend_lifecycle_stage": "unknown",
            },
        ]
    )


def _scored_diagnostics_with_future() -> pd.DataFrame:
    frame = _sample_feature_frame()
    scored = assign_dragon_roles(compute_dragon_scores(frame))
    return scored.assign(
        future_1d_return=[0.01, 0.00, -0.02, 0.02, 0.03, -0.01, -0.03, 0.00],
        future_3d_return=[0.02, 0.01, -0.04, 0.03, 0.04, -0.01, -0.04, 0.00],
        future_5d_return=[0.03, 0.01, -0.08, 0.04, 0.05, -0.02, -0.05, 0.00],
        future_10d_return=[0.05, 0.02, -0.10, 0.03, 0.08, -0.01, -0.06, 0.01],
        future_20d_return=[0.08, 0.03, -0.12, 0.06, 0.12, -0.02, -0.08, 0.02],
        future_10d_max_drawdown=[-0.03, -0.04, -0.15, -0.05, -0.04, -0.03, -0.08, -0.02],
        future_20d_max_drawdown=[-0.05, -0.06, -0.20, -0.08, -0.06, -0.05, -0.12, -0.04],
    )


def _sample_bars() -> pd.DataFrame:
    rows = []
    dates = pd.bdate_range("2024-01-01", periods=30)
    for asset_id, base, step in [("LEADER", 10.0, 0.15), ("FOLLOW", 10.0, 0.03)]:
        for index, date in enumerate(dates):
            close = base + step * index
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": date.strftime("%Y-%m-%d"),
                    "open": close - 0.05,
                    "high": close + 0.1,
                    "low": close - 0.1,
                    "close": close,
                    "amount": 100_000_000 + index * 1_000_000,
                    "turnover_rate": 3.0,
                    "trade_status": "1",
                    "is_st": False,
                }
            )
    return pd.DataFrame(rows)
