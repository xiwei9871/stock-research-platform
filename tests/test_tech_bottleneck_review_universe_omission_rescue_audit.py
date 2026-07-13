from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_omission_rescue_audit.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_omission_rescue_audit_v1"
FRONTEND_DATASET = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_omission_rescue_fixture_recalls_keep_separate_without_duplication(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_review_universe_omission_rescue_audit import run

    review_universe = tmp_path / "review.csv"
    separate = tmp_path / "separate.csv"
    output = tmp_path / "out"
    pd.DataFrame(
        [
            {"stock_code": "000001", "stock_name": "已在复盘", "review_universe_source": "v5_hydrated"},
        ]
    ).to_csv(review_universe, index=False)
    pd.DataFrame(
        [
            {
                "stock_code": "002384",
                "stock_name": "东山精密",
                "sidecar_status": "expansion_keep_separate",
                "equivalence_gate_decision": "keep_as_expansion_candidate",
                "primary_source_supported": True,
                "primary_source_evidence_count": 8,
                "page_level_citation_count": 8,
                "tech_bottleneck_domain": "光电与通信",
                "tech_bottleneck_sub_domain": "AI PCB / high-speed board",
                "remaining_evidence_gap_flags": "missing_official_product_source|missing_route_around",
                "downgrade_risk_flags": "route_around_gap|disconfirmation_review_required",
                "recommended_next_action": "resolve route-around/substitution evidence before equivalence review",
            },
            {
                "stock_code": "000001",
                "stock_name": "已在复盘",
                "sidecar_status": "expansion_keep_separate",
                "equivalence_gate_decision": "keep_as_expansion_candidate",
                "primary_source_supported": True,
            },
        ]
    ).to_csv(separate, index=False)

    summary = run(
        review_universe_path=review_universe,
        source_files=[separate],
        output_dir=output,
    )

    additions = pd.read_csv(output / "review_universe_separate_review_additions.csv", dtype={"stock_code": str})
    assert summary["review_universe_reference_count"] == 1
    assert summary["recall_addition_count"] == 1
    assert additions["stock_code"].tolist() == ["002384"]
    row = additions.iloc[0]
    assert row["recall_decision"] == "add_to_review_universe_separate_review"
    assert "route_around" in row["recall_reason"]
    assert row["auto_added_to_quality_pool"] is False or str(row["auto_added_to_quality_pool"]).lower() == "false"


def test_omission_rescue_real_outputs_recall_dongshan_and_guardrails() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((OUTPUT_DIR / "review_universe_omission_rescue_audit_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "review_universe_omission_rescue_audit_guardrails.json").read_text(encoding="utf-8"))
    additions = pd.read_csv(OUTPUT_DIR / "review_universe_separate_review_additions.csv", dtype={"stock_code": str})
    expected_count = len(pd.read_csv(FRONTEND_DATASET, dtype={"stock_code": str}))

    assert summary["research_only"] is True
    assert summary["review_universe_reference_count"] == expected_count
    assert summary["duplicate_with_review_universe_count"] >= 0
    assert "002384" in set(additions["stock_code"])
    dongshan = additions[additions["stock_code"].eq("002384")].iloc[0]
    assert dongshan["stock_name"] == "东山精密"
    assert dongshan["recall_decision"] == "add_to_review_universe_separate_review"
    assert "route_around" in dongshan["remaining_evidence_gap_flags"]
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
