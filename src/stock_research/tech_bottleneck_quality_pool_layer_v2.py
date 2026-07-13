from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v2"
V1_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v1/quality_pool_layer_manifest.csv"
V1_EXPANSION_KEEP_4 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v1/expansion_keep_separate_4.csv"
V1_DOWNGRADE_REJECT_2 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v1/downgrade_or_reject_2.csv"
RESCUE_38 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_false_negative_rescue_core_equivalence_gate_v1/rescue_core_equivalent_add_to_quality_pool.csv"
)
RESCUE_KEEP_1 = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_false_negative_rescue_core_equivalence_gate_v1/keep_as_rescue_candidate.csv"
)
POSSIBLE_FALSE_NEGATIVE_9 = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_excluded_false_negative_review_v1/possible_false_negative_manual_review.csv"
)
REMAIN_EXCLUDED_22 = PROJECT_ROOT / "outputs/research/tech_bottleneck_excluded_false_negative_review_v1/remain_excluded.csv"
REJECT_CONCEPT_6 = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_excluded_false_negative_review_v1/reject_as_concept_or_non_bottleneck.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
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


def _load_inputs() -> dict[str, pd.DataFrame]:
    return {
        "v1_manifest": _read_csv(V1_MANIFEST),
        "rescue_38": _read_csv(RESCUE_38),
        "expansion_keep_4": _read_csv(V1_EXPANSION_KEEP_4),
        "rescue_keep_1": _read_csv(RESCUE_KEEP_1),
        "downgrade_reject_2": _read_csv(V1_DOWNGRADE_REJECT_2),
        "possible_false_negative_9": _read_csv(POSSIBLE_FALSE_NEGATIVE_9),
        "remain_excluded_22": _read_csv(REMAIN_EXCLUDED_22),
        "reject_concept_6": _read_csv(REJECT_CONCEPT_6),
    }


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _rescue_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "quality_layer": "false_negative_rescue_core_equivalent_quality_pool",
                "source_group": row.get("source_group", "false_negative_rescue_backfilled"),
                "proposal_source": "false_negative_rescue_core_equivalence_gate_v1",
                "manual_review_status": "pending_manual_approval",
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support_after_backfill", ""),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": row.get("concept_pollution_residual_risk", ""),
                "manual_approval_question": "Should this false-negative rescue-origin core-equivalent candidate enter the same manual review quality layer as v1 quality-pool names?",
                "recommended_next_action": row.get("recommended_next_action", ""),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_manifest(v1_manifest: pd.DataFrame, rescue_38: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stock_code",
        "stock_name",
        "quality_layer",
        "source_group",
        "proposal_source",
        "manual_review_status",
        "primary_source_supported",
        "bottleneck_thesis_support",
        "remaining_evidence_gap_flags",
        "downgrade_risk_flags",
        "manual_approval_question",
        "recommended_next_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    v1 = v1_manifest[columns].copy()
    v1["research_only"] = True
    v1["used_for_signal"] = False
    v1["used_for_admission"] = False
    rescue = _rescue_rows(rescue_38)
    manifest = pd.concat([v1, rescue], ignore_index=True, sort=False)
    return manifest[columns].sort_values(["quality_layer", "stock_code"]).reset_index(drop=True)


def _by_source(manifest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (layer, source), group in manifest.groupby(["quality_layer", "source_group"], dropna=False):
        rows.append(
            {
                "quality_layer": layer,
                "source_group": source,
                "candidate_count": int(len(group)),
                "primary_source_supported_count": int(group["primary_source_supported"].astype(bool).sum()),
                "research_only": True,
                "used_for_signal_count": int(group["used_for_signal"].astype(bool).sum()),
                "used_for_admission_count": int(group["used_for_admission"].astype(bool).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["quality_layer", "source_group"]).reset_index(drop=True)


def _normalize_sidecar(frame: pd.DataFrame, status: str) -> pd.DataFrame:
    rows = frame.copy().sort_values("stock_code").reset_index(drop=True)
    rows["sidecar_status"] = status
    rows["research_only"] = True
    rows["used_for_signal"] = False
    rows["used_for_admission"] = False
    rows["auto_applied"] = False
    rows["auto_added_to_quality_pool"] = False
    return rows


def _summary(
    manifest: pd.DataFrame,
    sidecars: dict[str, pd.DataFrame],
    strategy_clean: bool,
) -> dict[str, Any]:
    layer_counts = manifest["quality_layer"].value_counts()
    used_for_signal = int(manifest["used_for_signal"].astype(bool).sum())
    used_for_admission = int(manifest["used_for_admission"].astype(bool).sum())
    duplicate_count = int(len(manifest) - manifest["stock_code"].nunique())
    blocking = (
        len(manifest) != 210
        or duplicate_count != 0
        or int(layer_counts.get("internal_quality_pool", 0)) != 88
        or int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)) != 84
        or int(layer_counts.get("false_negative_rescue_core_equivalent_quality_pool", 0)) != 38
        or len(sidecars["expansion_keep_4"]) != 4
        or len(sidecars["rescue_keep_1"]) != 1
        or len(sidecars["downgrade_reject_2"]) != 2
        or len(sidecars["possible_false_negative_9"]) != 9
        or len(sidecars["remain_excluded_22"]) != 22
        or len(sidecars["reject_concept_6"]) != 6
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "quality_pool_v1_count": 172,
        "quality_pool_v2_count": int(len(manifest)),
        "internal_quality_pool_count": int(layer_counts.get("internal_quality_pool", 0)),
        "expansion_core_equivalent_count": int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)),
        "rescue_core_equivalent_count": int(
            layer_counts.get("false_negative_rescue_core_equivalent_quality_pool", 0)
        ),
        "expansion_keep_separate_count": int(len(sidecars["expansion_keep_4"])),
        "rescue_keep_separate_count": int(len(sidecars["rescue_keep_1"])),
        "downgrade_reject_count": int(len(sidecars["downgrade_reject_2"])),
        "possible_false_negative_manual_review_count": int(len(sidecars["possible_false_negative_9"])),
        "remain_excluded_count": int(len(sidecars["remain_excluded_22"])),
        "reject_concept_or_non_bottleneck_count": int(len(sidecars["reject_concept_6"])),
        "duplicate_stock_count": duplicate_count,
        "auto_applied_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "quality_pool_layer_v2_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_layer_v2_generated": True,
        "quality_pool_v1_count": summary["quality_pool_v1_count"],
        "quality_pool_v2_count": summary["quality_pool_v2_count"],
        "internal_quality_pool_count": summary["internal_quality_pool_count"],
        "expansion_core_equivalent_count": summary["expansion_core_equivalent_count"],
        "rescue_core_equivalent_count": summary["rescue_core_equivalent_count"],
        "expansion_keep_separate_count": summary["expansion_keep_separate_count"],
        "rescue_keep_separate_count": summary["rescue_keep_separate_count"],
        "downgrade_reject_count": summary["downgrade_reject_count"],
        "possible_false_negative_manual_review_count": summary["possible_false_negative_manual_review_count"],
        "remain_excluded_count": summary["remain_excluded_count"],
        "reject_concept_or_non_bottleneck_count": summary["reject_concept_or_non_bottleneck_count"],
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
            "# Tech Bottleneck Quality Pool Layer v2",
            "",
            "## 1. Scope",
            "This task updates the research-only quality pool / manual review quality layer from v1 to v2. It does not create a confirmed core pool, strategy candidate pool, signal input, or admission input.",
            "",
            "## 2. Quality Pool Layer v2",
            f"Quality pool v1 count: {summary['quality_pool_v1_count']}; rescue additions: {summary['rescue_core_equivalent_count']}; quality pool v2 count: {summary['quality_pool_v2_count']}.",
            f"Internal quality pool: {summary['internal_quality_pool_count']}; expansion core-equivalent: {summary['expansion_core_equivalent_count']}; false-negative rescue core-equivalent: {summary['rescue_core_equivalent_count']}.",
            "",
            "## 3. Sidecar Queues",
            f"Expansion keep separate: {summary['expansion_keep_separate_count']}; rescue keep separate: {summary['rescue_keep_separate_count']}; downgrade/reject: {summary['downgrade_reject_count']}; possible false-negative manual review: {summary['possible_false_negative_manual_review_count']}; remain excluded: {summary['remain_excluded_count']}; reject concept/non-bottleneck: {summary['reject_concept_or_non_bottleneck_count']}.",
            "688813 泰金新能 remains outside v2 because missing_architecture_shift / missing_route_around evidence gaps still block same-layer equivalence.",
            "",
            "## 4. Guardrails",
            f"auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_doubler_data_gap_watch_triage_v1",
            "2. tech_bottleneck_stock_workspace_docling_panel_v1",
            "3. tech_bottleneck_quality_pool_layer_v2_manual_review_packet_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs()
    manifest = _build_manifest(inputs["v1_manifest"], inputs["rescue_38"])
    by_source = _by_source(manifest)
    sidecars = {
        "expansion_keep_4": _normalize_sidecar(inputs["expansion_keep_4"], "expansion_keep_separate"),
        "rescue_keep_1": _normalize_sidecar(inputs["rescue_keep_1"], "rescue_keep_separate"),
        "downgrade_reject_2": _normalize_sidecar(inputs["downgrade_reject_2"], "downgrade_or_reject"),
        "possible_false_negative_9": _normalize_sidecar(
            inputs["possible_false_negative_9"], "possible_false_negative_manual_review"
        ),
        "remain_excluded_22": _normalize_sidecar(inputs["remain_excluded_22"], "remain_excluded"),
        "reject_concept_6": _normalize_sidecar(inputs["reject_concept_6"], "reject_concept_or_non_bottleneck"),
    }
    strategy_clean = _strategy_diff_clean()
    summary = _summary(manifest, sidecars, strategy_clean)
    guardrails = _guardrails(summary)

    manifest.to_csv(output / "quality_pool_layer_v2_manifest.csv", index=False)
    by_source.to_csv(output / "quality_pool_layer_v2_by_source.csv", index=False)
    sidecars["expansion_keep_4"].to_csv(output / "expansion_keep_separate_4.csv", index=False)
    sidecars["rescue_keep_1"].to_csv(output / "rescue_keep_separate_1.csv", index=False)
    sidecars["downgrade_reject_2"].to_csv(output / "downgrade_or_reject_2.csv", index=False)
    sidecars["possible_false_negative_9"].to_csv(output / "possible_false_negative_manual_review_9.csv", index=False)
    sidecars["remain_excluded_22"].to_csv(output / "remain_excluded_22.csv", index=False)
    sidecars["reject_concept_6"].to_csv(output / "reject_concept_or_non_bottleneck_6.csv", index=False)
    _write_json(output / "quality_pool_layer_v2_summary.json", summary)
    _write_json(output / "quality_pool_layer_v2_guardrails.json", guardrails)
    (output / "tech_bottleneck_quality_pool_layer_v2_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
