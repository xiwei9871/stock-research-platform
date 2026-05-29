from pathlib import Path

from stock_research.dashboard.reports import _report_type, load_report_links


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


def test_load_report_links_discovers_nested_reports(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    nested_dir = reports_dir / "market_state"
    nested_dir.mkdir(parents=True)
    nested_path = nested_dir / "market_state_2026-05-29.md"
    nested_path.write_text("# Market State\n", encoding="utf-8")

    result = load_report_links("2026-05-29", reports_dirs=[reports_dir])

    assert [row["path"] for row in result] == [str(nested_path)]
    assert result[0]["report_type"] == "daily_market_report"


def test_load_report_links_filters_supported_suffixes_and_keeps_html(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    md_path = reports_dir / "daily_topn_2026-05-29.md"
    html_path = reports_dir / "daily_topn_2026-05-29.html"
    txt_path = reports_dir / "daily_topn_2026-05-29.txt"
    md_path.write_text("# TopN\n", encoding="utf-8")
    html_path.write_text("<h1>TopN</h1>", encoding="utf-8")
    txt_path.write_text("skip", encoding="utf-8")

    result = load_report_links("2026-05-29", reports_dirs=[reports_dir])

    paths = {row["path"] for row in result}
    assert str(md_path) in paths
    assert str(html_path) in paths
    assert str(txt_path) not in paths


def test_load_report_links_requires_exact_date_token(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    exact_path = reports_dir / "risk_alerts_2026-05-29.md"
    leaked_path = reports_dir / "risk_alerts_2026-05-290.md"
    exact_path.write_text("# Risk Alerts\n", encoding="utf-8")
    leaked_path.write_text("# Risk Alerts\n", encoding="utf-8")

    result = load_report_links("2026-05-29", reports_dirs=[reports_dir])

    assert [row["path"] for row in result] == [str(exact_path)]


def test_load_report_links_skips_directories_named_like_reports(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "watchlist_report_2026-05-29.md").mkdir()
    file_path = reports_dir / "watchlist_report_2026-05-29.json"
    file_path.write_text("{}", encoding="utf-8")

    result = load_report_links("2026-05-29", reports_dirs=[reports_dir])

    assert [row["path"] for row in result] == [str(file_path)]


def test_report_type_matches_delivery_taxonomy():
    assert _report_type("risk_alerts_2026-05-29.md") == "risk_alert_report"
    assert _report_type("daily_topn_2026-05-29.md") == "daily_topn_report"
    assert _report_type("market_state_2026-05-29.md") == "daily_market_report"
    assert _report_type("watchlist_report_2026-05-29.md") == "watchlist_report"
    assert _report_type("notes_2026-05-29.md") == "generic_report"
