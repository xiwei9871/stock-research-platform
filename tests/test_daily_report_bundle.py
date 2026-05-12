from pathlib import Path

from stock_research.reports.daily_report_bundle import write_daily_report_bundle


def test_write_daily_report_bundle_outputs_daily_index(tmp_path):
    paths = write_daily_report_bundle(
        trade_date="2026-05-08",
        report_paths={
            "topn": tmp_path / "daily_topn_2026-05-08_manual_v1.md",
            "market_state": tmp_path / "market_state_2026-05-08_CSI300.md",
            "risk_alerts": tmp_path / "risk_alerts_2026-05-08.md",
            "position_review": tmp_path / "position_review_2026-05-08.md",
        },
        output_dir=tmp_path,
    )

    markdown_path = tmp_path / "daily_research_bundle_2026-05-08.md"
    assert paths == {"markdown_path": markdown_path}
    assert markdown_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# 2026-05-08 Daily Research Bundle" in markdown
    assert "TopN" in markdown
    assert "Market State" in markdown
    assert "Risk Alerts" in markdown
    assert "Position Review" in markdown
    assert "研究报告只作为人工复核入口，不构成交易指令。" in markdown


def test_write_daily_report_bundle_marks_missing_report_paths(tmp_path):
    paths = write_daily_report_bundle(
        trade_date="2026-05-08",
        report_paths={"topn": ""},
        output_dir=tmp_path,
    )

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "| TopN | missing |  |" in markdown
