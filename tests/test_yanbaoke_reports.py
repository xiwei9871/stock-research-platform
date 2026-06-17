from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.yanbaoke_reports import (
    build_yanbaoke_sources_events_from_downloads,
    choose_yanbaoke_download_candidates,
    download_yanbaoke_report_pdf,
    filter_yanbaoke_reports,
    run_yanbaoke_report_backfill,
    search_yanbaoke_reports,
)


def test_search_yanbaoke_reports_parses_structured_api_response():
    calls = {}

    def fake_get_json(url: str, *, headers: dict[str, str]) -> dict:
        calls["url"] = url
        calls["headers"] = headers
        return {
            "success": True,
            "message": "找到 1 份相关报告",
            "total": 1,
            "data": [
                {
                    "uuid": "u1",
                    "title": "20251025-中邮证券-神马电力-603530.SH-业绩符合预期_5页_856kb",
                    "url": "https://pc.yanbaoke.cn/info/u1",
                    "time": "2025-10-26",
                    "pagenum": 5,
                    "org_name": "中邮证券",
                    "rtype_name": "季报点评",
                    "formats": ["pdf"],
                    "content": "股票投资评级 增持",
                }
            ],
        }

    result = search_yanbaoke_reports(
        keyword="神马电力",
        start_date="2024-10-01",
        end_date="2026-06-04",
        size=10,
        get_json=fake_get_json,
    )

    assert result["total"] == 1
    assert result["reports"].iloc[0]["uuid"] == "u1"
    assert result["reports"].iloc[0]["org_name"] == "中邮证券"
    assert "keyword=%E7%A5%9E%E9%A9%AC%E7%94%B5%E5%8A%9B" in calls["url"]
    assert calls["headers"]["X-Skill-ID"] == "yanbaoke-research-report-download"


def test_filter_yanbaoke_reports_uses_a_first_then_b_fallback():
    reports = pd.DataFrame(
        [
            {
                "uuid": "a1",
                "title": "20260604-东吴证券-神马电力-603530.SH-深度报告_10页_2mb",
                "url": "https://pc.yanbaoke.cn/info/a1",
                "time": "2026-06-04",
                "pagenum": 10,
                "org_name": "东吴证券",
                "rtype_name": "公司研究",
                "formats": ["pdf"],
                "content": "",
            },
            {
                "uuid": "b1",
                "title": "20250501-国金证券-神马电力-603530.SH-跟踪报告_5页_1mb",
                "url": "https://pc.yanbaoke.cn/info/b1",
                "time": "2025-05-01",
                "pagenum": 5,
                "org_name": "国金证券",
                "rtype_name": "公司研究",
                "formats": ["pdf"],
                "content": "",
            },
        ]
    )

    filtered = filter_yanbaoke_reports(
        reports,
        ts_code="603530.SH",
        stock_name="神马电力",
        start_date="2024-10-01",
        end_date="2026-06-04",
        institutions_path="config/hibor_institutions.csv",
        fallback_tier="B",
    )

    assert filtered["uuid"].tolist() == ["a1"]
    assert filtered.iloc[0]["broker_tier"] == "A"
    assert filtered.iloc[0]["selected_tier_reason"] == "primary_A"


def test_filter_yanbaoke_reports_uses_b_when_a_absent():
    reports = pd.DataFrame(
        [
            {
                "uuid": "b1",
                "title": "20250501-国金证券-神马电力-603530.SH-跟踪报告_5页_1mb",
                "url": "https://pc.yanbaoke.cn/info/b1",
                "time": "2025-05-01",
                "pagenum": 5,
                "org_name": "国金证券",
                "rtype_name": "公司研究",
                "formats": ["pdf"],
                "content": "",
            }
        ]
    )

    filtered = filter_yanbaoke_reports(
        reports,
        ts_code="603530.SH",
        stock_name="神马电力",
        start_date="2024-10-01",
        end_date="2026-06-04",
        institutions_path="config/hibor_institutions.csv",
        fallback_tier="B",
    )

    assert filtered["uuid"].tolist() == ["b1"]
    assert filtered.iloc[0]["broker_tier"] == "B"
    assert filtered.iloc[0]["selected_tier_reason"] == "fallback_B"


def test_choose_yanbaoke_download_candidates_prioritizes_base_then_top10_depth():
    candidates = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "uuid": "base_a", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-01"},
            {"ts_code": "000002.SZ", "uuid": "top_a1", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-03"},
            {"ts_code": "000002.SZ", "uuid": "top_b1", "broker": "国金证券", "broker_tier": "B", "publish_date": "2026-01-02"},
            {"ts_code": "000002.SZ", "uuid": "top_b2", "broker": "天风证券", "broker_tier": "B", "publish_date": "2026-01-01"},
            {"ts_code": "000003.SZ", "uuid": "covered_a", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-01"},
        ]
    )
    existing = pd.DataFrame(
        [
            {"ts_code": "000003.SZ", "uuid": "old_base", "status": "downloaded"},
            {"ts_code": "000002.SZ", "uuid": "old_top", "status": "downloaded"},
        ]
    )

    chosen = choose_yanbaoke_download_candidates(
        candidates,
        existing_downloads=existing,
        top_ts_codes={"000002.SZ"},
        monthly_budget=4,
        base_budget=1,
        top_budget=2,
        reserve_budget=1,
        base_target_per_stock=1,
        depth_target_per_stock=3,
        max_broker_share=1.0,
    )

    assert chosen["uuid"].tolist() == ["base_a", "top_a1", "top_b1"]
    assert chosen["budget_bucket"].tolist() == ["base_coverage", "weekly_top10", "weekly_top10"]
    assert "covered_a" not in set(chosen["uuid"])


def test_choose_yanbaoke_download_candidates_uses_reserve_after_primary_budgets():
    candidates = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "uuid": "base_a", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-01"},
            {"ts_code": "000002.SZ", "uuid": "top_a1", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-03"},
        ]
    )

    chosen = choose_yanbaoke_download_candidates(
        candidates,
        existing_downloads=pd.DataFrame(),
        top_ts_codes={"000002.SZ"},
        monthly_budget=2,
        base_budget=0,
        top_budget=1,
        reserve_budget=1,
        max_broker_share=1.0,
    )

    assert chosen["uuid"].tolist() == ["top_a1", "base_a"]
    assert chosen["budget_bucket"].tolist() == ["weekly_top10", "reserve"]


def test_choose_yanbaoke_download_candidates_diversifies_brokers_for_depth_stock():
    candidates = pd.DataFrame(
        [
            {"ts_code": "000002.SZ", "uuid": "dw_new", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-05", "pagenum": 10},
            {"ts_code": "000002.SZ", "uuid": "dw_old", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-04", "pagenum": 10},
            {"ts_code": "000002.SZ", "uuid": "gx", "broker": "国信证券", "broker_tier": "A", "publish_date": "2026-01-03", "pagenum": 8},
            {"ts_code": "000002.SZ", "uuid": "gj", "broker": "国金证券", "broker_tier": "B", "publish_date": "2026-01-02", "pagenum": 8},
        ]
    )

    chosen = choose_yanbaoke_download_candidates(
        candidates,
        existing_downloads=pd.DataFrame(),
        position_ts_codes={"000002.SZ"},
        monthly_budget=3,
        base_budget=0,
        top_budget=3,
        reserve_budget=0,
        depth_target_per_stock=3,
    )

    assert chosen["uuid"].tolist() == ["dw_new", "gx", "gj"]
    assert chosen["broker"].tolist() == ["东吴证券", "国信证券", "国金证券"]


def test_choose_yanbaoke_download_candidates_caps_single_broker_share_across_batch():
    candidates = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "uuid": "dw1", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-05"},
            {"ts_code": "000002.SZ", "uuid": "dw2", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-05"},
            {"ts_code": "000003.SZ", "uuid": "dw3", "broker": "东吴证券", "broker_tier": "A", "publish_date": "2026-01-05"},
            {"ts_code": "000004.SZ", "uuid": "gx1", "broker": "国信证券", "broker_tier": "A", "publish_date": "2026-01-04"},
            {"ts_code": "000005.SZ", "uuid": "gf1", "broker": "广发证券", "broker_tier": "A", "publish_date": "2026-01-03"},
        ]
    )

    chosen = choose_yanbaoke_download_candidates(
        candidates,
        existing_downloads=pd.DataFrame(),
        monthly_budget=5,
        base_budget=5,
        top_budget=0,
        reserve_budget=0,
        base_target_per_stock=1,
        max_broker_share=0.4,
    )

    assert chosen["uuid"].tolist() == ["dw1", "dw2", "gx1", "gf1"]
    assert int(chosen["broker"].eq("东吴证券").sum()) == 2


def test_download_yanbaoke_report_pdf_fetches_link_and_writes_pdf(tmp_path: Path):
    calls = {}

    def fake_get_json(url: str, *, headers: dict[str, str]) -> dict:
        calls["download_api_url"] = url
        calls["auth"] = headers["Authorization"]
        return {
            "download_url": "https://files.quzili.cn/report.pdf",
            "title": "20251025-中邮证券-神马电力-603530.SH-业绩符合预期_5页_856kb",
            "filename": "20251025-中邮证券-神马电力-603530.SH-业绩符合预期_5页_856kb.pdf",
            "format": "pdf",
            "expires_in": 60,
        }

    def fake_get_binary(url: str) -> bytes:
        calls["file_url"] = url
        return b"%PDF-1.7\nfake"

    result = download_yanbaoke_report_pdf(
        uuid="u1",
        output_dir=tmp_path,
        api_key="sk-test",
        get_json=fake_get_json,
        get_binary=fake_get_binary,
    )

    assert result["status"] == "downloaded"
    assert Path(result["pdf_path"]).read_bytes().startswith(b"%PDF")
    assert calls["auth"] == "Bearer sk-test"
    assert calls["file_url"] == "https://files.quzili.cn/report.pdf"


def test_build_yanbaoke_sources_events_from_downloads_uses_existing_schema(tmp_path: Path):
    pdf_path = tmp_path / "20251025-中邮证券-神马电力-603530.SH-业绩符合预期_5页_856kb.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nfake")
    downloads = pd.DataFrame(
        [
            {
                "uuid": "u1",
                "title": "20251025-中邮证券-神马电力-603530.SH-业绩符合预期_5页_856kb",
                "detail_url": "https://pc.yanbaoke.cn/info/u1",
                "pdf_path": str(pdf_path),
                "broker": "中邮证券",
                "broker_tier": "B",
                "broker_group": "B1_domestic",
                "broker_region": "domestic",
                "publish_date": "2025-10-26",
                "ts_code": "603530.SH",
                "asset_id": "CN:SH:603530",
                "stock_name": "神马电力",
                "report_title": "业绩符合预期",
            }
        ]
    )

    result = build_yanbaoke_sources_events_from_downloads(downloads)

    source = result["sources"].iloc[0]
    event = result["events"].iloc[0]
    assert source["source_type"] == "yanbaoke_api"
    assert source["source_name"] == "研报客 API"
    assert source["broker"] == "中邮证券"
    assert event["ts_code"] == "603530.SH"
    assert event["report_date"] == "2025-10-26"
    assert '"broker_tier": "B"' in source["metadata"]


def test_run_yanbaoke_report_backfill_searches_downloads_and_imports(monkeypatch, tmp_path: Path):
    tasks_path = tmp_path / "tasks.csv"
    pd.DataFrame(
        [
            {
                "task_id": "yanbaoke_603530",
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
    ).to_csv(tasks_path, index=False)
    calls = {}

    def fake_search(**kwargs):
        calls["keyword"] = kwargs["keyword"]
        return {
            "total": 1,
            "reports": pd.DataFrame(
                [
                    {
                        "uuid": "u1",
                        "title": "20251025-中邮证券-神马电力-603530.SH-业绩符合预期_5页_856kb",
                        "url": "https://pc.yanbaoke.cn/info/u1",
                        "time": "2025-10-26",
                        "pagenum": 5,
                        "org_name": "中邮证券",
                        "rtype_name": "季报点评",
                        "formats": ["pdf"],
                        "content": "",
                    }
                ]
            ),
        }

    def fake_download(**kwargs):
        pdf_path = tmp_path / "pdfs" / "20251025-中邮证券-神马电力-603530.SH-业绩符合预期_5页_856kb.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.7\nfake")
        return {
            "status": "downloaded",
            "uuid": kwargs["uuid"],
            "pdf_path": str(pdf_path),
            "download_url": "https://files.quzili.cn/report.pdf",
            "filename": pdf_path.name,
        }

    monkeypatch.setattr("stock_research.yanbaoke_reports.search_yanbaoke_reports", fake_search)
    monkeypatch.setattr("stock_research.yanbaoke_reports.download_yanbaoke_report_pdf", fake_download)

    result = run_yanbaoke_report_backfill(
        tasks_path=tasks_path,
        output_dir=tmp_path,
        download_dir=tmp_path / "pdfs",
        api_key="sk-test",
        import_pdfs=False,
    )

    assert calls["keyword"] == "神马电力"
    assert result["summary"]["downloaded_count"] == 1
    assert result["tasks"].iloc[0]["status"] == "done"
    assert Path(result["paths"]["downloads"]).exists()


def test_cli_dispatches_run_yanbaoke_report_backfill(monkeypatch, tmp_path: Path, capsys):
    task_path = tmp_path / "tasks.csv"
    task_path.write_text("task_id,status\nx,pending\n", encoding="utf-8")
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {
            "summary": {"processed_tasks": 1, "downloaded_count": 1, "done_tasks": 1},
            "paths": {
                "tasks": str(task_path),
                "discovered": str(tmp_path / "discovered.csv"),
                "filtered": str(tmp_path / "filtered.csv"),
                "downloads": str(tmp_path / "downloads.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_yanbaoke_report_backfill", fake_run)

    cli.main(
        [
            "run-yanbaoke-report-backfill",
            "--tasks-path",
            str(task_path),
            "--output-dir",
            str(tmp_path),
            "--max-tasks",
            "1",
            "--max-downloads",
            "2",
            "--monthly-budget",
            "1000",
            "--base-budget",
            "600",
            "--top-budget",
            "300",
            "--reserve-budget",
            "100",
            "--top-ts-code",
            "603530.SH",
            "--position-ts-code",
            "000001.SZ",
            "--max-broker-share",
            "0.25",
            "--no-import",
        ]
    )

    out = capsys.readouterr().out
    assert called["tasks_path"] == str(task_path)
    assert called["max_tasks"] == 1
    assert called["max_downloads"] == 2
    assert called["monthly_budget"] == 1000
    assert called["base_budget"] == 600
    assert called["top_budget"] == 300
    assert called["reserve_budget"] == 100
    assert called["top_ts_codes"] == {"603530.SH"}
    assert called["position_ts_codes"] == {"000001.SZ"}
    assert called["max_broker_share"] == 0.25
    assert called["import_pdfs"] is False
    assert "yanbaoke_backfill|downloaded|1" in out


def test_cli_run_yanbaoke_report_backfill_uses_budget_defaults(monkeypatch, tmp_path: Path):
    task_path = tmp_path / "tasks.csv"
    task_path.write_text("task_id,status\nx,pending\n", encoding="utf-8")
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {
            "summary": {"processed_tasks": 0, "downloaded_count": 0, "done_tasks": 0},
            "paths": {
                "tasks": str(task_path),
                "discovered": str(tmp_path / "discovered.csv"),
                "filtered": str(tmp_path / "filtered.csv"),
                "downloads": str(tmp_path / "downloads.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_yanbaoke_report_backfill", fake_run)

    cli.main(
        [
            "run-yanbaoke-report-backfill",
            "--tasks-path",
            str(task_path),
            "--output-dir",
            str(tmp_path),
            "--no-import",
        ]
    )

    assert called["monthly_budget"] == 1000
    assert called["base_budget"] == 600
    assert called["top_budget"] == 300
    assert called["reserve_budget"] == 100
    assert called["max_broker_share"] == 0.25
