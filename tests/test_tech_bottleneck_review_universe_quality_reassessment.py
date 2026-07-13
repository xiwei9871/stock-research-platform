from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_quality_reassessment.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_quality_reassessment_v1"
FRONTEND_DATASET = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _fixture_market_profile() -> dict[str, pd.DataFrame]:
    return {
        "company": pd.DataFrame(
            [
                {"stock_code": "000001", "asset_id": "CN:SZ:000001", "region": "深圳", "db_industry": "专用设备制造业"},
                {"stock_code": "000002", "asset_id": "CN:SZ:000002", "region": "苏州", "db_industry": "计算机、通信和其他电子设备制造业"},
                {"stock_code": "000003", "asset_id": "CN:SZ:000003", "region": "上海", "db_industry": "批发业"},
            ]
        ),
        "concepts": pd.DataFrame(
            [
                {"stock_code": "000001", "db_concept_tags": "半导体设备/国产替代/光刻机"},
                {"stock_code": "000002", "db_concept_tags": "消费电子/代工"},
                {"stock_code": "000003", "db_concept_tags": "贸易/概念主题"},
            ]
        ),
        "financial": pd.DataFrame(
            [
                {
                    "stock_code": "000001",
                    "latest_report_period": "2025-12-31",
                    "latest_revenue": 100.0,
                    "latest_np_parent": 12.0,
                    "net_operate_cash_flow": 10.0,
                    "roe": 14.0,
                    "gross_margin": 42.0,
                    "debt_ratio": 35.0,
                    "ocf_to_np": 0.9,
                },
                {
                    "stock_code": "000002",
                    "latest_report_period": "2025-12-31",
                    "latest_revenue": 200.0,
                    "latest_np_parent": 2.0,
                    "net_operate_cash_flow": -3.0,
                    "roe": 2.0,
                    "gross_margin": 8.0,
                    "debt_ratio": 74.0,
                    "ocf_to_np": -1.5,
                },
                {
                    "stock_code": "000003",
                    "latest_report_period": "2025-12-31",
                    "latest_revenue": 50.0,
                    "latest_np_parent": 1.0,
                    "net_operate_cash_flow": 1.0,
                    "roe": 3.0,
                    "gross_margin": 5.0,
                    "debt_ratio": 40.0,
                    "ocf_to_np": 1.0,
                },
            ]
        ),
        "business": pd.DataFrame(
            [
                {
                    "stock_code": "000001",
                    "business_report_period": "2025-12-31",
                    "top_product_name": "半导体刻蚀设备",
                    "top_product_revenue_ratio": 72.0,
                    "top_product_gross_margin": 46.0,
                    "hard_tech_product_hit_count": 2,
                    "product_item_count": 3,
                },
                {
                    "stock_code": "000002",
                    "business_report_period": "2025-12-31",
                    "top_product_name": "手机组装服务",
                    "top_product_revenue_ratio": 60.0,
                    "top_product_gross_margin": 7.0,
                    "hard_tech_product_hit_count": 0,
                    "product_item_count": 2,
                },
            ]
        ),
    }


def test_quality_reassessment_fixture_grades_and_guardrails(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_review_universe_quality_reassessment import run

    dataset = tmp_path / "dataset.csv"
    evidence = tmp_path / "report_evidence.csv"
    output = tmp_path / "out"
    pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "stock_name": "强瓶颈",
                "industry": "专用设备制造业",
                "concept_tags": "半导体设备",
                "evidence_strength": "strong",
                "bottleneck_relevance": "core",
                "source_group": "v5_hydrated",
                "previous_tier": "Tier A",
                "bottleneck_confidence_score": 90,
                "evidence_quality_score": 80,
                "evidence_count": 40,
                "page_citation_count": 20,
                "source_pdf_count": 3,
                "primary_source_supported": True,
                "concept_pollution_risk": "low",
                "route_around_or_substitution_risk": "weak",
                "value_capture_risk": "strong",
            },
            {
                "stock_code": "000002",
                "stock_name": "低质配套",
                "industry": "电子制造",
                "concept_tags": "消费电子",
                "evidence_strength": "strong",
                "bottleneck_relevance": "core",
                "source_group": "v7_proposal_new",
                "previous_tier": "Tier B",
                "bottleneck_confidence_score": 80,
                "evidence_quality_score": 70,
                "evidence_count": 30,
                "page_citation_count": 15,
                "source_pdf_count": 2,
                "primary_source_supported": True,
                "concept_pollution_risk": "medium",
                "route_around_or_substitution_risk": "high",
                "value_capture_risk": "weak",
            },
            {
                "stock_code": "000003",
                "stock_name": "主题贸易",
                "industry": "批发业",
                "concept_tags": "概念主题",
                "evidence_strength": "insufficient",
                "bottleneck_relevance": "unclear",
                "source_group": "v5_hydrated",
                "previous_tier": "Tier C",
                "bottleneck_confidence_score": 45,
                "evidence_quality_score": 30,
                "evidence_count": 3,
                "page_citation_count": 1,
                "source_pdf_count": 1,
                "primary_source_supported": False,
                "concept_pollution_risk": "high",
                "route_around_or_substitution_risk": "high",
                "value_capture_risk": "weak",
            },
        ]
    ).to_csv(dataset, index=False)
    pd.DataFrame(
        [
            {"stock_code": "000001", "evidence_text": "刻蚀设备 国产替代 客户验证", "citation_granularity": "page_level"},
            {"stock_code": "000002", "evidence_text": "手机组装 代工", "citation_granularity": "page_level"},
        ]
    ).to_csv(evidence, index=False)

    summary = run(
        frontend_dataset_path=dataset,
        report_evidence_path=evidence,
        output_dir=output,
        market_profile=_fixture_market_profile(),
    )

    result = pd.read_csv(output / "review_universe_quality_reassessment.csv", dtype={"stock_code": str})
    grades = dict(zip(result["stock_code"], result["quality_reassessment_tier"]))
    assert grades["000001"] == "tier_1_core_review_priority"
    assert grades["000002"] in {"tier_3_quality_or_value_capture_gap", "tier_4_downgrade_or_reject_review"}
    assert grades["000003"] == "tier_4_downgrade_or_reject_review"
    assert summary["review_universe_total_count"] == 3
    assert summary["reassessment_performed"] is True
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0

    guardrails = json.loads((output / "review_universe_quality_reassessment_guardrails.json").read_text(encoding="utf-8"))
    assert guardrails["research_only"] is True
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["frozen_quality_pool_generated"] is False


def test_quality_reassessment_real_outputs_and_strategy_diff() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((OUTPUT_DIR / "review_universe_quality_reassessment_summary.json").read_text(encoding="utf-8"))
    reassessment = pd.read_csv(OUTPUT_DIR / "review_universe_quality_reassessment.csv", dtype={"stock_code": str})
    business = pd.read_csv(OUTPUT_DIR / "review_universe_business_quality_snapshot.csv", dtype={"stock_code": str})
    expected_count = len(pd.read_csv(FRONTEND_DATASET, dtype={"stock_code": str}))

    assert summary["research_only"] is True
    assert summary["review_universe_total_count"] == expected_count
    assert len(reassessment) == expected_count
    assert len(business) == expected_count
    assert summary["market_profile_region_gap_count"] == 0
    assert summary["market_profile_concept_gap_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert set(reassessment["quality_reassessment_tier"]).issubset(
        {
            "tier_1_core_review_priority",
            "tier_2_strong_review_candidate",
            "tier_3_quality_or_value_capture_gap",
            "tier_4_downgrade_or_reject_review",
        }
    )
    zhongji = reassessment[reassessment["stock_code"].eq("300308")].iloc[0]
    zhongji_business = business[business["stock_code"].eq("300308")].iloc[0]
    assert zhongji_business["top_product_name"] == "光通信收发模块"
    assert float(zhongji_business["top_product_revenue_ratio"]) >= 90
    assert float(zhongji_business["top_product_gross_margin"]) >= 35
    assert float(zhongji_business["hard_tech_product_hit_count"]) > 0
    assert float(zhongji["business_alignment_score"]) >= 70
    assert zhongji["quality_reassessment_tier"] == "tier_1_core_review_priority"

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
