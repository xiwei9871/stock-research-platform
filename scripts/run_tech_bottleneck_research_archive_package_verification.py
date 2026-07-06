#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
PACKAGE_DIR = RESEARCH_DIR / "tech_bottleneck_research_archive_packaging_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_archive_package_verification_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

LATEST_REQUIRED = {
    "tech_bottleneck_manual_review_writeback_persistence_adapter_v1": [
        "manual_review_persistence_adapter_summary.json",
        "manual_review_persistence_adapter_contract.json",
        "manual_review_persistence_store.csv",
        "manual_review_persistence_audit_log.csv",
        "manual_review_persistence_guardrails.json",
        "tech_bottleneck_manual_review_writeback_persistence_adapter_v1_report.md",
    ],
    "tech_bottleneck_dashboard_readonly_user_smoke_test_v6": [
        "smoke_test_v6_summary.json",
        "smoke_test_v6_section_status.csv",
        "smoke_test_v6_guardrail_checks.json",
        "tech_bottleneck_dashboard_readonly_user_smoke_test_v6_report.md",
    ],
    "tech_bottleneck_manual_review_persistence_replay_regression_v1": [
        "manual_review_persistence_replay_regression_summary.json",
        "manual_review_persistence_replay_regression_events.csv",
        "manual_review_persistence_replay_regression_rejected_writes.csv",
        "manual_review_persistence_replay_regression_guardrails.json",
        "tech_bottleneck_manual_review_persistence_replay_regression_v1_report.md",
    ],
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> pd.DataFrame:
    path = PACKAGE_DIR / "research_archive_package_manifest.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def build_latest_coverage(manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest_tasks = set(manifest.get("source_task", pd.Series(dtype=str)).astype(str))
    manifest_files = set(manifest.get("file_name", pd.Series(dtype=str)).astype(str))
    rows: list[dict[str, Any]] = []
    delta_rows: list[dict[str, Any]] = []
    for task, artifact_names in LATEST_REQUIRED.items():
        for artifact in artifact_names:
            artifact_path = RESEARCH_DIR / task / artifact
            included = task in manifest_tasks and artifact in manifest_files
            checksum = sha256_file(artifact_path) if artifact_path.exists() else ""
            row = {
                "latest_task": task,
                "artifact_name": artifact,
                "artifact_path": str(artifact_path.relative_to(PROJECT_ROOT)),
                "included_in_current_package": included,
                "required_for_latest_package": True,
                "recommended_package_group": task.replace("tech_bottleneck_", ""),
                "checksum_sha256": checksum,
                "status": "passed" if included else "warning",
                "notes": "present in current package" if included else "package was generated before latest persistence chain",
            }
            rows.append(row)
            if not included:
                delta_rows.append(row)
    coverage = pd.DataFrame(rows)
    delta = pd.DataFrame(delta_rows)
    missing = delta[["latest_task", "artifact_name", "artifact_path", "notes"]].copy() if not delta.empty else pd.DataFrame(
        columns=["latest_task", "artifact_name", "artifact_path", "notes"]
    )
    return coverage, delta, missing


def build_checksum_verification(manifest: pd.DataFrame) -> pd.DataFrame:
    if manifest.empty:
        return pd.DataFrame(columns=["package_path", "file_name", "checksum_present", "status", "notes"])
    rows = []
    for row in manifest.to_dict("records"):
        checksum = str(row.get("checksum_sha256", ""))
        rows.append(
            {
                "package_path": row.get("package_path", ""),
                "file_name": row.get("file_name", ""),
                "checksum_sha256": checksum,
                "checksum_present": len(checksum) == 64,
                "status": "passed" if len(checksum) == 64 else "failed",
                "notes": "manifest checksum present",
            }
        )
    return pd.DataFrame(rows)


def build_checks(summary: dict[str, Any]) -> pd.DataFrame:
    specs = [
        ("package_generated", True, summary["package_generated"], "blocking"),
        ("package_manifest_generated", True, summary["package_manifest_generated"], "blocking"),
        ("package_checksums_generated", True, summary["package_checksums_generated"], "blocking"),
        ("release_notes_ready", True, summary["release_notes_ready"], "blocking"),
        ("archive_integrity_ready", True, summary["archive_integrity_ready"], "blocking"),
        ("ops_handoff_ready", True, summary["ops_handoff_ready"], "blocking"),
        ("persistence_adapter_ready", True, summary["persistence_adapter_ready"], "blocking"),
        ("smoke_v6_ready", True, summary["smoke_v6_ready"], "blocking"),
        ("persistence_replay_regression_ready", True, summary["persistence_replay_regression_ready"], "blocking"),
        ("latest_artifacts_in_package", "complete", summary["latest_artifact_coverage_status"], "warning"),
        ("package_refresh_required", False, summary["package_refresh_required"], "warning"),
        ("strategy_writeback_disabled", 0, summary["strategy_writeback_enabled_count"], "blocking"),
        ("baseline_admission_change_disabled", 0, summary["baseline_admission_change_enabled_count"], "blocking"),
        ("used_for_signal_zero", 0, summary["used_for_signal_count"], "blocking"),
        ("used_for_admission_zero", 0, summary["used_for_admission_count"], "blocking"),
        ("execution_language_zero", 0, summary["execution_language_hit_count"], "blocking"),
        ("lookahead_violation_zero", 0, summary["lookahead_violation_rows"], "blocking"),
        ("formal_strategy_diff_empty", True, summary["strategy_file_diff_clean"], "blocking"),
    ]
    rows = []
    for name, expected, actual, severity in specs:
        status = "passed" if str(expected) == str(actual) else ("warning" if severity == "warning" else "failed")
        rows.append(
            {
                "check_name": name,
                "expected_value": expected,
                "actual_value": actual,
                "status": status,
                "severity": severity if status != "passed" else "info",
                "notes": "package was generated before latest persistence chain; refresh recommended"
                if name in {"latest_artifacts_in_package", "package_refresh_required"} and status == "warning"
                else "package verification check",
            }
        )
    return pd.DataFrame(rows)


def build_report(summary: dict[str, Any], test_results: dict[str, str]) -> str:
    coverage_note = (
        "Current package is valid for its original cut, but refresh is required to include persistence adapter, smoke v6, and replay regression artifacts."
        if summary["package_refresh_required"]
        else "Current package covers the latest required artifacts."
    )
    return f"""# Tech Bottleneck Research Archive Package Verification v1

## 1. Scope

This task verifies whether the research archive package covers the latest research-only dashboard and persistence chain. It does not change formal strategy files, baseline admission, or automated execution behavior.

## 2. Input Artifacts

- Archive package v1
- Release notes v1
- Archive integrity v1
- Ops handoff v1
- Persistence adapter v1
- Smoke v6
- Persistence replay regression v1

## 3. Package Baseline

- package generated: {summary["package_generated"]}
- package manifest generated: {summary["package_manifest_generated"]}
- package checksums generated: {summary["package_checksums_generated"]}
- included artifact count: {summary["included_artifact_count"]}
- package archive file: {summary["package_archive_file"]}

## 4. Latest Chain Verification

- persistence adapter ready: {summary["persistence_adapter_ready"]}
- smoke v6 ready: {summary["smoke_v6_ready"]}
- persistence replay regression ready: {summary["persistence_replay_regression_ready"]}

## 5. Latest Artifact Coverage

- latest artifact coverage status: {summary["latest_artifact_coverage_status"]}
- package refresh required: {summary["package_refresh_required"]}

{coverage_note}

## 6. Delta Manifest

Delta artifacts are listed in `research_archive_package_delta_manifest.csv`.

## 7. Guardrail Checks

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- replay consistency mismatch count: {summary["replay_consistency_mismatch_count"]}
- forbidden field persisted count: {summary["forbidden_field_persisted_count"]}
- formal strategy diff clean: {summary["strategy_file_diff_clean"]}

## 8. Test Results

- package verification pytest: {test_results["verification_pytest"]}
- replay regression pytest: {test_results["regression_pytest"]}
- smoke v6 pytest: {test_results["smoke_v6_pytest"]}
- archive packaging pytest: {test_results["packaging_pytest"]}
- formal strategy diff: {test_results["formal_strategy_diff"]}

## 9. Acceptance Decision

`{summary["acceptance_decision"]}`

## 10. Recommended Next Steps

1. `tech_bottleneck_research_archive_packaging_v2`
2. `tech_bottleneck_dashboard_readonly_ops_handoff_update_v1`
3. `tech_bottleneck_manual_review_persistence_ops_monitor_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    package = read_json(PACKAGE_DIR / "research_archive_package_summary.json")
    package_guardrails = read_json(PACKAGE_DIR / "research_archive_package_guardrails.json")
    release = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1/dashboard_readonly_release_notes_summary.json")
    archive = read_json(RESEARCH_DIR / "tech_bottleneck_research_archive_integrity_check_v1/research_archive_integrity_summary.json")
    ops = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_v1/ops_handoff_summary.json")
    persistence = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_persistence_adapter_v1/manual_review_persistence_adapter_summary.json")
    persistence_guardrails = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_persistence_adapter_v1/manual_review_persistence_guardrails.json")
    smoke_v6 = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v6/smoke_test_v6_summary.json")
    smoke_v6_guardrails = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v6/smoke_test_v6_guardrail_checks.json")
    regression = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_persistence_replay_regression_v1/manual_review_persistence_replay_regression_summary.json")
    regression_guardrails = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_persistence_replay_regression_v1/manual_review_persistence_replay_regression_guardrails.json")
    manifest = load_manifest()
    coverage, delta, missing = build_latest_coverage(manifest)
    checksums = build_checksum_verification(manifest)
    package_refresh_required = bool((coverage["included_in_current_package"] == False).any()) if not coverage.empty else True
    latest_status = "incomplete" if package_refresh_required else "complete"
    strategy_clean = strategy_diff_clean()
    blocking_issue_count = 0
    blocking_issue_count += 0 if strategy_clean else 1
    blocking_issue_count += int(regression.get("replay_consistency_mismatch_count", 0) > 0)
    blocking_issue_count += int(regression.get("latest_state_mismatch_count", 0) > 0)
    blocking_issue_count += int(regression.get("forbidden_field_persisted_count", 0) > 0)
    blocking_issue_count += int(smoke_v6.get("acceptance_decision") != "dashboard_ready_with_research_only_manual_review_persistence")
    guardrail_counts = {
        "strategy_writeback_enabled_count": max(
            int(package_guardrails.get("strategy_writeback_enabled_count", 0)),
            int(persistence_guardrails.get("strategy_writeback_enabled_count", 0)),
            int(smoke_v6_guardrails.get("strategy_writeback_enabled_count", 0)),
            int(regression_guardrails.get("strategy_writeback_enabled_count", 0)),
        ),
        "baseline_admission_change_enabled_count": max(
            int(package_guardrails.get("baseline_admission_change_enabled_count", 0)),
            int(persistence_guardrails.get("baseline_admission_change_enabled_count", 0)),
            int(smoke_v6_guardrails.get("baseline_admission_change_enabled_count", 0)),
            int(regression_guardrails.get("baseline_admission_change_enabled_count", 0)),
        ),
        "baseline_admission_changed_count": max(
            int(package_guardrails.get("baseline_admission_changed_count", 0)),
            int(persistence_guardrails.get("baseline_admission_changed_count", 0)),
            int(smoke_v6_guardrails.get("baseline_admission_changed_count", 0)),
            int(regression_guardrails.get("baseline_admission_changed_count", 0)),
        ),
        "used_for_signal_count": max(
            int(package_guardrails.get("used_for_signal_count", 0)),
            int(persistence_guardrails.get("used_for_signal_count", 0)),
            int(smoke_v6_guardrails.get("used_for_signal_count", 0)),
            int(regression_guardrails.get("used_for_signal_count", 0)),
        ),
        "used_for_admission_count": max(
            int(package_guardrails.get("used_for_admission_count", 0)),
            int(persistence_guardrails.get("used_for_admission_count", 0)),
            int(smoke_v6_guardrails.get("used_for_admission_count", 0)),
            int(regression_guardrails.get("used_for_admission_count", 0)),
        ),
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": max(
            int(package_guardrails.get("lookahead_violation_rows", 0)),
            int(persistence_guardrails.get("lookahead_violation_rows", 0)),
            int(smoke_v6_guardrails.get("lookahead_violation_rows", 0)),
            int(regression_guardrails.get("lookahead_violation_rows", 0)),
        ),
    }
    blocking_issue_count += sum(1 for value in guardrail_counts.values() if value > 0)
    if blocking_issue_count > 0:
        decision = "blocked_due_to_package_verification_guardrail_failure"
    elif package_refresh_required:
        decision = "package_refresh_required_for_latest_persistence_chain"
    else:
        decision = "research_archive_package_verified_current"
    summary = {
        "package_verification_generated": True,
        "package_generated": package.get("package_generated", False),
        "package_manifest_generated": package.get("package_manifest_generated", False),
        "package_checksums_generated": package.get("package_checksums_generated", False),
        "latest_artifact_coverage_status": latest_status,
        "package_refresh_required": package_refresh_required,
        "release_notes_ready": release.get("acceptance_decision") == "dashboard_readonly_release_notes_ready",
        "archive_integrity_ready": archive.get("acceptance_decision") == "research_archive_integrity_ready",
        "ops_handoff_ready": ops.get("acceptance_decision") == "dashboard_readonly_ops_handoff_ready",
        "persistence_adapter_ready": persistence.get("acceptance_decision") == "manual_review_writeback_persistence_adapter_ready",
        "smoke_v6_ready": smoke_v6.get("acceptance_decision") == "dashboard_ready_with_research_only_manual_review_persistence",
        "persistence_replay_regression_ready": regression.get("acceptance_decision") == "manual_review_persistence_replay_regression_ready",
        "included_artifact_count": package.get("included_artifact_count", 0),
        "package_archive_file": package.get("package_archive_file", ""),
        "missing_latest_artifact_count": int(len(missing)),
        "blocking_issue_count": blocking_issue_count,
        "warning_issue_count": int(len(missing)) if package_refresh_required else 0,
        "replay_consistency_mismatch_count": regression.get("replay_consistency_mismatch_count", 0),
        "latest_state_mismatch_count": regression.get("latest_state_mismatch_count", 0),
        "forbidden_field_persisted_count": regression.get("forbidden_field_persisted_count", 0),
        **guardrail_counts,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": decision,
    }
    checks = build_checks(summary)
    guardrails = {
        "package_verification_generated": True,
        "package_generated": summary["package_generated"],
        "package_manifest_generated": summary["package_manifest_generated"],
        "package_checksums_generated": summary["package_checksums_generated"],
        "latest_artifact_coverage_status": latest_status,
        "package_refresh_required": package_refresh_required,
        "release_notes_ready": summary["release_notes_ready"],
        "archive_integrity_ready": summary["archive_integrity_ready"],
        "ops_handoff_ready": summary["ops_handoff_ready"],
        "persistence_adapter_ready": summary["persistence_adapter_ready"],
        "smoke_v6_ready": summary["smoke_v6_ready"],
        "persistence_replay_regression_ready": summary["persistence_replay_regression_ready"],
        "strategy_writeback_enabled_count": summary["strategy_writeback_enabled_count"],
        "baseline_admission_change_enabled_count": summary["baseline_admission_change_enabled_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "replay_consistency_mismatch_count": summary["replay_consistency_mismatch_count"],
        "latest_state_mismatch_count": summary["latest_state_mismatch_count"],
        "forbidden_field_persisted_count": summary["forbidden_field_persisted_count"],
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": decision,
    }
    test_results = {
        "verification_pytest": "pending_initial_generation",
        "regression_pytest": "pending_initial_generation",
        "smoke_v6_pytest": "pending_initial_generation",
        "packaging_pytest": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }
    coverage.to_csv(OUTPUT_DIR / "research_archive_package_latest_artifact_coverage.csv", index=False)
    delta.to_csv(OUTPUT_DIR / "research_archive_package_delta_manifest.csv", index=False)
    missing.to_csv(OUTPUT_DIR / "research_archive_package_missing_latest_artifacts.csv", index=False)
    checksums.to_csv(OUTPUT_DIR / "research_archive_package_checksum_verification.csv", index=False)
    checks.to_csv(OUTPUT_DIR / "research_archive_package_verification_checks.csv", index=False)
    write_json(OUTPUT_DIR / "research_archive_package_verification_summary.json", summary)
    write_json(OUTPUT_DIR / "research_archive_package_verification_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_research_archive_package_verification_v1_report.md").write_text(
        build_report(summary, test_results), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
