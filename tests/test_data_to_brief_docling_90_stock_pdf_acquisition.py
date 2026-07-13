from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_90_stock_pdf_acquisition.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_pdf_acquisition_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_yanbaoke_missing_pdf_acquisition_outputs_and_guardrails() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    expected = {
        "yanbaoke_missing_pdf_acquisition_summary.json",
        "yanbaoke_missing_pdf_search_audit.csv",
        "yanbaoke_missing_pdf_download_audit.csv",
        "data_to_brief_docling_90_stock_pdf_acquisition_v1_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "yanbaoke_missing_pdf_acquisition_summary.json").read_text(encoding="utf-8"))
    downloads = pd.read_csv(OUTPUT_DIR / "yanbaoke_missing_pdf_download_audit.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "data_to_brief_docling_90_stock_pdf_acquisition_v1"
    assert summary["missing_pdf_input_count"] == 42
    assert summary["downloaded_stock_count"] == 42
    assert summary["downloaded_pdf_count"] >= 42
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False
    assert summary["strategy_file_diff_clean"] is True
    assert downloads["stock_code"].nunique() == 42
    assert downloads["status"].isin(["downloaded", "already_downloaded"]).all()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
