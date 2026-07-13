from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_manual_review_first_triage.py"
INPUT_MANUAL_FIRST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_manual_review_first.csv"
)
INPUT_DEFER_REJECT = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_defer_or_reject.csv"
)
QUALITY_POOL_V5 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _output_hashes() -> dict[str, str]:
    return {path.name: _sha(path) for path in sorted(OUTPUT_DIR.iterdir()) if path.is_file()}


def test_latent_manual_review_first_triage_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "manual_first": _sha(INPUT_MANUAL_FIRST),
        "defer_reject": _sha(INPUT_DEFER_REJECT),
        "quality_pool_v5": _sha(QUALITY_POOL_V5),
    }
    _run_generator()
    input_hashes_after = {
        "manual_first": _sha(INPUT_MANUAL_FIRST),
        "defer_reject": _sha(INPUT_DEFER_REJECT),
        "quality_pool_v5": _sha(QUALITY_POOL_V5),
    }

    expected = {
        "latent_manual_review_first_triage_summary.json",
        "latent_manual_review_first_triage.csv",
        "latent_manual_review_high_priority_collection_queue.csv",
        "latent_manual_review_standard_collection_queue.csv",
        "latent_manual_review_human_confirm_first.csv",
        "latent_manual_review_defer_or_reject.csv",
        "latent_manual_review_first_triage_guardrails.json",
        "tech_bottleneck_latent_manual_review_first_triage_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "latent_manual_review_first_triage_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "latent_manual_review_first_triage_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_manual_review_first_count"] == 113
    assert summary["processed_count"] == 113
    assert (
        summary["high_priority_collection_queue_count"]
        + summary["standard_collection_queue_count"]
        + summary["human_confirm_first_count"]
        + summary["defer_or_reject_count"]
        == 113
    )
    assert summary["primary_source_collection_performed"] is False
    assert summary["backfill_decision_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["quality_pool_v5_processed"] is False
    assert summary["defer_reject_24_processed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_manual_review_first_triage_ready",
        "conditionally_ready_with_manual_review_needed",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_manual_review_first_count"] == 113
    assert guardrails["processed_count"] == 113
    assert guardrails["primary_source_collection_performed"] is False
    assert guardrails["backfill_decision_performed"] is False
    assert guardrails["core_equivalence_performed"] is False
    assert guardrails["quality_pool_v5_processed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_manual_review_first_triage_integrity() -> None:
    _run_generator()

    source = pd.read_csv(INPUT_MANUAL_FIRST, dtype={"stock_code": str})
    defer_input = pd.read_csv(INPUT_DEFER_REJECT, dtype={"stock_code": str})
    quality_pool_v5 = pd.read_csv(QUALITY_POOL_V5, dtype={"stock_code": str})
    triage = pd.read_csv(OUTPUT_DIR / "latent_manual_review_first_triage.csv", dtype={"stock_code": str})
    high = pd.read_csv(OUTPUT_DIR / "latent_manual_review_high_priority_collection_queue.csv", dtype={"stock_code": str})
    standard = pd.read_csv(OUTPUT_DIR / "latent_manual_review_standard_collection_queue.csv", dtype={"stock_code": str})
    human = pd.read_csv(OUTPUT_DIR / "latent_manual_review_human_confirm_first.csv", dtype={"stock_code": str})
    defer = pd.read_csv(OUTPUT_DIR / "latent_manual_review_defer_or_reject.csv", dtype={"stock_code": str})

    required_columns = {
        "stock_code",
        "stock_name",
        "tech_bottleneck_domain",
        "candidate_tier",
        "hard_tech_domain_signal",
        "bottleneck_or_chokepoint_possibility",
        "business_relevance_signal",
        "concept_pollution_risk",
        "beneficiary_only_risk",
        "primary_source_feasibility",
        "needs_human_supply_chain_role_confirmation",
        "triage_decision",
        "triage_reason",
        "recommended_next_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    }
    assert required_columns.issubset(triage.columns)
    assert len(triage) == 113
    assert triage["stock_code"].nunique() == 113
    assert set(triage["stock_code"]) == set(source["stock_code"].astype(str).str.zfill(6))
    assert set(triage["stock_code"]).isdisjoint(set(defer_input["stock_code"].astype(str).str.zfill(6)))
    assert set(triage["stock_code"]).isdisjoint(set(quality_pool_v5["stock_code"].astype(str).str.zfill(6)))
    assert len(high) + len(standard) + len(human) + len(defer) == 113
    assert set(triage["triage_decision"]).issubset(
        {
            "high_priority_collection_queue",
            "standard_collection_queue",
            "human_confirm_first",
            "defer_or_reject",
        }
    )
    assert triage["triage_reason"].astype(str).str.len().gt(0).all()
    assert triage["recommended_next_action"].astype(str).str.len().gt(0).all()
    assert triage["research_only"].eq(True).all()
    assert triage["used_for_signal"].eq(False).all()
    assert triage["used_for_admission"].eq(False).all()
    assert set(high["triage_decision"]) <= {"high_priority_collection_queue"}
    assert set(standard["triage_decision"]) <= {"standard_collection_queue"}
    assert set(human["triage_decision"]) <= {"human_confirm_first"}
    assert set(defer["triage_decision"]) <= {"defer_or_reject"}


def test_latent_manual_review_first_triage_deterministic_and_strategy_diff_clean() -> None:
    _run_generator()
    first = _output_hashes()
    _run_generator()
    second = _output_hashes()
    assert first == second

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
