from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

import pandas as pd

try:  # pragma: no cover - dependency availability is captured in smoke output
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


TASK_NAME = "data_to_brief_docling_parser_poc_v1"
DEFAULT_OUTPUT_DIR = Path("outputs/research") / TASK_NAME
DEFAULT_SOURCE_ROOTS = [Path("data/manual")]
DEFAULT_PILOT_STOCKS = [
    {"stock_code": "002371", "stock_name": "北方华创", "asset_id": "002371.SZ"},
    {"stock_code": "688012", "stock_name": "中微公司", "asset_id": "688012.SH"},
    {"stock_code": "002885", "stock_name": "京泉华", "asset_id": "002885.SZ"},
    {"stock_code": "300838", "stock_name": "浙江力诺", "asset_id": "300838.SZ"},
    {"stock_code": "000400", "stock_name": "许继电气", "asset_id": "000400.SZ"},
]


DoclingParser = Callable[[Path], dict[str, Any]]


@dataclass(frozen=True)
class PilotSource:
    stock_code: str
    stock_name: str
    asset_id: str
    pdf_path: Path | None
    source_status: str


def run_data_to_brief_docling_parser_poc(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    source_roots: list[str | Path] | None = None,
    limit_per_stock: int = 1,
    docling_parser: DoclingParser | None = None,
    skip_docling: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    roots = [Path(root) for root in (source_roots or DEFAULT_SOURCE_ROOTS)]
    output.mkdir(parents=True, exist_ok=True)
    (output / "parsed_documents").mkdir(parents=True, exist_ok=True)
    (output / "chunks").mkdir(parents=True, exist_ok=True)

    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sources = discover_pilot_sources(source_roots=roots, limit_per_stock=limit_per_stock)
    smoke = build_docling_install_smoke(skip_docling=skip_docling)
    if docling_parser is None and not skip_docling:
        docling_parser = parse_with_docling

    comparison_rows: list[dict[str, Any]] = []
    source_chunk_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    claim_map_rows: list[dict[str, Any]] = []
    table_rows: list[dict[str, Any]] = []

    for source in sources:
        if source.pdf_path is None:
            evidence = _missing_source_evidence(source, updated_at=updated_at)
            evidence_rows.append(evidence)
            claim_map_rows.append(_claim_map_from_evidence(evidence))
            comparison_rows.append(_missing_comparison_row(source, updated_at=updated_at))
            continue

        baseline = parse_with_pypdf(source.pdf_path)
        docling = (
            {
                "status": "skipped",
                "parser": "docling",
                "markdown": "",
                "json": {},
                "tables": [],
                "error_type": "",
                "error_message": "Docling skipped by caller",
            }
            if skip_docling or docling_parser is None
            else docling_parser(source.pdf_path)
        )
        markdown = _safe_text(docling.get("markdown")) or _safe_text(baseline.get("text"))
        document_stem = _document_stem(source, sequence=1)
        md_path = output / "parsed_documents" / f"{document_stem}.md"
        json_path = output / "parsed_documents" / f"{document_stem}.json"
        chunks_path = output / "chunks" / f"{source.stock_code}_{_safe_filename(source.stock_name)}_chunks.csv"
        md_path.write_text(markdown, encoding="utf-8")
        _write_json(
            json_path,
            {
                "stock_code": source.stock_code,
                "stock_name": source.stock_name,
                "asset_id": source.asset_id,
                "pdf_path": str(source.pdf_path),
                "docling": _jsonable(docling.get("json") or {}),
                "baseline": {
                    "status": baseline["status"],
                    "char_count": baseline["char_count"],
                    "error_type": baseline["error_type"],
                    "error_message": baseline["error_message"],
                },
            },
        )

        chunks = build_chunks(markdown)
        chunk_records = []
        for index, chunk_text in enumerate(chunks, start=1):
            citation_id = f"S{len(source_chunk_rows) + 1}"
            chunk_id = f"{source.stock_code}-D1-C{index}"
            row = {
                "citation_id": citation_id,
                "chunk_id": chunk_id,
                "stock_code": source.stock_code,
                "stock_name": source.stock_name,
                "asset_id": source.asset_id,
                "source_type": "local_pdf",
                "source_title": source.pdf_path.name,
                "source_path": str(source.pdf_path),
                "parser": "docling" if docling.get("status") == "parsed" else "pypdf_fallback",
                "docling_status": _safe_text(docling.get("status")),
                "chunk_index": index,
                "char_count": len(chunk_text),
                "excerpt": _excerpt(chunk_text),
                "parsed_markdown_path": str(md_path),
                "parsed_json_path": str(json_path),
                "updated_at": updated_at,
            }
            source_chunk_rows.append(row)
            chunk_records.append({**row, "chunk_text": chunk_text})
        pd.DataFrame(chunk_records).to_csv(chunks_path, index=False)

        first_citation = chunk_records[0]["citation_id"] if chunk_records else f"S{len(source_chunk_rows) + 1}"
        if not chunk_records:
            empty_chunk = {
                "citation_id": first_citation,
                "chunk_id": f"{source.stock_code}-D1-C1",
                "stock_code": source.stock_code,
                "stock_name": source.stock_name,
                "asset_id": source.asset_id,
                "source_type": "local_pdf",
                "source_title": source.pdf_path.name,
                "source_path": str(source.pdf_path),
                "parser": "docling" if docling.get("status") == "parsed" else "pypdf_fallback",
                "docling_status": _safe_text(docling.get("status")),
                "chunk_index": 1,
                "char_count": 0,
                "excerpt": "",
                "parsed_markdown_path": str(md_path),
                "parsed_json_path": str(json_path),
                "updated_at": updated_at,
            }
            source_chunk_rows.append(empty_chunk)
            pd.DataFrame([{**empty_chunk, "chunk_text": ""}]).to_csv(chunks_path, index=False)

        evidence = {
            "claim_id": f"C{len(evidence_rows) + 1}",
            "stock_code": source.stock_code,
            "stock_name": source.stock_name,
            "claim_text": "local PDF was parsed into evidence-ready chunks for Data-to-Brief follow-up",
            "citation_id": first_citation,
            "source_type": "local_pdf",
            "source_path": str(source.pdf_path),
            "excerpt": _excerpt(markdown),
            "evidence_strength": "source_chunk_available" if markdown else "source_file_available_text_empty",
            "evidence_required": False,
            "parser": "docling" if docling.get("status") == "parsed" else "pypdf_fallback",
            "docling_status": _safe_text(docling.get("status")),
            "updated_at": updated_at,
        }
        evidence_rows.append(evidence)
        claim_map_rows.append(_claim_map_from_evidence(evidence))

        for table_index, table in enumerate(_list_value(docling.get("tables")), start=1):
            table_rows.append(
                {
                    "stock_code": source.stock_code,
                    "stock_name": source.stock_name,
                    "citation_id": first_citation,
                    "table_id": _safe_text(table.get("table_id")) or f"T{table_index}",
                    "row_count": table.get("row_count", ""),
                    "column_count": table.get("column_count", ""),
                    "caption": _safe_text(table.get("caption")),
                    "source_path": str(source.pdf_path),
                    "parser": "docling",
                    "updated_at": updated_at,
                }
            )
        comparison_rows.append(_comparison_row(source, baseline=baseline, docling=docling, updated_at=updated_at))

    _write_json(output / "docling_install_smoke.json", smoke)
    _write_csv(output / "parser_comparison_matrix.csv", comparison_rows)
    _write_csv(output / "source_chunk_manifest.csv", source_chunk_rows)
    _write_csv(output / "pilot_evidence_matrix.csv", evidence_rows)
    _write_csv(output / "pilot_claim_citation_map.csv", claim_map_rows)
    _write_csv(
        output / "table_inventory.csv",
        table_rows,
        columns=[
            "stock_code",
            "stock_name",
            "citation_id",
            "table_id",
            "row_count",
            "column_count",
            "caption",
            "source_path",
            "parser",
            "updated_at",
        ],
    )

    summary = {
        "task_name": TASK_NAME,
        "output_dir": str(output),
        "pilot_stock_count": len(DEFAULT_PILOT_STOCKS),
        "local_pdf_count": sum(1 for source in sources if source.pdf_path is not None),
        "docling_parsed_count": sum(1 for row in comparison_rows if row.get("docling_status") == "parsed"),
        "docling_failed_count": sum(1 for row in comparison_rows if row.get("docling_status") in {"parse_error", "import_error"}),
        "evidence_required_stock_count": sum(1 for source in sources if source.pdf_path is None),
        "chunk_count": len(source_chunk_rows),
        "table_count": len(table_rows),
        "research_only": True,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "updated_at": updated_at,
        "paths": {
            "docling_install_smoke": str(output / "docling_install_smoke.json"),
            "parser_comparison_matrix": str(output / "parser_comparison_matrix.csv"),
            "source_chunk_manifest": str(output / "source_chunk_manifest.csv"),
            "pilot_evidence_matrix": str(output / "pilot_evidence_matrix.csv"),
            "pilot_claim_citation_map": str(output / "pilot_claim_citation_map.csv"),
            "table_inventory": str(output / "table_inventory.csv"),
        },
    }
    _write_json(output / "pilot_run_summary.json", summary)
    return {"summary": summary, "sources": sources}


def discover_pilot_sources(*, source_roots: list[Path], limit_per_stock: int = 1) -> list[PilotSource]:
    pdfs = _all_pdfs(source_roots)
    selected: list[PilotSource] = []
    for stock in DEFAULT_PILOT_STOCKS:
        matches = [
            path
            for path in pdfs
            if stock["stock_code"] in path.name or stock["asset_id"] in path.name or stock["stock_name"] in path.name
        ]
        retained = matches[: max(1, int(limit_per_stock or 1))]
        if retained:
            for path in retained:
                selected.append(
                    PilotSource(
                        stock_code=stock["stock_code"],
                        stock_name=stock["stock_name"],
                        asset_id=stock["asset_id"],
                        pdf_path=path,
                        source_status="local_pdf_found",
                    )
                )
        else:
            selected.append(
                PilotSource(
                    stock_code=stock["stock_code"],
                    stock_name=stock["stock_name"],
                    asset_id=stock["asset_id"],
                    pdf_path=None,
                    source_status="evidence_required",
                )
            )
    return selected


def build_docling_install_smoke(*, skip_docling: bool = False) -> dict[str, Any]:
    if skip_docling:
        return {
            "package": "docling",
            "installed": False,
            "status": "skipped",
            "version": "",
            "error_type": "",
            "error_message": "Docling skipped by caller",
        }
    try:
        import docling  # type: ignore

        return {
            "package": "docling",
            "installed": True,
            "status": "import_ok",
            "version": _docling_version(docling),
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:
        return {
            "package": "docling",
            "installed": False,
            "status": "import_error",
            "version": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _docling_version(docling_module: Any) -> str:
    try:
        return version("docling")
    except PackageNotFoundError:
        return _safe_text(getattr(docling_module, "__version__", "")) or "unknown"


def parse_with_docling(pdf_path: Path) -> dict[str, Any]:
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except Exception as exc:
        return _parser_error("import_error", exc)
    try:
        result = DocumentConverter().convert(str(pdf_path))
        document = result.document
        markdown = document.export_to_markdown()
        return {
            "status": "parsed",
            "parser": "docling",
            "markdown": markdown,
            "json": _docling_json(document),
            "tables": _docling_tables(document),
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:  # pragma: no cover - depends on runtime model/network/pdf conditions
        return _parser_error("parse_error", exc)


def parse_with_pypdf(pdf_path: Path) -> dict[str, Any]:
    if PdfReader is None:
        return {
            "status": "unavailable",
            "parser": "pypdf",
            "text": "",
            "char_count": 0,
            "error_type": "ImportError",
            "error_message": "pypdf is unavailable",
        }
    try:
        reader = PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return {
            "status": "parsed" if text else "empty_text",
            "parser": "pypdf",
            "text": text,
            "char_count": len(text),
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:
        return {
            "status": "parse_error",
            "parser": "pypdf",
            "text": "",
            "char_count": 0,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
        }


def build_chunks(markdown: str, *, max_chars: int = 1400) -> list[str]:
    text = _safe_text(markdown)
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not current:
            current = paragraph
            continue
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}"
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _all_pdfs(source_roots: list[Path]) -> list[Path]:
    pdfs: list[Path] = []
    for root in source_roots:
        if not root.exists():
            continue
        pdfs.extend(sorted(path for path in root.rglob("*.pdf") if path.is_file()))
    return sorted(pdfs, key=lambda path: str(path))


def _parser_error(status: str, exc: Exception) -> dict[str, Any]:
    return {
        "status": status,
        "parser": "docling",
        "markdown": "",
        "json": {},
        "tables": [],
        "error_type": type(exc).__name__,
        "error_message": str(exc)[:500],
    }


def _docling_json(document: Any) -> dict[str, Any]:
    for method_name in ["export_to_dict", "model_dump"]:
        method = getattr(document, method_name, None)
        if callable(method):
            try:
                value = method()
                return value if isinstance(value, dict) else {"value": value}
            except Exception:
                continue
    return {"repr": repr(document)[:1000]}


def _docling_tables(document: Any) -> list[dict[str, Any]]:
    tables = getattr(document, "tables", None) or []
    rows: list[dict[str, Any]] = []
    for index, table in enumerate(tables, start=1):
        rows.append(
            {
                "table_id": f"T{index}",
                "row_count": getattr(table, "num_rows", ""),
                "column_count": getattr(table, "num_cols", ""),
                "caption": _safe_text(getattr(table, "caption", "")),
            }
        )
    return rows


def _comparison_row(
    source: PilotSource,
    *,
    baseline: dict[str, Any],
    docling: dict[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    return {
        "stock_code": source.stock_code,
        "stock_name": source.stock_name,
        "asset_id": source.asset_id,
        "source_status": source.source_status,
        "pdf_path": str(source.pdf_path or ""),
        "pypdf_status": _safe_text(baseline.get("status")),
        "pypdf_char_count": int(baseline.get("char_count") or 0),
        "pypdf_error_type": _safe_text(baseline.get("error_type")),
        "docling_status": _safe_text(docling.get("status")),
        "docling_markdown_chars": len(_safe_text(docling.get("markdown"))),
        "docling_table_count": len(_list_value(docling.get("tables"))),
        "docling_error_type": _safe_text(docling.get("error_type")),
        "docling_error_message": _safe_text(docling.get("error_message")),
        "updated_at": updated_at,
    }


def _missing_comparison_row(source: PilotSource, *, updated_at: str) -> dict[str, Any]:
    return {
        "stock_code": source.stock_code,
        "stock_name": source.stock_name,
        "asset_id": source.asset_id,
        "source_status": source.source_status,
        "pdf_path": "",
        "pypdf_status": "not_attempted",
        "pypdf_char_count": 0,
        "pypdf_error_type": "",
        "docling_status": "not_attempted",
        "docling_markdown_chars": 0,
        "docling_table_count": 0,
        "docling_error_type": "",
        "docling_error_message": "local PDF evidence required",
        "updated_at": updated_at,
    }


def _missing_source_evidence(source: PilotSource, *, updated_at: str) -> dict[str, Any]:
    return {
        "claim_id": "",
        "stock_code": source.stock_code,
        "stock_name": source.stock_name,
        "claim_text": "evidence_required: local PDF source is missing for Docling parser PoC",
        "citation_id": "evidence_required",
        "source_type": "evidence_required",
        "source_path": "evidence_required",
        "excerpt": "evidence_required: annual report, announcement, official disclosure, or broker PDF must be added to local source roots",
        "evidence_strength": "missing",
        "evidence_required": True,
        "parser": "not_attempted",
        "docling_status": "not_attempted",
        "updated_at": updated_at,
    }


def _claim_map_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    claim_id = _safe_text(evidence.get("claim_id")) or f"C{evidence.get('stock_code')}-missing"
    evidence["claim_id"] = claim_id
    return {
        "claim_id": claim_id,
        "stock_code": evidence.get("stock_code", ""),
        "stock_name": evidence.get("stock_name", ""),
        "claim_text": evidence.get("claim_text", ""),
        "citation_id": evidence.get("citation_id", ""),
        "source_path": evidence.get("source_path", ""),
        "evidence_required": evidence.get("evidence_required", False),
    }


def _document_stem(source: PilotSource, *, sequence: int) -> str:
    return f"{source.stock_code}_{_safe_filename(source.stock_name)}_{sequence}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value).strip("_") or "unknown"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _excerpt(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", _safe_text(value))
    return text[:limit]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except TypeError:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=columns)
    frame.to_csv(path, index=False)
