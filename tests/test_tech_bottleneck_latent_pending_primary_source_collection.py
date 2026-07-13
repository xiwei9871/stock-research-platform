from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_pending_primary_source_collection.py"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_v1/latent_backfill_batch1_remain_pending.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_pending_primary_source_collection_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT), "--sleep-seconds", "0"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_latent_pending_primary_source_collection_outputs_and_guardrails() -> None:
    input_hash_before = _sha(INPUT_QUEUE)
    _run_generator()
    input_hash_after = _sha(INPUT_QUEUE)

    expected = {
        "latent_pending_primary_source_collection_summary.json",
        "latent_pending_primary_source_collection_manifest.csv",
        "latent_pending_primary_source_search_audit.csv",
        "latent_pending_primary_source_download_audit.csv",
        "latent_pending_primary_source_collection_guardrails.json",
        "tech_bottleneck_latent_pending_primary_source_collection_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hash_before == input_hash_after

    summary = json.loads((OUTPUT_DIR / "latent_pending_primary_source_collection_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads(
        (OUTPUT_DIR / "latent_pending_primary_source_collection_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["research_only"] is True
    assert summary["source_latent_pending_count"] == 45
    assert summary["processed_stock_count"] == 45
    assert summary["primary_source_collection_performed"] is True
    assert summary["backfill_decision_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_pending_primary_source_collection_ready",
        "conditionally_ready_with_collection_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_latent_pending_count"] == 45
    assert guardrails["only_latent_pending_processed"] is True
    assert guardrails["primary_source_collection_performed"] is True
    assert guardrails["backfill_decision_performed"] is False
    assert guardrails["core_equivalence_performed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_pending_primary_source_collection_processes_only_45_pending_rows() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    manifest = pd.read_csv(OUTPUT_DIR / "latent_pending_primary_source_collection_manifest.csv", dtype={"stock_code": str})
    search = pd.read_csv(OUTPUT_DIR / "latent_pending_primary_source_search_audit.csv", dtype={"stock_code": str})
    downloads = pd.read_csv(OUTPUT_DIR / "latent_pending_primary_source_download_audit.csv", dtype={"stock_code": str})

    expected_codes = set(queue["stock_code"].astype(str).str.zfill(6))
    assert len(queue) == 45
    assert set(search["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
    assert set(downloads["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
    assert set(manifest["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
    if not manifest.empty:
        assert manifest["is_primary_source"].eq(True).all()
        assert manifest["used_for_signal"].eq(False).all()
        assert manifest["used_for_admission"].eq(False).all()
        assert manifest["local_pdf_path"].astype(str).str.endswith(".pdf").all()


def test_latent_pending_primary_source_collection_strategy_diff_clean() -> None:
    _run_generator()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
