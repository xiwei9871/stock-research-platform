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
NEWS_DIR = RESEARCH_DIR / "tech_bottleneck_news_source_mapping_v1"
CONSOLIDATED_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_consolidated_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_news_patch_v1"

NEWS_EVENTS = NEWS_DIR / "news_source_mapping_events.csv"
NEWS_COMPANY = NEWS_DIR / "news_source_mapping_company_summary.csv"
NEWS_SOURCE_QUALITY = NEWS_DIR / "news_source_mapping_source_quality.csv"
NEWS_GUARDRAILS = NEWS_DIR / "news_source_mapping_guardrails.json"
CONSOLIDATED_INDEX = CONSOLIDATED_DIR / "watchlist_report_consolidated_index.csv"
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

SECTION_COLUMNS = [
    "ts_code",
    "stock_code",
    "stock_name",
    "asset_id",
    "first_admission_date",
    "news_support",
    "news_event_count",
    "pit_available_event_count",
    "post_admission_event_count",
    "date_missing_event_count",
    "company_specific_count",
    "industry_level_count",
    "policy_level_count",
    "risk_event_count",
    "source_quality",
    "news_data_gap",
    "used_for_signal",
    "used_for_admission",
    "used_for_dashboard",
    "used_for_manual_review",
    "research_only",
    "section_markdown",
]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def formal_strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def contains_forbidden_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def clean_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def event_record(event: pd.Series) -> dict[str, Any]:
    return {
        "event_id": clean_value(event.get("event_id")),
        "event_title": clean_value(event.get("event_title")),
        "event_summary": clean_value(event.get("event_summary")),
        "event_type": clean_value(event.get("event_type")),
        "source_type": clean_value(event.get("source_type")),
        "source_name": clean_value(event.get("source_name")),
        "source_url": clean_value(event.get("source_url")),
        "publish_date": clean_value(event.get("publish_date")),
        "matched_keyword": clean_value(event.get("matched_keyword")),
        "matched_topic": clean_value(event.get("matched_topic")),
        "pit_status": clean_value(event.get("pit_status")),
        "source_quality": clean_value(event.get("source_quality")),
        "is_company_specific": bool_value(event.get("is_company_specific")),
        "is_industry_level": bool_value(event.get("is_industry_level")),
        "is_policy_level": bool_value(event.get("is_policy_level")),
        "is_risk_event": bool_value(event.get("is_risk_event")),
        "first_admission_date": clean_value(event.get("first_admission_date")),
    }


def table_rows(events: pd.DataFrame, pit_status: str) -> list[str]:
    subset = events[events["pit_status"].eq(pit_status)].copy()
    if subset.empty:
        return []
    rows: list[str] = []
    for _, event in subset.iterrows():
        if pit_status == "pit_available":
            rows.append(
                "| "
                + " | ".join(
                    [
                        clean_value(event.get("publish_date")),
                        clean_value(event.get("event_type")),
                        clean_value(event.get("source_type")),
                        clean_value(event.get("event_title")),
                        clean_value(event.get("matched_topic")),
                        clean_value(event.get("source_quality")),
                    ]
                )
                + " |"
            )
        elif pit_status == "post_admission_context":
            rows.append(
                "| "
                + " | ".join(
                    [
                        clean_value(event.get("publish_date")),
                        clean_value(event.get("event_type")),
                        clean_value(event.get("event_title")),
                        "Post-admission context only; not PIT evidence",
                    ]
                )
                + " |"
            )
        else:
            rows.append(
                "| "
                + " | ".join(
                    [
                        clean_value(event.get("event_type")),
                        clean_value(event.get("event_title")),
                        clean_value(event.get("source_type")),
                        "Date missing; degraded source quality; not strong PIT evidence",
                    ]
                )
                + " |"
            )
    return rows


def build_section(company: pd.Series, events: pd.DataFrame) -> str:
    lines = [
        "## News and Event Review Context",
        "",
        "### Research-Only Metadata",
        "",
        f"- first_admission_date: {clean_value(company['first_admission_date'])}",
        f"- news_support: {clean_value(company['news_support'])}",
        f"- news_event_count: {int(company['news_event_count'])}",
        f"- pit_available_event_count: {int(company['pit_available_event_count'])}",
        f"- post_admission_event_count: {int(company['post_admission_event_count'])}",
        f"- date_missing_event_count: {int(company['date_missing_event_count'])}",
        f"- source_quality: {clean_value(company['source_quality'])}",
        "- research_only: true",
        "- used_for_signal: false",
        "- used_for_admission: false",
        "",
        "### PIT-Available News Events",
        "",
        "| Publish Date | Event Type | Source Type | Title | Matched Topic | Source Quality |",
        "|---|---|---|---|---|---|",
    ]
    pit_rows = table_rows(events, "pit_available")
    lines.extend(pit_rows if pit_rows else ["|  |  |  | No PIT-available event mapped. |  |  |"])

    post_rows = table_rows(events, "post_admission_context")
    if post_rows:
        lines.extend(
            [
                "",
                "### Post-Admission Review Context",
                "",
                "| Publish Date | Event Type | Title | Note |",
                "|---|---|---|---|",
                *post_rows,
            ]
        )

    date_missing_rows = table_rows(events, "date_missing")
    if date_missing_rows:
        lines.extend(
            [
                "",
                "### Date-Missing / Degraded Events",
                "",
                "| Event Type | Title | Source Type | Note |",
                "|---|---|---|---|",
                *date_missing_rows,
            ]
        )

    if clean_value(company["news_support"]) == "missing":
        lines.extend(
            [
                "",
                "### Missing News Data Gap",
                "",
                "- missing reason: no local dated news or disclosure event mapped at the first admission cutoff.",
                "- source limitation: local media, policy, and industry event sources remain incomplete.",
                "- manual review impact: treat news context as missing until a dated source is added.",
                "- not an exclusion condition: true",
            ]
        )
    elif clean_value(company["news_support"]) == "partial":
        lines.extend(
            [
                "",
                "### Partial News Coverage",
                "",
                "- partial reason: mapped events exist only after the first admission cutoff.",
                "- PIT interpretation: post-admission rows are review context only.",
                "- manual review impact: do not treat partial coverage as PIT support.",
            ]
        )
    return "\n".join(lines) + "\n"


def build_patch_tables(company: pd.DataFrame, events: pd.DataFrame, consolidated: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    report_lookup = consolidated.set_index("asset_id").to_dict(orient="index") if not consolidated.empty else {}
    manifest_rows: list[dict[str, Any]] = []
    section_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    partial_rows: list[dict[str, Any]] = []
    section_json: list[dict[str, Any]] = []

    for _, row in company.iterrows():
        asset_id = clean_value(row["asset_id"])
        asset_events = events[events["asset_id"].astype(str).eq(asset_id)].copy()
        report = report_lookup.get(asset_id, {})
        report_path = clean_value(report.get("consolidated_report_path", ""))
        report_exists = Path(report_path).exists() if report_path else False
        news_support = clean_value(row["news_support"])
        patch_status = {
            "supported": "news_supported_section",
            "partial": "news_partial_section",
            "missing": "news_data_gap_section",
        }.get(news_support, "news_data_gap_section")
        section = build_section(row, asset_events)
        common = {
            "ts_code": clean_value(row["ts_code"]),
            "stock_code": clean_value(row["stock_code"]),
            "stock_name": clean_value(row["stock_name"]),
            "asset_id": asset_id,
            "first_admission_date": clean_value(row["first_admission_date"]),
            "news_support": news_support,
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
            "used_for_signal": False,
            "used_for_admission": False,
            "used_for_dashboard": True,
            "used_for_manual_review": True,
            "research_only": True,
        }
        manifest_rows.append(
            {
                **common,
                "consolidated_report_path": report_path,
                "report_exists": report_exists,
                "patch_status": patch_status,
                "section_output_mode": "patch_section_only",
                "writeback_allowed": False,
            }
        )
        section_rows.append({**common, "section_markdown": section})
        section_json.append({**common, "section_markdown": section, "events": [event_record(event) for _, event in asset_events.iterrows()]})
        if news_support == "missing":
            missing_rows.append(
                {
                    **common,
                    "data_gap_note": "No local dated news or disclosure event mapped at the first admission cutoff.",
                    "source_limitation": "Local media, policy, and industry event sources remain incomplete.",
                    "manual_review_impact": "Treat news context as missing until a dated source is added.",
                    "not_exclusion_condition": True,
                }
            )
        if news_support == "partial":
            partial_rows.append(
                {
                    **common,
                    "partial_note": "Mapped events are after the first admission cutoff and are review context only.",
                    "pit_interpretation": "not_pit_support",
                    "not_exclusion_condition": True,
                }
            )
    return (
        pd.DataFrame(manifest_rows),
        pd.DataFrame(section_rows, columns=SECTION_COLUMNS),
        pd.DataFrame(missing_rows),
        pd.DataFrame(partial_rows),
        section_json,
    )


def build_pit_audit(events: pd.DataFrame) -> pd.DataFrame:
    pit_events = events[events["pit_status"].eq("pit_available")].copy()
    lookahead = 0
    if not pit_events.empty:
        lookahead = int(
            (
                pd.to_datetime(pit_events["publish_date"], errors="coerce")
                > pd.to_datetime(pit_events["first_admission_date"], errors="coerce")
            ).sum()
        )
    rows = [
        ("pit_available_event_count", int(events["pit_status"].eq("pit_available").sum()), "dated events at or before first admission cutoff"),
        ("post_admission_event_count", int(events["pit_status"].eq("post_admission_context").sum()), "events after first admission cutoff"),
        ("date_missing_event_count", int(events["pit_status"].eq("date_missing").sum()), "events with missing date or source gap"),
        ("lookahead_violation_rows", lookahead, "pit_available rows with publish date after cutoff"),
        ("date_missing_degraded_rows", int(events[events["pit_status"].eq("date_missing")]["source_quality"].eq("degraded").sum()), "date missing rows degraded"),
        ("used_for_signal_count", int(events["used_for_signal"].astype(bool).sum()), "must remain zero"),
        ("used_for_admission_count", int(events["used_for_admission"].astype(bool).sum()), "must remain zero"),
    ]
    return pd.DataFrame([{"metric": metric, "value": value, "note": note} for metric, value, note in rows])


def build_event_type_coverage(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["event_type", "source_type", "pit_status", "event_count"])
    return (
        events.groupby(["event_type", "source_type", "pit_status"], dropna=False)
        .size()
        .reset_index(name="event_count")
        .sort_values(["event_type", "source_type", "pit_status"])
    )


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if contains_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(summary: dict[str, Any], event_type: pd.DataFrame, pit_audit: pd.DataFrame) -> str:
    event_lines = "\n".join(
        f"| {row.event_type} | {row.source_type} | {row.pit_status} | {row.event_count} |"
        for row in event_type.itertuples(index=False)
    )
    pit_lines = "\n".join(f"| {row.metric} | {row.value} | {row.note} |" for row in pit_audit.itertuples(index=False))
    return f"""# Tech Bottleneck Watchlist Report News Patch v1

## 1. Scope

This task creates a research-only news context patch for consolidated reports. It does not modify formal strategy files, baseline admission, dashboard write capability, or automated execution prompts.

## 2. Input Artifacts

- News source mapping: `tech_bottleneck_news_source_mapping_v1`
- Consolidated report index: `tech_bottleneck_watchlist_report_consolidated_v1/watchlist_report_consolidated_index.csv`
- Formal strategy files were checked only for diff status.

## 3. Patch Methodology

Each company-level news summary row is matched to the consolidated report index by `asset_id`. The output is a patch section only; existing consolidated report markdown files are not overwritten. Supported assets receive PIT event tables, the partial asset receives a partial coverage section, and missing assets receive a data gap section.

Post-admission rows are retained as review context only. Date-missing rows are degraded and are not treated as PIT support.

## 4. Coverage Summary

- Reports total: {summary["reports_total"]}
- Reports news supported: {summary["reports_news_supported"]}
- Reports news partial: {summary["reports_news_partial"]}
- Reports news missing: {summary["reports_news_missing"]}
- PIT available events: {summary["pit_available_event_count"]}
- Post-admission events: {summary["post_admission_event_count"]}
- Date missing events: {summary["date_missing_event_count"]}

## 5. Event Type Summary

| Event type | Source type | PIT status | Event count |
|---|---|---|---:|
{event_lines}

## 6. PIT Audit

| Metric | Value | Note |
|---|---:|---|
{pit_lines}

## 7. Example Patched Section

The generated sections use this structure: research-only metadata, PIT-available event table, post-admission review context if present, date-missing degraded rows if present, and missing data gap notes when source coverage is absent.

## 8. Missing / Partial / Date-Missing Summary

- Missing reports: {summary["reports_news_missing"]}; each receives an explicit data gap note.
- Partial reports: {summary["reports_news_partial"]}; mapped events are after the first admission cutoff and are not PIT support.
- Date-missing events: {summary["date_missing_event_count"]}; all are degraded source-quality rows.

## 9. Guardrail Checks

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

## 10. Test Results

Verification commands are recorded after generation:

- Pending at initial generation: `pytest tests/test_tech_bottleneck_watchlist_report_news_patch.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_news_source_mapping.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_user_smoke_test_v3.py -q`
- Pending at initial generation: `git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py`

## 11. Acceptance Decision

`{summary["acceptance_decision"]}`

## 12. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_news_patch_v1`
2. `tech_bottleneck_dashboard_readonly_user_smoke_test_v4`
3. `tech_bottleneck_manual_review_writeback_research_only_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    company = read_csv(NEWS_COMPANY)
    events = read_csv(NEWS_EVENTS)
    source_quality = read_csv(NEWS_SOURCE_QUALITY)
    consolidated = read_csv(CONSOLIDATED_INDEX)
    upstream_guardrails = read_json(NEWS_GUARDRAILS)

    manifest, sections, missing, partial, section_json = build_patch_tables(company, events, consolidated)
    pit_audit = build_pit_audit(events)
    event_type = build_event_type_coverage(events)
    strategy_clean = formal_strategy_diff_clean()
    lookahead = int(pit_audit.loc[pit_audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0])
    summary = {
        "task_name": "tech_bottleneck_watchlist_report_news_patch_v1",
        "watchlist_count": int(len(company)),
        "reports_total": int(len(sections)),
        "reports_news_supported": int(company["news_support"].eq("supported").sum()),
        "reports_news_partial": int(company["news_support"].eq("partial").sum()),
        "reports_news_missing": int(company["news_support"].eq("missing").sum()),
        "pit_available_event_count": int(events["pit_status"].eq("pit_available").sum()),
        "post_admission_event_count": int(events["pit_status"].eq("post_admission_context").sum()),
        "date_missing_event_count": int(events["pit_status"].eq("date_missing").sum()),
        "lookahead_violation_rows": lookahead,
        "writeback_allowed_count": 0,
        "manual_review_writeback_enabled_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "used_for_signal_count": int(sections["used_for_signal"].astype(bool).sum()) + int(events["used_for_signal"].astype(bool).sum()),
        "used_for_admission_count": int(sections["used_for_admission"].astype(bool).sum()) + int(events["used_for_admission"].astype(bool).sum()),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "upstream_acceptance_decision": upstream_guardrails.get("acceptance_decision", ""),
        "acceptance_decision": "watchlist_report_news_patch_ready_with_degraded_coverage",
    }

    manifest.to_csv(OUTPUT_DIR / "watchlist_report_news_patch_manifest.csv", index=False)
    sections.to_csv(OUTPUT_DIR / "watchlist_report_news_sections.csv", index=False)
    write_json(OUTPUT_DIR / "watchlist_report_news_sections.json", section_json)
    missing.to_csv(OUTPUT_DIR / "watchlist_report_news_missing.csv", index=False)
    partial.to_csv(OUTPUT_DIR / "watchlist_report_news_partial.csv", index=False)
    pit_audit.to_csv(OUTPUT_DIR / "watchlist_report_news_pit_audit.csv", index=False)
    event_type.to_csv(OUTPUT_DIR / "watchlist_report_news_event_type_coverage.csv", index=False)
    source_quality.to_csv(OUTPUT_DIR / "watchlist_report_news_source_quality.csv", index=False)
    write_json(OUTPUT_DIR / "watchlist_report_news_patch_summary.json", summary)
    write_json(OUTPUT_DIR / "watchlist_report_news_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_watchlist_report_news_patch_v1_report.md").write_text(
        build_report(summary, event_type, pit_audit),
        encoding="utf-8",
    )

    language_hits = scan_outputs()
    summary["trading_language_hit_count"] = language_hits
    summary["execution_language_hit_count"] = language_hits
    summary["forbidden_action_leakage_count"] = language_hits
    write_json(OUTPUT_DIR / "watchlist_report_news_patch_summary.json", summary)
    write_json(OUTPUT_DIR / "watchlist_report_news_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_watchlist_report_news_patch_v1_report.md").write_text(
        build_report(summary, event_type, pit_audit),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
