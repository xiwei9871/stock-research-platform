from pathlib import Path

import pandas as pd

from stock_research import industry_factor_audit


def _diagnostics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rebalance_month": "2026-01",
                "rebalance_date": "2026-01-02",
                "industry_name": "过热弱行业",
                "selected_by_v1_topk": True,
                "selected_by_v1_lagged_exit": False,
                "selected_by_v2_topk": True,
                "industry_focus_score_v2": 0.8,
                "v1_score": 0.9,
                "future_20d_return": -0.05,
                "future_20d_rank": 30,
                "future_20d_excess_return": -0.08,
                "future_20d_max_drawdown": -0.20,
                "diagnosis_tag": "overheat",
                "trend_persistence_score": 0.9,
                "amount_share_score": 0.9,
                "candidate_density_score": 0.8,
                "breadth_expansion_score": 0.7,
                "leader_to_middle_expansion_score": 0.2,
                "overheat_penalty": 0.9,
                "concentration_penalty": 0.1,
            },
            {
                "rebalance_month": "2026-01",
                "rebalance_date": "2026-01-02",
                "industry_name": "未来强行业",
                "selected_by_v1_topk": False,
                "selected_by_v1_lagged_exit": False,
                "selected_by_v2_topk": False,
                "industry_focus_score_v2": 0.2,
                "v1_score": 0.1,
                "future_20d_return": 0.12,
                "future_20d_rank": 2,
                "future_20d_excess_return": 0.09,
                "future_20d_max_drawdown": -0.03,
                "diagnosis_tag": "broad_strength",
                "trend_persistence_score": 0.2,
                "amount_share_score": 0.3,
                "candidate_density_score": 0.2,
                "breadth_expansion_score": 0.9,
                "leader_to_middle_expansion_score": 0.8,
                "overheat_penalty": 0.1,
                "concentration_penalty": 0.0,
            },
            {
                "rebalance_month": "2026-01",
                "rebalance_date": "2026-01-03",
                "industry_name": "窄龙头陷阱",
                "selected_by_v1_topk": True,
                "selected_by_v1_lagged_exit": True,
                "selected_by_v2_topk": False,
                "industry_focus_score_v2": 0.4,
                "v1_score": 0.8,
                "future_20d_return": -0.02,
                "future_20d_rank": 25,
                "future_20d_excess_return": -0.04,
                "future_20d_max_drawdown": -0.18,
                "diagnosis_tag": "narrow_leader_only",
                "trend_persistence_score": 0.5,
                "amount_share_score": 0.5,
                "candidate_density_score": 0.7,
                "breadth_expansion_score": 0.2,
                "leader_to_middle_expansion_score": 0.1,
                "overheat_penalty": 0.2,
                "concentration_penalty": 0.8,
            },
        ]
    )


def test_classify_error_types_marks_selected_weak_missed_and_traps():
    audited = industry_factor_audit.build_error_audit_monthly(_diagnostics())
    by_industry = audited.groupby("industry_name")["error_type"].apply(set).to_dict()

    assert "selected_weak_future_return" in by_industry["过热弱行业"]
    assert "chasing_after_overheat" in by_industry["过热弱行业"]
    assert "missed_strong_industry" in by_industry["未来强行业"]
    assert "narrow_leader_trap" in by_industry["窄龙头陷阱"]


def test_diagnosis_tag_effectiveness_groups_future_performance():
    effectiveness = industry_factor_audit.build_diagnosis_tag_effectiveness(_diagnostics())
    overheat = effectiveness[effectiveness["diagnosis_tag"] == "overheat"].iloc[0]
    broad = effectiveness[effectiveness["diagnosis_tag"] == "broad_strength"].iloc[0]

    assert overheat["sample_count"] == 1
    assert overheat["avg_future_20d_return"] == -0.05
    assert broad["win_rate_vs_market"] == 1.0
    assert overheat["selected_by_v1_topk_count"] == 1


def test_component_effectiveness_builds_quantile_buckets_and_signal_quality():
    rows = []
    for idx in range(10):
        rows.append(
            {
                "rebalance_date": f"2026-01-{idx + 1:02d}",
                "industry_name": f"I{idx}",
                "trend_persistence_score": idx / 9,
                "overheat_penalty": idx / 9,
                "future_20d_return": idx / 100,
                "future_20d_excess_return": idx / 100 - 0.03,
                "future_20d_rank": 10 - idx,
                "future_20d_max_drawdown": -0.01 * idx,
            }
        )
    effectiveness = industry_factor_audit.build_component_effectiveness(pd.DataFrame(rows), buckets=5)

    trend = effectiveness[effectiveness["component_name"] == "trend_persistence_score"]
    overheat = effectiveness[effectiveness["component_name"] == "overheat_penalty"]
    assert set(trend["quantile_bucket"]) == {1, 2, 3, 4, 5}
    assert trend["signal_quality"].iloc[0] == "useful_signal"
    assert overheat["signal_quality"].iloc[0] == "inverted_signal"


def test_markdown_report_can_be_generated(tmp_path: Path):
    paths = industry_factor_audit.write_industry_factor_audit_report(
        output_dir=tmp_path,
        backtest_summary=pd.DataFrame(
            [{"variant": "base_top20", "cumulative_return": -0.01, "max_drawdown": -0.2}]
        ),
        reconciliation=pd.DataFrame(
            [{"notes": "new_membership_logic: one industry per asset-date"}]
        ),
        error_summary=pd.DataFrame(
            [{"error_type": "selected_weak_future_return", "event_count": 3}]
        ),
        tag_effectiveness=pd.DataFrame(
            [{"diagnosis_tag": "overheat", "sample_count": 10, "avg_future_20d_return": -0.02}]
        ),
        component_effectiveness=pd.DataFrame(
            [{"component_name": "trend_persistence_score", "signal_quality": "useful_signal"}]
        ),
        yearly_diagnosis=pd.DataFrame(
            [{"year": "2026", "variant": "base_top20", "period_return": 0.1}]
        ),
    )

    report = Path(paths["markdown_report"])
    assert report.exists()
    assert "行业因子失败归因审计报告" in report.read_text(encoding="utf-8")
