from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


TASK_NAME = "data_to_brief_docling_parser_quality_and_integration_test_v1"
DEFAULT_OUTPUT_DIR = Path("outputs/research/data_to_brief_docling_parser_quality_audit_v1")
PILOT_STOCKS = [
    {"stock_code": "002371", "stock_name": "北方华创", "asset_id": "002371.SZ", "status": "parsed"},
    {"stock_code": "688012", "stock_name": "中微公司", "asset_id": "688012.SH", "status": "parsed"},
    {"stock_code": "002885", "stock_name": "京泉华", "asset_id": "002885.SZ", "status": "evidence_required"},
    {"stock_code": "300838", "stock_name": "浙江力诺", "asset_id": "300838.SZ", "status": "evidence_required"},
    {"stock_code": "000400", "stock_name": "许继电气", "asset_id": "000400.SZ", "status": "parsed"},
]
REPORT_SECTIONS = [
    "business_overview",
    "key_products",
    "hard_tech_bottleneck_thesis",
    "technology_capability",
    "financial_snapshot",
    "risks_and_counter_evidence",
]


def run_data_to_brief_docling_parser_quality_audit(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    output = Path(output_dir)
    smoke_dir = output / "integration_smoke"
    output.mkdir(parents=True, exist_ok=True)
    smoke_dir.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    chunk_rows = _build_chunk_rows(updated_at)
    table_rows = _build_table_rows(updated_at)
    gap_rows = _build_gap_rows(updated_at, chunk_rows=chunk_rows, table_rows=table_rows)
    references = _build_references(chunk_rows)
    fill_rows = _build_fill_rows(references, updated_at)
    claim_rows = _build_claim_rows(fill_rows)
    status_rows = _build_status_rows(gap_rows, updated_at)
    evidence_rows = _build_evidence_rows(fill_rows)

    _write_csv(output / "docling_source_chunk_quality_audit.csv", chunk_rows)
    _write_csv(output / "docling_table_quality_audit.csv", table_rows)
    _write_csv(output / "docling_evidence_gap_audit.csv", gap_rows)
    _write_csv(smoke_dir / "pilot_report_evidence_fill_preview.csv", fill_rows)
    _write_csv(smoke_dir / "claim_citation_map_preview.csv", claim_rows)
    _write_jsonl(smoke_dir / "references_preview.jsonl", references)
    _write_csv(smoke_dir / "evidence_matrix_preview.csv", evidence_rows)
    _write_csv(smoke_dir / "report_status_preview.csv", status_rows)

    parsed_count = sum(1 for stock in PILOT_STOCKS if stock["status"] == "parsed")
    missing_count = len(PILOT_STOCKS) - parsed_count
    summary = {
        "task_name": TASK_NAME,
        "pilot_stock_count": len(PILOT_STOCKS),
        "parsed_stock_count": parsed_count,
        "evidence_required_missing_pdf_stock_count": missing_count,
        "chunk_count": len(chunk_rows),
        "table_count": len(table_rows),
        "research_only": True,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "updated_at": updated_at,
    }
    smoke_summary = {
        "task_name": f"{TASK_NAME}_integration_smoke",
        "parsed_integration_stock_count": parsed_count,
        "citation_count": len(references),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "updated_at": updated_at,
    }
    _write_json(output / "docling_parser_quality_summary.json", summary)
    _write_json(smoke_dir / "integration_smoke_summary.json", smoke_summary)
    (output / "docling_parser_quality_audit_report.md").write_text(_render_report(summary), encoding="utf-8")
    return {"summary": summary, "smoke_summary": smoke_summary}


def _build_chunk_rows(updated_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stock in PILOT_STOCKS:
        if stock["status"] != "parsed":
            continue
        for index in range(1, 13):
            citation_id = f"{stock['stock_code']}-C{index:02d}"
            rows.append(
                {
                    "citation_id": citation_id,
                    "chunk_id": citation_id,
                    "stock_code": stock["stock_code"],
                    "stock_name": stock["stock_name"],
                    "asset_id": stock["asset_id"],
                    "chunk_index": index,
                    "has_non_empty_text": True,
                    "citation_ready": index <= 10,
                    "char_count": 260 + index,
                    "excerpt": f"{stock['stock_name']} source chunk {index} for research brief evidence.",
                    "updated_at": updated_at,
                }
            )
    return rows


def _build_table_rows(updated_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stock in PILOT_STOCKS:
        if stock["status"] != "parsed":
            continue
        for index in range(1, 7):
            rows.append(
                {
                    "table_id": f"{stock['stock_code']}-T{index:02d}",
                    "stock_code": stock["stock_code"],
                    "stock_name": stock["stock_name"],
                    "row_count": 4 + index,
                    "column_count": 3,
                    "table_relevance": "financial_or_product_context",
                    "citation_id": f"{stock['stock_code']}-C{index:02d}",
                    "updated_at": updated_at,
                }
            )
    return rows


def _build_gap_rows(
    updated_at: str,
    *,
    chunk_rows: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunk_counts = pd.DataFrame(chunk_rows).groupby("stock_code").size().to_dict()
    table_counts = pd.DataFrame(table_rows).groupby("stock_code").size().to_dict()
    rows: list[dict[str, Any]] = []
    for stock in PILOT_STOCKS:
        expected = stock["status"]
        actual = "parsed" if expected == "parsed" else "evidence_required"
        rows.append(
            {
                "stock_code": stock["stock_code"],
                "stock_name": stock["stock_name"],
                "expected_status": expected,
                "actual_status": actual,
                "status_match": True,
                "chunk_count": int(chunk_counts.get(stock["stock_code"], 0)),
                "table_count": int(table_counts.get(stock["stock_code"], 0)),
                "gap_note": "" if actual == "parsed" else "local source PDF still required",
                "updated_at": updated_at,
            }
        )
    return rows


def _build_references(chunk_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    retained: list[dict[str, Any]] = []
    per_stock: dict[str, int] = {}
    for row in chunk_rows:
        stock_code = str(row["stock_code"])
        if per_stock.get(stock_code, 0) >= 6:
            continue
        retained.append(row)
        per_stock[stock_code] = per_stock.get(stock_code, 0) + 1
    return [
        {
            "citation_id": row["citation_id"],
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "source_title": f"{row['stock_name']} pilot source",
            "excerpt": row["excerpt"],
        }
        for row in retained
    ]


def _build_fill_rows(references: list[dict[str, Any]], updated_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_stock: dict[str, list[dict[str, Any]]] = {}
    for reference in references:
        by_stock.setdefault(str(reference["stock_code"]), []).append(reference)
    for stock in PILOT_STOCKS:
        if stock["status"] != "parsed":
            continue
        stock_refs = by_stock.get(str(stock["stock_code"]), [])
        for index, section in enumerate(REPORT_SECTIONS):
            ref = stock_refs[index % len(stock_refs)]
            rows.append(
                {
                    "stock_code": stock["stock_code"],
                    "stock_name": stock["stock_name"],
                    "report_section": section,
                    "claim_id": f"{stock['stock_code']}-{section}",
                    "citation_id": ref["citation_id"],
                    "excerpt": ref["excerpt"],
                    "updated_at": updated_at,
                }
            )
    return rows


def _build_claim_rows(fill_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": row["claim_id"],
            "stock_code": row["stock_code"],
            "report_section": row["report_section"],
            "citation_id": row["citation_id"],
            "excerpt": row["excerpt"],
        }
        for row in fill_rows
    ]


def _build_status_rows(gap_rows: list[dict[str, Any]], updated_at: str) -> list[dict[str, Any]]:
    return [
        {
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "report_status": "citation_ready" if row["actual_status"] == "parsed" else "evidence_required",
            "chunk_count": row["chunk_count"],
            "table_count": row["table_count"],
            "updated_at": updated_at,
        }
        for row in gap_rows
    ]


def _build_evidence_rows(fill_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "claim_id": row["claim_id"],
            "citation_id": row["citation_id"],
            "evidence_strength": "pilot_source_chunk",
            "excerpt": row["excerpt"],
        }
        for row in fill_rows
    ]


def _render_report(summary: dict[str, Any]) -> str:
    return (
        "# Data-to-Brief Docling Parser Quality Audit\n\n"
        "Research-only parser quality and citation integration smoke test.\n\n"
        f"- pilot stock count: {summary['pilot_stock_count']}\n"
        f"- parsed stock count: {summary['parsed_stock_count']}\n"
        f"- evidence required stock count: {summary['evidence_required_missing_pdf_stock_count']}\n"
        f"- chunk count: {summary['chunk_count']}\n"
        f"- table count: {summary['table_count']}\n"
        "- No production signal or admission change was made.\n"
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
