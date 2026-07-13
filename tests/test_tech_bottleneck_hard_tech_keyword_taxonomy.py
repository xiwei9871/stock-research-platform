from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_hard_tech_keyword_taxonomy.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_hard_tech_keyword_taxonomy_v1"
FRONTEND_DATASET = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_keyword_taxonomy_fixture_extracts_star50_and_review_universe_terms(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_hard_tech_keyword_taxonomy import run

    review_universe = tmp_path / "review_universe.csv"
    star50 = tmp_path / "star50.csv"
    output = tmp_path / "out"
    pd.DataFrame(
        [
            {
                "stock_code": "300308",
                "stock_name": "中际旭创",
                "industry": "计算机、通信和其他电子设备制造业",
                "concept_tags": "光电与通信 / 光互联 / 光芯片",
                "strongest_primary_source_claim": "主营业务为高端光通信收发模块，提供800G、1.6T高速光模块和CPO相关光互联方案。",
                "bottleneck_confidence_score": 88,
                "evidence_quality_score": 68,
                "quality_reassessment_tier": "tier_1_core_review_priority",
            },
            {
                "stock_code": "688041",
                "stock_name": "海光信息",
                "industry": "计算机、通信和其他电子设备制造业",
                "concept_tags": "CPU / GPU / AI芯片",
                "strongest_primary_source_claim": "公司产品包括高端处理器、CPU、DCU和AI芯片。",
                "bottleneck_confidence_score": 90,
                "evidence_quality_score": 70,
                "quality_reassessment_tier": "tier_1_core_review_priority",
            },
            {
                "stock_code": "688008",
                "stock_name": "澜起科技",
                "industry": "计算机、通信和其他电子设备制造业",
                "concept_tags": "存储芯片 / DDR5 / HBM",
                "strongest_primary_source_claim": "公司聚焦内存接口芯片、DDR5、HBM相关存储芯片。",
                "bottleneck_confidence_score": 86,
                "evidence_quality_score": 66,
                "quality_reassessment_tier": "tier_1_core_review_priority",
            },
        ]
    ).to_csv(review_universe, index=False)
    pd.DataFrame(
        [
            {"stock_code": "688041", "stock_name": "海光信息"},
            {"stock_code": "688008", "stock_name": "澜起科技"},
        ]
    ).to_csv(star50, index=False)

    summary = run(review_universe_path=review_universe, star50_constituents_path=star50, output_dir=output)

    taxonomy = pd.read_csv(output / "hard_tech_keyword_taxonomy.csv")
    stock_hits = pd.read_csv(output / "stock_keyword_hit_audit.csv", dtype={"stock_code": str})
    source_audit = pd.read_csv(output / "keyword_source_audit.csv")
    missing = pd.read_csv(output / "missing_keyword_candidates.csv", dtype={"stock_code": str})

    keywords = set(taxonomy["keyword"])
    assert {
        "光模块",
        "光通信",
        "CPO",
        "硅光",
        "存储芯片",
        "HBM",
        "DDR5",
        "CPU",
        "GPU",
        "AI芯片",
        "AI服务器",
        "高速PCB",
        "高阶PCB",
        "高速信号完整性",
        "224Gbps",
    }.issubset(keywords)
    assert stock_hits[stock_hits["stock_code"].eq("300308")]["matched_keywords"].str.contains("光模块|光通信").any()
    assert stock_hits[stock_hits["stock_code"].eq("688008")]["matched_keywords"].str.contains("存储芯片|HBM|DDR5").any()
    assert set(source_audit["source_type"]).issuperset({"policy_seed", "star50_constituent", "review_universe"})
    assert "300308" not in set(missing["stock_code"])
    assert summary["research_only"] is True
    assert summary["review_universe_count"] == 3
    assert summary["star50_constituent_count"] == 2
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0


def test_keyword_taxonomy_real_outputs_and_guardrails() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((OUTPUT_DIR / "hard_tech_keyword_taxonomy_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "hard_tech_keyword_taxonomy_guardrails.json").read_text(encoding="utf-8"))
    taxonomy = pd.read_csv(OUTPUT_DIR / "hard_tech_keyword_taxonomy.csv")
    stock_hits = pd.read_csv(OUTPUT_DIR / "stock_keyword_hit_audit.csv", dtype={"stock_code": str})

    keywords = set(taxonomy["keyword"])
    assert {"光模块", "光通信", "存储芯片", "HBM", "CPO", "硅光", "AI服务器", "高阶PCB", "224Gbps"}.issubset(keywords)
    expected_count = len(pd.read_csv(FRONTEND_DATASET, dtype={"stock_code": str}))
    assert summary["review_universe_count"] == expected_count
    assert summary["star50_constituent_count"] >= 1
    assert summary["keyword_count"] >= 80
    assert guardrails["research_only"] is True
    assert guardrails["quality_reassessment_performed"] is False
    assert guardrails["strategy_file_diff_clean"] is True
    assert stock_hits[stock_hits["stock_code"].eq("300308")]["matched_keywords"].str.contains("光模块|光通信").any()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
