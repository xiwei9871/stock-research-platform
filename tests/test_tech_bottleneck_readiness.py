from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.tech_bottleneck_readiness import (
    READINESS_FLAGS,
    build_readiness_audit,
    normalize_readiness_candidates,
    run_readiness_audit_from_files,
    write_readiness_artifacts,
)


def test_readiness_module_exports_runner() -> None:
    from stock_research.tech_bottleneck_readiness import run_readiness_audit_from_files

    assert callable(run_readiness_audit_from_files)


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


def _single_candidate() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688099",
                "stock_name": "证据测试",
                "trade_date": "2026-06-05",
                "candidate_source": "unit-test",
                "rank": 1,
            }
        ]
    )


def _single_candidate_frames(
    *,
    report_title: str = "经营跟踪",
    raw_summary: str = "产品结构稳定。",
    risk_summary: str = "",
    news: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    return {
        "industry": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688099",
                    "industry_system": "申万",
                    "industry_code": "801080",
                    "industry_name": "电子",
                    "level": 1,
                }
            ]
        ),
        "main_business": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688099",
                    "report_period": "2026-03-31",
                    "classify_type": "按产品分类",
                    "item_name": "通用电子材料",
                    "revenue": 100,
                    "revenue_ratio": 45,
                    "gross_margin": 35,
                }
            ]
        ),
        "reports": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688099",
                    "report_id": "r-test",
                    "report_date": "2026-05-20",
                    "report_title": report_title,
                    "raw_summary": raw_summary,
                    "company_view": "",
                    "industry_view": "",
                    "risk_summary": risk_summary,
                    "source_type": "public_web_search_result",
                    "broker": "示例证券",
                }
            ]
        ),
        "report_features": pd.DataFrame(),
        "events": pd.DataFrame(),
        "news": news if news is not None else pd.DataFrame(),
    }


def test_domestic_substitution_alone_does_not_set_invalidation_evidence() -> None:
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **_single_candidate_frames(
            report_title="关键材料国产替代加速",
            raw_summary="公司推进国产替代，客户导入稳步进行。",
        ),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_invalidation_evidence"] is False


@pytest.mark.parametrize(
    "substitution_text",
    [
        "The company benefits from domestic substitution in critical materials.",
        "Import substitution demand is accelerating for this product line.",
    ],
)
def test_positive_english_substitution_does_not_set_invalidation_evidence(substitution_text: str) -> None:
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **_single_candidate_frames(
            report_title="Critical material localization opportunity",
            raw_summary=substitution_text,
        ),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_bottleneck_keywords"] is True
    assert row["has_invalidation_evidence"] is False


def test_explicit_technology_substitution_sets_invalidation_evidence() -> None:
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **_single_candidate_frames(risk_summary="主要风险为技术替代导致需求下滑。"),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_invalidation_evidence"] is True


@pytest.mark.parametrize(
    "risk_text",
    [
        "Main risk is technology substitution reducing demand for the current route.",
        "Technical substitution may replace the current solution faster than expected.",
    ],
)
def test_explicit_english_substitution_risk_sets_invalidation_evidence(risk_text: str) -> None:
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **_single_candidate_frames(risk_summary=risk_text),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_invalidation_evidence"] is True


def test_news_source_event_id_is_used_in_keyword_match_details() -> None:
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **_single_candidate_frames(
            news=pd.DataFrame(
                [
                    {
                        "asset_id": "CN:SH:688099",
                        "source_event_id": "news-source-123",
                        "published_at": "2026-05-28",
                        "title": "公司突破关键设备卡脖子环节",
                        "content": "客户验证同步推进。",
                    }
                ]
            )
        ),
    )

    detail = audit.details[0]["flag_details"]["has_bottleneck_keywords"][0]
    assert detail["source_table"] == "news"
    assert detail["source_id"] == "news-source-123"


def test_future_report_does_not_set_research_or_keyword_flags_for_earlier_candidate() -> None:
    audit = build_readiness_audit(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688099",
                    "stock_name": "证据测试",
                    "trade_date": "2026-01-10",
                    "candidate_source": "unit-test",
                    "rank": 1,
                }
            ]
        ),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **_single_candidate_frames(report_title="关键材料国产替代加速"),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_research_report"] is False
    assert row["has_bottleneck_keywords"] is False


def test_undated_report_does_not_set_research_or_keyword_flags() -> None:
    frames = _single_candidate_frames(report_title="关键材料国产替代加速")
    frames["reports"] = frames["reports"].assign(report_date=None)

    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **frames,
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_research_report"] is False
    assert row["has_bottleneck_keywords"] is False
    assert audit.details[0]["evidence_counts"]["reports"] == 0


def test_undated_main_business_does_not_set_product_or_proxy_keyword_flags() -> None:
    frames = _single_candidate_frames(report_title="经营跟踪", raw_summary="产品结构稳定。")
    frames["main_business"] = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688099",
                "report_period": None,
                "classify_type": "按产品分类",
                "item_name": "AI 光模块关键材料",
                "revenue": 100,
                "revenue_ratio": 45,
                "gross_margin": 35,
            }
        ]
    )

    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **frames,
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_product_revenue_exposure"] is False
    assert row["has_bottleneck_keywords"] is False
    assert "has_bottleneck_keywords" not in row["proxy_flags"]
    assert audit.details[0]["evidence_counts"]["main_business"] == 0


def test_safe_strong_evidence_csv_sets_readiness_flags(tmp_path: Path) -> None:
    evidence_csv = tmp_path / "evidence.csv"
    pd.DataFrame(
        [
            {
                "run_id": "evidence-unit",
                "asset_id": "CN:SH:688099",
                "stock_name": "证据测试",
                "candidate_trade_date": "2026-06-05",
                "as_of_date": "2026-06-05",
                "evidence_date": "2026-05-20",
                "source_type": "fixture",
                "source_id": "fixture-product",
                "source_title": "主营构成",
                "source_url": "",
                "evidence_type": "product_revenue_exposure",
                "matched_keyword": "",
                "evidence_snippet": "AI关键材料收入占比45%",
                "source_confidence": "strong",
                "is_proxy": False,
                "as_of_safe": True,
                "metadata_json": "{}",
            },
            {
                "run_id": "evidence-unit",
                "asset_id": "CN:SH:688099",
                "stock_name": "证据测试",
                "candidate_trade_date": "2026-06-05",
                "as_of_date": "2026-06-05",
                "evidence_date": "2026-05-20",
                "source_type": "fixture",
                "source_id": "fixture-bottleneck",
                "source_title": "国产替代",
                "source_url": "",
                "evidence_type": "bottleneck_keyword",
                "matched_keyword": "国产替代",
                "evidence_snippet": "关键材料国产替代加速",
                "source_confidence": "medium",
                "is_proxy": False,
                "as_of_safe": True,
                "metadata_json": "{}",
            },
        ]
    ).to_csv(evidence_csv, index=False)

    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        evidence=pd.read_csv(evidence_csv),
        **_single_candidate_frames(report_title="经营跟踪", raw_summary="产品结构稳定。"),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_product_revenue_exposure"] is True
    assert row["has_bottleneck_keywords"] is True
    assert audit.details[0]["flag_details"]["has_product_revenue_exposure"][0]["source_table"] == "evidence"


def test_proxy_or_unsafe_product_evidence_does_not_set_product_flag() -> None:
    base = {
        "run_id": "evidence-unit",
        "asset_id": "CN:SH:688099",
        "stock_name": "证据测试",
        "candidate_trade_date": "2026-06-05",
        "as_of_date": "2026-06-05",
        "evidence_date": "2026-05-20",
        "source_type": "fixture",
        "source_id": "fixture-product",
        "source_title": "产品描述",
        "source_url": "",
        "evidence_type": "product_revenue_exposure",
        "matched_keyword": "",
        "evidence_snippet": "产品描述但不是强主营构成",
        "source_confidence": "medium",
        "is_proxy": True,
        "as_of_safe": True,
        "metadata_json": "{}",
    }
    frames = _single_candidate_frames(report_title="经营跟踪", raw_summary="产品结构稳定。")
    frames["main_business"] = pd.DataFrame()
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        evidence=pd.DataFrame(
            [
                base,
                {**base, "source_confidence": "strong", "is_proxy": False, "as_of_safe": False},
                {**base, "source_confidence": "strong", "is_proxy": False, "evidence_date": None},
                {**base, "source_confidence": "strong", "is_proxy": False, "evidence_date": "2026-06-06"},
            ]
        ),
        **frames,
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_product_revenue_exposure"] is False


def test_unsafe_missing_or_future_text_evidence_does_not_set_flags() -> None:
    base = {
        "run_id": "evidence-unit",
        "asset_id": "CN:SH:688099",
        "stock_name": "证据测试",
        "candidate_trade_date": "2026-06-05",
        "as_of_date": "2026-06-05",
        "evidence_date": "2026-05-20",
        "source_type": "fixture",
        "source_id": "fixture-bottleneck",
        "source_title": "国产替代",
        "source_url": "",
        "evidence_type": "bottleneck_keyword",
        "matched_keyword": "国产替代",
        "evidence_snippet": "关键材料国产替代加速",
        "source_confidence": "medium",
        "is_proxy": False,
        "as_of_safe": False,
        "metadata_json": "{}",
    }
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        evidence=pd.DataFrame(
            [
                base,
                {**base, "as_of_safe": True, "evidence_date": None},
                {**base, "as_of_safe": True, "evidence_date": "2026-06-06"},
            ]
        ),
        **_single_candidate_frames(report_title="经营跟踪", raw_summary="产品结构稳定。"),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_bottleneck_keywords"] is False


def test_future_main_business_does_not_set_product_revenue_exposure() -> None:
    frames = _single_candidate_frames()
    frames["main_business"] = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688099",
                "report_period": "2026-03-31",
                "classify_type": "按产品分类",
                "item_name": "AI 光模块关键材料",
                "revenue": 100,
                "revenue_ratio": 45,
                "gross_margin": 35,
            }
        ]
    )
    audit = build_readiness_audit(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688099",
                    "stock_name": "证据测试",
                    "trade_date": "2026-01-10",
                    "candidate_source": "unit-test",
                    "rank": 1,
                }
            ]
        ),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        **frames,
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_product_revenue_exposure"] is False


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


def test_write_readiness_artifacts_writes_csv_json_and_summary(tmp_path: Path) -> None:
    audit = build_readiness_audit(
        candidates=_candidate_pool(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        source_tables_empty={"news": True},
        **_context_frames(),
    )

    paths = write_readiness_artifacts(audit=audit, output_dir=tmp_path)

    assert paths["csv"] == tmp_path / "readiness.csv"
    assert paths["json"] == tmp_path / "readiness.json"
    assert paths["summary"] == tmp_path / "summary.md"
    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["summary"].exists()

    csv_text = paths["csv"].read_text(encoding="utf-8")
    assert "ready_for_scoring" in csv_text
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["candidate_count"] == len(_candidate_pool())
    assert payload["candidates"][0]["run_id"] == "readiness-test"
    markdown = paths["summary"].read_text(encoding="utf-8")
    assert "# tech-bottleneck data readiness audit" in markdown
    assert "ready_for_scoring" in markdown
    assert "has_news_or_announcement_catalyst" in markdown


def test_run_readiness_audit_from_files_uses_loader_and_writes_artifacts(tmp_path: Path) -> None:
    candidates_csv = tmp_path / "candidates.csv"
    evidence_csv = tmp_path / "evidence.csv"
    _candidate_pool().to_csv(candidates_csv, index=False)
    pd.DataFrame(
        [
            {
                "run_id": "evidence-unit",
                "asset_id": "CN:SZ:300001",
                "stock_name": "缺主营科技",
                "candidate_trade_date": "2026-06-05",
                "as_of_date": "2026-06-05",
                "evidence_date": "2026-05-20",
                "source_type": "fixture",
                "source_id": "fixture-product",
                "source_title": "主营构成",
                "source_url": "",
                "evidence_type": "product_revenue_exposure",
                "matched_keyword": "",
                "evidence_snippet": "AI关键材料收入占比45%",
                "source_confidence": "strong",
                "is_proxy": False,
                "as_of_safe": True,
                "metadata_json": "{}",
            }
        ]
    ).to_csv(evidence_csv, index=False)
    loader_context = _context_frames() | {"source_tables_empty": {"news": True}}

    def fake_loader(candidates: pd.DataFrame, *, lookback_days: int, service: str) -> dict[str, pd.DataFrame]:
        assert set(candidates["asset_id"]) == {"CN:SH:688001", "CN:SZ:300001", "CN:SH:688002", "CN:SH:688003"}
        assert lookback_days == 365
        assert service == "stock_research"
        return loader_context

    paths = run_readiness_audit_from_files(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        service="stock_research",
        evidence_csv=evidence_csv,
        context_loader=fake_loader,
    )

    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["summary"].exists()
    assert loader_context["source_tables_empty"] == {"news": True}
    rows = pd.read_csv(paths["csv"]).set_index("asset_id")
    assert bool(rows.loc["CN:SZ:300001", "has_product_revenue_exposure"]) is True
