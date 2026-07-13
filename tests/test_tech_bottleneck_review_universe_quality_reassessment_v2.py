from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_quality_reassessment_v2.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_quality_reassessment_v2"
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
            [{"stock_code": "002463", "asset_id": "CN:SZ:002463", "region": "江苏", "db_industry": "计算机、通信和其他电子设备制造业"}]
        ),
        "concepts": pd.DataFrame([{"stock_code": "002463", "db_concept_tags": "PCB/AI服务器/高速互连"}]),
        "financial": pd.DataFrame(
            [
                {
                    "stock_code": "002463",
                    "latest_report_period": "2025-12-31",
                    "latest_revenue": 13300.0,
                    "latest_np_parent": 2600.0,
                    "net_operate_cash_flow": 2200.0,
                    "roe": 22.0,
                    "gross_margin": 36.0,
                    "debt_ratio": 42.0,
                    "ocf_to_np": 0.9,
                }
            ]
        ),
        "business": pd.DataFrame(
            [
                {
                    "stock_code": "002463",
                    "business_report_period": "2025-12-31",
                    "top_product_name": "产品销售收入(印制电路板业务)",
                    "top_product_revenue_ratio": 95.8,
                    "top_product_gross_margin": 36.9,
                    "hard_tech_product_hit_count": 0,
                    "product_item_count": 1,
                }
            ]
        ),
    }


def test_quality_reassessment_v2_uses_page_level_evidence_for_ai_pcb_alignment(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_review_universe_quality_reassessment_v2 import run

    dataset = tmp_path / "dataset.csv"
    report_evidence = tmp_path / "report.csv"
    evidence_index = tmp_path / "evidence_index.csv"
    output = tmp_path / "out"
    pd.DataFrame(
        [
            {
                "stock_code": "002463",
                "stock_name": "沪电股份",
                "industry": "计算机、通信和其他电子设备制造业",
                "concept_tags": "PCB",
                "evidence_strength": "strong",
                "bottleneck_relevance": "core",
                "source_group": "v5_hydrated",
                "previous_tier": "Tier A",
                "bottleneck_confidence_score": 75,
                "evidence_quality_score": 65,
                "evidence_count": 22,
                "page_citation_count": 22,
                "source_pdf_count": 3,
                "primary_source_supported": True,
                "concept_pollution_risk": "low",
                "route_around_or_substitution_risk": "weak",
                "value_capture_risk": "strong",
                "strongest_primary_source_claim": "",
                "evidence_summary_for_review": "",
            }
        ]
    ).to_csv(dataset, index=False)
    pd.DataFrame([{"stock_code": "002463", "evidence_text": "PCB", "citation_granularity": "page_level"}]).to_csv(report_evidence, index=False)
    pd.DataFrame(
        [
            {
                "stock_code": "002463",
                "source_title": "2025年半年度报告",
                "page": 12,
                "evidence_text": "面向人工智能服务器和高速网络基础设施等对PCB的强劲结构性需求，公司加速高阶产能投放。",
                "evidence_claim_type": "hard_tech_exposure",
            },
            {
                "stock_code": "002463",
                "source_title": "2025年半年度报告",
                "page": 24,
                "evidence_text": "224Gbps高速信号完整性、10阶以上HDI、下一代GPU平台产品已通过认证。",
                "evidence_claim_type": "technology_capability",
            },
        ]
    ).to_csv(evidence_index, index=False)

    summary = run(
        frontend_dataset_path=dataset,
        report_evidence_path=report_evidence,
        frontend_evidence_index_path=evidence_index,
        output_dir=output,
        market_profile=_fixture_market_profile(),
    )

    result = pd.read_csv(output / "review_universe_quality_reassessment_v2.csv", dtype={"stock_code": str})
    row = result.iloc[0]
    assert summary["page_level_evidence_enrichment_applied"] is True
    assert float(row["page_level_hard_tech_keyword_hit_count"]) >= 4
    assert float(row["business_alignment_score"]) >= 70
    assert row["quality_reassessment_tier"] in {"tier_1_core_review_priority", "tier_2_strong_review_candidate"}


def test_quality_reassessment_v2_real_outputs_fix_hudepcb_and_guardrails() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((OUTPUT_DIR / "review_universe_quality_reassessment_v2_summary.json").read_text(encoding="utf-8"))
    reassessment = pd.read_csv(OUTPUT_DIR / "review_universe_quality_reassessment_v2.csv", dtype={"stock_code": str})
    hude = reassessment[reassessment["stock_code"].eq("002463")].iloc[0]
    expected_count = len(pd.read_csv(FRONTEND_DATASET, dtype={"stock_code": str}))

    assert summary["research_only"] is True
    assert summary["review_universe_total_count"] == expected_count
    assert summary["page_level_evidence_enrichment_applied"] is True
    assert int(summary["page_level_evidence_stock_count"]) >= 300
    assert float(hude["business_alignment_score"]) >= 70
    assert float(hude["page_level_hard_tech_keyword_hit_count"]) >= 4
    assert hude["quality_reassessment_tier"] in {"tier_1_core_review_priority", "tier_2_strong_review_candidate"}
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
