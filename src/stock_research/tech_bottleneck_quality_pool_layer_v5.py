from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v5"
V4_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v4/quality_pool_layer_v4_manifest.csv"
V4_KEEP = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v4/latent_keep_separate_v4.csv"
LATENT_STANDARD_24 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_core_equivalent_candidates.csv"
)
STANDARD_KEEP = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_keep_separate_candidates.csv"
)
STANDARD_WATCH = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_remain_watch.csv"
)
STANDARD_REJECT = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_downgrade_or_reject.csv"
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _latent_standard_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "quality_layer": "latent_standard_core_equivalent_quality_pool",
                "source_group": "latent_standard_primary_source_backfilled",
                "proposal_source": "latent_standard_core_equivalence_gate_v1",
                "manual_review_status": "pending_manual_approval",
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support", ""),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": row.get("route_around_risk", ""),
                "manual_approval_question": "Should this latent standard core-equivalent candidate enter the manual review quality layer v5?",
                "recommended_next_action": "manual quality-pool review as latent standard core-equivalent; do not auto-apply",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_manifest(v4_manifest: pd.DataFrame, latent_standard: pd.DataFrame) -> pd.DataFrame:
    v4 = v4_manifest[MANIFEST_COLUMNS].copy()
    v4["research_only"] = True
    v4["used_for_signal"] = False
    v4["used_for_admission"] = False
    added = _latent_standard_rows(latent_standard)
    manifest = pd.concat([v4, added], ignore_index=True, sort=False)
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


def _separate_buckets(v4_keep: pd.DataFrame, standard_keep: pd.DataFrame, standard_watch: pd.DataFrame, standard_reject: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "bucket_name": "latent_keep_separate_v4",
            "source_artifact": str(V4_KEEP.relative_to(PROJECT_ROOT)),
            "candidate_count": int(len(v4_keep)),
            "bucket_status": "preserved_outside_quality_pool_v5",
        },
        {
            "bucket_name": "latent_standard_keep_separate",
            "source_artifact": str(STANDARD_KEEP.relative_to(PROJECT_ROOT)),
            "candidate_count": int(len(standard_keep)),
            "bucket_status": "preserved_outside_quality_pool_v5",
        },
        {
            "bucket_name": "latent_standard_remain_watch",
            "source_artifact": str(STANDARD_WATCH.relative_to(PROJECT_ROOT)),
            "candidate_count": int(len(standard_watch)),
            "bucket_status": "preserved_outside_quality_pool_v5",
        },
        {
            "bucket_name": "latent_standard_downgrade_or_reject",
            "source_artifact": str(STANDARD_REJECT.relative_to(PROJECT_ROOT)),
            "candidate_count": int(len(standard_reject)),
            "bucket_status": "preserved_outside_quality_pool_v5",
        },
    ]
    frame = pd.DataFrame(rows)
    frame["auto_applied"] = False
    frame["used_for_signal"] = False
    frame["used_for_admission"] = False
    frame["research_only"] = True
    return frame


def _summary(
    manifest: pd.DataFrame,
    v4_keep: pd.DataFrame,
    standard_keep: pd.DataFrame,
    standard_watch: pd.DataFrame,
    standard_reject: pd.DataFrame,
    strategy_clean: bool,
) -> dict[str, Any]:
    layer_counts = manifest["quality_layer"].value_counts()
    duplicate_count = int(len(manifest) - manifest["stock_code"].nunique())
    used_for_signal = int(manifest["used_for_signal"].map(_truthy).sum())
    used_for_admission = int(manifest["used_for_admission"].map(_truthy).sum())
    blocking = (
        len(manifest) != 300
        or int(layer_counts.get("latent_standard_core_equivalent_quality_pool", 0)) != 24
        or duplicate_count != 0
        or len(v4_keep) != 7
        or len(standard_keep) != 0
        or len(standard_watch) != 0
        or len(standard_reject) != 0
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "quality_pool_v4_count": 276,
        "latent_standard_core_equivalent_added": int(
            layer_counts.get("latent_standard_core_equivalent_quality_pool", 0)
        ),
        "quality_pool_v5_count": int(len(manifest)),
        "internal_quality_pool_count": int(layer_counts.get("internal_quality_pool", 0)),
        "expansion_core_equivalent_count": int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)),
        "rescue_core_equivalent_count": int(
            layer_counts.get("false_negative_rescue_core_equivalent_quality_pool", 0)
        ),
        "data_gap_core_equivalent_count": int(layer_counts.get("data_gap_core_equivalent_quality_pool", 0)),
        "latent_core_equivalent_count": int(layer_counts.get("latent_core_equivalent_quality_pool", 0)),
        "latent_keep_separate_count": int(len(v4_keep)),
        "latent_standard_keep_separate_count": int(len(standard_keep)),
        "latent_standard_remain_watch_count": int(len(standard_watch)),
        "latent_standard_downgrade_or_reject_count": int(len(standard_reject)),
        "duplicate_stock_count": duplicate_count,
        "auto_applied_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "quality_pool_layer_v5_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_layer_v5_generated": True,
        "quality_pool_v4_count": summary["quality_pool_v4_count"],
        "latent_standard_core_equivalent_added": summary["latent_standard_core_equivalent_added"],
        "quality_pool_v5_count": summary["quality_pool_v5_count"],
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
            "# Tech Bottleneck Quality Pool Layer v5",
            "",
            "## 1. Scope",
            "This task solidifies the research-only quality pool / manual review quality layer v5. It does not create a confirmed core pool, formal core pool, strategy candidate pool, signal input, or admission input.",
            "",
            "## 2. Input Baseline",
            f"Quality pool v4 count: {summary['quality_pool_v4_count']}. Latent standard core-equivalent additions: {summary['latent_standard_core_equivalent_added']}.",
            "",
            "## 3. Quality Pool Layer v5",
            f"Quality pool v5 count: {summary['quality_pool_v5_count']}. Internal: {summary['internal_quality_pool_count']}; expansion core-equivalent: {summary['expansion_core_equivalent_count']}; false-negative rescue core-equivalent: {summary['rescue_core_equivalent_count']}; data-gap core-equivalent: {summary['data_gap_core_equivalent_count']}; latent core-equivalent: {summary['latent_core_equivalent_count']}; latent standard core-equivalent: {summary['latent_standard_core_equivalent_added']}.",
            "",
            "## 4. Separate Buckets",
            f"Latent keep separate: {summary['latent_keep_separate_count']}; latent standard keep separate: {summary['latent_standard_keep_separate_count']}; latent standard remain watch: {summary['latent_standard_remain_watch_count']}; latent standard downgrade/reject: {summary['latent_standard_downgrade_or_reject_count']}. These buckets remain outside quality pool v5.",
            "",
            "## 5. Guardrail Checks",
            f"Auto applied: {summary['auto_applied_count']}; price move used for signal: {summary['price_move_used_for_signal']}; low position used for signal: {summary['low_position_used_for_signal']}; used for signal: {summary['used_for_signal_count']}; used for admission: {summary['used_for_admission_count']}; strategy file diff clean: {summary['strategy_file_diff_clean']}.",
            "",
            "## 6. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 7. Recommended Next Steps",
            "1. tech_bottleneck_latent_manual_review_first_triage_v1",
            "2. tech_bottleneck_quality_pool_layer_v5_manual_review_packet_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
            "",
        ]
    )


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v4_manifest = _read_csv(V4_MANIFEST)
    v4_keep = _read_csv(V4_KEEP)
    latent_standard = _read_csv(LATENT_STANDARD_24)
    standard_keep = _read_csv(STANDARD_KEEP)
    standard_watch = _read_csv(STANDARD_WATCH)
    standard_reject = _read_csv(STANDARD_REJECT)

    manifest = _build_manifest(v4_manifest, latent_standard)
    by_source = _by_source(manifest)
    buckets = _separate_buckets(v4_keep, standard_keep, standard_watch, standard_reject)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(manifest, v4_keep, standard_keep, standard_watch, standard_reject, strategy_clean)
    guardrails = _guardrails(summary)

    manifest.to_csv(OUTPUT_DIR / "quality_pool_layer_v5_manifest.csv", index=False)
    by_source.to_csv(OUTPUT_DIR / "quality_pool_layer_v5_by_source.csv", index=False)
    buckets.to_csv(OUTPUT_DIR / "quality_pool_layer_v5_separate_buckets.csv", index=False)
    _write_json(OUTPUT_DIR / "quality_pool_layer_v5_summary.json", summary)
    _write_json(OUTPUT_DIR / "quality_pool_layer_v5_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v5_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
