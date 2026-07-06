from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_dashboard_e2e_smoke_and_release_checkpoint_v1"
PAYLOAD_PATH = (
    PROJECT_ROOT
    / "outputs/research/data_to_brief_docling_90_stock_review_and_dashboard_integration_v1/dashboard_payload.json"
)
FRONTEND_COMPONENT = PROJECT_ROOT / "dashboard/src/components/DataToBriefDocling90ReviewWorkspace.tsx"
APP_SHELL = PROJECT_ROOT / "dashboard/src/components/AppShell.tsx"
FORBIDDEN_CONTROL_PATTERNS = [
    "入选策略",
    "生成信号",
    "加入准入",
    "Apply to production",
    "Promote to signal",
    "Enable admission",
]
FORBIDDEN_RECOMMENDATION_PATTERNS = [
    "buy recommendation",
    "sell recommendation",
    "target price",
    "买入建议",
    "卖出建议",
    "目标价建议",
]
REQUIRED_STOCK_FIELDS = {
    "stock_code",
    "stock_name",
    "report_status",
    "parser_artifact_status",
    "citation_claim_count",
    "page_level_citation_count",
    "source_level_citation_count",
    "table_row_count",
    "table_provenance_status",
    "report_html_path",
    "report_pdf_path",
    "evidence_matrix_path",
    "claim_citation_map_path",
    "sources_jsonl_path",
    "allowed_for_signal",
    "allowed_for_admission",
}


def _load_payload() -> dict[str, Any]:
    if not PAYLOAD_PATH.exists():
        raise FileNotFoundError(f"dashboard payload missing: {PAYLOAD_PATH}")
    return json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))


def _api_smoke(payload: dict[str, Any]) -> dict[str, Any]:
    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/research/data-to-brief/docling-90")
    response_payload = response.json() if response.status_code == 200 else {}
    missing_required = 0
    for row in response_payload.get("per_stock", []):
        missing_required += len([field for field in REQUIRED_STOCK_FIELDS if field not in row])
    counts_match = all(
        response_payload.get(key) == payload.get(key)
        for key in [
            "stock_count",
            "report_success_count",
            "evidence_required_count",
            "citation_claim_count",
            "page_level_citation_count",
            "source_level_citation_count",
            "table_row_count",
            "table_provenance_full_count",
            "parser_artifact_ready_count",
        ]
    )
    return {
        "api_route": "/api/research/data-to-brief/docling-90",
        "api_status_code": response.status_code,
        "stock_count": int(response_payload.get("stock_count", 0)),
        "report_success_count": int(response_payload.get("report_success_count", 0)),
        "evidence_required_count": int(response_payload.get("evidence_required_count", 0)),
        "citation_claim_count": int(response_payload.get("citation_claim_count", 0)),
        "page_level_citation_count": int(response_payload.get("page_level_citation_count", 0)),
        "source_level_citation_count": int(response_payload.get("source_level_citation_count", 0)),
        "table_row_count": int(response_payload.get("table_row_count", 0)),
        "parser_artifact_ready_count": int(response_payload.get("parser_artifact_ready_count", 0)),
        "missing_required_field_count": missing_required,
        "summary_counts_match_payload": counts_match,
        "allowed_for_signal": bool(response_payload.get("allowed_for_signal")),
        "allowed_for_admission": bool(response_payload.get("allowed_for_admission")),
        "production_update": bool(response_payload.get("production_update")),
        "api_smoke_passed": response.status_code == 200
        and int(response_payload.get("stock_count", 0)) == 90
        and missing_required == 0
        and counts_match,
    }


def _dashboard_static_smoke(payload: dict[str, Any]) -> dict[str, Any]:
    component_text = FRONTEND_COMPONENT.read_text(encoding="utf-8")
    shell_text = APP_SHELL.read_text(encoding="utf-8")
    return {
        "frontend_route": "/research/data-to-brief/docling-90",
        "frontend_route_declared": "/research/data-to-brief/docling-90" in shell_text,
        "dashboard_component": str(FRONTEND_COMPONENT),
        "dashboard_payload_rows": len(payload.get("per_stock", [])),
        "summary_counts_match_payload": payload.get("stock_count") == len(payload.get("per_stock", [])),
        "table_declared": "Docling 90-stock review table" in component_text,
        "filter_controls_declared": "Filter stocks" in component_text
        and all(value in component_text for value in ["warnings", "parser_ready", "citation_ready", "table_full"]),
        "expandable_detail_declared": "citation detail" in component_text and "page locator coverage" in component_text,
        "artifact_links_declared": all(
            value in component_text for value in ["report_html_path", "report_pdf_path", "evidence_matrix_path", "claim_citation_map_path"]
        ),
        "no_docling_parse_trigger": "docling" in component_text.lower() and "parse(" not in component_text,
        "browser_smoke_note": "Run dashboard/tests/data-to-brief-docling-90-review.spec.ts for browser screenshot validation.",
    }


def _research_boundary(payload: dict[str, Any]) -> dict[str, Any]:
    component_text = FRONTEND_COMPONENT.read_text(encoding="utf-8")
    shell_text = APP_SHELL.read_text(encoding="utf-8")
    combined = f"{component_text}\n{shell_text}"
    forbidden_control_hits = [
        pattern for pattern in FORBIDDEN_CONTROL_PATTERNS if re.search(re.escape(pattern), combined, flags=re.IGNORECASE)
    ]
    recommendation_hits = [
        pattern for pattern in FORBIDDEN_RECOMMENDATION_PATTERNS if re.search(re.escape(pattern), combined, flags=re.IGNORECASE)
    ]
    rows = payload.get("per_stock", [])
    allowed_signal_count = sum(1 for row in rows if row.get("allowed_for_signal"))
    allowed_admission_count = sum(1 for row in rows if row.get("allowed_for_admission"))
    return {
        "research_only": bool(payload.get("research_only")),
        "allowed_for_signal_count": allowed_signal_count,
        "allowed_for_admission_count": allowed_admission_count,
        "payload_allowed_for_signal": bool(payload.get("allowed_for_signal")),
        "payload_allowed_for_admission": bool(payload.get("allowed_for_admission")),
        "production_update": bool(payload.get("production_update")),
        "forbidden_control_hits": forbidden_control_hits,
        "forbidden_control_hit_count": len(forbidden_control_hits),
        "recommendation_language_hits": recommendation_hits,
        "recommendation_language_hit_count": len(recommendation_hits),
        "research_only_boundary_passed": allowed_signal_count == 0
        and allowed_admission_count == 0
        and not bool(payload.get("allowed_for_signal"))
        and not bool(payload.get("allowed_for_admission"))
        and not bool(payload.get("production_update"))
        and not forbidden_control_hits
        and not recommendation_hits,
    }


def _summary(api: dict[str, Any], dashboard: dict[str, Any], boundary: dict[str, Any], acceptance_decision: str) -> str:
    return "\n".join(
        [
            "# Data-to-Brief Docling 90 Dashboard E2E Smoke and Release Checkpoint v1",
            "",
            f"- api_status_code: {api['api_status_code']}",
            f"- stock_count: {api['stock_count']}",
            f"- report_success_count: {api['report_success_count']}",
            f"- evidence_required_count: {api['evidence_required_count']}",
            f"- citation_claim_count: {api['citation_claim_count']}",
            f"- page_level_citation_count: {api['page_level_citation_count']}",
            f"- source_level_citation_count: {api['source_level_citation_count']}",
            f"- dashboard_route: {dashboard['frontend_route']}",
            f"- dashboard_payload_rows: {dashboard['dashboard_payload_rows']}",
            f"- filter_controls_declared: {str(dashboard['filter_controls_declared']).lower()}",
            f"- expandable_detail_declared: {str(dashboard['expandable_detail_declared']).lower()}",
            f"- allowed_for_signal_count: {boundary['allowed_for_signal_count']}",
            f"- allowed_for_admission_count: {boundary['allowed_for_admission_count']}",
            f"- forbidden_control_hit_count: {boundary['forbidden_control_hit_count']}",
            f"- recommendation_language_hit_count: {boundary['recommendation_language_hit_count']}",
            f"- acceptance_decision: {acceptance_decision}",
            "",
            "No Docling cold parse was triggered. This checkpoint uses existing dashboard payload and batch artifacts.",
        ]
    )


def build_release_checkpoint(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = _load_payload()
    api = _api_smoke(payload)
    dashboard = _dashboard_static_smoke(payload)
    boundary = _research_boundary(payload)
    acceptance = (
        "ready_for_read_only_release_checkpoint"
        if api["api_smoke_passed"]
        and dashboard["frontend_route_declared"]
        and dashboard["summary_counts_match_payload"]
        and dashboard["filter_controls_declared"]
        and dashboard["expandable_detail_declared"]
        and boundary["research_only_boundary_passed"]
        else "release_checkpoint_needs_attention"
    )
    envelope = {
        "task_name": "data_to_brief_docling_90_dashboard_e2e_smoke_and_release_checkpoint_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api": api,
        "dashboard": dashboard,
        "research_only_boundary": boundary,
        "acceptance_decision": acceptance,
    }
    (output_dir / "api_smoke_audit.json").write_text(json.dumps(api, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "dashboard_e2e_smoke_audit.json").write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "research_only_boundary_audit.json").write_text(
        json.dumps(boundary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "release_checkpoint_summary.md").write_text(_summary(api, dashboard, boundary, acceptance), encoding="utf-8")
    return envelope


if __name__ == "__main__":
    print(json.dumps(build_release_checkpoint(), ensure_ascii=False, indent=2))
