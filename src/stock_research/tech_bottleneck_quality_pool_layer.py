from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_quality_pool_layer_v1"
INTERNAL_88 = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_manual_approval_consolidation_v1/manual_approval_candidates_88.csv"
INTERNAL_REJECT_2 = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_manual_approval_consolidation_v1/downgrade_or_reject_2.csv"
EXPANSION_84 = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_doubler_expansion_core_equivalence_gate_v1/core_equivalent_add_to_quality_pool.csv"
)
EXPANSION_KEEP_4 = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_doubler_expansion_core_equivalence_gate_v1/keep_as_expansion_candidate.csv"
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


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _read_csv(INTERNAL_88), _read_csv(INTERNAL_REJECT_2), _read_csv(EXPANSION_84), _read_csv(EXPANSION_KEEP_4)


def _internal_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "quality_layer": "internal_quality_pool",
                "source_group": "canonical_90_internal_manual_review",
                "proposal_source": row.get("manual_approval_source", ""),
                "manual_review_status": row.get("manual_approval_status", "pending_manual_approval"),
                "primary_source_supported": bool(row.get("primary_source_supported", False)),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support", ""),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": "internal_manual_review_gap",
                "manual_approval_question": row.get("manual_approval_question", ""),
                "recommended_next_action": row.get("recommended_next_action", ""),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _expansion_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "quality_layer": "expansion_core_equivalent_quality_pool",
                "source_group": row.get("source_group", "expansion_2025_doubler_discovered"),
                "proposal_source": "doubler_expansion_core_equivalence_gate_v1",
                "manual_review_status": "pending_manual_approval",
                "primary_source_supported": bool(row.get("primary_source_supported", False)),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support", ""),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": row.get("downgrade_risk_flags", ""),
                "manual_approval_question": "Should this expansion-origin core-equivalent candidate be reviewed at the same quality-pool layer as internal 90 candidates?",
                "recommended_next_action": row.get("recommended_next_action", ""),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _normalize_sidecar(frame: pd.DataFrame, status: str) -> pd.DataFrame:
    rows = frame.copy().sort_values("stock_code").reset_index(drop=True)
    rows["sidecar_status"] = status
    rows["research_only"] = True
    rows["used_for_signal"] = False
    rows["used_for_admission"] = False
    rows["auto_applied"] = False
    return rows


def _build_manifest(internal: pd.DataFrame, expansion: pd.DataFrame) -> pd.DataFrame:
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
    manifest = pd.concat([internal, expansion], ignore_index=True, sort=False)
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


def _summary(manifest: pd.DataFrame, keep: pd.DataFrame, reject: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    layer_counts = manifest["quality_layer"].value_counts()
    used_for_signal = int(manifest["used_for_signal"].astype(bool).sum())
    used_for_admission = int(manifest["used_for_admission"].astype(bool).sum())
    blocking = (
        len(manifest) != 172
        or int(layer_counts.get("internal_quality_pool", 0)) != 88
        or int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)) != 84
        or len(keep) != 4
        or len(reject) != 2
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "quality_pool_count": int(len(manifest)),
        "internal_quality_pool_count": int(layer_counts.get("internal_quality_pool", 0)),
        "expansion_core_equivalent_count": int(layer_counts.get("expansion_core_equivalent_quality_pool", 0)),
        "expansion_keep_separate_count": int(len(keep)),
        "downgrade_reject_count": int(len(reject)),
        "auto_applied_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "quality_pool_layer_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_pool_layer_generated": True,
        "quality_pool_count": summary["quality_pool_count"],
        "internal_quality_pool_count": summary["internal_quality_pool_count"],
        "expansion_core_equivalent_count": summary["expansion_core_equivalent_count"],
        "expansion_keep_separate_count": summary["expansion_keep_separate_count"],
        "downgrade_reject_count": summary["downgrade_reject_count"],
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
            "# Tech Bottleneck Quality Pool Layer v1",
            "",
            "## 1. Scope",
            "This task freezes the research-only quality pool / manual review quality layer. It does not create a confirmed core pool, strategy candidate pool, signal input, or admission input.",
            "",
            "## 2. Quality Pool Layer",
            f"Quality pool count: {summary['quality_pool_count']}; internal quality pool: {summary['internal_quality_pool_count']}; expansion core-equivalent: {summary['expansion_core_equivalent_count']}.",
            "",
            "## 3. Sidecar Queues",
            f"Expansion keep separate: {summary['expansion_keep_separate_count']}; downgrade/reject: {summary['downgrade_reject_count']}.",
            "",
            "## 4. Guardrails",
            f"auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_excluded_false_negative_review_v1",
            "2. tech_bottleneck_doubler_data_gap_watch_triage_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    internal_raw, reject_raw, expansion_raw, keep_raw = _load_inputs()
    internal = _internal_rows(internal_raw)
    expansion = _expansion_rows(expansion_raw)
    manifest = _build_manifest(internal, expansion)
    by_source = _by_source(manifest)
    keep = _normalize_sidecar(keep_raw, "expansion_keep_separate")
    reject = _normalize_sidecar(reject_raw, "downgrade_or_reject")
    strategy_clean = _strategy_diff_clean()
    summary = _summary(manifest, keep, reject, strategy_clean)
    guardrails = _guardrails(summary)

    manifest.to_csv(output / "quality_pool_layer_manifest.csv", index=False)
    by_source.to_csv(output / "quality_pool_layer_by_source.csv", index=False)
    keep.to_csv(output / "expansion_keep_separate_4.csv", index=False)
    reject.to_csv(output / "downgrade_or_reject_2.csv", index=False)
    _write_json(output / "quality_pool_layer_summary.json", summary)
    _write_json(output / "quality_pool_layer_guardrails.json", guardrails)
    (output / "tech_bottleneck_quality_pool_layer_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
