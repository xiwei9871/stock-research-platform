from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SOURCE_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_review_and_dashboard_integration_v1"
BATCH_ID = "data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
TASK_NAME = "data_to_brief_docling_90_stock_review_and_dashboard_integration_v1"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"stock_code": str}).assign(stock_code=lambda df: df["stock_code"].map(_stock_code))


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _str(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _read_quality() -> dict[str, Any]:
    quality_path = SOURCE_DIR / "quality_audit.json"
    if not quality_path.exists():
        raise FileNotFoundError(f"missing source quality audit: {quality_path}")
    return json.loads(quality_path.read_text(encoding="utf-8"))


def _merge_review_manifest() -> pd.DataFrame:
    manifest = _read_csv(SOURCE_DIR / "batch_manifest.csv")
    parser = _read_csv(SOURCE_DIR / "parser_artifact_audit.csv")
    reports = _read_csv(SOURCE_DIR / "report_generation_audit.csv")
    citations = _read_csv(SOURCE_DIR / "citation_audit.csv")
    tables = _read_csv(SOURCE_DIR / "table_provenance_audit.csv")

    merged = manifest.merge(
        parser[["stock_code", "parser_artifact_status", "chunk_count", "page_level_chunk_count", "docling_status", "issue_warning"]],
        on="stock_code",
        how="left",
    )
    merged = merged.merge(
        reports[
            [
                "stock_code",
                "blocker_reason",
                "report_md_path",
                "report_html_path",
                "report_pdf_path",
                "evidence_matrix_path",
                "claim_citation_map_path",
                "sources_jsonl_path",
            ]
        ],
        on="stock_code",
        how="left",
    )
    merged = merged.merge(
        citations[
            [
                "stock_code",
                "citation_claim_count",
                "citations_with_page_locator_count",
                "page_level_citation_row_count",
                "source_level_citation_count",
            ]
        ],
        on="stock_code",
        how="left",
    )
    merged = merged.merge(
        tables[
            [
                "stock_code",
                "table_row_count",
                "table_provenance_full_count",
                "table_provenance_partial_count",
                "table_provenance_missing_count",
            ]
        ],
        on="stock_code",
        how="left",
    )
    merged["citation_status"] = merged.apply(
        lambda row: "page_level_ready"
        if int(row.get("citation_claim_count") or 0) == int(row.get("citations_with_page_locator_count") or 0)
        and int(row.get("source_level_citation_count") or 0) == 0
        else "needs_review",
        axis=1,
    )
    merged["table_provenance_status"] = merged.apply(
        lambda row: "full"
        if int(row.get("table_provenance_missing_count") or 0) == 0 and int(row.get("table_provenance_partial_count") or 0) == 0
        else "partial_or_missing",
        axis=1,
    )
    return merged


def _artifact_consistency_audit(manifest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in manifest.iterrows():
        checks = {
            "report_md_exists": Path(_str(row.get("report_md_path"))).exists(),
            "report_html_exists": Path(_str(row.get("report_html_path"))).exists(),
            "report_pdf_exists": Path(_str(row.get("report_pdf_path"))).exists(),
            "evidence_matrix_exists": Path(_str(row.get("evidence_matrix_path"))).exists(),
            "claim_citation_map_exists": Path(_str(row.get("claim_citation_map_path"))).exists(),
            "sources_jsonl_exists": Path(_str(row.get("sources_jsonl_path"))).exists(),
            "parser_artifact_ready": _bool(row.get("parser_artifact_ready")),
            "report_success": _str(row.get("report_status")) != "failed",
            "research_only_guardrails": not _bool(row.get("allowed_for_signal"))
            and not _bool(row.get("allowed_for_admission"))
            and not _bool(row.get("production_update")),
        }
        missing = [name for name, ok in checks.items() if not ok]
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                **checks,
                "artifact_consistency_status": "pass" if not missing else "fail",
                "issue_detail": ";".join(missing),
            }
        )
    return pd.DataFrame(rows)


def _citation_resolution_audit(manifest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, stock in manifest.iterrows():
        claim_path = Path(_str(stock.get("claim_citation_map_path")))
        sources_path = Path(_str(stock.get("sources_jsonl_path")))
        if not claim_path.exists():
            rows.append(
                {
                    "stock_code": stock["stock_code"],
                    "stock_name": stock["stock_name"],
                    "claim_id": "",
                    "citation_id": "",
                    "source_id": "",
                    "page_locator": "",
                    "citation_granularity": "",
                    "reference_found": False,
                    "page_locator_found": False,
                    "unresolved_citation": True,
                    "citation_resolution_status": "missing_claim_map",
                    "issue_detail": str(claim_path),
                }
            )
            continue

        claims = pd.read_csv(claim_path, dtype={"stock_code": str})
        sources = {str(row.get("citation_id")): row for row in _load_jsonl(sources_path)}
        for _, claim in claims.iterrows():
            citation_id = _str(claim.get("citation_id"))
            page_locator = _str(claim.get("page_locator"))
            granularity = _str(claim.get("citation_granularity"))
            ref = sources.get(citation_id)
            unresolved = ref is None or not page_locator or granularity != "page_level"
            rows.append(
                {
                    "stock_code": stock["stock_code"],
                    "stock_name": stock["stock_name"],
                    "claim_id": _str(claim.get("claim_id")),
                    "citation_id": citation_id,
                    "source_id": _str(claim.get("source_id")),
                    "chunk_id": _str(claim.get("chunk_id")),
                    "table_id": _str(claim.get("table_id")),
                    "page_locator": page_locator,
                    "citation_granularity": granularity,
                    "reference_found": ref is not None,
                    "page_locator_found": bool(page_locator),
                    "unresolved_citation": unresolved,
                    "citation_resolution_status": "resolved_page_level" if not unresolved else "unresolved",
                    "issue_detail": "" if not unresolved else "missing_reference_or_page_locator",
                }
            )
    return pd.DataFrame(rows)


def _payload_from_audits(
    manifest: pd.DataFrame,
    consistency: pd.DataFrame,
    citation_resolution: pd.DataFrame,
    quality: dict[str, Any],
) -> dict[str, Any]:
    unresolved_count = int(citation_resolution["unresolved_citation"].sum()) if not citation_resolution.empty else 0
    consistency_fail_count = int((consistency["artifact_consistency_status"] != "pass").sum())
    expected_ready = (
        int(quality.get("stock_count", 0)) == 90
        and int(quality.get("report_success_count", 0)) == 90
        and int(quality.get("evidence_required_count", 0)) == 0
        and int(quality.get("citation_claim_count", 0)) == 1061
        and int(quality.get("page_level_citation_row_count", 0)) == 1061
        and int(quality.get("source_level_citation_count", 0)) == 0
        and unresolved_count == 0
        and consistency_fail_count == 0
        and not bool(quality.get("allowed_for_signal"))
        and not bool(quality.get("allowed_for_admission"))
        and not bool(quality.get("production_update"))
    )
    per_stock = []
    for _, row in manifest.sort_values("stock_code").iterrows():
        warnings = [item for item in [_str(row.get("issue_warning")), _str(row.get("blocker_reason"))] if item]
        per_stock.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "asset_id": _str(row.get("asset_id")),
                "report_status": _str(row.get("report_status")),
                "parser_artifact_status": _str(row.get("parser_artifact_status")),
                "citation_status": _str(row.get("citation_status")),
                "citation_claim_count": int(row.get("citation_claim_count") or 0),
                "page_level_citation_count": int(row.get("page_level_citation_row_count") or 0),
                "source_level_citation_count": int(row.get("source_level_citation_count") or 0),
                "table_row_count": int(row.get("table_row_count") or 0),
                "table_provenance_status": _str(row.get("table_provenance_status")),
                "table_provenance_full_count": int(row.get("table_provenance_full_count") or 0),
                "parser_artifact_ready": _bool(row.get("parser_artifact_ready")),
                "report_md_path": _str(row.get("report_md_path")),
                "report_html_path": _str(row.get("report_html_path")),
                "report_pdf_path": _str(row.get("report_pdf_path")),
                "evidence_matrix_path": _str(row.get("evidence_matrix_path")),
                "claim_citation_map_path": _str(row.get("claim_citation_map_path")),
                "sources_jsonl_path": _str(row.get("sources_jsonl_path")),
                "warnings": warnings,
                "allowed_for_signal": False,
                "allowed_for_admission": False,
                "production_update": False,
            }
        )
    return {
        "task_name": TASK_NAME,
        "batch_id": BATCH_ID,
        "source_output_dir": str(SOURCE_DIR),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "research_only": True,
        "stock_count": int(quality.get("stock_count", len(manifest))),
        "report_success_count": int(quality.get("report_success_count", 0)),
        "evidence_required_count": int(quality.get("evidence_required_count", 0)),
        "citation_claim_count": int(quality.get("citation_claim_count", len(citation_resolution))),
        "page_level_citation_count": int(quality.get("page_level_citation_row_count", 0)),
        "source_level_citation_count": int(quality.get("source_level_citation_count", 0)),
        "table_row_count": int(quality.get("table_row_count", 0)),
        "table_provenance_full_count": int(quality.get("table_provenance_full_count", 0)),
        "parser_artifact_ready_count": int(quality.get("parser_artifact_ready_count", 0)),
        "cold_parse_runtime_seconds": float(quality.get("cold_parse_runtime_seconds", 0.0)),
        "cached_postprocess_runtime_seconds": float(quality.get("cached_postprocess_runtime_seconds", 0.0)),
        "unresolved_citation_count": unresolved_count,
        "artifact_consistency_fail_count": consistency_fail_count,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "acceptance_decision": "ready_for_read_only_dashboard_review" if expected_ready else "review_dashboard_integration_needs_attention",
        "per_stock": per_stock,
    }


def build_review_dashboard_outputs(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    quality = _read_quality()
    manifest = _merge_review_manifest()
    consistency = _artifact_consistency_audit(manifest)
    citation_resolution = _citation_resolution_audit(manifest)
    payload = _payload_from_audits(manifest, consistency, citation_resolution, quality)

    manifest.to_csv(output_dir / "review_manifest.csv", index=False)
    consistency.to_csv(output_dir / "artifact_consistency_audit.csv", index=False)
    citation_resolution.to_csv(output_dir / "citation_resolution_audit.csv", index=False)
    (output_dir / "dashboard_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "summary.md").write_text(_summary_markdown(payload), encoding="utf-8")
    return payload


def load_dashboard_payload() -> dict[str, Any]:
    payload_path = OUTPUT_DIR / "dashboard_payload.json"
    if not payload_path.exists():
        return build_review_dashboard_outputs()
    return json.loads(payload_path.read_text(encoding="utf-8"))


def _summary_markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Data-to-Brief Docling 90-Stock Review",
            "",
            "Research-only read-only dashboard integration package.",
            "",
            f"- stock_count: {payload['stock_count']}",
            f"- report_success_count: {payload['report_success_count']}",
            f"- evidence_required_count: {payload['evidence_required_count']}",
            f"- citation_claim_count: {payload['citation_claim_count']}",
            f"- page_level_citation_count: {payload['page_level_citation_count']}",
            f"- source_level_citation_count: {payload['source_level_citation_count']}",
            f"- unresolved_citation_count: {payload['unresolved_citation_count']}",
            f"- table_row_count: {payload['table_row_count']}",
            f"- table_provenance_full_count: {payload['table_provenance_full_count']}",
            f"- parser_artifact_ready_count: {payload['parser_artifact_ready_count']}",
            f"- cold_parse_runtime_seconds: {payload['cold_parse_runtime_seconds']}",
            f"- cached_postprocess_runtime_seconds: {payload['cached_postprocess_runtime_seconds']}",
            f"- allowed_for_signal: {str(payload['allowed_for_signal']).lower()}",
            f"- allowed_for_admission: {str(payload['allowed_for_admission']).lower()}",
            f"- production_update: {str(payload['production_update']).lower()}",
            f"- acceptance_decision: {payload['acceptance_decision']}",
            "",
            "No production signal, admission, scoring, or strategy integration was added.",
        ]
    )


if __name__ == "__main__":
    print(json.dumps(build_review_dashboard_outputs(), ensure_ascii=False, indent=2))
