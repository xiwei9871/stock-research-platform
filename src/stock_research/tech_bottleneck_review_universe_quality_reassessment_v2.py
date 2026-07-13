from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_review_universe_quality_reassessment import (
    FORMAL_STRATEGY_FILES,
    HARD_TECH_KEYWORDS,
    LOW_VALUE_KEYWORDS,
    PROJECT_ROOT,
    REPORT_EVIDENCE,
    _build_business_snapshot,
    _clip,
    _contains_any,
    _count_keywords,
    _evidence_score,
    _financial_quality_score,
    _load_market_profile_from_db,
    _merge_inputs,
    _read_csv,
    _risk_penalty,
    _stock_code,
    _strategy_diff_clean,
    _tier,
    _to_float,
    _truthy,
    _write_json,
)


TASK_NAME = "tech_bottleneck_review_universe_quality_reassessment_v2"
FRONTEND_DATASET = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
FRONTEND_EVIDENCE_INDEX = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_evidence_index.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME


def _page_evidence_features(evidence_index: pd.DataFrame) -> pd.DataFrame:
    if evidence_index.empty or "stock_code" not in evidence_index.columns:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "page_level_evidence_text",
                "page_level_evidence_row_count",
                "page_level_hard_tech_keyword_hit_count",
                "page_level_matched_keywords",
            ]
        )
    frame = evidence_index.copy()
    frame["stock_code"] = frame["stock_code"].map(_stock_code)
    text_columns = [column for column in ["evidence_text", "source_title", "evidence_claim_type"] if column in frame.columns]
    if not text_columns:
        frame["page_text_piece"] = ""
    else:
        frame["page_text_piece"] = frame[text_columns].astype(str).agg(" ".join, axis=1)
    rows: list[dict[str, Any]] = []
    for code, group in frame.groupby("stock_code"):
        text = " ".join(group["page_text_piece"].astype(str).tolist())
        upper = text.upper()
        matched = sorted({keyword for keyword in HARD_TECH_KEYWORDS if keyword.upper() in upper})
        rows.append(
            {
                "stock_code": code,
                "page_level_evidence_text": text[:20000],
                "page_level_evidence_row_count": int(len(group)),
                "page_level_hard_tech_keyword_hit_count": int(len(matched)),
                "page_level_matched_keywords": "|".join(matched),
            }
        )
    return pd.DataFrame(rows)


def _merge_inputs_v2(
    dataset: pd.DataFrame,
    report_evidence: pd.DataFrame,
    frontend_evidence_index: pd.DataFrame,
    market_profile: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    base = _merge_inputs(dataset, report_evidence, market_profile)
    features = _page_evidence_features(frontend_evidence_index)
    if not features.empty:
        base = base.merge(features, on="stock_code", how="left")
    for column in [
        "page_level_evidence_text",
        "page_level_evidence_row_count",
        "page_level_hard_tech_keyword_hit_count",
        "page_level_matched_keywords",
    ]:
        if column not in base.columns:
            base[column] = "" if column.endswith("text") or column.endswith("keywords") else 0
    return base.fillna("")


def _business_alignment_score_v2(row: pd.Series) -> float:
    text = " / ".join(
        str(row.get(column) or "")
        for column in [
            "industry",
            "db_industry",
            "concept_tags",
            "db_concept_tags",
            "top_product_name",
            "strongest_primary_source_claim",
            "evidence_summary_for_review",
            "page_level_evidence_text",
        ]
    )
    page_hits = _to_float(row.get("page_level_hard_tech_keyword_hit_count"))
    total_hits = _count_keywords(text, HARD_TECH_KEYWORDS)
    score = 35 + min(40, total_hits * 6)
    top_ratio = _to_float(row.get("top_product_revenue_ratio"))
    top_gm = _to_float(row.get("top_product_gross_margin"))
    hard_hits = _to_float(row.get("hard_tech_product_hit_count"))
    if top_ratio >= 50 and (hard_hits or page_hits >= 2):
        score += 15
    elif top_ratio >= 30 and (hard_hits or page_hits >= 2):
        score += 8
    if top_gm >= 35:
        score += 10
    elif top_gm >= 20:
        score += 5
    if page_hits >= 4:
        score += 6
    elif page_hits >= 2:
        score += 3
    if _contains_any(text, LOW_VALUE_KEYWORDS):
        score -= 15
    return _clip(score)


def _score_frame_v2(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        report_count = int(_to_float(row.get("broker_report_evidence_count")))
        evidence_score = _evidence_score(row, report_count)
        business_score = _business_alignment_score_v2(row)
        financial_score = _financial_quality_score(row)
        penalty = _risk_penalty(row)
        overall = _clip(0.38 * evidence_score + 0.30 * business_score + 0.24 * financial_score + 8 - penalty)
        output = row.to_dict()
        output.update(
            {
                "evidence_chain_score": round(evidence_score, 1),
                "business_alignment_score": round(business_score, 1),
                "financial_quality_score": round(financial_score, 1),
                "risk_penalty": round(penalty, 1),
                "overall_quality_score": round(overall, 1),
            }
        )
        tier, action, reason = _tier(pd.Series(output))
        output.update(
            {
                "quality_reassessment_tier": tier,
                "recommended_review_action": action,
                "quality_reassessment_reason": reason,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
            }
        )
        rows.append(output)
    return pd.DataFrame(rows)


def _summary(
    scored: pd.DataFrame,
    *,
    expected_count: int,
    strategy_clean: bool,
) -> dict[str, Any]:
    tier_counts = scored["quality_reassessment_tier"].value_counts().to_dict()
    used_for_signal = int(scored["used_for_signal"].map(_truthy).sum())
    used_for_admission = int(scored["used_for_admission"].map(_truthy).sum())
    page_stock_count = int(scored["page_level_evidence_row_count"].map(_to_float).gt(0).sum())
    hude = scored[scored["stock_code"].eq("002463")]
    hude_tier = str(hude.iloc[0]["quality_reassessment_tier"]) if not hude.empty else ""
    hude_business = float(hude.iloc[0]["business_alignment_score"]) if not hude.empty else 0.0
    blocking = (
        len(scored) != expected_count
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": int(len(scored)),
        "tier_1_core_review_priority_count": int(tier_counts.get("tier_1_core_review_priority", 0)),
        "tier_2_strong_review_candidate_count": int(tier_counts.get("tier_2_strong_review_candidate", 0)),
        "tier_3_quality_or_value_capture_gap_count": int(tier_counts.get("tier_3_quality_or_value_capture_gap", 0)),
        "tier_4_downgrade_or_reject_review_count": int(tier_counts.get("tier_4_downgrade_or_reject_review", 0)),
        "page_level_evidence_enrichment_applied": True,
        "page_level_evidence_stock_count": page_stock_count,
        "hude_business_alignment_score": hude_business,
        "hude_quality_reassessment_tier": hude_tier,
        "reassessment_performed": True,
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
        else "review_universe_quality_reassessment_v2_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": summary["review_universe_total_count"],
        "page_level_evidence_enrichment_applied": summary["page_level_evidence_enrichment_applied"],
        "reassessment_performed": True,
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

- review universe: {summary['review_universe_total_count']}
- tier 1: {summary['tier_1_core_review_priority_count']}
- tier 2: {summary['tier_2_strong_review_candidate_count']}
- tier 3: {summary['tier_3_quality_or_value_capture_gap_count']}
- tier 4: {summary['tier_4_downgrade_or_reject_review_count']}
- page-level evidence stock count: {summary['page_level_evidence_stock_count']}
- 沪电股份 business score/tier: {summary['hude_business_alignment_score']} / {summary['hude_quality_reassessment_tier']}

## Guardrails

- research-only: true
- frozen quality pool generated: false
- auto added to quality pool: 0
- used_for_signal/admission: 0 / 0
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## Acceptance

{summary['acceptance_decision']}
"""
    (output / "tech_bottleneck_review_universe_quality_reassessment_v2_report.md").write_text(text, encoding="utf-8")


def run(
    *,
    frontend_dataset_path: Path = FRONTEND_DATASET,
    report_evidence_path: Path = REPORT_EVIDENCE,
    frontend_evidence_index_path: Path = FRONTEND_EVIDENCE_INDEX,
    output_dir: Path = OUTPUT_DIR,
    as_of_date: str = "2026-07-09",
    service: str = SETTINGS.research_service,
    market_profile: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dataset = _read_csv(Path(frontend_dataset_path))
    report_evidence = _read_csv(Path(report_evidence_path)) if Path(report_evidence_path).exists() else pd.DataFrame()
    frontend_evidence = _read_csv(Path(frontend_evidence_index_path)) if Path(frontend_evidence_index_path).exists() else pd.DataFrame()
    codes = dataset["stock_code"].astype(str).map(_stock_code).tolist()
    profile = market_profile or _load_market_profile_from_db(codes, as_of_date=as_of_date, service=service)
    merged = _merge_inputs_v2(dataset, report_evidence, frontend_evidence, profile)
    scored = _score_frame_v2(merged)
    business_snapshot = _build_business_snapshot(scored)
    score_breakdown = scored[
        [
            "stock_code",
            "stock_name",
            "evidence_chain_score",
            "business_alignment_score",
            "financial_quality_score",
            "risk_penalty",
            "overall_quality_score",
            "page_level_hard_tech_keyword_hit_count",
            "page_level_matched_keywords",
            "quality_reassessment_tier",
            "recommended_review_action",
            "quality_reassessment_reason",
        ]
    ].copy()
    tier_buckets = (
        scored.groupby("quality_reassessment_tier", as_index=False)
        .agg(stock_count=("stock_code", "count"), avg_overall_quality_score=("overall_quality_score", "mean"))
        .sort_values("quality_reassessment_tier")
    )
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        scored,
        expected_count=len(dataset),
        strategy_clean=strategy_clean,
    )
    guardrails = _guardrails(summary)
    scored.to_csv(output / "review_universe_quality_reassessment_v2.csv", index=False)
    score_breakdown.to_csv(output / "review_universe_quality_score_breakdown_v2.csv", index=False)
    business_snapshot.to_csv(output / "review_universe_business_quality_snapshot_v2.csv", index=False)
    tier_buckets.to_csv(output / "review_universe_reassessment_tier_buckets_v2.csv", index=False)
    _write_json(output / "review_universe_quality_reassessment_v2_summary.json", summary)
    _write_json(output / "review_universe_quality_reassessment_v2_guardrails.json", guardrails)
    _write_report(output, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reassess review-universe stocks with page-level evidence enrichment.")
    parser.add_argument("--frontend-dataset-path", type=Path, default=FRONTEND_DATASET)
    parser.add_argument("--report-evidence-path", type=Path, default=REPORT_EVIDENCE)
    parser.add_argument("--frontend-evidence-index-path", type=Path, default=FRONTEND_EVIDENCE_INDEX)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--as-of-date", default="2026-07-09")
    parser.add_argument("--service", default=SETTINGS.research_service)
    args = parser.parse_args(argv)
    summary = run(
        frontend_dataset_path=args.frontend_dataset_path,
        report_evidence_path=args.report_evidence_path,
        frontend_evidence_index_path=args.frontend_evidence_index_path,
        output_dir=args.output_dir,
        as_of_date=args.as_of_date,
        service=args.service,
    )
    print(f"{TASK_NAME}|acceptance_decision|{summary['acceptance_decision']}")
    print(f"{TASK_NAME}|review_universe_total_count|{summary['review_universe_total_count']}")
    print(f"{TASK_NAME}|hude_business_alignment_score|{summary['hude_business_alignment_score']}")
    print(f"{TASK_NAME}|hude_quality_reassessment_tier|{summary['hude_quality_reassessment_tier']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
