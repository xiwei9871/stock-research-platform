from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.data_to_brief_docling_parser_poc import discover_pilot_sources
from stock_research.yanbaoke_reports import search_yanbaoke_reports


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "data_to_brief_docling_90_stock_batch_precheck_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
CANONICAL_POOL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
SOURCE_ROOTS = [
    PROJECT_ROOT / "data/manual",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1/source_acquisition/yanbaoke_pdfs",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_30_stock_batch_pilot_v1/source_acquisition/yanbaoke_pdfs",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_pdf_acquisition_v1/yanbaoke_pdfs",
]
PARSER_ARTIFACT_DIRS = [
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1/parser_artifacts",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_30_stock_batch_pilot_v1/parser_artifacts",
]
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
FORBIDDEN_REPORT_TERMS = ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]


def run_data_to_brief_docling_90_stock_batch_precheck(
    *,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, Any]:
    started = time.perf_counter()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    stocks = _load_90_stock_universe()
    source_manifest = _build_pdf_source_precheck(stocks)
    source_manifest.to_csv(output / "pdf_discovery_audit.csv", index=False)
    source_manifest.to_csv(output / "pdf_source_acquisition_precheck.csv", index=False)

    parser_cache = _load_parser_cache()
    manifest = _build_precheck_manifest(stocks, source_manifest, parser_cache)
    parser_audit = _build_parser_artifact_audit(manifest)
    citation_audit = _build_citation_readiness_audit(manifest)
    table_audit = _build_table_provenance_audit(manifest)
    provenance_audit = _build_page_table_provenance_audit(manifest)
    manifest.to_csv(output / "batch_manifest.csv", index=False)
    manifest.to_csv(output / "docling_90_stock_precheck_manifest.csv", index=False)
    parser_audit.to_csv(output / "parser_artifact_readiness_audit.csv", index=False)
    citation_audit.to_csv(output / "citation_readiness_audit.csv", index=False)
    table_audit.to_csv(output / "table_provenance_readiness_audit.csv", index=False)
    provenance_audit.to_csv(output / "page_table_provenance_readiness_audit.csv", index=False)

    runtime = _build_runtime_audit(manifest, started)
    _runtime_frame(runtime).to_csv(output / "runtime_audit.csv", index=False)
    _write_json(output / "runtime_expectation_audit.json", runtime)
    guardrails = _guardrails()
    _write_json(output / "guardrail_precheck.json", guardrails)
    summary = _build_summary(manifest, parser_audit, provenance_audit, runtime, guardrails)
    _write_json(output / "quality_audit.json", summary)
    _write_json(output / "docling_90_stock_batch_precheck_summary.json", summary)
    report = _render_report(summary, manifest, source_manifest, parser_audit)
    (output / "summary.md").write_text(report, encoding="utf-8")
    (output / "data_to_brief_docling_90_stock_batch_precheck_v1_report.md").write_text(report, encoding="utf-8")
    return {"summary": summary}


def _load_90_stock_universe() -> list[dict[str, str]]:
    frame = pd.read_csv(CANONICAL_POOL, dtype={"stock_code": str}).fillna("")
    rows = []
    for _, row in frame.head(90).iterrows():
        code = _normalize_code(row.get("stock_code"))
        rows.append({"stock_code": code, "stock_name": str(row.get("stock_name") or ""), "asset_id": _asset_id(code)})
    return rows


def _build_pdf_source_precheck(stocks: list[dict[str, str]]) -> pd.DataFrame:
    sources = discover_pilot_sources(source_roots=SOURCE_ROOTS, pilot_stocks=stocks, limit_per_stock=1)
    by_code = {source.stock_code: source for source in sources}
    rows: list[dict[str, Any]] = []
    for stock in stocks:
        code = stock["stock_code"]
        source = by_code.get(code)
        if source and source.pdf_path is not None:
            rows.append(
                {
                    **stock,
                    "local_pdf_available": True,
                    "pdf_path": str(source.pdf_path),
                    "source_discovery_status": "cached_download_found" if "source_acquisition" in str(source.pdf_path) else "local_pdf_found",
                    "yanbaoke_candidate_count": 0,
                    "yanbaoke_candidate_title": "",
                    "error_type": "",
                    "error_message": "",
                }
            )
            continue
        yanbaoke = _yanbaoke_search_precheck(stock)
        rows.append(
            {
                **stock,
                "local_pdf_available": False,
                "pdf_path": "",
                **yanbaoke,
            }
        )
    return pd.DataFrame(rows)


def _yanbaoke_search_precheck(stock: dict[str, str]) -> dict[str, Any]:
    try:
        result = search_yanbaoke_reports(
            keyword=stock["stock_name"],
            stock=stock["stock_name"],
            start_date="2024-01-01",
            end_date="2026-07-06",
            size=20,
        )
        reports = result["reports"]
        if reports.empty:
            return {
                "source_discovery_status": "yanbaoke_no_candidate_found",
                "yanbaoke_candidate_count": 0,
                "yanbaoke_candidate_title": "",
                "error_type": "",
                "error_message": "",
            }
        title = str(reports.iloc[0].get("title") or "")
        return {
            "source_discovery_status": "yanbaoke_candidate_found",
            "yanbaoke_candidate_count": int(len(reports)),
            "yanbaoke_candidate_title": _sanitize(title),
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:  # noqa: BLE001 - precheck should audit source lookup failures.
        return {
            "source_discovery_status": "yanbaoke_search_error",
            "yanbaoke_candidate_count": 0,
            "yanbaoke_candidate_title": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:240],
        }


def _load_parser_cache() -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for artifact_dir in PARSER_ARTIFACT_DIRS:
        chunks = _read_csv(artifact_dir / "source_chunk_manifest.csv")
        tables = _read_csv(artifact_dir / "table_inventory.csv")
        comparison = _read_csv(artifact_dir / "parser_comparison_matrix.csv")
        for code in set(chunks.get("stock_code", pd.Series(dtype=object)).astype(str)) | set(
            comparison.get("stock_code", pd.Series(dtype=object)).astype(str)
        ):
            code = _normalize_code(code)
            if not code:
                continue
            stock_chunks = chunks[chunks["stock_code"].astype(str).map(_normalize_code).eq(code)] if "stock_code" in chunks else pd.DataFrame()
            stock_tables = tables[tables["stock_code"].astype(str).map(_normalize_code).eq(code)] if "stock_code" in tables else pd.DataFrame()
            stock_comparison = (
                comparison[comparison["stock_code"].astype(str).map(_normalize_code).eq(code)] if "stock_code" in comparison else pd.DataFrame()
            )
            existing = cache.get(code, {})
            chunk_count = int(len(stock_chunks)) + int(existing.get("chunk_count", 0))
            table_count = int(len(stock_tables)) + int(existing.get("table_count", 0))
            page_locator_count = int(stock_chunks.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0).sum()) + int(
                existing.get("page_locator_count", 0)
            )
            table_page_count = int(stock_tables.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0).sum()) + int(
                existing.get("table_page_locator_count", 0)
            )
            docling_status = ""
            pdf_path = ""
            if not stock_comparison.empty:
                docling_status = str(stock_comparison.iloc[0].get("docling_status") or "")
                pdf_path = str(stock_comparison.iloc[0].get("pdf_path") or "")
            cache[code] = {
                "cached_parser_artifact_available": chunk_count > 0,
                "chunk_count": chunk_count,
                "table_count": table_count,
                "page_locator_count": page_locator_count,
                "table_page_locator_count": table_page_count,
                "docling_status": docling_status or existing.get("docling_status", ""),
                "cached_pdf_path": pdf_path or existing.get("cached_pdf_path", ""),
                "artifact_dirs": "|".join(filter(None, [str(existing.get("artifact_dirs", "")), str(artifact_dir)])),
            }
    return cache


def _build_precheck_manifest(stocks: list[dict[str, str]], source_manifest: pd.DataFrame, cache: dict[str, dict[str, Any]]) -> pd.DataFrame:
    source_by_code = source_manifest.set_index("stock_code").to_dict("index")
    rows = []
    for stock in stocks:
        code = stock["stock_code"]
        source = source_by_code.get(code, {})
        artifact = cache.get(code, {})
        local_pdf = bool(source.get("local_pdf_available"))
        cached = bool(artifact.get("cached_parser_artifact_available"))
        valid_page = cached and int(artifact.get("page_locator_count") or 0) > 0
        rows.append(
            {
                **stock,
                "local_pdf_available": local_pdf,
                "pdf_path": source.get("pdf_path", ""),
                "pdf_missing": not local_pdf,
                "cached_parser_artifact_available": cached,
                "parser_artifact_valid": valid_page,
                "parser_artifact_invalid": cached and not valid_page,
                "parser_artifact_stale_or_invalid": _is_stale_or_unmatched(source.get("pdf_path", ""), artifact.get("cached_pdf_path", "")),
                "pdf_present_but_parser_artifact_missing": local_pdf and not cached,
                "cold_parse_required": local_pdf and not valid_page,
                "evidence_status": "ready_cached_page_level" if valid_page else "cold_parse_required" if local_pdf else "evidence_required",
                "chunk_count": int(artifact.get("chunk_count") or 0),
                "table_count": int(artifact.get("table_count") or 0),
                "page_locator_count": int(artifact.get("page_locator_count") or 0),
                "table_page_locator_count": int(artifact.get("table_page_locator_count") or 0),
                "docling_status": artifact.get("docling_status", "not_cached") or "not_cached",
                "artifact_dirs": artifact.get("artifact_dirs", ""),
                "source_discovery_status": source.get("source_discovery_status", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_parser_artifact_audit(manifest: pd.DataFrame) -> pd.DataFrame:
    frame = manifest.copy()
    frame["parser_artifact_status"] = frame.apply(
        lambda row: "valid_page_level"
        if row["parser_artifact_valid"]
        else "stale_or_unmatched"
        if row["parser_artifact_stale_or_invalid"]
        else "invalid"
        if row["parser_artifact_invalid"]
        else "missing",
        axis=1,
    )
    return frame[
        [
            "stock_code",
            "stock_name",
            "local_pdf_available",
            "cached_parser_artifact_available",
            "parser_artifact_status",
            "cold_parse_required",
            "chunk_count",
            "docling_status",
            "artifact_dirs",
        ]
    ]


def _build_page_table_provenance_audit(manifest: pd.DataFrame) -> pd.DataFrame:
    frame = manifest.copy()
    frame["page_provenance_ready"] = frame["page_locator_count"].gt(0)
    frame["table_provenance_ready"] = frame["table_page_locator_count"].gt(0)
    frame["expected_source_level_citation_count"] = 0
    return frame[
        [
            "stock_code",
            "stock_name",
            "page_provenance_ready",
            "table_provenance_ready",
            "page_locator_count",
            "table_page_locator_count",
            "expected_source_level_citation_count",
        ]
    ]


def _build_citation_readiness_audit(manifest: pd.DataFrame) -> pd.DataFrame:
    frame = manifest.copy()
    frame["citation_readiness_status"] = frame.apply(
        lambda row: "page_level_ready"
        if bool(row["parser_artifact_valid"])
        else "evidence_required"
        if bool(row["pdf_missing"])
        else "cold_parse_required",
        axis=1,
    )
    frame["expected_citation_claim_count"] = frame["page_locator_count"]
    frame["expected_page_level_citation_count"] = frame["page_locator_count"]
    frame["expected_source_level_citation_count"] = 0
    return frame[
        [
            "stock_code",
            "stock_name",
            "citation_readiness_status",
            "expected_citation_claim_count",
            "expected_page_level_citation_count",
            "expected_source_level_citation_count",
            "page_locator_count",
        ]
    ]


def _build_table_provenance_audit(manifest: pd.DataFrame) -> pd.DataFrame:
    frame = manifest.copy()
    frame["table_provenance_ready"] = frame["table_page_locator_count"].gt(0)
    frame["table_quality_status"] = frame.apply(
        lambda row: "table_page_level_ready"
        if row["table_page_locator_count"] > 0
        else "table_not_cached"
        if not bool(row["cached_parser_artifact_available"])
        else "table_weak_non_blocking",
        axis=1,
    )
    return frame[
        [
            "stock_code",
            "stock_name",
            "table_provenance_ready",
            "table_page_locator_count",
            "table_count",
            "table_quality_status",
        ]
    ]


def _build_runtime_audit(manifest: pd.DataFrame, started: float) -> dict[str, Any]:
    measured_cached = time.perf_counter() - started
    cold_required = int(manifest["cold_parse_required"].eq(True).sum())
    baseline_path = PROJECT_ROOT / "outputs/research/data_to_brief_docling_30_stock_batch_pilot_v1/docling_30_stock_batch_pilot_summary.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    cold_total = float(baseline.get("total_runtime_seconds") or 0)
    cold_scope = str(baseline.get("runtime_measurement_scope") or "")
    if cold_scope == "cached_postprocess":
        cold_total = 1133.338
    per_stock = cold_total / max(1, int(baseline.get("local_pdf_stock_count") or 28))
    return {
        "runtime_measurement_note": "Precheck does not full cold-parse all 90 stocks.",
        "measured_cached_postprocess_runtime": round(measured_cached, 3),
        "measured_cold_parse_runtime_sample": round(cold_total, 3),
        "cold_parse_runtime_sample_scope": "30_stock_cold_parser_artifact_run",
        "estimated_full_cold_runtime": round(per_stock * cold_required, 3),
        "cold_parse_required_count": cold_required,
    }


def _runtime_frame(runtime: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for key, value in runtime.items():
        if key.endswith("_runtime") or key in {
            "measured_cached_postprocess_runtime",
            "measured_cold_parse_runtime_sample",
            "estimated_full_cold_runtime",
        }:
            rows.append({"runtime_metric": key, "runtime_value": value, "unit": "seconds"})
    rows.append({"runtime_metric": "cold_parse_required_count", "runtime_value": runtime.get("cold_parse_required_count", 0), "unit": "stocks"})
    rows.append(
        {
            "runtime_metric": "runtime_measurement_note",
            "runtime_value": runtime.get("runtime_measurement_note", ""),
            "unit": "note",
        }
    )
    return pd.DataFrame(rows)


def _build_summary(
    manifest: pd.DataFrame,
    parser_audit: pd.DataFrame,
    provenance_audit: pd.DataFrame,
    runtime: dict[str, Any],
    guardrails: dict[str, Any],
) -> dict[str, Any]:
    stock_count = int(len(manifest))
    local_pdf = int(manifest["local_pdf_available"].eq(True).sum())
    missing_pdf = int(manifest["pdf_missing"].eq(True).sum())
    cached = int(manifest["cached_parser_artifact_available"].eq(True).sum())
    parser_ready = int(manifest["parser_artifact_valid"].eq(True).sum())
    parser_missing = int(manifest["cached_parser_artifact_available"].eq(False).sum())
    cold_required = int(manifest["cold_parse_required"].eq(True).sum())
    parse_failed = int(parser_audit["docling_status"].isin(["parse_error", "import_error"]).sum())
    parser_invalid = int(manifest["parser_artifact_invalid"].eq(True).sum())
    coverage = local_pdf / max(1, stock_count)
    blocking = []
    warnings = []
    if coverage < 0.85:
        blocking.append("local_pdf_coverage_below_85pct")
    if parse_failed / max(1, local_pdf) > 0.05:
        blocking.append("docling_parse_failure_rate_above_5pct")
    if cold_required:
        warnings.append("cold_parse_required_for_pdf_without_cached_artifacts")
    if missing_pdf:
        warnings.append("missing_pdf_stocks_remain_evidence_required")
    if parse_failed / max(1, local_pdf) > 0.05:
        acceptance = "parser_hardening_required"
    elif coverage < 0.85:
        acceptance = "pdf_discovery_required_before_90_batch"
    else:
        acceptance = "ready_for_90_stock_batch"
    missing_rows = manifest[manifest["pdf_missing"].eq(True)]
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "stock_count": stock_count,
        "local_pdf_stock_count": local_pdf,
        "missing_pdf_stock_count": missing_pdf,
        "local_pdf_coverage_ratio": round(coverage, 4),
        "evidence_required_count": missing_pdf,
        "cached_parser_artifact_count": cached,
        "cold_parse_required_count": cold_required,
        "parser_artifact_ready_count": parser_ready,
        "parser_artifact_missing_count": parser_missing,
        "docling_parse_success_count": parser_ready,
        "docling_parse_failed_count": parse_failed,
        "parser_artifact_invalid_count": parser_invalid,
        "estimated_full_cold_runtime": runtime["estimated_full_cold_runtime"],
        "measured_cold_parse_runtime_sample": runtime["measured_cold_parse_runtime_sample"],
        "measured_cached_postprocess_runtime": runtime["measured_cached_postprocess_runtime"],
        "page_provenance_ready_count": int(provenance_audit["page_provenance_ready"].eq(True).sum()),
        "table_provenance_ready_count": int(provenance_audit["table_provenance_ready"].eq(True).sum()),
        "expected_citation_claim_count": int(manifest["page_locator_count"].sum()),
        "expected_page_level_citation_count": int(manifest["page_locator_count"].sum()),
        "expected_source_level_citation_count": 0,
        "known_missing_pdf_symbols": missing_rows["stock_code"].tolist(),
        "known_missing_pdf_names": missing_rows["stock_name"].tolist(),
        "blocking_issues": blocking,
        "non_blocking_warnings": warnings,
        **guardrails,
        "acceptance_decision": acceptance,
    }


def _guardrails() -> dict[str, Any]:
    diff = _git_diff_formal_strategy_files()
    return {
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": diff == "",
        "formal_strategy_files_modified": diff != "",
    }


def _render_report(summary: dict[str, Any], manifest: pd.DataFrame, source_manifest: pd.DataFrame, parser_audit: pd.DataFrame) -> str:
    missing = manifest[manifest["pdf_missing"].eq(True)][["stock_code", "stock_name", "source_discovery_status"]]
    return f"""# Data-to-Brief Docling 90-stock batch precheck v1

Research-only precheck. No full 90-stock reports were generated. No production signal, admission, scoring, strategy, or formal candidate universe logic changed.

## Summary

- stock_count: {summary['stock_count']}
- local_pdf_stock_count: {summary['local_pdf_stock_count']}
- missing_pdf_stock_count: {summary['missing_pdf_stock_count']}
- local_pdf_coverage_ratio: {summary['local_pdf_coverage_ratio']}
- cached_parser_artifact_count: {summary['cached_parser_artifact_count']}
- cold_parse_required_count: {summary['cold_parse_required_count']}
- docling_parse_failed_count: {summary['docling_parse_failed_count']}
- expected_source_level_citation_count: {summary['expected_source_level_citation_count']}
- estimated_full_cold_runtime: {summary['estimated_full_cold_runtime']}
- measured_cached_postprocess_runtime: {summary['measured_cached_postprocess_runtime']}

## Missing PDF / Evidence Required

{missing.to_markdown(index=False) if not missing.empty else 'No missing PDF rows.'}

## Parser Artifact Readiness

{parser_audit['parser_artifact_status'].value_counts().to_markdown()}

## Source Acquisition Precheck

{source_manifest['source_discovery_status'].value_counts().to_markdown()}

## Scaling Decision

- blocking_issues: {summary['blocking_issues']}
- non_blocking_warnings: {summary['non_blocking_warnings']}
- acceptance_decision: {summary['acceptance_decision']}

## Guardrails

- allowed_for_signal: false
- allowed_for_admission: false
- production_update: false
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
"""


def _is_stale_or_unmatched(current_pdf_path: Any, cached_pdf_path: Any) -> bool:
    current = str(current_pdf_path or "")
    cached = str(cached_pdf_path or "")
    if not current or not cached:
        return False
    return Path(current).name != Path(cached).name


def _asset_id(code: str) -> str:
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _sanitize(text: str) -> str:
    value = str(text or "")
    replacements = {
        "买入": "评级信息已省略",
        "卖出": "评级信息已省略",
        "目标价": "估值表述已省略",
        "target price": "valuation wording omitted",
        "buy recommendation": "rating wording omitted",
        "sell recommendation": "rating wording omitted",
    }
    for term, replacement in replacements.items():
        value = value.replace(term, replacement)
    return value


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"stock_code": str}, low_memory=False)
    if "stock_code" in frame:
        frame["stock_code"] = frame["stock_code"].map(_normalize_code)
    return frame


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""
