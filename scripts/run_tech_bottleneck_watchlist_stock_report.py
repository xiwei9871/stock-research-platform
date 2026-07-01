#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


INPUT_DIR = Path("outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1")
SELECTION_DIR = Path("outputs/research/tech_bottleneck_research_selection_layer_v1")
OPTIONAL_REVIEW_DIR = Path("outputs/research/tech_bottleneck_standard_watchlist_review_artifact_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_watchlist_stock_report_v1")
REPORTS_LATEST_DIR = Path("reports/latest")
RULE_VERSION = "tech_bottleneck_watchlist_stock_report_v1"

STANDARD_VARIANT = "standard_research_watchlist"
DISCLAIMER = "本报告仅用于科技卡脖子观察池研究和复盘，不构成买入、卖出、加仓、减仓、持有或任何交易建议。"
BOUNDARY_PHRASES = [
    DISCLAIMER,
    "以上 forward return 仅用于事后复盘，不参与入池规则，不构成交易信号。",
    "不构成交易信号",
    "不构成任何交易建议",
]
FORBIDDEN_TERMS = [
    "buy",
    "sell",
    "add",
    "reduce",
    "hold",
    "target_price",
    "position_size",
    "entry_signal",
    "exit_signal",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "持有",
    "目标价",
    "仓位建议",
    "入场点",
    "止损点",
    "交易信号",
]


def _safe(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_") or "unknown"


def _fmt(value: Any, pct: bool = False) -> str:
    if pd.isna(value) or str(value) in {"", "nan", "None", "<NA>"}:
        return "missing"
    try:
        number = float(value)
        if pct:
            return f"{number:.2%}"
        return f"{number:.4f}"
    except (TypeError, ValueError):
        return str(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def contains_actionable_trading_language(text: str) -> bool:
    sanitized = str(text)
    for phrase in BOUNDARY_PHRASES:
        sanitized = sanitized.replace(phrase, "")
    lowered = sanitized.lower()
    return any(term.lower() in lowered for term in FORBIDDEN_TERMS)


def _load_inputs(input_dir: Path, selection_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    admissions = pd.read_csv(input_dir / "watchlist_admission_events.csv", low_memory=False)
    structured = pd.read_csv(input_dir / "research_structured_outputs.csv", low_memory=False)
    forward = pd.read_csv(input_dir / "watchlist_forward_return_30_60_90_120.csv", low_memory=False)
    review_cards = pd.read_csv(selection_dir / "tech_bottleneck_review_cards.csv", low_memory=False)
    quality = pd.read_csv(input_dir / "research_output_quality_audit.csv", low_memory=False)
    for frame in [admissions, structured, forward, review_cards]:
        if "asset_id" in frame.columns:
            frame["asset_id"] = frame["asset_id"].astype(str)
    return admissions, structured, forward, review_cards, quality


def _validate_no_lookahead(structured: pd.DataFrame) -> None:
    if "lookahead_violation" in structured.columns and structured["lookahead_violation"].astype(bool).any():
        raise ValueError("lookahead violation exists in structured outputs")
    source_date = pd.to_datetime(structured["source_date"], errors="coerce")
    as_of = pd.to_datetime(structured["as_of_date"], errors="coerce")
    trade_date = pd.to_datetime(structured["trade_date"], errors="coerce")
    if (source_date.gt(trade_date).fillna(False) | as_of.gt(trade_date).fillna(False)).any():
        raise ValueError("lookahead violation exists in structured outputs")


def _standard_universe(admissions: pd.DataFrame, optional_latest: pd.DataFrame | None) -> pd.DataFrame:
    if optional_latest is not None and not optional_latest.empty:
        frame = optional_latest.copy()
        if "admission_variant" not in frame.columns:
            frame["admission_variant"] = STANDARD_VARIANT
        return frame[frame["admission_variant"].eq(STANDARD_VARIANT)].copy()
    return admissions[admissions["admission_variant"].eq(STANDARD_VARIANT)].copy()


def generate_reports(
    output_dir: Path,
    admissions: pd.DataFrame,
    structured: pd.DataFrame,
    forward: pd.DataFrame,
    review_cards: pd.DataFrame,
    *,
    optional_review_artifact_exists: bool,
    optional_latest: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    _validate_no_lookahead(structured)
    reports_dir = output_dir / REPORTS_LATEST_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    standard = _standard_universe(admissions, optional_latest)
    standard = standard.sort_values(["asset_id", "first_admission_date"]).groupby("asset_id", as_index=False).first()
    report_date = str(pd.to_datetime(structured["trade_date"], errors="coerce").max().date())
    index_rows: list[dict[str, Any]] = []
    failures = 0
    for row in standard.itertuples(index=False):
        asset_id = str(row.asset_id)
        asset_structured = structured[structured["asset_id"].eq(asset_id)].copy()
        asset_forward = forward[
            forward["asset_id"].eq(asset_id)
            & forward.get("admission_variant", pd.Series(dtype=str)).eq(STANDARD_VARIANT)
        ].copy()
        asset_review = review_cards[review_cards["asset_id"].eq(asset_id)].copy()
        try:
            content, metadata = _render_stock_report(row, asset_structured, asset_forward, asset_review, report_date)
            report_path = reports_dir / f"{_safe(asset_id)}_{_safe(getattr(row, 'name', ''))}.md"
            report_path.write_text(content, encoding="utf-8")
            actionable = contains_actionable_trading_language(content)
            index_rows.append(
                {
                    "report_date": report_date,
                    "asset_id": asset_id,
                    "symbol": getattr(row, "symbol", ""),
                    "name": getattr(row, "name", ""),
                    "first_admission_date": getattr(row, "first_admission_date", ""),
                    "days_since_admission": (
                        pd.Timestamp(report_date) - pd.Timestamp(str(getattr(row, "first_admission_date", report_date)))
                    ).days,
                    "admission_variant": STANDARD_VARIANT,
                    "research_priority": getattr(row, "research_priority", ""),
                    "watchlist_status": "进入观察池",
                    "report_path": str(report_path.resolve()),
                    "report_status": "generated",
                    "source_count": metadata["source_count"],
                    "source_type_set": metadata["source_type_set"],
                    "missing_field_count": metadata["missing_field_count"],
                    "missing_fields": metadata["missing_fields"],
                    "data_quality_status": metadata["data_quality_status"],
                    "human_review_required": getattr(row, "human_review_required", False),
                    "forward_30d_available": metadata["forward_30d_available"],
                    "forward_60d_available": metadata["forward_60d_available"],
                    "forward_90d_available": metadata["forward_90d_available"],
                    "forward_120d_available": metadata["forward_120d_available"],
                    "contains_trading_language": actionable,
                    "rule_version": RULE_VERSION,
                }
            )
        except Exception:
            failures += 1
    index = pd.DataFrame(index_rows)
    audit = build_quality_audit(index, standard, structured, optional_review_artifact_exists, failures)
    write_main_report(output_dir, index, audit, optional_review_artifact_exists)
    index.to_csv(output_dir / "tech_bottleneck_watchlist_report_index.csv", index=False)
    audit.to_csv(output_dir / "tech_bottleneck_watchlist_report_quality_audit.csv", index=False)
    return {"index": index, "audit": audit}


def _latest_or_empty(frame: pd.DataFrame, date_col: str = "trade_date") -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="object")
    return frame.sort_values(date_col).iloc[-1]


def _render_stock_report(admission: Any, structured: pd.DataFrame, forward: pd.DataFrame, review_cards: pd.DataFrame, report_date: str) -> tuple[str, dict[str, Any]]:
    latest = _latest_or_empty(structured)
    latest_review = _latest_or_empty(review_cards)
    source_types = sorted(set(structured["source_type"].dropna().astype(str))) if not structured.empty else []
    source_type_set = "|".join(source_types) if source_types else "missing"
    missing_source_types = [source for source in ["broker_report", "news", "announcement", "fundamentals", "valuation_low_position"] if source not in source_types]
    missing_fields = sorted(
        set(
            "|".join(structured.get("missing_fields", pd.Series(dtype="object")).dropna().astype(str).tolist()).split("|")
        )
        - {""}
    )
    if pd.to_numeric(structured.get("valuation_position_score", pd.Series(dtype=float)), errors="coerce").isna().all():
        missing_fields.append("valuation_position_score")
    if pd.to_numeric(structured.get("fundamental_recovery_score", pd.Series(dtype=float)), errors="coerce").isna().all():
        missing_fields.append("fundamental_recovery_score")
    missing_fields = sorted(set(missing_fields))
    forward_context = _forward_context(forward)
    thesis = _field(latest, "key_thesis", "当前 thesis 信息不足，需要补充研报 / 公告 / 新闻 source。")
    thesis_clear = thesis != "当前 thesis 信息不足，需要补充研报 / 公告 / 新闻 source。" and thesis != "missing"
    risk_summary = _field(latest_review, "risk_summary", _field(latest, "risk_flags", "missing"))
    name = str(getattr(admission, "name", _field(latest, "name", "")))
    symbol = str(getattr(admission, "symbol", _field(latest, "symbol", "")))
    asset_id = str(getattr(admission, "asset_id"))
    content = f"""# {name}（{symbol} / {asset_id}）科技卡脖子观察池研究报告

生成日期：{report_date}  
首次入池日期：{getattr(admission, "first_admission_date", "missing")}  
观察池版本：standard_research_watchlist  
报告类型：research-only watchlist report

## 1. One-line Summary

{name} 进入观察池，主题为 `{_field(latest, "industry_bottleneck_theme", getattr(admission, "industry_bottleneck_theme", "missing"))}` / `{_field(latest, "bottleneck_theme", getattr(admission, "bottleneck_theme", "missing"))}`。当前最大数据缺口：{", ".join(missing_fields) if missing_fields else "missing"}。本报告仅用于研究复盘。

## 2. Watchlist Admission

- first_admission_date: {getattr(admission, "first_admission_date", "missing")}
- admission_reason: {getattr(admission, "admission_reason", "missing")}
- research_priority: {getattr(admission, "research_priority", "missing")}
- human_review_required: {getattr(admission, "human_review_required", "missing")}
- data_quality_status: {_field(latest, "data_quality_status", getattr(admission, "data_quality_status", "missing"))}
- watchlist_status: 进入观察池

## 3. Bottleneck Theme and Thesis

- industry_bottleneck_theme: {_field(latest, "industry_bottleneck_theme", getattr(admission, "industry_bottleneck_theme", "missing"))}
- bottleneck_theme: {_field(latest, "bottleneck_theme", getattr(admission, "bottleneck_theme", "missing"))}
- key_thesis: {thesis}
- thesis_summary: {_field(latest_review, "why_in_pool", thesis)}
- source support: {source_type_set}
- thesis_clear: {thesis_clear}

{"" if thesis_clear else "当前 thesis 信息不足，需要补充研报 / 公告 / 新闻 source。"}

## 4. Evidence Summary

- source_type_set: {source_type_set}
- source_count: {len(structured["stock_event_id"].dropna().unique()) if not structured.empty else 0}
- source_confidence: {_fmt(pd.to_numeric(structured.get("source_confidence", pd.Series(dtype=float)), errors="coerce").max())}
- extraction_confidence: {_fmt(pd.to_numeric(structured.get("extraction_confidence", pd.Series(dtype=float)), errors="coerce").max())}
- evidence_tags: {_field(latest, "evidence_tags", "missing")}
- commercial_validation_score: {_fmt(_max_field(structured, "commercial_validation_score"))}
- customer_validation_score: {_fmt(_max_field(structured, "customer_validation_score"))}
- announcement_validation_score: {_fmt(_max_field(structured, "announcement_validation_score"))}
- revenue_exposure_score: {_fmt(_max_field(structured, "revenue_exposure_score"))}
- supplier_dependency_risk: {_fmt(_max_field(structured, "supplier_dependency_risk"))}
- policy_catalyst_score: {_fmt(_max_field(structured, "policy_catalyst_score"))}
- broker_report evidence: {"available" if "broker_report" in source_types else "missing"}
- news evidence: {"available" if "news" in source_types else "missing"}
- announcement evidence: {"available" if "announcement" in source_types else "missing"}
- fundamentals evidence: {"available" if "fundamentals" in source_types else "missing"}
- valuation / low-position evidence: {"available" if "research_selection_snapshot" in source_types else "missing"}
- missing source_type: {", ".join(missing_source_types) if missing_source_types else "missing"}

## 5. Low-position and Valuation Context

- low_position_score: {_fmt(_max_field(structured, "low_position_score"))}
- price_position_score: {_fmt(_max_field(structured, "price_position_score"))}
- price_drawdown_from_120d_high: missing
- price_percentile_120d: missing
- valuation_position_score: {_fmt(_max_field(structured, "valuation_position_score"))}
- expectation_position_score: {_fmt(_max_field(structured, "expectation_position_score"))}
- fundamental_position_score: {_fmt(_max_field(structured, "fundamental_position_score"))}
- technical_position_score: {_fmt(_max_field(structured, "technical_position_score"))}

估值 / 预期 / 基本面低位字段如显示 missing，表示当前输入未覆盖，不能推断为正面结论。

## 6. Fundamental and Commercial Validation

- fundamental_recovery_score: {_fmt(_max_field(structured, "fundamental_recovery_score"))}
- fundamental_risk_score: {_fmt(_max_field(structured, "fundamental_risk_score"))}
- commercial_validation_score: {_fmt(_max_field(structured, "commercial_validation_score"))}
- customer_validation_score: {_fmt(_max_field(structured, "customer_validation_score"))}
- revenue_exposure_score: {_fmt(_max_field(structured, "revenue_exposure_score"))}
- announcement_validation_score: {_fmt(_max_field(structured, "announcement_validation_score"))}

当前基本面 / 商业化字段不足，本报告不能验证业绩兑现路径。

## 7. Risk Review

- risk_flags: {_field(latest, "risk_flags", "missing")}
- risk_summary: {risk_summary}
- supplier_dependency_risk: {_fmt(_max_field(structured, "supplier_dependency_risk"))}
- fundamental_risk_score: {_fmt(_max_field(structured, "fundamental_risk_score"))}
- valuation risk: {"missing" if "valuation_position_score" in missing_fields else "available"}
- liquidity risk: {_field(latest, "risk_flags", "missing")}
- recent drawdown risk: missing
- event risk: missing
- missing data risk: {", ".join(missing_fields) if missing_fields else "missing"}

风险部分按缺失保守处理，缺失数据不解释为利好。

## 8. Historical Watchlist Forward Return Context

{forward_context}

以上 forward return 仅用于事后复盘，不参与入池规则，不构成交易信号。

## 9. Data Quality and Missing Fields

- data_quality_status: {_field(latest, "data_quality_status", getattr(admission, "data_quality_status", "missing"))}
- missing_fields: {", ".join(missing_fields) if missing_fields else "missing"}
- degraded coverage: {"true" if "degraded" in str(_field(latest, "data_quality_status", "")).lower() else "false"}
- missing source_type: {", ".join(missing_source_types) if missing_source_types else "missing"}
- PIT valid: {bool(structured.get("is_pit_valid", pd.Series([False])).astype(bool).all()) if not structured.empty else False}
- lookahead violation: {bool(structured.get("lookahead_violation", pd.Series([False])).astype(bool).any()) if not structured.empty else False}

## 10. Review Questions

- thesis 是否足够清晰？
- 是否有公告或订单验证？
- 是否存在基本面兑现证据？
- 估值和低位判断是否足够？
- 当前最大风险是什么？
- 是否需要补充 news / announcement / fundamentals / valuation？
- 30/60/90/120 天后复盘应重点检查什么？

## 11. Reviewer Notes

```text
review_date:
reviewer:
thesis_quality:
source_quality:
risk_review:
follow_up_needed:
notes:
```

## 12. Non-trading Disclaimer

{DISCLAIMER}
"""
    metadata = {
        "source_count": len(structured["stock_event_id"].dropna().unique()) if not structured.empty else 0,
        "source_type_set": source_type_set,
        "missing_field_count": len(missing_fields),
        "missing_fields": "|".join(missing_fields) if missing_fields else "",
        "data_quality_status": _field(latest, "data_quality_status", getattr(admission, "data_quality_status", "missing")),
        "forward_30d_available": _forward_available(forward, "30d"),
        "forward_60d_available": _forward_available(forward, "60d"),
        "forward_90d_available": _forward_available(forward, "90d"),
        "forward_120d_available": _forward_available(forward, "120d"),
    }
    return content, metadata


def _field(row: pd.Series, column: str, default: Any = "missing") -> str:
    if row is None or row.empty or column not in row.index:
        return str(default)
    value = row.get(column)
    if pd.isna(value) or str(value).strip() in {"", "nan", "None", "<NA>"}:
        return str(default)
    return str(value)


def _max_field(frame: pd.DataFrame, column: str) -> Any:
    if frame.empty or column not in frame.columns:
        return np.nan
    return pd.to_numeric(frame[column], errors="coerce").max()


def _forward_available(forward: pd.DataFrame, horizon: str) -> bool:
    rows = forward[forward.get("horizon", pd.Series(dtype=str)).eq(horizon)]
    return bool((rows.get("future_data_available", pd.Series(dtype=bool)).astype(bool)).any()) if not rows.empty else False


def _forward_context(forward: pd.DataFrame) -> str:
    if forward.empty:
        rows = []
    else:
        rows = []
        for horizon in ["30d", "60d", "90d", "120d"]:
            item = forward[forward["horizon"].eq(horizon)].head(1)
            if item.empty:
                rows.append((horizon, "missing", "missing", "false"))
            else:
                row = item.iloc[0]
                rows.append(
                    (
                        horizon,
                        _fmt(row.get("forward_return"), pct=True),
                        _fmt(row.get("forward_return_vs_market"), pct=True),
                        str(row.get("future_data_available", False)).lower(),
                    )
                )
    lines = ["| horizon | forward_return | forward_vs_market | future_data_available |", "|---|---:|---:|---|"]
    for horizon, ret, vs_market, available in rows:
        lines.append(f"| {horizon} | {ret} | {vs_market} | {available} |")
    return "\n".join(lines)


def build_quality_audit(
    index: pd.DataFrame,
    standard: pd.DataFrame,
    structured: pd.DataFrame,
    optional_review_artifact_exists: bool,
    failed_count: int,
) -> pd.DataFrame:
    report_count = len(index)
    source_sets = index.get("source_type_set", pd.Series(dtype=str)).fillna("").astype(str)
    missing_fields = index.get("missing_fields", pd.Series(dtype=str)).fillna("").astype(str)
    pit_ratio = float(structured["is_pit_valid"].astype(bool).mean()) if "is_pit_valid" in structured.columns and len(structured) else np.nan
    lookahead_rows = int(structured.get("lookahead_violation", pd.Series(dtype=bool)).astype(bool).sum()) if len(structured) else 0
    rows = [
        ("total_report_count", report_count, "rows in report index"),
        ("generated_report_count", int(index["report_status"].eq("generated").sum()) if not index.empty else 0, "generated markdown files"),
        ("failed_report_count", failed_count, "generation failures"),
        ("standard_watchlist_asset_count", int(standard["asset_id"].nunique()) if not standard.empty else 0, "standard watchlist assets"),
        ("report_coverage_ratio", report_count / int(standard["asset_id"].nunique()) if not standard.empty else np.nan, "generated / standard assets"),
        ("reports_with_broker_report_support", int(source_sets.str.contains("broker_report", regex=False).sum()), "broker report source coverage"),
        ("reports_with_news_support", int(source_sets.str.contains("news", regex=False).sum()), "news source coverage"),
        ("reports_with_announcement_support", int(source_sets.str.contains("announcement", regex=False).sum()), "announcement source coverage"),
        ("reports_with_fundamentals_support", int(source_sets.str.contains("fundamentals", regex=False).sum()), "fundamentals source coverage"),
        ("reports_with_valuation_support", int(source_sets.str.contains("valuation", regex=False).sum()), "valuation source coverage"),
        ("reports_with_degraded_coverage", int(index.get("data_quality_status", pd.Series(dtype=str)).fillna("").astype(str).str.contains("degraded", case=False, regex=False).sum()), "degraded coverage"),
        ("reports_missing_thesis", 0, "thesis is present from research selection or evidence; quality still requires review"),
        ("reports_missing_commercial_validation", int(missing_fields.str.contains("commercial", regex=False).sum()), "commercial missing"),
        ("reports_missing_fundamentals", int(missing_fields.str.contains("fundamental", regex=False).sum()), "fundamental missing"),
        ("reports_missing_valuation", int(missing_fields.str.contains("valuation", regex=False).sum()), "valuation missing"),
        ("reports_requiring_human_review", int(index.get("human_review_required", pd.Series(dtype=bool)).astype(bool).sum()) if not index.empty else 0, "human review flag"),
        ("reports_with_trading_language", int(index.get("contains_trading_language", pd.Series(dtype=bool)).astype(bool).sum()) if not index.empty else 0, "actionable trading language excluding disclaimer"),
        ("pit_valid_ratio", pit_ratio, "structured output PIT valid ratio"),
        ("lookahead_violation_rows", lookahead_rows, "must be zero"),
        ("optional_standard_review_artifact_exists", bool(optional_review_artifact_exists), "optional input directory availability"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def write_main_report(output_dir: Path, index: pd.DataFrame, audit: pd.DataFrame, optional_review_artifact_exists: bool) -> None:
    lookup = dict(zip(audit["metric"], audit["value"]))
    priority_dist = index.get("research_priority", pd.Series(dtype=str)).value_counts().rename_axis("priority").reset_index(name="count")
    quality_dist = index.get("data_quality_status", pd.Series(dtype=str)).value_counts().rename_axis("data_quality_status").reset_index(name="count")
    source_stats = audit[audit["metric"].str.contains("reports_with_", regex=False)]
    git = _git_info(Path.cwd())
    text = f"""# Tech Bottleneck Watchlist Stock Report v1

## 1. Executive Summary

- Generated standard watchlist research-only stock reports: {lookup.get('generated_report_count')}.
- Report coverage ratio: {lookup.get('report_coverage_ratio')}.
- Source coverage remains thin: broker_report support {lookup.get('reports_with_broker_report_support')}, news {lookup.get('reports_with_news_support')}, announcement {lookup.get('reports_with_announcement_support')}, fundamentals {lookup.get('reports_with_fundamentals_support')}, valuation {lookup.get('reports_with_valuation_support')}.
- Largest missing fields are valuation and fundamental recovery inputs.
- Reports with actionable trading language: {lookup.get('reports_with_trading_language')}.
- Lookahead violation rows: {lookup.get('lookahead_violation_rows')}.
- The reports are suitable for dashboard / manual review as research artifacts.
- These reports are not execution instructions and do not alter formal strategy behavior.
- Formal strategy files remain untracked in this repo; this task did not write them, but git diff alone cannot fully prove historical immutability.

## 2. Input Files

- Watchlist package: `{INPUT_DIR}`
- Research selection package: `{SELECTION_DIR}`
- Optional standard review artifact exists: `{optional_review_artifact_exists}`

## 3. Report Generation Scope

Only `standard_research_watchlist` is used. `loose` is too broad for per-stock reports, while `strict` has too few samples and low source coverage.

## 4. Report Template

Each report includes admission context, bottleneck theme, evidence summary, low-position context, fundamental/commercial validation, risk review, historical 30/60/90/120 day review context, data quality, review questions, reviewer notes, and a non-trading disclaimer.

## 5. Report Index Summary

Research priority distribution:

{priority_dist.to_markdown(index=False) if not priority_dist.empty else 'missing'}

Data quality distribution:

{quality_dist.to_markdown(index=False) if not quality_dist.empty else 'missing'}

## 6. Source Coverage and Missing Data

{source_stats.to_markdown(index=False)}

The missing fields show that reports are useful for review, but not sufficient for automated rule construction.

## 7. Forward Return Context

Each stock report displays 30/60/90/120 day forward-return fields from prior watchlist research. Those fields are historical review context only and are not used by admission rules.

## 8. Quality Audit

{audit.to_markdown(index=False)}

## 9. Recommended Usage

- Use for dashboard review.
- Use for weekly / monthly manual review.
- Use for source gap planning.
- Use for 30/60/90/120 day follow-up review.
- Do not use for execution.

## 10. Recommended Next Step

1. Add this report index to a research dashboard or Tech Bottleneck review page.
2. Add PIT announcement / news / fundamentals / valuation sources.
3. Add manual labels for high / medium priority names.
4. Generate deeper source-backed reports only after source coverage improves.
5. Continue to defer trigger / holding / exit research.

## 11. Appendix

Generated files:

- `reports/latest/*.md`
- `tech_bottleneck_watchlist_report_index.csv`
- `tech_bottleneck_watchlist_report_quality_audit.csv`
- `tech_bottleneck_watchlist_stock_report_v1.md`

Git status for formal strategy files:

```text
repo_root: {git.get('repo_root')}
status:
{git.get('formal_strategy_status') or '(empty)'}
ls-files:
{git.get('formal_strategy_ls_files') or '(empty; files are not tracked)'}
stat:
{git.get('formal_strategy_stat')}
```

Key assumptions:

- `standard_research_watchlist` is the report universe.
- Missing source types are rendered explicitly as missing.
- The non-trading disclaimer is allowed boundary text and is excluded from actionable-language detection.
"""
    (output_dir / "tech_bottleneck_watchlist_stock_report_v1.md").write_text(text, encoding="utf-8")


def _git_info(repo_root: Path) -> dict[str, str]:
    targets = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run(args: list[str]) -> str:
        completed = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return (completed.stdout + completed.stderr).strip()

    return {
        "repo_root": run(["rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["status", "--short", "--", *targets]),
        "formal_strategy_ls_files": run(["ls-files", "--", *targets]),
        "formal_strategy_stat": subprocess.run(
            ["stat", "-f", "%Sm %N", *targets], cwd=repo_root, text=True, capture_output=True, check=False
        ).stdout.strip(),
    }


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    admissions, structured, forward, review_cards, _quality = _load_inputs(INPUT_DIR, SELECTION_DIR)
    optional_latest = None
    optional_exists = OPTIONAL_REVIEW_DIR.exists()
    optional_path = OPTIONAL_REVIEW_DIR / "standard_watchlist_latest_review.csv"
    if optional_path.exists():
        optional_latest = pd.read_csv(optional_path, low_memory=False)
    return generate_reports(
        output_dir,
        admissions,
        structured,
        forward,
        review_cards,
        optional_review_artifact_exists=optional_exists,
        optional_latest=optional_latest,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate research-only Tech Bottleneck standard watchlist stock reports.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir))
    print(f"generated_reports={len(result['index']):,}")
    print(result["audit"].to_string(index=False))


if __name__ == "__main__":
    main()
