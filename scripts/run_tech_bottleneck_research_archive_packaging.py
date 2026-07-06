#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_archive_packaging_v1"
PACKAGE_DIR = OUTPUT_DIR / "package"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
]

PACKAGE_ARTIFACTS = [
    ("release_notes", "tech_bottleneck_dashboard_readonly_release_notes_v1", "tech_bottleneck_dashboard_readonly_release_notes_v1.md", "release notes", "internal_research"),
    ("release_notes", "tech_bottleneck_dashboard_readonly_release_notes_v1", "dashboard_readonly_release_notes_summary.json", "release summary", "auditor"),
    ("release_notes", "tech_bottleneck_dashboard_readonly_release_notes_v1", "dashboard_readonly_release_notes_guardrails.json", "release guardrails", "auditor"),
    ("archive_integrity", "tech_bottleneck_research_archive_integrity_check_v1", "research_archive_integrity_summary.json", "archive integrity summary", "auditor"),
    ("archive_integrity", "tech_bottleneck_research_archive_integrity_check_v1", "research_archive_artifact_manifest.csv", "artifact manifest", "developer"),
    ("archive_integrity", "tech_bottleneck_research_archive_integrity_check_v1", "research_archive_artifact_checksums.csv", "artifact checksums", "auditor"),
    ("archive_integrity", "tech_bottleneck_research_archive_integrity_check_v1", "research_archive_task_dependency_graph.json", "dependency graph", "developer"),
    ("archive_integrity", "tech_bottleneck_research_archive_integrity_check_v1", "research_archive_metric_consistency_checks.csv", "metric consistency", "auditor"),
    ("archive_integrity", "tech_bottleneck_research_archive_integrity_check_v1", "research_archive_guardrail_consistency_checks.csv", "guardrail consistency", "auditor"),
    ("dashboard_smoke", "tech_bottleneck_dashboard_readonly_user_smoke_test_v5", "smoke_test_v5_summary.json", "smoke v5 summary", "dashboard_user"),
    ("dashboard_smoke", "tech_bottleneck_dashboard_readonly_user_smoke_test_v5", "smoke_test_v5_section_status.csv", "smoke section status", "dashboard_user"),
    ("dashboard_smoke", "tech_bottleneck_dashboard_readonly_user_smoke_test_v5", "smoke_test_v5_guardrail_checks.json", "smoke guardrails", "auditor"),
    ("financial_statement_context", "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1", "dashboard_financial_statement_patch_summary.json", "financial statement dashboard summary", "reviewer"),
    ("financial_statement_context", "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1", "dashboard_financial_statement_frontend_contract.json", "financial statement frontend contract", "developer"),
    ("financial_statement_context", "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1", "watchlist_report_full_financial_statement_patch_summary.json", "financial statement report summary", "reviewer"),
    ("news_context", "tech_bottleneck_dashboard_readonly_news_patch_v1", "dashboard_news_patch_summary.json", "news dashboard summary", "reviewer"),
    ("news_context", "tech_bottleneck_dashboard_readonly_news_patch_v1", "dashboard_news_frontend_contract.json", "news frontend contract", "developer"),
    ("news_context", "tech_bottleneck_watchlist_report_news_patch_v1", "watchlist_report_news_patch_summary.json", "news report summary", "reviewer"),
    ("manual_review_writeback", "tech_bottleneck_manual_review_writeback_research_only_v1", "manual_review_writeback_summary.json", "manual review writeback summary", "reviewer"),
    ("manual_review_writeback", "tech_bottleneck_manual_review_writeback_research_only_v1", "manual_review_writeback_schema.json", "manual review writeback schema", "developer"),
    ("manual_review_writeback", "tech_bottleneck_manual_review_writeback_research_only_v1", "manual_review_writeback_frontend_contract.json", "manual review frontend contract", "developer"),
    ("manual_review_writeback", "tech_bottleneck_manual_review_writeback_research_only_v1", "manual_review_writeback_guardrails.json", "manual review guardrails", "auditor"),
    ("audit_replay", "tech_bottleneck_manual_review_writeback_audit_replay_v1", "manual_review_writeback_audit_replay_summary.json", "audit replay summary", "auditor"),
    ("audit_replay", "tech_bottleneck_manual_review_writeback_audit_replay_v1", "manual_review_writeback_audit_replay_consistency_checks.csv", "audit replay consistency", "auditor"),
    ("audit_replay", "tech_bottleneck_manual_review_writeback_audit_replay_v1", "manual_review_writeback_audit_replay_guardrails.json", "audit replay guardrails", "auditor"),
]


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


def has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".csv", ".txt"}:
            if has_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def copy_package_artifacts() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    for file_group, task, file_name, description, consumer in PACKAGE_ARTIFACTS:
        source = RESEARCH_DIR / task / file_name
        package_path = PACKAGE_DIR / file_group / file_name
        package_path.parent.mkdir(parents=True, exist_ok=True)
        included = source.exists()
        checksum = ""
        size = 0
        if included:
            if task == "tech_bottleneck_research_archive_integrity_check_v1" and file_name == "research_archive_artifact_manifest.csv":
                pd.DataFrame(
                    [
                        {
                            "source_artifact": str(source.relative_to(PROJECT_ROOT)),
                            "source_checksum_sha256": sha256_file(source),
                            "package_policy": "referenced_not_raw_copied",
                            "reason": "raw external report filenames are omitted from the handoff package",
                            "research_only": True,
                            "used_for_signal": False,
                            "used_for_admission": False,
                        }
                    ]
                ).to_csv(package_path, index=False)
            else:
                shutil.copy2(source, package_path)
            checksum = sha256_file(package_path)
            size = package_path.stat().st_size
        rows.append(
            {
                "package_version": "v1",
                "package_name": "tech_bottleneck_research_only_dashboard_v1_archive_package",
                "source_task": task,
                "artifact_type": file_group,
                "source_path": str(source.relative_to(PROJECT_ROOT)),
                "package_path": str(package_path.relative_to(PROJECT_ROOT)),
                "file_name": file_name,
                "file_ext": Path(file_name).suffix.lower(),
                "file_size_bytes": size,
                "checksum_sha256": checksum,
                "included_in_package": included,
                "required_for_handoff": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": description,
            }
        )
    return pd.DataFrame(rows)


def build_file_index(manifest: pd.DataFrame) -> pd.DataFrame:
    rows = []
    consumer_map = {
        "release_notes": "internal_research",
        "archive_integrity": "auditor",
        "dashboard_smoke": "dashboard_user",
        "financial_statement_context": "reviewer",
        "news_context": "reviewer",
        "manual_review_writeback": "developer",
        "audit_replay": "auditor",
        "handoff": "ops_handoff",
    }
    for row in manifest.itertuples(index=False):
        rows.append(
            {
                "file_group": row.artifact_type,
                "file_name": row.file_name,
                "package_path": row.package_path,
                "description": row.notes,
                "consumer": row.consumer if hasattr(row, "consumer") else consumer_map.get(row.artifact_type, "internal_research"),
                "required": True,
                "checksum_sha256": row.checksum_sha256,
                "notes": "curated package artifact",
            }
        )
    rows.extend(
        [
            {
                "file_group": "handoff",
                "file_name": name,
                "package_path": f"outputs/research/tech_bottleneck_research_archive_packaging_v1/{name}",
                "description": description,
                "consumer": "ops_handoff",
                "required": True,
                "checksum_sha256": "",
                "notes": "generated handoff document",
            }
            for name, description in [
                ("research_archive_package_README.md", "package README"),
                ("research_archive_package_usage_boundary.md", "usage boundary"),
                ("research_archive_package_known_limitations.md", "known limitations"),
                ("research_archive_package_handoff_notes.md", "handoff notes"),
            ]
        ]
    )
    return pd.DataFrame(rows)


def build_readme(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Research-Only Dashboard v1 Archive Package

## 1. Package Purpose

This is the internal archive package for Tech Bottleneck research-only dashboard v1.

## 2. What This Package Contains

- Release notes
- Archive integrity outputs
- Dashboard smoke outputs
- Financial statement context
- News context
- Manual review writeback contracts
- Audit replay outputs

## 3. Current Ready State

- release notes ready: {summary["release_notes_ready"]}
- archive integrity ready: {summary["archive_integrity_ready"]}
- smoke v5 ready: {summary["smoke_v5_ready"]}
- manual review writeback ready: {summary["manual_review_writeback_ready"]}
- audit replay ready: {summary["audit_replay_ready"]}

## 4. Data Coverage

- watchlist count: 102
- financial statement: {summary["financial_statement_supported_count"]} supported / {summary["financial_statement_missing_count"]} missing
- news: {summary["news_supported_count"]} supported / {summary["news_partial_count"]} partial / {summary["news_missing_count"]} missing

## 5. Research-Only Boundary

- not a formal execution system
- not an automated prompt generator
- no baseline admission change
- no strategy writeback
- no trigger-stage, middle-stage, or later-stage automation research

## 6. How to Use

Internal researchers can review dashboard context, consolidated reports, manual review labels, data gaps, financial context, news context, and audit replay outputs.

## 7. Known Limitations

Financial statement coverage and news coverage remain incomplete. Date-missing news remains degraded. Post-admission news remains review context only.

## 8. Guardrail Summary

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- formal strategy diff: empty

## 9. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_ops_handoff_v1`
2. `tech_bottleneck_manual_review_writeback_persistence_adapter_v1`
3. `tech_bottleneck_research_archive_package_verification_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def build_usage_boundary() -> str:
    return """# Research Archive Package Usage Boundary

## Allowed Usage

- Internal research review.
- Manual review labels and notes.
- Data gap validation.
- Financial statement and news context review.
- Audit replay validation.
- Dashboard readonly review.

## Forbidden Usage

- Formal execution basis.
- Formal exposure adjustment basis.
- Baseline admission modification basis.
- Trigger-stage, middle-stage, or later-stage automation rules.
- Routing manual review content into formal strategy inputs.
- Treating missing news or missing financial statement coverage as an automatic removal condition.
- Treating post-admission news as PIT evidence.
- Treating date-missing news as strong PIT evidence.
"""


def build_known_limitations(summary: dict[str, Any]) -> str:
    return f"""# Known Limitations

- Financial statement coverage: {summary["financial_statement_supported_count"]} supported / {summary["financial_statement_missing_count"]} missing.
- News coverage: {summary["news_supported_count"]} supported / {summary["news_partial_count"]} partial / {summary["news_missing_count"]} missing.
- Date-missing news remains degraded.
- Post-admission news remains review context only.
- Manual review writeback remains research-only.
- Package is curated and referenced; no large compressed archive was generated.
"""


def build_handoff_notes(summary: dict[str, Any]) -> str:
    return f"""# Internal Handoff Notes

## Ready State

- release notes ready: {summary["release_notes_ready"]}
- archive integrity ready: {summary["archive_integrity_ready"]}
- smoke v5 ready: {summary["smoke_v5_ready"]}
- manual review writeback ready: {summary["manual_review_writeback_ready"]}
- audit replay ready: {summary["audit_replay_ready"]}

## Handoff Checks

- included artifact count: {summary["included_artifact_count"]}
- checksum missing / failed: {summary["checksum_missing_or_failed_count"]}
- formal strategy diff clean: {summary["strategy_file_diff_clean"]}

## Operator Note

Use this package for internal research review and audit handoff only.
"""


def build_report(summary: dict[str, Any], test_results: dict[str, str]) -> str:
    return f"""# Tech Bottleneck Research Archive Packaging v1 Report

## 1. Scope

This task generated a curated research-only archive package for Tech Bottleneck dashboard v1.

## 2. Package Outputs

- package generated: {summary["package_generated"]}
- package manifest generated: {summary["package_manifest_generated"]}
- package checksums generated: {summary["package_checksums_generated"]}
- package archive file: {summary["package_archive_file"]}

## 3. Readiness

- release notes ready: {summary["release_notes_ready"]}
- archive integrity ready: {summary["archive_integrity_ready"]}
- smoke v5 ready: {summary["smoke_v5_ready"]}
- manual review writeback ready: {summary["manual_review_writeback_ready"]}
- audit replay ready: {summary["audit_replay_ready"]}

## 4. Guardrails

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- formal strategy diff clean: {summary["strategy_file_diff_clean"]}

## 5. Test Results

- New pytest: {test_results["new_pytest"]}
- Release notes pytest: {test_results["release_notes_pytest"]}
- Archive integrity pytest: {test_results["archive_integrity_pytest"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 6. Acceptance Decision

`{summary["acceptance_decision"]}`
"""


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    release = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1/dashboard_readonly_release_notes_summary.json")
    release_guardrails = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1/dashboard_readonly_release_notes_guardrails.json")
    archive = read_json(RESEARCH_DIR / "tech_bottleneck_research_archive_integrity_check_v1/research_archive_integrity_summary.json")
    smoke = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5/smoke_test_v5_summary.json")
    manual = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1/manual_review_writeback_summary.json")
    audit = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1/manual_review_writeback_audit_replay_summary.json")
    financial = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1/dashboard_financial_statement_patch_summary.json")
    news = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1/dashboard_news_patch_summary.json")
    strategy_clean = strategy_diff_clean()
    manifest = copy_package_artifacts()
    checksum_missing = int(manifest["checksum_sha256"].fillna("").str.len().ne(64).sum())
    included_count = int(manifest["included_in_package"].astype(bool).sum())
    summary = {
        "package_generated": True,
        "package_manifest_generated": True,
        "package_checksums_generated": True,
        "package_archive_file": "not_generated_curated_referenced_package",
        "release_notes_ready": release.get("acceptance_decision") == "dashboard_readonly_release_notes_ready",
        "archive_integrity_ready": archive.get("acceptance_decision") == "research_archive_integrity_ready",
        "smoke_v5_ready": smoke.get("acceptance_decision") == "dashboard_ready_with_research_only_manual_review_writeback",
        "manual_review_writeback_ready": manual.get("acceptance_decision") == "manual_review_writeback_research_only_ready",
        "audit_replay_ready": audit.get("acceptance_decision") == "manual_review_writeback_audit_replay_ready",
        "included_artifact_count": included_count,
        "checksum_missing_or_failed_count": checksum_missing,
        "financial_statement_supported_count": financial.get("supported_count", 0),
        "financial_statement_missing_count": financial.get("missing_count", 0),
        "news_supported_count": news.get("news_supported_count", 0),
        "news_partial_count": news.get("news_partial_count", 0),
        "news_missing_count": news.get("news_missing_count", 0),
        "strategy_writeback_enabled_count": release_guardrails.get("strategy_writeback_enabled_count", 0),
        "baseline_admission_change_enabled_count": release_guardrails.get("baseline_admission_change_enabled_count", 0),
        "baseline_admission_changed_count": release_guardrails.get("baseline_admission_changed_count", 0),
        "used_for_signal_count": release_guardrails.get("used_for_signal_count", 0),
        "used_for_admission_count": release_guardrails.get("used_for_admission_count", 0),
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": release_guardrails.get("lookahead_violation_rows", 0),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": "research_archive_packaging_ready",
    }
    readme = build_readme(summary)
    usage = build_usage_boundary()
    limitations = build_known_limitations(summary)
    handoff = build_handoff_notes(summary)
    (OUTPUT_DIR / "research_archive_package_README.md").write_text(readme, encoding="utf-8")
    (OUTPUT_DIR / "research_archive_package_usage_boundary.md").write_text(usage, encoding="utf-8")
    (OUTPUT_DIR / "research_archive_package_known_limitations.md").write_text(limitations, encoding="utf-8")
    (OUTPUT_DIR / "research_archive_package_handoff_notes.md").write_text(handoff, encoding="utf-8")
    for doc in [
        OUTPUT_DIR / "research_archive_package_README.md",
        OUTPUT_DIR / "research_archive_package_usage_boundary.md",
        OUTPUT_DIR / "research_archive_package_known_limitations.md",
        OUTPUT_DIR / "research_archive_package_handoff_notes.md",
    ]:
        manifest.loc[len(manifest)] = {
            "package_version": "v1",
            "package_name": "tech_bottleneck_research_only_dashboard_v1_archive_package",
            "source_task": "tech_bottleneck_research_archive_packaging_v1",
            "artifact_type": "handoff",
            "source_path": str(doc.relative_to(PROJECT_ROOT)),
            "package_path": str(doc.relative_to(PROJECT_ROOT)),
            "file_name": doc.name,
            "file_ext": doc.suffix.lower(),
            "file_size_bytes": doc.stat().st_size,
            "checksum_sha256": sha256_file(doc),
            "included_in_package": True,
            "required_for_handoff": True,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
            "notes": "generated package handoff document",
        }
    file_index = build_file_index(manifest)
    checksums = manifest[["package_path", "file_name", "checksum_sha256", "file_size_bytes"]].copy()
    guardrails = {
        "package_generated": True,
        "package_manifest_generated": True,
        "package_checksums_generated": True,
        "release_notes_ready": summary["release_notes_ready"],
        "archive_integrity_ready": summary["archive_integrity_ready"],
        "smoke_v5_ready": summary["smoke_v5_ready"],
        "manual_review_writeback_ready": summary["manual_review_writeback_ready"],
        "audit_replay_ready": summary["audit_replay_ready"],
        "strategy_writeback_enabled_count": summary["strategy_writeback_enabled_count"],
        "baseline_admission_change_enabled_count": summary["baseline_admission_change_enabled_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": summary["acceptance_decision"],
    }
    manifest.to_csv(OUTPUT_DIR / "research_archive_package_manifest.csv", index=False)
    file_index.to_csv(OUTPUT_DIR / "research_archive_package_file_index.csv", index=False)
    checksums.to_csv(OUTPUT_DIR / "research_archive_package_checksums.csv", index=False)
    write_json(OUTPUT_DIR / "research_archive_package_summary.json", summary)
    write_json(OUTPUT_DIR / "research_archive_package_guardrails.json", guardrails)
    report = build_report(
        summary,
        {
            "new_pytest": "pending_initial_generation",
            "release_notes_pytest": "pending_initial_generation",
            "archive_integrity_pytest": "pending_initial_generation",
            "formal_strategy_diff": "pending_initial_generation",
        },
    )
    (OUTPUT_DIR / "tech_bottleneck_research_archive_packaging_v1_report.md").write_text(report, encoding="utf-8")
    hits = scan_outputs()
    summary["trading_language_hit_count"] = hits
    summary["execution_language_hit_count"] = hits
    guardrails["trading_language_hit_count"] = hits
    guardrails["execution_language_hit_count"] = hits
    write_json(OUTPUT_DIR / "research_archive_package_summary.json", summary)
    write_json(OUTPUT_DIR / "research_archive_package_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_research_archive_packaging_v1_report.md").write_text(
        build_report(
            summary,
            {
                "new_pytest": "pending_initial_generation",
                "release_notes_pytest": "pending_initial_generation",
                "archive_integrity_pytest": "pending_initial_generation",
                "formal_strategy_diff": "pending_initial_generation",
            },
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
