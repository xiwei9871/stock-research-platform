from pathlib import Path

import pandas as pd
import pytest

from stock_research import industry_mainline_regime


def _diagnostics() -> pd.DataFrame:
    rows = []
    for trade_date, specs in {
        "2026-01-01": [
            ("持续扩散行业", 0.90, 0.08, 0.07, 0.30, 0.25, 0.55, 0.70, 0.65, 0.20, 0.10, 0.08, 0.05),
            ("过热行业", 0.62, 0.15, 0.12, 0.45, 0.10, 0.30, 0.35, 0.30, 0.88, 0.20, -0.04, -0.05),
            ("弱行业", 0.20, -0.02, -0.03, 0.05, 0.04, 0.10, 0.20, 0.15, 0.10, 0.40, -0.03, -0.02),
        ],
        "2026-01-02": [
            ("行业A", 0.52, 0.03, 0.02, 0.08, 0.05, 0.15, 0.45, 0.40, 0.30, 0.25, 0.01, -0.01),
            ("行业B", 0.50, 0.02, 0.01, 0.07, 0.05, 0.14, 0.44, 0.39, 0.25, 0.25, 0.02, 0.00),
            ("行业C", 0.48, 0.01, 0.00, 0.06, 0.05, 0.13, 0.43, 0.38, 0.20, 0.25, -0.01, -0.02),
        ],
        "2026-01-03": [
            ("普弱A", 0.20, -0.05, -0.04, 0.03, 0.02, 0.08, 0.20, 0.18, 0.15, 0.20, -0.02, -0.01),
            ("普弱B", 0.18, -0.04, -0.03, 0.02, 0.02, 0.07, 0.22, 0.20, 0.10, 0.20, -0.01, 0.00),
        ],
    }.items():
        for name, v2, ret20, excess20, amount_chg, top20, top50, breadth, excess_breadth, overheat, concentration, future, future_excess in specs:
            rows.append(
                {
                    "rebalance_date": trade_date,
                    "rebalance_month": trade_date[:7],
                    "industry_name": name,
                    "industry_focus_score_v2": v2,
                    "industry_ret_5d": ret20 / 2,
                    "industry_ret_10d": ret20 * 0.75,
                    "industry_ret_20d": ret20,
                    "industry_excess_ret_5d": excess20 / 2,
                    "industry_excess_ret_10d": excess20 * 0.75,
                    "industry_excess_ret_20d": excess20,
                    "industry_amount_share_change_5d_vs_20d": amount_chg,
                    "industry_amount_share_5d": 0.10 + amount_chg / 10,
                    "industry_amount_share_20d": 0.10,
                    "top20_density": top20,
                    "top50_density": top50,
                    "top100_density": max(top50, top20),
                    "breadth_expansion_score": breadth,
                    "up_ratio_20d": breadth,
                    "excess_up_ratio_20d": excess_breadth,
                    "leader_to_middle_expansion_score": breadth,
                    "overheat_penalty": overheat,
                    "concentration_penalty": concentration,
                    "future_20d_return": future,
                    "future_20d_excess_return": future_excess,
                    "future_20d_rank": 1 if future_excess > 0 else 20,
                    "future_20d_max_drawdown": -0.03,
                }
            )
    return pd.DataFrame(rows)


def test_classify_market_regime_distinguishes_mainline_rotation_and_weak():
    regimes = industry_mainline_regime.build_market_regime_diagnostics(_diagnostics())

    by_date = regimes.set_index("rebalance_date")["market_regime"].to_dict()
    assert by_date["2026-01-01"] == "mainline"
    assert by_date["2026-01-02"] == "rotation"
    assert by_date["2026-01-03"] == "weak_market"


def test_mainline_score_rewards_persistence_density_and_expansion():
    scored = industry_mainline_regime.build_industry_mainline_scores(_diagnostics())
    strong = scored[scored["industry_name"] == "持续扩散行业"].iloc[0]
    hot = scored[scored["industry_name"] == "过热行业"].iloc[0]

    assert strong["industry_mainline_score_v1"] > hot["industry_mainline_score_v1"]
    assert strong["mainline_tag"] == "sustained_mainline"
    assert hot["mainline_tag"] == "overheated_mainline"


def test_mainline_score_does_not_use_future_columns():
    base = _diagnostics()
    changed_future = base.copy()
    changed_future["future_20d_return"] = -0.99
    changed_future["future_20d_excess_return"] = -0.99
    changed_future["future_20d_rank"] = 99

    score_a = industry_mainline_regime.build_industry_mainline_scores(base)
    score_b = industry_mainline_regime.build_industry_mainline_scores(changed_future)

    assert score_a["industry_mainline_score_v1"].tolist() == pytest.approx(
        score_b["industry_mainline_score_v1"].tolist()
    )
    assert score_a["mainline_tag"].tolist() == score_b["mainline_tag"].tolist()


def test_regime_effectiveness_groups_future_returns_by_regime_and_bucket():
    diagnostics = _diagnostics()
    scored = industry_mainline_regime.build_industry_mainline_scores(diagnostics)
    regimes = industry_mainline_regime.build_market_regime_diagnostics(diagnostics)

    table = industry_mainline_regime.build_regime_effectiveness(scored, regimes, buckets=3)

    assert {
        "market_regime",
        "score_bucket",
        "sample_count",
        "avg_future_20d_excess_return",
    }.issubset(table.columns)
    assert set(table["market_regime"]) >= {"mainline", "rotation", "weak_market"}


def test_markdown_report_can_be_generated(tmp_path: Path):
    diagnostics = _diagnostics()
    scored = industry_mainline_regime.build_industry_mainline_scores(diagnostics)
    regimes = industry_mainline_regime.build_market_regime_diagnostics(diagnostics)
    regime_effectiveness = industry_mainline_regime.build_regime_effectiveness(scored, regimes)
    tag_effectiveness = industry_mainline_regime.build_mainline_tag_effectiveness(scored)

    path = tmp_path / "report.md"
    industry_mainline_regime.write_industry_mainline_report(
        path=path,
        start_date="2026-01-01",
        end_date="2026-01-03",
        regimes=regimes,
        regime_effectiveness=regime_effectiveness,
        tag_effectiveness=tag_effectiveness,
    )

    text = path.read_text(encoding="utf-8")
    assert "行业主线 Regime 诊断报告" in text
