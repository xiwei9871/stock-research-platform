from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_remaining_primary_source_collection.py"
INPUT_QUEUE = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1/primary_source_backfill_queue.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_remaining_primary_source_collection_v1"
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


def test_remaining_primary_source_collection_outputs_and_guardrails() -> None:
    queue_hash_before = _sha(INPUT_QUEUE)
    _run_generator()
    queue_hash_after = _sha(INPUT_QUEUE)

    expected = {
        "remaining_primary_source_collection_summary.json",
        "primary_source_collection_manifest.csv",
        "cninfo_primary_source_search_audit.csv",
        "cninfo_primary_source_download_audit.csv",
        "baostock_financial_trace_audit.csv",
        "remaining_primary_source_collection_guardrails.json",
        "tech_bottleneck_remaining_primary_source_collection_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert queue_hash_before == queue_hash_after

    summary = json.loads((OUTPUT_DIR / "remaining_primary_source_collection_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "remaining_primary_source_collection_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_backfill_queue_count"] == 23
    assert summary["processed_stock_count"] == 23
    assert summary["cninfo_search_success_stock_count"] > 0
    assert summary["downloaded_primary_source_pdf_count"] > 0
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "remaining_primary_source_collection_ready",
        "conditionally_ready_with_collection_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["only_backfill_queue_processed"] is True
    assert guardrails["primary_source_collection_generated"] is True
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_remaining_primary_source_collection_processes_only_queue_stocks() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    manifest = pd.read_csv(OUTPUT_DIR / "primary_source_collection_manifest.csv", dtype={"stock_code": str})
    search = pd.read_csv(OUTPUT_DIR / "cninfo_primary_source_search_audit.csv", dtype={"stock_code": str})
    downloads = pd.read_csv(OUTPUT_DIR / "cninfo_primary_source_download_audit.csv", dtype={"stock_code": str})
    baostock = pd.read_csv(OUTPUT_DIR / "baostock_financial_trace_audit.csv", dtype={"stock_code": str})

    expected_codes = set(queue["stock_code"].str.zfill(6))
    assert set(search["stock_code"]).issubset(expected_codes)
    assert set(downloads["stock_code"]).issubset(expected_codes)
    assert set(baostock["stock_code"]) == expected_codes
    assert set(manifest["stock_code"]).issubset(expected_codes)
    if not manifest.empty:
        assert manifest["is_primary_source"].eq(True).all()
        assert manifest["used_for_signal"].eq(False).all()
        assert manifest["used_for_admission"].eq(False).all()
        assert manifest["local_pdf_path"].astype(str).str.endswith(".pdf").all()


def test_remaining_primary_source_collection_strategy_diff_clean() -> None:
    _run_generator()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
