from pathlib import Path

import pandas as pd

from stock_research.reports.risk_alert_report import (
    generate_risk_alerts,
    write_risk_alert_report,
)


def test_generate_risk_alerts_flags_market_and_candidate_risks():
    alerts = generate_risk_alerts(
        trade_date="2026-05-08",
        top_scores=[
            {
                "rank": 1,
                "asset_id": "A",
                "score_total": 88.0,
                "industry_code": "TECH",
            }
        ],
        market_state={"market_state": "defensive", "risk_level": "high"},
        sector_strength=pd.DataFrame(
            [
                {
                    "industry_code": "TECH",
                    "industry_name": "Technology",
                    "strength_rank": 32,
                    "strength_score": 42.0,
                }
            ]
        ),
        feature_snapshot=pd.DataFrame(
            [
                {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.22},
                {"asset_id": "A", "feature_name": "volatility_20d", "feature_value": 0.06},
                {"asset_id": "A", "feature_name": "max_drawdown_20d", "feature_value": -0.18},
                {"asset_id": "A", "feature_name": "amount_20d_avg", "feature_value": 20_000_000.0},
            ]
        ),
    )

    assert list(alerts["alert_type"]) == [
        "market_defensive",
        "sector_weak",
        "candidate_overheat",
        "candidate_high_volatility",
        "candidate_deep_drawdown",
        "candidate_low_liquidity",
    ]
    assert alerts.iloc[0]["scope"] == "market"
    assert alerts.iloc[0]["severity"] == "high"
    assert alerts[alerts["alert_type"] == "candidate_low_liquidity"].iloc[0]["asset_id"] == "A"


def test_write_risk_alert_report_outputs_markdown_and_csv(tmp_path):
    alerts = generate_risk_alerts(
        trade_date="2026-05-08",
        top_scores=[{"rank": 1, "asset_id": "A", "score_total": 88.0}],
        market_state={"market_state": "defensive", "risk_level": "high"},
        feature_snapshot=pd.DataFrame(
            [{"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.22}]
        ),
    )

    paths = write_risk_alert_report(
        alerts,
        trade_date="2026-05-08",
        output_dir=tmp_path,
    )

    markdown_path = tmp_path / "risk_alerts_2026-05-08.md"
    csv_path = tmp_path / "risk_alerts_2026-05-08.csv"
    assert paths == {"markdown_path": markdown_path, "csv_path": csv_path}
    assert markdown_path.exists()
    assert csv_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# 2026-05-08 Risk Alerts" in markdown
    assert "风险提示只作为研究过滤器，不构成交易指令。" in markdown
    assert "candidate_overheat" in markdown
    csv = pd.read_csv(csv_path)
    assert "alert_type" in csv.columns
