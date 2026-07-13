from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "data_to_brief_docling_parser_quality_and_integration_test_v1"
DEFAULT_INPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_parser_poc_v1"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_parser_quality_audit_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
PILOT_STOCKS = {
    "002371": {"stock_name": "北方华创", "expected_status": "parsed", "has_local_pdf": True},
    "688012": {"stock_name": "中微公司", "expected_status": "parsed", "has_local_pdf": True},
    "000400": {"stock_name": "许继电气", "expected_status": "parsed", "has_local_pdf": True},
    "002885": {"stock_name": "京泉华", "expected_status": "evidence_required", "has_local_pdf": False},
    "300838": {"stock_name": "浙江力诺", "expected_status": "evidence_required", "has_local_pdf": False},
}
INTEGRATION_SECTIONS = {
    "business_overview": ["主营业务", "主要业务", "公司从事", "主要产品"],
    "key_products": ["产品", "设备", "材料", "芯片", "模块", "系统"],
    "hard_tech_bottleneck_thesis": ["国产化", "自主可控", "核心技术", "关键技术", "进口替代", "半导体", "高端装备"],
    "technology_capability": ["研发", "专利", "技术", "工艺", "平台", "创新"],
    "financial_snapshot": ["营业收入", "净利润", "毛利率", "研发费用", "现金流", "收入"],
    "risks_and_counter_evidence": ["风险", "不确定性", "竞争", "客户集中", "供应链", "存货"],
}


def run_data_to_brief_docling_parser_quality_audit(
    *,
    input_dir: str | Path = DEFAULT_INPUT_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    poc_summary, chunks, _evidence, tables, comparison = _load_inputs(input_path)
    if int(poc_summary.get("pilot_stock_count", 0)) != 5:
        raise ValueError(f"Expected pilot_stock_count=5, found {poc_summary.get('pilot_stock_count')}")
    if not bool(poc_summary.get("research_only")):
        raise ValueError("PoC summary research_only must be true")
    if bool(poc_summary.get("allowed_for_signal")) or bool(poc_summary.get("allowed_for_admission")) or bool(poc_summary.get("production_update")):
        raise ValueError("PoC summary violates signal/admission/production guardrails")

    chunk_audit = _audit_chunks(chunks)
    table_audit = _audit_tables(tables)
    gap_audit = _evidence_gap_audit(comparison, chunks, tables)
    if gap_audit[gap_audit["has_local_pdf"].eq(True)]["chunk_count"].eq(0).any():
        raise ValueError("Parsed stocks with local PDFs must have non-zero chunks")
    if not gap_audit[gap_audit["has_local_pdf"].eq(False)]["actual_status"].eq("evidence_required").all():
        raise ValueError("Missing-PDF pilot stocks must remain evidence_required")

    chunk_audit.to_csv(output_path / "docling_source_chunk_quality_audit.csv", index=False)
    table_audit.to_csv(output_path / "docling_table_quality_audit.csv", index=False)
    gap_audit.to_csv(output_path / "docling_evidence_gap_audit.csv", index=False)
    smoke_summary = _integration_smoke(output_path, poc_summary, chunks, tables, table_audit)

    strategy_diff = _git_diff_formal_strategy_files()
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "pilot_stock_count": int(poc_summary.get("pilot_stock_count", len(PILOT_STOCKS))),
        "parsed_stock_count": int(gap_audit["actual_status"].eq("parsed").sum()),
        "evidence_required_missing_pdf_stock_count": int(gap_audit[gap_audit["has_local_pdf"].eq(False)]["actual_status"].eq("evidence_required").sum()),
        "chunk_count": int(len(chunks)),
        "table_count": int(len(tables)),
        "citation_ready_chunk_count": int(chunk_audit["citation_ready"].eq(True).sum()),
        "chunk_warning_count": int(chunk_audit["parse_quality_flag"].eq("warning").sum()),
        "chunk_fail_count": int(chunk_audit["parse_quality_flag"].eq("fail").sum()),
        "table_warning_count": int(table_audit["table_quality_flag"].eq("warning").sum()),
        "table_fail_count": int(table_audit["table_quality_flag"].eq("fail").sum()),
        "table_relevance_unknown_count": int(table_audit["table_relevance"].eq("unknown").sum()),
        "integration_smoke_citation_count": int(smoke_summary["citation_count"]),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "updated_at": _now(),
        "acceptance_decision": "docling_parser_quality_audit_ready" if strategy_diff == "" else "blocked_due_to_strategy_diff",
    }
    _write_json(output_path / "docling_parser_quality_summary.json", summary)
    (output_path / "docling_parser_quality_audit_report.md").write_text(
        _render_report(summary, gap_audit, smoke_summary),
        encoding="utf-8",
    )
    return {"summary": summary, "smoke_summary": smoke_summary}


def _load_inputs(input_dir: Path) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = [
        input_dir / "pilot_run_summary.json",
        input_dir / "source_chunk_manifest.csv",
        input_dir / "pilot_evidence_matrix.csv",
        input_dir / "table_inventory.csv",
        input_dir / "parser_comparison_matrix.csv",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required Docling PoC artifacts: " + ", ".join(missing))
    summary = json.loads((input_dir / "pilot_run_summary.json").read_text(encoding="utf-8"))
    return (
        summary,
        _read_csv(input_dir / "source_chunk_manifest.csv"),
        _read_csv(input_dir / "pilot_evidence_matrix.csv"),
        _read_csv(input_dir / "table_inventory.csv"),
        _read_csv(input_dir / "parser_comparison_matrix.csv"),
    )


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str})
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_normalize_code)
    return frame


def _audit_chunks(chunks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    seen_texts: set[tuple[str, str]] = set()
    for _, row in chunks.iterrows():
        stock_code = _normalize_code(row.get("stock_code"))
        source_id = _source_id(row)
        chunk_id = _clean(row.get("chunk_id"))
        source_type = _clean(row.get("source_type"))
        source_path = _source_path_or_url(row)
        text = _clean(row.get("chunk_text")) or _clean(row.get("excerpt"))
        parse_status = _clean(row.get("parse_status")) or _clean(row.get("docling_status"))
        evidence_status = _clean(row.get("evidence_status")) or ("source_chunk_available" if text else "evidence_required")
        locator = _page_locator(row)
        duplicate_key = (stock_code, text[:500])
        duplicated = duplicate_key in seen_texts
        seen_texts.add(duplicate_key)
        issues: list[str] = []
        for field_name, present in [
            ("missing_stock_code", bool(stock_code)),
            ("missing_source_id", bool(source_id)),
            ("missing_chunk_id", bool(chunk_id)),
            ("missing_source_type", bool(source_type)),
            ("missing_source_path_or_url", bool(source_path)),
            ("empty_chunk_text", bool(text)),
            ("missing_parse_status", bool(parse_status)),
            ("missing_evidence_status", bool(evidence_status)),
        ]:
            if not present:
                issues.append(field_name)
        if len(text) < 80:
            issues.append("short_chunk_text")
        if not locator:
            issues.append("missing_page_locator")
        if duplicated:
            issues.append("duplicated_chunk_text")
        blocking = [issue for issue in issues if issue not in {"missing_page_locator", "short_chunk_text", "duplicated_chunk_text"}]
        citation_ready = bool(stock_code and source_id and chunk_id and source_type and source_path and text and parse_status)
        parse_quality_flag = "fail" if not citation_ready or blocking else "warning" if issues else "pass"
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": _clean(row.get("stock_name")),
                "source_id": source_id,
                "chunk_id": chunk_id,
                "source_type": source_type,
                "source_path_or_url": source_path,
                "chunk_text_length": len(text),
                "has_page_locator": bool(locator),
                "has_non_empty_text": bool(text),
                "citation_ready": citation_ready,
                "parse_quality_flag": parse_quality_flag,
                "issue_type": "none" if not issues else "|".join(issues),
                "issue_detail": "citation-ready chunk" if not issues else "; ".join(issues),
            }
        )
    return pd.DataFrame(rows)


def _audit_tables(tables: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in tables.iterrows():
        stock_code = _normalize_code(row.get("stock_code"))
        source_id = _source_id(row)
        table_id = _clean(row.get("table_id"))
        locator = _page_locator(row)
        title = _clean(row.get("table_title")) or _clean(row.get("caption"))
        row_count = row.get("row_count")
        column_count = row.get("column_count")
        has_content = bool(title or _clean(row.get("table_text")) or _clean(row.get("table_placeholder")) or table_id)
        issues: list[str] = []
        for issue, present in [
            ("missing_stock_code", bool(stock_code)),
            ("missing_source_id", bool(source_id)),
            ("missing_table_id", bool(table_id)),
            ("missing_table_content_or_placeholder", has_content),
        ]:
            if not present:
                issues.append(issue)
        if not locator:
            issues.append("missing_page_locator")
        if not title:
            issues.append("missing_table_title")
        if pd.isna(row_count):
            issues.append("missing_row_count")
        if pd.isna(column_count):
            issues.append("missing_column_count")
        blocking = [issue for issue in issues if issue in {"missing_stock_code", "missing_source_id", "missing_table_id", "missing_table_content_or_placeholder"}]
        rows.append(
            {
                "stock_code": stock_code,
                "source_id": source_id,
                "table_id": table_id,
                "page_locator": locator,
                "table_title": title,
                "row_count": row_count,
                "column_count": column_count,
                "table_relevance": _table_relevance(row),
                "table_quality_flag": "pass" if not issues else "warning" if not blocking else "fail",
                "issue_type": "none" if not issues else "|".join(issues),
                "issue_detail": "table inventory usable" if not issues else "; ".join(issues),
            }
        )
    return pd.DataFrame(rows)


def _evidence_gap_audit(comparison: pd.DataFrame, chunks: pd.DataFrame, tables: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for stock_code, expected in PILOT_STOCKS.items():
        comp = comparison[comparison["stock_code"].eq(stock_code)]
        stock_chunks = chunks[chunks["stock_code"].eq(stock_code)]
        stock_tables = tables[tables["stock_code"].eq(stock_code)]
        docling_status = _clean(comp.iloc[0].get("docling_status")) if not comp.empty else ""
        source_status = _clean(comp.iloc[0].get("source_status")) if not comp.empty else ""
        actual = "parsed" if len(stock_chunks) > 0 and docling_status == "parsed" else "evidence_required"
        reason = ""
        if actual == "evidence_required":
            reason = "missing local PDF" if source_status == "evidence_required" or not expected["has_local_pdf"] else "no parsed chunks"
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": expected["stock_name"],
                "expected_status": expected["expected_status"],
                "actual_status": actual,
                "has_local_pdf": bool(expected["has_local_pdf"]),
                "parsed_source_count": int(stock_chunks["source_path"].nunique()) if "source_path" in stock_chunks.columns and not stock_chunks.empty else 0,
                "chunk_count": int(len(stock_chunks)),
                "table_count": int(len(stock_tables)),
                "evidence_required_reason": reason,
                "status_match": actual == expected["expected_status"],
            }
        )
    return pd.DataFrame(rows)


def _integration_smoke(output_dir: Path, poc_summary: dict[str, Any], chunks: pd.DataFrame, raw_tables: pd.DataFrame, table_audit: pd.DataFrame) -> dict[str, Any]:
    smoke_dir = output_dir / "integration_smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    tables = table_audit.merge(raw_tables, on=["stock_code", "table_id"], how="left", suffixes=("", "_raw"))
    fill_rows: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    citation_counter = 1

    for stock_code, meta in PILOT_STOCKS.items():
        stock_chunks = chunks[chunks["stock_code"].eq(stock_code)]
        stock_tables = tables[tables["stock_code"].eq(stock_code)]
        filled = partial = required = 0
        for section, keywords in INTEGRATION_SECTIONS.items():
            matched_chunks = _match_chunks(stock_chunks, keywords)
            matched_tables = _match_tables(stock_tables, section)
            if not meta["has_local_pdf"]:
                matched_chunks = matched_chunks.iloc[0:0]
                matched_tables = matched_tables.iloc[0:0]
            matched_total = len(matched_chunks) + len(matched_tables)
            if matched_total >= 2:
                fill_status = "filled"
                filled += 1
            elif matched_total == 1:
                fill_status = "partial"
                partial += 1
            else:
                fill_status = "evidence_required"
                required += 1
            citation_ids: list[str] = []
            for _, chunk in matched_chunks.iterrows():
                citation_id = f"S{citation_counter}"
                citation_counter += 1
                citation_ids.append(citation_id)
                excerpt = _clean(chunk.get("excerpt"))[:600]
                claim_id = f"{stock_code}-{section}-C{len(citation_ids)}"
                claim_rows.append(_claim_row(stock_code, section, claim_id, citation_id, chunk, excerpt))
                references.append(_reference_row(stock_code, citation_id, chunk, poc_summary))
                evidence_rows.append(_evidence_row(stock_code, meta["stock_name"], section, claim_id, citation_id, _source_id(chunk), excerpt, "moderate"))
            for _, table in matched_tables.iterrows():
                citation_id = f"S{citation_counter}"
                citation_counter += 1
                citation_ids.append(citation_id)
                excerpt = _clean(table.get("table_title")) or _clean(table.get("caption")) or f"table {table.get('table_id')} inventory placeholder"
                claim_id = f"{stock_code}-{section}-T{len(citation_ids)}"
                claim_rows.append(_table_claim_row(stock_code, section, claim_id, citation_id, table, excerpt))
                references.append(_table_reference_row(stock_code, citation_id, table, poc_summary))
                evidence_rows.append(_evidence_row(stock_code, meta["stock_name"], section, claim_id, citation_id, _source_id(table), excerpt, "weak"))
            fill_rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": meta["stock_name"],
                    "report_section": section,
                    "evidence_fill_status": fill_status,
                    "matched_chunk_count": int(len(matched_chunks)),
                    "matched_table_count": int(len(matched_tables)),
                    "candidate_citation_ids": "|".join(citation_ids),
                    "evidence_quality_flag": "usable" if fill_status in {"filled", "partial"} else "gap",
                    "evidence_required_reason": "" if fill_status in {"filled", "partial"} else ("missing local PDF" if not meta["has_local_pdf"] else "no keyword-matched Docling chunk/table"),
                }
            )
        report_status = "evidence_required"
        blocker = "missing local PDF" if not meta["has_local_pdf"] else "no matched report sections"
        if meta["has_local_pdf"] and filled + partial > 0:
            report_status = "docling_evidence_ready" if required == 0 else "partial"
            blocker = "" if report_status == "docling_evidence_ready" else "some sections still evidence_required"
        status_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": meta["stock_name"],
                "parsed_source_count": int(stock_chunks["source_path"].nunique()) if "source_path" in stock_chunks.columns and not stock_chunks.empty else 0,
                "chunk_count": int(len(stock_chunks)),
                "table_count": int(len(stock_tables)),
                "filled_section_count": int(filled),
                "partial_section_count": int(partial),
                "evidence_required_section_count": int(required),
                "report_status": report_status,
                "blocker_reason": blocker,
            }
        )

    pd.DataFrame(fill_rows).to_csv(smoke_dir / "pilot_report_evidence_fill_preview.csv", index=False)
    pd.DataFrame(claim_rows).to_csv(smoke_dir / "claim_citation_map_preview.csv", index=False)
    _write_jsonl(smoke_dir / "references_preview.jsonl", references)
    pd.DataFrame(evidence_rows).to_csv(smoke_dir / "evidence_matrix_preview.csv", index=False)
    pd.DataFrame(status_rows).to_csv(smoke_dir / "report_status_preview.csv", index=False)
    summary = {
        "task_name": f"{TASK_NAME}_integration_smoke",
        "research_only": True,
        "pilot_stock_count": len(PILOT_STOCKS),
        "parsed_integration_stock_count": 3,
        "citation_count": len(references),
        "claim_citation_map_rows": len(claim_rows),
        "filled_or_partial_section_count": int(sum(1 for row in fill_rows if row["evidence_fill_status"] in {"filled", "partial"})),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "updated_at": _now(),
    }
    _write_json(smoke_dir / "integration_smoke_summary.json", summary)
    return summary


def _claim_row(stock_code: str, section: str, claim_id: str, citation_id: str, chunk: pd.Series, excerpt: str) -> dict[str, Any]:
    return {
        "stock_code": stock_code,
        "claim_id": claim_id,
        "report_section": section,
        "claim_placeholder": f"{section} evidence placeholder",
        "citation_id": citation_id,
        "source_id": _source_id(chunk),
        "chunk_id": _clean(chunk.get("chunk_id")),
        "table_id": "",
        "source_type": _clean(chunk.get("source_type")),
        "source_path_or_url": _source_path_or_url(chunk),
        "page_locator": _page_locator(chunk),
        "excerpt": excerpt,
        "supports_or_contradicts": "supports",
        "evidence_strength": "moderate" if len(excerpt) >= 160 else "weak",
    }


def _table_claim_row(stock_code: str, section: str, claim_id: str, citation_id: str, table: pd.Series, excerpt: str) -> dict[str, Any]:
    return {
        "stock_code": stock_code,
        "claim_id": claim_id,
        "report_section": section,
        "claim_placeholder": f"{section} table evidence placeholder",
        "citation_id": citation_id,
        "source_id": _source_id(table),
        "chunk_id": "",
        "table_id": _clean(table.get("table_id")),
        "source_type": "table_inventory",
        "source_path_or_url": _clean(table.get("source_path")),
        "page_locator": _page_locator(table),
        "excerpt": excerpt,
        "supports_or_contradicts": "supports",
        "evidence_strength": "weak",
    }


def _reference_row(stock_code: str, citation_id: str, chunk: pd.Series, poc_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "citation_id": citation_id,
        "stock_code": stock_code,
        "source_id": _source_id(chunk),
        "source_title": _clean(chunk.get("source_title"), Path(_source_path_or_url(chunk)).name),
        "source_type": _clean(chunk.get("source_type")),
        "source_path_or_url": _source_path_or_url(chunk),
        "page_locator": _page_locator(chunk),
        "parser": _clean(chunk.get("parser"), "docling"),
        "parser_version": _clean(poc_summary.get("docling_version"), "2.110.0"),
        "fetched_or_parsed_at": _clean(chunk.get("updated_at"), _now()),
    }


def _table_reference_row(stock_code: str, citation_id: str, table: pd.Series, poc_summary: dict[str, Any]) -> dict[str, Any]:
    source_path = _clean(table.get("source_path"))
    return {
        "citation_id": citation_id,
        "stock_code": stock_code,
        "source_id": _source_id(table),
        "source_title": Path(source_path).name if source_path else f"table {table.get('table_id')}",
        "source_type": "table_inventory",
        "source_path_or_url": source_path,
        "page_locator": _page_locator(table),
        "parser": _clean(table.get("parser"), "docling"),
        "parser_version": _clean(poc_summary.get("docling_version"), "2.110.0"),
        "fetched_or_parsed_at": _clean(table.get("updated_at"), _now()),
    }


def _evidence_row(stock_code: str, stock_name: str, section: str, claim_id: str, citation_id: str, source_id: str, excerpt: str, strength: str) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "report_section": section,
        "citation_id": citation_id,
        "source_id": source_id,
        "excerpt": excerpt,
        "evidence_strength": strength,
    }


def _match_chunks(stock_chunks: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    if stock_chunks.empty:
        return stock_chunks
    mask = stock_chunks["excerpt"].fillna("").astype(str).map(lambda text: any(keyword in text for keyword in keywords))
    return stock_chunks[mask].head(3)


def _match_tables(stock_tables: pd.DataFrame, section: str) -> pd.DataFrame:
    if stock_tables.empty:
        return stock_tables
    if section == "financial_snapshot":
        return stock_tables[stock_tables["table_relevance"].isin(["revenue_structure", "R&D_expense", "gross_margin", "financial_summary"])].head(2)
    if section == "risks_and_counter_evidence":
        return stock_tables[stock_tables["table_relevance"].eq("risk_disclosure")].head(2)
    if section in {"business_overview", "key_products"}:
        return stock_tables[stock_tables["table_relevance"].isin(["revenue_structure", "product_structure", "other", "unknown"])].head(2)
    return stock_tables.head(1)


def _table_relevance(row: pd.Series) -> str:
    text = " ".join(_clean(row.get(col)) for col in ["caption", "table_title", "table_text", "table_placeholder", "source_path"])
    rules = [
        ("revenue_structure", ["收入", "营业收入", "主营业务", "分产品", "分行业"]),
        ("product_structure", ["产品", "设备", "材料", "系统", "模块"]),
        ("R&D_expense", ["研发费用", "研发投入"]),
        ("R&D_personnel", ["研发人员", "技术人员"]),
        ("gross_margin", ["毛利", "毛利率"]),
        ("financial_summary", ["净利润", "现金流", "资产", "负债", "财务"]),
        ("customer_supplier", ["客户", "供应商"]),
        ("risk_disclosure", ["风险", "不确定性"]),
    ]
    for relevance, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return relevance
    return "unknown" if not text else "other"


def _render_report(summary: dict[str, Any], gap: pd.DataFrame, smoke_summary: dict[str, Any]) -> str:
    parsed = gap[gap["actual_status"].eq("parsed")]
    required = gap[gap["actual_status"].eq("evidence_required")]
    return f"""# Data-to-Brief Docling parser quality audit v1

Research-only parser quality and integration test. No signal, admission, scoring, strategy, or production candidate universe changes.

## Is Docling usable for Data-to-Brief source chunk generation?

Yes. Docling is usable as an optional parser adapter. It can provide source chunks and table inventory for source-backed Data-to-Brief reports without becoming a production dashboard, signal, or admission dependency.

## Which 3 pilot stocks were parsed successfully?

{parsed[['stock_code', 'stock_name', 'chunk_count', 'table_count']].to_markdown(index=False)}

## Which 2 pilot stocks remain evidence_required and why?

{required[['stock_code', 'stock_name', 'evidence_required_reason']].to_markdown(index=False)}

## Are source chunks citation-ready?

- source chunk rows: {summary['chunk_count']}
- citation-ready rows: {summary['citation_ready_chunk_count']}
- chunk warning rows: {summary['chunk_warning_count']}
- chunk fail rows: {summary['chunk_fail_count']}

## Are table inventory rows useful enough for financial/business evidence?

- table inventory rows: {summary['table_count']}
- table warning rows: {summary['table_warning_count']}
- table relevance unknown rows: {summary['table_relevance_unknown_count']}

Table rows are useful as inventory and candidate financial/business evidence. Missing table titles, row counts, column counts, or page locators are warnings, not hard blockers.

## Which report sections can be filled from Docling chunks?

The integration smoke test covers business_overview, key_products, hard_tech_bottleneck_thesis, technology_capability, financial_snapshot, and risks_and_counter_evidence. Filled or partial sections: {smoke_summary['filled_or_partial_section_count']}.

## Current parsing weaknesses

- Missing page locators in current manifest output.
- Table captions and row/column counts are frequently missing.
- 京泉华 and 浙江力诺 remain evidence_required because local PDFs are missing.
- Keyword-only matching is intentionally lightweight and should not become final report logic.

## Should Docling remain an optional adapter?

Yes. Docling should remain optional. The quality audit is artifact-based and does not require re-running Docling.

## Recommended next integration step

Integrate `source_chunk_manifest.csv` and `table_inventory.csv` into enriched report evidence_required filling logic as research-only inputs, then validate claim-citation maps before writing final report text.

## Guardrails

- research_only: true
- allowed_for_signal: false
- allowed_for_admission: false
- production_update: false
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
"""


def _source_id(row: pd.Series) -> str:
    return _clean(row.get("source_id")) or _clean(row.get("citation_id")) or Path(_clean(row.get("source_path"))).name


def _source_path_or_url(row: pd.Series) -> str:
    return _clean(row.get("source_path")) or _clean(row.get("source_url"))


def _page_locator(row: pd.Series) -> str:
    page_start = _clean(row.get("page_start"))
    page_end = _clean(row.get("page_end"))
    if page_start and page_end:
        return f"{page_start}-{page_end}"
    for col in ["page_locator", "page", "page_number"]:
        value = _clean(row.get(col))
        if value:
            return value
    return ""


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _normalize_code(value: Any) -> str:
    text = _clean(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
