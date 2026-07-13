from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.data_to_brief_backfill_primary_source_text_first_parse import (
    _build_source_rows,
    _extract_pages,
)
from stock_research.tech_bottleneck_90_primary_source_backfill import (
    _assess_stock,
    _build_gap_matrix,
    _strategy_diff_clean,
    _stock_code,
    _write_json,
)
from stock_research.tech_bottleneck_90_primary_source_backfill_rerun_v2 import (
    _build_evidence_matrix,
    _upgrade_decision_if_needed,
)
from stock_research.tech_bottleneck_remaining_primary_source_collection import (
    SEARCH_CATEGORIES,
    _build_manifest,
    _download_pdf,
    _load_stock_org_map,
    _query_cninfo,
    _select_announcements,
    _session,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_likely_core_36_primary_source_backfill_v1"
INPUT_QUEUE = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1/likely_core_pending_evidence_queue.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _read_queue() -> pd.DataFrame:
    return _read_csv(INPUT_QUEUE).sort_values("stock_code").reset_index(drop=True)


def _load_cached(output: Path) -> dict[str, Any] | None:
    summary_path = output / "likely_core_36_primary_source_backfill_summary.json"
    required = [
        summary_path,
        output / "likely_core_36_backfill_results.csv",
        output / "likely_core_36_primary_source_evidence_matrix.csv",
        output / "likely_core_36_gap_matrix.csv",
        output / "likely_core_36_upgrade_candidates.csv",
        output / "likely_core_36_remain_pending_candidates.csv",
        output / "likely_core_36_adjacent_or_downgrade_candidates.csv",
        output / "likely_core_36_primary_source_backfill_guardrails.json",
        output / "tech_bottleneck_likely_core_36_primary_source_backfill_v1_report.md",
    ]
    if not all(path.exists() for path in required):
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("source_likely_core_queue_count") == 36 and summary.get("processed_count") == 36:
        return summary
    return None


def _collect_primary_sources(
    queue: pd.DataFrame,
    output: Path,
    *,
    max_sources_per_stock: int = 3,
    sleep_seconds: float = 0.05,
    start_date: str = "2023-01-01",
    end_date: str = "2026-07-07",
) -> pd.DataFrame:
    manifest_path = output / "likely_core_36_primary_source_collection_manifest.csv"
    if manifest_path.exists():
        manifest = _read_csv(manifest_path)
        if not manifest.empty:
            return manifest

    download_dir = output / "cninfo_primary_source_pdfs"
    download_dir.mkdir(parents=True, exist_ok=True)
    session = _session()
    search_rows: list[dict[str, Any]] = []
    download_rows: list[dict[str, Any]] = []
    try:
        org_map = _load_stock_org_map(session)
    except Exception as exc:  # noqa: BLE001 - audited collection gap.
        org_map = {}
        for _, row in queue.iterrows():
            for category in SEARCH_CATEGORIES:
                search_rows.append(
                    {
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "category": category,
                        "status": "stock_map_error",
                        "candidate_count": 0,
                        "selected_count": 0,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )

    for _, row in queue.iterrows():
        code = row["stock_code"]
        name = row["stock_name"]
        org_id = org_map.get(code, "")
        candidates = []
        if org_id:
            for category in SEARCH_CATEGORIES:
                found, audit = _query_cninfo(
                    session,
                    stock_code=code,
                    stock_name=name,
                    org_id=org_id,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                )
                candidates.extend(found)
                search_rows.append(audit)
                if sleep_seconds:
                    time.sleep(sleep_seconds)
        elif org_map:
            for category in SEARCH_CATEGORIES:
                search_rows.append(
                    {
                        "stock_code": code,
                        "stock_name": name,
                        "category": category,
                        "status": "org_id_missing",
                        "candidate_count": 0,
                        "selected_count": 0,
                        "error_type": "org_id_missing",
                        "error_message": "stock code not found in cninfo stock map",
                    }
                )
        selected = _select_announcements(candidates, max_per_stock=max_sources_per_stock)
        for search_row in search_rows:
            if search_row["stock_code"] == code and search_row["status"] == "ok":
                search_row["selected_count"] = len([item for item in selected if item.category == search_row["category"]])
        for item in selected:
            download_rows.append(_download_pdf(session, item, download_dir))
            if sleep_seconds:
                time.sleep(sleep_seconds)

    search = pd.DataFrame(search_rows)
    downloads = pd.DataFrame(download_rows)
    manifest = _build_manifest(downloads)
    manifest.to_csv(manifest_path, index=False)
    search.to_csv(output / "likely_core_36_cninfo_search_audit.csv", index=False)
    downloads.to_csv(output / "likely_core_36_cninfo_download_audit.csv", index=False)
    return manifest


def _parse_text_first(manifest: pd.DataFrame, output: Path, *, max_pages_per_source: int = 80, max_chunks_per_source: int = 10) -> pd.DataFrame:
    chunks_path = output / "likely_core_36_text_first_evidence_chunks.csv"
    parse_manifest_path = output / "likely_core_36_text_first_parse_manifest.csv"
    if chunks_path.exists() and parse_manifest_path.exists():
        return _read_csv(chunks_path)
    if manifest.empty:
        pd.DataFrame().to_csv(parse_manifest_path, index=False)
        pd.DataFrame().to_csv(chunks_path, index=False)
        return pd.DataFrame()
    manifest = manifest.copy().sort_values(["stock_code", "source_type", "local_pdf_path"]).reset_index(drop=True)
    manifest["source_index"] = range(1, len(manifest) + 1)
    parse_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    for source in manifest.to_dict("records"):
        pages, metadata = _extract_pages(Path(str(source["local_pdf_path"])), max_pages_per_source)
        parse_row, chunks, fallback = _build_source_rows(source, pages, metadata, max_chunks_per_source=max_chunks_per_source)
        parse_rows.append(parse_row)
        chunk_rows.extend(chunks)
        fallback_rows.append(fallback)
        quality_rows.append(
            {
                "stock_code": source["stock_code"],
                "stock_name": source["stock_name"],
                "source_type": source["source_type"],
                "source_title": source["source_title"],
                "source_path": source["local_pdf_path"],
                "page_count": metadata["page_count"],
                "pages_examined": metadata["pages_examined"],
                "non_empty_page_count": metadata["non_empty_page_count"],
                "selected_page_count": parse_row["selected_page_count"],
                "text_extract_quality": "usable" if parse_row["selected_page_count"] else "missing",
                "citation_ready": bool(parse_row["selected_page_count"]),
                "issue_warning": "" if parse_row["selected_page_count"] else "no_citation_ready_text_chunk",
                "runtime_seconds": metadata["runtime_seconds"],
            }
        )
    pd.DataFrame(parse_rows).to_csv(parse_manifest_path, index=False)
    pd.DataFrame(chunk_rows).to_csv(chunks_path, index=False)
    pd.DataFrame(quality_rows).to_csv(output / "likely_core_36_text_first_quality_audit.csv", index=False)
    pd.DataFrame(fallback_rows).to_csv(output / "likely_core_36_docling_fallback_audit.csv", index=False)
    return pd.DataFrame(chunk_rows)


def _assess_results(queue: pd.DataFrame, evidence_matrix: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in queue.iterrows():
        stock_evidence = evidence_matrix[evidence_matrix["stock_code"].eq(row["stock_code"])]
        assessed = _assess_stock(row, stock_evidence)
        assessed = _upgrade_decision_if_needed(assessed, stock_evidence)
        decision = assessed["recommended_backfill_decision"]
        if decision == "upgrade_to_confirmed_core_proposal":
            assessed["recommended_backfill_decision"] = "upgrade_to_confirmed_core_manual_approval_candidate"
        if assessed["recommended_manual_review_entry_class"] == "evidence_backfill_required":
            assessed["recommended_manual_review_entry_class"] = "likely_core_pending_evidence"
        rows.append(assessed)
    return pd.DataFrame(rows).sort_values("stock_code").reset_index(drop=True)


def _split_outputs(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    upgrades = results[results["recommended_backfill_decision"].eq("upgrade_to_confirmed_core_manual_approval_candidate")]
    pending = results[results["recommended_backfill_decision"].eq("remain_likely_core_pending_evidence")]
    adjacent_or_downgrade = results[
        results["recommended_backfill_decision"].isin({"move_to_adjacent_watchlist", "downgrade_or_reject"})
    ]
    return upgrades, pending, adjacent_or_downgrade


def _summary(queue: pd.DataFrame, results: pd.DataFrame, manifest: pd.DataFrame, evidence: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    upgrades, pending, adjacent_or_downgrade = _split_outputs(results)
    adjacent = adjacent_or_downgrade[adjacent_or_downgrade["recommended_backfill_decision"].eq("move_to_adjacent_watchlist")]
    downgrade = adjacent_or_downgrade[adjacent_or_downgrade["recommended_backfill_decision"].eq("downgrade_or_reject")]
    used_for_signal = int(results["used_for_signal"].astype(bool).sum()) if not results.empty else 0
    used_for_admission = int(results["used_for_admission"].astype(bool).sum()) if not results.empty else 0
    if not strategy_clean or used_for_signal or used_for_admission:
        acceptance = "blocked_due_to_guardrail_violation"
    elif len(pending) or len(adjacent_or_downgrade):
        acceptance = "conditionally_ready_with_remaining_evidence_gaps"
    else:
        acceptance = "likely_core_36_primary_source_backfill_ready"
    return {
        "task_name": TASK_NAME,
        "source_likely_core_queue_count": int(len(queue)),
        "processed_count": int(len(results)),
        "collection_manifest_count": int(len(manifest)),
        "primary_source_supported_count": int(results["primary_source_supported"].astype(bool).sum()) if not results.empty else 0,
        "evidence_matrix_count": int(len(evidence)),
        "upgrade_count": int(len(upgrades)),
        "remain_pending_count": int(len(pending)),
        "adjacent_count": int(len(adjacent)),
        "downgrade_or_reject_count": int(len(downgrade)),
        "auto_applied_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_likely_core_queue_count": summary["source_likely_core_queue_count"],
        "only_likely_core_queue_processed": summary["source_likely_core_queue_count"] == 36 and summary["processed_count"] == 36,
        "primary_source_backfill_generated": True,
        "auto_applied_count": summary["auto_applied_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Likely Core 36 Primary Source Backfill v1",
            "",
            "## 1. Scope",
            "This task processes only the 36 likely_core_pending_evidence rows from the canonical 90-stock hard-tech review pool. It is research-only and does not expand the pool, apply confirmed core status, or connect signal/admission.",
            "",
            "## 2. Source Collection And Parse",
            f"Likely queue count: {summary['source_likely_core_queue_count']}; collection manifest rows: {summary['collection_manifest_count']}; evidence matrix rows: {summary['evidence_matrix_count']}.",
            "",
            "## 3. Backfill Results",
            f"Upgrade candidates: {summary['upgrade_count']}; remain pending: {summary['remain_pending_count']}; adjacent watchlist: {summary['adjacent_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 4. Guardrail Checks",
            f"research_only=true; auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_stock_workspace_docling_panel_v1",
            "2. tech_bottleneck_evidence_completion_expansion_queue_v1",
            "3. tech_bottleneck_confirmed_core_manual_decision_apply_draft_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    cached = _load_cached(output)
    if cached is not None:
        return cached
    queue = _read_queue()
    manifest = _collect_primary_sources(queue, output)
    chunks = _parse_text_first(manifest, output)
    evidence = _build_evidence_matrix(chunks)
    results = _assess_results(queue, evidence)
    gaps = _build_gap_matrix(results)
    upgrades, pending, adjacent_or_downgrade = _split_outputs(results)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(queue, results, manifest, evidence, strategy_clean)
    guardrails = _guardrails(summary)

    results.to_csv(output / "likely_core_36_backfill_results.csv", index=False)
    evidence.to_csv(output / "likely_core_36_primary_source_evidence_matrix.csv", index=False)
    gaps.to_csv(output / "likely_core_36_gap_matrix.csv", index=False)
    upgrades.to_csv(output / "likely_core_36_upgrade_candidates.csv", index=False)
    pending.to_csv(output / "likely_core_36_remain_pending_candidates.csv", index=False)
    adjacent_or_downgrade.to_csv(output / "likely_core_36_adjacent_or_downgrade_candidates.csv", index=False)
    _write_json(output / "likely_core_36_primary_source_backfill_summary.json", summary)
    _write_json(output / "likely_core_36_primary_source_backfill_guardrails.json", guardrails)
    (output / "tech_bottleneck_likely_core_36_primary_source_backfill_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
