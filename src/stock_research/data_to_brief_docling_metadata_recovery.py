from __future__ import annotations

import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "data_to_brief_docling_page_table_metadata_recovery_v1"
POC_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_parser_poc_v1"
INTEGRATION_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_enriched_report_docling_integration_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_page_table_metadata_recovery_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
PILOT_STOCKS = {
    "002371": {"stock_name": "北方华创", "has_local_pdf": True},
    "688012": {"stock_name": "中微公司", "has_local_pdf": True},
    "000400": {"stock_name": "许继电气", "has_local_pdf": True},
    "002885": {"stock_name": "京泉华", "has_local_pdf": False},
    "300838": {"stock_name": "浙江力诺", "has_local_pdf": False},
}
REPORT_SECTION_TITLES = {
    "business_overview": "主营业务与收入结构",
    "key_products": "核心产品与产业链位置",
    "hard_tech_bottleneck_thesis": "硬科技 / 卡脖子相关性",
    "technology_capability": "技术能力与研发投入",
    "financial_snapshot": "财务与经营快照",
    "risks_and_counter_evidence": "风险与反证",
}
FORBIDDEN_REPORT_TERMS = ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]


def run_data_to_brief_docling_metadata_recovery(
    *,
    poc_dir: str | Path = POC_DIR,
    integration_dir: str | Path = INTEGRATION_DIR,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, Any]:
    poc_path = Path(poc_dir)
    integration_path = Path(integration_dir)
    output_path = Path(output_dir)
    for subdir in ["reports_md", "reports_html", "reports_pdf", "evidence"]:
        (output_path / subdir).mkdir(parents=True, exist_ok=True)
    _ensure_inputs(poc_path, integration_path)

    source_chunks = _read_csv(poc_path / "source_chunk_manifest.csv")
    table_inventory = _read_csv(poc_path / "table_inventory.csv")
    old_package = _read_csv(integration_path / "docling_evidence_package.csv")
    old_claim_map = _read_csv(integration_path / "docling_claim_citation_map.csv")
    old_refs = _read_jsonl(integration_path / "docling_references.jsonl")
    old_status = _read_csv(integration_path / "pilot_docling_enriched_report_status.csv")

    raw_probe, text_probe, table_probe, parsed_index = _probe_docling_structures(poc_path)
    _write_jsonl(output_path / "docling_raw_structure_probe.jsonl", raw_probe)
    text_probe.to_csv(output_path / "docling_text_item_provenance_probe.csv", index=False)
    table_probe.to_csv(output_path / "docling_table_item_provenance_probe.csv", index=False)

    page_recovery = _recover_chunk_pages(source_chunks, text_probe)
    table_recovery = _recover_table_metadata(table_inventory, table_probe)
    page_recovery.to_csv(output_path / "docling_page_locator_recovery_audit.csv", index=False)
    table_recovery.to_csv(output_path / "docling_table_metadata_recovery_audit.csv", index=False)

    package = _upgrade_package(old_package, page_recovery, table_recovery)
    package.to_csv(output_path / "docling_evidence_package_with_metadata.csv", index=False)
    package.to_csv(output_path / "docling_evidence_matrix_with_metadata.csv", index=False)
    claim_map = _claim_map(package)
    claim_map.to_csv(output_path / "docling_claim_citation_map_with_metadata.csv", index=False)
    refs = _references(package, old_refs)
    _write_jsonl(output_path / "docling_references_with_metadata.jsonl", refs)
    upgrade_audit = _upgrade_audit(old_package, package)
    upgrade_audit.to_csv(output_path / "citation_granularity_upgrade_audit.csv", index=False)

    status_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    citation_audit_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    for stock_code, meta in PILOT_STOCKS.items():
        stock_package = package[package["stock_code"].eq(stock_code)].copy()
        stock_old_status = old_status[old_status["stock_code"].eq(stock_code)]
        status = _report_status(stock_code, meta, stock_package, stock_old_status, page_recovery, table_recovery)
        paths = _write_stock_report(output_path, stock_code, meta["stock_name"], stock_package, status)
        status_rows.append(status)
        manifest_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": meta["stock_name"],
                "report_md_path": str(paths["md"]),
                "report_html_path": str(paths["html"]),
                "report_pdf_path": str(paths["pdf"]),
                "evidence_matrix_path": str(paths["evidence_matrix"]),
                "sources_jsonl_path": str(paths["sources"]),
                "claim_citation_map_path": str(paths["claim_map"]),
                "report_status": status["report_status"],
                "citation_count": status["citation_count"],
                "citation_granularity_summary": f"page_level={status['page_level_citation_count']};source_level={status['source_level_citation_count']}",
                "blocker_reason": status["blocker_reason"],
                "updated_at": _now(),
            }
        )
        citation_audit_rows.extend(_citation_integrity(stock_code, paths["md"], paths["sources"], stock_package))
        quality_rows.append(_report_quality(stock_code, meta["stock_name"], paths["md"], status))

    status_df = pd.DataFrame(status_rows)
    status_df.to_csv(output_path / "pilot_docling_metadata_enriched_report_status.csv", index=False)
    pd.DataFrame(citation_audit_rows).to_csv(output_path / "citation_integrity_audit_with_metadata.csv", index=False)
    pd.DataFrame(quality_rows).to_csv(output_path / "report_quality_audit_with_metadata.csv", index=False)
    pd.DataFrame(manifest_rows).to_csv(output_path / "dashboard_docling_metadata_report_manifest_preview.csv", index=False)

    strategy_diff = _git_diff_formal_strategy_files()
    previous_count = int(old_package["citation_id"].nunique())
    preserved_count = int(package["citation_id"].nunique())
    page_count = int(package["citation_granularity"].eq("page_level").sum()) if not package.empty else 0
    source_count = int(package["citation_granularity"].eq("source_level").sum()) if not package.empty else 0
    missing_count = int(status_df["report_status"].eq("evidence_required").sum())
    acceptance = (
        "page_level_docling_metadata_ready"
        if page_count > 0 and preserved_count >= previous_count and missing_count == 2 and strategy_diff == ""
        else "source_level_docling_metadata_accepted"
        if preserved_count >= previous_count and missing_count == 2 and strategy_diff == ""
        else "metadata_recovery_blocked"
    )
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "pilot_stock_count": len(PILOT_STOCKS),
        "parsed_stock_count": 3,
        "missing_pdf_evidence_required_count": missing_count,
        "previous_citation_count": previous_count,
        "preserved_or_remapped_citation_count": preserved_count,
        "page_level_citation_count": page_count,
        "source_level_citation_count": source_count,
        "upgraded_to_page_level_count": int(upgrade_audit["upgrade_status"].eq("upgraded_to_page_level").sum()),
        "recovered_page_locator_count": int(page_recovery["recovery_status"].isin(["recovered", "partial"]).sum()) if not page_recovery.empty else 0,
        "recovered_table_metadata_count": int(table_recovery["recovery_status"].isin(["recovered", "partial"]).sum()) if not table_recovery.empty else 0,
        "metadata_recovery_status": "recovered_from_existing_docling_json" if parsed_index else "not_rerun_docling",
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "updated_at": _now(),
        "acceptance_decision": acceptance,
    }
    _write_json(output_path / "docling_metadata_recovery_summary.json", summary)
    (output_path / "docling_metadata_recovery_report.md").write_text(
        _render_report(summary, status_df, upgrade_audit, table_recovery),
        encoding="utf-8",
    )
    return {"summary": summary}


def _ensure_inputs(poc_dir: Path, integration_dir: Path) -> None:
    required = [
        poc_dir / "source_chunk_manifest.csv",
        poc_dir / "table_inventory.csv",
        integration_dir / "docling_evidence_package.csv",
        integration_dir / "docling_claim_citation_map.csv",
        integration_dir / "docling_references.jsonl",
        integration_dir / "pilot_docling_enriched_report_status.csv",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing metadata recovery inputs: " + ", ".join(missing))


def _probe_docling_structures(poc_dir: Path) -> tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    text_rows: list[dict[str, Any]] = []
    table_rows: list[dict[str, Any]] = []
    parsed_index: dict[str, dict[str, Any]] = {}
    for path in sorted((poc_dir / "parsed_documents").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append({"file": str(path), "probe_status": "failed", "error": str(exc)})
            continue
        stock_code = _normalize_code(payload.get("stock_code"))
        docling = payload.get("docling", {}) if isinstance(payload, dict) else {}
        parsed_index[stock_code] = docling
        texts = docling.get("texts", []) if isinstance(docling, dict) else []
        tables = docling.get("tables", []) if isinstance(docling, dict) else []
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": _clean(payload.get("stock_name")),
                "file": str(path),
                "probe_status": "parsed_json_available",
                "top_level_keys": "|".join(sorted(docling.keys())[:80]) if isinstance(docling, dict) else "",
                "text_item_count": len(texts),
                "table_item_count": len(tables),
                "has_pages": bool(docling.get("pages")) if isinstance(docling, dict) else False,
                "has_text_prov": any(bool(item.get("prov")) for item in texts if isinstance(item, dict)),
                "has_table_prov": any(bool(item.get("prov")) for item in tables if isinstance(item, dict)),
            }
        )
        for index, item in enumerate(texts):
            if not isinstance(item, dict):
                continue
            prov = item.get("prov", []) or []
            pages = sorted({str(p.get("page_no")) for p in prov if isinstance(p, dict) and p.get("page_no")})
            bbox = _bbox_string(prov[0].get("bbox")) if prov and isinstance(prov[0], dict) else ""
            text_rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": _clean(payload.get("stock_name")),
                    "docling_item_ref": _clean(item.get("self_ref"), f"#/texts/{index}"),
                    "item_index": index,
                    "label": _clean(item.get("label")),
                    "text": _clean(item.get("text"))[:1000],
                    "text_length": len(_clean(item.get("text"))),
                    "page_locator": ",".join(pages),
                    "bbox": bbox,
                    "has_provenance": bool(pages),
                    "parent_ref": _clean((item.get("parent") or {}).get("$ref")) if isinstance(item.get("parent"), dict) else "",
                }
            )
        for index, item in enumerate(tables):
            if not isinstance(item, dict):
                continue
            prov = item.get("prov", []) or []
            pages = sorted({str(p.get("page_no")) for p in prov if isinstance(p, dict) and p.get("page_no")})
            grid = ((item.get("data") or {}).get("grid") or []) if isinstance(item.get("data"), dict) else []
            caption_refs = [c.get("$ref") for c in item.get("captions", []) if isinstance(c, dict)]
            table_text = _table_grid_text(grid)
            table_rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": _clean(payload.get("stock_name")),
                    "docling_table_ref": _clean(item.get("self_ref"), f"#/tables/{index}"),
                    "table_index": index,
                    "page_locator": ",".join(pages),
                    "bbox": _bbox_string(prov[0].get("bbox")) if prov and isinstance(prov[0], dict) else "",
                    "caption_refs": "|".join(caption_refs),
                    "row_count": len(grid),
                    "column_count": max((len(row) for row in grid), default=0),
                    "table_text": table_text[:2000],
                    "has_provenance": bool(pages),
                    "has_table_data": bool(grid),
                }
            )
    return rows, pd.DataFrame(text_rows), pd.DataFrame(table_rows), parsed_index


def _recover_chunk_pages(chunks: pd.DataFrame, text_probe: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, chunk in chunks.iterrows():
        stock_code = _normalize_code(chunk.get("stock_code"))
        excerpt = _clean(chunk.get("excerpt"))
        stock_texts = text_probe[text_probe["stock_code"].eq(stock_code)] if not text_probe.empty else text_probe
        matched = _match_text_items(excerpt, stock_texts)
        pages = sorted({p for p in matched["page_locator"].fillna("").astype(str).tolist() if p})
        locator = _range_locator(pages)
        method = "text_match" if locator else "unavailable"
        status = "recovered" if locator else "unavailable"
        confidence = "high" if len(matched) >= 2 and locator else "medium" if locator else "low"
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": _clean(chunk.get("stock_name")),
                "source_id": _clean(chunk.get("citation_id")),
                "chunk_id": _clean(chunk.get("chunk_id")),
                "original_page_locator": "",
                "recovered_page_start": locator.split("-")[0] if locator else "",
                "recovered_page_end": locator.split("-")[-1] if locator else "",
                "recovered_page_locator": locator,
                "recovered_bbox": _clean(matched.iloc[0].get("bbox")) if not matched.empty else "",
                "docling_item_ref": "|".join(matched["docling_item_ref"].head(5).tolist()) if not matched.empty else "",
                "section_heading": _nearest_heading(matched, stock_texts),
                "recovery_method": method,
                "recovery_status": status,
                "confidence": confidence,
                "issue_warning": "" if locator else "page provenance unavailable for chunk text",
            }
        )
    return pd.DataFrame(rows)


def _recover_table_metadata(table_inventory: pd.DataFrame, table_probe: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, table in table_inventory.iterrows():
        stock_code = _normalize_code(table.get("stock_code"))
        table_id = _clean(table.get("table_id"))
        table_index = _table_index(table_id)
        matched = table_probe[(table_probe["stock_code"].eq(stock_code)) & (table_probe["table_index"].eq(table_index))] if not table_probe.empty else table_probe
        item = matched.iloc[0] if not matched.empty else pd.Series(dtype=object)
        locator = _clean(item.get("page_locator"))
        row_count = _clean(item.get("row_count"))
        column_count = _clean(item.get("column_count"))
        table_text = _clean(item.get("table_text"))
        status = "recovered" if locator and row_count and column_count else "partial" if locator or row_count or column_count else "unavailable"
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": _clean(table.get("stock_name")),
                "source_id": _clean(table.get("citation_id")),
                "table_id": table_id,
                "original_page_locator": "",
                "recovered_page_locator": locator,
                "original_table_title": _clean(table.get("caption")),
                "recovered_table_title": _infer_table_title(table_text),
                "recovered_table_caption": _infer_table_title(table_text),
                "original_row_count": _clean(table.get("row_count")),
                "recovered_row_count": row_count,
                "original_column_count": _clean(table.get("column_count")),
                "recovered_column_count": column_count,
                "has_table_markdown": bool(table_text),
                "has_table_csv_preview": bool(table_text),
                "has_table_html_preview": bool(table_text),
                "table_relevance": _table_relevance(table_text),
                "recovery_method": "direct_provenance" if locator else "unavailable",
                "recovery_status": status,
                "issue_warning": "" if status == "recovered" else "partial table metadata recovered" if status == "partial" else "table metadata unavailable",
            }
        )
    return pd.DataFrame(rows)


def _upgrade_package(old_package: pd.DataFrame, page_recovery: pd.DataFrame, table_recovery: pd.DataFrame) -> pd.DataFrame:
    page_map = page_recovery.set_index("chunk_id").to_dict("index") if "chunk_id" in page_recovery else {}
    table_map = (
        table_recovery.assign(_key=table_recovery["stock_code"].astype(str) + "|" + table_recovery["table_id"].astype(str))
        .drop_duplicates("_key")
        .set_index("_key")
        .to_dict("index")
        if {"stock_code", "table_id"}.issubset(table_recovery.columns)
        else {}
    )
    rows: list[dict[str, Any]] = []
    for _, row in old_package.iterrows():
        chunk_id = _clean(row.get("chunk_id"))
        table_id = _clean(row.get("table_id"))
        page_meta = page_map.get(chunk_id, {}) if chunk_id else {}
        table_meta = table_map.get(f"{_normalize_code(row.get('stock_code'))}|{table_id}", {}) if table_id else {}
        locator = _clean(table_meta.get("recovered_page_locator")) or _clean(page_meta.get("recovered_page_locator")) or _clean(row.get("page_locator"))
        new = row.to_dict()
        new["page_locator"] = locator
        new["citation_granularity"] = "page_level" if locator else "source_level"
        new["evidence_kind"] = "table" if table_id else "chunk"
        new["docling_item_ref"] = _clean(page_meta.get("docling_item_ref")) or _clean(table_meta.get("docling_table_ref"))
        new["section_heading"] = _clean(page_meta.get("section_heading"))
        new["recovered_table_title"] = _clean(table_meta.get("recovered_table_title"))
        new["recovered_row_count"] = _clean(table_meta.get("recovered_row_count"))
        new["recovered_column_count"] = _clean(table_meta.get("recovered_column_count"))
        if locator:
            new["issue_warning"] = _clean(row.get("issue_warning")).replace("missing_page_locator", "").strip("|")
        rows.append(new)
    return pd.DataFrame(rows)


def _upgrade_audit(old_package: pd.DataFrame, package: pd.DataFrame) -> pd.DataFrame:
    old_map = old_package.set_index("citation_id").to_dict("index") if "citation_id" in old_package else {}
    rows = []
    for _, row in package.iterrows():
        old = old_map.get(_clean(row.get("citation_id")), {})
        old_grain = _clean(old.get("citation_granularity"), "source_level")
        new_grain = _clean(row.get("citation_granularity"))
        status = "upgraded_to_page_level" if old_grain != "page_level" and new_grain == "page_level" else "still_source_level" if new_grain == "source_level" else "unavailable"
        rows.append(
            {
                "stock_code": _normalize_code(row.get("stock_code")),
                "citation_id": _clean(row.get("citation_id")),
                "source_id": _clean(row.get("source_id")),
                "chunk_id": _clean(row.get("chunk_id")),
                "table_id": _clean(row.get("table_id")),
                "old_citation_granularity": old_grain,
                "new_citation_granularity": new_grain,
                "old_page_locator": _clean(old.get("page_locator")),
                "new_page_locator": _clean(row.get("page_locator")),
                "upgrade_status": status,
                "reason": "page provenance recovered" if status == "upgraded_to_page_level" else "no recovered page locator available",
            }
        )
    return pd.DataFrame(rows)


def _report_status(stock_code: str, meta: dict[str, Any], package: pd.DataFrame, old_status: pd.DataFrame, page_recovery: pd.DataFrame, table_recovery: pd.DataFrame) -> dict[str, Any]:
    old = old_status.iloc[0].to_dict() if not old_status.empty else {}
    citation_count = int(package["citation_id"].nunique()) if not package.empty else 0
    page_count = int(package["citation_granularity"].eq("page_level").sum()) if not package.empty else 0
    source_count = int(package["citation_granularity"].eq("source_level").sum()) if not package.empty else 0
    table_count = int(package["evidence_kind"].eq("table").sum()) if "evidence_kind" in package else 0
    recovered_page_count = int(page_recovery[(page_recovery["stock_code"].eq(stock_code)) & (page_recovery["recovery_status"].isin(["recovered", "partial"]))].shape[0]) if not page_recovery.empty else 0
    recovered_table_count = int(table_recovery[(table_recovery["stock_code"].eq(stock_code)) & (table_recovery["recovery_status"].isin(["recovered", "partial"]))].shape[0]) if not table_recovery.empty else 0
    if not meta["has_local_pdf"]:
        status = "evidence_required"
        blocker = "missing_local_pdf"
    elif page_count > 0:
        status = "page_level_docling_enriched"
        blocker = _clean(old.get("blocker_reason"))
    elif citation_count > 0:
        status = "source_level_docling_enriched"
        blocker = _clean(old.get("blocker_reason")) or "page locator unavailable"
    else:
        status = "evidence_required"
        blocker = "no recovered evidence"
    return {
        "stock_code": stock_code,
        "stock_name": meta["stock_name"],
        "report_status": status,
        "citation_count": citation_count,
        "page_level_citation_count": page_count,
        "source_level_citation_count": source_count,
        "table_citation_count": table_count,
        "recovered_page_locator_count": recovered_page_count,
        "recovered_table_metadata_count": recovered_table_count,
        "evidence_required_section_count": int(old.get("evidence_required_section_count", 6 if status == "evidence_required" else 0)),
        "blocker_reason": blocker,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
    }


def _write_stock_report(output_dir: Path, stock_code: str, stock_name: str, package: pd.DataFrame, status: dict[str, Any]) -> dict[str, Path]:
    evidence_dir = output_dir / "evidence" / stock_code
    evidence_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "reports_md" / f"{stock_code}_{stock_name}_docling_metadata_enriched_report.md"
    html_path = output_dir / "reports_html" / f"{stock_code}_{stock_name}_docling_metadata_enriched_report.html"
    pdf_path = output_dir / "reports_pdf" / f"{stock_code}_{stock_name}_docling_metadata_enriched_report.pdf"
    sources_path = evidence_dir / "sources.jsonl"
    matrix_path = evidence_dir / "evidence_matrix.csv"
    claim_path = evidence_dir / "claim_citation_map.csv"
    status_path = evidence_dir / "report_status.json"
    refs = _references(package, [])
    _write_jsonl(sources_path, refs)
    package.to_csv(matrix_path, index=False)
    _claim_map(package).to_csv(claim_path, index=False)
    _write_json(status_path, status)
    markdown = _stock_report_markdown(stock_code, stock_name, package, status, refs)
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    _render_pdf(markdown, pdf_path)
    return {"md": md_path, "html": html_path, "pdf": pdf_path, "sources": sources_path, "evidence_matrix": matrix_path, "claim_map": claim_path, "status": status_path}


def _stock_report_markdown(stock_code: str, stock_name: str, package: pd.DataFrame, status: dict[str, Any], refs: list[dict[str, Any]]) -> str:
    lines = [
        f"# {stock_code} {stock_name}：Docling Metadata-Enriched Report",
        "",
        "Research-only. No signal, no admission, no production update.",
        "",
        "## 1. 研究结论摘要",
        f"- report_status: {status['report_status']}",
        f"- page_level_citation_count: {status['page_level_citation_count']}",
        f"- source_level_citation_count: {status['source_level_citation_count']}",
        f"- blocker_reason: {status['blocker_reason'] or 'none'}",
        "",
    ]
    idx = 2
    for section_key, title in REPORT_SECTION_TITLES.items():
        lines.append(f"## {idx}. {title}")
        section = package[package["report_section"].eq(section_key)] if not package.empty else package
        if section.empty:
            lines.append("evidence_required")
        else:
            for _, row in section.head(3).iterrows():
                excerpt = _sanitize(_clean(row.get("excerpt")))[:260]
                note = "page-level" if _clean(row.get("citation_granularity")) == "page_level" else "source-level warning"
                lines.append(f"- {excerpt} [{row['citation_id']}] ({note})")
        lines.append("")
        idx += 1
    lines.extend(
        [
            f"## {idx}. Evidence Required / 证据缺口",
            status["blocker_reason"] or "remaining evidence_required sections are listed in status artifacts",
            "",
            f"## {idx + 1}. Research-only 复盘结论",
            "This report only validates Docling metadata recovery for evidence routing. It does not create recommendations or production decisions.",
            "",
            "## 引用与数据源 / References",
        ]
    )
    if not refs:
        lines.append("- evidence_required: no local PDF / no recovered citation")
    for ref in refs:
        locator = _clean(ref.get("page_locator")) or "source_level"
        lines.append(f"- [{ref['citation_id']}] {_sanitize(_clean(ref.get('source_title')))}; locator={locator}; path={ref.get('source_path_or_url')}")
    return "\n".join(lines) + "\n"


def _citation_integrity(stock_code: str, md_path: Path, sources_path: Path, package: pd.DataFrame) -> list[dict[str, Any]]:
    text = md_path.read_text(encoding="utf-8")
    inline = set(re.findall(r"\[(S\d+)\]", text))
    refs = _read_jsonl(sources_path) if sources_path.exists() else []
    ref_ids = {str(row["citation_id"]) for row in refs}
    rows: list[dict[str, Any]] = []
    if not inline:
        rows.append(
            {
                "stock_code": stock_code,
                "citation_id": "",
                "integrity_status": "pass",
                "issue_detail": "evidence_required stub has no citations",
            }
        )
    for citation_id in sorted(inline):
        row = package[package["citation_id"].eq(citation_id)]
        ok = citation_id in ref_ids and not row.empty and row["source_id"].fillna("").astype(str).str.len().gt(0).any()
        if ok and row["citation_granularity"].eq("page_level").any():
            ok = row["page_locator"].fillna("").astype(str).str.len().gt(0).any()
        rows.append(
            {
                "stock_code": stock_code,
                "citation_id": citation_id,
                "integrity_status": "pass" if ok else "fail",
                "issue_detail": "" if ok else "citation/reference/provenance mapping failed",
            }
        )
    return rows


def _report_quality(stock_code: str, stock_name: str, md_path: Path, status: dict[str, Any]) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    hits = [term for term in FORBIDDEN_REPORT_TERMS if term.lower() in text.lower()]
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "report_status": status["report_status"],
        "has_references_section": "## 引用与数据源 / References" in text,
        "forbidden_language_hit_count": len(hits),
        "forbidden_language_hits": "|".join(hits),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "quality_status": "pass" if not hits and "## 引用与数据源 / References" in text else "fail",
    }


def _match_text_items(excerpt: str, stock_texts: pd.DataFrame) -> pd.DataFrame:
    if stock_texts.empty or not excerpt:
        return stock_texts.iloc[0:0]
    compact_excerpt = _compact(excerpt)
    scored = []
    for _, item in stock_texts.iterrows():
        text = _compact(item.get("text"))
        if not text:
            continue
        score = 0
        if text[:80] and text[:80] in compact_excerpt:
            score += 2
        if compact_excerpt[:80] and compact_excerpt[:80] in text:
            score += 3
        overlap = len(set(text) & set(compact_excerpt))
        if overlap > 30:
            score += 1
        if score:
            scored.append((score, item))
    if not scored:
        return stock_texts.iloc[0:0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return pd.DataFrame([item for _, item in scored[:8]])


def _nearest_heading(matched: pd.DataFrame, stock_texts: pd.DataFrame) -> str:
    if matched.empty or stock_texts.empty:
        return ""
    first_index = int(matched.iloc[0].get("item_index", 0))
    prior = stock_texts[(stock_texts["item_index"] <= first_index) & (stock_texts["label"].astype(str).str.contains("section_header", na=False))]
    return _clean(prior.iloc[-1].get("text")) if not prior.empty else ""


def _table_index(table_id: str) -> int:
    match = re.search(r"(\d+)$", table_id or "")
    return int(match.group(1)) - 1 if match else -1


def _table_grid_text(grid: Any) -> str:
    rows = []
    if not isinstance(grid, list):
        return ""
    for row in grid[:20]:
        if not isinstance(row, list):
            continue
        rows.append(" | ".join(_clean(cell.get("text")) for cell in row if isinstance(cell, dict)))
    return "\n".join(rows)


def _infer_table_title(text: str) -> str:
    if not text:
        return ""
    first = text.splitlines()[0].strip()
    return first[:120]


def _table_relevance(text: str) -> str:
    if any(k in text for k in ["收入", "营业收入", "分产品", "分行业"]):
        return "revenue_structure"
    if any(k in text for k in ["研发费用", "研发投入"]):
        return "R&D_expense"
    if any(k in text for k in ["毛利", "毛利率"]):
        return "gross_margin"
    if any(k in text for k in ["净利润", "现金流", "资产", "负债"]):
        return "financial_summary"
    return "other" if text else "unknown"


def _references(package: pd.DataFrame, old_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if package.empty:
        return []
    old_by_id = {str(row.get("citation_id")): row for row in old_refs}
    refs = []
    for _, row in package.drop_duplicates("citation_id").sort_values("citation_id").iterrows():
        old = old_by_id.get(_clean(row.get("citation_id")), {})
        refs.append(
            {
                "citation_id": _clean(row.get("citation_id")),
                "stock_code": _normalize_code(row.get("stock_code")),
                "source_id": _clean(row.get("source_id")),
                "source_title": _clean(row.get("source_title")) or _clean(old.get("source_title")),
                "source_type": _clean(row.get("source_type")) or _clean(old.get("source_type")),
                "source_path_or_url": _clean(row.get("source_path_or_url")) or _clean(old.get("source_path_or_url")),
                "page_locator": _clean(row.get("page_locator")),
                "citation_granularity": _clean(row.get("citation_granularity")),
                "parser": _clean(row.get("parser"), "docling"),
                "parser_version": _clean(row.get("parser_version"), "2.110.0"),
                "fetched_or_parsed_at": _now(),
            }
        )
    return refs


def _claim_map(package: pd.DataFrame) -> pd.DataFrame:
    if package.empty:
        return pd.DataFrame(columns=["stock_code", "claim_id", "report_section", "citation_id", "source_id", "chunk_id", "table_id", "citation_granularity", "page_locator", "excerpt"])
    frame = package.copy()
    frame["claim_id"] = frame["stock_code"] + "-" + frame["report_section"] + "-" + frame["evidence_id"]
    return frame[
        [
            "stock_code",
            "claim_id",
            "report_section",
            "citation_id",
            "source_id",
            "chunk_id",
            "table_id",
            "source_type",
            "source_path_or_url",
            "page_locator",
            "citation_granularity",
            "excerpt",
            "supports_or_contradicts",
            "evidence_strength",
        ]
    ]


def _render_report(summary: dict[str, Any], status: pd.DataFrame, upgrade: pd.DataFrame, table_recovery: pd.DataFrame) -> str:
    page_sentence = (
        f"Docling provided usable page-level provenance for {summary['page_level_citation_count']} citations."
        if summary["page_level_citation_count"] > 0
        else "page-level provenance could not be recovered from the current adapter artifacts."
    )
    ten_stock = "ready for a 10-stock batch pilot" if summary["page_level_citation_count"] > 0 else "acceptable for internal source-level drafts, but page/table metadata should improve before a 10-stock final-report pilot"
    full_batch = "not ready for 90-stock full batch until page/table metadata is reliable"
    return f"""# Docling page/table metadata recovery v1

Research-only metadata recovery test. No signal, admission, scoring, strategy, or production candidate universe changes.

## Did Docling provide usable page-level provenance?

{page_sentence}

## Citation granularity

- previous citations: {summary['previous_citation_count']}
- preserved/remapped citations: {summary['preserved_or_remapped_citation_count']}
- upgraded to page-level: {summary['upgraded_to_page_level_count']}
- page-level citations: {summary['page_level_citation_count']}
- source-level citations: {summary['source_level_citation_count']}

## Did table metadata improve?

- recovered/partial table metadata rows: {summary['recovered_table_metadata_count']}
- table audit rows: {len(table_recovery)}

## Report status

{status[['stock_code', 'stock_name', 'report_status', 'citation_count', 'page_level_citation_count', 'source_level_citation_count', 'blocker_reason']].to_markdown(index=False)}

## Which report sections remain evidence_required?

See `pilot_docling_metadata_enriched_report_status.csv`; missing-PDF stocks remain evidence_required and parsed stocks retain any section-level gaps from the previous integration.

## Is Docling ready for 10-stock batch pilot?

{ten_stock}.

## Is Docling ready for 90-stock full batch?

{full_batch}.

## Should Docling remain optional?

Yes. Docling should remain an optional Data-to-Brief parser adapter.

## Next recommended step

If page locators are recovered, proceed to a 10-stock batch pilot. If page locators remain unavailable, accept source-level citations for internal drafts but add page/table metadata extraction or a fallback parser before 90-stock final reports.

## Guardrails

- allowed_for_signal: false
- allowed_for_admission: false
- production_update: false
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- acceptance_decision: {summary['acceptance_decision']}
"""


def _markdown_to_html(markdown: str) -> str:
    body = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.strip():
            body.append(f"<p>{html.escape(line)}</p>")
    return "<!doctype html><html><head><meta charset='utf-8'><title>Docling metadata recovery</title></head><body>" + "\n".join(body) + "</body></html>"


def _render_pdf(markdown: str, path: Path) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        path.write_bytes(b"%PDF-1.4\n% fallback placeholder\n")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    y = height - 40
    pdf.setFont("Helvetica", 8)
    for raw in markdown.splitlines():
        line = raw.encode("latin-1", "replace").decode("latin-1")
        pdf.drawString(36, y, line[:120])
        y -= 11
        if y < 36:
            pdf.showPage()
            pdf.setFont("Helvetica", 8)
            y = height - 40
    pdf.save()


def _sanitize(text: str) -> str:
    sanitized = text
    replacements = {
        "买入": "评级信息已省略",
        "卖出": "评级信息已省略",
        "目标价": "估值表述已省略",
        "target price": "valuation wording omitted",
        "buy recommendation": "rating wording omitted",
        "sell recommendation": "rating wording omitted",
    }
    for term, replacement in replacements.items():
        sanitized = re.sub(re.escape(term), replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def _bbox_string(bbox: Any) -> str:
    if not isinstance(bbox, dict):
        return ""
    keys = ["l", "t", "r", "b"]
    return ",".join(f"{key}={bbox.get(key)}" for key in keys if key in bbox)


def _range_locator(pages: list[str]) -> str:
    numbers = sorted({int(part) for value in pages for part in str(value).split(",") if str(part).isdigit()})
    if not numbers:
        return ""
    return str(numbers[0]) if numbers[0] == numbers[-1] else f"{numbers[0]}-{numbers[-1]}"


def _compact(text: Any) -> str:
    return re.sub(r"\s+", "", _clean(text))


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str})
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_normalize_code)
    return frame


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")


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


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""
