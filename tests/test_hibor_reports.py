from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.hibor_reports import (
    DEFAULT_TOP_BROKERS,
    build_hibor_a_tier_backfill_plan,
    build_hibor_download_queue,
    build_hibor_sources_events_from_pdfs,
    choose_hibor_reports_by_tier,
    download_hibor_report_pdfs,
    extract_hibor_auth_params_from_text,
    filter_hibor_a_tier_reports,
    import_hibor_report_pdfs,
    load_hibor_a_tier_institutions,
    normalize_hibor_broker,
    parse_hibor_search_results,
    parse_hibor_pdf_filename,
    run_hibor_a_tier_backfill,
)


def test_parse_hibor_pdf_filename_extracts_report_metadata():
    meta = parse_hibor_pdf_filename(
        Path("/tmp/20260604-东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期.pdf")
    )

    assert meta["publish_date"] == "2026-06-04"
    assert meta["broker"] == "东吴证券"
    assert meta["stock_name"] == "神马电力"
    assert meta["symbol"] == "603530"
    assert meta["ts_code"] == "603530.SH"
    assert meta["asset_id"] == "CN:SH:603530"
    assert meta["report_title"] == "全球复合外绝缘头部企业，迎来出海高速增长期"


def test_parse_hibor_pdf_filename_extracts_auto_download_metadata():
    meta = parse_hibor_pdf_filename(
        Path("/tmp/东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期-260604.pdf")
    )

    assert meta["publish_date"] == "2026-06-04"
    assert meta["broker"] == "东吴证券"
    assert meta["stock_name"] == "神马电力"
    assert meta["symbol"] == "603530"
    assert meta["ts_code"] == "603530.SH"
    assert meta["report_title"] == "全球复合外绝缘头部企业，迎来出海高速增长期"


def test_load_hibor_a_tier_institutions_normalizes_domestic_and_foreign_aliases():
    rules = load_hibor_a_tier_institutions("config/hibor_a_tier_institutions.csv")

    assert normalize_hibor_broker("东吴证券", rules)["institution_name"] == "东吴证券"
    assert normalize_hibor_broker("Morgan Stanley", rules)["institution_name"] == "摩根士丹利"
    assert normalize_hibor_broker("大摩", rules)["region"] == "foreign"
    assert normalize_hibor_broker("未知证券", rules) is None


def test_build_hibor_a_tier_backfill_plan_outputs_active_asset_tasks(tmp_path: Path):
    assets = pd.DataFrame(
        [
            {"asset_id": "CN:SH:603530", "ts_code": "603530.SH", "stock_name": "神马电力", "symbol": "603530"},
            {"asset_id": "CN:SZ:002484", "ts_code": "002484.SZ", "stock_name": "江海股份", "symbol": "002484"},
        ]
    )

    result = build_hibor_a_tier_backfill_plan(
        assets,
        start_date="2024-10-01",
        end_date="2026-06-04",
        output_dir=tmp_path,
    )

    assert result["tasks"]["task_id"].tolist() == ["hibor_a_tier_603530", "hibor_a_tier_002484"]
    assert list(result["tasks"]["status"]) == ["pending", "pending"]
    assert Path(result["paths"]["tasks"]).exists()


def test_filter_hibor_discovered_reports_keeps_a_tier_window_only():
    rows = pd.DataFrame(
        [
            {"ts_code": "603530.SH", "title": "东吴证券-神马电力-603530-深度报告-260604", "detail_url": "u1"},
            {"ts_code": "603530.SH", "title": "Morgan Stanley-神马电力-603530-Update-250101", "detail_url": "u2"},
            {"ts_code": "603530.SH", "title": "未知证券-神马电力-603530-点评-260101", "detail_url": "u3"},
            {"ts_code": "603530.SH", "title": "东吴证券-神马电力-603530-旧报告-240901", "detail_url": "u4"},
        ]
    )
    rules = load_hibor_a_tier_institutions("config/hibor_a_tier_institutions.csv")

    filtered = filter_hibor_a_tier_reports(rows, rules, start_date="2024-10-01", end_date="2026-06-04")

    assert filtered["detail_url"].tolist() == ["u1", "u2"]
    assert filtered.loc[filtered["detail_url"].eq("u2"), "broker_region"].iloc[0] == "foreign"
    assert filtered.loc[filtered["detail_url"].eq("u2"), "broker"].iloc[0] == "摩根士丹利"


def test_filter_hibor_reports_supports_b_tier_fallback_config():
    rows = pd.DataFrame(
        [
            {"ts_code": "603530.SH", "title": "国金证券-神马电力-603530-跟踪报告-250101", "detail_url": "u1"},
            {"ts_code": "603530.SH", "title": "未知证券-神马电力-603530-点评-250101", "detail_url": "u2"},
        ]
    )
    rules = load_hibor_a_tier_institutions("config/hibor_institutions.csv")

    filtered = filter_hibor_a_tier_reports(rows, rules, start_date="2024-10-01", end_date="2026-06-04")

    assert filtered["detail_url"].tolist() == ["u1"]
    assert filtered.iloc[0]["broker_tier"] == "B"
    assert filtered.iloc[0]["broker"] == "国金证券"


def test_choose_hibor_reports_by_tier_uses_a_first_then_b_fallback():
    rows = pd.DataFrame(
        [
            {"detail_url": "a1", "broker_tier": "A", "title": "东吴证券-神马电力-603530-深度报告-250101"},
            {"detail_url": "b1", "broker_tier": "B", "title": "国金证券-神马电力-603530-跟踪报告-250101"},
        ]
    )

    chosen = choose_hibor_reports_by_tier(rows, fallback_tier="B")

    assert chosen["detail_url"].tolist() == ["a1"]
    assert set(chosen["selected_tier_reason"]) == {"primary_A"}


def test_choose_hibor_reports_by_tier_uses_b_when_a_absent():
    rows = pd.DataFrame(
        [
            {"detail_url": "b1", "broker_tier": "B", "title": "国金证券-神马电力-603530-跟踪报告-250101"},
            {"detail_url": "b2", "broker_tier": "B", "title": "天风证券-神马电力-603530-跟踪报告-250101"},
        ]
    )

    chosen = choose_hibor_reports_by_tier(rows, fallback_tier="B")

    assert chosen["detail_url"].tolist() == ["b1", "b2"]
    assert set(chosen["selected_tier_reason"]) == {"fallback_B"}


def test_run_hibor_a_tier_backfill_skips_done_and_marks_review(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "hibor_a_tier_backfill_tasks.csv"
    tasks = pd.DataFrame(
        [
            {
                "task_id": "hibor_a_tier_done",
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "symbol": "600000",
                "stock_name": "浦发银行",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "done",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            },
            {
                "task_id": "hibor_a_tier_review",
                "asset_id": "CN:SH:603530",
                "ts_code": "603530.SH",
                "symbol": "603530",
                "stock_name": "神马电力",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            },
        ]
    )
    tasks.to_csv(task_path, index=False)

    def fake_get_text(url: str) -> str:
        rows = [
            f'<tr><td><a href="http://sys.hibor.com.cn/center/maibo/maibopdfsys.asp?did={idx}">东吴证券-神马电力-603530-深度报告{idx}-250101</a></td></tr>'
            for idx in range(51)
        ]
        return "\n".join(rows)

    monkeypatch.setattr("stock_research.hibor_reports.load_hibor_auth_params_from_cache", lambda: {"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"})

    result = run_hibor_a_tier_backfill(
        tasks_path=task_path,
        output_dir=tmp_path,
        review_threshold=50,
        text_fetcher=fake_get_text,
        binary_fetcher=lambda url: b"%PDF-1.4\nfake",
        import_pdfs=False,
    )

    refreshed = pd.read_csv(result["paths"]["tasks"], low_memory=False)
    assert refreshed.loc[refreshed["task_id"].eq("hibor_a_tier_done"), "status"].iloc[0] == "done"
    assert refreshed.loc[refreshed["task_id"].eq("hibor_a_tier_review"), "status"].iloc[0] == "needs_review"
    assert Path(result["paths"]["discovered"]).exists()
    assert Path(result["paths"]["downloads"]).exists()


def test_run_hibor_a_tier_backfill_processes_pending_only_by_default(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "hibor_a_tier_backfill_tasks.csv"
    pd.DataFrame(
        [
            {
                "task_id": "hibor_a_tier_old",
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "symbol": "600000",
                "stock_name": "浦发银行",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "download_error",
                "discovered_count": 1,
                "downloaded_count": 0,
                "error_type": "ValueError",
                "error_message": "old failure",
                "started_at": "",
                "finished_at": "",
            },
            {
                "task_id": "hibor_a_tier_new",
                "asset_id": "CN:SH:603530",
                "ts_code": "603530.SH",
                "symbol": "603530",
                "stock_name": "神马电力",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            },
        ]
    ).to_csv(task_path, index=False)
    seen = []

    def fake_get_text(url: str) -> str:
        seen.append(url)
        return ""

    monkeypatch.setattr("stock_research.hibor_reports.load_hibor_auth_params_from_cache", lambda: {"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"})

    result = run_hibor_a_tier_backfill(
        tasks_path=task_path,
        output_dir=tmp_path,
        max_tasks=1,
        text_fetcher=fake_get_text,
        binary_fetcher=lambda url: b"%PDF-1.4\nfake",
        import_pdfs=False,
    )

    assert all("gjz=600000" not in url for url in seen)
    assert any("gjz=603530" in url for url in seen)
    assert result["tasks"].iloc[0]["status"] == "download_error"
    assert result["tasks"].iloc[1]["status"] == "no_qualified_report"


def test_run_hibor_a_tier_backfill_stops_batch_on_hibor_rate_limit(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "hibor_a_tier_backfill_tasks.csv"
    pd.DataFrame(
        [
            {
                "task_id": "hibor_a_tier_603530",
                "asset_id": "CN:SH:603530",
                "ts_code": "603530.SH",
                "symbol": "603530",
                "stock_name": "神马电力",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            },
            {
                "task_id": "hibor_a_tier_002484",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "symbol": "002484",
                "stock_name": "江海股份",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            },
        ]
    ).to_csv(task_path, index=False)

    def fake_get_text(url: str) -> str:
        if "gaojisousuo" in url:
            return '<tr><td><a href="http://sys.hibor.com.cn/center/maibo/maibopdfsys.asp?did=1">东吴证券-神马电力-603530-深度报告-250101</a></td></tr>'
        return "<title>您已达到今日的浏览上限！</title>"

    monkeypatch.setattr("stock_research.hibor_reports.load_hibor_auth_params_from_cache", lambda: {"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"})

    result = run_hibor_a_tier_backfill(
        tasks_path=task_path,
        output_dir=tmp_path,
        text_fetcher=fake_get_text,
        binary_fetcher=lambda url: b"%PDF-1.4\nfake",
        import_pdfs=False,
    )

    assert result["tasks"].iloc[0]["status"] == "rate_limited"
    assert result["tasks"].iloc[1]["status"] == "pending"


def test_run_hibor_a_tier_backfill_stops_at_detail_attempt_budget(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "hibor_a_tier_backfill_tasks.csv"
    pd.DataFrame(
        [
            {
                "task_id": "hibor_a_tier_603530",
                "asset_id": "CN:SH:603530",
                "ts_code": "603530.SH",
                "symbol": "603530",
                "stock_name": "神马电力",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            },
            {
                "task_id": "hibor_a_tier_002484",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "symbol": "002484",
                "stock_name": "江海股份",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            },
        ]
    ).to_csv(task_path, index=False)
    detail_calls = []

    def fake_get_text(url: str) -> str:
        if "gaojisousuo" in url:
            symbol = "603530" if "gjz=603530" in url else "002484"
            stock = "神马电力" if symbol == "603530" else "江海股份"
            return f'<tr><td><a href="http://sys.hibor.com.cn/center/maibo/maibopdfsys.asp?did={symbol}">东吴证券-{stock}-{symbol}-深度报告-250101</a></td></tr>'
        detail_calls.append(url)
        return """
        <a href="/hiborClientDownload/Download/Index?abc=A1&amp;def=D2&amp;xyz=X4&amp;vidd=51&amp;keyy=K3&amp;op=0&amp;did=x&amp;docType=1&amp;fromType=16&amp;downloadType=d&amp;linkType=pdf">下载</a>
        """

    monkeypatch.setattr("stock_research.hibor_reports.load_hibor_auth_params_from_cache", lambda: {"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"})

    result = run_hibor_a_tier_backfill(
        tasks_path=task_path,
        output_dir=tmp_path,
        text_fetcher=fake_get_text,
        binary_fetcher=lambda url: b"%PDF-1.4\nfake",
        import_pdfs=False,
        max_detail_attempts=1,
    )

    assert len(detail_calls) == 1
    assert result["tasks"].iloc[0]["status"] == "done"
    assert result["tasks"].iloc[1]["status"] == "pending"
    assert result["summary"]["detail_attempts"] == 1


def test_run_hibor_a_tier_backfill_retries_transient_search_errors(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "hibor_a_tier_backfill_tasks.csv"
    pd.DataFrame(
        [
            {
                "task_id": "hibor_a_tier_603530",
                "asset_id": "CN:SH:603530",
                "ts_code": "603530.SH",
                "symbol": "603530",
                "stock_name": "神马电力",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            }
        ]
    ).to_csv(task_path, index=False)
    calls = {"search": 0}

    def fake_get_text(url: str) -> str:
        if "gaojisousuo" in url:
            calls["search"] += 1
            if calls["search"] == 1:
                raise RuntimeError("temporary 502")
            return ""
        return ""

    monkeypatch.setattr("stock_research.hibor_reports.load_hibor_auth_params_from_cache", lambda: {"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"})

    result = run_hibor_a_tier_backfill(
        tasks_path=task_path,
        output_dir=tmp_path,
        text_fetcher=fake_get_text,
        binary_fetcher=lambda url: b"%PDF-1.4\nfake",
        import_pdfs=False,
        retry_attempts=2,
        retry_sleep_seconds=0,
    )

    assert calls["search"] == 2
    assert result["tasks"].iloc[0]["status"] == "no_qualified_report"


def test_run_hibor_a_tier_backfill_preserves_existing_manifests_when_no_tasks(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "hibor_a_tier_backfill_tasks.csv"
    pd.DataFrame(
        [
            {
                "task_id": "hibor_a_tier_603530",
                "asset_id": "CN:SH:603530",
                "ts_code": "603530.SH",
                "symbol": "603530",
                "stock_name": "神马电力",
                "start_date": "2024-10-01",
                "end_date": "2026-06-04",
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            }
        ]
    ).to_csv(task_path, index=False)
    discovered_path = tmp_path / "hibor_a_tier_discovered_reports.csv"
    downloads_path = tmp_path / "hibor_a_tier_downloaded_reports.csv"
    pd.DataFrame([{"detail_url": "u1", "title": "东吴证券-神马电力-603530-深度报告-250101"}]).to_csv(discovered_path, index=False)
    pd.DataFrame([{"detail_url": "u1", "pdf_path": "/tmp/a.pdf", "status": "downloaded"}]).to_csv(downloads_path, index=False)
    monkeypatch.setattr("stock_research.hibor_reports.load_hibor_auth_params_from_cache", lambda: {"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"})

    result = run_hibor_a_tier_backfill(
        tasks_path=task_path,
        output_dir=tmp_path,
        max_tasks=0,
        import_pdfs=False,
    )

    assert len(pd.read_csv(result["paths"]["discovered"], low_memory=False)) == 1
    assert len(pd.read_csv(result["paths"]["downloads"], low_memory=False)) == 1


def test_build_hibor_sources_events_from_local_pdfs_uses_existing_schema(tmp_path: Path):
    pdf_path = tmp_path / "20260604-东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    result = build_hibor_sources_events_from_pdfs([pdf_path])

    source = result["sources"].iloc[0]
    event = result["events"].iloc[0]
    assert source["source_type"] == "hibor_manual"
    assert source["source_name"] == "慧博智能策略终端"
    assert source["broker"] == "东吴证券"
    assert source["source_url"].startswith("file://")
    assert source["public_access"] is False
    assert "internal research" in source["copyright_note"]
    assert event["ts_code"] == "603530.SH"
    assert event["stock_name"] == "神马电力"
    assert event["report_date"] == "2026-06-04"
    assert event["auto_trade_enabled"] is False


def test_build_hibor_sources_events_skips_unmatched_pdf_names(tmp_path: Path):
    good_pdf = tmp_path / "20260604-东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期.pdf"
    bad_pdf = tmp_path / "unrelated.pdf"
    good_pdf.write_bytes(b"%PDF-1.4")
    bad_pdf.write_bytes(b"%PDF-1.4")

    result = build_hibor_sources_events_from_pdfs([bad_pdf, good_pdf])

    assert len(result["sources"]) == 1
    assert result["sources"].iloc[0]["broker"] == "东吴证券"


def test_import_hibor_report_pdfs_writes_sources_events_and_pdf_fields(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "20260604-东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    calls = {}

    def fake_upsert_sources_events(**kwargs):
        calls["sources"] = kwargs["sources"]
        calls["events"] = kwargs["events"]
        return {"source_rows": len(kwargs["sources"]), "event_rows": len(kwargs["events"])}

    def fake_pdf_backfill(**kwargs):
        calls["pdf_sources"] = kwargs["sources"]
        return {
            "fields": pd.DataFrame([{"report_id": kwargs["sources"].iloc[0]["report_id"], "status": "parsed"}]),
            "paths": {"fields": str(tmp_path / "fields.csv")},
        }

    def fake_upsert_pdf_fields(fields, service):
        calls["pdf_fields"] = fields
        return {"updated_rows": len(fields)}

    monkeypatch.setattr("stock_research.hibor_reports.upsert_stock_report_sources_events", fake_upsert_sources_events)
    monkeypatch.setattr("stock_research.hibor_reports.build_stock_report_pdf_field_backfill", fake_pdf_backfill)
    monkeypatch.setattr("stock_research.hibor_reports.upsert_stock_report_pdf_fields", fake_upsert_pdf_fields)

    result = import_hibor_report_pdfs(input_dir=tmp_path, output_dir=tmp_path / "out", write_db=True)

    assert result["summary"]["pdf_count"] == 1
    assert result["summary"]["scanned_pdf_count"] == 1
    assert calls["sources"].iloc[0]["source_type"] == "hibor_manual"
    assert calls["events"].iloc[0]["ts_code"] == "603530.SH"
    assert calls["pdf_sources"].iloc[0]["source_url"].startswith("file://")
    assert len(calls["pdf_fields"]) == 1


def test_import_hibor_report_pdfs_can_build_feature_rows(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "20260604-东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    calls = {}

    def fake_pdf_backfill(**kwargs):
        return {
            "fields": pd.DataFrame(
                [
                    {
                        "report_id": "ignored",
                        "status": "parsed",
                        "rating_pdf": "买入",
                        "rating_change_type": "首次覆盖",
                        "target_price": 76.6,
                        "risk_summary": "海外市场拓展风险",
                        "target_price_confidence": 0.8,
                        "has_profit_forecast": True,
                        "has_risk_section": True,
                    }
                ]
            ),
            "paths": {},
        }

    def fake_feature_build(events, *, trade_date, output_dir):
        calls["feature_events"] = events
        calls["feature_trade_date"] = trade_date
        assert events.iloc[0]["rating"] == "买入"
        assert events.iloc[0]["rating_change"] == "首次覆盖"
        assert events.iloc[0]["target_price"] == 76.6
        assert events.iloc[0]["risk_summary"] == "海外市场拓展风险"
        return {
            "features": pd.DataFrame([{"trade_date": trade_date, "ts_code": events.iloc[0]["ts_code"]}]),
            "paths": {"features": str(tmp_path / "features.csv"), "report": str(tmp_path / "features.md")},
        }

    monkeypatch.setattr("stock_research.hibor_reports.build_stock_report_pdf_field_backfill", fake_pdf_backfill)
    monkeypatch.setattr("stock_research.hibor_reports.build_stock_report_features_from_events", fake_feature_build)

    result = import_hibor_report_pdfs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out",
        feature_trade_date="2026-06-04",
    )

    assert calls["feature_trade_date"] == "2026-06-04"
    assert calls["feature_events"].iloc[0]["ts_code"] == "603530.SH"
    assert result["features"].iloc[0]["ts_code"] == "603530.SH"
    assert result["paths"]["features"].endswith("features.csv")


def test_import_hibor_report_pdfs_writes_features_with_keyword_arguments(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "20260604-东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    calls = {}

    def fake_upsert_sources_events(**kwargs):
        return {"source_rows": len(kwargs["sources"]), "event_rows": len(kwargs["events"])}

    def fake_pdf_backfill(**kwargs):
        return {"fields": pd.DataFrame(), "paths": {}}

    def fake_feature_build(events, *, trade_date, output_dir):
        return {
            "features": pd.DataFrame([{"trade_date": trade_date, "ts_code": events.iloc[0]["ts_code"]}]),
            "paths": {"features": str(tmp_path / "features.csv")},
        }

    def fake_upsert_features(*, features, service):
        calls["features"] = features
        calls["service"] = service
        return {"feature_rows": len(features)}

    def fake_upsert_pdf_fields(fields, service):
        return {"updated_rows": len(fields)}

    monkeypatch.setattr("stock_research.hibor_reports.upsert_stock_report_sources_events", fake_upsert_sources_events)
    monkeypatch.setattr("stock_research.hibor_reports.build_stock_report_pdf_field_backfill", fake_pdf_backfill)
    monkeypatch.setattr("stock_research.hibor_reports.upsert_stock_report_pdf_fields", fake_upsert_pdf_fields)
    monkeypatch.setattr("stock_research.hibor_reports.build_stock_report_features_from_events", fake_feature_build)
    monkeypatch.setattr("stock_research.hibor_reports.upsert_stock_report_features", fake_upsert_features)

    result = import_hibor_report_pdfs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out",
        write_db=True,
        service="research",
        feature_trade_date="2026-06-04",
    )

    assert calls["features"].iloc[0]["ts_code"] == "603530.SH"
    assert calls["service"] == "research"
    assert result["features"].iloc[0]["trade_date"] == "2026-06-04"


def test_build_hibor_download_queue_from_candidates(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-06-04", "ts_code": "603530.SH", "stock_name": "神马电力"},
            {"trade_date": "2026-06-04", "ts_code": "002484.SZ", "stock_name": "江海股份"},
        ]
    )

    result = build_hibor_download_queue(
        candidates,
        start_date="2026-05-01",
        end_date="2026-06-04",
        output_dir=tmp_path,
        brokers=["东吴证券", "中信证券"],
    )

    queue = result["queue"]
    assert len(queue) == 4
    assert queue.iloc[0]["query"] == "603530 神马电力 东吴证券 研报"
    assert set(queue["status"]) == {"pending"}
    assert Path(result["paths"]["queue"]).exists()
    assert "东吴证券" in Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert "中信证券" in DEFAULT_TOP_BROKERS


def test_extract_hibor_auth_params_from_cached_text():
    text = "http://sys.hibor.com.cn/HiborClientDownload/DocDetail/Index?id=x&abc=A1&def=D2&vidd=51&keyy=K3&xyz=X4&op=0"

    params = extract_hibor_auth_params_from_text(text)

    assert params == {"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"}


def test_parse_hibor_search_results_extracts_report_links():
    html = """
    <a href="http://sys.hibor.com.cn/center/maibo/maibopdfsys.asp?did=tOoPrQzRrMuMmO&amp;baogaotype=1&amp;fromtype=16&amp;abc=A1"
       target="_blank">东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期</a>
    """

    rows = parse_hibor_search_results(html)

    assert rows == [
        {
            "detail_url": "http://sys.hibor.com.cn/center/maibo/maibopdfsys.asp?did=tOoPrQzRrMuMmO&baogaotype=1&fromtype=16&abc=A1",
            "title": "东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期",
        }
    ]


def test_download_hibor_report_pdfs_searches_details_and_writes_pdf(tmp_path: Path):
    candidates = pd.DataFrame([{"ts_code": "603530.SH", "stock_name": "神马电力"}])
    calls = []

    def fake_get_text(url: str) -> str:
        calls.append(url)
        if "gaojisousuo" in url:
            return """
            <a href="http://sys.hibor.com.cn/center/maibo/maibopdfsys.asp?did=tOoPrQzRrMuMmO&amp;baogaotype=1&amp;fromtype=16&amp;abc=A1"
               target="_blank">东吴证券-神马电力-603530-全球复合外绝缘头部企业，迎来出海高速增长期</a>
            """
        return """
        <a href="/hiborClientDownload/Download/Index?abc=A1&amp;def=D2&amp;xyz=X4&amp;vidd=51&amp;keyy=K3&amp;op=0&amp;did=tOoPrQzRrMuMmO&amp;docType=1&amp;fromType=16&amp;downloadType=d&amp;linkType=pdf">下载</a>
        """

    def fake_download(url: str) -> bytes:
        calls.append(url)
        assert "downloadType=d" in url
        return b"%PDF-1.4\nfake"

    result = download_hibor_report_pdfs(
        candidates,
        start_date="2026-05-01",
        end_date="2026-06-04",
        download_dir=tmp_path,
        auth_params={"abc": "A1", "def": "D2", "vidd": "51", "keyy": "K3", "xyz": "X4", "op": "0"},
        brokers=["东吴证券"],
        max_reports_per_candidate=1,
        text_fetcher=fake_get_text,
        binary_fetcher=fake_download,
    )

    assert result["summary"]["downloaded_count"] == 1
    assert result["downloads"].iloc[0]["status"] == "downloaded"
    assert Path(result["downloads"].iloc[0]["pdf_path"]).read_bytes().startswith(b"%PDF")
    assert any("gjz=603530" in url for url in calls)


def test_cli_dispatches_import_hibor_report_pdfs(monkeypatch, tmp_path: Path, capsys):
    called = {}

    def fake_import(**kwargs):
        called.update(kwargs)
        return {
            "summary": {"pdf_count": 1},
            "paths": {
                "sources": str(tmp_path / "sources.csv"),
                "events": str(tmp_path / "events.csv"),
                "fields": str(tmp_path / "fields.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "import_hibor_report_pdfs", fake_import)

    cli.main(["import-hibor-report-pdfs", "--input-dir", str(tmp_path), "--output-dir", str(tmp_path / "out"), "--write-db"])

    out = capsys.readouterr().out
    assert called["input_dir"] == str(tmp_path)
    assert called["write_db"] is True
    assert called["feature_trade_date"] is None
    assert "hibor_report_import|pdf_count|1" in out


def test_cli_dispatches_build_hibor_download_queue(monkeypatch, tmp_path: Path, capsys):
    candidates_path = tmp_path / "candidates.csv"
    pd.DataFrame([{"ts_code": "603530.SH", "stock_name": "神马电力"}]).to_csv(candidates_path, index=False)
    called = {}

    def fake_queue(candidates, **kwargs):
        called["candidates"] = candidates
        called.update(kwargs)
        return {
            "queue": pd.DataFrame([{"query": "603530 神马电力 东吴证券 研报"}]),
            "paths": {"queue": str(tmp_path / "queue.csv"), "report": str(tmp_path / "report.md")},
        }

    monkeypatch.setattr(cli, "build_hibor_download_queue", fake_queue)

    cli.main(
        [
            "build-hibor-download-queue",
            "--candidates-path",
            str(candidates_path),
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-06-04",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    out = capsys.readouterr().out
    assert len(called["candidates"]) == 1
    assert called["start_date"] == "2026-05-01"
    assert "hibor_download_queue|rows|1" in out


def test_cli_dispatches_build_hibor_a_tier_backfill_plan(monkeypatch, tmp_path: Path, capsys):
    called = {}

    def fake_assets(**kwargs):
        called["asset_service"] = kwargs["service"]
        return pd.DataFrame([{"asset_id": "CN:SH:603530", "ts_code": "603530.SH", "stock_name": "神马电力", "symbol": "603530"}])

    def fake_plan(assets, **kwargs):
        called["assets"] = assets
        called.update(kwargs)
        return {
            "tasks": pd.DataFrame([{"task_id": "hibor_a_tier_603530", "status": "pending"}]),
            "paths": {"tasks": str(tmp_path / "tasks.csv"), "report": str(tmp_path / "report.md")},
        }

    monkeypatch.setattr(cli, "load_stock_report_asset_universe", fake_assets)
    monkeypatch.setattr(cli, "build_hibor_a_tier_backfill_plan", fake_plan)

    cli.main(
        [
            "build-hibor-a-tier-backfill-plan",
            "--start-date",
            "2024-10-01",
            "--end-date",
            "2026-06-04",
            "--output-dir",
            str(tmp_path),
            "--sample-size",
            "1",
            "--service",
            "research",
        ]
    )

    out = capsys.readouterr().out
    assert called["asset_service"] == "research"
    assert len(called["assets"]) == 1
    assert called["start_date"] == "2024-10-01"
    assert "hibor_a_tier_backfill_plan|rows|1" in out


def test_cli_dispatches_run_hibor_a_tier_backfill(monkeypatch, tmp_path: Path, capsys):
    task_path = tmp_path / "tasks.csv"
    task_path.write_text("task_id,status\nhibor_a_tier_603530,pending\n", encoding="utf-8")
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {
            "summary": {"processed_tasks": 1, "detail_attempts": 1, "done_tasks": 1, "needs_review_tasks": 0, "downloaded_count": 2},
            "paths": {
                "tasks": str(task_path),
                "discovered": str(tmp_path / "discovered.csv"),
                "filtered": str(tmp_path / "filtered.csv"),
                "downloads": str(tmp_path / "downloads.csv"),
                "report": str(tmp_path / "report.md"),
                "import_report": str(tmp_path / "import.md"),
            },
        }

    monkeypatch.setattr(cli, "run_hibor_a_tier_backfill", fake_run)

    cli.main(
        [
            "run-hibor-a-tier-backfill",
            "--tasks-path",
            str(task_path),
            "--output-dir",
            str(tmp_path),
            "--max-tasks",
            "1",
            "--max-detail-attempts",
            "120",
            "--fallback-tier",
            "B",
            "--no-import",
        ]
    )

    out = capsys.readouterr().out
    assert called["tasks_path"] == str(task_path)
    assert called["max_tasks"] == 1
    assert called["max_detail_attempts"] == 120
    assert called["fallback_tier"] == "B"
    assert called["import_pdfs"] is False
    assert "hibor_a_tier_backfill|detail_attempts|1" in out
    assert "hibor_a_tier_backfill|downloaded|2" in out
