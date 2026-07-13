from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.data_to_brief_docling_parser_poc import (
    _docling_text_items,
    _recover_chunk_provenance,
    _safe_text,
    build_chunks,
    build_docling_install_smoke,
    parse_with_docling,
)
from stock_research.data_to_brief_backfill_primary_source_text_first_parse import _stock_code
from stock_research.tech_bottleneck_review_universe_report_pdf_docling_parse import (
    _safe_frame,
    _strategy_diff_clean,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_report_pdf_targeted_docling_fallback_v1"
PREVIOUS_PARSE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_report_pdf_docling_parse_v1"
FRONTEND_DATASET = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME

DoclingParser = Callable[[Path], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame = _read_csv(path)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame


def _target_failures(failures: pd.DataFrame) -> pd.DataFrame:
    if failures.empty:
        return failures.copy()
    targets = failures[
        failures["parse_status"].astype(str).eq("evidence_required")
        & failures["source_path"].astype(str).str.len().gt(0)
    ].copy()
    targets = targets[targets["source_path"].map(lambda value: Path(str(value)).exists())]
    return targets.sort_values(["stock_code", "source_path"]).reset_index(drop=True)


def _fallback_one(
    row: dict[str, Any],
    *,
    source_index: int,
    docling_parser: DoclingParser,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updated_at = _now()
    pdf_path = Path(str(row.get("source_path") or ""))
    docling = docling_parser(pdf_path)
    base = {
        "stock_code": _stock_code(row.get("stock_code")),
        "stock_name": _safe_text(row.get("stock_name")),
        "source_type": "broker_report_pdf",
        "source_title": _safe_text(row.get("source_title")) or pdf_path.name,
        "source_path": str(pdf_path),
        "source_id": f"targeted-docling-report-{_stock_code(row.get('stock_code'))}-{source_index}",
        "collection_source_id": f"targeted-docling-report-{_stock_code(row.get('stock_code'))}-{source_index}",
        "source_index": source_index,
        "parser": "docling",
        "parser_mode": "targeted_docling_layout_fallback",
        "updated_at": updated_at,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }
    manifest = {
        **base,
        "docling_status": _safe_text(docling.get("status")),
        "parse_status": "parsed" if docling.get("status") == "parsed" else _safe_text(docling.get("status")) or "parse_error",
        "docling_markdown_chars": len(_safe_text(docling.get("markdown"))),
        "docling_error_type": _safe_text(docling.get("error_type")),
        "docling_error_message": _safe_text(docling.get("error_message"))[:500],
        "page_provenance_ready": False,
        "citation_granularity": "",
        "fallback_success": False,
    }
    if docling.get("status") != "parsed":
        return manifest, []

    docling_json = docling.get("json") or {}
    text_items = _docling_text_items(docling_json)
    chunks: list[dict[str, Any]] = []
    for chunk_index, chunk_text in enumerate(build_chunks(_safe_text(docling.get("markdown"))), start=1):
        provenance = _recover_chunk_provenance(chunk_text, text_items)
        citation_id = f"TD{source_index}C{chunk_index}"
        citation_granularity = "page_level" if provenance["page_locator"] else "source_level"
        chunks.append(
            {
                **base,
                "citation_id": citation_id,
                "chunk_id": f"{base['stock_code']}-TD{source_index}-C{chunk_index}",
                "chunk_index": chunk_index,
                "page_start": provenance["page_start"],
                "page_end": provenance["page_end"],
                "page_locator": provenance["page_locator"],
                "char_count": len(chunk_text),
                "chunk_text_length": len(chunk_text),
                "excerpt": chunk_text[:320].replace("\n", " "),
                "chunk_text": chunk_text,
                "evidence_text": chunk_text,
                "evidence_claim_type": "targeted_docling_broker_report_text",
                "bbox": provenance["bbox"],
                "docling_item_ref": provenance["docling_item_ref"],
                "section_heading": provenance["section_heading"],
                "parse_status": "parsed",
                "docling_status": "parsed",
                "citation_granularity": citation_granularity,
                "citation_ready": bool(provenance["page_locator"]),
                "issue_warning": "" if provenance["page_locator"] else "missing_page_locator",
            }
        )
    manifest["page_provenance_ready"] = any(chunk["citation_granularity"] == "page_level" for chunk in chunks)
    manifest["citation_granularity"] = "page_level" if manifest["page_provenance_ready"] else "source_level"
    manifest["fallback_success"] = bool(chunks)
    return manifest, chunks


def _build_page_citations(chunks: pd.DataFrame) -> pd.DataFrame:
    if chunks.empty:
        return pd.DataFrame(
            columns=[
                "citation_id",
                "stock_code",
                "stock_name",
                "source_file",
                "source_type",
                "source_title",
                "page",
                "evidence_text",
                "evidence_claim_type",
                "citation_quality",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    page_chunks = chunks[chunks["citation_granularity"].eq("page_level")].copy()
    rows: list[dict[str, Any]] = []
    for _, row in page_chunks.iterrows():
        rows.append(
            {
                "citation_id": row.get("citation_id", ""),
                "stock_code": row.get("stock_code", ""),
                "stock_name": row.get("stock_name", ""),
                "source_file": row.get("source_path", ""),
                "source_type": row.get("source_type", "broker_report_pdf"),
                "source_title": row.get("source_title", ""),
                "page": row.get("page_start", ""),
                "evidence_text": row.get("evidence_text", row.get("chunk_text", "")),
                "evidence_claim_type": row.get("evidence_claim_type", ""),
                "citation_quality": "page_level",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def _build_failures(manifest: pd.DataFrame, previous_failures: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not manifest.empty:
        unresolved = manifest[~manifest["fallback_success"].map(lambda value: str(value).lower() == "true")].copy()
        for _, row in unresolved.iterrows():
            rows.append(
                {
                    "stock_code": row.get("stock_code", ""),
                    "stock_name": row.get("stock_name", ""),
                    "source_type": row.get("source_type", "broker_report_pdf"),
                    "source_title": row.get("source_title", ""),
                    "source_path": row.get("source_path", ""),
                    "parse_status": row.get("parse_status", ""),
                    "gap_type": "docling_fallback_unresolved",
                    "gap_detail": row.get("docling_error_message", "") or "Docling fallback did not produce citation-ready text",
                    "recommended_next_action": "try OCR-specific workflow or collect alternate broker report",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    if not previous_failures.empty:
        missing = previous_failures[previous_failures["parse_status"].eq("missing_report_pdf")].copy()
        for _, row in missing.iterrows():
            rows.append(
                {
                    "stock_code": row.get("stock_code", ""),
                    "stock_name": row.get("stock_name", ""),
                    "source_type": row.get("source_type", "broker_report_pdf"),
                    "source_title": row.get("source_title", ""),
                    "source_path": row.get("source_path", ""),
                    "parse_status": "missing_report_pdf",
                    "gap_type": "missing_report_pdf",
                    "gap_detail": row.get("error_detail", "missing report PDF"),
                    "recommended_next_action": "collect broker report PDF before reassessment if report coverage is required",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    return pd.DataFrame(rows)


def _standardize_existing_chunks(chunks: pd.DataFrame) -> pd.DataFrame:
    if chunks.empty:
        return chunks.copy()
    result = chunks.copy()
    if "evidence_text" not in result.columns:
        result["evidence_text"] = result.get("chunk_text", "")
    if "evidence_claim_type" not in result.columns:
        result["evidence_claim_type"] = "broker_report_text"
    if "source_path" not in result.columns and "source_file" in result.columns:
        result["source_path"] = result["source_file"]
    result["report_evidence_stage"] = "initial_text_first_parse"
    result["research_only"] = True
    result["used_for_signal"] = False
    result["used_for_admission"] = False
    return result


def _build_stock_status(universe: pd.DataFrame, evidence: pd.DataFrame, failures: pd.DataFrame) -> pd.DataFrame:
    evidence_counts = evidence.groupby("stock_code").size().to_dict() if not evidence.empty else {}
    citation_counts = (
        evidence[evidence["citation_granularity"].eq("page_level")].groupby("stock_code").size().to_dict()
        if not evidence.empty and "citation_granularity" in evidence.columns
        else {}
    )
    source_counts = evidence.groupby("stock_code")["source_path"].nunique().to_dict() if not evidence.empty and "source_path" in evidence.columns else {}
    missing_codes = set(failures[failures["gap_type"].eq("missing_report_pdf")]["stock_code"]) if not failures.empty and "gap_type" in failures.columns else set()
    unresolved_codes = set(failures[failures["gap_type"].eq("docling_fallback_unresolved")]["stock_code"]) if not failures.empty and "gap_type" in failures.columns else set()
    rows: list[dict[str, Any]] = []
    for _, row in universe.sort_values("stock_code").iterrows():
        code = _stock_code(row.get("stock_code"))
        if int(evidence_counts.get(code, 0)):
            status = "report_evidence_ready"
        elif code in missing_codes:
            status = "missing_report_pdf"
        elif code in unresolved_codes:
            status = "report_parse_gap_unresolved"
        else:
            status = "report_evidence_not_available"
        rows.append(
            {
                "stock_code": code,
                "stock_name": row.get("stock_name", ""),
                "report_reassessment_input_status": status,
                "broker_report_evidence_count": int(evidence_counts.get(code, 0)),
                "broker_report_page_citation_count": int(citation_counts.get(code, 0)),
                "broker_report_source_count": int(source_counts.get(code, 0)),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "reassessment_performed": False,
                "notes": "broker report evidence prepared for later reassessment; no decision generated",
            }
        )
    return pd.DataFrame(rows)


def _summary(
    *,
    universe: pd.DataFrame,
    targets: pd.DataFrame,
    manifest: pd.DataFrame,
    fallback_chunks: pd.DataFrame,
    fallback_citations: pd.DataFrame,
    existing_chunks: pd.DataFrame,
    reassessment_evidence: pd.DataFrame,
    failures: pd.DataFrame,
    stock_status: pd.DataFrame,
    strategy_clean: bool,
) -> dict[str, Any]:
    unresolved_parse = int(failures["gap_type"].eq("docling_fallback_unresolved").sum()) if not failures.empty else 0
    missing_report = int(failures["gap_type"].eq("missing_report_pdf").sum()) if not failures.empty else 0
    fallback_success = int(manifest["fallback_success"].map(lambda value: str(value).lower() == "true").sum()) if not manifest.empty else 0
    if not strategy_clean:
        acceptance = "blocked_due_to_guardrail_violation"
    elif unresolved_parse:
        acceptance = "conditionally_ready_with_remaining_report_parse_gaps"
    else:
        acceptance = "review_universe_report_reassessment_input_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": int(len(universe)),
        "targeted_fallback_source_count": int(len(targets)),
        "fallback_parse_attempt_count": int(len(manifest)),
        "fallback_parse_success_count": fallback_success,
        "fallback_parse_failure_count": int(len(manifest) - fallback_success),
        "fallback_evidence_chunk_count": int(len(fallback_chunks)),
        "fallback_page_level_citation_count": int(len(fallback_citations)),
        "existing_page_level_report_evidence_count": int(
            existing_chunks["citation_granularity"].eq("page_level").sum()
        )
        if not existing_chunks.empty and "citation_granularity" in existing_chunks.columns
        else 0,
        "reassessment_input_stock_count": int(len(stock_status)),
        "reassessment_input_evidence_count": int(len(reassessment_evidence)),
        "missing_report_pdf_stock_count": missing_report,
        "unresolved_report_parse_gap_count": unresolved_parse,
        "docling_fallback_performed": True,
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "reassessment_performed": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": summary["review_universe_total_count"],
        "targeted_fallback_source_count": summary["targeted_fallback_source_count"],
        "docling_fallback_performed": True,
        "reassessment_input_stock_count": summary["reassessment_input_stock_count"],
        "reassessment_input_evidence_count": summary["reassessment_input_evidence_count"],
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "reassessment_performed": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "acceptance_decision": summary["acceptance_decision"],
    }


def _write_report(output: Path, summary: dict[str, Any]) -> None:
    report = f"""# {TASK_NAME}

## Summary

- review universe: {summary['review_universe_total_count']}
- targeted fallback sources: {summary['targeted_fallback_source_count']}
- fallback success/failure: {summary['fallback_parse_success_count']} / {summary['fallback_parse_failure_count']}
- fallback page-level citations: {summary['fallback_page_level_citation_count']}
- existing report evidence rows: {summary['existing_page_level_report_evidence_count']}
- reassessment input evidence rows: {summary['reassessment_input_evidence_count']}
- missing report PDF stocks: {summary['missing_report_pdf_stock_count']}
- unresolved report parse gaps: {summary['unresolved_report_parse_gap_count']}

## Guardrails

- research-only: true
- Docling fallback performed: true
- reassessment performed: false
- used_for_signal/admission: 0 / 0
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## Acceptance

{summary['acceptance_decision']}
"""
    (output / "tech_bottleneck_review_universe_report_pdf_targeted_docling_fallback_v1_report.md").write_text(
        report,
        encoding="utf-8",
    )


def run(
    *,
    universe_path: Path = FRONTEND_DATASET,
    previous_parse_dir: Path = PREVIOUS_PARSE_DIR,
    output_dir: Path = OUTPUT_DIR,
    docling_parser: DoclingParser = parse_with_docling,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    previous = Path(previous_parse_dir)
    universe = _read_csv(Path(universe_path))
    existing_chunks = _load_csv(
        previous / "review_universe_report_pdf_evidence_chunks.csv",
        ["stock_code", "stock_name", "citation_granularity", "source_path"],
    )
    previous_failures = _load_csv(
        previous / "review_universe_report_pdf_parse_failures.csv",
        ["stock_code", "stock_name", "source_type", "source_title", "source_path", "parse_status", "error_detail"],
    )
    targets = _target_failures(previous_failures)
    smoke = build_docling_install_smoke()
    manifest_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    for source_index, row in enumerate(targets.to_dict("records"), start=1):
        manifest, chunks = _fallback_one(row, source_index=source_index, docling_parser=docling_parser)
        manifest_rows.append(manifest)
        chunk_rows.extend(chunks)
    fallback_manifest = pd.DataFrame(manifest_rows)
    fallback_chunks = pd.DataFrame(chunk_rows)
    fallback_citations = _build_page_citations(fallback_chunks)
    failures = _build_failures(fallback_manifest, previous_failures)
    existing_standardized = _standardize_existing_chunks(existing_chunks)
    if not fallback_chunks.empty:
        fallback_chunks = fallback_chunks.copy()
        fallback_chunks["report_evidence_stage"] = "targeted_docling_fallback"
    reassessment_evidence = pd.concat([existing_standardized, fallback_chunks], ignore_index=True, sort=False)
    stock_status = _build_stock_status(universe, reassessment_evidence, failures)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        universe=universe,
        targets=targets,
        manifest=fallback_manifest,
        fallback_chunks=fallback_chunks,
        fallback_citations=fallback_citations,
        existing_chunks=existing_standardized,
        reassessment_evidence=reassessment_evidence,
        failures=failures,
        stock_status=stock_status,
        strategy_clean=strategy_clean,
    )
    guardrails = _guardrails(summary)

    _write_json(output / "docling_install_smoke.json", smoke)
    _safe_frame(fallback_manifest).to_csv(output / "targeted_docling_fallback_manifest.csv", index=False)
    _safe_frame(fallback_chunks).to_csv(output / "targeted_docling_fallback_evidence_chunks.csv", index=False)
    _safe_frame(fallback_citations).to_csv(output / "targeted_docling_fallback_page_citations.csv", index=False)
    _safe_frame(failures).to_csv(output / "targeted_docling_fallback_failures.csv", index=False)
    _safe_frame(reassessment_evidence).to_csv(output / "review_universe_report_evidence_for_reassessment.csv", index=False)
    _safe_frame(stock_status).to_csv(output / "review_universe_reassessment_input_stock_status.csv", index=False)
    _write_json(output / "targeted_docling_fallback_summary.json", summary)
    _write_json(output / "targeted_docling_fallback_guardrails.json", guardrails)
    _write_report(output, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Target Docling fallback for report parse gaps and build reassessment input.")
    parser.add_argument("--universe-path", type=Path, default=FRONTEND_DATASET)
    parser.add_argument("--previous-parse-dir", type=Path, default=PREVIOUS_PARSE_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    summary = run(
        universe_path=args.universe_path,
        previous_parse_dir=args.previous_parse_dir,
        output_dir=args.output_dir,
    )
    print(f"{TASK_NAME}|acceptance_decision|{summary['acceptance_decision']}")
    print(f"{TASK_NAME}|targeted_fallback_source_count|{summary['targeted_fallback_source_count']}")
    print(f"{TASK_NAME}|fallback_parse_success_count|{summary['fallback_parse_success_count']}")
    print(f"{TASK_NAME}|reassessment_input_evidence_count|{summary['reassessment_input_evidence_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
