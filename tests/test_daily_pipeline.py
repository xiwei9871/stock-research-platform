from stock_research import daily_pipeline


def test_run_daily_factor_pipeline_runs_build_score_topn_and_report(monkeypatch):
    calls = []

    monkeypatch.setattr(
        daily_pipeline,
        "build_and_store_factor_daily",
        lambda **kwargs: calls.append("build") or 100,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append("score") or 20,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-08", "asset_id": "A", "rank": 1, "score_total": 88.5}],
    )
    monkeypatch.setattr(
        daily_pipeline,
        "write_daily_topn_report",
        lambda **kwargs: {"markdown_path": "/tmp/report.md", "csv_path": "/tmp/report.csv"},
    )

    result = daily_pipeline.run_daily_factor_pipeline("2026-05-08", top_n=10)

    assert calls == ["build", "score"]
    assert result["factor_rows"] == 100
    assert result["score_rows"] == 20
    assert result["top_scores"][0]["asset_id"] == "A"
    assert result["report_paths"]["markdown_path"] == "/tmp/report.md"
