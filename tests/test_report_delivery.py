from stock_research import report_delivery


def test_collect_artifacts_scans_markdown_json_csv_and_run_card(tmp_path):
    input_dir = tmp_path / "reports"
    run_card_dir = input_dir / "run_card" / "daily"
    evidence_dir = run_card_dir / "evidence"
    evidence_dir.mkdir(parents=True)

    (input_dir / "daily_topn_2026-05-20_manual_v1.md").write_text(
        "# topn\n",
        encoding="utf-8",
    )
    (input_dir / "daily_topn_2026-05-20_manual_v1.csv").write_text(
        "rank,asset_id\n1,A\n",
        encoding="utf-8",
    )
    (input_dir / "watchlist_report_2026-05-20_core.json").write_text(
        "[]\n",
        encoding="utf-8",
    )
    (run_card_dir / "run_card.json").write_text("{}", encoding="utf-8")
    (evidence_dir / "manifest.json").write_text("{}", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    artifact_types = {item.report_type for item in artifacts}
    assert "topn" in artifact_types
    assert "watchlist" in artifact_types
    assert "run_card" in artifact_types
    assert warnings == []


def test_collect_artifacts_returns_warning_for_empty_input_dir(tmp_path):
    input_dir = tmp_path / "empty"
    input_dir.mkdir()

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts == []
    assert warnings == [f"no_artifacts_found:{input_dir}"]
