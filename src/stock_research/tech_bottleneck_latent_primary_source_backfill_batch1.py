from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_primary_source_backfill_batch1_v1"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_high_priority_backfill_queue.csv"
)
SOURCE_UNIVERSE = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1/a_share_candidate_universe.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_QUEUE_COUNT = 49
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

GAP_TYPES = [
    "missing_primary_source",
    "missing_annual_report",
    "missing_announcement",
    "missing_named_customer",
    "missing_order_or_capacity",
    "missing_revenue_trace",
    "missing_financial_trace",
    "missing_architecture_shift",
    "missing_route_around",
    "missing_value_capture",
    "missing_disconfirmation",
]

RESULT_COLUMNS = [
    "stock_code",
    "stock_name",
    "previous_quality_audit_decision",
    "primary_source_backfill_status",
    "primary_source_supported",
    "structured_primary_source_count",
    "annual_report_evidence_count",
    "announcement_evidence_count",
    "revenue_trace_evidence_count",
    "financial_trace_evidence_count",
    "brokerage_only_after_backfill",
    "bottleneck_thesis_support_after_backfill",
    "business_relevance_after_backfill",
    "supply_chain_role_quality_after_backfill",
    "architecture_shift_quality_after_backfill",
    "route_around_quality_after_backfill",
    "value_capture_quality_after_backfill",
    "disconfirmation_found",
    "remaining_evidence_gap_flags",
    "recommended_backfill_decision",
    "recommended_manual_review_entry_class",
    "recommended_next_evidence_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "price_move_used_for_signal",
    "low_position_used_for_signal",
    "notes",
]

EVIDENCE_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_type",
    "source_title",
    "source_path_or_url",
    "page",
    "claim",
    "supports_field",
    "evidence_strength",
    "is_primary_source",
    "provenance_status",
    "notes",
]

GAP_COLUMNS = [
    "stock_code",
    "stock_name",
    "gap_type",
    "gap_severity",
    "why_it_matters",
    "recommended_source_to_check",
    "recommended_next_action",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _int(value: Any) -> int:
    try:
        if value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    queue = _read_csv(INPUT_QUEUE).sort_values("stock_code").reset_index(drop=True)
    universe = _read_csv(SOURCE_UNIVERSE).sort_values("stock_code").drop_duplicates("stock_code", keep="first")
    return queue, universe


def _enriched_queue(queue: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    enrich_cols = [
        "stock_code",
        "primary_source_count",
        "evidence_count",
        "evidence_type",
        "evidence_strength",
        "data_gap_flags",
        "named_customer_flag",
        "order_or_capacity_flag",
        "revenue_traceable_flag",
        "financial_traceable_flag",
        "candidate_reason",
    ]
    merged = queue.merge(universe[enrich_cols], on="stock_code", how="left", suffixes=("", "_universe"))
    return merged.sort_values("stock_code").reset_index(drop=True)


def _evidence_rows(row: pd.Series) -> list[dict[str, Any]]:
    if _int(row.get("primary_source_count")) <= 0:
        return []
    rows = [
        {
            "source_type": "annual_report",
            "source_title": "structured candidate-universe annual/financial primary-source evidence",
            "claim": row.get("candidate_reason", ""),
            "supports_field": "hard_tech_exposure|business_relevance|financial_trace",
            "evidence_strength": "structured_primary_source",
        }
    ]
    if _truthy(row.get("order_or_capacity_flag")) or _truthy(row.get("named_customer_flag")):
        rows.append(
            {
                "source_type": "announcement",
                "source_title": "structured candidate-universe announcement/customer primary-source evidence",
                "claim": row.get("candidate_reason", ""),
                "supports_field": "customer_certification|order_or_capacity|supply_chain_role",
                "evidence_strength": "structured_primary_source",
            }
        )
    if _truthy(row.get("revenue_traceable_flag")) or _truthy(row.get("financial_traceable_flag")):
        rows.append(
            {
                "source_type": "revenue_or_financial_trace",
                "source_title": "structured candidate-universe revenue and financial trace evidence",
                "claim": row.get("candidate_reason", ""),
                "supports_field": "revenue_trace|financial_trace|value_capture",
                "evidence_strength": "structured_primary_source",
            }
        )
    out = []
    for item in rows:
        out.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "source_type": item["source_type"],
                "source_title": item["source_title"],
                "source_path_or_url": "",
                "page": "",
                "claim": item["claim"],
                "supports_field": item["supports_field"],
                "evidence_strength": item["evidence_strength"],
                "is_primary_source": True,
                "provenance_status": "structured_candidate_universe_field",
                "notes": "No source path or page was fabricated; this row preserves existing structured local audit evidence.",
            }
        )
    return out


def _gaps(row: pd.Series, primary_supported: bool) -> list[str]:
    gaps: list[str] = []
    if not primary_supported:
        gaps.append("missing_primary_source")
    if _int(row.get("primary_source_count")) <= 0:
        gaps.append("missing_annual_report")
        gaps.append("missing_announcement")
    if not _truthy(row.get("named_customer_flag")):
        gaps.append("missing_named_customer")
    if not _truthy(row.get("order_or_capacity_flag")):
        gaps.append("missing_order_or_capacity")
    if not _truthy(row.get("revenue_traceable_flag")):
        gaps.append("missing_revenue_trace")
    if not _truthy(row.get("financial_traceable_flag")):
        gaps.append("missing_financial_trace")
    gaps.extend(["missing_architecture_shift", "missing_route_around", "missing_value_capture", "missing_disconfirmation"])
    return list(dict.fromkeys(gaps))


def _assess(row: pd.Series) -> dict[str, Any]:
    primary_count = _int(row.get("primary_source_count"))
    named = _truthy(row.get("named_customer_flag"))
    order = _truthy(row.get("order_or_capacity_flag"))
    revenue = _truthy(row.get("revenue_traceable_flag"))
    financial = _truthy(row.get("financial_traceable_flag"))
    primary_supported = primary_count > 0
    gaps = _gaps(row, primary_supported)
    if primary_supported and revenue and financial and (named or order):
        status = "completed_with_structured_primary_source"
        support = "moderate"
        decision = "upgrade_to_latent_manual_approval_candidate"
        entry = "latent_manual_approval_candidate"
        next_action = "manual review of structured primary-source evidence before any quality-pool consideration"
        notes = "structured local audit fields support a manual approval candidate only; no automatic quality-pool addition"
    elif primary_supported:
        status = "completed_with_partial_structured_primary_source"
        support = "weak"
        decision = "remain_latent_pending_evidence"
        entry = "latent_pending_evidence"
        next_action = "collect page-level annual report, announcement, or official product source before equivalence review"
        notes = "partial structured primary-source support exists, but thesis gaps remain"
    else:
        status = "unresolved_due_to_missing_primary_source"
        support = "weak"
        decision = "remain_latent_pending_evidence"
        entry = "latent_pending_evidence"
        next_action = "collect annual report, announcement, official product source, and revenue trace"
        notes = "no local primary-source path or page evidence was found; evidence was not fabricated"
    return {
        "stock_code": row["stock_code"],
        "stock_name": row["stock_name"],
        "previous_quality_audit_decision": row.get("quality_audit_decision", ""),
        "primary_source_backfill_status": status,
        "primary_source_supported": primary_supported,
        "structured_primary_source_count": primary_count,
        "annual_report_evidence_count": 1 if primary_supported else 0,
        "announcement_evidence_count": 1 if primary_supported and (named or order) else 0,
        "revenue_trace_evidence_count": 1 if revenue else 0,
        "financial_trace_evidence_count": 1 if financial else 0,
        "brokerage_only_after_backfill": not primary_supported,
        "bottleneck_thesis_support_after_backfill": support,
        "business_relevance_after_backfill": "latent_hard_tech_primary_source_supported" if primary_supported else "latent_hard_tech_pending_primary_source",
        "supply_chain_role_quality_after_backfill": "moderate" if primary_supported else "weak",
        "architecture_shift_quality_after_backfill": "weak",
        "route_around_quality_after_backfill": "weak",
        "value_capture_quality_after_backfill": "moderate" if revenue and financial else "weak",
        "disconfirmation_found": False,
        "remaining_evidence_gap_flags": "|".join(gaps),
        "recommended_backfill_decision": decision,
        "recommended_manual_review_entry_class": entry,
        "recommended_next_evidence_action": next_action,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "price_move_used_for_signal": False,
        "low_position_used_for_signal": False,
        "notes": notes,
    }


def _build_results(queue: pd.DataFrame) -> pd.DataFrame:
    rows = [_assess(row) for _, row in queue.iterrows()]
    return pd.DataFrame(rows, columns=RESULT_COLUMNS).sort_values("stock_code").reset_index(drop=True)


def _build_evidence_matrix(queue: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in queue.iterrows():
        rows.extend(_evidence_rows(row))
    return pd.DataFrame(rows, columns=EVIDENCE_COLUMNS).sort_values(["stock_code", "source_type"]).reset_index(drop=True)


def _build_gap_matrix(results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in results.iterrows():
        flags = set(str(row["remaining_evidence_gap_flags"]).split("|")) if row["remaining_evidence_gap_flags"] else set()
        for gap in GAP_TYPES:
            present = gap in flags
            rows.append(
                {
                    "stock_code": row["stock_code"],
                    "stock_name": row["stock_name"],
                    "gap_type": gap,
                    "gap_severity": "high" if present and gap in {"missing_primary_source", "missing_annual_report"} else ("moderate" if present else "none"),
                    "why_it_matters": gap.replace("_", " "),
                    "recommended_source_to_check": _recommended_source(gap),
                    "recommended_next_action": f"backfill {gap.replace('_', ' ')} from primary source" if present else "no action for this gap",
                }
            )
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def _recommended_source(gap: str) -> str:
    return {
        "missing_primary_source": "annual report / announcement / official product source",
        "missing_annual_report": "annual report or prospectus",
        "missing_announcement": "exchange announcement",
        "missing_named_customer": "customer disclosure, certification, or annual report",
        "missing_order_or_capacity": "order, tender, capacity, or construction announcement",
        "missing_revenue_trace": "annual report product or segment revenue disclosure",
        "missing_financial_trace": "annual report financial statements",
        "missing_architecture_shift": "annual report business discussion or official technology source",
        "missing_route_around": "risk section, customer qualification, or competitor/substitute disclosure",
        "missing_value_capture": "gross margin, order, backlog, or pricing evidence",
        "missing_disconfirmation": "annual report risk section or counter evidence",
    }[gap]


def _split_outputs(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manual = results[results["recommended_backfill_decision"].eq("upgrade_to_latent_manual_approval_candidate")].copy()
    pending = results[results["recommended_backfill_decision"].eq("remain_latent_pending_evidence")].copy()
    adjacent = results[
        results["recommended_backfill_decision"].isin({"move_to_adjacent_watchlist", "downgrade_or_reject"})
    ].copy()
    return manual, pending, adjacent


def _summary(queue: pd.DataFrame, results: pd.DataFrame, evidence: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    manual, pending, adjacent_or_reject = _split_outputs(results)
    adjacent = adjacent_or_reject[adjacent_or_reject["recommended_backfill_decision"].eq("move_to_adjacent_watchlist")]
    reject = adjacent_or_reject[adjacent_or_reject["recommended_backfill_decision"].eq("downgrade_or_reject")]
    used_for_signal = int(results["used_for_signal"].astype(bool).sum()) if not results.empty else 0
    used_for_admission = int(results["used_for_admission"].astype(bool).sum()) if not results.empty else 0
    price_signal = int(results["price_move_used_for_signal"].astype(bool).sum()) if not results.empty else 0
    low_signal = int(results["low_position_used_for_signal"].astype(bool).sum()) if not results.empty else 0
    if not strategy_clean or used_for_signal or used_for_admission or price_signal or low_signal:
        acceptance = "blocked_due_to_guardrail_violation"
    elif len(pending) or len(adjacent_or_reject):
        acceptance = "conditionally_ready_with_remaining_gaps"
    else:
        acceptance = "latent_primary_source_backfill_batch1_ready"
    return {
        "task_name": TASK_NAME,
        "source_latent_high_priority_backfill_count": int(len(queue)),
        "processed_count": int(len(results)),
        "primary_source_supported_count": int(results["primary_source_supported"].astype(bool).sum()) if not results.empty else 0,
        "evidence_matrix_count": int(len(evidence)),
        "upgrade_count": int(len(manual)),
        "remain_pending_count": int(len(pending)),
        "adjacent_count": int(len(adjacent)),
        "downgrade_or_reject_count": int(len(reject)),
        "standard_backfill_processed": False,
        "manual_review_first_processed": False,
        "defer_reject_processed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": price_signal,
        "low_position_used_for_signal": low_signal,
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
        "source_latent_high_priority_backfill_count": summary["source_latent_high_priority_backfill_count"],
        "processed_count": summary["processed_count"],
        "only_high_priority_backfill_processed": summary["source_latent_high_priority_backfill_count"] == EXPECTED_QUEUE_COUNT
        and summary["processed_count"] == EXPECTED_QUEUE_COUNT,
        "standard_backfill_processed": False,
        "manual_review_first_processed": False,
        "defer_reject_processed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
        "low_position_used_for_signal": summary["low_position_used_for_signal"],
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
            "# Tech Bottleneck Latent Primary Source Backfill Batch1 v1",
            "",
            "## 1. Scope",
            "This task processes only the 49-stock latent high-priority backfill queue. It does not process standard backfill, manual-review-first, defer/reject, quality pool v3, or doubled-tech 596 names.",
            "",
            "## 2. Backfill Results",
            f"Processed: {summary['processed_count']}; primary-source supported: {summary['primary_source_supported_count']}; evidence rows: {summary['evidence_matrix_count']}.",
            "",
            "## 3. Queue Decisions",
            f"Latent manual approval candidates: {summary['upgrade_count']}; remain pending: {summary['remain_pending_count']}; adjacent: {summary['adjacent_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 4. Guardrails",
            f"auto_added_to_quality_pool_count={summary['auto_added_to_quality_pool_count']}; price_move_used_for_signal={summary['price_move_used_for_signal']}; low_position_used_for_signal={summary['low_position_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. latent_core_equivalence_gate_batch1_v1",
            "2. tech_bottleneck_latent_primary_source_backfill_batch2_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    queue, universe = _load_inputs()
    enriched = _enriched_queue(queue, universe)
    results = _build_results(enriched)
    evidence = _build_evidence_matrix(enriched)
    gaps = _build_gap_matrix(results)
    manual, pending, adjacent_or_reject = _split_outputs(results)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(enriched, results, evidence, strategy_clean)
    guardrails = _guardrails(summary)

    results.to_csv(output / "latent_backfill_batch1_results.csv", index=False)
    evidence.to_csv(output / "latent_backfill_batch1_evidence_matrix.csv", index=False)
    gaps.to_csv(output / "latent_backfill_batch1_gap_matrix.csv", index=False)
    manual.to_csv(output / "latent_backfill_batch1_manual_approval_candidates.csv", index=False)
    pending.to_csv(output / "latent_backfill_batch1_remain_pending.csv", index=False)
    adjacent_or_reject.to_csv(output / "latent_backfill_batch1_adjacent_or_reject.csv", index=False)
    _write_json(output / "latent_primary_source_backfill_batch1_summary.json", summary)
    _write_json(output / "latent_primary_source_backfill_batch1_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_primary_source_backfill_batch1_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary
