from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_90_stock_review_dashboard_integration.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_review_and_dashboard_integration_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_docling_90_stock_review_outputs_and_payload() -> None:
    _run_generator()

    expected = {
        "review_manifest.csv",
        "artifact_consistency_audit.csv",
        "citation_resolution_audit.csv",
        "dashboard_payload.json",
        "summary.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    payload = json.loads((OUTPUT_DIR / "dashboard_payload.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "review_manifest.csv", dtype={"stock_code": str})
    citation_audit = pd.read_csv(OUTPUT_DIR / "citation_resolution_audit.csv", dtype={"stock_code": str})
    consistency = pd.read_csv(OUTPUT_DIR / "artifact_consistency_audit.csv", dtype={"stock_code": str})

    assert payload["batch_id"] == "data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
    assert payload["stock_count"] == 90
    assert len(payload["per_stock"]) == 90
    assert len(manifest) == 90
    assert payload["report_success_count"] == 90
    assert payload["evidence_required_count"] == 0
    assert payload["citation_claim_count"] == 1061
    assert payload["page_level_citation_count"] == 1061
    assert payload["source_level_citation_count"] == 0
    assert payload["table_row_count"] == 10083
    assert payload["table_provenance_full_count"] == 10083
    assert payload["parser_artifact_ready_count"] == 90
    assert payload["acceptance_decision"] == "ready_for_read_only_dashboard_review"
    assert payload["allowed_for_signal"] is False
    assert payload["allowed_for_admission"] is False
    assert payload["production_update"] is False

    assert citation_audit["citation_resolution_status"].eq("resolved_page_level").all()
    assert int(citation_audit["unresolved_citation"].sum()) == 0
    assert consistency["artifact_consistency_status"].eq("pass").all()
    assert manifest["source_level_citation_count"].sum() == 0


def test_docling_90_stock_review_dashboard_api_and_strategy_diff() -> None:
    _run_generator()

    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/research/data-to-brief/docling-90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["stock_count"] == 90
    assert payload["citation_claim_count"] == 1061
    assert payload["source_level_citation_count"] == 0
    assert payload["acceptance_decision"] == "ready_for_read_only_dashboard_review"
    assert len(payload["per_stock"]) == 90
    assert all(row["allowed_for_signal"] is False for row in payload["per_stock"])
    assert all(row["allowed_for_admission"] is False for row in payload["per_stock"])

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
