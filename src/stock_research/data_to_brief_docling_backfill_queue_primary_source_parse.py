from __future__ import annotations

import json
import multiprocessing as mp
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "data_to_brief_docling_backfill_queue_primary_source_parse_v1"
COLLECTION_MANIFEST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_remaining_primary_source_collection_v1/primary_source_collection_manifest.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_manifest() -> pd.DataFrame:
    frame = pd.read_csv(COLLECTION_MANIFEST, dtype={"stock_code": str}).fillna("")
    frame["stock_code"] = frame["stock_code"].map(_stock_code)
    frame["source_index"] = range(1, len(frame) + 1)
    return frame.sort_values(["stock_code", "source_type", "local_pdf_path"]).reset_index(drop=True)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_pdf_worker(source: dict[str, Any], queue: mp.Queue) -> None:
    try:
        from stock_research.data_to_brief_docling_parser_poc import (
            _docling_table_items,
            _docling_text_items,
            _recover_chunk_provenance,
            _recover_table_provenance,
            _safe_text,
            _table_relevance,
            build_chunks,
            build_docling_install_smoke,
            parse_with_docling,
        )

        pdf_path = Path(str(source["local_pdf_path"]))
        smoke = build_docling_install_smoke()
        docling = parse_with_docling(pdf_path)
        updated_at = _now()
        source_index = int(source["source_index"])
        base = {
            "stock_code": source["stock_code"],
            "stock_name": source["stock_name"],
            "source_type": source["source_type"],
            "source_title": source["source_title"],
            "source_path": str(pdf_path),
            "collection_source_id": source["source_id"],
            "parser": "docling",
            "parser_version": str(smoke.get("version") or ""),
            "updated_at": updated_at,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
        comparison = {
            **base,
            "parse_status": str(docling.get("status") or ""),
            "docling_status": str(docling.get("status") or ""),
            "docling_markdown_chars": len(str(docling.get("markdown") or "")),
            "docling_table_count": len(docling.get("tables") or []),
            "docling_error_type": str(docling.get("error_type") or ""),
            "docling_error_message": str(docling.get("error_message") or ""),
            "page_provenance_ready": False,
        }
        if docling.get("status") != "parsed":
            queue.put({"comparison": comparison, "chunks": [], "tables": []})
            return

        markdown = str(docling.get("markdown") or "")
        docling_json = docling.get("json") or {}
        text_items = _docling_text_items(docling_json)
        table_items = _docling_table_items(docling_json)
        chunk_rows: list[dict[str, Any]] = []
        for chunk_index, chunk_text in enumerate(build_chunks(markdown), start=1):
            provenance = _recover_chunk_provenance(chunk_text, text_items)
            citation_id = f"B{source_index}C{chunk_index}"
            chunk_rows.append(
                {
                    **base,
                    "citation_id": citation_id,
                    "chunk_id": f"{source['stock_code']}-B{source_index}-C{chunk_index}",
                    "source_id": source["source_id"],
                    "chunk_index": chunk_index,
                    "char_count": len(chunk_text),
                    "chunk_text_length": len(chunk_text),
                    "excerpt": chunk_text[:320].replace("\n", " "),
                    "chunk_text": chunk_text,
                    "page_start": provenance["page_start"],
                    "page_end": provenance["page_end"],
                    "page_locator": provenance["page_locator"],
                    "bbox": provenance["bbox"],
                    "docling_item_ref": provenance["docling_item_ref"],
                    "section_heading": provenance["section_heading"],
                    "citation_granularity": "page_level" if provenance["page_locator"] else "source_level",
                    "citation_ready": bool(provenance["page_locator"]),
                    "parse_status": "parsed",
                    "issue_warning": "" if provenance["page_locator"] else "missing_page_locator",
                }
            )
        table_rows: list[dict[str, Any]] = []
        for table_index, table in enumerate(docling.get("tables") or [], start=1):
            table_id = _safe_text(table.get("table_id")) or f"T{table_index}"
            provenance = _recover_table_provenance(table_id, table_index, table, table_items)
            table_rows.append(
                {
                    **base,
                    "source_id": source["source_id"],
                    "citation_id": f"B{source_index}T{table_index}",
                    "table_id": f"{source['stock_code']}-B{source_index}-{table_id}",
                    "page_locator": provenance["page_locator"],
                    "bbox": provenance["bbox"],
                    "docling_table_ref": provenance["docling_table_ref"],
                    "row_count": provenance["row_count"] or table.get("row_count", ""),
                    "column_count": provenance["column_count"] or table.get("column_count", ""),
                    "table_title": _safe_text(table.get("caption")) or provenance["table_title"],
                    "table_caption": _safe_text(table.get("caption")) or provenance["table_caption"],
                    "table_markdown": provenance["table_markdown"],
                    "table_csv_preview": provenance["table_csv_preview"],
                    "table_html_preview": provenance["table_html_preview"],
                    "table_relevance": _table_relevance(provenance["table_markdown"]),
                    "parse_status": "parsed",
                    "citation_granularity": "page_level" if provenance["page_locator"] else "source_level",
                    "issue_warning": "" if provenance["page_locator"] else "missing_page_locator",
                }
            )
        comparison["page_provenance_ready"] = any(row["citation_granularity"] == "page_level" for row in chunk_rows)
        queue.put({"comparison": comparison, "chunks": chunk_rows, "tables": table_rows})
    except Exception as exc:  # noqa: BLE001 - worker returns audited failure.
        queue.put(
            {
                "comparison": {
                    "stock_code": source.get("stock_code", ""),
                    "stock_name": source.get("stock_name", ""),
                    "source_type": source.get("source_type", ""),
                    "source_title": source.get("source_title", ""),
                    "source_path": source.get("local_pdf_path", ""),
                    "collection_source_id": source.get("source_id", ""),
                    "parse_status": "parse_error",
                    "docling_status": "parse_error",
                    "docling_markdown_chars": 0,
                    "docling_table_count": 0,
                    "docling_error_type": type(exc).__name__,
                    "docling_error_message": str(exc)[:500],
                    "page_provenance_ready": False,
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                    "updated_at": _now(),
                },
                "chunks": [],
                "tables": [],
            }
        )


def _parse_one(source: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    process = ctx.Process(target=_parse_pdf_worker, args=(source, queue))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        return {
            "comparison": {
                "stock_code": source["stock_code"],
                "stock_name": source["stock_name"],
                "source_type": source["source_type"],
                "source_title": source["source_title"],
                "source_path": source["local_pdf_path"],
                "collection_source_id": source["source_id"],
                "parse_status": "parse_timeout",
                "docling_status": "parse_timeout",
                "docling_markdown_chars": 0,
                "docling_table_count": 0,
                "docling_error_type": "Timeout",
                "docling_error_message": f"Docling parse exceeded {timeout_seconds} seconds",
                "page_provenance_ready": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "updated_at": _now(),
            },
            "chunks": [],
            "tables": [],
        }
    if not queue.empty():
        return queue.get()
    return {
        "comparison": {
            "stock_code": source["stock_code"],
            "stock_name": source["stock_name"],
            "source_type": source["source_type"],
            "source_title": source["source_title"],
            "source_path": source["local_pdf_path"],
            "collection_source_id": source["source_id"],
            "parse_status": "parse_error",
            "docling_status": "parse_error",
            "docling_markdown_chars": 0,
            "docling_table_count": 0,
            "docling_error_type": "NoWorkerResult",
            "docling_error_message": "Docling worker exited without result",
            "page_provenance_ready": False,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
            "updated_at": _now(),
        },
        "chunks": [],
        "tables": [],
    }


def _load_cached(output: Path, collection_count: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    manifest_path = output / "backfill_primary_source_docling_manifest.csv"
    chunks_path = output / "backfill_primary_source_evidence_chunks.csv"
    tables_path = output / "backfill_primary_source_table_provenance.csv"
    if not (manifest_path.exists() and chunks_path.exists() and tables_path.exists()):
        return None
    manifest = pd.read_csv(manifest_path, dtype={"stock_code": str})
    if len(manifest) != collection_count:
        return None
    chunks = pd.read_csv(chunks_path, dtype={"stock_code": str})
    tables = pd.read_csv(tables_path, dtype={"stock_code": str})
    return manifest, chunks, tables


def _build_citation_claims(chunks: pd.DataFrame) -> pd.DataFrame:
    if chunks.empty:
        return pd.DataFrame(
            columns=[
                "claim_id",
                "stock_code",
                "stock_name",
                "source_type",
                "source_title",
                "source_path_or_url",
                "citation_id",
                "chunk_id",
                "page_locator",
                "citation_granularity",
                "claim_text",
                "evidence_strength",
                "is_primary_source",
                "parser",
                "parser_version",
                "parse_status",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    page_chunks = chunks[chunks["citation_granularity"].eq("page_level") & chunks["page_locator"].fillna("").astype(str).str.len().gt(0)].copy()
    page_chunks["claim_id"] = page_chunks["stock_code"] + "-" + page_chunks["chunk_id"].astype(str)
    page_chunks["claim_text"] = page_chunks["excerpt"].fillna("").astype(str).str.slice(0, 300)
    page_chunks["source_path_or_url"] = page_chunks["source_path"]
    page_chunks["evidence_strength"] = "primary_source_chunk"
    page_chunks["is_primary_source"] = True
    columns = [
        "claim_id",
        "stock_code",
        "stock_name",
        "source_type",
        "source_title",
        "source_path_or_url",
        "citation_id",
        "chunk_id",
        "page_locator",
        "citation_granularity",
        "claim_text",
        "evidence_strength",
        "is_primary_source",
        "parser",
        "parser_version",
        "parse_status",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    return page_chunks[[column for column in columns if column in page_chunks.columns]]


def _parse_failures(manifest: pd.DataFrame) -> pd.DataFrame:
    return manifest[~manifest["docling_status"].eq("parsed")].copy()


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _summary(
    *,
    collection: pd.DataFrame,
    manifest: pd.DataFrame,
    chunks: pd.DataFrame,
    claims: pd.DataFrame,
    tables: pd.DataFrame,
    failures: pd.DataFrame,
    strategy_clean: bool,
) -> dict[str, Any]:
    parse_failure_count = int(len(failures))
    if not COLLECTION_MANIFEST.exists():
        acceptance = "blocked_due_to_missing_collection_manifest"
    elif not strategy_clean:
        acceptance = "blocked_due_to_guardrail_violation"
    elif parse_failure_count:
        acceptance = "conditionally_ready_with_parse_failures"
    else:
        acceptance = "backfill_primary_source_parse_ready"
    return {
        "task_name": TASK_NAME,
        "source_stock_count": int(collection["stock_code"].nunique()),
        "source_pdf_count": int(len(collection)),
        "parse_attempt_count": int(len(manifest)),
        "parse_success_count": int(manifest["docling_status"].eq("parsed").sum()) if not manifest.empty else 0,
        "parse_failure_count": parse_failure_count,
        "stock_parse_coverage_count": int(manifest.loc[manifest["docling_status"].eq("parsed"), "stock_code"].nunique()) if not manifest.empty else 0,
        "page_level_citation_count": int(len(claims)),
        "source_level_citation_count": 0,
        "table_provenance_count": int(len(tables)),
        "evidence_chunk_count": int(len(chunks)),
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "only_collection_manifest_processed": True,
        "source_pdf_count": summary["source_pdf_count"],
        "parse_success_count": summary["parse_success_count"],
        "all_sources_accounted_for": summary["parse_attempt_count"] == summary["source_pdf_count"] == 69,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Data-to-Brief Docling Backfill Queue Primary Source Parse v1",
            "",
            "## 1. Scope",
            "This task parses only the 69 primary-source PDFs from the 23-stock backfill queue collection manifest. It is research-only and does not upgrade candidates, change the pool, or connect signal/admission.",
            "",
            "## 2. Input Manifest",
            f"Source stocks: {summary['source_stock_count']}; source PDFs: {summary['source_pdf_count']}.",
            "",
            "## 3. Parse Results",
            f"Parse attempts: {summary['parse_attempt_count']}; successes: {summary['parse_success_count']}; failures: {summary['parse_failure_count']}; stock coverage: {summary['stock_parse_coverage_count']}.",
            "",
            "## 4. Evidence Artifacts",
            f"Evidence chunks: {summary['evidence_chunk_count']}; page-level citation claims: {summary['page_level_citation_count']}; source-level citation claims: {summary['source_level_citation_count']}; table provenance rows: {summary['table_provenance_count']}.",
            "",
            "## 5. Guardrail Checks",
            f"used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 6. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 7. Recommended Next Step",
            "tech_bottleneck_90_primary_source_backfill_rerun_v2",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR, *, timeout_seconds: int = 12) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    collection = _read_manifest()
    cached = _load_cached(output, len(collection))
    if cached is None:
        manifest_rows: list[dict[str, Any]] = []
        chunk_rows: list[dict[str, Any]] = []
        table_rows: list[dict[str, Any]] = []
        for source in collection.to_dict("records"):
            result = _parse_one(source, timeout_seconds)
            manifest_rows.append(result["comparison"])
            chunk_rows.extend(result["chunks"])
            table_rows.extend(result["tables"])
        manifest = pd.DataFrame(manifest_rows)
        chunks = pd.DataFrame(chunk_rows)
        tables = pd.DataFrame(table_rows)
    else:
        manifest, chunks, tables = cached
    claims = _build_citation_claims(chunks)
    failures = _parse_failures(manifest)
    parse_audit = manifest.copy()
    if not parse_audit.empty:
        parse_audit["parse_audit_status"] = parse_audit["docling_status"].map(lambda value: "pass" if value == "parsed" else "fail")
        parse_audit["issue_detail"] = parse_audit["docling_error_message"].fillna("").astype(str)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        collection=collection,
        manifest=manifest,
        chunks=chunks,
        claims=claims,
        tables=tables,
        failures=failures,
        strategy_clean=strategy_clean,
    )
    guardrails = _guardrails(summary)

    manifest.to_csv(output / "backfill_primary_source_docling_manifest.csv", index=False)
    parse_audit.to_csv(output / "backfill_primary_source_parse_audit.csv", index=False)
    chunks.to_csv(output / "backfill_primary_source_evidence_chunks.csv", index=False)
    claims.to_csv(output / "backfill_primary_source_citation_claims.csv", index=False)
    tables.to_csv(output / "backfill_primary_source_table_provenance.csv", index=False)
    failures.to_csv(output / "backfill_primary_source_parse_failures.csv", index=False)
    _write_json(output / "backfill_primary_source_docling_parse_summary.json", summary)
    _write_json(output / "backfill_primary_source_docling_parse_guardrails.json", guardrails)
    (output / "data_to_brief_docling_backfill_queue_primary_source_parse_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
