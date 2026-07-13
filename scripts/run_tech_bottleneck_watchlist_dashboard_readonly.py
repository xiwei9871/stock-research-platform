#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
CONSOLIDATED_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_consolidated_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_dashboard_readonly_v1"
RULE_VERSION = "tech_bottleneck_watchlist_dashboard_readonly_v1"
SNAPSHOT_DATE = "2026-07-01"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]

ALLOWED_REVIEW_ACTIONS = {
    "review_consolidated_report",
    "review_thesis",
    "review_specific_risk_event",
    "review_fundamental_risk",
    "review_pe_not_meaningful",
    "review_valuation_discrepancy",
    "request_more_sources",
    "manual_review_required",
}


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _safe(value: Any, default: str = "missing") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value)
    return text if text else default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _num(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count_values(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.fillna("missing").value_counts(dropna=False).sort_index().items()}


def _filter_options(table: pd.DataFrame, field: str) -> dict[str, Any]:
    if field not in table.columns:
        return {"field": field, "options": []}
    counts = table[field].fillna("missing").astype(str).value_counts(dropna=False).sort_index()
    return {"field": field, "options": [{"value": str(k), "count": int(v)} for k, v in counts.items()]}


def _git_lines(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        return f"git unavailable: {exc}"
    return (result.stdout or result.stderr or "").strip()


def load_consolidated() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_index.csv")
    summary = _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_summary_by_asset.csv")
    audit = _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_quality_audit.csv")
    preview = _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_dashboard_preview.csv")
    return index, summary, audit, preview


def build_summary(index: pd.DataFrame, summary: pd.DataFrame, audit: pd.DataFrame) -> dict[str, Any]:
    lookup = dict(zip(audit.get("metric", []), audit.get("value", [])))
    return {
        "snapshot_date": SNAPSHOT_DATE,
        "watchlist_count": int(len(index)),
        "consolidated_report_count": int(len(index)),
        "announcement_fulltext_support_count": int(index["announcement_fulltext_support"].astype(bool).sum()),
        "fundamental_support_count": int(index["fundamental_support"].astype(bool).sum()),
        "baostock_valuation_support_count": int(index["baostock_valuation_support"].astype(bool).sum()),
        "baidu_validation_support_count": int(index["baidu_validation_support"].astype(bool).sum()),
        "specific_validation_count": int(index["specific_validation_count"].sum()),
        "specific_risk_event_count": int(index["specific_risk_event_count"].sum()),
        "recovery_distribution": _count_values(index["fundamental_recovery_signal"]),
        "fundamental_risk_distribution": _count_values(index["fundamental_risk_level"]),
        "fundamental_quality_distribution": _count_values(index["fundamental_quality_level"]),
        "pe_meaningfulness_distribution": _count_values(index["pe_meaningfulness"]),
        "valuation_context_distribution": _count_values(index["valuation_context_level"]),
        "baidu_validation_distribution": _count_values(index["baidu_validation_status"]),
        "degraded_source_warning": "degraded-source warning required: announcement, derived fundamental, valuation validation, and missing source gaps remain visible.",
        "lookahead_violation_rows": int(float(lookup.get("lookahead violation rows", 0))),
        "trading_signal_present": False,
        "rule_version": RULE_VERSION,
    }


def build_table(index: pd.DataFrame, summary: pd.DataFrame, preview: pd.DataFrame) -> pd.DataFrame:
    table = preview.copy()
    keep = [
        "snapshot_date",
        "asset_id",
        "symbol",
        "name",
        "research_priority",
        "one_line_summary",
        "theme",
        "announcement_status",
        "fundamental_status",
        "valuation_status",
        "baidu_validation_status",
        "main_risk_summary",
        "main_missing_data",
        "recommended_review_action",
        "consolidated_report_path",
    ]
    table = table[[c for c in keep if c in table.columns]].copy()
    table = table.merge(
        summary[
            [
                "asset_id",
                "announcement_evidence_quality",
                "specific_validation_count",
                "specific_risk_event_count",
                "fundamental_support",
                "fundamental_recovery_signal",
                "fundamental_risk_level",
                "fundamental_quality_level",
                "pe_meaningfulness",
                "valuation_context_level",
                "cross_source_discrepancy_flag",
                "forward_30d_return",
                "forward_60d_return",
                "forward_90d_return",
                "forward_120d_return",
                "data_quality_status",
            ]
        ],
        on="asset_id",
        how="left",
    )
    table["human_review_required"] = True
    table["recommended_review_action"] = table["recommended_review_action"].where(
        table["recommended_review_action"].isin(ALLOWED_REVIEW_ACTIONS), "manual_review_required"
    )
    ordered = [
        "snapshot_date",
        "asset_id",
        "symbol",
        "name",
        "research_priority",
        "theme",
        "one_line_summary",
        "announcement_status",
        "announcement_evidence_quality",
        "specific_validation_count",
        "specific_risk_event_count",
        "fundamental_status",
        "fundamental_recovery_signal",
        "fundamental_risk_level",
        "fundamental_quality_level",
        "valuation_status",
        "pe_meaningfulness",
        "valuation_context_level",
        "baidu_validation_status",
        "cross_source_discrepancy_flag",
        "forward_30d_return",
        "forward_60d_return",
        "forward_90d_return",
        "forward_120d_return",
        "main_risk_summary",
        "main_missing_data",
        "recommended_review_action",
        "consolidated_report_path",
        "data_quality_status",
        "human_review_required",
    ]
    return table[ordered]


def build_cards(table: pd.DataFrame) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for _, row in table.iterrows():
        cards.append(
            {
                "asset_id": _safe(row.get("asset_id")),
                "symbol": _safe(row.get("symbol")),
                "name": _safe(row.get("name")),
                "card_title": f"{_safe(row.get('name'))} research review card",
                "one_line_summary": _safe(row.get("one_line_summary")),
                "why_in_watchlist": f"进入观察池主题：{_safe(row.get('theme'))}; priority={_safe(row.get('research_priority'))}.",
                "theme_summary": _safe(row.get("theme")),
                "announcement_summary": f"{_safe(row.get('announcement_status'))}; specific_validation={_safe(row.get('specific_validation_count'), '0')}; specific_risk_event={_safe(row.get('specific_risk_event_count'), '0')}.",
                "fundamental_summary": f"{_safe(row.get('fundamental_status'))}; recovery={_safe(row.get('fundamental_recovery_signal'))}; risk={_safe(row.get('fundamental_risk_level'))}; quality={_safe(row.get('fundamental_quality_level'))}.",
                "valuation_summary": f"{_safe(row.get('valuation_status'))}; PE={_safe(row.get('pe_meaningfulness'))}; context={_safe(row.get('valuation_context_level'))}.",
                "validation_summary": f"Baidu validation={_safe(row.get('baidu_validation_status'))}; discrepancy={_safe(row.get('cross_source_discrepancy_flag'))}.",
                "forward_return_context": (
                    f"30/60/90/120d post-review values: {_safe(row.get('forward_30d_return'))}, "
                    f"{_safe(row.get('forward_60d_return'))}, {_safe(row.get('forward_90d_return'))}, "
                    f"{_safe(row.get('forward_120d_return'))}. 仅用于事后复盘，不暗示未来收益。"
                ),
                "data_quality_summary": f"{_safe(row.get('data_quality_status'))}; missing={_safe(row.get('main_missing_data'))}.",
                "review_questions": [
                    "thesis 是否需要补 source？",
                    "公告 evidence 是否需要人工复核？",
                    "基本面风险是否需要更多明细字段？",
                    "BaoStock/Baidu 估值上下文是否一致？",
                    "是否需要 news 或 full financial statement source？",
                ],
                "recommended_review_action": _safe(row.get("recommended_review_action")),
                "consolidated_report_path": _safe(row.get("consolidated_report_path")),
            }
        )
    return cards


def build_filters(table: pd.DataFrame) -> dict[str, Any]:
    filter_fields = [
        "research_priority",
        "announcement_status",
        "announcement_evidence_quality",
        "fundamental_support",
        "fundamental_recovery_signal",
        "fundamental_risk_level",
        "fundamental_quality_level",
        "pe_meaningfulness",
        "valuation_context_level",
        "baidu_validation_status",
        "cross_source_discrepancy_flag",
        "human_review_required",
        "data_quality_status",
    ]
    return {field: _filter_options(table, field) for field in filter_fields}


def build_warnings() -> list[dict[str, Any]]:
    return [
        {
            "warning_id": "not_trading_signal",
            "severity": "critical",
            "title": "Research-only review boundary",
            "message": "This data pack is read-only research context and does not provide automated execution prompts.",
            "affected_sections": ["summary", "table", "cards", "report_links"],
            "recommended_review_action": "review_consolidated_report",
        },
        {
            "warning_id": "research_only",
            "severity": "critical",
            "title": "Research-only data pack",
            "message": "Use this package for internal review, source coverage, and manual replay only.",
            "affected_sections": ["all"],
            "recommended_review_action": "review_consolidated_report",
        },
        {
            "warning_id": "degraded_source_warning",
            "severity": "high",
            "title": "Degraded source coverage remains",
            "message": "Announcement, fundamental, valuation validation, and missing source gaps must remain visible in UI.",
            "affected_sections": ["summary", "table", "cards"],
            "recommended_review_action": "request_more_sources",
        },
        {
            "warning_id": "fundamental_derived_feature_warning",
            "severity": "high",
            "title": "Derived PIT fundamental features",
            "message": "Fundamental data is derived PIT feature context and not full financial statement evidence.",
            "affected_sections": ["fundamental_status", "cards"],
            "recommended_review_action": "review_fundamental_risk",
        },
        {
            "warning_id": "valuation_cross_source_warning",
            "severity": "medium",
            "title": "Valuation validation is auxiliary",
            "message": "BaoStock remains primary; Baidu is auxiliary and does not validate PS/PS-TTM.",
            "affected_sections": ["valuation_status", "baidu_validation_status"],
            "recommended_review_action": "review_valuation_discrepancy",
        },
        {
            "warning_id": "forward_return_backtest_context_warning",
            "severity": "medium",
            "title": "Forward return is post-review context",
            "message": "Forward return fields are historical replay fields and must not be framed as prediction.",
            "affected_sections": ["forward_return_context"],
            "recommended_review_action": "review_consolidated_report",
        },
        {
            "warning_id": "missing_news_source_warning",
            "severity": "medium",
            "title": "News source missing",
            "message": "News source mapping has not been added to this data pack.",
            "affected_sections": ["cards", "warnings"],
            "recommended_review_action": "request_more_sources",
        },
        {
            "warning_id": "missing_full_financial_statement_warning",
            "severity": "medium",
            "title": "Full financial statement source missing",
            "message": "Raw revenue, profit, cashflow, inventory, receivable, R&D and capex detail remain missing.",
            "affected_sections": ["fundamental_status", "cards"],
            "recommended_review_action": "request_more_sources",
        },
        {
            "warning_id": "formal_strategy_file_untracked_warning",
            "severity": "medium",
            "title": "Formal strategy files are untracked",
            "message": "Current git status shows formal strategy files as untracked; this task does not write those paths.",
            "affected_sections": ["contract", "appendix"],
            "recommended_review_action": "manual_review_required",
        },
    ]


def build_report_links(index: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in index.iterrows():
        path = Path(_safe(row.get("consolidated_report_path"), ""))
        exists = path.exists()
        text = path.read_text(encoding="utf-8", errors="ignore") if exists else ""
        rows.append(
            {
                "asset_id": _safe(row.get("asset_id")),
                "symbol": _safe(row.get("symbol")),
                "name": _safe(row.get("name")),
                "consolidated_report_path": str(path),
                "report_exists": exists,
                "report_file_size": path.stat().st_size if exists else 0,
                "report_status": "available" if exists else "missing",
                "contains_trading_language": contains_actionable_trading_language(text),
            }
        )
    return pd.DataFrame(rows)


def render_contract(summary: dict[str, Any], filters: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Watchlist Read-only Dashboard Contract v1

## 1. Page Positioning

Page name: Tech Bottleneck Watchlist Review

Positioning:
- read-only watchlist review page
- shows technology bottleneck research files
- does not show automated execution prompts
- does not show execution recommendations
- does not change any strategy ranking

## 2. Recommended Page Sections

1. Snapshot Summary
2. Degraded Source Warning Banner
3. Watchlist Table
4. Stock Review Cards
5. Source Coverage Summary
6. Risk Review Queue
7. Valuation Cross-source Validation
8. Forward Return Context
9. Report Links

## 3. Summary Metrics

- watchlist_count: {summary['watchlist_count']}
- consolidated_report_count: {summary['consolidated_report_count']}
- announcement_fulltext_support_count: {summary['announcement_fulltext_support_count']}
- fundamental_support_count: {summary['fundamental_support_count']}
- baostock_valuation_support_count: {summary['baostock_valuation_support_count']}
- baidu_validation_support_count: {summary['baidu_validation_support_count']}
- lookahead_violation_rows: {summary['lookahead_violation_rows']}

## 4. Table Columns

The table should use `tech_bottleneck_dashboard_table.csv` as its source and display research priority, theme, source coverage, risk context, valuation context, validation status, missing data, review action, and report path.

## 5. Card Fields

Cards should use `tech_bottleneck_dashboard_cards.json` and show why-in-watchlist, theme, announcement, fundamental, valuation, validation, forward-return post-review context, data-quality summary, review questions, and report path.

## 6. Filters

Available filter groups: {', '.join(filters.keys())}

## 7. Warning Banners

Use `tech_bottleneck_dashboard_warnings.json`. Required banners include research-only boundary, degraded-source warning, derived fundamental warning, valuation validation warning, forward-return replay warning, missing news, missing full financial statement, and formal strategy file status warning.

## 8. Allowed User Actions

- open report
- filter watchlist
- sort watchlist
- copy report path
- mark for offline review; this task does not implement writeback
- request more sources; this task does not implement writeback

## 9. Forbidden UI Elements

Any automated execution controls, portfolio sizing controls, quote-level execution controls, strategy score override controls, or Top5 replacement controls are forbidden. Do not repeat constrained execution vocabulary in UI copy.

## 10. Data Refresh

Data source: `outputs/research/tech_bottleneck_watchlist_report_consolidated_v1/`

This task does not implement automatic refresh.

## 11. Dashboard Readiness

- read_only_internal_review: ready
- daily_review_lite: conditionally ready with warning
- production_dashboard: not ready

## 12. Next Phase

- manual_review_label_schema_v1
- dashboard_readonly_integration
- full_financial_statement_source_adapter
- news_source_mapping
"""


def _git_status() -> tuple[str, str]:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py")
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py")
    return status or "clean", diff or "empty"


def render_main_report(summary: dict[str, Any], warnings: list[dict[str, Any]], links: pd.DataFrame) -> str:
    status, diff = _git_status()
    warning_ids = ", ".join(item["warning_id"] for item in warnings)
    return f"""# Tech Bottleneck Watchlist Dashboard Read-only v1

## 1. Executive Summary

Dashboard-ready data pack generated for 102 standard watchlist assets. Consolidated report count is {summary['consolidated_report_count']}; announcement fulltext support is {summary['announcement_fulltext_support_count']}/102; fundamental support is {summary['fundamental_support_count']}/102; BaoStock valuation support is {summary['baostock_valuation_support_count']}/102; Baidu validation support is {summary['baidu_validation_support_count']}/102.

Degraded warnings are preserved. This package is suitable for read-only internal review and conditionally suitable for Daily Review Lite with warning banners. Production dashboard integration is not ready. No automated execution prompt is present. Formal strategy files were not modified by this task; if untracked, 无法仅靠 `git diff` 完整证明历史状态。

## 2. Input Files

- watchlist_report_consolidated_index.csv
- watchlist_report_consolidated_summary_by_asset.csv
- watchlist_report_consolidated_quality_audit.csv
- watchlist_report_consolidated_dashboard_preview.csv
- reports_consolidated/latest/*.md

## 3. Dashboard Data Pack

- tech_bottleneck_dashboard_summary.json
- tech_bottleneck_dashboard_table.csv
- tech_bottleneck_dashboard_cards.json
- tech_bottleneck_dashboard_filters.json
- tech_bottleneck_dashboard_warnings.json
- tech_bottleneck_dashboard_report_links.csv
- tech_bottleneck_dashboard_contract.md

## 4. Summary Metrics

- watchlist_count: {summary['watchlist_count']}
- consolidated_report_count: {summary['consolidated_report_count']}
- specific_validation_count: {summary['specific_validation_count']}
- specific_risk_event_count: {summary['specific_risk_event_count']}
- lookahead_violation_rows: {summary['lookahead_violation_rows']}
- trading_signal_present: {summary['trading_signal_present']}

## 5. Table and Card Design

The table provides asset-level source coverage, risk context, valuation context, validation status, missing data, review action, and report path. Cards provide narrative read-only review context and explicitly frame forward return as historical replay context.

## 6. Filters and Warnings

Filter groups cover priority, source status, fundamental states, PE meaningfulness, valuation context, Baidu validation, discrepancy flags, review state, and data quality. Warning banners: {warning_ids}.

## 7. Report Link Handling

Report links generated: {len(links)}. Existing links: {int(links['report_exists'].astype(bool).sum())}. Link-level execution vocabulary scan count: {int(links['contains_trading_language'].astype(bool).sum())}.

## 8. Dashboard Readiness Decision

- read_only_internal_review: ready
- daily_review_lite: conditionally ready with degraded-source warning
- production_dashboard: not ready

## 9. Frontend Integration Notes

dashboard frontend integration deferred. Existing frontend has multiple workspaces, but this task only emits a read-only data contract and does not wire production UI.

## 10. What This Dashboard Does Not Do

- no automated execution prompt
- no Top5 change
- no formal strategy change
- no trigger / holding / exit study
- no evidence multiplier
- no execution instruction
- no manual label writeback

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_manual_review_label_schema_v1`, then `tech_bottleneck_dashboard_readonly_integration_v1`. Continue planning full financial statement and news source adapters; continue deferring trigger / holding / exit.

## 12. Appendix

Generated files are listed in section 3.

Test commands:
- PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/pytest stock_research/tests/test_tech_bottleneck_watchlist_dashboard_readonly.py -q
- related historical pytest commands listed in task spec

Formal strategy git status:
```text
{status}
```

Formal strategy git diff:
```text
{diff}
```

Key assumptions: read-only internal package; no frontend writeback; BaoStock remains primary valuation context; Baidu is auxiliary validation only.

Uncertainties: frontend integration route, manual review label schema, full financial statement source, and news source remain future work.
"""


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index, consolidated_summary, audit, preview = load_consolidated()
    summary = build_summary(index, consolidated_summary, audit)
    table = build_table(index, consolidated_summary, preview)
    cards = build_cards(table)
    filters = build_filters(table)
    warnings = build_warnings()
    links = build_report_links(index)
    contract = render_contract(summary, filters)
    main_report = render_main_report(summary, warnings, links)

    write_json(OUTPUT_DIR / "tech_bottleneck_dashboard_summary.json", summary)
    table.to_csv(OUTPUT_DIR / "tech_bottleneck_dashboard_table.csv", index=False)
    write_json(OUTPUT_DIR / "tech_bottleneck_dashboard_cards.json", cards)
    write_json(OUTPUT_DIR / "tech_bottleneck_dashboard_filters.json", filters)
    write_json(OUTPUT_DIR / "tech_bottleneck_dashboard_warnings.json", warnings)
    links.to_csv(OUTPUT_DIR / "tech_bottleneck_dashboard_report_links.csv", index=False)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_contract.md").write_text(contract, encoding="utf-8")
    (OUTPUT_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1.md").write_text(main_report, encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
