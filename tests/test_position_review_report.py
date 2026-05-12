from pathlib import Path

import pandas as pd

from stock_research.reports.position_review_report import (
    calc_position_risk_summary,
    generate_position_review,
    write_position_review_report,
)


def test_generate_position_review_combines_rank_market_and_risks():
    review = generate_position_review(
        trade_date="2026-05-08",
        positions=[
            {"asset_id": "A", "weight": 0.1, "holding_days": 12},
            {"asset_id": "B", "weight": 0.2, "holding_days": 3},
        ],
        top_scores=[
            {"asset_id": "A", "rank": 8, "score_total": 82.0, "industry_code": "TECH"},
            {"asset_id": "B", "rank": 45, "score_total": 55.0, "industry_code": "TECH"},
        ],
        market_state={"market_state": "defensive", "risk_level": "high"},
        risk_alerts=pd.DataFrame(
            [
                {
                    "asset_id": "B",
                    "alert_type": "candidate_deep_drawdown",
                    "severity": "high",
                    "message": "20-day drawdown is deep.",
                }
            ]
        ),
        top_n=30,
    )

    assert list(review["asset_id"]) == ["A", "B"]
    assert review.iloc[0]["review_status"] == "monitor"
    assert review.iloc[0]["industry_code"] == "TECH"
    assert "market_defensive" in review.iloc[0]["review_reasons"]
    assert review.iloc[1]["review_status"] == "blocked"
    assert "out_of_top_n" in review.iloc[1]["review_reasons"]
    assert "candidate_deep_drawdown" in review.iloc[1]["risk_alerts"]


def test_calc_position_risk_summary_flags_weight_and_industry_concentration():
    review = generate_position_review(
        trade_date="2026-05-08",
        positions=[
            {"asset_id": "A", "weight": 0.35, "holding_days": 12},
            {"asset_id": "B", "weight": 0.25, "holding_days": 3},
            {"asset_id": "C", "weight": 0.45, "holding_days": 2},
        ],
        top_scores=[
            {"asset_id": "A", "rank": 8, "score_total": 82.0, "industry_code": "TECH"},
            {"asset_id": "B", "rank": 9, "score_total": 81.0, "industry_code": "TECH"},
            {"asset_id": "C", "rank": 10, "score_total": 80.0, "industry_code": "BANK"},
        ],
    )

    summary = calc_position_risk_summary(
        review,
        max_total_weight=1.0,
        max_industry_weight=0.4,
    )

    assert summary["total_weight"] == 1.05
    assert summary["max_industry_code"] == "TECH"
    assert summary["max_industry_weight"] == 0.6
    assert summary["total_weight_status"] == "over_limit"
    assert summary["industry_concentration_status"] == "over_limit"


def test_write_position_review_report_outputs_markdown_and_csv(tmp_path):
    review = generate_position_review(
        trade_date="2026-05-08",
        positions=[{"asset_id": "A", "weight": 0.1, "holding_days": 12}],
        top_scores=[{"asset_id": "A", "rank": 8, "score_total": 82.0}],
        market_state={"market_state": "bullish", "risk_level": "low"},
        risk_alerts=pd.DataFrame(),
        top_n=30,
    )

    paths = write_position_review_report(
        review,
        trade_date="2026-05-08",
        output_dir=tmp_path,
    )

    markdown_path = tmp_path / "position_review_2026-05-08.md"
    csv_path = tmp_path / "position_review_2026-05-08.csv"
    assert paths == {"markdown_path": markdown_path, "csv_path": csv_path}
    assert markdown_path.exists()
    assert csv_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# 2026-05-08 Position Review" in markdown
    assert "持仓复核只作为人工检查清单，不构成交易指令。" in markdown
    assert "Total weight" in markdown
    assert "A" in markdown
    csv = pd.read_csv(csv_path)
    assert list(csv["asset_id"]) == ["A"]
