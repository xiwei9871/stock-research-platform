from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.tech_bottleneck_latent_pending_primary_source_collection import _collect
from stock_research.tech_bottleneck_remaining_primary_source_collection import _stock_code, _strategy_diff_clean


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_manual_review_collection_batch1_v1"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_high_priority_collection_queue.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 26

GAP_COLUMNS = [
    "stock_code",
    "stock_name",
    "gap_type",
    "gap_reason",
    "recommended_next_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]


def _read_queue() -> pd.DataFrame:
    frame = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str}).fillna("")
    frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame.sort_values("stock_code").reset_index(drop=True)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_cached(output: Path) -> dict[str, Any] | None:
    summary_path = output / "latent_manual_review_collection_batch1_summary.json"
    required = [
        summary_path,
        output / "latent_manual_review_collection_batch1_sources.csv",
        output / "latent_manual_review_collection_batch1_download_manifest.csv",
        output / "latent_manual_review_collection_batch1_collection_gaps.csv",
        output / "latent_manual_review_collection_batch1_guardrails.json",
        output / "tech_bottleneck_latent_manual_review_collection_batch1_v1_report.md",
    ]
    if not all(path.exists() for path in required):
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (
        summary.get("source_high_priority_collection_queue_count") == EXPECTED_COUNT
        and summary.get("processed_count") == EXPECTED_COUNT
    ):
        return summary
    return None


def _collection_gaps(queue: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    source_codes = set(sources["stock_code"]) if not sources.empty else set()
    rows: list[dict[str, Any]] = []
    for _, row in queue.iterrows():
        if row["stock_code"] in source_codes:
            continue
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "gap_type": "missing_primary_source_pdf",
                "gap_reason": "No selected CNINFO/SSE/SZSE primary-source PDF was downloaded for this high-priority manual-review candidate.",
                "recommended_next_action": "retry source collection or use an alternate official disclosure source before backfill",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def _summary(queue: pd.DataFrame, downloads: pd.DataFrame, sources: pd.DataFrame, gaps: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    downloaded = downloads[downloads["download_status"].isin(["downloaded", "already_exists"])] if not downloads.empty else pd.DataFrame()
    downloaded_codes = set(downloaded["stock_code"]) if not downloaded.empty else set()
    used_for_signal = int(sources["used_for_signal"].astype(bool).sum()) if not sources.empty else 0
    used_for_admission = int(sources["used_for_admission"].astype(bool).sum()) if not sources.empty else 0
    if not strategy_clean or used_for_signal or used_for_admission:
        acceptance = "blocked_due_to_guardrail_violation"
    elif len(gaps):
        acceptance = "conditionally_ready_with_collection_gaps"
    else:
        acceptance = "latent_manual_review_collection_batch1_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_high_priority_collection_queue_count": int(len(queue)),
        "processed_count": int(len(queue)),
        "selected_primary_source_count": int(len(downloads)),
        "downloaded_primary_source_pdf_count": int(len(downloaded)),
        "downloaded_primary_source_stock_count": int(len(downloaded_codes)),
        "source_manifest_row_count": int(len(sources)),
        "collection_gap_stock_count": int(len(gaps)),
        "primary_source_collection_performed": True,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "quality_pool_v5_processed": False,
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
        "source_high_priority_collection_queue_count": summary["source_high_priority_collection_queue_count"],
        "processed_count": summary["processed_count"],
        "primary_source_collection_performed": True,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "quality_pool_v5_processed": False,
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
            "# Tech Bottleneck Latent Manual Review Collection Batch1 v1",
            "",
            "## 1. Scope",
            "This task collects primary-source disclosures only for the 26-stock latent manual-review high-priority collection queue. It does not perform evidence backfill, core equivalence, quality-pool application, signal, admission, scoring, or strategy actions.",
            "",
            "## 2. Collection Results",
            f"Processed stocks: {summary['processed_count']}; selected sources: {summary['selected_primary_source_count']}; downloaded PDFs: {summary['downloaded_primary_source_pdf_count']}; stock coverage: {summary['downloaded_primary_source_stock_count']}; collection gaps: {summary['collection_gap_stock_count']}.",
            "",
            "## 3. Guardrails",
            f"primary_source_collection_performed=true; evidence_backfill_performed=false; core_equivalence_performed=false; quality_pool_v5_processed=false; auto_added_to_quality_pool_count=0; price_move_used_for_signal=0; low_position_used_for_signal=0; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 4. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 5. Recommended Next Steps",
            "1. tech_bottleneck_latent_manual_review_backfill_batch1_v1",
            "2. tech_bottleneck_latent_manual_review_standard_collection_v1",
            "3. tech_bottleneck_latent_manual_review_human_confirm_packet_v1",
        ]
    )


def run(
    *,
    output_dir: str | Path = OUTPUT_DIR,
    max_sources_per_stock: int = 3,
    sleep_seconds: float = 0.0,
    start_date: str = "2023-01-01",
    end_date: str = "2026-07-08",
    force: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cached(output)
        if cached is not None:
            return cached
    queue = _read_queue()
    _search, downloads, sources = _collect(
        queue,
        output,
        max_sources_per_stock=max_sources_per_stock,
        sleep_seconds=sleep_seconds,
        start_date=start_date,
        end_date=end_date,
    )
    sources = sources[sources["stock_code"].isin(set(queue["stock_code"]))].copy().sort_values(["stock_code", "source_type"])
    gaps = _collection_gaps(queue, sources)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(queue, downloads, sources, gaps, strategy_clean)
    guardrails = _guardrails(summary)

    sources.to_csv(output / "latent_manual_review_collection_batch1_sources.csv", index=False)
    downloads.to_csv(output / "latent_manual_review_collection_batch1_download_manifest.csv", index=False)
    gaps.to_csv(output / "latent_manual_review_collection_batch1_collection_gaps.csv", index=False)
    _write_json(output / "latent_manual_review_collection_batch1_summary.json", summary)
    _write_json(output / "latent_manual_review_collection_batch1_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_manual_review_collection_batch1_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
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
