import json

import pandas as pd

from stock_research.official_disclosure_product_backfill import (
    build_product_evidence_rows,
    is_supported_product_disclosure,
    normalize_disclosure_manifest,
)


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
