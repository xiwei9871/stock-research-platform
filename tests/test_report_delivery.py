from stock_research import report_delivery


def test_collect_artifacts_scans_markdown_json_csv_and_run_card(tmp_path):
    input_dir = tmp_path / "reports"
    run_card_dir = input_dir / "run_card" / "daily"
    evidence_dir = run_card_dir / "evidence"
    evidence_dir.mkdir(parents=True)

    markdown_path = input_dir / "daily_topn_2026-05-20_manual_v1.md"
    csv_path = input_dir / "daily_topn_2026-05-20_manual_v1.csv"
    watchlist_path = input_dir / "watchlist_report_2026-05-20_core.json"
    run_card_path = run_card_dir / "run_card.json"

    markdown_path.write_text(
        "# topn\n",
        encoding="utf-8",
    )
    csv_path.write_text(
        "rank,asset_id\n1,A\n",
        encoding="utf-8",
    )
    watchlist_path.write_text(
        "[]\n",
        encoding="utf-8",
    )
    run_card_path.write_text("{}", encoding="utf-8")
    (evidence_dir / "manifest.json").write_text("{}", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    topn_artifact = next(item for item in artifacts if item.report_type == "topn")
    watchlist_artifact = next(item for item in artifacts if item.report_type == "watchlist")
    run_card_artifact = next(item for item in artifacts if item.report_type == "run_card")
    evidence_artifact = next(
        item for item in artifacts if item.report_type == "evidence_bundle"
    )

    assert topn_artifact.markdown_path == str(markdown_path)
    assert topn_artifact.csv_paths == [str(csv_path)]
    assert watchlist_artifact.json_path == str(watchlist_path)
    assert run_card_artifact.run_card_path == str(run_card_path)
    assert evidence_artifact.evidence_dir == str(evidence_dir)
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


def test_collect_artifacts_warns_for_missing_explicit_dirs(tmp_path):
    missing_report_dir = tmp_path / "missing-report-dir"
    missing_run_card_dir = tmp_path / "missing-run-card-dir"

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[],
        report_dirs=[missing_report_dir],
        run_card_dirs=[missing_run_card_dir],
        artifact_paths=[],
    )

    assert artifacts == []
    assert warnings == [
        f"missing_report_dir:{missing_report_dir}",
        f"missing_run_card_dir:{missing_run_card_dir}",
    ]
