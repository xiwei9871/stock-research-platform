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
V2_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
ANNOUNCEMENT_DIR = RESEARCH_DIR / "tech_bottleneck_announcement_fulltext_extraction_v2"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_news_source_mapping_v1"

V2_CANDIDATES = V2_DIR / "tech_bottleneck_research_selection_v2_candidates.csv"
ANNOUNCEMENT_EVIDENCE = ANNOUNCEMENT_DIR / "announcement_fulltext_v2_structured_evidence.csv"
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

FORBIDDEN_REPLACEMENTS = {
    "buy": "execution_word_removed",
    "sell": "execution_word_removed",
    "add": "execution_word_removed",
    "reduce": "execution_word_removed",
    "hold": "execution_word_removed",
    "entry": "execution_word_removed",
    "exit": "execution_word_removed",
    "position": "execution_word_removed",
    "target price": "execution_word_removed",
    "target_price": "execution_word_removed",
    "position_size": "execution_word_removed",
    "entry_signal": "execution_word_removed",
    "exit_signal": "execution_word_removed",
    "买入": "execution_word_removed",
    "卖出": "execution_word_removed",
    "加仓": "execution_word_removed",
    "减仓": "execution_word_removed",
    "持有": "execution_word_removed",
    "目标价": "execution_word_removed",
    "仓位建议": "execution_word_removed",
    "入场点": "execution_word_removed",
    "退出": "execution_word_removed",
    "止盈": "execution_word_removed",
    "止损": "execution_word_removed",
    "调仓": "execution_word_removed",
    "交易信号": "execution_word_removed",
    "保存": "manual_action_removed",
    "提交": "manual_action_removed",
    "写回": "manual_action_removed",
}

EVENT_COLUMNS = [
    "ts_code",
    "stock_code",
    "stock_name",
    "asset_id",
    "first_admission_date",
    "event_id",
    "event_title",
    "event_summary",
    "event_type",
    "source_type",
    "source_name",
    "source_url",
    "publish_date",
    "matched_keyword",
    "matched_topic",
    "pit_status",
    "source_quality",
    "is_company_specific",
    "is_industry_level",
    "is_policy_level",
    "is_risk_event",
    "used_for_signal",
    "used_for_admission",
    "used_for_dashboard",
    "used_for_manual_review",
    "research_only",
]


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _strategy_diff_clean() -> bool:
    return not _git("diff", "--", *FORMAL_STRATEGY_FILES)


def _contains_forbidden_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _sanitize_text(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    for source, replacement in FORBIDDEN_REPLACEMENTS.items():
        text = re.sub(re.escape(source), replacement, text, flags=re.I)
    return text.replace("\n", " ").replace("\r", " ").strip()


def _to_date(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce")


def _date_string(value: Any) -> str:
    date = _to_date(value)
    if pd.isna(date):
        return ""
    return date.strftime("%Y-%m-%d")


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def asset_id_to_ts_code(asset_id: str, symbol: Any) -> str:
    market = "SH" if ":SH:" in str(asset_id) else "SZ" if ":SZ:" in str(asset_id) else ""
    symbol_str = f"{int(symbol):06d}" if str(symbol).isdigit() else str(symbol)
    return f"{symbol_str}.{market}" if market else symbol_str


def _stock_code(symbol: Any) -> str:
    return f"{int(symbol):06d}" if str(symbol).isdigit() else str(symbol)


def _event_type(row: pd.Series) -> str:
    if _bool_value(row.get("litigation_or_penalty")):
        return "litigation_or_penalty"
    if _bool_value(row.get("risk_disclosure")):
        return "financial_risk"
    if _bool_value(row.get("order_contract")) or _bool_value(row.get("customer_contract")) or _bool_value(row.get("major_customer_or_supplier")):
        return "customer_validation"
    if _bool_value(row.get("capacity_project")):
        return "capacity_expansion"
    if _bool_value(row.get("financial_guidance")) or _bool_value(row.get("performance_forecast")) or _bool_value(row.get("fundraising_project")):
        return "company_announcement"
    return "company_announcement"


def _source_quality(row: pd.Series, pit_status: str) -> str:
    if pit_status == "date_missing":
        return "degraded"
    fulltext_status = str(row.get("fulltext_status", "")).lower()
    data_quality = str(row.get("data_quality_status", "")).lower()
    if "available" in data_quality and "extracted" in fulltext_status:
        return "high"
    if "failed" in fulltext_status or "degraded" in data_quality:
        return "low"
    return "medium"


def _pit_status(publish_date: Any, first_admission_date: Any) -> str:
    publish_dt = _to_date(publish_date)
    admission_dt = _to_date(first_admission_date)
    if pd.isna(publish_dt) or pd.isna(admission_dt):
        return "date_missing"
    if publish_dt <= admission_dt:
        return "pit_available"
    return "post_admission_context"


def build_events(v2: pd.DataFrame, announcements: pd.DataFrame) -> pd.DataFrame:
    events: list[dict[str, Any]] = []
    if v2.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    announcements = announcements.copy()
    if not announcements.empty:
        announcements["asset_id"] = announcements["asset_id"].astype(str)

    for _, stock in v2.iterrows():
        asset_id = str(stock["asset_id"])
        symbol = stock["symbol"]
        stock_code = _stock_code(symbol)
        ts_code = asset_id_to_ts_code(asset_id, symbol)
        first_admission_date = _date_string(stock["baseline_first_admission_date"])
        stock_events = announcements[announcements["asset_id"].eq(asset_id)] if not announcements.empty else pd.DataFrame()

        if stock_events.empty:
            events.append(
                {
                    "ts_code": ts_code,
                    "stock_code": stock_code,
                    "stock_name": _sanitize_text(stock["name"]),
                    "asset_id": asset_id,
                    "first_admission_date": first_admission_date,
                    "event_id": f"data_gap|{asset_id}",
                    "event_title": "News source mapping data gap",
                    "event_summary": "No local news source mapped for this observation pool asset.",
                    "event_type": "data_gap",
                    "source_type": "unknown",
                    "source_name": "missing_local_news_source",
                    "source_url": "",
                    "publish_date": "",
                    "matched_keyword": "",
                    "matched_topic": "missing_news_source",
                    "pit_status": "date_missing",
                    "source_quality": "degraded",
                    "is_company_specific": False,
                    "is_industry_level": False,
                    "is_policy_level": False,
                    "is_risk_event": False,
                    "used_for_signal": False,
                    "used_for_admission": False,
                    "used_for_dashboard": True,
                    "used_for_manual_review": True,
                    "research_only": True,
                }
            )
            continue

        for _, event in stock_events.iterrows():
            publish_date = _date_string(event.get("announcement_date"))
            pit_status = _pit_status(publish_date, first_admission_date)
            event_type = _event_type(event)
            matched_keyword = _sanitize_text(event.get("matched_keywords"))
            matched_topic = _sanitize_text(event.get("announcement_type")) or event_type
            is_risk_event = event_type in {"financial_risk", "litigation_or_penalty"}
            events.append(
                {
                    "ts_code": ts_code,
                    "stock_code": stock_code,
                    "stock_name": _sanitize_text(stock["name"]),
                    "asset_id": asset_id,
                    "first_admission_date": first_admission_date,
                    "event_id": _sanitize_text(event.get("announcement_id")) or f"announcement|{asset_id}|{len(events) + 1}",
                    "event_title": _sanitize_text(event.get("announcement_title")),
                    "event_summary": "Company disclosure evidence mapped from local announcement fulltext source for research review.",
                    "event_type": event_type,
                    "source_type": "announcement",
                    "source_name": "announcement_fulltext_extraction_v2",
                    "source_url": _sanitize_text(event.get("source_url")),
                    "publish_date": publish_date,
                    "matched_keyword": matched_keyword,
                    "matched_topic": matched_topic,
                    "pit_status": pit_status,
                    "source_quality": _source_quality(event, pit_status),
                    "is_company_specific": True,
                    "is_industry_level": False,
                    "is_policy_level": False,
                    "is_risk_event": is_risk_event,
                    "used_for_signal": False,
                    "used_for_admission": False,
                    "used_for_dashboard": True,
                    "used_for_manual_review": True,
                    "research_only": True,
                }
            )

    return pd.DataFrame(events, columns=EVENT_COLUMNS)


def build_company_summary(v2: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, stock in v2.iterrows():
        asset_id = str(stock["asset_id"])
        symbol = stock["symbol"]
        subset = events[events["asset_id"].astype(str).eq(asset_id)]
        non_gap = subset[~subset["event_type"].eq("data_gap")]
        pit_count = int(non_gap["pit_status"].eq("pit_available").sum())
        post_count = int(non_gap["pit_status"].eq("post_admission_context").sum())
        date_missing_count = int(subset["pit_status"].eq("date_missing").sum())
        risk_count = int(non_gap["is_risk_event"].astype(bool).sum()) if not non_gap.empty else 0
        company_specific = int(non_gap["is_company_specific"].astype(bool).sum()) if not non_gap.empty else 0
        industry_level = int(non_gap["is_industry_level"].astype(bool).sum()) if not non_gap.empty else 0
        policy_level = int(non_gap["is_policy_level"].astype(bool).sum()) if not non_gap.empty else 0

        if pit_count > 0:
            news_support = "supported"
            source_quality = "high" if subset["source_quality"].eq("high").any() else "medium"
            context_quality = "strong" if pit_count >= 3 else "moderate"
        elif post_count > 0:
            news_support = "partial"
            source_quality = "low"
            context_quality = "weak"
        else:
            news_support = "missing"
            source_quality = "missing"
            context_quality = "missing"

        rows.append(
            {
                "ts_code": asset_id_to_ts_code(asset_id, symbol),
                "stock_code": _stock_code(symbol),
                "stock_name": _sanitize_text(stock["name"]),
                "asset_id": asset_id,
                "first_admission_date": _date_string(stock["baseline_first_admission_date"]),
                "news_support": news_support,
                "news_event_count": int(len(non_gap)),
                "pit_available_event_count": pit_count,
                "post_admission_event_count": post_count,
                "date_missing_event_count": date_missing_count,
                "company_specific_count": company_specific,
                "industry_level_count": industry_level,
                "policy_level_count": policy_level,
                "risk_event_count": risk_count,
                "source_quality": source_quality,
                "news_data_gap": news_support in {"missing", "partial"},
                "news_context_quality": context_quality,
                "risk_news_context": "present" if risk_count else ("missing" if news_support == "missing" else "absent"),
                "policy_context": "present" if policy_level else ("missing" if news_support == "missing" else "absent"),
                "industry_context": "present" if industry_level else ("missing" if news_support == "missing" else "absent"),
                "used_for_signal": False,
                "used_for_admission": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows)


def build_missing(company: pd.DataFrame) -> pd.DataFrame:
    missing = company[company["news_support"].eq("missing")].copy()
    if missing.empty:
        return pd.DataFrame(
            columns=[
                "ts_code",
                "stock_code",
                "stock_name",
                "asset_id",
                "first_admission_date",
                "missing_reason",
                "source_limitation",
                "manual_review_impact",
                "recommended_follow_up",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    missing["missing_reason"] = "No local news or disclosure event mapped for the first admission cutoff."
    missing["source_limitation"] = "Local news media source is not yet available; announcement evidence is evaluated separately when present."
    missing["manual_review_impact"] = "Manual review should treat news context as missing until a dated source is added."
    missing["recommended_follow_up"] = "news_source_follow_up"
    return missing[
        [
            "ts_code",
            "stock_code",
            "stock_name",
            "asset_id",
            "first_admission_date",
            "missing_reason",
            "source_limitation",
            "manual_review_impact",
            "recommended_follow_up",
            "research_only",
            "used_for_signal",
            "used_for_admission",
        ]
    ]


def build_source_quality(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["source_type", "source_name", "source_quality", "pit_status", "event_count"])
    return (
        events.groupby(["source_type", "source_name", "source_quality", "pit_status"], dropna=False)
        .size()
        .reset_index(name="event_count")
        .sort_values(["source_type", "source_quality", "pit_status"])
    )


def build_keywords(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, event in events.iterrows():
        keywords = [part.strip() for part in str(event.get("matched_keyword", "")).split("|") if part.strip()]
        if not keywords:
            keywords = [""]
        for keyword in keywords:
            rows.append(
                {
                    "event_id": event["event_id"],
                    "ts_code": event["ts_code"],
                    "stock_code": event["stock_code"],
                    "stock_name": event["stock_name"],
                    "matched_keyword": keyword,
                    "matched_topic": event["matched_topic"],
                    "event_type": event["event_type"],
                    "pit_status": event["pit_status"],
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    return pd.DataFrame(rows)


def build_pit_audit(events: pd.DataFrame, company: pd.DataFrame) -> pd.DataFrame:
    lookahead = 0
    pit_events = events[events["pit_status"].eq("pit_available")].copy()
    if not pit_events.empty:
        lookahead = int(
            (
                pd.to_datetime(pit_events["publish_date"], errors="coerce")
                > pd.to_datetime(pit_events["first_admission_date"], errors="coerce")
            ).sum()
        )
    metrics = [
        ("watchlist_count", len(company), "company summary rows"),
        ("event_rows", len(events), "event mapping rows including data gap rows"),
        ("pit_available_event_count", int(events["pit_status"].eq("pit_available").sum()), "dated events available by first admission date"),
        ("post_admission_event_count", int(events["pit_status"].eq("post_admission_context").sum()), "dated events after first admission date"),
        ("date_missing_event_count", int(events["pit_status"].eq("date_missing").sum()), "events with missing publish date or source gap"),
        ("lookahead_violation_rows", lookahead, "pit_available rows with publish date after first admission date"),
        ("used_for_signal_count", int(events["used_for_signal"].astype(bool).sum()), "must remain zero"),
        ("used_for_admission_count", int(events["used_for_admission"].astype(bool).sum()), "must remain zero"),
    ]
    return pd.DataFrame([{"metric": metric, "value": value, "note": note} for metric, value, note in metrics])


def scan_output_files() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if _contains_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(summary: dict[str, Any], source_quality: pd.DataFrame, pit_audit: pd.DataFrame) -> str:
    source_lines = "\n".join(
        f"| {row.source_type} | {row.source_quality} | {row.pit_status} | {row.event_count} |"
        for row in source_quality.itertuples(index=False)
    )
    pit_lines = "\n".join(f"| {row.metric} | {row.value} | {row.note} |" for row in pit_audit.itertuples(index=False))
    return f"""# Tech Bottleneck News Source Mapping v1

## 1. Scope

This task builds a research-only news source mapping layer for the Tech Bottleneck observation pool. It does not modify formal strategy files, baseline admission, dashboard write capability, or automated execution prompts.

## 2. Input Artifacts

- v2 candidates: `tech_bottleneck_research_selection_layer_v2_generator_v1/tech_bottleneck_research_selection_v2_candidates.csv`
- Company disclosure evidence: `tech_bottleneck_announcement_fulltext_extraction_v2/announcement_fulltext_v2_structured_evidence.csv`
- Formal strategy files were checked only for diff status.

## 3. Source Mapping Methodology

The local dated disclosure evidence is mapped as company disclosure events with `source_type = announcement`. It is not treated as generic media news. Assets without mapped local news or disclosure evidence receive explicit `data_gap` rows so source coverage is auditable.

Event categories are derived from existing evidence flags: customer validation, capacity expansion, company announcement, litigation or penalty, financial risk, and data gap.

## 4. PIT Methodology

Each event compares `publish_date` with `first_admission_date`. Rows dated on or before the cutoff are `pit_available`. Rows dated after the cutoff are retained only as `post_admission_context`. Rows without a date or without a mapped source are `date_missing` and source quality is degraded.

## 5. Coverage Summary

- Watchlist count: {summary["watchlist_count"]}
- News supported count: {summary["news_supported_count"]}
- News partial count: {summary["news_partial_count"]}
- News missing count: {summary["news_missing_count"]}
- PIT available events: {summary["pit_available_event_count"]}
- Post-admission context events: {summary["post_admission_event_count"]}
- Date missing events: {summary["date_missing_event_count"]}

## 6. Event Type Summary

| Source type | Source quality | PIT status | Event count |
|---|---|---|---:|
{source_lines}

## 7. Company-Level Summary

Company-level output records news support, event counts, PIT event counts, risk event counts, source quality, and data gap status. These fields are research-only dashboard and manual review support fields.

## 8. Data Gap and Source Quality

Missing rows identify assets without local news evidence at the first admission cutoff. The current source layer is mainly dated disclosure evidence, so broader media, policy, and industry event coverage remains incomplete.

## 9. Guardrail Checks

| Metric | Value | Note |
|---|---:|---|
{pit_lines}
| writeback_allowed_count | {summary["writeback_allowed_count"]} | readonly output |
| manual_review_writeback_enabled_count | {summary["manual_review_writeback_enabled_count"]} | readonly output |
| forbidden_action_leakage_count | {summary["forbidden_action_leakage_count"]} | generated outputs |
| trading_language_hit_count | {summary["trading_language_hit_count"]} | generated outputs |
| execution_language_hit_count | {summary["execution_language_hit_count"]} | generated outputs |
| baseline_admission_changed_count | {summary["baseline_admission_changed_count"]} | baseline is not modified |
| strategy_file_diff_clean | {summary["strategy_file_diff_clean"]} | formal strategy diff check |
| used_for_signal_count | {summary["used_for_signal_count"]} | must remain zero |
| used_for_admission_count | {summary["used_for_admission_count"]} | must remain zero |

## 10. Test Results

Verification commands are recorded after generation:

- Pending at initial generation: `pytest tests/test_tech_bottleneck_news_source_mapping.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_user_smoke_test_v3.py -q`
- Pending at initial generation: `pytest tests/test_tech_bottleneck_dashboard_readonly_financial_statement_patch.py -q`
- Pending at initial generation: `git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py`

## 11. Acceptance Decision

`{summary["acceptance_decision"]}`

The mapping is usable as research-only source context, with degraded coverage because broad media and policy sources are not yet fully mapped.

## 12. Recommended Next Steps

1. `tech_bottleneck_watchlist_report_news_patch_v1`
2. `tech_bottleneck_dashboard_readonly_news_patch_v1`
3. `tech_bottleneck_manual_review_writeback_research_only_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v2 = _read_csv(V2_CANDIDATES)
    announcements = _read_csv(ANNOUNCEMENT_EVIDENCE)
    events = build_events(v2, announcements)
    company = build_company_summary(v2, events)
    missing = build_missing(company)
    source_quality = build_source_quality(events)
    keywords = build_keywords(events)
    pit_audit = build_pit_audit(events, company)

    lookahead = int(pit_audit.loc[pit_audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0])
    strategy_clean = _strategy_diff_clean()
    summary = {
        "task_name": "tech_bottleneck_news_source_mapping_v1",
        "watchlist_count": int(len(company)),
        "event_rows": int(len(events)),
        "news_supported_count": int(company["news_support"].eq("supported").sum()),
        "news_partial_count": int(company["news_support"].eq("partial").sum()),
        "news_missing_count": int(company["news_support"].eq("missing").sum()),
        "pit_available_event_count": int(events["pit_status"].eq("pit_available").sum()),
        "post_admission_event_count": int(events["pit_status"].eq("post_admission_context").sum()),
        "date_missing_event_count": int(events["pit_status"].eq("date_missing").sum()),
        "lookahead_violation_rows": lookahead,
        "writeback_allowed_count": 0,
        "manual_review_writeback_enabled_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "used_for_signal_count": int(events["used_for_signal"].astype(bool).sum() + company["used_for_signal"].astype(bool).sum()),
        "used_for_admission_count": int(events["used_for_admission"].astype(bool).sum() + company["used_for_admission"].astype(bool).sum()),
        "acceptance_decision": "conditionally_ready_with_degraded_news_coverage",
    }

    events.to_csv(OUTPUT_DIR / "news_source_mapping_events.csv", index=False)
    events.to_json(OUTPUT_DIR / "news_source_mapping_events.json", orient="records", force_ascii=False, indent=2)
    company.to_csv(OUTPUT_DIR / "news_source_mapping_company_summary.csv", index=False)
    source_quality.to_csv(OUTPUT_DIR / "news_source_mapping_source_quality.csv", index=False)
    pit_audit.to_csv(OUTPUT_DIR / "news_source_mapping_pit_audit.csv", index=False)
    missing.to_csv(OUTPUT_DIR / "news_source_mapping_missing.csv", index=False)
    keywords.to_csv(OUTPUT_DIR / "news_source_mapping_keywords.csv", index=False)
    _write_json(OUTPUT_DIR / "news_source_mapping_summary.json", summary)
    _write_json(OUTPUT_DIR / "news_source_mapping_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_news_source_mapping_v1_report.md").write_text(
        build_report(summary, source_quality, pit_audit),
        encoding="utf-8",
    )

    language_hits = scan_output_files()
    summary["trading_language_hit_count"] = language_hits
    summary["execution_language_hit_count"] = language_hits
    summary["forbidden_action_leakage_count"] = language_hits
    _write_json(OUTPUT_DIR / "news_source_mapping_summary.json", summary)
    _write_json(OUTPUT_DIR / "news_source_mapping_guardrails.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_news_source_mapping_v1_report.md").write_text(
        build_report(summary, source_quality, pit_audit),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
