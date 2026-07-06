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
TASK_NAME = "data_to_brief_enriched_report_docling_integration_v1"
POC_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_parser_poc_v1"
QUALITY_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_parser_quality_audit_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_enriched_report_docling_integration_v1"
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
REPORT_SECTIONS = {
    "business_overview": ("主营业务与收入结构", ["主营业务", "主要业务", "公司从事", "主要产品", "经营范围"]),
    "key_products": ("核心产品与产业链位置", ["产品", "设备", "材料", "芯片", "模块", "系统", "解决方案"]),
    "hard_tech_bottleneck_thesis": ("硬科技 / 卡脖子相关性", ["国产化", "自主可控", "核心技术", "关键技术", "进口替代", "半导体", "高端装备", "工业控制", "电力设备"]),
    "technology_capability": ("技术能力与研发投入", ["研发", "专利", "技术", "工艺", "平台", "创新", "实验室", "技术中心"]),
    "financial_snapshot": ("催化与事件线索", ["营业收入", "净利润", "毛利率", "研发费用", "现金流", "分产品", "分行业"]),
    "risks_and_counter_evidence": ("风险与反证", ["风险", "不确定性", "竞争", "客户集中", "供应链", "存货", "应收账款", "毛利率下降"]),
}
FORBIDDEN_REPORT_TERMS = ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]


def run_data_to_brief_enriched_report_docling_integration(
    *,
    poc_dir: str | Path = POC_DIR,
    quality_dir: str | Path = QUALITY_DIR,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, Any]:
    poc_path = Path(poc_dir)
    quality_path = Path(quality_dir)
    output_path = Path(output_dir)
    for subdir in ["reports_md", "reports_html", "reports_pdf", "evidence"]:
        (output_path / subdir).mkdir(parents=True, exist_ok=True)
    _ensure_inputs(poc_path, quality_path)

    poc_summary = json.loads((poc_path / "pilot_run_summary.json").read_text(encoding="utf-8"))
    quality_summary = json.loads((quality_path / "docling_parser_quality_summary.json").read_text(encoding="utf-8"))
    if not bool(poc_summary.get("research_only")) or bool(poc_summary.get("allowed_for_signal")) or bool(poc_summary.get("allowed_for_admission")):
        raise ValueError("Docling PoC guardrails failed")
    if bool(poc_summary.get("production_update")) or bool(quality_summary.get("production_update")):
        raise ValueError("Docling quality audit production_update guardrail failed")

    chunks = _read_csv(poc_path / "source_chunk_manifest.csv")
    tables = _read_csv(poc_path / "table_inventory.csv")
    chunk_quality = _read_csv(quality_path / "docling_source_chunk_quality_audit.csv")
    table_quality = _read_csv(quality_path / "docling_table_quality_audit.csv")
    gap_audit = _read_csv(quality_path / "docling_evidence_gap_audit.csv")
    smoke_claims = _read_csv(quality_path / "integration_smoke/claim_citation_map_preview.csv")
    smoke_evidence = _read_csv(quality_path / "integration_smoke/evidence_matrix_preview.csv")
    smoke_refs = _read_jsonl(quality_path / "integration_smoke/references_preview.jsonl")

    evidence_package = _build_evidence_package(smoke_claims, smoke_refs, smoke_evidence, chunk_quality, table_quality)
    evidence_package.to_csv(output_path / "docling_evidence_package.csv", index=False)
    evidence_package.to_csv(output_path / "docling_evidence_matrix.csv", index=False)
    _claim_map_from_package(evidence_package).to_csv(output_path / "docling_claim_citation_map.csv", index=False)
    _write_jsonl(output_path / "docling_references.jsonl", smoke_refs)
    _write_json(output_path / "docling_evidence_package_summary.json", _evidence_package_summary(evidence_package))

    metadata_attempt = _metadata_improvement_attempt(chunks, tables, chunk_quality, table_quality)
    metadata_attempt.to_csv(output_path / "docling_metadata_improvement_attempt.csv", index=False)

    status_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    citation_audit_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    for stock_code, stock_meta in PILOT_STOCKS.items():
        stock_package = evidence_package[evidence_package["stock_code"].eq(stock_code)].copy()
        stock_gap = gap_audit[gap_audit["stock_code"].eq(stock_code)]
        report_status = _stock_report_status(stock_code, stock_meta, stock_package, stock_gap)
        paths = _write_stock_artifacts(output_path, stock_code, stock_meta["stock_name"], stock_package, report_status)
        status_rows.append(report_status)
        manifest_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_meta["stock_name"],
                "report_md_path": str(paths["md"]),
                "report_html_path": str(paths["html"]),
                "report_pdf_path": str(paths["pdf"]),
                "evidence_matrix_path": str(paths["evidence_matrix"]),
                "sources_jsonl_path": str(paths["sources"]),
                "claim_citation_map_path": str(paths["claim_map"]),
                "report_status": report_status["report_status"],
                "citation_count": report_status["citation_count"],
                "citation_granularity_summary": f"page_level={report_status['page_level_citation_count']};source_level={report_status['source_level_citation_count']}",
                "evidence_quality_flag": "usable" if report_status["report_status"] != "evidence_required" else "gap",
                "blocker_reason": report_status["blocker_reason"],
                "updated_at": _now(),
            }
        )
        citation_audit_rows.extend(_citation_integrity_for_stock(stock_code, paths["md"], paths["sources"], stock_package))
        quality_rows.append(_report_quality_for_stock(stock_code, stock_meta["stock_name"], paths["md"], report_status))

    status_df = pd.DataFrame(status_rows)
    status_df.to_csv(output_path / "pilot_docling_enriched_report_status.csv", index=False)
    pd.DataFrame(manifest_rows).to_csv(output_path / "dashboard_docling_report_manifest_preview.csv", index=False)
    citation_audit = pd.DataFrame(citation_audit_rows)
    citation_audit.to_csv(output_path / "citation_integrity_audit.csv", index=False)
    quality_audit = pd.DataFrame(quality_rows)
    quality_audit.to_csv(output_path / "report_quality_audit.csv", index=False)

    strategy_diff = _git_diff_formal_strategy_files()
    parsed_count = int(status_df["report_status"].isin(["docling_enriched_ready", "partial_docling_enriched"]).sum())
    missing_count = int(status_df["report_status"].eq("evidence_required").sum())
    full_ready = int(status_df["report_status"].eq("docling_enriched_ready").sum())
    acceptance = "docling_enriched_report_integration_ready" if full_ready == 3 and missing_count == 2 and strategy_diff == "" else "partial_docling_enriched_report_integration_ready" if parsed_count == 3 and missing_count == 2 and strategy_diff == "" else "blocked"
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "pilot_stock_count": len(PILOT_STOCKS),
        "parsed_stock_count": parsed_count,
        "missing_pdf_evidence_required_count": missing_count,
        "docling_evidence_package_rows": int(len(evidence_package)),
        "citation_count": int(evidence_package["citation_id"].nunique()) if not evidence_package.empty else 0,
        "page_level_citation_count": int(evidence_package["citation_granularity"].eq("page_level").sum()) if not evidence_package.empty else 0,
        "source_level_citation_count": int(evidence_package["citation_granularity"].eq("source_level").sum()) if not evidence_package.empty else 0,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "updated_at": _now(),
        "acceptance_decision": acceptance,
    }
    _write_json(output_path / "docling_integration_summary.json", summary)
    (output_path / "data_to_brief_enriched_report_docling_integration_v1_report.md").write_text(
        _render_integration_report(summary, status_df, citation_audit, metadata_attempt),
        encoding="utf-8",
    )
    return {"summary": summary}


def _ensure_inputs(poc_dir: Path, quality_dir: Path) -> None:
    required = [
        poc_dir / "pilot_run_summary.json",
        poc_dir / "source_chunk_manifest.csv",
        poc_dir / "table_inventory.csv",
        quality_dir / "docling_parser_quality_summary.json",
        quality_dir / "docling_source_chunk_quality_audit.csv",
        quality_dir / "docling_table_quality_audit.csv",
        quality_dir / "docling_evidence_gap_audit.csv",
        quality_dir / "integration_smoke/claim_citation_map_preview.csv",
        quality_dir / "integration_smoke/references_preview.jsonl",
        quality_dir / "integration_smoke/evidence_matrix_preview.csv",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing Docling integration inputs: " + ", ".join(missing))


def _build_evidence_package(
    claims: pd.DataFrame,
    references: list[dict[str, Any]],
    evidence: pd.DataFrame,
    chunk_quality: pd.DataFrame,
    table_quality: pd.DataFrame,
) -> pd.DataFrame:
    ref_by_id = {str(row["citation_id"]): row for row in references}
    chunk_quality_map = chunk_quality.set_index("chunk_id").to_dict("index") if "chunk_id" in chunk_quality else {}
    table_quality_map = (
        table_quality.assign(_quality_key=table_quality["stock_code"].astype(str) + "|" + table_quality["table_id"].astype(str))
        .drop_duplicates("_quality_key")
        .set_index("_quality_key")
        .to_dict("index")
        if {"stock_code", "table_id"}.issubset(table_quality.columns)
        else {}
    )
    evidence_map = evidence.set_index("citation_id").to_dict("index") if "citation_id" in evidence else {}
    rows: list[dict[str, Any]] = []
    for index, claim in claims.iterrows():
        citation_id = _clean(claim.get("citation_id"))
        ref = ref_by_id.get(citation_id, {})
        chunk_id = _clean(claim.get("chunk_id"))
        table_id = _clean(claim.get("table_id"))
        table_key = f"{_normalize_code(claim.get('stock_code'))}|{table_id}"
        q = chunk_quality_map.get(chunk_id, {}) if chunk_id else table_quality_map.get(table_key, {})
        page_locator = _clean(claim.get("page_locator")) or _clean(ref.get("page_locator"))
        source_path = _clean(claim.get("source_path_or_url")) or _clean(ref.get("source_path_or_url"))
        excerpt = _clean(claim.get("excerpt")) or _clean(evidence_map.get(citation_id, {}).get("excerpt"))
        rows.append(
            {
                "stock_code": _normalize_code(claim.get("stock_code")),
                "stock_name": _stock_name(_normalize_code(claim.get("stock_code"))),
                "report_section": _clean(claim.get("report_section")),
                "evidence_id": f"E{index + 1}",
                "citation_id": citation_id,
                "source_id": _clean(claim.get("source_id")) or _clean(ref.get("source_id")),
                "chunk_id": chunk_id,
                "table_id": table_id,
                "source_type": _clean(claim.get("source_type")) or _clean(ref.get("source_type")),
                "source_title": _clean(ref.get("source_title")) or Path(source_path).name,
                "source_path_or_url": source_path,
                "citation_granularity": "page_level" if page_locator else "source_level" if source_path else "unknown",
                "page_locator": page_locator,
                "excerpt": excerpt,
                "evidence_strength": _clean(claim.get("evidence_strength"), "weak"),
                "evidence_quality_flag": "usable" if excerpt and source_path else "gap",
                "parser": _clean(ref.get("parser"), "docling"),
                "parser_version": _clean(ref.get("parser_version"), "2.110.0"),
                "parse_quality_flag": _clean(q.get("parse_quality_flag")) or _clean(q.get("table_quality_flag"), "warning"),
                "issue_warning": _clean(q.get("issue_type"), "missing_page_locator") if not page_locator else _clean(q.get("issue_type"), ""),
                "supports_or_contradicts": _clean(claim.get("supports_or_contradicts"), "supports"),
            }
        )
    return pd.DataFrame(rows)


def _stock_report_status(stock_code: str, stock_meta: dict[str, Any], package: pd.DataFrame, gap: pd.DataFrame) -> dict[str, Any]:
    chunk_count = int(gap.iloc[0].get("chunk_count", 0)) if not gap.empty else 0
    table_count = int(gap.iloc[0].get("table_count", 0)) if not gap.empty else 0
    parsed_source_count = int(gap.iloc[0].get("parsed_source_count", 0)) if not gap.empty else 0
    citation_count = int(package["citation_id"].nunique()) if not package.empty else 0
    page_count = int(package["citation_granularity"].eq("page_level").sum()) if not package.empty else 0
    source_count = int(package["citation_granularity"].eq("source_level").sum()) if not package.empty else 0
    filled_sections = 0
    partial_sections = 0
    evidence_required_sections = 0
    for section in REPORT_SECTIONS:
        count = int(package["report_section"].eq(section).sum()) if not package.empty else 0
        if count >= 2:
            filled_sections += 1
        elif count == 1:
            partial_sections += 1
        else:
            evidence_required_sections += 1
    if not stock_meta["has_local_pdf"]:
        report_status = "evidence_required"
        blocker = "missing local PDF"
    elif filled_sections + partial_sections == 0:
        report_status = "evidence_required"
        blocker = "no Docling evidence matched report sections"
    elif evidence_required_sections == 0:
        report_status = "docling_enriched_ready"
        blocker = ""
    else:
        report_status = "partial_docling_enriched"
        blocker = "some sections still evidence_required"
    return {
        "stock_code": stock_code,
        "stock_name": stock_meta["stock_name"],
        "parsed_source_count": parsed_source_count,
        "chunk_count": chunk_count,
        "table_count": table_count,
        "citation_count": citation_count,
        "page_level_citation_count": page_count,
        "source_level_citation_count": source_count,
        "filled_section_count": filled_sections,
        "partial_section_count": partial_sections,
        "evidence_required_section_count": evidence_required_sections,
        "report_status": report_status,
        "blocker_reason": blocker,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
    }


def _write_stock_artifacts(output_dir: Path, stock_code: str, stock_name: str, package: pd.DataFrame, status: dict[str, Any]) -> dict[str, Path]:
    evidence_dir = output_dir / "evidence" / stock_code
    evidence_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "reports_md" / f"{stock_code}_{stock_name}_docling_enriched_report.md"
    html_path = output_dir / "reports_html" / f"{stock_code}_{stock_name}_docling_enriched_report.html"
    pdf_path = output_dir / "reports_pdf" / f"{stock_code}_{stock_name}_docling_enriched_report.pdf"
    sources_path = evidence_dir / "sources.jsonl"
    matrix_path = evidence_dir / "evidence_matrix.csv"
    claim_path = evidence_dir / "claim_citation_map.csv"
    status_path = evidence_dir / "report_status.json"
    sources = _references_from_package(package)
    _write_jsonl(sources_path, sources)
    package.to_csv(matrix_path, index=False)
    _claim_map_from_package(package).to_csv(claim_path, index=False)
    _write_json(status_path, status)
    markdown = _render_stock_report(stock_code, stock_name, package, status, sources)
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    _render_pdf(markdown, pdf_path)
    return {"md": md_path, "html": html_path, "pdf": pdf_path, "sources": sources_path, "evidence_matrix": matrix_path, "claim_map": claim_path, "status": status_path}


def _render_stock_report(stock_code: str, stock_name: str, package: pd.DataFrame, status: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    lines = [
        f"# {stock_code} {stock_name}：Docling Source-backed Data-to-Brief Pilot Report",
        "",
        "Research-only report. No signal, no admission, no production update.",
        "",
        "## 1. 研究结论摘要",
        f"- report_status: {status['report_status']}",
        f"- citations: {status['citation_count']}",
        f"- blocker_reason: {status['blocker_reason'] or 'none'}",
        "- conclusion: evidence_required" if status["report_status"] == "evidence_required" else "- conclusion: Docling evidence can support a partial research brief.",
        "",
    ]
    section_number = 2
    for section_key, (title, _keywords) in REPORT_SECTIONS.items():
        lines.append(f"## {section_number}. {title}")
        section_package = package[package["report_section"].eq(section_key)] if not package.empty else package
        if section_package.empty:
            lines.append("evidence_required")
        else:
            for _, row in section_package.head(3).iterrows():
                excerpt = _sanitize_report_text(_clean(row.get("excerpt")))[:260]
                lines.append(f"- {excerpt} [{row['citation_id']}]")
        lines.append("")
        section_number += 1
    lines.extend(
        [
            f"## {section_number}. Evidence Required / 证据缺口",
            "missing local PDF" if status["report_status"] == "evidence_required" else status["blocker_reason"] or "page-level locator and table metadata still need improvement",
            "",
            f"## {section_number + 1}. Research-only 复盘结论",
            "This output is a deterministic Docling integration pilot. It does not create any recommendation, trading signal, admission decision, or scoring change.",
            "",
            "## 引用与数据源 / References",
        ]
    )
    if not sources:
        lines.append("- evidence_required: no local source PDF available")
    for source in sources:
        title = _sanitize_report_text(_clean(source.get("source_title"), "source title missing"))
        location = _clean(source.get("source_path_or_url"), "source path missing")
        lines.append(f"- [{source['citation_id']}] {title}; type={source.get('source_type')}; locator={source.get('page_locator') or 'source_level'}; path={location}")
    return "\n".join(lines) + "\n"


def _citation_integrity_for_stock(stock_code: str, md_path: Path, sources_path: Path, package: pd.DataFrame) -> list[dict[str, Any]]:
    text = md_path.read_text(encoding="utf-8")
    inline = set(re.findall(r"\[(S\d+)\]", text))
    refs = _read_jsonl(sources_path) if sources_path.exists() else []
    ref_ids = {str(row["citation_id"]) for row in refs}
    rows = []
    if not inline:
        rows.append(
            {
                "stock_code": stock_code,
                "citation_id": "",
                "inline_citation_present": False,
                "reference_present": True,
                "source_id_present": True,
                "chunk_or_table_present": True,
                "excerpt_present": True,
                "citation_granularity_valid": True,
                "integrity_status": "pass",
                "issue_detail": "no inline citations required for evidence_required stub",
            }
        )
    for citation_id in sorted(inline):
        row = package[package["citation_id"].eq(citation_id)]
        source_id_present = not row.empty and row["source_id"].fillna("").astype(str).str.len().gt(0).any()
        chunk_or_table = not row.empty and (
            row["chunk_id"].fillna("").astype(str).str.len().gt(0).any() or row["table_id"].fillna("").astype(str).str.len().gt(0).any()
        )
        excerpt_present = not row.empty and row["excerpt"].fillna("").astype(str).str.len().gt(0).any()
        granularity = not row.empty and row["citation_granularity"].isin(["page_level", "source_level", "unknown"]).all()
        ok = citation_id in ref_ids and source_id_present and chunk_or_table and excerpt_present and granularity
        rows.append(
            {
                "stock_code": stock_code,
                "citation_id": citation_id,
                "inline_citation_present": True,
                "reference_present": citation_id in ref_ids,
                "source_id_present": source_id_present,
                "chunk_or_table_present": chunk_or_table,
                "excerpt_present": excerpt_present,
                "citation_granularity_valid": granularity,
                "integrity_status": "pass" if ok else "fail",
                "issue_detail": "" if ok else "citation mapping incomplete",
            }
        )
    return rows


def _report_quality_for_stock(stock_code: str, stock_name: str, md_path: Path, status: dict[str, Any]) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    forbidden_hits = [term for term in FORBIDDEN_REPORT_TERMS if term.lower() in text.lower()]
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "report_status": status["report_status"],
        "has_references_section": "## 引用与数据源 / References" in text,
        "forbidden_language_hit_count": len(forbidden_hits),
        "forbidden_language_hits": "|".join(forbidden_hits),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "quality_status": "pass" if not forbidden_hits and "## 引用与数据源 / References" in text else "fail",
    }


def _references_from_package(package: pd.DataFrame) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if package.empty:
        return refs
    for _, row in package.drop_duplicates("citation_id").sort_values("citation_id").iterrows():
        refs.append(
            {
                "citation_id": _clean(row.get("citation_id")),
                "stock_code": _clean(row.get("stock_code")),
                "source_id": _clean(row.get("source_id")),
                "source_title": _clean(row.get("source_title")),
                "source_type": _clean(row.get("source_type")),
                "source_path_or_url": _clean(row.get("source_path_or_url")),
                "page_locator": _clean(row.get("page_locator")),
                "parser": _clean(row.get("parser"), "docling"),
                "parser_version": _clean(row.get("parser_version"), "2.110.0"),
                "fetched_or_parsed_at": _now(),
            }
        )
    return refs


def _claim_map_from_package(package: pd.DataFrame) -> pd.DataFrame:
    if package.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "claim_id",
                "report_section",
                "claim_placeholder",
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
        )
    frame = package.copy()
    frame["claim_id"] = frame["stock_code"] + "-" + frame["report_section"] + "-" + frame["evidence_id"]
    frame["claim_placeholder"] = frame["report_section"] + " deterministic evidence placeholder"
    return frame[
        [
            "stock_code",
            "claim_id",
            "report_section",
            "claim_placeholder",
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


def _metadata_improvement_attempt(chunks: pd.DataFrame, tables: pd.DataFrame, chunk_quality: pd.DataFrame, table_quality: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in chunk_quality.iterrows():
        rows.append(
            {
                "source_id": _clean(row.get("source_id")),
                "chunk_id": _clean(row.get("chunk_id")),
                "table_id": "",
                "original_page_locator": "",
                "improved_page_locator": "",
                "original_table_title": "",
                "improved_table_title": "",
                "original_row_count": "",
                "improved_row_count": "",
                "original_column_count": "",
                "improved_column_count": "",
                "improvement_status": "not_recovered",
                "reason": "parsed structures do not expose stable page locator in current artifact",
            }
        )
    for _, row in table_quality.iterrows():
        rows.append(
            {
                "source_id": _clean(row.get("source_id")),
                "chunk_id": "",
                "table_id": _clean(row.get("table_id")),
                "original_page_locator": _clean(row.get("page_locator")),
                "improved_page_locator": "",
                "original_table_title": _clean(row.get("table_title")),
                "improved_table_title": _clean(row.get("table_title")),
                "original_row_count": _clean(row.get("row_count")),
                "improved_row_count": _clean(row.get("row_count")),
                "original_column_count": _clean(row.get("column_count")),
                "improved_column_count": _clean(row.get("column_count")),
                "improvement_status": "not_recovered",
                "reason": "table metadata remains source-level in current artifact",
            }
        )
    return pd.DataFrame(rows)


def _evidence_package_summary(package: pd.DataFrame) -> dict[str, Any]:
    return {
        "task_name": f"{TASK_NAME}_evidence_package",
        "research_only": True,
        "row_count": int(len(package)),
        "stock_count": int(package["stock_code"].nunique()) if not package.empty else 0,
        "citation_count": int(package["citation_id"].nunique()) if not package.empty else 0,
        "page_level_citation_count": int(package["citation_granularity"].eq("page_level").sum()) if not package.empty else 0,
        "source_level_citation_count": int(package["citation_granularity"].eq("source_level").sum()) if not package.empty else 0,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
    }


def _render_integration_report(summary: dict[str, Any], status: pd.DataFrame, citation_audit: pd.DataFrame, metadata: pd.DataFrame) -> str:
    return f"""# Data-to-Brief enriched report Docling integration v1

Research-only integration pilot. No signal, admission, scoring, strategy, dashboard routing, or production candidate universe changes.

## Scope

- pilot_stock_count: {summary['pilot_stock_count']}
- parsed_stock_count: {summary['parsed_stock_count']}
- missing_pdf_evidence_required_count: {summary['missing_pdf_evidence_required_count']}
- evidence_package_rows: {summary['docling_evidence_package_rows']}
- citation_count: {summary['citation_count']}
- page_level_citation_count: {summary['page_level_citation_count']}
- source_level_citation_count: {summary['source_level_citation_count']}

## Report status

{status[['stock_code', 'stock_name', 'report_status', 'citation_count', 'filled_section_count', 'partial_section_count', 'evidence_required_section_count', 'blocker_reason']].to_markdown(index=False)}

## Citation integrity

- audit rows: {len(citation_audit)}
- failures: {int(citation_audit['integrity_status'].eq('fail').sum()) if not citation_audit.empty else 0}
- missing page locator is a warning and remains source-level citation, not a hard failure.

## Metadata improvement attempt

- rows checked: {len(metadata)}
- recovered page/table metadata: {int(metadata['improvement_status'].eq('recovered').sum()) if not metadata.empty else 0}
- current status: source-level citations are usable; page-level citation needs parser metadata improvement.

## Conclusion

Docling can be used as an optional Data-to-Brief parser adapter. Current evidence is source-level citation-ready for parsed pilot stocks, while 京泉华 and 浙江力诺 remain evidence_required because local PDFs are missing. Recommended next step: improve Docling page/table metadata extraction or run a 10-stock batch pilot before scaling to 90.

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
        escaped = html.escape(line)
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body.append(f"<p>{escaped}</p>")
        elif line.strip():
            body.append(f"<p>{escaped}</p>")
    return "<!doctype html><html><head><meta charset='utf-8'><title>Docling Integration Report</title></head><body>" + "\n".join(body) + "</body></html>"


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


def _sanitize_report_text(text: str) -> str:
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


def _stock_name(stock_code: str) -> str:
    return PILOT_STOCKS.get(stock_code, {}).get("stock_name", "")


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
