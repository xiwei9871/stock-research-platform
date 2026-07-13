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
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_archive_integrity_check_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

REQUIRED_TASKS = [
    "tech_bottleneck_watchlist_report_consolidated_v1",
    "tech_bottleneck_watchlist_dashboard_readonly_v1",
    "tech_bottleneck_dashboard_readonly_ui_enhancement_v1",
    "tech_bottleneck_dashboard_readonly_user_smoke_test_v2",
    "tech_bottleneck_full_financial_statement_source_adapter_v1",
    "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1",
    "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1",
    "tech_bottleneck_dashboard_readonly_user_smoke_test_v3",
    "tech_bottleneck_news_source_mapping_v1",
    "tech_bottleneck_watchlist_report_news_patch_v1",
    "tech_bottleneck_dashboard_readonly_news_patch_v1",
    "tech_bottleneck_dashboard_readonly_user_smoke_test_v4",
    "tech_bottleneck_manual_review_writeback_research_only_v1",
    "tech_bottleneck_dashboard_readonly_user_smoke_test_v5",
    "tech_bottleneck_manual_review_writeback_audit_replay_v1",
    "tech_bottleneck_announcement_source_ingestion_v1",
    "tech_bottleneck_announcement_fulltext_extraction_v2",
    "tech_bottleneck_fundamental_source_adapter_v1",
    "tech_bottleneck_baostock_pe_pb_ps_source_adapter_v1",
    "tech_bottleneck_research_selection_layer_v2_generator_v1",
    "tech_bottleneck_manual_review_label_schema_v1",
    "tech_bottleneck_manual_review_template_v1",
]

LATEST_BLOCKING_TASKS = {
    "tech_bottleneck_dashboard_readonly_user_smoke_test_v5",
    "tech_bottleneck_manual_review_writeback_research_only_v1",
    "tech_bottleneck_manual_review_writeback_audit_replay_v1",
}

REQUIRED_FILES = {
    "tech_bottleneck_dashboard_readonly_user_smoke_test_v5": [
        "smoke_test_v5_summary.json",
        "smoke_test_v5_guardrail_checks.json",
        "tech_bottleneck_dashboard_readonly_user_smoke_test_v5_report.md",
    ],
    "tech_bottleneck_manual_review_writeback_research_only_v1": [
        "manual_review_writeback_summary.json",
        "manual_review_writeback_guardrails.json",
        "manual_review_writeback_store_template.csv",
        "manual_review_writeback_schema.json",
    ],
    "tech_bottleneck_manual_review_writeback_audit_replay_v1": [
        "manual_review_writeback_audit_replay_summary.json",
        "manual_review_writeback_audit_replay_guardrails.json",
        "manual_review_writeback_audit_replay_consistency_checks.csv",
    ],
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


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


def classify_file(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".json") and ("summary" in name or "guardrail" in name):
        return "summary_or_guardrail"
    if name.endswith(".md") and ("report" in name or "v1" in name):
        return "markdown_report"
    if name.endswith(".csv"):
        return "csv_data"
    if name.endswith(".json"):
        return "json_data"
    return "other"


def discover_tasks() -> list[Path]:
    return sorted(path for path in RESEARCH_DIR.glob("tech_bottleneck_*") if path.is_dir())


def build_manifest(tasks: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for task_dir in tasks:
        for file_path in sorted(path for path in task_dir.rglob("*") if path.is_file()):
            rel = file_path.relative_to(PROJECT_ROOT)
            rows.append(
                {
                    "task_name": task_dir.name,
                    "file_path": str(rel),
                    "file_name": file_path.name,
                    "file_type": file_path.suffix.lower().lstrip(".") or "none",
                    "artifact_role": classify_file(file_path),
                    "size_bytes": file_path.stat().st_size,
                    "required_task": task_dir.name in REQUIRED_TASKS,
                    "latest_blocking_task": task_dir.name in LATEST_BLOCKING_TASKS,
                }
            )
    return pd.DataFrame(rows)


def build_checksums(manifest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if manifest.empty:
        return pd.DataFrame(columns=["task_name", "file_path", "sha256", "size_bytes"])
    for row in manifest.itertuples(index=False):
        path = PROJECT_ROOT / row.file_path
        if row.artifact_role in {"summary_or_guardrail", "markdown_report", "csv_data", "json_data"}:
            rows.append(
                {
                    "task_name": row.task_name,
                    "file_path": row.file_path,
                    "sha256": sha256_file(path),
                    "size_bytes": row.size_bytes,
                }
            )
    return pd.DataFrame(rows)


def build_required_checks(tasks: list[Path]) -> pd.DataFrame:
    discovered = {path.name for path in tasks}
    rows: list[dict[str, Any]] = []
    for task in REQUIRED_TASKS:
        exists = task in discovered
        severity = "blocking" if task in LATEST_BLOCKING_TASKS else "warning"
        rows.append(
            {
                "task_name": task,
                "artifact_name": "__task_directory__",
                "artifact_path": str(RESEARCH_DIR / task),
                "required": True,
                "exists": exists,
                "severity": severity,
                "status": "passed" if exists else ("failed" if severity == "blocking" else "warning"),
                "notes": "required task directory",
            }
        )
        for file_name in REQUIRED_FILES.get(task, []):
            path = RESEARCH_DIR / task / file_name
            file_exists = path.exists()
            rows.append(
                {
                    "task_name": task,
                    "artifact_name": file_name,
                    "artifact_path": str(path),
                    "required": True,
                    "exists": file_exists,
                    "severity": "blocking",
                    "status": "passed" if file_exists else "failed",
                    "notes": "latest chain required artifact",
                }
            )
    return pd.DataFrame(rows)


def metric_row(metric: str, expected: Any, actual: Any, source_file: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "expected_value": expected,
        "actual_value": actual,
        "status": "passed" if str(expected) == str(actual) else "failed",
        "source_file": source_file,
        "notes": "archive metric consistency",
    }


def build_metric_checks() -> pd.DataFrame:
    smoke_v5 = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5/smoke_test_v5_summary.json")
    financial = read_json(
        RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1/dashboard_financial_statement_patch_summary.json"
    )
    news = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1/dashboard_news_patch_summary.json")
    manual = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1/manual_review_writeback_summary.json")
    audit = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1/manual_review_writeback_audit_replay_summary.json")
    consolidated = read_csv(RESEARCH_DIR / "tech_bottleneck_watchlist_report_consolidated_v1/watchlist_report_consolidated_index.csv")
    dashboard_links = read_csv(RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1/tech_bottleneck_dashboard_report_links.csv")
    rows = [
        metric_row("watchlist_count", 102, smoke_v5.get("watchlist_count"), "smoke_test_v5_summary.json"),
        metric_row("consolidated_report_count", 102, len(consolidated), "watchlist_report_consolidated_index.csv"),
        metric_row("dashboard_report_links", 102, len(dashboard_links), "tech_bottleneck_dashboard_report_links.csv"),
        metric_row("financial_statement_supported", 63, financial.get("supported_count"), "dashboard_financial_statement_patch_summary.json"),
        metric_row("financial_statement_missing", 39, financial.get("missing_count"), "dashboard_financial_statement_patch_summary.json"),
        metric_row("financial_statement_pit_strong", 63, financial.get("pit_strong_count"), "dashboard_financial_statement_patch_summary.json"),
        metric_row("financial_statement_pit_degraded", 0, financial.get("pit_degraded_count"), "dashboard_financial_statement_patch_summary.json"),
        metric_row("news_supported", 30, news.get("news_supported_count"), "dashboard_news_patch_summary.json"),
        metric_row("news_partial", 1, news.get("news_partial_count"), "dashboard_news_patch_summary.json"),
        metric_row("news_missing", 71, news.get("news_missing_count"), "dashboard_news_patch_summary.json"),
        metric_row("news_pit_available_events", 189, news.get("pit_available_event_count"), "dashboard_news_patch_summary.json"),
        metric_row("news_post_admission_events", 11, news.get("post_admission_event_count"), "dashboard_news_patch_summary.json"),
        metric_row("news_date_missing_events", 71, news.get("date_missing_event_count"), "dashboard_news_patch_summary.json"),
        metric_row("dashboard_v5_sections_partial", 0, smoke_v5.get("sections_partial"), "smoke_test_v5_summary.json"),
        metric_row("dashboard_v5_sections_failed", 0, smoke_v5.get("sections_failed"), "smoke_test_v5_summary.json"),
        metric_row("manual_review_allowed_fields", 11, manual.get("allowed_fields_count"), "manual_review_writeback_summary.json"),
        metric_row("manual_review_forbidden_fields", 37, manual.get("forbidden_fields_count"), "manual_review_writeback_summary.json"),
        metric_row("audit_replay_mismatch_count", 0, audit.get("replay_consistency_mismatch_count"), "manual_review_writeback_audit_replay_summary.json"),
        metric_row("audit_hash_missing_count", 0, audit.get("audit_hash_missing_count"), "manual_review_writeback_audit_replay_summary.json"),
    ]
    return pd.DataFrame(rows)


def guardrail_row(metric: str, expected: Any, actual: Any, source_file: str) -> dict[str, Any]:
    return {
        "guardrail": metric,
        "expected_value": expected,
        "actual_value": actual,
        "status": "passed" if str(expected) == str(actual) else "failed",
        "source_file": source_file,
        "notes": "latest chain guardrail consistency",
    }


def build_guardrail_checks(strategy_clean: bool) -> pd.DataFrame:
    smoke_v5 = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5/smoke_test_v5_summary.json")
    manual = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1/manual_review_writeback_guardrails.json")
    audit = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1/manual_review_writeback_audit_replay_guardrails.json")
    values = {
        "baseline_admission_changed_count": max(
            int(smoke_v5.get("baseline_admission_changed_count", 0)),
            int(manual.get("baseline_admission_changed_count", 0)),
            int(audit.get("baseline_admission_changed_count", 0)),
        ),
        "used_for_signal_count": max(
            int(smoke_v5.get("used_for_signal_count", 0)),
            int(manual.get("used_for_signal_count", 0)),
            int(audit.get("used_for_signal_count", 0)),
        ),
        "used_for_admission_count": max(
            int(smoke_v5.get("used_for_admission_count", 0)),
            int(manual.get("used_for_admission_count", 0)),
            int(audit.get("used_for_admission_count", 0)),
        ),
        "trading_language_hit_count": max(
            int(smoke_v5.get("trading_language_hit_count", 0)),
            int(manual.get("trading_language_hit_count", 0)),
            int(audit.get("trading_language_hit_count", 0)),
        ),
        "execution_language_hit_count": max(
            int(smoke_v5.get("execution_language_hit_count", 0)),
            int(manual.get("execution_language_hit_count", 0)),
            int(audit.get("execution_language_hit_count", 0)),
        ),
        "forbidden_action_leakage_count": max(
            int(smoke_v5.get("forbidden_action_leakage_count", 0)),
            int(manual.get("forbidden_action_leakage_count", 0)),
            int(audit.get("forbidden_action_leakage_count", 0)),
        ),
        "lookahead_violation_rows": max(
            int(smoke_v5.get("lookahead_violation_rows", 0)),
            int(manual.get("lookahead_violation_rows", 0)),
            int(audit.get("lookahead_violation_rows", 0)),
        ),
        "strategy_writeback_enabled_count": max(
            int(smoke_v5.get("strategy_writeback_enabled_count", 0)),
            int(manual.get("strategy_writeback_enabled_count", 0)),
            int(audit.get("strategy_writeback_enabled_count", 0)),
        ),
        "baseline_admission_change_enabled_count": max(
            int(smoke_v5.get("baseline_admission_change_enabled_count", 0)),
            int(manual.get("baseline_admission_change_enabled_count", 0)),
            int(audit.get("baseline_admission_change_enabled_count", 0)),
        ),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
    }
    expected = {
        "baseline_admission_changed_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "forbidden_action_leakage_count": 0,
        "lookahead_violation_rows": 0,
        "strategy_writeback_enabled_count": 0,
        "baseline_admission_change_enabled_count": 0,
        "strategy_file_diff_clean": True,
        "formal_strategy_files_modified": False,
        "research_only": True,
    }
    return pd.DataFrame(
        [guardrail_row(metric, expected_value, values[metric], "latest_chain_guardrails") for metric, expected_value in expected.items()]
    )


def build_dependency_graph(tasks: list[Path]) -> dict[str, Any]:
    discovered = {path.name for path in tasks}
    node_names = [task for task in REQUIRED_TASKS if task in discovered]
    edges = [
        ("tech_bottleneck_research_selection_layer_v2_generator_v1", "tech_bottleneck_manual_review_label_schema_v1"),
        ("tech_bottleneck_manual_review_label_schema_v1", "tech_bottleneck_manual_review_template_v1"),
        ("tech_bottleneck_manual_review_template_v1", "tech_bottleneck_dashboard_readonly_user_smoke_test_v5"),
        ("tech_bottleneck_full_financial_statement_source_adapter_v1", "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1"),
        ("tech_bottleneck_watchlist_report_full_financial_statement_patch_v1", "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1"),
        ("tech_bottleneck_news_source_mapping_v1", "tech_bottleneck_watchlist_report_news_patch_v1"),
        ("tech_bottleneck_watchlist_report_news_patch_v1", "tech_bottleneck_dashboard_readonly_news_patch_v1"),
        ("tech_bottleneck_dashboard_readonly_news_patch_v1", "tech_bottleneck_dashboard_readonly_user_smoke_test_v4"),
        ("tech_bottleneck_manual_review_writeback_research_only_v1", "tech_bottleneck_dashboard_readonly_user_smoke_test_v5"),
        ("tech_bottleneck_manual_review_writeback_research_only_v1", "tech_bottleneck_manual_review_writeback_audit_replay_v1"),
    ]
    return {
        "nodes": [{"id": task, "exists": task in discovered, "required": task in REQUIRED_TASKS} for task in node_names],
        "edges": [
            {"from": source, "to": target, "status": "active" if source in discovered and target in discovered else "missing_endpoint"}
            for source, target in edges
        ],
    }


def build_issue_report(required_checks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in required_checks.itertuples(index=False):
        if row.status != "passed":
            rows.append(
                {
                    "task_name": row.task_name,
                    "artifact_name": row.artifact_name,
                    "issue_type": "missing_artifact",
                    "severity": row.severity,
                    "status": row.status,
                    "notes": row.notes,
                }
            )
    if not rows:
        rows.append(
            {
                "task_name": "archive_integrity",
                "artifact_name": "none",
                "issue_type": "none",
                "severity": "info",
                "status": "passed",
                "notes": "no blocking or warning artifacts detected",
            }
        )
    return pd.DataFrame(rows)


def build_report(summary: dict[str, Any], graph: dict[str, Any], test_results: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Research Archive Integrity Check v1

## 1. Scope

This task validates the research artifact archive only. It does not modify formal strategy files, baseline admission, or automated execution prompts.

## 2. Archive Coverage

- discovered tasks: {summary["discovered_task_count"]}
- required tasks: {summary["required_task_count"]}
- required artifact missing count: {summary["required_artifact_missing_count"]}
- warning issue count: {summary["warning_issue_count"]}

## 3. Artifact Manifest and Checksums

- manifest rows: {summary["artifact_manifest_rows"]}
- checksum rows: {summary["checksum_rows"]}
- checksum missing / failed: {summary["checksum_missing_or_failed_count"]}

## 4. Dependency Graph

- dependency nodes: {len(graph["nodes"])}
- dependency edges: {len(graph["edges"])}
- latest smoke, manual review writeback, and audit replay are linked in the graph.

## 5. Metric Consistency Checks

- metric mismatch count: {summary["metric_mismatch_count"]}
- latest smoke v5 ready: {summary["latest_smoke_v5_ready"]}
- manual review writeback ready: {summary["manual_review_writeback_ready"]}
- audit replay ready: {summary["audit_replay_ready"]}

## 6. Guardrail Consistency Checks

- guardrail mismatch count: {summary["guardrail_mismatch_count"]}
- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used for signal count: {summary["used_for_signal_count"]}
- used for admission count: {summary["used_for_admission_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- strategy file diff clean: {summary["strategy_file_diff_clean"]}

## 7. Missing / Stale / Warning Artifacts

- blocking issue count: {summary["blocking_issue_count"]}
- warning issue count: {summary["warning_issue_count"]}

## 8. Test Results

- New pytest: {test_results["new_pytest"]}
- Audit replay pytest: {test_results["audit_replay_pytest"]}
- Smoke v5 pytest: {test_results["smoke_v5_pytest"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 9. Acceptance Decision

`{summary["acceptance_decision"]}`

## 10. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_release_notes_v1`
2. `tech_bottleneck_research_archive_packaging_v1`
3. `tech_bottleneck_manual_review_writeback_persistence_adapter_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tasks = discover_tasks()
    manifest = build_manifest(tasks)
    checksums = build_checksums(manifest)
    required_checks = build_required_checks(tasks)
    metrics = build_metric_checks()
    strategy_clean = strategy_diff_clean()
    guardrail_checks = build_guardrail_checks(strategy_clean)
    issues = build_issue_report(required_checks)
    graph = build_dependency_graph(tasks)
    smoke_v5 = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5/smoke_test_v5_summary.json")
    manual = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1/manual_review_writeback_summary.json")
    audit = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1/manual_review_writeback_audit_replay_summary.json")
    blocking_issue_count = int(issues["severity"].eq("blocking").sum()) if not issues.empty else 0
    warning_issue_count = int(issues["severity"].eq("warning").sum()) if not issues.empty else 0
    metric_mismatch_count = int(metrics["status"].ne("passed").sum())
    guardrail_mismatch_count = int(guardrail_checks["status"].ne("passed").sum())
    checksum_missing_or_failed_count = int(checksums["sha256"].fillna("").str.len().ne(64).sum()) if not checksums.empty else 1
    latest_ready = smoke_v5.get("acceptance_decision") == "dashboard_ready_with_research_only_manual_review_writeback"
    manual_ready = manual.get("acceptance_decision") == "manual_review_writeback_research_only_ready"
    audit_ready = audit.get("acceptance_decision") == "manual_review_writeback_audit_replay_ready"
    guardrail_values = dict(zip(guardrail_checks["guardrail"], guardrail_checks["actual_value"]))
    total_blocking = blocking_issue_count + metric_mismatch_count + guardrail_mismatch_count + checksum_missing_or_failed_count
    if not latest_ready:
        total_blocking += 1
    if not manual_ready:
        total_blocking += 1
    if not audit_ready:
        total_blocking += 1
    acceptance = "research_archive_integrity_ready" if total_blocking == 0 and warning_issue_count == 0 else (
        "conditionally_ready_with_non_blocking_archive_warnings" if total_blocking == 0 else "blocked_due_to_archive_integrity_failure"
    )
    summary = {
        "task_name": "tech_bottleneck_research_archive_integrity_check_v1",
        "required_task_count": len(REQUIRED_TASKS),
        "discovered_task_count": len(tasks),
        "artifact_manifest_rows": len(manifest),
        "checksum_rows": len(checksums),
        "required_artifact_missing_count": int(required_checks["exists"].eq(False).sum()),
        "blocking_issue_count": int(total_blocking),
        "warning_issue_count": warning_issue_count,
        "metric_mismatch_count": metric_mismatch_count,
        "guardrail_mismatch_count": guardrail_mismatch_count,
        "checksum_missing_or_failed_count": checksum_missing_or_failed_count,
        "latest_smoke_v5_ready": latest_ready,
        "manual_review_writeback_ready": manual_ready,
        "audit_replay_ready": audit_ready,
        "strategy_writeback_enabled_count": int(guardrail_values.get("strategy_writeback_enabled_count", 0)),
        "baseline_admission_change_enabled_count": int(guardrail_values.get("baseline_admission_change_enabled_count", 0)),
        "baseline_admission_changed_count": int(guardrail_values.get("baseline_admission_changed_count", 0)),
        "used_for_signal_count": int(guardrail_values.get("used_for_signal_count", 0)),
        "used_for_admission_count": int(guardrail_values.get("used_for_admission_count", 0)),
        "trading_language_hit_count": int(guardrail_values.get("trading_language_hit_count", 0)),
        "execution_language_hit_count": int(guardrail_values.get("execution_language_hit_count", 0)),
        "forbidden_action_leakage_count": int(guardrail_values.get("forbidden_action_leakage_count", 0)),
        "lookahead_violation_rows": int(guardrail_values.get("lookahead_violation_rows", 0)),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": acceptance,
    }
    guardrails = {
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "forbidden_action_leakage_count": summary["forbidden_action_leakage_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_writeback_enabled_count": summary["strategy_writeback_enabled_count"],
        "baseline_admission_change_enabled_count": summary["baseline_admission_change_enabled_count"],
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": acceptance,
    }
    test_results = {
        "new_pytest": "pending_initial_generation",
        "audit_replay_pytest": "pending_initial_generation",
        "smoke_v5_pytest": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }

    write_json(OUTPUT_DIR / "research_archive_integrity_summary.json", summary)
    manifest.to_csv(OUTPUT_DIR / "research_archive_artifact_manifest.csv", index=False)
    checksums.to_csv(OUTPUT_DIR / "research_archive_artifact_checksums.csv", index=False)
    write_json(OUTPUT_DIR / "research_archive_task_dependency_graph.json", graph)
    required_checks.to_csv(OUTPUT_DIR / "research_archive_required_artifact_checks.csv", index=False)
    metrics.to_csv(OUTPUT_DIR / "research_archive_metric_consistency_checks.csv", index=False)
    guardrail_checks.to_csv(OUTPUT_DIR / "research_archive_guardrail_consistency_checks.csv", index=False)
    issues.to_csv(OUTPUT_DIR / "research_archive_missing_or_stale_artifacts.csv", index=False)
    write_json(OUTPUT_DIR / "research_archive_integrity_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_research_archive_integrity_check_v1_report.md").write_text(
        build_report(summary, graph, test_results),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
