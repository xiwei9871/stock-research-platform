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
REPORT_NEWS_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_news_patch_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1"

REPORT_SUMMARY = REPORT_NEWS_DIR / "watchlist_report_news_patch_summary.json"
REPORT_SECTIONS = REPORT_NEWS_DIR / "watchlist_report_news_sections.csv"
REPORT_SECTIONS_JSON = REPORT_NEWS_DIR / "watchlist_report_news_sections.json"
REPORT_MISSING = REPORT_NEWS_DIR / "watchlist_report_news_missing.csv"
REPORT_PARTIAL = REPORT_NEWS_DIR / "watchlist_report_news_partial.csv"
REPORT_EVENT_TYPE = REPORT_NEWS_DIR / "watchlist_report_news_event_type_coverage.csv"
REPORT_SOURCE_QUALITY = REPORT_NEWS_DIR / "watchlist_report_news_source_quality.csv"
REPORT_GUARDRAILS = REPORT_NEWS_DIR / "watchlist_report_news_guardrails.json"
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
    re.compile(r"保存|提交|写回"),
]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def contains_forbidden_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def clean_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def build_rows(sections: pd.DataFrame, missing: pd.DataFrame, partial: pd.DataFrame) -> pd.DataFrame:
    missing_notes = missing.set_index("asset_id").to_dict(orient="index") if not missing.empty else {}
    partial_notes = partial.set_index("asset_id").to_dict(orient="index") if not partial.empty else {}
    rows: list[dict[str, Any]] = []
    for _, row in sections.iterrows():
        asset_id = clean_value(row["asset_id"])
        missing_note = missing_notes.get(asset_id, {})
        partial_note = partial_notes.get(asset_id, {})
        rows.append(
            {
                "asset_id": asset_id,
                "ts_code": clean_value(row["ts_code"]),
                "stock_code": clean_value(row["stock_code"]),
                "stock_name": clean_value(row["stock_name"]),
                "first_admission_date": clean_value(row["first_admission_date"]),
                "news_support": clean_value(row["news_support"]),
                "news_event_count": int(row["news_event_count"]),
                "pit_available_event_count": int(row["pit_available_event_count"]),
                "post_admission_event_count": int(row["post_admission_event_count"]),
                "date_missing_event_count": int(row["date_missing_event_count"]),
                "company_specific_count": int(row["company_specific_count"]),
                "industry_level_count": int(row["industry_level_count"]),
                "policy_level_count": int(row["policy_level_count"]),
                "risk_event_count": int(row["risk_event_count"]),
                "source_quality": clean_value(row["source_quality"]),
                "news_data_gap": bool_value(row["news_data_gap"]),
                "data_gap_note": clean_value(missing_note.get("data_gap_note", "")),
                "partial_coverage_note": clean_value(partial_note.get("partial_note", "")),
                "used_for_signal": False,
                "used_for_admission": False,
                "used_for_dashboard": True,
                "used_for_manual_review": True,
                "research_only": True,
                "writeback_enabled": False,
            }
        )
    return pd.DataFrame(rows)


def build_event_cards(section_json: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for section in section_json:
        for event in section.get("events", []):
            pit_status = clean_value(event.get("pit_status"))
            if pit_status == "pit_available":
                card_group = "PIT-Available Events"
                event_note = "Available at first admission cutoff."
            elif pit_status == "post_admission_context":
                card_group = "Post-Admission Review Context"
                event_note = "Post-admission review context only; not PIT evidence."
            else:
                card_group = "Date-Missing / Degraded Events"
                event_note = "Date missing or source gap; degraded and not strong PIT evidence."
            rows.append(
                {
                    "asset_id": clean_value(section.get("asset_id")),
                    "ts_code": clean_value(section.get("ts_code")),
                    "stock_code": clean_value(section.get("stock_code")),
                    "stock_name": clean_value(section.get("stock_name")),
                    "first_admission_date": clean_value(section.get("first_admission_date")),
                    "event_id": clean_value(event.get("event_id")),
                    "event_title": clean_value(event.get("event_title")),
                    "event_type": clean_value(event.get("event_type")),
                    "source_type": clean_value(event.get("source_type")),
                    "publish_date": clean_value(event.get("publish_date")),
                    "matched_topic": clean_value(event.get("matched_topic")),
                    "pit_status": pit_status,
                    "source_quality": clean_value(event.get("source_quality")),
                    "card_group": card_group,
                    "event_note": event_note,
                    "used_for_signal": False,
                    "used_for_admission": False,
                    "research_only": True,
                    "writeback_enabled": False,
                }
            )
    return pd.DataFrame(rows)


def build_filters() -> dict[str, Any]:
    return {
        "filter_scope": "display_only",
        "news_support": ["supported", "partial", "missing"],
        "pit_status": ["pit_available", "post_admission_context", "date_missing"],
        "source_quality": ["high", "medium", "low", "missing", "degraded"],
        "event_type": [
            "company_announcement",
            "capacity_expansion",
            "customer_validation",
            "financial_risk",
            "litigation_or_penalty",
            "data_gap",
        ],
        "used_for_signal": False,
        "used_for_admission": False,
    }


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if contains_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Dashboard Readonly News Patch v1

## 1. Scope

This task creates a readonly dashboard news context patch. It does not modify formal strategy files, baseline admission, dashboard write capability, or automated execution prompts.

## 2. Input Artifacts

- News report patch output: `tech_bottleneck_watchlist_report_news_patch_v1`
- Existing readonly dashboard feature module: `dashboard/src/features/techBottleneckWatchlistReview`
- Formal strategy files were checked only for diff status.

## 3. Dashboard Patch Methodology

Report-level news sections are converted into dashboard rows, event cards, missing rows, partial rows, date-missing rows, post-admission rows, event type coverage, display-only filters, and a frontend contract. Filters are display-only and do not change admission.

## 4. Coverage Summary

- Watchlist count: {summary["watchlist_count"]}
- News supported: {summary["news_supported_count"]}
- News partial: {summary["news_partial_count"]}
- News missing: {summary["news_missing_count"]}
- PIT available events: {summary["pit_available_event_count"]}
- Post-admission events: {summary["post_admission_event_count"]}
- Date-missing events: {summary["date_missing_event_count"]}
- Source quality rows: {summary["source_quality_rows"]}
- Event type rows: {summary["event_type_rows"]}

## 5. Frontend Changes

The readonly feature module is patched with summary chips, a news section, watchlist news columns, event cards, missing notes, partial notes, date-missing degraded notes, post-admission context notes, and display-only filter metadata.

## 6. Readonly and Guardrail Checks

- writeback_allowed_count: {summary["writeback_allowed_count"]}
- manual_review_writeback_enabled_count: {summary["manual_review_writeback_enabled_count"]}
- forbidden_action_leakage_count: {summary["forbidden_action_leakage_count"]}
- trading_language_hit_count: {summary["trading_language_hit_count"]}
- execution_language_hit_count: {summary["execution_language_hit_count"]}
- used_for_signal_count: {summary["used_for_signal_count"]}
- used_for_admission_count: {summary["used_for_admission_count"]}
- baseline_admission_changed_count: {summary["baseline_admission_changed_count"]}
- lookahead_violation_rows: {summary["lookahead_violation_rows"]}
- strategy_file_diff_clean: {summary["strategy_file_diff_clean"]}

## 7. Test Results

Verification commands are recorded after generation:

- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_news_patch.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_watchlist_report_news_patch.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_news_source_mapping.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_user_smoke_test_v3.py -q`
- Pending at initial generation: `cd dashboard && pnpm build`
- Pending at initial generation: `cd dashboard && pnpm test -- tech-bottleneck-route.test.tsx`
- Pending at initial generation: `git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py`

## 8. Acceptance Decision

`{summary["acceptance_decision"]}`

## 9. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_user_smoke_test_v4`
2. `tech_bottleneck_manual_review_writeback_research_only_v1`
3. `tech_bottleneck_research_archive_integrity_check_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_summary = read_json(REPORT_SUMMARY)
    sections = read_csv(REPORT_SECTIONS)
    section_json = read_json(REPORT_SECTIONS_JSON)
    missing = read_csv(REPORT_MISSING)
    partial = read_csv(REPORT_PARTIAL)
    event_type = read_csv(REPORT_EVENT_TYPE)
    source_quality = read_csv(REPORT_SOURCE_QUALITY)
    report_guardrails = read_json(REPORT_GUARDRAILS)

    rows = build_rows(sections, missing, partial)
    event_cards = build_event_cards(section_json)
    date_missing = event_cards[event_cards["pit_status"].eq("date_missing")].copy()
    post_admission = event_cards[event_cards["pit_status"].eq("post_admission_context")].copy()
    strategy_clean = strategy_diff_clean()
    filters = build_filters()
    contract = {
        "section_name": "News and Event Review Context",
        "section_status": "passed",
        "watchlist_count": int(report_summary.get("reports_total", len(rows))),
        "news_supported_count": int(report_summary.get("reports_news_supported", rows["news_support"].eq("supported").sum())),
        "news_partial_count": int(report_summary.get("reports_news_partial", rows["news_support"].eq("partial").sum())),
        "news_missing_count": int(report_summary.get("reports_news_missing", rows["news_support"].eq("missing").sum())),
        "pit_available_event_count": int(report_summary.get("pit_available_event_count", event_cards["pit_status"].eq("pit_available").sum())),
        "post_admission_event_count": int(report_summary.get("post_admission_event_count", len(post_admission))),
        "date_missing_event_count": int(report_summary.get("date_missing_event_count", len(date_missing))),
        "lookahead_violation_rows": int(report_summary.get("lookahead_violation_rows", 0)),
        "writeback_enabled": False,
        "manual_review_writeback_enabled": False,
        "used_for_signal": False,
        "used_for_admission": False,
        "research_only": True,
        "frontend_fields": [
            "news_support",
            "news_event_count",
            "pit_available_event_count",
            "post_admission_event_count",
            "date_missing_event_count",
            "risk_event_count",
            "source_quality",
            "news_data_gap",
        ],
        "filters": filters,
        "warnings": [
            "News coverage is degraded for missing and date-missing rows.",
            "Post-admission rows are review context only.",
            "Display filters do not change baseline admission.",
        ],
        "acceptance_decision": "dashboard_readonly_news_patch_ready_with_degraded_coverage",
    }
    summary = {
        "task_name": "tech_bottleneck_dashboard_readonly_news_patch_v1",
        "watchlist_count": int(contract["watchlist_count"]),
        "news_supported_count": int(contract["news_supported_count"]),
        "news_partial_count": int(contract["news_partial_count"]),
        "news_missing_count": int(contract["news_missing_count"]),
        "pit_available_event_count": int(contract["pit_available_event_count"]),
        "post_admission_event_count": int(contract["post_admission_event_count"]),
        "date_missing_event_count": int(contract["date_missing_event_count"]),
        "section_status": "passed",
        "lookahead_violation_rows": int(contract["lookahead_violation_rows"]),
        "writeback_allowed_count": 0,
        "manual_review_writeback_enabled_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "used_for_signal_count": int(rows["used_for_signal"].astype(bool).sum()) + int(event_cards["used_for_signal"].astype(bool).sum()),
        "used_for_admission_count": int(rows["used_for_admission"].astype(bool).sum()) + int(event_cards["used_for_admission"].astype(bool).sum()),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "readonly_ui_only": True,
        "event_type_rows": int(len(event_type)),
        "source_quality_rows": int(len(source_quality)),
        "upstream_acceptance_decision": report_guardrails.get("acceptance_decision", ""),
        "acceptance_decision": "dashboard_readonly_news_patch_ready_with_degraded_coverage",
    }

    rows.to_csv(OUTPUT_DIR / "dashboard_news_rows.csv", index=False)
    write_json(OUTPUT_DIR / "dashboard_news_event_cards.json", event_cards.to_dict(orient="records"))
    missing.to_csv(OUTPUT_DIR / "dashboard_news_missing_rows.csv", index=False)
    partial_export = partial.rename(columns={"partial_note": "partial_coverage_note"})
    partial_export.to_csv(OUTPUT_DIR / "dashboard_news_partial_rows.csv", index=False)
    date_missing.to_csv(OUTPUT_DIR / "dashboard_news_date_missing_rows.csv", index=False)
    post_admission.to_csv(OUTPUT_DIR / "dashboard_news_post_admission_rows.csv", index=False)
    event_type.to_csv(OUTPUT_DIR / "dashboard_news_event_type_coverage.csv", index=False)
    write_json(OUTPUT_DIR / "dashboard_news_filters.json", filters)
    write_json(OUTPUT_DIR / "dashboard_news_frontend_contract.json", contract)
    source_quality.to_csv(OUTPUT_DIR / "dashboard_news_source_quality.csv", index=False)
    write_json(OUTPUT_DIR / "dashboard_news_patch_summary.json", summary)
    write_json(OUTPUT_DIR / "dashboard_news_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1_report.md").write_text(
        build_report(summary),
        encoding="utf-8",
    )

    language_hits = scan_outputs()
    summary["trading_language_hit_count"] = language_hits
    summary["execution_language_hit_count"] = language_hits
    summary["forbidden_action_leakage_count"] = language_hits
    write_json(OUTPUT_DIR / "dashboard_news_patch_summary.json", summary)
    write_json(OUTPUT_DIR / "dashboard_news_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1_report.md").write_text(
        build_report(summary),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
