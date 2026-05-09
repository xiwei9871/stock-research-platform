from pathlib import Path

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
