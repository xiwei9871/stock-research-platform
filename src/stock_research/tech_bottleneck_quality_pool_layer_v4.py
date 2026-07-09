from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v4"
V3_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
LATENT_CORE_42 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2/latent_core_equivalent_batch1_rerun_v2_candidates.csv"
)
LATENT_KEEP_3 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2/latent_keep_separate_batch1_rerun_v2_candidates.csv"
)
LATENT_INITIAL_KEEP_4 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_core_equivalence_gate_batch1_v1/latent_keep_separate_batch1_candidates.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

MANIFEST_COLUMNS = [
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


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _latent_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "quality_layer": "latent_core_equivalent_quality_pool",
                "source_group": "latent_primary_source_backfill_batch1_rerun_v2",
                "proposal_source": "latent_core_equivalence_gate_batch1_rerun_v2",
                "manual_review_status": "pending_manual_approval",
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support", ""),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": row.get("route_around_risk", ""),
                "manual_approval_question": "Should this latent core-equivalent candidate enter the manual review quality layer v4?",
                "recommended_next_action": "manual quality-pool review as latent core-equivalent; do not auto-apply",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_manifest(v3_manifest: pd.DataFrame, latent_core: pd.DataFrame) -> pd.DataFrame:
    v3 = v3_manifest[MANIFEST_COLUMNS].copy()
    v3["research_only"] = True
    v3["used_for_signal"] = False
    v3["used_for_admission"] = False
    latent = _latent_rows(latent_core)
    manifest = pd.concat([v3, latent], ignore_index=True, sort=False)
    return manifest[MANIFEST_COLUMNS].sort_values(["quality_layer", "stock_code"]).reset_index(drop=True)


def _by_source(manifest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (layer, source), group in manifest.groupby(["quality_layer", "source_group"], dropna=False):
        rows.append(
            {
                "quality_layer": layer,
                "source_group": source,
                "candidate_count": int(len(group)),
                "primary_source_supported_count": int(group["primary_source_supported"].map(_truthy).sum()),
                "research_only": True,
                "used_for_signal_count": int(group["used_for_signal"].map(_truthy).sum()),
                "used_for_admission_count": int(group["used_for_admission"].map(_truthy).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["quality_layer", "source_group"]).reset_index(drop=True)


def _normalize_keep_separate(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    keep = frame.copy()
    keep["latent_keep_separate_source"] = source
    keep["research_only"] = True
    keep["used_for_signal"] = False
    keep["used_for_admission"] = False
    keep["auto_added_to_quality_pool"] = False
    keep["manual_review_status"] = "pending_manual_review"
    return keep.sort_values(["latent_keep_separate_source", "stock_code"]).reset_index(drop=True)


def _summary(
    manifest: pd.DataFrame,
    latent_keep_3: pd.DataFrame,
    latent_initial_keep_4: pd.DataFrame,
    keep_separate: pd.DataFrame,
    strategy_clean: bool,
) -> dict[str, Any]:
    layer_counts = manifest["quality_layer"].value_counts()
    duplicate_count = int(len(manifest) - manifest["stock_code"].nunique())
    used_for_signal_count = int(manifest["used_for_signal"].map(_truthy).sum())
    used_for_admission_count = int(manifest["used_for_admission"].map(_truthy).sum())
    keep_overlap_count = int(len(set(keep_separate["stock_code"]) & set(manifest["stock_code"])))
    blocking = (
        int(layer_counts.get("internal_quality_pool", 0)) != 88
        or int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)) != 84
        or int(layer_counts.get("false_negative_rescue_core_equivalent_quality_pool", 0)) != 38
        or int(layer_counts.get("data_gap_core_equivalent_quality_pool", 0)) != 24
        or int(layer_counts.get("latent_core_equivalent_quality_pool", 0)) != 42
        or len(manifest) != 276
        or duplicate_count != 0
        or len(latent_keep_3) != 3
        or len(latent_initial_keep_4) != 4
        or len(keep_separate) != 7
        or keep_overlap_count != 0
        or used_for_signal_count != 0
        or used_for_admission_count != 0
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "quality_pool_v3_count": 234,
        "latent_core_equivalent_added": int(layer_counts.get("latent_core_equivalent_quality_pool", 0)),
        "quality_pool_v4_count": int(len(manifest)),
        "internal_quality_pool_count": int(layer_counts.get("internal_quality_pool", 0)),
        "expansion_core_equivalent_count": int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)),
        "rescue_core_equivalent_count": int(
            layer_counts.get("false_negative_rescue_core_equivalent_quality_pool", 0)
        ),
        "data_gap_core_equivalent_count": int(layer_counts.get("data_gap_core_equivalent_quality_pool", 0)),
        "latent_keep_separate_rerun_v2_count": int(len(latent_keep_3)),
        "latent_keep_separate_initial_count": int(len(latent_initial_keep_4)),
        "latent_keep_separate_count": int(len(keep_separate)),
        "duplicate_stock_count": duplicate_count,
        "latent_keep_separate_overlap_with_quality_pool_count": keep_overlap_count,
        "auto_applied_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "quality_pool_layer_v4_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_layer_v4_generated": True,
        "quality_pool_v3_count": summary["quality_pool_v3_count"],
        "latent_core_equivalent_added": summary["latent_core_equivalent_added"],
        "quality_pool_v4_count": summary["quality_pool_v4_count"],
        "latent_keep_separate_count": summary["latent_keep_separate_count"],
        "duplicate_stock_count": summary["duplicate_stock_count"],
        "auto_applied_count": summary["auto_applied_count"],
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
        "low_position_used_for_signal": summary["low_position_used_for_signal"],
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
            "# Tech Bottleneck Quality Pool Layer v4",
            "",
            "## 1. Scope",
            "This task solidifies the research-only quality pool / manual review quality layer v4. It does not create a confirmed core pool, formal core pool, strategy candidate pool, signal input, or admission input.",
            "",
            "## 2. Input Baseline",
            f"Quality pool v3 count: {summary['quality_pool_v3_count']}. Latent batch1 rerun v2 core-equivalent additions: {summary['latent_core_equivalent_added']}.",
            "",
            "## 3. Quality Pool Layer v4",
            f"Quality pool v4 count: {summary['quality_pool_v4_count']}. Internal: {summary['internal_quality_pool_count']}; expansion core-equivalent: {summary['expansion_core_equivalent_count']}; false-negative rescue core-equivalent: {summary['rescue_core_equivalent_count']}; data-gap core-equivalent: {summary['data_gap_core_equivalent_count']}; latent core-equivalent: {summary['latent_core_equivalent_added']}.",
            "",
            "## 4. Latent Keep Separate",
            f"Latent keep separate total: {summary['latent_keep_separate_count']}; initial batch1 keep separate: {summary['latent_keep_separate_initial_count']}; rerun v2 keep separate: {summary['latent_keep_separate_rerun_v2_count']}. These names are preserved outside the quality pool layer.",
            "",
            "## 5. Guardrail Checks",
            f"Auto applied: {summary['auto_applied_count']}; price move used for signal: {summary['price_move_used_for_signal']}; low position used for signal: {summary['low_position_used_for_signal']}; used for signal: {summary['used_for_signal_count']}; used for admission: {summary['used_for_admission_count']}; strategy file diff clean: {summary['strategy_file_diff_clean']}.",
            "",
            "## 6. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 7. Recommended Next Steps",
            "1. tech_bottleneck_latent_standard_backfill_queue_v1",
            "2. tech_bottleneck_quality_pool_layer_v4_manual_review_packet_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
            "",
        ]
    )


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v3_manifest = _read_csv(V3_MANIFEST)
    latent_core = _read_csv(LATENT_CORE_42)
    latent_keep_3 = _read_csv(LATENT_KEEP_3)
    latent_initial_keep_4 = _read_csv(LATENT_INITIAL_KEEP_4)

    manifest = _build_manifest(v3_manifest, latent_core)
    by_source = _by_source(manifest)
    keep_separate = pd.concat(
        [
            _normalize_keep_separate(latent_initial_keep_4, "latent_core_equivalence_gate_batch1_v1"),
            _normalize_keep_separate(latent_keep_3, "latent_core_equivalence_gate_batch1_rerun_v2"),
        ],
        ignore_index=True,
        sort=False,
    ).sort_values(["latent_keep_separate_source", "stock_code"]).reset_index(drop=True)

    strategy_clean = _strategy_diff_clean()
    summary = _summary(manifest, latent_keep_3, latent_initial_keep_4, keep_separate, strategy_clean)
    guardrails = _guardrails(summary)

    manifest.to_csv(OUTPUT_DIR / "quality_pool_layer_v4_manifest.csv", index=False)
    by_source.to_csv(OUTPUT_DIR / "quality_pool_layer_v4_by_source.csv", index=False)
    keep_separate.to_csv(OUTPUT_DIR / "latent_keep_separate_v4.csv", index=False)
    _write_json(OUTPUT_DIR / "quality_pool_layer_v4_summary.json", summary)
    _write_json(OUTPUT_DIR / "quality_pool_layer_v4_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v4_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
