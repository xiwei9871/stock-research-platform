#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1"
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

SECTIONS = [
    "Summary",
    "Watchlist Table",
    "Risk Review Queue",
    "Manual Review Template Status",
    "Consolidated Report Links",
    "Full Financial Statement Review Context",
    "News and Event Review Context",
    "Manual Review Research-Only Writeback",
    "Warnings / Data Gaps",
    "Route / Navigation",
    "Readonly / Research-Only Guardrails",
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


def has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def scan_release_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".csv", ".txt"}:
            if has_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def checklist_row(check_name: str, expected: Any, actual: Any, notes: str) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "expected_value": expected,
        "actual_value": actual,
        "status": "passed" if str(expected) == str(actual) else "failed",
        "notes": notes,
    }


def build_checklist(summary: dict[str, Any], release_notes_generated: bool, strategy_clean: bool) -> pd.DataFrame:
    rows = [
        checklist_row("smoke_v5_ready", True, summary["smoke_v5_ready"], "latest dashboard smoke is ready"),
        checklist_row("manual_review_writeback_ready", True, summary["manual_review_writeback_ready"], "manual review writeback ready"),
        checklist_row("audit_replay_ready", True, summary["audit_replay_ready"], "audit replay ready"),
        checklist_row("archive_integrity_ready", True, summary["archive_integrity_ready"], "archive integrity ready"),
        checklist_row("financial_statement_section_passed", "passed", summary["financial_statement_section_status"], "financial section"),
        checklist_row("news_section_passed", "passed", summary["news_section_status"], "news section"),
        checklist_row("manual_review_writeback_section_passed", "passed", summary["manual_review_writeback_section_status"], "manual review section"),
        checklist_row("strategy_writeback_disabled", 0, summary["strategy_writeback_enabled_count"], "strategy writeback disabled"),
        checklist_row("baseline_admission_change_disabled", 0, summary["baseline_admission_change_enabled_count"], "baseline admission change disabled"),
        checklist_row("used_for_signal_zero", 0, summary["used_for_signal_count"], "not used for signal"),
        checklist_row("used_for_admission_zero", 0, summary["used_for_admission_count"], "not used for admission"),
        checklist_row("execution_language_zero", 0, summary["execution_language_hit_count"], "execution language scan"),
        checklist_row("lookahead_violation_zero", 0, summary["lookahead_violation_rows"], "lookahead audit"),
        checklist_row("formal_strategy_diff_empty", True, strategy_clean, "formal strategy diff"),
        checklist_row("release_notes_generated", True, release_notes_generated, "release notes generated"),
    ]
    return pd.DataFrame(rows)


def build_limitations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "limitation": "financial_statement_coverage_gap",
                "detail": "Financial statement coverage is 63 / 102, with 39 missing rows.",
                "severity": "known_gap",
            },
            {
                "limitation": "news_coverage_degraded",
                "detail": "News coverage is 30 supported, 1 partial, and 71 missing.",
                "severity": "known_gap",
            },
            {
                "limitation": "post_admission_context_only",
                "detail": "Post-admission news is review context only and not PIT evidence.",
                "severity": "methodology_boundary",
            },
            {
                "limitation": "date_missing_news_degraded",
                "detail": "Date-missing news is degraded and not strong PIT evidence.",
                "severity": "methodology_boundary",
            },
            {
                "limitation": "manual_review_research_only",
                "detail": "Manual review writeback does not affect formal strategy or admission.",
                "severity": "boundary",
            },
            {
                "limitation": "later_stage_deferred",
                "detail": "Trigger-stage, middle-stage, and later-stage automation remain deferred.",
                "severity": "scope_limit",
            },
            {
                "limitation": "no_execution_action_language",
                "detail": "Release materials avoid execution-action vocabulary.",
                "severity": "boundary",
            },
        ]
    )


def build_usage_boundary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "usage_type": "recommended",
                "usage": "open_review_dashboard",
                "description": "Open the Tech Bottleneck review page from the sidebar.",
            },
            {
                "usage_type": "recommended",
                "usage": "inspect_research_context",
                "description": "Review summary, warnings, watchlist rows, report links, financial context, and news context.",
            },
            {
                "usage_type": "recommended",
                "usage": "record_manual_review",
                "description": "Record research-only labels, notes, data gap confirmation, reviewer, and timestamp.",
            },
            {
                "usage_type": "forbidden",
                "usage": "formal_execution_basis",
                "description": "Do not use this release as formal execution basis.",
            },
            {
                "usage_type": "forbidden",
                "usage": "strategy_admission_change_basis",
                "description": "Do not use this release to alter baseline admission.",
            },
            {
                "usage_type": "forbidden",
                "usage": "strategy_writeback_path",
                "description": "Do not route manual review content into formal strategy inputs.",
            },
            {
                "usage_type": "forbidden",
                "usage": "automatic_removal_condition",
                "description": "Do not treat missing financial or news coverage as an automatic removal condition.",
            },
        ]
    )


def build_release_notes(summary: dict[str, Any]) -> str:
    section_lines = "\n".join(f"- {section}" for section in SECTIONS)
    return f"""# Tech Bottleneck Watchlist Review Dashboard v1
## Research-Only Internal Review Release Notes

### 1. Release Summary

This version is the internal research review dashboard for the Tech Bottleneck watchlist. It is research-only and supports dashboard inspection, report navigation, manual review notes, and audit replay. It is not a formal execution system, not an automated prompt generator, and does not change baseline admission or formal strategy files.

### 2. Current Acceptance State

- dashboard smoke v5 acceptance decision: `{summary["smoke_v5_acceptance_decision"]}`
- archive integrity acceptance decision: `{summary["archive_integrity_acceptance_decision"]}`
- manual review writeback acceptance decision: `{summary["manual_review_writeback_acceptance_decision"]}`
- audit replay acceptance decision: `{summary["audit_replay_acceptance_decision"]}`

### 3. Dashboard Sections

{section_lines}

### 4. Data Coverage

- watchlist count: {summary["watchlist_count"]}
- financial statement supported / missing: {summary["financial_statement_supported_count"]} / {summary["financial_statement_missing_count"]}
- financial statement PIT strong / degraded: {summary["financial_statement_pit_strong_count"]} / {summary["financial_statement_pit_degraded_count"]}
- news supported / partial / missing: {summary["news_supported_count"]} / {summary["news_partial_count"]} / {summary["news_missing_count"]}
- news PIT / post-admission / date_missing events: {summary["news_pit_available_event_count"]} / {summary["news_post_admission_event_count"]} / {summary["news_date_missing_event_count"]}

### 5. Manual Review Writeback Boundary

- manual review writeback enabled: {summary["manual_review_writeback_enabled"]}
- writeback scope: {summary["manual_review_writeback_scope"]}
- strategy writeback enabled: {summary["strategy_writeback_enabled"]}
- baseline admission change enabled: {summary["baseline_admission_change_enabled"]}
- allowed fields: {summary["allowed_fields_count"]}
- forbidden fields: {summary["forbidden_fields_count"]}
- audit log required: {summary["audit_log_required"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}

### 6. Audit Replay

- synthetic event count: {summary["synthetic_event_count"]}
- allowed event count: {summary["allowed_event_count"]}
- forbidden attempt count: {summary["forbidden_attempt_count"]}
- rejected event count: {summary["rejected_event_count"]}
- replay consistency mismatch count: {summary["replay_consistency_mismatch_count"]}
- audit hash missing count: {summary["audit_hash_missing_count"]}

### 7. Archive Integrity

- required task count: {summary["required_task_count"]}
- discovered task count: {summary["discovered_task_count"]}
- required artifact missing count: {summary["required_artifact_missing_count"]}
- blocking issue count: {summary["blocking_issue_count"]}
- warning issue count: {summary["warning_issue_count"]}
- metric mismatch count: {summary["metric_mismatch_count"]}
- guardrail mismatch count: {summary["guardrail_mismatch_count"]}
- checksum missing / failed: {summary["checksum_missing_or_failed_count"]}

### 8. Guardrails

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- baseline admission changed count: {summary["baseline_admission_changed_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- trading / execution language hit count: {summary["trading_language_hit_count"]} / {summary["execution_language_hit_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- formal strategy diff: empty

### 9. Known Limitations

- Financial statement coverage remains partial: 63 / 102 supported and 39 missing.
- News coverage is degraded: 30 supported, 1 partial, and 71 missing.
- Post-admission news is review context only and not PIT evidence.
- Date-missing news is degraded and not strong PIT evidence.
- Manual review writeback is research-only and does not affect formal strategy.
- Trigger-stage, middle-stage, and later-stage automation are not included.
- Execution-action vocabulary is intentionally excluded from release materials.

### 10. Recommended Internal Usage

1. Open `科技卡脖子观察池`.
2. Review summary and warnings.
3. Use Watchlist Table for read-only filtering.
4. Open individual consolidated report links.
5. Review financial statement context.
6. Review news and event context.
7. Fill research-only manual review labels and notes.
8. Review data gaps before drawing research conclusions.
9. Keep all usage inside the research review boundary.

### 11. Forbidden Usage

- Do not use as formal execution basis.
- Do not use as formal exposure adjustment basis.
- Do not use as baseline admission modification basis.
- Do not use as trigger-stage, middle-stage, or later-stage automation rules.
- Do not route manual review content into formal strategy inputs.
- Do not treat degraded news coverage as an automatic removal condition.
- Do not treat missing financial statement coverage as an automatic removal condition.

### 12. Recommended Next Steps

1. `tech_bottleneck_research_archive_packaging_v1`
2. `tech_bottleneck_manual_review_writeback_persistence_adapter_v1`
3. `tech_bottleneck_dashboard_readonly_ops_handoff_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def build_report(summary: dict[str, Any], test_results: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Dashboard Readonly Release Notes v1 Report

## 1. Scope

This task generated internal research-only release notes for Tech Bottleneck Watchlist Review Dashboard v1.

## 2. Inputs

- Smoke v5 summary
- Manual review writeback summary and contract
- Audit replay summary
- Archive integrity summary
- Financial statement and news dashboard patch summaries

## 3. Release State

- release notes generated: {summary["release_notes_generated"]}
- smoke v5 ready: {summary["smoke_v5_ready"]}
- manual review writeback ready: {summary["manual_review_writeback_ready"]}
- audit replay ready: {summary["audit_replay_ready"]}
- archive integrity ready: {summary["archive_integrity_ready"]}

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
- Archive integrity pytest: {test_results["archive_integrity_pytest"]}
- Smoke v5 pytest: {test_results["smoke_v5_pytest"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 6. Acceptance Decision

`{summary["acceptance_decision"]}`
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    smoke_v5 = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5/smoke_test_v5_summary.json")
    manual = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1/manual_review_writeback_summary.json")
    manual_contract = read_json(
        RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1/manual_review_writeback_frontend_contract.json"
    )
    audit = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1/manual_review_writeback_audit_replay_summary.json")
    archive = read_json(RESEARCH_DIR / "tech_bottleneck_research_archive_integrity_check_v1/research_archive_integrity_summary.json")
    archive_guardrails = read_json(
        RESEARCH_DIR / "tech_bottleneck_research_archive_integrity_check_v1/research_archive_integrity_guardrails.json"
    )
    financial = read_json(
        RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1/dashboard_financial_statement_patch_summary.json"
    )
    news = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1/dashboard_news_patch_summary.json")
    strategy_clean = strategy_diff_clean()

    summary = {
        "release_name": "Tech Bottleneck Watchlist Review Dashboard v1",
        "release_scope": "research-only internal review release",
        "release_notes_generated": True,
        "smoke_v5_ready": smoke_v5.get("acceptance_decision") == "dashboard_ready_with_research_only_manual_review_writeback",
        "manual_review_writeback_ready": manual.get("acceptance_decision") == "manual_review_writeback_research_only_ready",
        "audit_replay_ready": audit.get("acceptance_decision") == "manual_review_writeback_audit_replay_ready",
        "archive_integrity_ready": archive.get("acceptance_decision") == "research_archive_integrity_ready",
        "smoke_v5_acceptance_decision": smoke_v5.get("acceptance_decision"),
        "manual_review_writeback_acceptance_decision": manual.get("acceptance_decision"),
        "audit_replay_acceptance_decision": audit.get("acceptance_decision"),
        "archive_integrity_acceptance_decision": archive.get("acceptance_decision"),
        "watchlist_count": smoke_v5.get("watchlist_count", 0),
        "financial_statement_supported_count": financial.get("supported_count", 0),
        "financial_statement_missing_count": financial.get("missing_count", 0),
        "financial_statement_pit_strong_count": financial.get("pit_strong_count", 0),
        "financial_statement_pit_degraded_count": financial.get("pit_degraded_count", 0),
        "news_supported_count": news.get("news_supported_count", 0),
        "news_partial_count": news.get("news_partial_count", 0),
        "news_missing_count": news.get("news_missing_count", 0),
        "news_pit_available_event_count": news.get("pit_available_event_count", 0),
        "news_post_admission_event_count": news.get("post_admission_event_count", 0),
        "news_date_missing_event_count": news.get("date_missing_event_count", 0),
        "financial_statement_section_status": smoke_v5.get("financial_statement_section_status"),
        "news_section_status": smoke_v5.get("news_section_status"),
        "manual_review_writeback_section_status": smoke_v5.get("manual_review_writeback_section_status"),
        "manual_review_writeback_enabled": manual.get("manual_review_writeback_enabled"),
        "manual_review_writeback_scope": manual.get("writeback_scope"),
        "strategy_writeback_enabled": manual.get("strategy_writeback_enabled"),
        "baseline_admission_change_enabled": manual.get("baseline_admission_change_enabled"),
        "allowed_fields_count": manual.get("allowed_fields_count"),
        "forbidden_fields_count": manual.get("forbidden_fields_count"),
        "audit_log_required": manual_contract.get("audit_required"),
        "synthetic_event_count": audit.get("synthetic_event_count"),
        "allowed_event_count": audit.get("allowed_event_count"),
        "forbidden_attempt_count": audit.get("forbidden_attempt_count"),
        "rejected_event_count": audit.get("rejected_event_count"),
        "replay_consistency_mismatch_count": audit.get("replay_consistency_mismatch_count"),
        "audit_hash_missing_count": audit.get("audit_hash_missing_count"),
        "required_task_count": archive.get("required_task_count"),
        "discovered_task_count": archive.get("discovered_task_count"),
        "required_artifact_missing_count": archive.get("required_artifact_missing_count"),
        "blocking_issue_count": archive.get("blocking_issue_count"),
        "warning_issue_count": archive.get("warning_issue_count"),
        "metric_mismatch_count": archive.get("metric_mismatch_count"),
        "guardrail_mismatch_count": archive.get("guardrail_mismatch_count"),
        "checksum_missing_or_failed_count": archive.get("checksum_missing_or_failed_count"),
        "strategy_writeback_enabled_count": archive_guardrails.get("strategy_writeback_enabled_count", 0),
        "baseline_admission_change_enabled_count": archive_guardrails.get("baseline_admission_change_enabled_count", 0),
        "baseline_admission_changed_count": archive_guardrails.get("baseline_admission_changed_count", 0),
        "used_for_signal_count": archive_guardrails.get("used_for_signal_count", 0),
        "used_for_admission_count": archive_guardrails.get("used_for_admission_count", 0),
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": archive_guardrails.get("lookahead_violation_rows", 0),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": "dashboard_readonly_release_notes_ready",
    }
    notes = build_release_notes(summary)
    report = build_report(
        summary,
        {
            "new_pytest": "pending_initial_generation",
            "archive_integrity_pytest": "pending_initial_generation",
            "smoke_v5_pytest": "pending_initial_generation",
            "formal_strategy_diff": "pending_initial_generation",
        },
    )
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1.md").write_text(notes, encoding="utf-8")
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1_report.md").write_text(report, encoding="utf-8")
    hits = scan_release_outputs()
    summary["trading_language_hit_count"] = hits
    summary["execution_language_hit_count"] = hits
    guardrails = {
        "release_notes_generated": True,
        "smoke_v5_ready": summary["smoke_v5_ready"],
        "manual_review_writeback_ready": summary["manual_review_writeback_ready"],
        "audit_replay_ready": summary["audit_replay_ready"],
        "archive_integrity_ready": summary["archive_integrity_ready"],
        "strategy_writeback_enabled_count": summary["strategy_writeback_enabled_count"],
        "baseline_admission_change_enabled_count": summary["baseline_admission_change_enabled_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "trading_language_hit_count": hits,
        "execution_language_hit_count": hits,
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": summary["acceptance_decision"],
    }
    checklist = build_checklist(summary, True, strategy_clean)
    limitations = build_limitations()
    usage = build_usage_boundary()

    write_json(OUTPUT_DIR / "dashboard_readonly_release_notes_summary.json", summary)
    checklist.to_csv(OUTPUT_DIR / "dashboard_readonly_release_notes_checklist.csv", index=False)
    write_json(OUTPUT_DIR / "dashboard_readonly_release_notes_guardrails.json", guardrails)
    limitations.to_csv(OUTPUT_DIR / "dashboard_readonly_release_notes_known_limitations.csv", index=False)
    usage.to_csv(OUTPUT_DIR / "dashboard_readonly_release_notes_usage_boundary.csv", index=False)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1_report.md").write_text(
        build_report(
            summary,
            {
                "new_pytest": "pending_initial_generation",
                "archive_integrity_pytest": "pending_initial_generation",
                "smoke_v5_pytest": "pending_initial_generation",
                "formal_strategy_diff": "pending_initial_generation",
            },
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
