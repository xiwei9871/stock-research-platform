import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_review_universe_yanbaoke_report_backfill import (
    build_existing_report_pdf_coverage,
    rank_yanbaoke_report_candidates_for_stock,
    run_tech_bottleneck_review_universe_yanbaoke_report_backfill,
)


def test_build_existing_report_pdf_coverage_only_counts_real_report_pdfs(tmp_path: Path) -> None:
    universe = pd.DataFrame(
        [
            {"stock_code": "000001", "stock_name": "平安银行"},
            {"stock_code": "000002", "stock_name": "万科A"},
        ]
    )
    pdf_dir = tmp_path / "outputs" / "yanbaoke_batch" / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "20260101-中信证券-平安银行-000001.SZ-公司点评_3页.pdf").write_bytes(b"%PDF-1.7\nfake")
    generic = tmp_path / "outputs" / "stock_report_event_candidates.csv"
    pd.DataFrame([{"stock_code": "000002", "stock_name": "万科A"}]).to_csv(generic, index=False)

    coverage = build_existing_report_pdf_coverage(universe, search_roots=[tmp_path / "outputs"])

    by_code = coverage.set_index("stock_code")
    assert by_code.loc["000001", "has_report_pdf"] is True
    assert by_code.loc["000001", "report_pdf_count"] == 1
    assert by_code.loc["000002", "has_report_pdf"] is False
    assert by_code.loc["000002", "report_pdf_count"] == 0


def test_build_existing_report_pdf_coverage_excludes_exchange_filing_pdfs(tmp_path: Path) -> None:
    universe = pd.DataFrame([{"stock_code": "000001", "stock_name": "平安银行"}])
    pdf_dir = tmp_path / "outputs" / "yanbaoke_batch" / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "2025-03-20-深交所-平安银行_2024年年度报告_200页_2mb.pdf").write_bytes(b"%PDF-1.7\nfake")

    coverage = build_existing_report_pdf_coverage(universe, search_roots=[tmp_path / "outputs"])

    row = coverage.set_index("stock_code").loc["000001"]
    assert row["has_report_pdf"] is False
    assert row["report_pdf_count"] == 0


def test_build_existing_report_pdf_coverage_excludes_generic_report_manifest_rows(tmp_path: Path) -> None:
    universe = pd.DataFrame([{"stock_code": "000001", "stock_name": "平安银行"}])
    manifest = tmp_path / "yanbaoke_downloads.csv"
    pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "stock_name": "平安银行",
                "status": "downloaded",
                "report_title": "2026-01-01-中信证券-银行行业周报_30页_2mb",
                "filename": "2026-01-01-中信证券-银行行业周报_30页_2mb.pdf",
                "pdf_path": str(tmp_path / "2026-01-01-中信证券-银行行业周报_30页_2mb.pdf"),
            }
        ]
    ).to_csv(manifest, index=False)

    coverage = build_existing_report_pdf_coverage(universe, search_roots=[tmp_path])

    row = coverage.set_index("stock_code").loc["000001"]
    assert row["has_report_pdf"] is False
    assert row["report_pdf_count"] == 0


def test_build_existing_report_pdf_coverage_accepts_broker_name_in_pdf_filename(tmp_path: Path) -> None:
    universe = pd.DataFrame([{"stock_code": "002837", "stock_name": "英维克"}])
    pdf_dir = tmp_path / "yanbaoke_pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "2025-06-10-花旗集团-深圳市英维克科技股份有限公司（002837）_首次评级为买入_51页_5mb.pdf").write_bytes(
        b"%PDF-1.7\nfake"
    )

    coverage = build_existing_report_pdf_coverage(universe, search_roots=[tmp_path])

    row = coverage.set_index("stock_code").loc["002837"]
    assert row["has_report_pdf"] is True
    assert row["report_pdf_count"] == 1


def test_build_existing_report_pdf_coverage_accepts_stock_name_in_pdf_filename_without_code(tmp_path: Path) -> None:
    universe = pd.DataFrame([{"stock_code": "301418", "stock_name": "协昌科技"}])
    pdf_dir = tmp_path / "yanbaoke_pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "中小市值行业新股研究月报：建议关注固高科技、司南导航、协昌科技、波长光电-20230729-国海证券-20页.pdf").write_bytes(
        b"%PDF-1.7\nfake"
    )

    coverage = build_existing_report_pdf_coverage(universe, search_roots=[tmp_path])

    row = coverage.set_index("stock_code").loc["301418"]
    assert row["has_report_pdf"] is True
    assert row["report_pdf_count"] == 1


def test_run_yanbaoke_report_backfill_downloads_missing_only(tmp_path: Path) -> None:
    universe_path = tmp_path / "frontend_dataset.csv"
    pd.DataFrame(
        [
            {"stock_code": "000001", "stock_name": "平安银行"},
            {"stock_code": "000002", "stock_name": "万科A"},
        ]
    ).to_csv(universe_path, index=False)
    existing_root = tmp_path / "existing"
    pdf_dir = existing_root / "yanbaoke" / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "20260101-中信证券-平安银行-000001.SZ-公司点评_3页.pdf").write_bytes(b"%PDF-1.7\nfake")

    calls: list[str] = []

    def fake_search(**kwargs):
        calls.append(kwargs["keyword"])
        return {
            "reports": pd.DataFrame(
                [
                    {
                        "uuid": "u2",
                        "title": "20260102-中信证券-万科A-000002.SZ-公司深度_20页_2mb",
                        "content": "万科A 000002",
                        "formats": ["pdf"],
                        "time": "2026-01-02",
                        "pagenum": 20,
                        "org_name": "中信证券",
                        "url": "https://pc.yanbaoke.cn/info/u2",
                    }
                ]
            )
        }

    def fake_download(*, uuid, output_dir, api_key):
        path = Path(output_dir) / "20260102-中信证券-万科A-000002.SZ-公司深度_20页.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7\nfake")
        return {
            "uuid": uuid,
            "status": "downloaded",
            "pdf_path": str(path),
            "download_url": "https://files.example/report.pdf",
            "filename": path.name,
            "title": path.stem,
        }

    result = run_tech_bottleneck_review_universe_yanbaoke_report_backfill(
        universe_path=universe_path,
        output_dir=tmp_path / "out",
        search_roots=[existing_root],
        api_key="sk-test",
        search_func=fake_search,
        download_func=fake_download,
        sleep_seconds=0,
    )

    summary = result["summary"]
    assert summary["review_universe_count"] == 2
    assert summary["existing_report_pdf_covered_count"] == 1
    assert summary["missing_report_pdf_before_count"] == 1
    assert summary["downloaded_stock_count"] == 1
    assert summary["unresolved_missing_report_pdf_count"] == 0
    assert calls == ["万科A"]
    assert (tmp_path / "out" / "review_universe_yanbaoke_report_download_manifest.csv").exists()
    assert json.loads((tmp_path / "out" / "review_universe_yanbaoke_report_backfill_guardrails.json").read_text())[
        "used_for_signal_count"
    ] == 0


def test_run_yanbaoke_report_backfill_falls_back_when_first_query_has_only_filings(tmp_path: Path) -> None:
    universe_path = tmp_path / "frontend_dataset.csv"
    pd.DataFrame([{"stock_code": "000002", "stock_name": "万科A"}]).to_csv(universe_path, index=False)
    calls: list[tuple[str, str | None]] = []

    def fake_search(**kwargs):
        calls.append((kwargs["keyword"], kwargs.get("stock")))
        if len(calls) == 1:
            return {
                "reports": pd.DataFrame(
                    [
                        {
                            "uuid": "filing",
                            "title": "2025-03-20-深交所-万科A_2024年年度报告_200页_2mb",
                            "content": "万科A",
                            "formats": ["pdf"],
                            "time": "2025-03-20",
                            "pagenum": 200,
                            "org_name": "深交所",
                        }
                    ]
                )
            }
        return {
            "reports": pd.DataFrame(
                [
                    {
                        "uuid": "broker",
                        "title": "2025-04-01-中信证券-万科A-000002.SZ-年报点评_5页_800kb",
                        "content": "万科A 000002",
                        "formats": ["pdf"],
                        "time": "2025-04-01",
                        "pagenum": 5,
                        "org_name": "中信证券",
                    }
                ]
            )
        }

    def fake_download(*, uuid, output_dir, api_key):
        path = Path(output_dir) / "2025-04-01-中信证券-万科A-000002.SZ-年报点评_5页.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7\nfake")
        return {"uuid": uuid, "status": "downloaded", "pdf_path": str(path), "filename": path.name}

    result = run_tech_bottleneck_review_universe_yanbaoke_report_backfill(
        universe_path=universe_path,
        output_dir=tmp_path / "out",
        search_roots=[tmp_path / "empty"],
        api_key="sk-test",
        search_func=fake_search,
        download_func=fake_download,
        sleep_seconds=0,
    )

    assert result["summary"]["downloaded_stock_count"] == 1
    assert calls[:2] == [("万科A", "万科A"), ("000002", None)]


def test_run_yanbaoke_report_backfill_can_use_content_search_fallback(tmp_path: Path) -> None:
    universe_path = tmp_path / "frontend_dataset.csv"
    pd.DataFrame([{"stock_code": "000002", "stock_name": "万科A"}]).to_csv(universe_path, index=False)
    calls: list[tuple[str, str]] = []

    def fake_search(**kwargs):
        calls.append((kwargs["keyword"], kwargs["search_type"]))
        if kwargs["search_type"] != "content":
            return {"reports": pd.DataFrame()}
        return {
            "reports": pd.DataFrame(
                [
                    {
                        "uuid": "broker",
                        "title": "2025-04-01-中信证券-万科A-000002.SZ-年报点评_5页_800kb",
                        "content": "万科A 000002",
                        "formats": ["pdf"],
                        "time": "2025-04-01",
                        "pagenum": 5,
                        "org_name": "中信证券",
                    }
                ]
            )
        }

    def fake_download(*, uuid, output_dir, api_key):
        path = Path(output_dir) / "2025-04-01-中信证券-万科A-000002.SZ-年报点评_5页.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7\nfake")
        return {"uuid": uuid, "status": "downloaded", "pdf_path": str(path), "filename": path.name}

    result = run_tech_bottleneck_review_universe_yanbaoke_report_backfill(
        universe_path=universe_path,
        output_dir=tmp_path / "out",
        search_roots=[tmp_path / "empty"],
        api_key="sk-test",
        search_func=fake_search,
        download_func=fake_download,
        sleep_seconds=0,
    )

    assert result["summary"]["downloaded_stock_count"] == 1
    assert calls[-1] == ("万科A", "content")


def test_run_yanbaoke_report_backfill_can_use_stock_code_content_search_fallback(tmp_path: Path) -> None:
    universe_path = tmp_path / "frontend_dataset.csv"
    pd.DataFrame([{"stock_code": "000002", "stock_name": "万科A"}]).to_csv(universe_path, index=False)
    calls: list[tuple[str, str]] = []

    def fake_search(**kwargs):
        calls.append((kwargs["keyword"], kwargs["search_type"]))
        if kwargs["keyword"] != "000002" or kwargs["search_type"] != "content":
            return {"reports": pd.DataFrame()}
        return {
            "reports": pd.DataFrame(
                [
                    {
                        "uuid": "broker",
                        "title": "2025-04-01-中信证券-万科A-000002.SZ-年报点评_5页_800kb",
                        "content": "000002",
                        "formats": ["pdf"],
                        "time": "2025-04-01",
                        "pagenum": 5,
                        "org_name": "中信证券",
                    }
                ]
            )
        }

    def fake_download(*, uuid, output_dir, api_key):
        path = Path(output_dir) / "2025-04-01-中信证券-万科A-000002.SZ-年报点评_5页.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7\nfake")
        return {"uuid": uuid, "status": "downloaded", "pdf_path": str(path), "filename": path.name}

    result = run_tech_bottleneck_review_universe_yanbaoke_report_backfill(
        universe_path=universe_path,
        output_dir=tmp_path / "out",
        search_roots=[tmp_path / "empty"],
        api_key="sk-test",
        search_func=fake_search,
        download_func=fake_download,
        sleep_seconds=0,
    )

    assert result["summary"]["downloaded_stock_count"] == 1
    assert calls[-1] == ("000002", "content")


def test_rank_yanbaoke_report_candidates_excludes_exchange_filings() -> None:
    candidates = pd.DataFrame(
        [
            {
                "uuid": "filing",
                "title": "2025-03-20-深交所-万科A_2024年年度报告_200页_2mb",
                "content": "万科A",
                "formats": ["pdf"],
                "time": "2025-03-20",
                "pagenum": 200,
                "org_name": "深交所",
            },
            {
                "uuid": "broker",
                "title": "2025-04-01-中信证券-万科A-000002.SZ-年报点评_5页_800kb",
                "content": "万科A",
                "formats": ["pdf"],
                "time": "2025-04-01",
                "pagenum": 5,
                "org_name": "中信证券",
            },
        ]
    )

    ranked = rank_yanbaoke_report_candidates_for_stock(candidates, stock_code="000002", stock_name="万科A")

    assert ranked["uuid"].tolist() == ["broker"]


def test_rank_yanbaoke_report_candidates_rejects_title_with_other_stock_code() -> None:
    candidates = pd.DataFrame(
        [
            {
                "uuid": "wrong-code",
                "title": "2025-06-13-花旗集团-天孚通信（300570）_行业更新_24页_1mb",
                "content": "天孚通信",
                "formats": ["pdf"],
                "time": "2025-06-13",
                "pagenum": 24,
                "org_name": "花旗集团",
            },
            {
                "uuid": "right-code",
                "title": "2025-06-13-花旗集团-天孚通信-300394.SZ-公司更新_24页_1mb",
                "content": "天孚通信 300394",
                "formats": ["pdf"],
                "time": "2025-06-13",
                "pagenum": 24,
                "org_name": "花旗集团",
            },
        ]
    )

    ranked = rank_yanbaoke_report_candidates_for_stock(candidates, stock_code="300394", stock_name="天孚通信")

    assert ranked["uuid"].tolist() == ["right-code"]


def test_rank_yanbaoke_report_candidates_rejects_generic_industry_title_without_stock_identity() -> None:
    candidates = pd.DataFrame(
        [
            {
                "uuid": "generic",
                "title": "2026-01-01-中信证券-银行行业周报_30页_2mb",
                "content": "平安银行 000001",
                "formats": ["pdf"],
                "time": "2026-01-01",
                "pagenum": 30,
                "org_name": "中信证券",
            }
        ]
    )

    ranked = rank_yanbaoke_report_candidates_for_stock(candidates, stock_code="000001", stock_name="平安银行")

    assert ranked.empty
