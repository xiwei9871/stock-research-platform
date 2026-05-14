from pathlib import Path

import pandas as pd
import pytest

from stock_research import industry_focus_v2


def test_expand_interval_memberships_uses_only_active_window():
    trade_dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
    asset_dates = pd.DataFrame(
        [
            {"trade_date": date, "asset_id": "A"}
            for date in trade_dates
        ]
    )
    intervals = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "industry_name": "旧行业",
                "start_date": "2025-01-01",
                "end_date": "2026-01-02",
            },
            {
                "asset_id": "A",
                "industry_name": "新行业",
                "start_date": "2026-01-03",
                "end_date": None,
            },
        ]
    )

    expanded = industry_focus_v2.expand_interval_memberships(asset_dates, intervals)

    assert expanded[["trade_date", "asset_id", "industry_name"]].to_dict("records") == [
        {"trade_date": "2026-01-01", "asset_id": "A", "industry_name": "旧行业"},
        {"trade_date": "2026-01-02", "asset_id": "A", "industry_name": "旧行业"},
        {"trade_date": "2026-01-03", "asset_id": "A", "industry_name": "新行业"},
    ]


def test_candidate_density_counts_top20_top50_top100_by_industry():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": f"A{i:03d}", "score_total": 200 - i}
            for i in range(1, 31)
        ]
        + [
            {"trade_date": "2026-01-01", "asset_id": f"B{i:03d}", "score_total": 100 - i}
            for i in range(1, 81)
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": f"A{i:03d}", "industry_name": "行业A"}
            for i in range(1, 31)
        ]
        + [
            {"trade_date": "2026-01-01", "asset_id": f"B{i:03d}", "industry_name": "行业B"}
            for i in range(1, 81)
        ]
    )

    density = industry_focus_v2.build_candidate_density(scores, memberships)
    row_a = density[density["industry_name"] == "行业A"].iloc[0]
    row_b = density[density["industry_name"] == "行业B"].iloc[0]

    assert row_a["industry_member_count"] == 30
    assert row_a["top20_stock_count"] == 20
    assert row_a["top50_stock_count"] == 30
    assert row_a["top100_stock_count"] == 30
    assert row_a["top20_density"] == pytest.approx(20 / 30)
    assert row_b["top20_stock_count"] == 0
    assert row_b["top50_stock_count"] == 20
    assert row_b["top100_stock_count"] == 70


def test_overheat_penalty_rises_on_short_term_surge_and_amount_spike():
    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "industry_name": "冷静行业",
                "industry_ret_5d": 0.01,
                "industry_amount_share_change_5d_vs_20d": 0.02,
                "industry_amount_share_5d_percentile_60d": 0.50,
                "industry_distance_ma20": 0.02,
            },
            {
                "trade_date": "2026-01-01",
                "industry_name": "过热行业",
                "industry_ret_5d": 0.18,
                "industry_amount_share_change_5d_vs_20d": 0.40,
                "industry_amount_share_5d_percentile_60d": 0.98,
                "industry_distance_ma20": 0.16,
            },
        ]
    )

    scored = industry_focus_v2.add_overheat_penalty(frame)

    cool = scored[scored["industry_name"] == "冷静行业"]["overheat_penalty"].iloc[0]
    hot = scored[scored["industry_name"] == "过热行业"]["overheat_penalty"].iloc[0]
    assert hot > cool
    assert hot > 0.5


def test_concentration_penalty_detects_top3_dominated_returns():
    concentrated = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "industry_name": "集中行业", "asset_id": f"A{i}", "ret_20d": 0.30}
            for i in range(1, 4)
        ]
        + [
            {"trade_date": "2026-01-01", "industry_name": "集中行业", "asset_id": f"A{i}", "ret_20d": 0.01}
            for i in range(4, 21)
        ]
        + [
            {"trade_date": "2026-01-01", "industry_name": "扩散行业", "asset_id": f"B{i}", "ret_20d": 0.10}
            for i in range(1, 21)
        ]
    )

    penalty = industry_focus_v2.build_return_concentration(concentrated)
    concentrated_row = penalty[penalty["industry_name"] == "集中行业"].iloc[0]
    broad_row = penalty[penalty["industry_name"] == "扩散行业"].iloc[0]

    assert concentrated_row["industry_return_concentration_top3"] > broad_row[
        "industry_return_concentration_top3"
    ]
    assert concentrated_row["concentration_penalty"] > broad_row["concentration_penalty"]


def test_v2_score_does_not_use_future_return():
    base = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "industry_name": "行业A",
                "industry_ret_5d": 0.03,
                "industry_ret_10d": 0.05,
                "industry_ret_20d": 0.08,
                "industry_excess_ret_5d": 0.02,
                "industry_excess_ret_10d": 0.03,
                "industry_excess_ret_20d": 0.04,
                "top_rank_days_20d": 10,
                "industry_amount_share_5d": 0.10,
                "industry_amount_share_20d": 0.08,
                "industry_amount_share_change_5d_vs_20d": 0.25,
                "industry_amount_share_5d_percentile_60d": 0.80,
                "top20_density": 0.30,
                "top50_density": 0.25,
                "top100_density": 0.20,
                "up_ratio_20d": 0.70,
                "excess_up_ratio_20d": 0.60,
                "top100_stock_count": 15,
                "leader_to_middle_ratio": 1.20,
                "middle_ret_20d": 0.06,
                "industry_volatility_20d": 0.02,
                "industry_forward_20d_return": 0.50,
                "industry_forward_20d_excess_return": 0.40,
            }
        ]
    )
    changed_future = base.copy()
    changed_future["industry_forward_20d_return"] = -0.50
    changed_future["industry_forward_20d_excess_return"] = -0.60

    score_a = industry_focus_v2.build_industry_focus_score_v2(base)
    score_b = industry_focus_v2.build_industry_focus_score_v2(changed_future)

    assert score_a["industry_focus_score_v2"].iloc[0] == pytest.approx(
        score_b["industry_focus_score_v2"].iloc[0]
    )


def test_run_v2_diagnostics_writes_expected_files(tmp_path: Path, monkeypatch):
    def fake_inputs(**kwargs):
        dates = ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]
        prices = pd.DataFrame(
            [
                {"trade_date": date, "asset_id": "A", "close": 10 + idx, "amount": 1000 + idx * 100}
                for idx, date in enumerate(dates)
            ]
            + [
                {"trade_date": date, "asset_id": "B", "close": 20 - idx, "amount": 800 - idx * 20}
                for idx, date in enumerate(dates)
            ]
        )
        memberships = pd.DataFrame(
            [
                {"trade_date": date, "asset_id": "A", "industry_name": "强行业"}
                for date in dates
            ]
            + [
                {"trade_date": date, "asset_id": "B", "industry_name": "弱行业"}
                for date in dates
            ]
        )
        stock_scores = pd.DataFrame(
            [
                {"trade_date": date, "asset_id": "A", "score_total": 90, "rank": 1}
                for date in dates
            ]
            + [
                {"trade_date": date, "asset_id": "B", "score_total": 50, "rank": 2}
                for date in dates
            ]
        )
        return prices, memberships, stock_scores

    monkeypatch.setattr(industry_focus_v2, "load_research_inputs", fake_inputs)

    result = industry_focus_v2.run_industry_focus_v2_diagnostics(
        start_date="2026-01-01",
        end_date="2026-01-06",
        min_industry_stocks=1,
        output_dir=tmp_path,
        short_window=1,
        medium_window=2,
        long_window=3,
        forward_window=1,
    )

    assert Path(result["paths"]["v1_failure_attribution"]).exists()
    assert Path(result["paths"]["v2_diagnostics"]).exists()
    assert {"industry_focus_score_v2", "diagnosis_tag"}.issubset(result["v2_diagnostics"].columns)
