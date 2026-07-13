from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_omission_rescue_evidence_completion_reassessment.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_omission_rescue_evidence_completion_reassessment_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _fixture_market_profile() -> dict[str, pd.DataFrame]:
    return {
        "company": pd.DataFrame(
            [
                {"stock_code": "002384", "asset_id": "CN:SZ:002384", "region": "江苏", "db_industry": "计算机、通信和其他电子设备制造业"},
                {"stock_code": "000333", "asset_id": "CN:SZ:000333", "region": "广东", "db_industry": "电气机械和器材制造业"},
            ]
        ),
        "concepts": pd.DataFrame(
            [
                {"stock_code": "002384", "db_concept_tags": "AI服务器/高速PCB/高速互连"},
                {"stock_code": "000333", "db_concept_tags": "机器人/家电/工业互联网"},
            ]
        ),
        "financial": pd.DataFrame(
            [
                {
                    "stock_code": "002384",
                    "latest_revenue": 360.0,
                    "latest_np_parent": 18.0,
                    "net_operate_cash_flow": 20.0,
                    "roe": 12.0,
                    "gross_margin": 22.0,
                    "debt_ratio": 55.0,
                    "ocf_to_np": 1.0,
                },
                {
                    "stock_code": "000333",
                    "latest_revenue": 4000.0,
                    "latest_np_parent": 350.0,
                    "net_operate_cash_flow": 420.0,
                    "roe": 20.0,
                    "gross_margin": 25.0,
                    "debt_ratio": 62.0,
                    "ocf_to_np": 1.1,
                },
            ]
        ),
        "business": pd.DataFrame(
            [
                {
                    "stock_code": "002384",
                    "top_product_name": "电子电路产品",
                    "top_product_revenue_ratio": 70.0,
                    "top_product_gross_margin": 24.0,
                    "hard_tech_product_hit_count": 0,
                    "product_item_count": 3,
                },
                {
                    "stock_code": "000333",
                    "top_product_name": "智能家电",
                    "top_product_revenue_ratio": 70.0,
                    "top_product_gross_margin": 25.0,
                    "hard_tech_product_hit_count": 0,
                    "product_item_count": 3,
                },
            ]
        ),
    }


def test_omission_rescue_reassessment_fixture_scores_with_evidence_gap_penalty(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_omission_rescue_evidence_completion_reassessment import run

    queue = tmp_path / "queue.csv"
    evidence = tmp_path / "evidence.csv"
    output = tmp_path / "out"
    pd.DataFrame(
        [
            {
                "stock_code": "002384",
                "stock_name": "东山精密",
                "recall_decision": "add_to_review_universe_separate_review",
                "tech_bottleneck_domain": "光电与通信",
                "supply_chain_role": "bottleneck",
                "primary_source_supported": True,
                "page_level_citation_count": 2,
                "remaining_evidence_gap_flags": "missing_route_around",
            },
            {
                "stock_code": "000333",
                "stock_name": "美的集团",
                "recall_decision": "human_confirm_before_review",
                "tech_bottleneck_domain": "其他战略性关键环节",
                "supply_chain_role": "bottleneck",
                "primary_source_supported": False,
                "page_level_citation_count": "",
                "remaining_evidence_gap_flags": "",
            },
        ]
    ).to_csv(queue, index=False)
    pd.DataFrame(
        [
            {
                "stock_code": "002384",
                "stock_name": "东山精密",
                "source_title": "2025年半年度报告",
                "source_path": "/tmp/002384.pdf",
                "source_type": "interim_report",
                "page": 18,
                "evidence_text": "公司电子电路产品面向AI服务器高速PCB、高速互连和高速信号完整性需求。",
                "evidence_claim_type": "hard_tech_exposure",
            }
        ]
    ).to_csv(evidence, index=False)

    summary = run(
        rescue_queue_path=queue,
        evidence_files=[evidence],
        output_dir=output,
        market_profile=_fixture_market_profile(),
    )

    result = pd.read_csv(output / "omission_rescue_quality_reassessment.csv", dtype={"stock_code": str})
    dongshan = result[result["stock_code"].eq("002384")].iloc[0]
    meidi = result[result["stock_code"].eq("000333")].iloc[0]
    assert summary["source_rescue_queue_count"] == 2
    assert summary["scored_count"] == 2
    assert summary["page_level_evidence_stock_count"] == 1
    assert float(dongshan["page_level_hard_tech_keyword_hit_count"]) >= 2
    assert dongshan["quality_reassessment_tier"] in {"tier_1_core_review_priority", "tier_2_strong_review_candidate", "tier_3_quality_or_value_capture_gap"}
    assert meidi["evidence_completion_status"] == "remaining_needs_primary_source_collection"
    assert meidi["quality_reassessment_tier"] in {"tier_3_quality_or_value_capture_gap", "tier_4_downgrade_or_reject_review"}


def test_omission_rescue_reassessment_real_outputs_and_guardrails() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((OUTPUT_DIR / "omission_rescue_evidence_completion_reassessment_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "omission_rescue_evidence_completion_reassessment_guardrails.json").read_text(encoding="utf-8"))
    result_frame = pd.read_csv(OUTPUT_DIR / "omission_rescue_quality_reassessment.csv", dtype={"stock_code": str})
    gaps = pd.read_csv(OUTPUT_DIR / "omission_rescue_remaining_evidence_gap_queue.csv", dtype={"stock_code": str})

    assert summary["research_only"] is True
    assert summary["source_rescue_queue_count"] == len(result_frame)
    assert (
        summary["direct_separate_review_count"]
        + summary["human_confirm_before_review_count"]
        == len(result_frame)
    )
    assert summary["scored_count"] == len(result_frame)
    assert "002384" in set(result_frame["stock_code"])
    dongshan = result_frame[result_frame["stock_code"].eq("002384")].iloc[0]
    assert int(float(dongshan["evidence_count"])) > 0
    assert dongshan["quality_reassessment_tier"] in {
        "tier_1_core_review_priority",
        "tier_2_strong_review_candidate",
        "tier_3_quality_or_value_capture_gap",
    }
    assert summary["page_level_evidence_stock_count"] >= 8
    assert len(gaps) == summary["remaining_evidence_gap_count"]
    assert len(gaps) >= 0
    assert guardrails["frozen_quality_pool_generated"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
