from pathlib import Path

import pandas as pd

from stock_research.reports.daily_topn_report import write_daily_topn_report


def test_write_daily_topn_report_writes_markdown_and_csv(tmp_path):
    result = write_daily_topn_report(
        trade_date="2026-05-08",
        score_version="manual_v1",
        top_scores=[
            {"rank": 1, "asset_id": "A", "score_total": 88.5},
            {"rank": 2, "asset_id": "B", "score_total": 80.0},
        ],
        output_dir=tmp_path,
    )

    markdown_path = Path(result["markdown_path"])
    csv_path = Path(result["csv_path"])
    assert markdown_path.exists()
    assert csv_path.exists()
    assert "2026-05-08 TopN" in markdown_path.read_text(encoding="utf-8")
    assert "A" in csv_path.read_text(encoding="utf-8")


def test_write_daily_topn_report_formats_score_components_and_guardrail(tmp_path):
    result = write_daily_topn_report(
        trade_date="2026-05-08",
        score_version="manual_v1",
        top_scores=[
            {
                "rank": 1,
                "asset_id": "A",
                "score_total": 88.5123,
                "score_components": {
                    "momentum_20d": 93.2,
                    "risk_volatility_20d": 41.7,
                },
            },
        ],
        output_dir=tmp_path,
    )

    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert "TopN 只是候选股票池，不是买入信号。" in markdown
    assert "| Rank | Asset | Score | Components |" in markdown
    assert "momentum_20d=93.20" in markdown
    csv = pd.read_csv(result["csv_path"])
    assert list(csv.columns) == [
        "rank",
        "asset_id",
        "score_total",
        "score_version",
        "score_components",
    ]
    assert '"momentum_20d": 93.2' in csv.iloc[0]["score_components"]
