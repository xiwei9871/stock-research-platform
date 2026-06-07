from __future__ import annotations

import pandas as pd

from stock_research.official_report_semantic_backfill import build_official_report_semantic_evidence


def test_build_official_report_semantic_evidence_uses_only_pit_safe_reports() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例科技",
                "trade_date": "2025-01-10",
            }
        ]
    )
    manifest = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "ts_code": "688001.SH",
                "publish_date": "2024-08-30",
                "report_period": "2024-06-30",
                "announcement_title": "2024年半年度报告",
                "source_document_id": "safe",
                "source_document_url": "http://example.com/safe.pdf",
            },
            {
                "asset_id": "CN:SH:688001",
                "ts_code": "688001.SH",
                "publish_date": "2025-04-30",
                "report_period": "2024-12-31",
                "announcement_title": "2024年年度报告",
                "source_document_id": "future",
                "source_document_url": "http://example.com/future.pdf",
            },
        ]
    )

    evidence = build_official_report_semantic_evidence(
        candidates=candidates,
        manifest=manifest,
        run_id="unit",
        lookback_days=365,
        text_loader=lambda url: "公司打破国外垄断，国产化率提升，拥有发明专利，产线已量产。",
    )

    assert set(evidence["source_id"]) == {"safe"}
    assert {"bottleneck_keyword", "technical_barrier", "news_or_announcement_catalyst"}.issubset(
        set(evidence["evidence_type"])
    )
    assert evidence["as_of_safe"].tolist()


def test_build_official_report_semantic_evidence_skips_empty_or_unmatched_text() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例科技",
                "trade_date": "2025-01-10",
            }
        ]
    )
    manifest = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "publish_date": "2024-08-30",
                "report_period": "2024-06-30",
                "announcement_title": "2024年半年度报告",
                "source_document_id": "safe",
                "source_document_url": "http://example.com/safe.pdf",
            }
        ]
    )

    evidence = build_official_report_semantic_evidence(
        candidates=candidates,
        manifest=manifest,
        run_id="unit",
        lookback_days=365,
        text_loader=lambda url: "普通主营业务描述。",
    )

    assert evidence.empty
