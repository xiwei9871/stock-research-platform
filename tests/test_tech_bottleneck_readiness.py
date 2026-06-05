from __future__ import annotations

import pandas as pd
import pytest

from stock_research.tech_bottleneck_readiness import (
    READINESS_FLAGS,
    build_readiness_audit,
    normalize_readiness_candidates,
)


def test_normalize_readiness_candidates_requires_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        normalize_readiness_candidates(
            pd.DataFrame([{"stock_name": "缺少代码"}]),
            run_date="2026-06-06",
            as_of_date=None,
            lookback_days=365,
        )


def test_normalize_readiness_candidates_fills_optional_columns_and_dates() -> None:
    candidates = normalize_readiness_candidates(
        pd.DataFrame(
            [
                {"asset_id": "CN:SH:688001", "stock_name": "示例光电", "trade_date": "2026-06-05", "rank": 1},
                {"asset_id": "CN:SZ:300001"},
            ]
        ),
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
    )

    assert list(candidates.columns) == [
        "asset_id",
        "stock_name",
        "trade_date",
        "candidate_source",
        "rank",
        "as_of_date",
        "lookback_days",
    ]
    rows = candidates.set_index("asset_id")
    assert rows.loc["CN:SH:688001", "as_of_date"] == "2026-06-05"
    assert rows.loc["CN:SH:688001", "rank"] == "1"
    assert rows.loc["CN:SZ:300001", "as_of_date"] == "2026-06-06"
    assert rows.loc["CN:SZ:300001", "stock_name"] == ""
    assert rows.loc["CN:SZ:300001", "candidate_source"] == ""
    assert rows.loc["CN:SZ:300001", "lookback_days"] == 365


def _candidate_pool() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例光电",
                "trade_date": "2026-06-05",
                "candidate_source": "industry-focus",
                "rank": 1,
            },
            {
                "asset_id": "CN:SZ:300001",
                "stock_name": "缺主营科技",
                "trade_date": "2026-06-05",
                "candidate_source": "industry-focus",
                "rank": 2,
            },
            {
                "asset_id": "CN:SH:688002",
                "stock_name": "新闻缺口",
                "trade_date": "2026-06-05",
                "candidate_source": "industry-focus",
                "rank": 3,
            },
            {
                "asset_id": "CN:SH:688003",
                "stock_name": "待补证据",
                "trade_date": "2026-06-05",
                "candidate_source": "industry-focus",
                "rank": 4,
            },
        ]
    )


def _context_frames() -> dict[str, pd.DataFrame]:
    return {
        "industry": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "industry_system": "申万",
                    "industry_code": "801080",
                    "industry_name": "电子",
                    "level": 1,
                },
                {
                    "asset_id": "CN:SH:688002",
                    "industry_system": "申万",
                    "industry_code": "801080",
                    "industry_name": "电子",
                    "level": 1,
                },
                {
                    "asset_id": "CN:SH:688003",
                    "industry_system": "申万",
                    "industry_code": "801080",
                    "industry_name": "电子",
                    "level": 1,
                },
            ]
        ),
        "main_business": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2026-03-31",
                    "classify_type": "按产品分类",
                    "item_name": "AI 光模块关键材料",
                    "revenue": 100,
                    "revenue_ratio": 45,
                    "gross_margin": 35,
                },
                {
                    "asset_id": "CN:SH:688002",
                    "report_period": "2026-03-31",
                    "classify_type": "按产品分类",
                    "item_name": "高纯关键材料",
                    "revenue": 80,
                    "revenue_ratio": 40,
                    "gross_margin": 30,
                },
                {
                    "asset_id": "CN:SH:688003",
                    "report_period": "2026-03-31",
                    "classify_type": "按产品分类",
                    "item_name": "通用电子材料",
                    "revenue": 60,
                    "revenue_ratio": 35,
                    "gross_margin": 25,
                },
            ]
        ),
        "reports": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_id": "r1",
                    "report_date": "2026-05-20",
                    "report_title": "关键材料国产替代加速",
                    "raw_summary": "客户验证推进，扩产建设周期长，技术壁垒高，存在需求不及预期风险。",
                    "company_view": "公司是关键材料供应商。",
                    "industry_view": "供给受限。",
                    "risk_summary": "客户导入延期。",
                    "source_type": "public_web_search_result",
                    "broker": "示例证券",
                },
                {
                    "asset_id": "CN:SH:688002",
                    "report_id": "r2",
                    "report_date": "2026-05-20",
                    "report_title": "关键材料供应商",
                    "raw_summary": "技术壁垒较高。",
                    "company_view": "",
                    "industry_view": "",
                    "risk_summary": "",
                    "source_type": "public_web_search_result",
                    "broker": "示例证券",
                },
                {
                    "asset_id": "CN:SH:688003",
                    "report_id": "r3",
                    "report_date": "2026-05-20",
                    "report_title": "电子材料经营跟踪",
                    "raw_summary": "产品结构稳定。",
                    "company_view": "",
                    "industry_view": "",
                    "risk_summary": "",
                    "source_type": "public_web_search_result",
                    "broker": "示例证券",
                },
            ]
        ),
        "report_features": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "trade_date": "2026-06-05",
                    "report_count_90d": 2,
                    "source_count": 2,
                },
                {
                    "asset_id": "CN:SH:688002",
                    "trade_date": "2026-06-05",
                    "report_count_90d": 1,
                    "source_count": 1,
                },
                {
                    "asset_id": "CN:SH:688003",
                    "trade_date": "2026-06-05",
                    "report_count_90d": 1,
                    "source_count": 1,
                },
            ]
        ),
        "events": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "event_type": "institution_survey",
                    "event_date": "2026-05-30",
                    "summary": "在手订单增长，合格供应商认证推进。",
                }
            ]
        ),
        "news": pd.DataFrame(),
    }


def test_build_readiness_audit_flags_statuses_and_source_gaps() -> None:
    audit = build_readiness_audit(
        candidates=_candidate_pool(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        source_tables_empty={"news": True},
        **_context_frames(),
    )

    rows = audit.summary.set_index("asset_id")
    ready = rows.loc["CN:SH:688001"]
    blocked = rows.loc["CN:SZ:300001"]
    ready_with_source_gap = rows.loc["CN:SH:688002"]
    source_gap = rows.loc["CN:SH:688003"]

    for flag in READINESS_FLAGS:
        assert flag in rows.columns

    assert ready["coverage_status"] == "ready_for_scoring"
    assert ready["coverage_score"] >= 7
    assert ready["has_industry_context"] is True
    assert ready["has_product_revenue_exposure"] is True
    assert ready["has_research_report"] is True
    assert ready["has_bottleneck_keywords"] is True
    assert ready["has_capacity_evidence"] is True
    assert ready["has_customer_certification_evidence"] is True
    assert ready["has_patent_or_technical_barrier"] is True
    assert ready["has_news_or_announcement_catalyst"] is True
    assert ready["has_invalidation_evidence"] is True
    assert "has_patent_or_technical_barrier" in ready["proxy_flags"]

    assert blocked["coverage_status"] == "data_blocked"
    assert blocked["has_product_revenue_exposure"] is False
    assert "has_product_revenue_exposure" in blocked["missing_flags"]

    assert ready_with_source_gap["coverage_status"] == "ready_for_scoring"
    assert ready_with_source_gap["has_news_or_announcement_catalyst"] is False
    assert "has_news_or_announcement_catalyst" in ready_with_source_gap["source_gap_flags"]

    assert source_gap["coverage_status"] == "source_gap"
    assert source_gap["has_news_or_announcement_catalyst"] is False
    assert "has_news_or_announcement_catalyst" in source_gap["source_gap_flags"]

    detail = {row["asset_id"]: row for row in audit.details}
    assert detail["CN:SH:688001"]["evidence_counts"]["reports"] == 1
    assert detail["CN:SH:688001"]["flag_details"]["has_capacity_evidence"][0]["keyword"] == "扩产"
