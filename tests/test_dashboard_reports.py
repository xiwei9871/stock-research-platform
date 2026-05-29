from pathlib import Path

from stock_research.dashboard.reports import load_report_links


def test_load_report_links_finds_trade_date_files(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "daily_topn_2026-05-29_manual_v1.md").write_text("# topn", encoding="utf-8")
    (reports_dir / "watchlist_report_2026-05-29.md").write_text("# watchlist", encoding="utf-8")
    (reports_dir / "old_2026-05-28.md").write_text("# old", encoding="utf-8")

    result = load_report_links("2026-05-29", reports_dirs=[reports_dir])

    paths = [row["path"] for row in result]
    assert str(reports_dir / "daily_topn_2026-05-29_manual_v1.md") in paths
    assert str(reports_dir / "watchlist_report_2026-05-29.md") in paths
    assert str(reports_dir / "old_2026-05-28.md") not in paths
