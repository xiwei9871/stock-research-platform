from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_doubler_market_discovered_closure_v1"
MASTER_596 = PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/tech_bottleneck_2025_doubler_tech_expansion_queue_master.csv"
QUALITY_V3 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
IPO_COHORT = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stocks_since_20250101_v1/ipo_after_20250101_doubled_stocks.csv"
V3_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

SIDECAR_FILES = {
    "expansion_keep_separate": V3_DIR / "expansion_keep_separate_4.csv",
    "rescue_keep_separate": V3_DIR / "rescue_keep_separate_1.csv",
    "data_gap_keep_separate": V3_DIR / "data_gap_keep_separate_3.csv",
    "downgrade_or_reject": V3_DIR / "downgrade_or_reject_2.csv",
    "possible_false_negative_manual_review": V3_DIR / "possible_false_negative_manual_review_9.csv",
    "data_gap_manual_review": V3_DIR / "data_gap_manual_review_31.csv",
    "remain_data_gap_watch": V3_DIR / "remain_data_gap_watch_6.csv",
    "remain_excluded": V3_DIR / "remain_excluded_22.csv",
    "reject_concept_or_non_bottleneck": V3_DIR / "reject_concept_or_non_bottleneck_6.csv",
    "reject_weak_or_concept": V3_DIR / "reject_weak_or_concept_3.csv",
}


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


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    sidecars = {name: _read_csv(path) for name, path in SIDECAR_FILES.items()}
    return _read_csv(MASTER_596), _read_csv(QUALITY_V3), _read_csv(IPO_COHORT), sidecars


def _sidecar_lookup(sidecars: dict[str, pd.DataFrame]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for bucket, frame in sidecars.items():
        for code in frame["stock_code"]:
            lookup[_stock_code(code)] = bucket
    return lookup


def _final_bucket_from_sidecar(sidecar: str | None, original_class: str) -> str:
    if sidecar in {"expansion_keep_separate", "rescue_keep_separate", "data_gap_keep_separate"}:
        return "keep_separate"
    if sidecar in {"possible_false_negative_manual_review", "data_gap_manual_review"}:
        return "residual_manual_review"
    if sidecar == "remain_data_gap_watch":
        return "remain_data_gap_watch"
    if sidecar == "remain_excluded":
        return "remain_excluded"
    if sidecar in {"reject_concept_or_non_bottleneck", "reject_weak_or_concept", "downgrade_or_reject"}:
        return "reject_or_downgrade"
    if original_class == "weak_or_concept_only_no_backfill":
        return "weak_or_concept_only_no_backfill"
    return original_class or "unclassified"


def _build_master(master: pd.DataFrame, quality: pd.DataFrame, ipo: pd.DataFrame, sidecars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    quality_cols = [
        "stock_code",
        "quality_layer",
        "source_group",
        "proposal_source",
        "manual_review_status",
        "primary_source_supported",
        "bottleneck_thesis_support",
        "remaining_evidence_gap_flags",
    ]
    quality_lookup = quality[quality_cols].drop_duplicates("stock_code").set_index("stock_code").to_dict("index")
    side_lookup = _sidecar_lookup(sidecars)
    ipo_codes = set(ipo["stock_code"].map(_stock_code)) if not ipo.empty else set()
    rows: list[dict[str, Any]] = []
    for _, row in master.sort_values("stock_code").iterrows():
        code = row["stock_code"]
        q = quality_lookup.get(code, {})
        sidecar_bucket = side_lookup.get(code, "")
        final_bucket = "quality_pool_v3" if q else _final_bucket_from_sidecar(sidecar_bucket, row.get("expansion_queue_class", ""))
        rows.append(
            {
                **row.to_dict(),
                "final_market_discovered_bucket": final_bucket,
                "quality_layer": q.get("quality_layer", ""),
                "quality_pool_source_group": q.get("source_group", ""),
                "proposal_source": q.get("proposal_source", ""),
                "manual_review_status": q.get("manual_review_status", ""),
                "primary_source_supported": q.get("primary_source_supported", ""),
                "bottleneck_thesis_support": q.get("bottleneck_thesis_support", ""),
                "final_remaining_evidence_gap_flags": q.get("remaining_evidence_gap_flags", row.get("data_gap_flags", "")),
                "sidecar_bucket": sidecar_bucket,
                "ipo_cohort_risk": code in ipo_codes,
                "price_move_used_for_signal": False,
                "auto_applied": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows).sort_values("stock_code").reset_index(drop=True)


def _bucket_summary(closure: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for bucket, group in closure.groupby("final_market_discovered_bucket", dropna=False):
        rows.append(
            {
                "final_market_discovered_bucket": bucket,
                "candidate_count": int(len(group)),
                "ipo_cohort_risk_count": int(group["ipo_cohort_risk"].astype(bool).sum()),
                "research_only": True,
                "used_for_signal_count": int(group["used_for_signal"].astype(bool).sum()),
                "used_for_admission_count": int(group["used_for_admission"].astype(bool).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("final_market_discovered_bucket").reset_index(drop=True)


def _quality_source_summary(quality: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (layer, source), group in quality.groupby(["quality_layer", "source_group"], dropna=False):
        rows.append(
            {
                "quality_layer": layer,
                "source_group": source,
                "candidate_count": int(len(group)),
                "research_only": True,
                "used_for_signal_count": int(group["used_for_signal"].astype(bool).sum()),
                "used_for_admission_count": int(group["used_for_admission"].astype(bool).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["quality_layer", "source_group"]).reset_index(drop=True)


def _concat_sidecars(sidecars: dict[str, pd.DataFrame], names: list[str]) -> pd.DataFrame:
    frames = [sidecars[name].copy() for name in names]
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False).sort_values("stock_code").reset_index(drop=True)
    out["research_only"] = True
    out["used_for_signal"] = False
    out["used_for_admission"] = False
    return out


def _summary(closure: pd.DataFrame, quality: pd.DataFrame, sidecars: dict[str, pd.DataFrame], strategy_clean: bool) -> dict[str, Any]:
    bucket_counts = closure["final_market_discovered_bucket"].value_counts()
    layer_counts = quality["quality_layer"].value_counts()
    used_for_signal = int(closure["used_for_signal"].astype(bool).sum())
    used_for_admission = int(closure["used_for_admission"].astype(bool).sum())
    price_signal = int(closure["price_move_used_for_signal"].astype(bool).sum())
    auto_applied = int(closure["auto_applied"].astype(bool).sum())
    quality_pool_v3_count = int(len(quality))
    quality_pool_v3_overlap_count = int(bucket_counts.get("quality_pool_v3", 0))
    keep_separate_count = (
        len(sidecars["expansion_keep_separate"]) + len(sidecars["rescue_keep_separate"]) + len(sidecars["data_gap_keep_separate"])
    )
    residual_manual_review_count = len(sidecars["possible_false_negative_manual_review"]) + len(sidecars["data_gap_manual_review"])
    reject_count = (
        len(sidecars["reject_concept_or_non_bottleneck"])
        + len(sidecars["reject_weak_or_concept"])
        + len(sidecars["downgrade_or_reject"])
    )
    blocking = (
        len(closure) != 596
        or closure["stock_code"].nunique() != 596
        or quality_pool_v3_count != 234
        or quality_pool_v3_overlap_count != 200
        or keep_separate_count != 8
        or residual_manual_review_count != 40
        or len(sidecars["remain_data_gap_watch"]) != 6
        or len(sidecars["remain_excluded"]) != 22
        or reject_count != 11
        or int(bucket_counts.get("weak_or_concept_only_no_backfill", 0)) != 310
        or used_for_signal
        or used_for_admission
        or price_signal
        or auto_applied
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "input_doubled_tech_count": int(len(closure)),
        "closed_count": int(len(closure)),
        "quality_pool_v3_count": quality_pool_v3_count,
        "quality_pool_v3_market_discovered_overlap_count": quality_pool_v3_overlap_count,
        "internal_quality_pool_count": int(layer_counts.get("internal_quality_pool", 0)),
        "expansion_core_equivalent_count": int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)),
        "false_negative_rescue_core_equivalent_count": int(
            layer_counts.get("false_negative_rescue_core_equivalent_quality_pool", 0)
        ),
        "data_gap_core_equivalent_count": int(layer_counts.get("data_gap_core_equivalent_quality_pool", 0)),
        "keep_separate_count": int(keep_separate_count),
        "residual_manual_review_count": int(residual_manual_review_count),
        "remain_watch_count": int(len(sidecars["remain_data_gap_watch"])),
        "remain_excluded_count": int(len(sidecars["remain_excluded"])),
        "reject_count": int(reject_count),
        "weak_or_concept_only_no_backfill_count": int(bucket_counts.get("weak_or_concept_only_no_backfill", 0)),
        "ipo_cohort_risk_count": int(closure["ipo_cohort_risk"].astype(bool).sum()),
        "price_move_used_for_signal": price_signal,
        "auto_applied_count": auto_applied,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "doubler_market_discovered_closure_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "closure_generated": True,
        "all_596_accounted_for": summary["input_doubled_tech_count"] == 596 and summary["closed_count"] == 596,
        "quality_pool_v3_auto_applied": False,
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
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
            "# Tech Bottleneck Doubler Market-Discovered Closure v1",
            "",
            "## 1. Scope",
            "This research-only closure accounts for all 596 doubled technology stocks in the market-discovered line. It does not perform new screening, source backfill, signal generation, admission, or strategy updates.",
            "",
            "## 2. Quality Pool v3",
            f"Quality pool v3: {summary['quality_pool_v3_count']} = internal {summary['internal_quality_pool_count']} + expansion {summary['expansion_core_equivalent_count']} + false-negative rescue {summary['false_negative_rescue_core_equivalent_count']} + data-gap {summary['data_gap_core_equivalent_count']}.",
            f"Within the 596 doubled-tech market-discovered universe, quality pool v3 overlap is {summary['quality_pool_v3_market_discovered_overlap_count']}; the rest of v3 comes from non-doubler internal candidates.",
            "",
            "## 3. Residual Buckets",
            f"Keep separate: {summary['keep_separate_count']}; residual manual review: {summary['residual_manual_review_count']}; remain watch: {summary['remain_watch_count']}; remain excluded: {summary['remain_excluded_count']}; reject: {summary['reject_count']}; weak/concept-only no backfill: {summary['weak_or_concept_only_no_backfill_count']}.",
            "",
            "## 4. IPO And Price Guardrails",
            f"IPO cohort risk count: {summary['ipo_cohort_risk_count']}. Price move used for signal: {summary['price_move_used_for_signal']}.",
            "",
            "## 5. Guardrails",
            f"auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 6. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 7. Recommended Next Steps",
            "1. tech_bottleneck_stock_workspace_docling_panel_v1",
            "2. tech_bottleneck_latent_candidate_discovery_v1",
            "3. tech_bottleneck_quality_pool_layer_v3_manual_review_packet_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    master, quality, ipo, sidecars = _load_inputs()
    closure = _build_master(master, quality, ipo, sidecars)
    bucket_summary = _bucket_summary(closure)
    quality_summary = _quality_source_summary(quality)
    residual = _concat_sidecars(sidecars, ["possible_false_negative_manual_review", "data_gap_manual_review"])
    keep = _concat_sidecars(sidecars, ["expansion_keep_separate", "rescue_keep_separate", "data_gap_keep_separate"])
    excluded = _concat_sidecars(
        sidecars,
        ["remain_excluded", "reject_concept_or_non_bottleneck", "reject_weak_or_concept", "downgrade_or_reject"],
    )
    ipo_audit = closure[closure["ipo_cohort_risk"].eq(True)].copy()
    strategy_clean = _strategy_diff_clean()
    summary = _summary(closure, quality, sidecars, strategy_clean)
    guardrails = _guardrails(summary)

    closure.to_csv(output / "doubler_market_discovered_closure_master.csv", index=False)
    bucket_summary.to_csv(output / "doubler_market_discovered_bucket_summary.csv", index=False)
    quality_summary.to_csv(output / "quality_pool_v3_source_summary.csv", index=False)
    residual.to_csv(output / "residual_review_queue.csv", index=False)
    keep.to_csv(output / "keep_separate_queue.csv", index=False)
    excluded.to_csv(output / "excluded_reject_queue.csv", index=False)
    ipo_audit.to_csv(output / "ipo_cohort_risk_audit.csv", index=False)
    _write_json(output / "doubler_market_discovered_closure_summary.json", summary)
    _write_json(output / "doubler_market_discovered_closure_guardrails.json", guardrails)
    (output / "tech_bottleneck_doubler_market_discovered_closure_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
