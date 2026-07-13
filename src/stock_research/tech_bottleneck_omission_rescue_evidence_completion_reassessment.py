from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_review_universe_quality_reassessment import (
    PROJECT_ROOT,
    _load_market_profile_from_db,
    _stock_code,
    _strategy_diff_clean,
    _to_float,
    _truthy,
    _write_json,
)
from stock_research.tech_bottleneck_review_universe_quality_reassessment_v2 import (
    _merge_inputs_v2,
    _score_frame_v2,
)


TASK_NAME = "tech_bottleneck_omission_rescue_evidence_completion_reassessment_v1"
RESCUE_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_omission_rescue_audit_v1/"
    "review_universe_omission_rescue_queue.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

EVIDENCE_TEXT_COLUMNS = [
    "evidence_text",
    "claim",
    "excerpt",
    "chunk_text",
    "text",
    "content",
    "raw_text",
]
SOURCE_TITLE_COLUMNS = ["source_title", "report_title", "source_name", "title"]
SOURCE_PATH_COLUMNS = ["source_path", "source_path_or_url", "source_file", "file_path", "pdf_path"]
PAGE_COLUMNS = ["page", "page_locator", "page_number", "start_page"]
CLAIM_TYPE_COLUMNS = ["evidence_claim_type", "supports_field", "report_section", "evidence_kind", "claim_type"]


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _first(row: pd.Series, columns: list[str]) -> str:
    for column in columns:
        if column in row.index:
            value = str(row.get(column) or "").strip()
            if value and value.lower() != "nan":
                return value
    return ""


def _column(frame: pd.DataFrame, name: str, default: Any = "") -> pd.Series:
    if name in frame.columns:
        return frame[name]
    return pd.Series([default] * len(frame), index=frame.index)


def _discover_evidence_files(root: Path = PROJECT_ROOT / "outputs/research") -> list[Path]:
    files: list[Path] = []
    if not root.exists():
        return files
    name_hints = ("evidence", "citation", "chunks", "matrix", "parse", "backfill")
    for path in root.rglob("*.csv"):
        lower = str(path).lower()
        if not any(hint in lower for hint in name_hints):
            continue
        try:
            columns = list(pd.read_csv(path, nrows=0).columns)
        except Exception:
            continue
        if "stock_code" not in columns:
            continue
        if not any(column in columns for column in EVIDENCE_TEXT_COLUMNS + SOURCE_TITLE_COLUMNS + PAGE_COLUMNS):
            continue
        files.append(path)
    return files


def _normalize_evidence_row(row: pd.Series, source_file: Path) -> dict[str, Any]:
    evidence_text = _first(row, EVIDENCE_TEXT_COLUMNS)
    source_title = _first(row, SOURCE_TITLE_COLUMNS)
    source_path = _first(row, SOURCE_PATH_COLUMNS)
    page = _first(row, PAGE_COLUMNS)
    claim_type = _first(row, CLAIM_TYPE_COLUMNS)
    citation_quality = _first(row, ["citation_quality", "citation_granularity"])
    if not citation_quality:
        citation_quality = "page_level" if page else "source_level"
    source_type = _first(row, ["source_type", "report_type", "document_type"])
    return {
        "stock_code": _stock_code(row.get("stock_code")),
        "stock_name": _first(row, ["stock_name", "name"]),
        "source_title": source_title,
        "source_type": source_type,
        "source_path": source_path,
        "source_artifact": str(source_file.relative_to(PROJECT_ROOT)) if source_file.is_relative_to(PROJECT_ROOT) else str(source_file),
        "page": page,
        "evidence_text": evidence_text,
        "evidence_claim_type": claim_type,
        "citation_quality": citation_quality,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }


def _collect_existing_evidence(codes: set[str], evidence_files: list[Path] | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    paths = evidence_files if evidence_files is not None else _discover_evidence_files()
    for path in paths:
        if not Path(path).exists():
            continue
        try:
            columns = list(pd.read_csv(path, nrows=0).columns)
        except Exception:
            continue
        if "stock_code" not in columns:
            continue
        wanted = set(["stock_code", "stock_name", "name"]) | set(EVIDENCE_TEXT_COLUMNS) | set(SOURCE_TITLE_COLUMNS) | set(SOURCE_PATH_COLUMNS) | set(PAGE_COLUMNS) | set(CLAIM_TYPE_COLUMNS) | {
            "citation_quality",
            "citation_granularity",
            "source_type",
            "report_type",
            "document_type",
        }
        try:
            frame = pd.read_csv(path, dtype={"stock_code": str}, usecols=lambda column: column in wanted).fillna("")
        except Exception:
            continue
        if "stock_code" not in frame.columns:
            continue
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
        subset = frame[frame["stock_code"].isin(codes)].copy()
        if subset.empty:
            continue
        for _, row in subset.iterrows():
            normalized = _normalize_evidence_row(row, Path(path))
            if normalized["evidence_text"] or normalized["source_title"]:
                rows.append(normalized)
    if not rows:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "source_title",
                "source_type",
                "source_path",
                "source_artifact",
                "page",
                "evidence_text",
                "evidence_claim_type",
                "citation_quality",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    evidence = pd.DataFrame(rows).fillna("")
    evidence = evidence[evidence["stock_code"].isin(codes)].copy()
    evidence = evidence.drop_duplicates(
        subset=["stock_code", "source_title", "source_path", "page", "evidence_text"],
        keep="first",
    ).reset_index(drop=True)
    return evidence


def _source_index(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "source_title",
                "source_type",
                "source_path",
                "source_artifact",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    return (
        evidence[
            [
                "stock_code",
                "stock_name",
                "source_title",
                "source_type",
                "source_path",
                "source_artifact",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        ]
        .drop_duplicates()
        .sort_values(["stock_code", "source_title", "source_path"])
        .reset_index(drop=True)
    )


def _evidence_stats(evidence: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["stock_code", "evidence_count", "page_citation_count", "source_pdf_count", "strongest_primary_source_claim"])
    evidence_count = evidence.groupby("stock_code").size().rename("evidence_count")
    page_count = (
        evidence[
            evidence["citation_quality"].astype(str).str.contains("page", case=False, na=False)
            | evidence["page"].astype(str).str.len().gt(0)
        ]
        .groupby("stock_code")
        .size()
        .rename("page_citation_count")
    )
    if sources.empty:
        source_count = pd.Series(dtype=int, name="source_pdf_count")
    else:
        source_count = sources.groupby("stock_code").size().rename("source_pdf_count")
    strongest = evidence.sort_values(["stock_code", "citation_quality", "page"]).groupby("stock_code")["evidence_text"].first().rename("strongest_primary_source_claim")
    return (
        pd.concat([evidence_count, page_count, source_count, strongest], axis=1)
        .reset_index()
        .fillna({"evidence_count": 0, "page_citation_count": 0, "source_pdf_count": 0, "strongest_primary_source_claim": ""})
    )


def _build_reassessment_dataset(queue: pd.DataFrame, evidence: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    stats = _evidence_stats(evidence, sources)
    frame = queue.copy().merge(stats, on="stock_code", how="left")
    for column in ["evidence_count", "page_citation_count", "source_pdf_count"]:
        frame[column] = frame[column].map(_to_float)
    frame["strongest_primary_source_claim"] = frame.get("strongest_primary_source_claim", "").fillna("")
    fallback_evidence_count = (
        frame["primary_source_evidence_count"].map(_to_float)
        if "primary_source_evidence_count" in frame.columns
        else pd.Series([0.0] * len(frame), index=frame.index)
    )
    fallback_page_count = (
        frame["page_level_citation_count"].map(_to_float)
        if "page_level_citation_count" in frame.columns
        else pd.Series([0.0] * len(frame), index=frame.index)
    )
    frame["evidence_count"] = frame["evidence_count"].where(frame["evidence_count"].gt(0), fallback_evidence_count)
    frame["page_citation_count"] = frame["page_citation_count"].where(frame["page_citation_count"].gt(0), fallback_page_count)
    frame["source_pdf_count"] = frame["source_pdf_count"].where(frame["source_pdf_count"].gt(0), 0)
    frame["primary_source_supported"] = frame["evidence_count"].gt(0) | _column(frame, "primary_source_supported", False).map(_truthy)
    frame["evidence_completion_status"] = "remaining_needs_primary_source_collection"
    frame.loc[frame["page_citation_count"].gt(0), "evidence_completion_status"] = "hydrated_page_level_evidence"
    frame.loc[frame["evidence_count"].gt(0) & frame["page_citation_count"].eq(0), "evidence_completion_status"] = "evidence_light_but_usable"
    frame["review_universe_source"] = frame["recall_decision"].map(
        {
            "add_to_review_universe_separate_review": "omission_rescue_direct_separate_review",
            "human_confirm_before_review": "omission_rescue_human_confirm",
        }
    ).fillna("omission_rescue")
    frame["current_layer_status"] = frame["recall_decision"]
    frame["manual_approval_status"] = "pending_manual_review"
    frame["industry"] = _column(frame, "tech_bottleneck_domain", "")
    frame["concept_tags"] = (
        _column(frame, "tech_bottleneck_domain", "").astype(str)
        + " / "
        + _column(frame, "remaining_evidence_gap_flags", "").astype(str)
        + " / "
        + _column(frame, "downgrade_risk_flags", "").astype(str)
    )
    frame["source_group"] = frame["review_universe_source"]
    frame["previous_tier"] = _column(frame, "candidate_tier", "")
    frame["evidence_strength"] = "insufficient"
    frame.loc[frame["page_citation_count"].between(1, 9), "evidence_strength"] = "moderate"
    frame.loc[frame["page_citation_count"].ge(10), "evidence_strength"] = "strong"
    frame["bottleneck_relevance"] = "unclear"
    frame.loc[frame["recall_decision"].eq("add_to_review_universe_separate_review"), "bottleneck_relevance"] = "core"
    frame.loc[frame["recall_decision"].eq("human_confirm_before_review") & frame["page_citation_count"].gt(0), "bottleneck_relevance"] = "likely_core_pending"
    frame["bottleneck_confidence_score"] = 45
    frame.loc[frame["recall_decision"].eq("add_to_review_universe_separate_review"), "bottleneck_confidence_score"] = 70
    frame.loc[frame["page_citation_count"].ge(10), "bottleneck_confidence_score"] = 76
    frame["evidence_quality_score"] = 20 + frame["page_citation_count"].clip(upper=25) * 2
    frame["evidence_quality_score"] = frame["evidence_quality_score"].clip(upper=78)
    frame.loc[frame["page_citation_count"].eq(0), "evidence_quality_score"] = 20
    frame["route_around_or_substitution_risk"] = _column(frame, "remaining_evidence_gap_flags", "").map(
        lambda value: "high" if "route_around" in str(value) else "medium" if str(value).strip() else "unclear"
    )
    frame["value_capture_risk"] = _column(frame, "downgrade_risk_flags", "").map(lambda value: "weak" if "value" in str(value).lower() else "unclear")
    frame["weakest_or_riskiest_claim"] = _column(frame, "remaining_evidence_gap_flags", "").astype(str)
    frame["evidence_summary_for_review"] = frame["strongest_primary_source_claim"].astype(str).str.slice(0, 500)
    frame["used_for_signal"] = False
    frame["used_for_admission"] = False
    frame["auto_added_to_quality_pool"] = False
    return frame.fillna("")


def _tier_outputs(scored: pd.DataFrame, output: Path) -> None:
    mapping = {
        "tier_1_core_review_priority": "omission_rescue_tier1_priority_review.csv",
        "tier_2_strong_review_candidate": "omission_rescue_tier2_review_candidate.csv",
        "tier_3_quality_or_value_capture_gap": "omission_rescue_tier3_gap_or_hold.csv",
        "tier_4_downgrade_or_reject_review": "omission_rescue_tier4_reject_or_downgrade.csv",
    }
    for tier, filename in mapping.items():
        scored[scored["quality_reassessment_tier"].eq(tier)].to_csv(output / filename, index=False)


def _summary(scored: pd.DataFrame, evidence: pd.DataFrame, sources: pd.DataFrame, queue: pd.DataFrame, *, strategy_clean: bool) -> dict[str, Any]:
    tier_counts = scored["quality_reassessment_tier"].value_counts().to_dict()
    used_for_signal = int(scored["used_for_signal"].map(_truthy).sum())
    used_for_admission = int(scored["used_for_admission"].map(_truthy).sum())
    page_stock_count = int(scored["page_citation_count"].map(_to_float).gt(0).sum())
    direct_count = int(queue["recall_decision"].eq("add_to_review_universe_separate_review").sum())
    human_count = int(queue["recall_decision"].eq("human_confirm_before_review").sum())
    blocking = len(scored) != len(queue) or used_for_signal or used_for_admission or not strategy_clean
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_rescue_queue_count": int(len(queue)),
        "direct_separate_review_count": direct_count,
        "human_confirm_before_review_count": human_count,
        "scored_count": int(len(scored)),
        "page_level_evidence_stock_count": page_stock_count,
        "evidence_index_rows": int(len(evidence)),
        "source_index_rows": int(len(sources)),
        "remaining_evidence_gap_count": int(scored["evidence_completion_status"].eq("remaining_needs_primary_source_collection").sum()),
        "tier_1_core_review_priority_count": int(tier_counts.get("tier_1_core_review_priority", 0)),
        "tier_2_strong_review_candidate_count": int(tier_counts.get("tier_2_strong_review_candidate", 0)),
        "tier_3_quality_or_value_capture_gap_count": int(tier_counts.get("tier_3_quality_or_value_capture_gap", 0)),
        "tier_4_downgrade_or_reject_review_count": int(tier_counts.get("tier_4_downgrade_or_reject_review", 0)),
        "evidence_completion_performed": True,
        "quality_reassessment_performed": True,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "blocked_due_to_guardrail_violation"
        if blocking
        else (
            "omission_rescue_reassessment_ready"
            if page_stock_count == len(queue)
            else "conditionally_ready_with_remaining_evidence_gaps"
        ),
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_rescue_queue_count": summary["source_rescue_queue_count"],
        "scored_count": summary["scored_count"],
        "evidence_completion_performed": True,
        "quality_reassessment_performed": True,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "acceptance_decision": summary["acceptance_decision"],
    }


def _write_report(output: Path, summary: dict[str, Any]) -> None:
    text = f"""# {TASK_NAME}

## Summary

- rescue queue: {summary['source_rescue_queue_count']}
- direct separate review: {summary['direct_separate_review_count']}
- human confirm before review: {summary['human_confirm_before_review_count']}
- page-level evidence stocks: {summary['page_level_evidence_stock_count']}
- remaining evidence gaps: {summary['remaining_evidence_gap_count']}
- tier1/tier2/tier3/tier4: {summary['tier_1_core_review_priority_count']} / {summary['tier_2_strong_review_candidate_count']} / {summary['tier_3_quality_or_value_capture_gap_count']} / {summary['tier_4_downgrade_or_reject_review_count']}

## Guardrails

- research-only: true
- frozen quality pool generated: false
- auto added to quality pool: 0
- used_for_signal/admission: 0 / 0
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## Acceptance

{summary['acceptance_decision']}
"""
    (output / "tech_bottleneck_omission_rescue_evidence_completion_reassessment_v1_report.md").write_text(text, encoding="utf-8")


def run(
    *,
    rescue_queue_path: Path = RESCUE_QUEUE,
    evidence_files: list[Path] | None = None,
    output_dir: Path = OUTPUT_DIR,
    as_of_date: str = "2026-07-09",
    service: str = SETTINGS.research_service,
    market_profile: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    queue = _read_csv(Path(rescue_queue_path))
    codes = set(queue["stock_code"].astype(str).map(_stock_code))
    evidence = _collect_existing_evidence(codes, evidence_files)
    sources = _source_index(evidence)
    dataset = _build_reassessment_dataset(queue, evidence, sources)
    profile = market_profile or _load_market_profile_from_db(sorted(codes), as_of_date=as_of_date, service=service)
    merged = _merge_inputs_v2(dataset, pd.DataFrame(), evidence, profile)
    scored = _score_frame_v2(merged)
    if "evidence_completion_status" not in scored.columns:
        scored["evidence_completion_status"] = dataset["evidence_completion_status"]
    strategy_clean = _strategy_diff_clean()
    summary = _summary(scored, evidence, sources, queue, strategy_clean=strategy_clean)
    guardrails = _guardrails(summary)
    scored.to_csv(output / "omission_rescue_quality_reassessment.csv", index=False)
    evidence.to_csv(output / "omission_rescue_evidence_index.csv", index=False)
    sources.to_csv(output / "omission_rescue_source_index.csv", index=False)
    _tier_outputs(scored, output)
    scored[scored["evidence_completion_status"].eq("remaining_needs_primary_source_collection")].to_csv(
        output / "omission_rescue_remaining_evidence_gap_queue.csv", index=False
    )
    _write_json(output / "omission_rescue_evidence_completion_reassessment_summary.json", summary)
    _write_json(output / "omission_rescue_evidence_completion_reassessment_guardrails.json", guardrails)
    _write_report(output, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Complete evidence hydration and preliminary tier reassessment for omission rescue candidates.")
    parser.add_argument("--rescue-queue-path", type=Path, default=RESCUE_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--evidence-file", action="append", type=Path, dest="evidence_files")
    parser.add_argument("--as-of-date", default="2026-07-09")
    parser.add_argument("--service", default=SETTINGS.research_service)
    args = parser.parse_args(argv)
    summary = run(
        rescue_queue_path=args.rescue_queue_path,
        evidence_files=args.evidence_files,
        output_dir=args.output_dir,
        as_of_date=args.as_of_date,
        service=args.service,
    )
    print(f"{TASK_NAME}|acceptance_decision|{summary['acceptance_decision']}")
    print(f"{TASK_NAME}|scored_count|{summary['scored_count']}")
    print(f"{TASK_NAME}|tier1|{summary['tier_1_core_review_priority_count']}")
    print(f"{TASK_NAME}|tier2|{summary['tier_2_strong_review_candidate_count']}")
    print(f"{TASK_NAME}|tier3|{summary['tier_3_quality_or_value_capture_gap_count']}")
    print(f"{TASK_NAME}|tier4|{summary['tier_4_downgrade_or_reject_review_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
