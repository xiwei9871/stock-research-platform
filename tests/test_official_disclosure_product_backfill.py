import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from stock_research.official_disclosure_product_backfill import (
    CninfoDisclosureIndexClient,
    OfficialDisclosureProductBackfillResult,
    _load_main_business_from_db,
    build_product_evidence_rows,
    is_supported_product_disclosure,
    normalize_disclosure_manifest,
    run_official_disclosure_product_backfill,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class FakeRawResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class FakeManifestClient:
    def query_asset(self, *, asset_id, ts_code, start_date, end_date):
        return normalize_disclosure_manifest(
            [
                {
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "publish_date": "2025-04-25",
                    "report_period": "2024-12-31",
                    "announcement_title": "2024年年度报告",
                    "source_document_id": "121999",
                    "source_document_url": "http://example.com/report.pdf",
                }
            ]
        )


def test_cninfo_client_parses_supported_announcements():
    requests = []

    def opener(request, timeout):
        requests.append(request)
        parsed = urlparse(request.full_url)
        body = parse_qs(request.data.decode("utf-8"))
        assert parsed.path.endswith("/new/hisAnnouncement/query")
        assert body["stock"] == ["000001,SZ"]
        return FakeResponse(
            {
                "announcements": [
                    {
                        "announcementTitle": "2024年年度报告",
                        "announcementTime": 1745510400000,
                        "announcementId": "121999",
                        "adjunctUrl": "finalpage/2025-04-25/121999.PDF",
                        "secCode": "000001",
                        "secName": "示例公司",
                    },
                    {
                        "announcementTitle": "2024年年度报告摘要",
                        "announcementTime": 1745510400000,
                        "announcementId": "122000",
                        "adjunctUrl": "finalpage/2025-04-25/122000.PDF",
                        "secCode": "000001",
                        "secName": "示例公司",
                    },
                ]
            }
        )

    client = CninfoDisclosureIndexClient(opener=opener)
    manifest = client.query_asset(
        asset_id=1,
        ts_code="000001.SZ",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert len(requests) == 2
    assert manifest.to_dict("records") == [
        {
            "asset_id": "1",
            "ts_code": "000001.SZ",
            "publish_date": pd.Timestamp("2025-04-25").date(),
            "report_period": pd.Timestamp("2024-12-31").date(),
            "announcement_title": "2024年年度报告",
            "source_document_id": "121999",
            "source_document_url": "http://static.cninfo.com.cn/finalpage/2025-04-25/121999.PDF",
            "disclosure_type": "annual",
            "is_supported_product_disclosure": True,
        }
    ]


@pytest.mark.parametrize(
    ("ts_code", "expected_stock", "expected_column", "expected_plate"),
    [
        ("600000.SH", "600000,SH", "sse", "sh"),
        ("600000.SSE", "600000,SH", "sse", "sh"),
        ("CN:SH:600000", "600000,SH", "sse", "sh"),
        ("000001.SZSE", "000001,SZ", "szse", "sz"),
        ("CN:SZ:000001", "000001,SZ", "szse", "sz"),
    ],
)
def test_cninfo_client_normalizes_exchange_suffixes(ts_code, expected_stock, expected_column, expected_plate):
    request_bodies = []

    def opener(request, timeout):
        request_bodies.append(parse_qs(request.data.decode("utf-8")))
        return FakeResponse({"announcements": []})

    CninfoDisclosureIndexClient(opener=opener).query_asset(
        asset_id=1,
        ts_code=ts_code,
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert len(request_bodies) == 2
    assert {body["stock"][0] for body in request_bodies} == {expected_stock}
    assert {body["column"][0] for body in request_bodies} == {expected_column}
    assert {body["plate"][0] for body in request_bodies} == {expected_plate}


@pytest.mark.parametrize("ts_code", ["", "600000", "600000.BJ", "CN:BJ:600000", "CN:SH", "CN:SH:"])
def test_cninfo_client_rejects_malformed_exchange_codes(ts_code):
    def opener(request, timeout):
        raise AssertionError("malformed codes should not issue CNINFO requests")

    with pytest.raises(ValueError):
        CninfoDisclosureIndexClient(opener=opener).query_asset(
            asset_id=1,
            ts_code=ts_code,
            start_date="2025-01-01",
            end_date="2025-12-31",
        )


def test_cninfo_client_skips_failed_category_and_returns_successful_rows():
    calls = []

    def opener(request, timeout):
        calls.append(parse_qs(request.data.decode("utf-8"))["category"][0])
        if len(calls) == 1:
            raise OSError("category request failed")
        return FakeResponse(
            {
                "announcements": [
                    {
                        "announcementTitle": "2024年年度报告",
                        "announcementTime": 1745510400000,
                        "announcementId": "121999",
                        "adjunctUrl": "finalpage/2025-04-25/121999.PDF",
                    }
                ]
            }
        )

    manifest = CninfoDisclosureIndexClient(opener=opener).query_asset(
        asset_id=1,
        ts_code="000001.SZ",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert len(calls) == 2
    assert manifest["source_document_id"].tolist() == ["121999"]


def test_runner_records_no_manifest_error_when_cninfo_category_partially_succeeds(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )
    calls = []

    def opener(request, timeout):
        calls.append(parse_qs(request.data.decode("utf-8"))["category"][0])
        if len(calls) == 1:
            raise OSError("first category failed")
        return FakeResponse(
            {
                "announcements": [
                    {
                        "announcementTitle": "2024年年度报告",
                        "announcementTime": 1745510400000,
                        "announcementId": "121999",
                        "adjunctUrl": "finalpage/2025-04-25/121999.PDF",
                    }
                ]
            }
        )

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=CninfoDisclosureIndexClient(opener=opener),
        main_business_loader=lambda asset_ids, start, end: pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    errors = pd.read_csv(tmp_path / "out" / "manifest_query_errors.csv")
    gaps = pd.read_csv(tmp_path / "out" / "source_gap_report.csv")
    assert len(calls) == 2
    assert errors.empty
    assert gaps.loc[0, "manifest_query_error_count"] == 0


def test_runner_records_manifest_error_when_all_cninfo_categories_fail(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )

    def opener(request, timeout):
        raise OSError("category request failed")

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=CninfoDisclosureIndexClient(opener=opener),
        main_business_loader=lambda asset_ids, start, end: pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    errors = pd.read_csv(tmp_path / "out" / "manifest_query_errors.csv")
    gaps = pd.read_csv(tmp_path / "out" / "source_gap_report.csv")
    assert errors.loc[0, "asset_id"] == 1
    assert errors.loc[0, "ts_code"] == "000001.SZ"
    assert errors.loc[0, "error_type"] in {"RuntimeError", "CninfoDisclosureQueryError"}
    assert "category request failed" in errors.loc[0, "error_message"]
    assert gaps.loc[0, "manifest_query_error_count"] == 1


@pytest.mark.parametrize(
    "response",
    [
        FakeRawResponse(b"{not-json"),
        FakeResponse(["not", "a", "dict"]),
        FakeResponse({"announcements": ["not-a-dict"]}),
    ],
)
def test_cninfo_client_ignores_malformed_response_shapes(response):
    def opener(request, timeout):
        return response

    manifest = CninfoDisclosureIndexClient(opener=opener).query_asset(
        asset_id=1,
        ts_code="000001.SZ",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert manifest.empty


def test_cninfo_client_parses_string_millisecond_timestamps():
    def opener(request, timeout):
        return FakeResponse(
            {
                "announcements": [
                    {
                        "announcementTitle": "2024年年度报告",
                        "announcementTime": "1745510400000",
                        "announcementId": "121999",
                        "adjunctUrl": "finalpage/2025-04-25/121999.PDF",
                    }
                ]
            }
        )

    manifest = CninfoDisclosureIndexClient(opener=opener).query_asset(
        asset_id=1,
        ts_code="000001.SZ",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert manifest["publish_date"].tolist() == [pd.Timestamp("2025-04-25").date()]


def test_supported_product_disclosure_title_filter():
    assert is_supported_product_disclosure("2024年年度报告")
    assert is_supported_product_disclosure("2024年度报告")
    assert is_supported_product_disclosure("2024年半年度报告")
    assert is_supported_product_disclosure("2024半年度报告")
    assert is_supported_product_disclosure("2024年年度报告（更正后）")
    assert not is_supported_product_disclosure("2024年年度报告摘要")
    assert not is_supported_product_disclosure("关于召开股东大会的公告")
    assert not is_supported_product_disclosure("Annual Report 2024")
    assert not is_supported_product_disclosure("关于取消披露2024年年度报告的公告")
    assert not is_supported_product_disclosure("2024年度社会责任报告")
    assert not is_supported_product_disclosure("2024年度环境、社会及治理报告")
    assert not is_supported_product_disclosure("关于2024年年度报告的问询函")
    assert not is_supported_product_disclosure("关于2024年年度报告问询函的回复公告")
    assert not is_supported_product_disclosure("关于撤销2024年年度报告的公告")
    assert not is_supported_product_disclosure("2024年年度CSR报告")
    assert not is_supported_product_disclosure("2024年年度ESG报告")
    assert not is_supported_product_disclosure("2024年年度报告 English Version")


def test_manifest_normalization_preserves_official_trace():
    rows = [
        {
            "asset_id": 1,
            "ts_code": "000001.SZ",
            "publish_date": "2025-04-25",
            "report_period": "2024-12-31",
            "announcement_title": "2024年年度报告",
            "source_document_id": "121999",
            "source_document_url": "http://example.com/report.pdf",
        }
    ]

    manifest = normalize_disclosure_manifest(rows)

    assert manifest.to_dict("records") == [
        {
            "asset_id": "1",
            "ts_code": "000001.SZ",
            "publish_date": pd.Timestamp("2025-04-25").date(),
            "report_period": pd.Timestamp("2024-12-31").date(),
            "announcement_title": "2024年年度报告",
            "source_document_id": "121999",
            "source_document_url": "http://example.com/report.pdf",
            "disclosure_type": "annual",
            "is_supported_product_disclosure": True,
        }
    ]


def test_manifest_normalization_infers_short_chinese_disclosure_types():
    manifest = normalize_disclosure_manifest(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "publish_date": "2025-04-25",
                "report_period": "2024-12-31",
                "announcement_title": "2024年度报告",
            },
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "publish_date": "2024-08-25",
                "report_period": "2024-06-30",
                "announcement_title": "2024半年度报告",
            },
        ]
    )

    assert manifest["disclosure_type"].tolist() == ["semiannual", "annual"]
    assert manifest["is_supported_product_disclosure"].tolist() == [True, True]


def test_product_evidence_returns_empty_schema_when_inputs_empty():
    evidence = build_product_evidence_rows(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    assert len(evidence) == 0
    assert {"asset_id", "evidence_type", "metadata_json", "as_of_safe"}.issubset(evidence.columns)


def test_product_evidence_returns_empty_schema_when_manifest_empty():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            }
        ]
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
            }
        ]
    )

    evidence = build_product_evidence_rows(candidates, pd.DataFrame(), main_business)

    assert len(evidence) == 0
    assert {"asset_id", "evidence_type", "metadata_json", "as_of_safe"}.issubset(evidence.columns)


def test_product_evidence_joins_asset_id_from_csv_string_to_numeric_sources():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "1",
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            }
        ]
    )
    manifest = normalize_disclosure_manifest(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "publish_date": "2025-04-25",
                "report_period": "2024-12-31",
                "announcement_title": "2024年年度报告",
                "source_document_id": "121999",
            }
        ]
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
            }
        ]
    )

    evidence = build_product_evidence_rows(candidates, manifest, main_business)

    assert len(evidence) == 1
    assert evidence.iloc[0]["asset_id"] == "1"
    assert evidence.iloc[0]["as_of_safe"] is True
    assert evidence.iloc[0]["evidence_type"] == "product_revenue_exposure"


def test_product_evidence_output_is_deterministic():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "1",
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            },
            {
                "asset_id": "1",
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
            },
        ]
    )
    manifest = normalize_disclosure_manifest(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "publish_date": "2025-04-25",
                "report_period": "2024-12-31",
                "announcement_title": "2024年年度报告",
                "source_document_id": "doc-b",
            }
        ]
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "Beta设备",
            },
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "Alpha设备",
            },
        ]
    )

    evidence = build_product_evidence_rows(candidates, manifest, main_business)

    assert evidence["candidate_trade_date"].tolist() == [
        "2025-04-18",
        "2025-04-18",
        "2025-05-09",
        "2025-05-09",
    ]
    assert [json.loads(row)["item_name"] for row in evidence["metadata_json"].tolist()] == [
        "Alpha设备",
        "Beta设备",
        "Alpha设备",
        "Beta设备",
    ]


def test_product_evidence_requires_publish_date_visible_to_candidate():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            },
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
            },
        ]
    )
    manifest = normalize_disclosure_manifest(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "publish_date": "2025-04-25",
                "report_period": "2024-12-31",
                "announcement_title": "2024年年度报告",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
            }
        ]
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
                "revenue": 123456789.0,
                "revenue_ratio": 42.5,
                "cost": 90000000.0,
                "gross_profit": 33456789.0,
                "gross_margin": 27.1,
                "source": "akshare.stock_zygc_em",
            }
        ]
    )

    evidence = build_product_evidence_rows(candidates, manifest, main_business)

    records = evidence.sort_values("as_of_date").to_dict("records")
    assert records[0]["as_of_safe"] is False
    assert records[0]["candidate_trade_date"] == "2025-04-18"
    assert records[1]["as_of_safe"] is True
    assert records[1]["candidate_trade_date"] == "2025-05-09"
    assert records[1]["evidence_type"] == "product_revenue_exposure"
    assert records[1]["source_confidence"] == "strong"
    assert records[1]["source_type"] == "official_disclosure_product_backfill"
    assert records[1]["is_proxy"] is False
    assert records[1]["evidence_date"] == "2025-04-25"
    assert "先进封装设备" in records[1]["evidence_snippet"]
    metadata = json.loads(records[1]["metadata_json"])
    assert metadata["item_name"] == "先进封装设备"
    assert metadata["source_document_id"] == "121999"


def test_runner_writes_product_backfill_artifacts(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
                "revenue": 123456789.0,
                "revenue_ratio": 42.5,
                "source": "fixture",
            }
        ]
    )

    result = run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=FakeManifestClient(),
        main_business_loader=lambda asset_ids, start, end: main_business,
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert isinstance(result, OfficialDisclosureProductBackfillResult)
    assert result.evidence_rows == 1
    assert result.safe_evidence_rows == 1
    assert (tmp_path / "out" / "product_evidence.csv").exists()
    assert (tmp_path / "out" / "disclosure_manifest.csv").exists()
    assert (tmp_path / "out" / "document_cache_index.csv").exists()
    assert (tmp_path / "out" / "coverage_summary.md").read_text(encoding="utf-8").startswith(
        "# Official Disclosure Product Backfill"
    )
    gaps = pd.read_csv(tmp_path / "out" / "source_gap_report.csv")
    assert gaps.loc[0, "assets_with_safe_product_evidence"] == 1


def test_runner_deduplicates_manifest_queries_per_asset_ts_code(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n"
        "1,000001.SZ,2025-05-10,2025-05-10\n",
        encoding="utf-8",
    )
    calls = []

    class CountingManifestClient(FakeManifestClient):
        def query_asset(self, *, asset_id, ts_code, start_date, end_date):
            calls.append((asset_id, ts_code, start_date, end_date))
            return super().query_asset(asset_id=asset_id, ts_code=ts_code, start_date=start_date, end_date=end_date)

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=CountingManifestClient(),
        main_business_loader=lambda asset_ids, start, end: pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert calls == [("1", "000001.SZ", "2025-01-01", "2025-12-31")]


def test_runner_continues_when_manifest_query_fails_for_asset(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )

    class FailingManifestClient:
        def query_asset(self, *, asset_id, ts_code, start_date, end_date):
            raise ValueError("bad exchange")

    result = run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=FailingManifestClient(),
        main_business_loader=lambda asset_ids, start, end: pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert result.manifest_rows == 0
    assert result.evidence_rows == 0
    errors = pd.read_csv(tmp_path / "out" / "manifest_query_errors.csv")
    assert errors.to_dict("records") == [
        {
            "asset_id": 1,
            "ts_code": "000001.SZ",
            "error_type": "ValueError",
            "error_message": "bad exchange",
        }
    ]
    gaps = pd.read_csv(tmp_path / "out" / "source_gap_report.csv")
    assert gaps.loc[0, "manifest_query_error_count"] == 1
    assert gaps.loc[0, "assets_with_safe_product_evidence"] == 0
    assert gaps.loc[0, "assets_without_safe_product_evidence"] == 1


def test_runner_empty_evidence_artifact_has_standard_columns(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=FakeManifestClient(),
        main_business_loader=lambda asset_ids, start, end: pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    evidence = pd.read_csv(tmp_path / "out" / "product_evidence.csv")
    assert {
        "run_id",
        "asset_id",
        "candidate_trade_date",
        "as_of_date",
        "evidence_type",
        "metadata_json",
        "as_of_safe",
    }.issubset(evidence.columns)


def test_runner_supports_real_pilot_candidate_shape(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,stock_name,trade_date,candidate_source,rank\n"
        "CN:SZ:000001,示例公司,2025-05-09,pilot,1\n",
        encoding="utf-8",
    )

    class AssertingManifestClient:
        def query_asset(self, *, asset_id, ts_code, start_date, end_date):
            assert asset_id == "CN:SZ:000001"
            assert ts_code == "000001.SZ"
            return normalize_disclosure_manifest(
                [
                    {
                        "asset_id": asset_id,
                        "ts_code": ts_code,
                        "publish_date": "2025-04-25",
                        "report_period": "2024-12-31",
                        "announcement_title": "2024年年度报告",
                        "source_document_id": "121999",
                    }
                ]
            )

    main_business = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
            }
        ]
    )

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=AssertingManifestClient(),
        main_business_loader=lambda asset_ids, start, end: main_business,
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    evidence = pd.read_csv(tmp_path / "out" / "product_evidence.csv")
    assert evidence.loc[0, "asset_id"] == "CN:SZ:000001"
    assert evidence.loc[0, "candidate_trade_date"] == "2025-05-09"
    assert evidence.loc[0, "as_of_date"] == "2025-05-09"


def test_db_loader_preserves_digit_asset_ids_as_strings(monkeypatch):
    captured = {}

    def fake_read_sql(sql, conn, params):
        captured["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(pd, "read_sql", fake_read_sql)

    _load_main_business_from_db(
        ["000001", "1", "CN:SZ:000729"],
        "2023-01-01",
        "2025-12-31",
        conn=object(),
    )

    assert captured["params"][0] == ["000001", "1", "CN:SZ:000729"]


def test_runner_preserves_leading_zero_asset_ids_from_candidate_csv(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "000001,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )
    captured = {}

    def loader(asset_ids, start, end):
        captured["asset_ids"] = asset_ids
        return pd.DataFrame()

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=FakeManifestClient(),
        main_business_loader=loader,
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert captured["asset_ids"] == ["000001"]


def test_runner_counts_candidate_rows_with_safe_product_evidence_by_date(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-04-18,2025-04-18\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
            }
        ]
    )

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=FakeManifestClient(),
        main_business_loader=lambda asset_ids, start, end: main_business,
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    gaps = pd.read_csv(tmp_path / "out" / "source_gap_report.csv")
    assert gaps.loc[0, "assets_with_safe_product_evidence"] == 1
    assert gaps.loc[0, "candidate_rows_with_safe_product_evidence"] == 1
    assert gaps.loc[0, "candidate_rows_without_safe_product_evidence"] == 1


def test_runner_falls_back_to_trade_date_when_candidate_date_is_invalid(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,trade_date,as_of_date\n"
        "1,000001.SZ,not-a-date,2025-05-09,\n",
        encoding="utf-8",
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
            }
        ]
    )

    run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=FakeManifestClient(),
        main_business_loader=lambda asset_ids, start, end: main_business,
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    evidence = pd.read_csv(tmp_path / "out" / "product_evidence.csv")
    assert evidence.loc[0, "candidate_trade_date"] == "2025-05-09"
    assert evidence.loc[0, "as_of_date"] == "2025-05-09"
