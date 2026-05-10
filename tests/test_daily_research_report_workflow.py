import pandas as pd

from stock_research.reports.daily_research_report_workflow import write_daily_research_reports


def test_write_daily_research_reports_writes_all_daily_reports(tmp_path):
    result = write_daily_research_reports(
        trade_date="2026-05-08",
        score_version="manual_v1",
        top_scores=[
            {
                "rank": 1,
                "asset_id": "A",
                "score_total": 88.0,
                "score_components": {"ret_20": 90.0},
                "industry_code": "TECH",
            }
        ],
        market_state={
            "trade_date": "2026-05-08",
            "index_id": "CSI300",
            "close": 4000.0,
            "ret_5d": 0.02,
            "ret_20d": 0.05,
            "ret_60d": 0.08,
            "ma20": 3900.0,
            "ma60": 3800.0,
            "drawdown_20d": -0.01,
            "amount_ratio_5_20": 1.1,
            "market_state": "bullish",
            "risk_level": "low",
            "entry_allowed": True,
        },
        sector_strength=pd.DataFrame(
            [
                {
                    "trade_date": "2026-05-08",
                    "industry_system": "csrc",
                    "industry_code": "TECH",
                    "industry_name": "Technology",
                    "ret_5d": 0.03,
                    "ret_20d": 0.08,
                    "amount_ratio_5_20": 1.2,
                    "strength_score": 88.0,
                    "strength_rank": 1,
                }
            ]
        ),
        positions=[{"asset_id": "A", "weight": 0.1, "holding_days": 5}],
        feature_snapshot=pd.DataFrame(
            [{"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.22}]
        ),
        output_dir=tmp_path,
    )

    expected_keys = {
        "topn",
        "market_state",
        "sector_strength",
        "risk_alerts",
        "position_review",
        "bundle",
    }
    assert set(result["report_paths"]) == expected_keys
    for paths in result["report_paths"].values():
        assert paths["markdown_path"].exists()
    assert result["risk_alerts"].iloc[0]["alert_type"] == "candidate_overheat"
    assert result["position_review"].iloc[0]["review_status"] == "review"
