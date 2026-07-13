from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_omission_rescue_audit_v1"
REVIEW_UNIVERSE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
DEFAULT_SOURCE_FILES = [
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/expansion_keep_separate_4.csv",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/rescue_keep_separate_1.csv",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/data_gap_keep_separate_3.csv",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v4/latent_keep_separate_v4.csv",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_excluded_false_negative_review_v1/possible_false_negative_manual_review.csv",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_doubler_data_gap_watch_triage_v1/data_gap_manual_review.csv",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_human_confirm_first.csv",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _display_path(path: Path) -> str:
    if path.is_absolute():
        try:
            return str(path.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(path)
    return str(path)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _first(row: pd.Series, names: list[str]) -> str:
    for name in names:
        value = str(row.get(name) or "").strip()
        if value:
            return value
    return ""


def _load_candidates(source_files: list[Path]) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    for source in source_files:
        if not source.exists():
            missing.append(str(source.relative_to(PROJECT_ROOT) if source.is_absolute() else source))
            continue
        frame = _read_csv(source)
        if frame.empty or "stock_code" not in frame.columns:
            continue
        frame = frame.copy()
        frame["source_artifact"] = _display_path(source)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(), missing
    all_columns = sorted({column for frame in frames for column in frame.columns})
    normalized = [frame.reindex(columns=all_columns, fill_value="") for frame in frames]
    return pd.concat(normalized, ignore_index=True).fillna(""), missing


def _classify(row: pd.Series) -> tuple[str, str, str]:
    decision_text = " ".join(
        str(row.get(column) or "")
        for column in [
            "sidecar_status",
            "equivalence_gate_decision",
            "review_decision",
            "triage_decision",
            "recommended_manual_review_entry_class",
        ]
    ).lower()
    gap_text = " ".join(
        str(row.get(column) or "")
        for column in [
            "remaining_evidence_gap_flags",
            "downgrade_risk_flags",
            "data_gap_flags",
            "original_excluded_reason",
            "triage_reason",
            "equivalence_gate_reason",
            "core_equivalence_reason",
        ]
    ).lower()
    supported = _truthy(row.get("primary_source_supported"))
    page_citations = int(float(str(row.get("page_level_citation_count") or row.get("primary_source_evidence_count") or 0) or 0))
    hard_tech_hint = bool(
        _first(row, ["tech_bottleneck_domain", "hard_tech_domain_signal", "strict_theme", "tech_bottleneck_sub_domain"])
    )

    if "reject" in decision_text or "concept_only" in decision_text:
        return "remain_excluded_or_watch", "prior decision remains reject/concept-only; no automatic recall", "manual review only if thesis materially changes"
    if "human_confirm" in decision_text or "manual_review" in decision_text:
        return "human_confirm_before_review", "prior bucket requires human supply-chain role confirmation", "confirm role before source collection or review universe insertion"
    if "keep_separate" in decision_text or "keep_as" in decision_text:
        if supported or page_citations or hard_tech_hint:
            return (
                "add_to_review_universe_separate_review",
                f"kept outside quality pool due to {gap_text or 'unresolved evidence gap'}; recall as separate manual-review candidate only",
                "add to separate review queue; resolve route-around/product/source gaps before any quality-pool action",
            )
    if "data_gap_manual_review" in decision_text or hard_tech_hint:
        return "needs_targeted_evidence_collection", "hard-tech hint remains but evidence or role gap blocks direct review", "targeted evidence collection or manual source mapping"
    return "remain_excluded_or_watch", "no sufficient hard-tech or primary-source recall signal", "keep outside review universe"


def _build_output(candidates: pd.DataFrame, review_codes: set[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if candidates.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        code = _stock_code(row.get("stock_code"))
        if not code:
            continue
        decision, reason, action = _classify(row)
        output = {
            "stock_code": code,
            "stock_name": _first(row, ["stock_name", "name"]),
            "source_artifact": row.get("source_artifact", ""),
            "source_bucket": _first(row, ["sidecar_status", "review_decision", "triage_decision", "equivalence_gate_decision"]),
            "already_in_review_universe": code in review_codes,
            "primary_source_supported": _truthy(row.get("primary_source_supported")),
            "primary_source_evidence_count": row.get("primary_source_evidence_count", ""),
            "page_level_citation_count": row.get("page_level_citation_count", ""),
            "tech_bottleneck_domain": _first(row, ["tech_bottleneck_domain", "hard_tech_domain_signal", "strict_theme"]),
            "supply_chain_role": _first(row, ["supply_chain_role", "supply_chain_role_quality", "supply_chain_role_quality_after_backfill"]),
            "concept_pollution_risk": _first(row, ["concept_pollution_risk", "concept_pollution_residual_risk"]),
            "remaining_evidence_gap_flags": _first(row, ["remaining_evidence_gap_flags", "data_gap_flags"]),
            "downgrade_risk_flags": _first(row, ["downgrade_risk_flags", "equivalence_gate_reason", "core_equivalence_reason"]),
            "recall_decision": "already_in_review_universe" if code in review_codes else decision,
            "recall_reason": "already covered by current review universe" if code in review_codes else reason,
            "recommended_next_action": "do not duplicate" if code in review_codes else action,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
            "auto_added_to_quality_pool": False,
        }
        rows.append(output)
    audit = pd.DataFrame(rows).drop_duplicates(subset=["stock_code", "source_artifact"], keep="first")
    rescue_queue = audit[
        audit["recall_decision"].isin(
            ["add_to_review_universe_separate_review", "needs_targeted_evidence_collection", "human_confirm_before_review"]
        )
        & ~audit["already_in_review_universe"].astype(bool)
    ].drop_duplicates(subset=["stock_code"], keep="first")
    direct_additions = rescue_queue[rescue_queue["recall_decision"].eq("add_to_review_universe_separate_review")].copy()
    return audit, rescue_queue, direct_additions


def run(
    *,
    review_universe_path: Path = REVIEW_UNIVERSE,
    source_files: list[Path] | None = None,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    review = _read_csv(Path(review_universe_path))
    review_codes = set(review["stock_code"].astype(str).map(_stock_code)) if not review.empty else set()
    sources = source_files or DEFAULT_SOURCE_FILES
    candidates, missing_sources = _load_candidates([Path(source) for source in sources])
    audit, rescue_queue, direct_additions = _build_output(candidates, review_codes)
    strategy_clean = _strategy_diff_clean()
    used_for_signal = int(audit["used_for_signal"].map(_truthy).sum()) if not audit.empty else 0
    used_for_admission = int(audit["used_for_admission"].map(_truthy).sum()) if not audit.empty else 0
    duplicate_count = int(audit["already_in_review_universe"].astype(bool).sum()) if not audit.empty else 0
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_reference_count": int(len(review_codes)),
        "source_candidate_row_count": int(len(candidates)),
        "audited_candidate_count": int(audit["stock_code"].nunique()) if not audit.empty else 0,
        "duplicate_with_review_universe_count": duplicate_count,
        "rescue_queue_count": int(len(rescue_queue)),
        "recall_addition_count": int(len(direct_additions)),
        "human_confirm_before_review_count": int(rescue_queue["recall_decision"].eq("human_confirm_before_review").sum())
        if not rescue_queue.empty
        else 0,
        "targeted_evidence_collection_count": int(rescue_queue["recall_decision"].eq("needs_targeted_evidence_collection").sum())
        if not rescue_queue.empty
        else 0,
        "dongshan_recalled": bool("002384" in set(direct_additions.get("stock_code", pd.Series(dtype=str)))),
        "missing_source_directory_or_file_count": len(missing_sources),
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": "blocked_due_to_guardrail_violation"
        if used_for_signal or used_for_admission or not strategy_clean
        else "review_universe_omission_rescue_audit_ready",
    }
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_reference_count": summary["review_universe_reference_count"],
        "source_candidate_row_count": summary["source_candidate_row_count"],
        "rescue_queue_count": summary["rescue_queue_count"],
        "recall_addition_count": summary["recall_addition_count"],
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": summary["acceptance_decision"],
    }
    audit.to_csv(output / "review_universe_omission_rescue_audit.csv", index=False)
    rescue_queue.to_csv(output / "review_universe_omission_rescue_queue.csv", index=False)
    direct_additions.to_csv(output / "review_universe_separate_review_additions.csv", index=False)
    rescue_queue[rescue_queue["recall_decision"].eq("human_confirm_before_review")].to_csv(
        output / "review_universe_omission_human_confirm_before_review.csv", index=False
    )
    rescue_queue[rescue_queue["recall_decision"].eq("needs_targeted_evidence_collection")].to_csv(
        output / "review_universe_omission_targeted_evidence_collection_queue.csv", index=False
    )
    audit[audit["recall_decision"].eq("already_in_review_universe")].to_csv(
        output / "review_universe_omission_duplicate_or_already_covered.csv", index=False
    )
    audit[audit["recall_decision"].eq("remain_excluded_or_watch")].to_csv(
        output / "review_universe_omission_remain_excluded_or_watch.csv", index=False
    )
    _write_json(output / "review_universe_omission_missing_source_files.json", {"missing": missing_sources})
    _write_json(output / "review_universe_omission_rescue_audit_summary.json", summary)
    _write_json(output / "review_universe_omission_rescue_audit_guardrails.json", guardrails)
    report = f"""# {TASK_NAME}

- review universe reference: {summary['review_universe_reference_count']}
- audited candidates: {summary['audited_candidate_count']}
- rescue queue: {summary['rescue_queue_count']}
- recall additions: {summary['recall_addition_count']}
- human confirm before review: {summary['human_confirm_before_review_count']}
- targeted evidence collection: {summary['targeted_evidence_collection_count']}
- 东山精密 recalled: {summary['dongshan_recalled']}
- frozen quality pool generated: false
- used_for_signal/admission: {used_for_signal} / {used_for_admission}
- acceptance: {summary['acceptance_decision']}
"""
    (output / "tech_bottleneck_review_universe_omission_rescue_audit_v1_report.md").write_text(report, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit keep-separate/manual-review buckets for review-universe omissions.")
    parser.add_argument("--review-universe-path", type=Path, default=REVIEW_UNIVERSE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--source-file", action="append", type=Path, dest="source_files")
    args = parser.parse_args(argv)
    summary = run(
        review_universe_path=args.review_universe_path,
        source_files=args.source_files,
        output_dir=args.output_dir,
    )
    print(f"{TASK_NAME}|acceptance_decision|{summary['acceptance_decision']}")
    print(f"{TASK_NAME}|recall_addition_count|{summary['recall_addition_count']}")
    print(f"{TASK_NAME}|dongshan_recalled|{summary['dongshan_recalled']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
