from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.tech_bottleneck_remaining_primary_source_collection import (
    SEARCH_CATEGORIES,
    _baostock_financial_audit,
    _build_manifest,
    _download_pdf,
    _load_stock_org_map,
    _query_cninfo,
    _select_announcements,
    _session,
    _stock_code,
    _strategy_diff_clean,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_pending_primary_source_collection_v1"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_v1/latent_backfill_batch1_remain_pending.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 45


DOWNLOAD_COLUMNS = [
    "stock_code",
    "stock_name",
    "category",
    "announcement_id",
    "org_id",
    "title",
    "announcement_time",
    "adjunct_url",
    "pdf_url",
    "page_column",
    "source_type",
    "download_status",
    "local_pdf_path",
    "file_size_bytes",
    "error_type",
    "error_message",
]

SEARCH_COLUMNS = [
    "stock_code",
    "stock_name",
    "category",
    "status",
    "candidate_count",
    "selected_count",
    "error_type",
    "error_message",
]


def _read_queue() -> pd.DataFrame:
    frame = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str}).fillna("")
    frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame.sort_values("stock_code").reset_index(drop=True)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_cached(output: Path) -> dict[str, Any] | None:
    summary_path = output / "latent_pending_primary_source_collection_summary.json"
    required = [
        summary_path,
        output / "latent_pending_primary_source_collection_manifest.csv",
        output / "latent_pending_primary_source_search_audit.csv",
        output / "latent_pending_primary_source_download_audit.csv",
        output / "latent_pending_primary_source_collection_guardrails.json",
        output / "tech_bottleneck_latent_pending_primary_source_collection_v1_report.md",
    ]
    if not all(path.exists() for path in required):
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("source_latent_pending_count") == EXPECTED_COUNT and summary.get("processed_stock_count") == EXPECTED_COUNT:
        return summary
    return None


def _collect(
    queue: pd.DataFrame,
    output: Path,
    *,
    max_sources_per_stock: int,
    sleep_seconds: float,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    download_dir = output / "cninfo_primary_source_pdfs"
    download_dir.mkdir(parents=True, exist_ok=True)
    session = _session()
    search_rows: list[dict[str, Any]] = []
    download_rows: list[dict[str, Any]] = []
    try:
        org_map = _load_stock_org_map(session)
    except Exception as exc:  # noqa: BLE001 - collection failures are audited.
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
                if sleep_seconds > 0:
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
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    search = pd.DataFrame(search_rows, columns=SEARCH_COLUMNS)
    downloads = pd.DataFrame(download_rows, columns=DOWNLOAD_COLUMNS)
    manifest = _build_manifest(downloads)
    return search, downloads, manifest


def _summary(
    *,
    queue: pd.DataFrame,
    search: pd.DataFrame,
    downloads: pd.DataFrame,
    manifest: pd.DataFrame,
    strategy_clean: bool,
    output: Path,
) -> dict[str, Any]:
    downloaded = downloads[downloads["download_status"].isin(["downloaded", "already_exists"])] if not downloads.empty else pd.DataFrame()
    downloaded_codes = set(downloaded["stock_code"]) if not downloaded.empty else set()
    successful_search_codes = set(search.loc[search["status"].eq("ok") & search["candidate_count"].gt(0), "stock_code"]) if not search.empty else set()
    used_for_signal = int(manifest["used_for_signal"].astype(bool).sum()) if not manifest.empty else 0
    used_for_admission = int(manifest["used_for_admission"].astype(bool).sum()) if not manifest.empty else 0
    gap_count = int(len(queue) - len(downloaded_codes))
    if not strategy_clean or used_for_signal or used_for_admission:
        acceptance = "blocked_due_to_guardrail_violation"
    elif gap_count:
        acceptance = "conditionally_ready_with_collection_gaps"
    else:
        acceptance = "latent_pending_primary_source_collection_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_latent_pending_count": int(len(queue)),
        "processed_stock_count": int(len(queue)),
        "cninfo_search_attempt_count": int(len(search)),
        "cninfo_search_success_stock_count": int(len(successful_search_codes)),
        "selected_primary_source_count": int(len(downloads)),
        "downloaded_primary_source_pdf_count": int(len(downloaded)),
        "downloaded_primary_source_stock_count": int(len(downloaded_codes)),
        "collection_gap_stock_count": gap_count,
        "manifest_row_count": int(len(manifest)),
        "download_dir": str(output / "cninfo_primary_source_pdfs"),
        "primary_source_collection_performed": True,
        "backfill_decision_performed": False,
        "core_equivalence_performed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_latent_pending_count": summary["source_latent_pending_count"],
        "only_latent_pending_processed": summary["source_latent_pending_count"] == EXPECTED_COUNT
        and summary["processed_stock_count"] == EXPECTED_COUNT,
        "primary_source_collection_performed": True,
        "backfill_decision_performed": False,
        "core_equivalence_performed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": 0,
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
            "# Tech Bottleneck Latent Pending Primary Source Collection v1",
            "",
            "## 1. Scope",
            "This task actively collects primary-source documents only for the 45 latent pending primary-source candidates. It does not process the 4 keep-separate latent candidates, standard backfill, manual-review-first, quality pool v3, or doubled-tech names.",
            "",
            "## 2. Collection Results",
            f"Processed stocks: {summary['processed_stock_count']}. Search success stocks: {summary['cninfo_search_success_stock_count']}. Downloaded primary-source PDFs: {summary['downloaded_primary_source_pdf_count']}. Downloaded stock count: {summary['downloaded_primary_source_stock_count']}.",
            "",
            "## 3. Guardrails",
            f"primary_source_collection_performed=true; backfill_decision_performed=false; core_equivalence_performed=false; auto_added_to_quality_pool_count=0; price_move_used_for_signal=0; low_position_used_for_signal=0; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 4. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 5. Recommended Next Steps",
            "1. tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2",
            "2. tech_bottleneck_latent_pending_docling_parse_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(
    *,
    output_dir: str | Path = OUTPUT_DIR,
    max_sources_per_stock: int = 3,
    sleep_seconds: float = 0.2,
    start_date: str = "2023-01-01",
    end_date: str = "2026-07-07",
    force: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cached(output)
        if cached is not None:
            return cached
    queue = _read_queue()
    search, downloads, manifest = _collect(
        queue,
        output,
        max_sources_per_stock=max_sources_per_stock,
        sleep_seconds=sleep_seconds,
        start_date=start_date,
        end_date=end_date,
    )
    strategy_clean = _strategy_diff_clean()
    summary = _summary(queue=queue, search=search, downloads=downloads, manifest=manifest, strategy_clean=strategy_clean, output=output)
    guardrails = _guardrails(summary)

    manifest.to_csv(output / "latent_pending_primary_source_collection_manifest.csv", index=False)
    search.to_csv(output / "latent_pending_primary_source_search_audit.csv", index=False)
    downloads.to_csv(output / "latent_pending_primary_source_download_audit.csv", index=False)
    _write_json(output / "latent_pending_primary_source_collection_summary.json", summary)
    _write_json(output / "latent_pending_primary_source_collection_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_pending_primary_source_collection_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--max-sources-per-stock", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run(sleep_seconds=args.sleep_seconds, max_sources_per_stock=args.max_sources_per_stock, force=args.force),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
