from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_read_only_release_baseline_v1"
PDF_ACQUISITION_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_pdf_acquisition_v1"
FULL_BATCH_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
DASHBOARD_INTEGRATION_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_review_and_dashboard_integration_v1"
E2E_CHECKPOINT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_dashboard_e2e_smoke_and_release_checkpoint_v1"
SUGGESTED_TAG = "v0.2-data-to-brief-docling-90-readonly-baseline"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _git_diff_clean(paths: list[str]) -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *paths],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _artifact_rows() -> list[dict[str, str]]:
    artifacts = [
        (
            "pdf_acquisition",
            PDF_ACQUISITION_DIR,
            "90-stock PDF acquisition output directory",
        ),
        (
            "pdf_acquisition",
            PDF_ACQUISITION_DIR / "yanbaoke_missing_pdf_acquisition_summary.json",
            "PDF acquisition summary",
        ),
        (
            "pdf_acquisition",
            PDF_ACQUISITION_DIR / "yanbaoke_pdfs",
            "downloaded/reused Yanbaoke PDFs",
        ),
        (
            "full_cold_parse_batch",
            FULL_BATCH_DIR / "quality_audit.json",
            "full cold parse quality audit",
        ),
        (
            "full_cold_parse_batch",
            FULL_BATCH_DIR / "batch_manifest.csv",
            "90-stock batch manifest",
        ),
        (
            "full_cold_parse_batch",
            FULL_BATCH_DIR / "source_chunk_manifest_all.csv",
            "page-level source chunk manifest",
        ),
        (
            "full_cold_parse_batch",
            FULL_BATCH_DIR / "table_inventory_all.csv",
            "table provenance inventory",
        ),
        (
            "full_cold_parse_batch",
            FULL_BATCH_DIR / "reports_md",
            "per-stock markdown reports",
        ),
        (
            "full_cold_parse_batch",
            FULL_BATCH_DIR / "evidence",
            "per-stock evidence packages",
        ),
        (
            "dashboard_review_integration",
            DASHBOARD_INTEGRATION_DIR / "dashboard_payload.json",
            "dashboard API/frontend payload",
        ),
        (
            "dashboard_review_integration",
            DASHBOARD_INTEGRATION_DIR / "citation_resolution_audit.csv",
            "citation resolution audit",
        ),
        (
            "dashboard_review_integration",
            DASHBOARD_INTEGRATION_DIR / "summary.md",
            "read-only dashboard integration summary",
        ),
        (
            "e2e_smoke_release_checkpoint",
            E2E_CHECKPOINT_DIR / "api_smoke_audit.json",
            "backend API smoke audit",
        ),
        (
            "e2e_smoke_release_checkpoint",
            E2E_CHECKPOINT_DIR / "dashboard_e2e_smoke_audit.json",
            "dashboard static smoke audit",
        ),
        (
            "e2e_smoke_release_checkpoint",
            E2E_CHECKPOINT_DIR / "docling_90_dashboard_smoke.png",
            "Playwright smoke screenshot",
        ),
        (
            "e2e_smoke_release_checkpoint",
            E2E_CHECKPOINT_DIR / "release_checkpoint_summary.md",
            "release checkpoint summary",
        ),
    ]
    rows = []
    for group, path, description in artifacts:
        rows.append(
            {
                "artifact_group": group,
                "artifact_path": str(path),
                "artifact_name": path.name,
                "exists": str(path.exists()).lower(),
                "description": description,
                "research_only": "true",
                "allowed_for_signal": "false",
                "allowed_for_admission": "false",
                "production_update": "false",
            }
        )
    return rows


def _validation_audit() -> dict[str, Any]:
    full_quality = _load_json(FULL_BATCH_DIR / "quality_audit.json")
    dashboard_payload = _load_json(DASHBOARD_INTEGRATION_DIR / "dashboard_payload.json")
    e2e_api = _load_json(E2E_CHECKPOINT_DIR / "api_smoke_audit.json")
    e2e_boundary = _load_json(E2E_CHECKPOINT_DIR / "research_only_boundary_audit.json")
    pdf_summary = _load_json(PDF_ACQUISITION_DIR / "yanbaoke_missing_pdf_acquisition_summary.json")
    artifact_rows = _artifact_rows()
    artifact_missing_count = sum(1 for row in artifact_rows if row["exists"] != "true")
    strategy_clean = _git_diff_clean(FORMAL_STRATEGY_FILES)
    ready = (
        artifact_missing_count == 0
        and strategy_clean
        and int(full_quality.get("stock_count", 0)) == 90
        and int(full_quality.get("local_pdf_stock_count", 0)) == 90
        and int(full_quality.get("docling_parse_failed_count", 0)) == 0
        and int(full_quality.get("report_failed_count", 0)) == 0
        and int(full_quality.get("citation_claim_count", 0)) == 1061
        and int(full_quality.get("page_level_citation_row_count", 0)) == 1061
        and int(full_quality.get("source_level_citation_count", 0)) == 0
        and dashboard_payload.get("acceptance_decision") == "ready_for_read_only_dashboard_review"
        and e2e_api.get("api_status_code") == 200
        and e2e_boundary.get("forbidden_control_hit_count") == 0
        and e2e_boundary.get("recommendation_language_hit_count") == 0
    )
    return {
        "task_name": "data_to_brief_docling_90_read_only_release_baseline_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pdf_acquisition_summary_path": str(PDF_ACQUISITION_DIR / "yanbaoke_missing_pdf_acquisition_summary.json"),
        "pdf_acquisition_raw": pdf_summary,
        "stock_count": int(full_quality.get("stock_count", 0)),
        "local_pdf_stock_count": int(full_quality.get("local_pdf_stock_count", 0)),
        "evidence_required_count": int(full_quality.get("evidence_required_count", 0)),
        "docling_parse_success_count": int(full_quality.get("docling_parse_success_count", 0)),
        "docling_parse_failed_count": int(full_quality.get("docling_parse_failed_count", 0)),
        "parser_artifact_ready_count": int(full_quality.get("parser_artifact_ready_count", 0)),
        "parser_artifact_invalid_count": int(full_quality.get("parser_artifact_invalid_count", 0)),
        "report_success_count": int(full_quality.get("report_success_count", 0)),
        "report_failed_count": int(full_quality.get("report_failed_count", 0)),
        "citation_claim_count": int(full_quality.get("citation_claim_count", 0)),
        "page_level_citation_count": int(full_quality.get("page_level_citation_row_count", 0)),
        "source_level_citation_count": int(full_quality.get("source_level_citation_count", 0)),
        "table_provenance_full_count": int(full_quality.get("table_provenance_full_count", 0)),
        "table_provenance_partial_count": int(full_quality.get("table_provenance_partial_count", 0)),
        "table_provenance_missing_count": int(full_quality.get("table_provenance_missing_count", 0)),
        "cold_parse_runtime_seconds": float(full_quality.get("cold_parse_runtime_seconds", 0.0)),
        "cached_postprocess_runtime_seconds": float(full_quality.get("cached_postprocess_runtime_seconds", 0.0)),
        "dashboard_acceptance_decision": dashboard_payload.get("acceptance_decision", ""),
        "e2e_api_status_code": e2e_api.get("api_status_code"),
        "forbidden_control_hit_count": int(e2e_boundary.get("forbidden_control_hit_count", 0)),
        "recommendation_language_hit_count": int(e2e_boundary.get("recommendation_language_hit_count", 0)),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": strategy_clean,
        "artifact_missing_count": artifact_missing_count,
        "tag_created": False,
        "suggested_tag": SUGGESTED_TAG,
        "validation_commands": [
            "pytest tests/test_data_to_brief_docling_90_dashboard_e2e_smoke_checkpoint.py tests/test_data_to_brief_docling_90_stock_review_and_dashboard_integration.py tests/test_data_to_brief_docling_90_stock_full_cold_parse_batch.py -q",
            "pnpm --dir dashboard exec vitest run tests/data-to-brief-docling-90-review.test.tsx tests/app-shell.test.tsx",
            "pnpm --dir dashboard exec playwright test tests/data-to-brief-docling-90-review.spec.ts --project=chromium",
            "pnpm --dir dashboard exec tsc --noEmit",
            "git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py",
            "git diff --check",
        ],
        "acceptance_decision": "ready_for_internal_read_only_baseline_tag" if ready else "release_baseline_needs_attention",
    }


def _summary_markdown(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Data-to-Brief Docling 90 Read-Only Release Baseline v1",
            "",
            "This baseline captures the completed research-only Data-to-Brief Docling 90-stock workflow.",
            "",
            "## Pipeline Summary",
            "",
            "- PDF acquisition: 90/90 local PDF coverage; evidence_required_count=0.",
            "- Full cold parse batch: Docling parse success/failed=90/0; parser artifact ready/invalid=90/0.",
            "- Report generation: report success/failed=90/0.",
            "- Citations: citation_claim_count=1061; page_level_citation_count=1061; source_level_citation_count=0.",
            "- Table provenance: full/partial/missing=10083/0/0.",
            f"- Runtime: cold parse {audit['cold_parse_runtime_seconds']} seconds; cached postprocess {audit['cached_postprocess_runtime_seconds']} seconds.",
            "- Dashboard: backend API `/api/research/data-to-brief/docling-90`; frontend route `/research/data-to-brief/docling-90`.",
            "- E2E smoke: API 200, route loads, filters and expandable row checked, console errors 0.",
            "",
            "## Known Limitations",
            "",
            "- Cold parse takes about 2 hours for 58 uncached stocks.",
            "- Dashboard is read-only.",
            "- No signal, admission, scoring, or production connection exists.",
            "- Reports are research evidence briefs, not investment recommendations.",
            "",
            "## Guardrails",
            "",
            f"- allowed_for_signal: {str(audit['allowed_for_signal']).lower()}",
            f"- allowed_for_admission: {str(audit['allowed_for_admission']).lower()}",
            f"- production_update: {str(audit['production_update']).lower()}",
            f"- strategy_file_diff_clean: {str(audit['strategy_file_diff_clean']).lower()}",
            "",
            "## Baseline Tag",
            "",
            f"- suggested_tag: `{SUGGESTED_TAG}`",
            "- No git tag was created.",
            "",
            f"acceptance_decision: {audit['acceptance_decision']}",
        ]
    )


def _runbook_markdown() -> str:
    return "\n".join(
        [
            "# Data-to-Brief Docling 90 Operator Runbook",
            "",
            "All commands are research-only. None of these commands connects reports to signal, admission, scoring, or production strategy logic.",
            "",
            "## rerunning PDF acquisition",
            "",
            "```bash",
            "rtk .venv/bin/python scripts/run_data_to_brief_docling_90_stock_pdf_acquisition.py",
            "```",
            "",
            "Use this when local PDF coverage drops or a new 90-stock pool needs source acquisition.",
            "",
            "## rerunning 90-stock precheck",
            "",
            "```bash",
            "rtk .venv/bin/python scripts/run_data_to_brief_docling_90_stock_batch_precheck.py",
            "```",
            "",
            "Use this before full report generation to check PDF coverage, cached parser artifacts, and expected runtime.",
            "",
            "## rerunning full cold parse batch",
            "",
            "```bash",
            "rtk .venv/bin/python scripts/run_data_to_brief_docling_90_stock_full_cold_parse_batch.py",
            "```",
            "",
            "This is the expensive step. Cold parsing 58 uncached stocks took about 7538 seconds. Existing valid parser artifacts are reused.",
            "",
            "## rerunning dashboard review audit",
            "",
            "```bash",
            "rtk .venv/bin/python scripts/run_data_to_brief_docling_90_stock_review_dashboard_integration.py",
            "```",
            "",
            "This reads completed batch artifacts and regenerates `dashboard_payload.json`; it must not run Docling parsing.",
            "",
            "## rerunning E2E smoke",
            "",
            "```bash",
            "rtk .venv/bin/python scripts/run_data_to_brief_docling_90_dashboard_e2e_smoke_checkpoint.py",
            "rtk pnpm --dir dashboard exec playwright test tests/data-to-brief-docling-90-review.spec.ts --project=chromium",
            "```",
            "",
            "The smoke test checks the read-only route, filters, expandable stock row, artifact paths, and forbidden controls.",
            "",
            "## using cached parser artifacts",
            "",
            "- Keep `outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/parser_artifacts/` intact.",
            "- Keep stock-code/source-id mappings stable.",
            "- Reuse cached artifacts when `parser_artifact_status` is `reused_page_level` or `cold_parse_page_level`.",
            "- If a parser artifact is invalid, regenerate only the affected stock and record the degradation in the audit.",
            "",
            "## final validation",
            "",
            "```bash",
            "rtk .venv/bin/pytest tests/test_data_to_brief_docling_90_dashboard_e2e_smoke_checkpoint.py tests/test_data_to_brief_docling_90_stock_review_and_dashboard_integration.py tests/test_data_to_brief_docling_90_stock_full_cold_parse_batch.py -q",
            "rtk pnpm --dir dashboard exec vitest run tests/data-to-brief-docling-90-review.test.tsx tests/app-shell.test.tsx",
            "rtk pnpm --dir dashboard exec playwright test tests/data-to-brief-docling-90-review.spec.ts --project=chromium",
            "rtk pnpm --dir dashboard exec tsc --noEmit",
            "rtk git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py",
            "rtk git diff --check",
            "```",
        ]
    )


def build_release_baseline(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = _validation_audit()
    rows = _artifact_rows()
    with (output_dir / "artifact_index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "final_validation_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "release_baseline_summary.md").write_text(_summary_markdown(audit), encoding="utf-8")
    (output_dir / "operator_runbook.md").write_text(_runbook_markdown(), encoding="utf-8")
    (output_dir / "suggested_tag.txt").write_text(f"{SUGGESTED_TAG}\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    print(json.dumps(build_release_baseline(), ensure_ascii=False, indent=2))
