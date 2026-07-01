#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


WATCHLIST_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_stock_report_v1")
WATCHLIST_FORWARD_DIR = Path("outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1")
RESEARCH_SELECTION_DIR = Path("outputs/research/tech_bottleneck_research_selection_layer_v1")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_research_source_expansion_plan_v1")
RULE_VERSION = "tech_bottleneck_research_source_expansion_plan_v1"

SOURCE_CATEGORIES = [
    "broker_report",
    "news",
    "announcement",
    "fundamentals",
    "valuation",
    "low_position",
    "price_volume",
    "industry_theme",
    "risk_event",
]

ACTIONABLE_TERMS = [
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


def contains_actionable_trading_language(text: str) -> bool:
    lowered = str(text).lower()
    for term in ACTIONABLE_TERMS:
        term_lower = term.lower()
        if term_lower.isascii() and term_lower.replace("_", "").isalpha():
            if re.search(rf"\b{re.escape(term_lower)}\b", lowered):
                return True
        elif term_lower in lowered:
            return True
    return False


def _scan_paths(project_root: Path) -> list[str]:
    if not project_root.exists():
        return []
    keywords = [
        "announcement",
        "news",
        "report",
        "broker",
        "fundamental",
        "financial",
        "valuation",
        "tushare",
        "akshare",
        "disclosure",
        "earnings",
        "income",
        "balance",
        "cashflow",
        "forecast",
        "estimate",
        "low_position",
        "market_daily_bar",
        "factor_value",
    ]
    roots = [project_root / "src", project_root / "scripts", project_root / "tests", project_root / "docs", project_root / "outputs" / "research"]
    paths: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(project_root))
                if any(keyword in rel.lower() for keyword in keywords):
                    paths.append(rel)
    return sorted(paths)


def _matching_paths(scanned_paths: list[str], tokens: list[str], limit: int = 8) -> list[str]:
    result = [path for path in scanned_paths if any(token in path.lower() for token in tokens)]
    return result[:limit]


def build_source_inventory(project_root: Path) -> pd.DataFrame:
    scanned = _scan_paths(project_root)
    rows: list[dict[str, Any]] = []
    specs = {
        "broker_report": {
            "tokens": ["yanbaoke", "hibor", "broker", "stock_report", "report_pdf"],
            "fields": "source_id, source_type, source_date, key_thesis, evidence_tags, extraction_confidence",
            "date": "source_date",
            "asset": "asset_id",
            "pit": "partial",
            "coverage": "low in current watchlist reports",
            "risk": "extraction quality and limited coverage",
            "notes": "Existing PDF/report ingestion and PIT evidence replay are available but only 4 standard reports have broker_report support.",
        },
        "news": {
            "tokens": ["news", "public_news", "topn_news"],
            "fields": "source_date, event_type, source_name, event_family, event_direction",
            "date": "source_date",
            "asset": "asset_id or symbol mapping",
            "pit": "partial",
            "coverage": "available infrastructure, not joined to watchlist reports",
            "risk": "high noise and source normalization risk",
            "notes": "Public news and news feature modules exist; need mapping into research input contract.",
        },
        "announcement": {
            "tokens": ["announcement", "disclosure", "cninfo"],
            "fields": "announcement_date, announcement_type, event_family, source_name, metadata",
            "date": "announcement_date or source_date",
            "asset": "asset_id or ts_code mapping",
            "pit": "partial",
            "coverage": "available backfill/test adapters, not joined to reports",
            "risk": "announcement classification and duplicate source handling",
            "notes": "CNINFO disclosure/announcement adapters appear in tests and news_source_backfill.",
        },
        "fundamentals": {
            "tokens": ["fundamental", "financial", "finance", "income", "balance", "cashflow", "akshare_finance"],
            "fields": "financial_as_of_date, revenue_growth, profit_growth, cashflow_quality, debt_risk",
            "date": "financial_as_of_date/report_disclosure_date",
            "asset": "asset_id",
            "pit": "partial",
            "coverage": "usable for Mid Trend, not connected to Tech Bottleneck reports",
            "risk": "schema mismatch and report disclosure date quality",
            "notes": "Midtrend PIT fundamentals and akshare finance loaders exist; need Tech Bottleneck adapter.",
        },
        "valuation": {
            "tokens": ["valuation", "pe_ttm", "ps_ttm", "pb", "factor_value"],
            "fields": "trade_date, pe_ttm, pb, ps_ttm, valuation_percentile, valuation_position_score",
            "date": "trade_date",
            "asset": "asset_id",
            "pit": "not_confirmed",
            "coverage": "field/test hints exist, no watchlist integration",
            "risk": "valuation history and industry percentile gaps",
            "notes": "Value factor tests mention pe_ttm/pb/ps_ttm; no current watchlist valuation coverage.",
        },
        "low_position": {
            "tokens": ["low_position", "research_selection_low_position"],
            "fields": "price_position_score, technical_position_score, low_position_score",
            "date": "trade_date",
            "asset": "asset_id",
            "pit": "yes",
            "coverage": "broad",
            "risk": "price-only low position, valuation/fundamental low missing",
            "notes": "Current watchlist reports use low-position data from research selection v1.",
        },
        "price_volume": {
            "tokens": ["market_daily_bar", "tech_bottleneck_v1.py", "setup_state_machine"],
            "fields": "trade_date, open, high, low, close, amount if available",
            "date": "trade_date",
            "asset": "asset_id",
            "pit": "yes",
            "coverage": "broad for OHLC, amount incomplete in current Tech Bottleneck loader",
            "risk": "amount/turnover not exposed in current research layer",
            "notes": "Formal loader exposes OHLC; setup state machine marked amount missing.",
        },
        "industry_theme": {
            "tokens": ["industry", "theme", "chain"],
            "fields": "industry_bottleneck_theme, primary_chain_name, industry_name",
            "date": "trade_date/source_date",
            "asset": "asset_id",
            "pit": "partial",
            "coverage": "broad in research selection snapshot",
            "risk": "theme taxonomy consistency",
            "notes": "Industry bottleneck theme is available in current research candidates.",
        },
        "risk_event": {
            "tokens": ["risk", "disclosure", "alert"],
            "fields": "risk_flags, risk_summary, risk_event, risk_disclosure",
            "date": "source_date or trade_date",
            "asset": "asset_id",
            "pit": "partial",
            "coverage": "basic flags available, event-level source missing",
            "risk": "missing event source may hide risk catalyst",
            "notes": "Risk audit exists but event-level risk evidence is not connected.",
        },
    }
    for category in SOURCE_CATEGORIES:
        spec = specs[category]
        paths = _matching_paths(scanned, spec["tokens"])
        if category == "price_volume" and not paths:
            paths = ["market_daily_bar table via stock_research.tech_bottleneck_v1._load_prices"]
        if category == "low_position" and not paths:
            paths = ["outputs/research/tech_bottleneck_research_selection_layer_v1/research_selection_low_position_breakdown.csv"]
        rows.append(
            {
                "source_category": category,
                "source_name": category,
                "source_type": category,
                "existing_in_project": bool(paths),
                "detected_path_or_table": "|".join(paths) if paths else "missing",
                "available_fields": spec["fields"],
                "date_field": spec["date"],
                "asset_id_field": spec["asset"],
                "pit_ready": spec["pit"],
                "coverage_estimate": spec["coverage"],
                "quality_risk": spec["risk"],
                "notes": spec["notes"],
            }
        )
    return pd.DataFrame(rows)


def build_watchlist_source_gap(index: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in index.itertuples(index=False):
        source_set = str(getattr(record, "source_type_set", "") or "")
        missing_fields = str(getattr(record, "missing_fields", "") or "")
        for category in SOURCE_CATEGORIES:
            has_source = _asset_has_source(category, source_set, missing_fields)
            rows.append(
                {
                    "asset_id": getattr(record, "asset_id"),
                    "symbol": getattr(record, "symbol", ""),
                    "name": getattr(record, "name", ""),
                    "source_category": category,
                    "has_source": has_source,
                    "source_count": int(getattr(record, "source_count", 0) or 0) if has_source else 0,
                    "latest_source_date": "missing",
                    "missing_required_fields": _missing_required_fields(category, missing_fields, has_source),
                    "gap_severity": _gap_severity(category, has_source, missing_fields),
                    "recommended_fill_action": _fill_action(category, has_source),
                    "human_review_required": bool(getattr(record, "human_review_required", True)),
                }
            )
    return pd.DataFrame(rows)


def _asset_has_source(category: str, source_set: str, missing_fields: str) -> bool:
    if category == "broker_report":
        return "broker_report" in source_set
    if category == "news":
        return "news" in source_set
    if category == "announcement":
        return "announcement" in source_set or "company_announcement" in source_set
    if category == "fundamentals":
        return "fundamental_recovery_score" not in missing_fields and "fundamental_position_score" not in missing_fields
    if category == "valuation":
        return "valuation_position_score" not in missing_fields
    if category == "low_position":
        return "research_selection_snapshot" in source_set
    if category == "price_volume":
        return True
    if category == "industry_theme":
        return True
    if category == "risk_event":
        return False
    return False


def _missing_required_fields(category: str, missing_fields: str, has_source: bool) -> str:
    if has_source:
        return ""
    required = {
        "broker_report": "key_thesis|commercial_validation|customer_validation|revenue_exposure",
        "news": "event_type|industry_catalyst|risk_event|evidence_direction",
        "announcement": "announcement_date|announcement_type|order_contract|risk_disclosure",
        "fundamentals": "financial_as_of_date|revenue_growth|profit_growth|cashflow_quality",
        "valuation": "pe_ttm|pb|ps_ttm|valuation_position_score",
        "low_position": "low_position_score",
        "price_volume": "amount|volume_state",
        "industry_theme": "industry_bottleneck_theme",
        "risk_event": "risk_event|risk_disclosure",
    }
    if category in {"fundamentals", "valuation"} and missing_fields:
        return missing_fields
    return required.get(category, "")


def _gap_severity(category: str, has_source: bool, missing_fields: str) -> str:
    if has_source:
        return "none"
    if category in {"fundamentals", "valuation"}:
        return "critical"
    if category in {"announcement", "news"}:
        return "high"
    if category in {"broker_report", "risk_event"}:
        return "medium"
    return "low"


def _fill_action(category: str, has_source: bool) -> str:
    if has_source:
        return "no_fill_required"
    return {
        "announcement": "build_pit_cninfo_announcement_adapter",
        "news": "map_public_news_events_to_contract",
        "fundamentals": "build_tech_bottleneck_fundamental_pit_adapter",
        "valuation": "build_valuation_percentile_feature_table",
        "broker_report": "expand_pit_report_evidence_extraction",
        "risk_event": "map_risk_disclosure_events",
    }.get(category, "review_source_gap")


def build_source_field_mapping_plan() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(category: str, raw: str, target: str, loose: bool, standard: bool, strict: bool, dtype: str, pit: str, fallback: str, missing: str, quality: str, notes: str = "") -> None:
        rows.append(
            {
                "source_category": category,
                "raw_field_name": raw,
                "target_contract_field": target,
                "required_for_loose_watchlist": loose,
                "required_for_standard_watchlist": standard,
                "required_for_strict_watchlist": strict,
                "data_type": dtype,
                "pit_rule": pit,
                "fallback_rule": fallback,
                "missing_behavior": missing,
                "quality_check": quality,
                "notes": notes,
            }
        )

    for raw in [
        "as_of_date",
        "announcement_date",
        "announcement_type",
        "order_contract",
        "customer_contract",
        "capacity_project",
        "fundraising_project",
        "equity_incentive",
        "risk_disclosure",
        "financial_guidance",
        "evidence_direction",
    ]:
        add("announcement", raw, raw, raw == "announcement_date", raw in {"announcement_date", "announcement_type"}, raw in {"announcement_date", "announcement_type", "evidence_direction"}, "string/date", "announcement_date <= trade_date and as_of_date <= trade_date", "missing", "missing", "date parse and source_id uniqueness")
    for raw in [
        "as_of_date",
        "source_date",
        "event_type",
        "industry_catalyst",
        "policy_catalyst",
        "supply_chain_event",
        "customer_event",
        "risk_event",
        "evidence_direction",
    ]:
        add("news", raw, raw, raw == "source_date", raw in {"source_date", "event_type"}, raw in {"source_date", "event_type", "evidence_direction"}, "string/date", "source_date <= trade_date and as_of_date <= trade_date", "missing", "missing", "source_type and event_family validation")
    for raw in [
        "as_of_date",
        "financial_as_of_date",
        "revenue_growth",
        "profit_growth",
        "gross_margin_trend",
        "cashflow_quality",
        "debt_risk",
        "inventory_risk",
        "receivable_risk",
        "fundamental_risk_score",
        "fundamental_recovery_score",
    ]:
        add("fundamentals", raw, raw, raw == "financial_as_of_date", raw in {"financial_as_of_date", "fundamental_risk_score"}, raw in {"financial_as_of_date", "fundamental_risk_score", "fundamental_recovery_score"}, "float/date", "financial_as_of_date <= trade_date and disclosure_date <= trade_date", "quality_unknown", "missing", "report disclosure date required")
    for raw in ["trade_date", "pe_ttm", "pb", "ps_ttm", "valuation_percentile_3y", "valuation_percentile_5y", "industry_valuation_percentile", "valuation_position_score"]:
        add("valuation", raw, raw, raw == "trade_date", raw in {"trade_date", "valuation_position_score"}, raw in {"trade_date", "valuation_position_score", "industry_valuation_percentile"}, "float/date", "trade_date <= watch_date", "missing", "missing", "finite numeric and industry percentile check")
    for raw in [
        "as_of_date",
        "source_date",
        "industry_theme",
        "bottleneck_theme",
        "key_thesis",
        "commercial_validation",
        "customer_validation",
        "revenue_exposure",
        "supplier_dependency",
        "risk_points",
        "extraction_confidence",
    ]:
        add("broker_report", raw, raw, raw == "source_date", raw in {"source_date", "bottleneck_theme", "key_thesis"}, raw in {"source_date", "bottleneck_theme", "key_thesis", "extraction_confidence"}, "string/float/date", "source_date <= trade_date and as_of_date <= trade_date", "unverified", "missing", "confidence range 0..1 and source_id uniqueness")
    return pd.DataFrame(rows)


def build_source_priority_roadmap() -> pd.DataFrame:
    rows = [
        {
            "priority_rank": 1,
            "source_category": "announcement",
            "why_priority": "Most auditable PIT source for contracts, capacity projects, risk disclosures, and corporate events.",
            "expected_impact": "Improve thesis support and risk review quality for standard watchlist reports.",
            "implementation_difficulty": "medium",
            "pit_complexity": "medium",
            "coverage_impact": "high",
            "recommended_next_task": "tech_bottleneck_announcement_source_ingestion_v1",
            "acceptance_criteria": "PIT-valid announcement rows; zero lookahead rows; source_id uniqueness; mapped event_type and risk fields.",
        },
        {
            "priority_rank": 2,
            "source_category": "fundamentals",
            "why_priority": "All 102 reports currently miss fundamental recovery fields.",
            "expected_impact": "Separate research themes with real financial recovery evidence from weak thesis-only names.",
            "implementation_difficulty": "medium",
            "pit_complexity": "high",
            "coverage_impact": "high",
            "recommended_next_task": "tech_bottleneck_fundamental_source_adapter_v1",
            "acceptance_criteria": "financial_as_of_date and disclosure_date controls; revenue/profit/cashflow fields mapped; missing remains unknown.",
        },
        {
            "priority_rank": 3,
            "source_category": "valuation",
            "why_priority": "All 102 reports currently miss valuation context, leaving low-position incomplete.",
            "expected_impact": "Improve low-position interpretation with valuation percentiles and industry-relative context.",
            "implementation_difficulty": "medium",
            "pit_complexity": "medium",
            "coverage_impact": "high",
            "recommended_next_task": "tech_bottleneck_valuation_source_adapter_v1",
            "acceptance_criteria": "pe/pb/ps and percentile features; zero date leakage; industry percentile coverage reported.",
        },
        {
            "priority_rank": 4,
            "source_category": "news",
            "why_priority": "Useful for catalyst and risk context, but noisier than announcements.",
            "expected_impact": "Provide event monitoring and risk review tags after core audited sources are available.",
            "implementation_difficulty": "medium",
            "pit_complexity": "medium",
            "coverage_impact": "medium",
            "recommended_next_task": "tech_bottleneck_news_source_mapping_v1",
            "acceptance_criteria": "event taxonomy mapped; noisy sources flagged; conflict handling included.",
        },
        {
            "priority_rank": 5,
            "source_category": "broker_report",
            "why_priority": "Already partially available but coverage is only 4 standard reports.",
            "expected_impact": "Improve thesis detail and commercial validation coverage without relying on it alone.",
            "implementation_difficulty": "low",
            "pit_complexity": "low",
            "coverage_impact": "medium",
            "recommended_next_task": "tech_bottleneck_broker_report_evidence_expansion_v1",
            "acceptance_criteria": "More source-backed events; confidence audit; source freshness distribution.",
        },
    ]
    return pd.DataFrame(rows)


def build_pit_checklist_text() -> str:
    return """# PIT Source Validation Checklist

## PIT 基本规则

- source_date <= trade_date
- as_of_date <= trade_date
- financial_as_of_date <= trade_date
- announcement_date <= trade_date
- no future report / future announcement / future financials

## 字段质量规则

- required fields completeness
- duplicate source handling
- source_id uniqueness
- asset_id mapping validation
- date parsing validation
- source_type validation
- confidence score range
- missing behavior
- conflict handling

## 审计指标

- coverage ratio
- usable ratio
- lookahead violation rows
- missing critical field ratio
- source freshness distribution
- degraded coverage rows
- conflict rows
- human review required rows

## 失败处理

- degraded coverage does not stop output generation
- invalid PIT rows must be excluded
- missing fields must remain missing
- no 0.6 missing penalty
- no execution-oriented instruction fields
"""


def render_main_report(
    *,
    inventory: pd.DataFrame,
    gap: pd.DataFrame,
    roadmap: pd.DataFrame,
    report_quality: pd.DataFrame,
    git_info: dict[str, str],
    scanned_paths: list[str],
) -> str:
    quality_lookup = dict(zip(report_quality.get("metric", []), report_quality.get("value", []))) if not report_quality.empty else {}
    inventory = inventory.copy()
    for column in ["pit_ready", "coverage_estimate", "quality_risk"]:
        if column not in inventory.columns:
            inventory[column] = "missing"
    inventory_table = inventory[["source_category", "existing_in_project", "pit_ready", "coverage_estimate", "quality_risk"]].to_markdown(index=False)
    gap_summary = gap.groupby(["source_category", "gap_severity"], as_index=False).size().rename(columns={"size": "asset_source_rows"})
    roadmap_table = roadmap[["priority_rank", "source_category", "recommended_next_task", "expected_impact", "acceptance_criteria"]].to_markdown(index=False)
    text = f"""# Tech Bottleneck Research Source Expansion Plan v1

## 1. Executive Summary

- The watchlist stock report generator is usable for internal research review, but source coverage remains incomplete.
- Current standard report count: {quality_lookup.get('generated_report_count', 'missing')}; degraded coverage rows: {quality_lookup.get('reports_with_degraded_coverage', 'missing')}.
- Largest source gaps are fundamentals and valuation: current reports show missing fundamentals and valuation for every standard watchlist asset.
- Existing project infrastructure already has partial broker report, public news, CNINFO disclosure, finance/fundamental, and factor-value related code.
- Next source to build first: announcement, because it is PIT-auditable and directly supports event / risk review.
- Dashboard decision: read-only internal review is acceptable; Daily Review Lite needs visible degraded-source warnings; production dashboard should wait.
- Continue to defer the technical execution layer until source coverage improves.
- No execution-oriented instruction output is produced by this plan.
- Formal strategy files remain untracked in git; this task does not write them, but git diff alone cannot fully prove historical immutability.

## 2. Current Report Quality Recap

- report count: {quality_lookup.get('generated_report_count', 'missing')}
- degraded coverage: {quality_lookup.get('reports_with_degraded_coverage', 'missing')}
- broker_report support: {quality_lookup.get('reports_with_broker_report_support', 'missing')}
- news support: {quality_lookup.get('reports_with_news_support', 'missing')}
- announcement support: {quality_lookup.get('reports_with_announcement_support', 'missing')}
- fundamentals support: {quality_lookup.get('reports_with_fundamentals_support', 'missing')}
- valuation support: {quality_lookup.get('reports_with_valuation_support', 'missing')}
- missing fundamentals: {quality_lookup.get('reports_missing_fundamentals', 'missing')}
- missing valuation: {quality_lookup.get('reports_missing_valuation', 'missing')}

## 3. Source Inventory

{inventory_table}

## 4. Watchlist Source Gap by Asset

{gap_summary.to_markdown(index=False)}

## 5. Field Mapping Plan

`source_field_mapping_plan.csv` maps announcement, news, fundamentals, valuation, and broker_report raw fields into the research input contract. Missing fields remain missing and are not converted into confidence penalties.

## 6. Priority Roadmap

{roadmap_table}

## 7. PIT Validation Checklist

See `pit_source_validation_checklist.md`. The core acceptance condition is zero lookahead rows and explicit missing behavior.

## 8. Dashboard Readiness Decision

- `read_only_internal_review`: yes, with degraded-source warnings.
- `daily_review_lite`: conditional; show as source-gap review only, not as complete stock research.
- `production_dashboard`: no; fundamentals, valuation, announcement, and news gaps are too large.

## 9. What This Plan Does Not Do

- Does not create execution instructions.
- Does not alter Top5.
- Does not alter formal strategy logic.
- Does not evaluate the technical execution layer.
- Does not use evidence multiplier.

## 10. Recommended Next Step

Recommended order:

1. `tech_bottleneck_announcement_source_ingestion_v1`
2. `tech_bottleneck_fundamental_source_adapter_v1`
3. `tech_bottleneck_valuation_source_adapter_v1`
4. `tech_bottleneck_news_source_mapping_v1`
5. `tech_bottleneck_broker_report_evidence_expansion_v1`

## 11. Appendix

Generated files:

- `research_source_inventory.csv`
- `watchlist_source_gap_by_asset.csv`
- `source_field_mapping_plan.csv`
- `source_priority_roadmap.csv`
- `pit_source_validation_checklist.md`
- `research_source_expansion_plan_v1.md`

Git status for formal strategy files:

```text
repo_root: {git_info.get('repo_root')}
status:
{git_info.get('formal_strategy_status') or '(empty)'}
ls-files:
{git_info.get('formal_strategy_ls_files') or '(empty; files are not tracked)'}
stat:
{git_info.get('formal_strategy_stat')}
```

Scanned path count: {len(scanned_paths)}

Example scanned paths:

```text
{chr(10).join(scanned_paths[:80])}
```
"""
    return text


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


def run(output_dir: Path = OUTPUT_DIR, project_root: Path | None = None) -> dict[str, pd.DataFrame]:
    repo_root = project_root or Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_index = pd.read_csv(WATCHLIST_REPORT_DIR / "tech_bottleneck_watchlist_report_index.csv", low_memory=False)
    report_quality = pd.read_csv(WATCHLIST_REPORT_DIR / "tech_bottleneck_watchlist_report_quality_audit.csv", low_memory=False)
    scanned_paths = _scan_paths(repo_root)
    inventory = build_source_inventory(repo_root)
    gap = build_watchlist_source_gap(report_index)
    mapping = build_source_field_mapping_plan()
    roadmap = build_source_priority_roadmap()
    checklist = build_pit_checklist_text()
    main_report = render_main_report(
        inventory=inventory,
        gap=gap,
        roadmap=roadmap,
        report_quality=report_quality,
        git_info=_git_info(repo_root),
        scanned_paths=scanned_paths,
    )
    if contains_actionable_trading_language(main_report):
        raise ValueError("main report contains actionable trading language")
    inventory.to_csv(output_dir / "research_source_inventory.csv", index=False)
    gap.to_csv(output_dir / "watchlist_source_gap_by_asset.csv", index=False)
    mapping.to_csv(output_dir / "source_field_mapping_plan.csv", index=False)
    roadmap.to_csv(output_dir / "source_priority_roadmap.csv", index=False)
    (output_dir / "pit_source_validation_checklist.md").write_text(checklist, encoding="utf-8")
    (output_dir / "research_source_expansion_plan_v1.md").write_text(main_report, encoding="utf-8")
    return {"inventory": inventory, "gap": gap, "mapping": mapping, "roadmap": roadmap}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Tech Bottleneck research source expansion plan v1.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir), project_root=Path.cwd())
    print(f"inventory_rows={len(result['inventory'])}")
    print(f"gap_rows={len(result['gap'])}")
    print(result["roadmap"][["priority_rank", "source_category", "recommended_next_task"]].to_string(index=False))


if __name__ == "__main__":
    main()
