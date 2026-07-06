#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = "a_share_doubled_tech_stock_strict_theme_quality_audit_v1"
PATTERN_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stock_pattern_study_v1"
SCAN_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stocks_since_20250101_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stock_strict_theme_quality_audit_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
SPECIAL_CASES = [
    "胜宏科技",
    "中际旭创",
    "新易盛",
    "天孚通信",
    "寒武纪",
    "源杰科技",
    "北方华创",
    "中微公司",
    "华海清科",
    "安集科技",
    "长川科技",
    "中科飞测",
]
STRICT_HARD_TECH_THEMES = {
    "AI chip / AI computing hardware",
    "optical module / CPO / optical chip / optical communication",
    "AI PCB / high-speed board / AI server component",
    "semiconductor equipment",
    "semiconductor materials",
    "semiconductor testing / advanced packaging",
    "memory / storage",
    "industrial software / EDA / simulation",
    "robotics core component: reducer / servo / controller / sensor",
    "high-end equipment / instrumentation",
    "key power electronics / grid equipment",
    "advanced material with clear bottleneck relevance",
}
STRICT_CATEGORIES = [
    "confirmed_hard_tech_doubler",
    "likely_hard_tech_doubler",
    "broad_tech_application_doubler",
    "theme_or_sentiment_driven_doubler",
    "concept_only_or_weak_tech_doubler",
    "non_tech_false_positive",
]
PRIMARY_DRIVER_VALUES = {
    "earnings",
    "AI_theme",
    "supply_chain_scarcity",
    "domestic_substitution",
    "product_cycle",
    "customer_validation",
    "policy",
    "sentiment",
    "liquidity",
    "technical_breakout",
    "unknown",
}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _normalize_code(value: Any) -> str:
    text = _clean(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str})
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_normalize_code)
    return frame


def _load_inputs() -> pd.DataFrame:
    master = _read_csv(PATTERN_DIR / "doubled_tech_stock_pattern_master.csv")
    scan = _read_csv(SCAN_DIR / "doubled_tech_stocks.csv")
    path = _read_csv(PATTERN_DIR / "doubling_path_features.csv")
    technical = _read_csv(PATTERN_DIR / "pre_breakout_technical_features.csv")
    fundamental = _read_csv(PATTERN_DIR / "fundamental_features.csv")
    sentiment = _read_csv(PATTERN_DIR / "sentiment_and_theme_features.csv")
    archetype = _read_csv(PATTERN_DIR / "pattern_archetype_classification.csv")
    catalyst = _read_csv(PATTERN_DIR / "catalyst_event_timeline.csv")

    if len(master) != 596:
        raise ValueError(f"Expected 596 pattern rows, found {len(master)}. Re-run {PATTERN_DIR.name} first.")

    catalyst_quality = _catalyst_quality_by_stock(catalyst)
    merged = (
        master.rename(columns={"strict_theme": "original_theme"})
        .merge(
            scan[
                [
                    "stock_code",
                    "exchange",
                    "listing_date",
                    "industry",
                    "concept_tags",
                    "tech_theme",
                    "hard_tech_relevance",
                    "evidence_source",
                    "source_url",
                ]
            ],
            on="stock_code",
            how="left",
        )
        .merge(path[["stock_code", "max_return_since_20250101", "number_of_limit_up_days", "max_drawdown_after_100pct"]], on="stock_code", how="left")
        .merge(
            technical[
                [
                    "stock_code",
                    "breakout_type",
                    "volume_ratio_20d_vs_120d",
                    "amount_ratio_20d_vs_120d",
                    "ma20_slope",
                    "ma60_slope",
                    "distance_to_120d_high_before_breakout",
                ]
            ].rename(columns={"breakout_type": "technical_breakout_type"}),
            on="stock_code",
            how="left",
        )
        .merge(
            fundamental[
                [
                    "stock_code",
                    "revenue_growth_ttm",
                    "net_profit_growth_ttm",
                    "operating_cash_flow",
                    "fundamental_data_status",
                ]
            ],
            on="stock_code",
            how="left",
        )
        .merge(
            sentiment[
                [
                    "stock_code",
                    "news_count_30d_before_breakout",
                    "research_report_count_60d_before_breakout",
                    "theme_news_burst",
                    "research_attention_burst",
                ]
            ],
            on="stock_code",
            how="left",
        )
        .merge(archetype[["stock_code", "primary_pattern_reason"]], on="stock_code", how="left")
        .merge(catalyst_quality, on="stock_code", how="left")
    )
    return merged


def _catalyst_quality_by_stock(catalyst: pd.DataFrame) -> pd.DataFrame:
    if catalyst.empty:
        return pd.DataFrame(columns=["stock_code", "source_backed_catalyst_count", "missing_catalyst_count"])
    catalyst = catalyst.copy()
    catalyst["has_source"] = ~catalyst["source_type"].fillna("").eq("evidence_required")
    return (
        catalyst.groupby("stock_code")
        .agg(
            source_backed_catalyst_count=("has_source", "sum"),
            missing_catalyst_count=("has_source", lambda values: int((~values).sum())),
        )
        .reset_index()
    )


def _row_text(row: pd.Series) -> str:
    return " ".join(
        _clean(row.get(column))
        for column in [
            "stock_name",
            "industry",
            "concept_tags",
            "tech_theme",
            "hard_tech_relevance",
            "original_theme",
            "primary_pattern_reason",
        ]
    )


def _strict_theme(row: pd.Series) -> str:
    text = _row_text(row)
    original = _clean(row.get("original_theme"))
    if any(k in text for k in ["中际旭创", "新易盛", "天孚通信", "源杰科技", "联特科技", "光模块", "光通信", "光芯片", "CPO"]):
        return "optical module / CPO / optical chip / optical communication"
    if any(k in text for k in ["胜宏科技", "沪电股份", "生益电子", "生益科技", "PCB", "印制电路", "高频", "高速"]):
        return "AI PCB / high-speed board / AI server component"
    if any(k in text for k in ["寒武纪", "AI芯片", "国产算力", "GPU", "算力"]):
        return "AI chip / AI computing hardware"
    if any(k in text for k in ["江波龙", "佰维存储", "德明利", "存储", "memory"]):
        return "memory / storage"
    if any(k in text for k in ["长川科技", "中科飞测", "精测电子", "金海通", "检测", "量测", "先进封装"]):
        return "semiconductor testing / advanced packaging"
    if any(k in text for k in ["北方华创", "中微公司", "华海清科", "芯碁微装", "半导体设备", "刻蚀", "清洗设备", "CMP设备", "专用设备"]):
        return "semiconductor equipment"
    if any(k in text for k in ["安集科技", "江丰电子", "光刻胶", "抛光液", "抛光垫", "电子特气", "靶材", "半导体材料", "电子专用材料"]):
        return "semiconductor materials"
    if any(k in text for k in ["EDA", "CAD", "CAE", "工业软件", "仿真", "基础软件"]):
        return "industrial software / EDA / simulation"
    if any(k in text for k in ["机器人", "伺服", "减速器", "控制器", "传感器", "运动控制"]):
        return "robotics core component: reducer / servo / controller / sensor"
    if any(k in text for k in ["电网", "电力电子", "功率器件", "IGBT", "SiC", "特高压", "继电保护", "智能电网"]):
        return "key power electronics / grid equipment"
    if any(k in text for k in ["高温合金", "PI膜", "碳纤维", "陶瓷", "高纯材料", "关键材料", "特种材料"]):
        return "advanced material with clear bottleneck relevance"
    if any(k in text for k in ["仪器", "科学仪器", "精密检测", "高端装备", "工业母机", "数控", "激光加工"]):
        return "high-end equipment / instrumentation"
    if original == "consumer electronics / edge AI":
        return "consumer electronics / edge AI"
    if original == "low-altitude economy / satellite / defense electronics":
        return "low-altitude economy / satellite / defense electronics"
    if original == "broad tech application":
        return "broad tech application"
    return "concept-only or weak-tech"


def _is_obvious_non_tech(row: pd.Series) -> bool:
    text = _row_text(row)
    hard_theme = _strict_theme(row) in STRICT_HARD_TECH_THEMES
    if hard_theme:
        return False
    return any(k in text for k in ["银行", "保险", "证券", "金融", "电力运营", "发电", "公用事业", "照明", "消费", "养殖", "农业"])


def _rank_quality(value: str) -> int:
    return {"missing": 0, "weak": 1, "moderate": 2, "strong": 3}.get(value, 0)


def _fundamental_strength(row: pd.Series) -> str:
    if _clean(row.get("fundamental_data_status")) != "partial_source_available":
        return "missing"
    revenue = pd.to_numeric(pd.Series([row.get("revenue_growth_ttm")]), errors="coerce").iloc[0]
    profit = pd.to_numeric(pd.Series([row.get("net_profit_growth_ttm")]), errors="coerce").iloc[0]
    cash = pd.to_numeric(pd.Series([row.get("operating_cash_flow")]), errors="coerce").iloc[0]
    if (pd.notna(revenue) and revenue >= 0.30) or (pd.notna(profit) and profit >= 0.50):
        return "strong"
    if (pd.notna(revenue) and revenue >= 0.10) or (pd.notna(profit) and profit >= 0.20) or (pd.notna(cash) and cash > 0):
        return "moderate"
    return "weak"


def _sentiment_strength(row: pd.Series) -> str:
    news_count = int(row.get("news_count_30d_before_breakout") or 0)
    report_count = int(row.get("research_report_count_60d_before_breakout") or 0)
    limit_up_days = int(row.get("number_of_limit_up_days") or 0)
    if bool(row.get("theme_news_burst")) or bool(row.get("research_attention_burst")) or news_count >= 3 or report_count >= 2 or limit_up_days >= 5:
        return "strong"
    if news_count >= 1 or report_count >= 1 or limit_up_days >= 2:
        return "moderate"
    return "weak"


def _technical_quality(row: pd.Series) -> str:
    breakout = _clean(row.get("technical_breakout_type"), _clean(row.get("breakout_type")))
    volume_ratio = pd.to_numeric(pd.Series([row.get("volume_ratio_20d_vs_120d")]), errors="coerce").iloc[0]
    amount_ratio = pd.to_numeric(pd.Series([row.get("amount_ratio_20d_vs_120d")]), errors="coerce").iloc[0]
    if breakout in {"low_base_breakout", "new_high_breakout", "gap_up_catalyst"} and (
        (pd.notna(volume_ratio) and volume_ratio >= 1.2) or (pd.notna(amount_ratio) and amount_ratio >= 1.2)
    ):
        return "strong"
    if breakout in {"low_base_breakout", "new_high_breakout", "gap_up_catalyst", "trend_continuation", "limit_up_cluster"}:
        return "moderate"
    return "weak"


def _catalyst_quality(row: pd.Series) -> str:
    backed = int(row.get("source_backed_catalyst_count") or 0)
    missing = int(row.get("missing_catalyst_count") or 0)
    if backed >= 2:
        return "strong"
    if backed == 1:
        return "moderate"
    if missing:
        return "missing"
    return "weak"


def _evidence_quality(row: pd.Series, strict_theme: str) -> str:
    source = _clean(row.get("evidence_source"))
    relevance = _clean(row.get("hard_tech_relevance"))
    if "candidate_universe" in source and strict_theme in STRICT_HARD_TECH_THEMES:
        if "Tier A" in _clean(row.get("concept_tags")) or "Tier A" in relevance:
            return "strong"
        return "moderate"
    if strict_theme in STRICT_HARD_TECH_THEMES:
        return "weak"
    if source:
        return "weak"
    return "missing"


def _primary_driver(row: pd.Series, strict_theme: str, fundamental: str, sentiment: str, technical: str) -> str:
    event = _clean(row.get("sentiment_event_type"))
    archetype = _clean(row.get("pattern_archetype"))
    if fundamental in {"strong", "moderate"} and event == "earnings":
        return "earnings"
    if strict_theme in {
        "AI chip / AI computing hardware",
        "optical module / CPO / optical chip / optical communication",
        "AI PCB / high-speed board / AI server component",
    }:
        return "AI_theme"
    if strict_theme in {"semiconductor equipment", "semiconductor materials", "semiconductor testing / advanced packaging", "memory / storage"}:
        return "domestic_substitution"
    if strict_theme in {"advanced material with clear bottleneck relevance", "key power electronics / grid equipment"}:
        return "supply_chain_scarcity"
    if event in {"order", "product launch", "overseas supply chain"}:
        return "customer_validation" if event == "overseas supply chain" else "product_cycle"
    if event == "policy":
        return "policy"
    if sentiment == "strong" or archetype == "limit_up_sentiment_wave":
        return "sentiment"
    if technical == "strong":
        return "technical_breakout"
    return "unknown"


def _hard_tech_relevance(strict_theme: str, category: str) -> str:
    if category == "confirmed_hard_tech_doubler":
        return "high"
    if category == "likely_hard_tech_doubler":
        return "medium_high"
    if strict_theme in STRICT_HARD_TECH_THEMES:
        return "medium"
    if category == "non_tech_false_positive":
        return "none"
    return "low"


def _classify(row: pd.Series) -> dict[str, Any]:
    strict_theme = _strict_theme(row)
    fundamental = _fundamental_strength(row)
    sentiment = _sentiment_strength(row)
    technical = _technical_quality(row)
    catalyst = _catalyst_quality(row)
    evidence = _evidence_quality(row, strict_theme)
    driver = _primary_driver(row, strict_theme, fundamental, sentiment, technical)
    is_false_positive = _is_obvious_non_tech(row)
    is_hard_theme = strict_theme in STRICT_HARD_TECH_THEMES
    original_theme = _clean(row.get("original_theme"))
    archetype = _clean(row.get("pattern_archetype"))

    if is_false_positive:
        category = "non_tech_false_positive"
    elif is_hard_theme and _rank_quality(evidence) >= 2 and (fundamental != "missing" or catalyst != "missing" or technical == "strong"):
        category = "confirmed_hard_tech_doubler"
    elif is_hard_theme:
        category = "likely_hard_tech_doubler"
    elif original_theme == "broad tech application" or strict_theme == "broad tech application":
        category = "broad_tech_application_doubler"
    elif sentiment == "strong" or archetype == "limit_up_sentiment_wave" or driver in {"sentiment", "policy"}:
        category = "theme_or_sentiment_driven_doubler"
    else:
        category = "concept_only_or_weak_tech_doubler"

    rationale_parts = [
        f"strict_theme={strict_theme}",
        f"original_theme={original_theme or 'missing'}",
        f"evidence={evidence}",
        f"fundamental={fundamental}",
        f"sentiment={sentiment}",
        f"technical={technical}",
        f"primary_driver={driver}",
    ]
    if category == "non_tech_false_positive":
        rationale_parts.append("strict audit identified non-hard-tech business contamination")
    elif category == "broad_tech_application_doubler":
        rationale_parts.append("broad application exposure kept out of confirmed hard-tech")
    elif category == "theme_or_sentiment_driven_doubler":
        rationale_parts.append("move appears more theme/sentiment driven than bottleneck-evidence driven")
    return {
        "strict_theme": strict_theme,
        "strict_quality_category": category,
        "hard_tech_relevance": _hard_tech_relevance(strict_theme, category),
        "fundamental_driver_strength": fundamental,
        "sentiment_driver_strength": sentiment,
        "technical_breakout_quality": technical,
        "catalyst_quality": catalyst,
        "evidence_quality": evidence,
        "primary_doubling_driver": driver if driver in PRIMARY_DRIVER_VALUES else "unknown",
        "rationale": "; ".join(rationale_parts),
    }


def _summarize_theme(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["strict_theme", "stock_count", "median_return", "mean_return", "representative_stocks"])
    return (
        frame.groupby("strict_theme")
        .agg(
            stock_count=("stock_code", "count"),
            median_return=("return_since_20250101", "median"),
            mean_return=("return_since_20250101", "mean"),
            representative_stocks=("stock_name", lambda values: "、".join(list(values.head(8)))),
        )
        .reset_index()
        .sort_values(["stock_count", "median_return"], ascending=[False, False])
    )


def _category_stats(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for category in STRICT_CATEGORIES:
        sub = frame[frame["strict_quality_category"] == category]
        rows.append(
            {
                "strict_quality_category": category,
                "stock_count": int(len(sub)),
                "median_return": float(sub["return_since_20250101"].median()) if not sub.empty else 0.0,
                "mean_return": float(sub["return_since_20250101"].mean()) if not sub.empty else 0.0,
                "top_strict_themes": "、".join(list(sub["strict_theme"].value_counts().head(5).index)),
                "dominant_driver": _clean(sub["primary_doubling_driver"].value_counts().head(1).index[0]) if not sub.empty else "",
            }
        )
    return pd.DataFrame(rows)


def _report(summary: dict[str, Any], stats: pd.DataFrame, confirmed_theme: pd.DataFrame, broad_theme: pd.DataFrame, sentiment_theme: pd.DataFrame, special: pd.DataFrame) -> str:
    return f"""# A-share doubled tech stock strict theme quality audit v1

Research-only strict quality audit. No production signal/admission change was made.

## Scope

- input count: {summary['input_count']}
- confirmed hard-tech doublers: {summary['confirmed_hard_tech_doubler_count']}
- likely hard-tech doublers: {summary['likely_hard_tech_doubler_count']}
- broad tech application doublers: {summary['broad_tech_application_doubler_count']}
- theme or sentiment driven doublers: {summary['theme_or_sentiment_driven_doubler_count']}
- concept-only or weak-tech doublers: {summary['concept_only_or_weak_tech_doubler_count']}
- non-tech false positives: {summary['non_tech_false_positive_count']}
- allowed_for_signal_count: {summary['allowed_for_signal_count']}
- allowed_for_admission_count: {summary['allowed_for_admission_count']}

## How many of the 596 are confirmed/likely hard-tech doublers?

Confirmed plus likely hard-tech doublers: {summary['confirmed_and_likely_hard_tech_count']}. The rest are kept in separate broad-tech, sentiment/theme, weak-tech, or false-positive files.

## How many are broad tech or concept/theme-driven doublers?

Broad tech, sentiment/theme, weak-tech, and false-positive rows total {summary['non_confirmed_hard_tech_count']}. They remain useful for pattern study, but are not mixed into confirmed hard-tech results.

## Which strict hard-tech themes produced the strongest doublers?

{confirmed_theme.to_markdown(index=False)}

## Broad tech application summary

{broad_theme.to_markdown(index=False)}

## Sentiment/theme-driven summary

{sentiment_theme.to_markdown(index=False)}

## What features distinguish hard-tech doublers from broad-tech/theme doublers?

Confirmed hard-tech rows must map to a stricter hard-tech theme and have at least moderate evidence plus a non-price quality signal such as fundamental source availability, catalyst support, or strong technical breakout quality. Broad-tech rows are separated when the prior label is broad application exposure or the strict theme cannot be tied to a bottleneck layer. Sentiment/theme-driven rows are separated when limit-up clusters, theme bursts, or weak evidence dominate.

## Which early features are reusable for future research?

Reusable research features are: strict hard-tech theme, primary doubling driver, catalyst quality, evidence quality, 20/120-day volume and amount expansion, breakout type, and whether the move was mainly sentiment-driven. These are research workflow features only.

## Special case audit

{special[['stock_code', 'stock_name', 'strict_theme', 'strict_quality_category', 'primary_doubling_driver', 'evidence_quality']].to_markdown(index=False)}

## Strict pattern statistics by category

{stats.to_markdown(index=False)}

## Guardrails

- research_only: true
- used_for_signal_count: {summary['used_for_signal_count']}
- used_for_admission_count: {summary['used_for_admission_count']}
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- production_update: false

## Acceptance

This audit is complete when tests pass and formal strategy file diff remains empty.
"""


def generate(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    merged = _load_inputs()
    classifications = merged.apply(_classify, axis=1, result_type="expand")
    result = pd.concat([merged, classifications], axis=1)
    result["max_return_since_20250101"] = pd.to_numeric(result["max_return_since_20250101"], errors="coerce")
    result["return_since_20250101"] = pd.to_numeric(result["return_since_20250101"], errors="coerce")
    result["research_only"] = True
    result["used_for_signal"] = False
    result["used_for_admission"] = False

    output_columns = [
        "stock_code",
        "stock_name",
        "return_since_20250101",
        "max_return_since_20250101",
        "original_theme",
        "strict_theme",
        "strict_quality_category",
        "hard_tech_relevance",
        "fundamental_driver_strength",
        "sentiment_driver_strength",
        "technical_breakout_quality",
        "catalyst_quality",
        "evidence_quality",
        "primary_doubling_driver",
        "rationale",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    master = result[output_columns].sort_values(
        ["strict_quality_category", "strict_theme", "return_since_20250101", "stock_code"],
        ascending=[True, True, False, True],
    )
    master.to_csv(output_dir / "strict_theme_quality_master.csv", index=False)

    category_files = {
        "confirmed_hard_tech_doubler": "confirmed_hard_tech_doublers.csv",
        "likely_hard_tech_doubler": "likely_hard_tech_doublers.csv",
        "broad_tech_application_doubler": "broad_tech_application_doublers.csv",
        "theme_or_sentiment_driven_doubler": "theme_or_sentiment_driven_doublers.csv",
        "concept_only_or_weak_tech_doubler": "concept_only_or_weak_tech_doublers.csv",
        "non_tech_false_positive": "non_tech_false_positives.csv",
    }
    for category, filename in category_files.items():
        master[master["strict_quality_category"] == category].to_csv(output_dir / filename, index=False)

    confirmed_theme = _summarize_theme(master[master["strict_quality_category"] == "confirmed_hard_tech_doubler"])
    broad_theme = _summarize_theme(master[master["strict_quality_category"] == "broad_tech_application_doubler"])
    sentiment_theme = _summarize_theme(master[master["strict_quality_category"] == "theme_or_sentiment_driven_doubler"])
    stats = _category_stats(master)
    special = master[master["stock_name"].isin(SPECIAL_CASES)].sort_values("stock_name")

    confirmed_theme.to_csv(output_dir / "confirmed_hard_tech_theme_summary.csv", index=False)
    broad_theme.to_csv(output_dir / "broad_tech_application_theme_summary.csv", index=False)
    sentiment_theme.to_csv(output_dir / "sentiment_driven_theme_summary.csv", index=False)
    stats.to_csv(output_dir / "strict_pattern_statistics_by_category.csv", index=False)
    special.to_csv(output_dir / "special_case_strict_audit.csv", index=False)

    strategy_diff = _git_diff_formal_strategy_files()
    counts = master["strict_quality_category"].value_counts().to_dict()
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "input_count": int(len(merged)),
        "master_rows": int(len(master)),
        "confirmed_hard_tech_doubler_count": int(counts.get("confirmed_hard_tech_doubler", 0)),
        "likely_hard_tech_doubler_count": int(counts.get("likely_hard_tech_doubler", 0)),
        "broad_tech_application_doubler_count": int(counts.get("broad_tech_application_doubler", 0)),
        "theme_or_sentiment_driven_doubler_count": int(counts.get("theme_or_sentiment_driven_doubler", 0)),
        "concept_only_or_weak_tech_doubler_count": int(counts.get("concept_only_or_weak_tech_doubler", 0)),
        "non_tech_false_positive_count": int(counts.get("non_tech_false_positive", 0)),
        "confirmed_and_likely_hard_tech_count": int(counts.get("confirmed_hard_tech_doubler", 0) + counts.get("likely_hard_tech_doubler", 0)),
        "non_confirmed_hard_tech_count": int(len(master) - counts.get("confirmed_hard_tech_doubler", 0)),
        "special_case_count": int(len(special)),
        "allowed_for_signal_count": 0,
        "allowed_for_admission_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "acceptance_decision": "strict_theme_quality_audit_ready" if strategy_diff == "" else "blocked_due_to_strategy_diff",
    }
    _write_json(output_dir / "strict_theme_quality_audit_summary.json", summary)
    report = _report(summary, stats, confirmed_theme, broad_theme, sentiment_theme, special)
    (output_dir / "strict_theme_quality_audit_report.md").write_text(report, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = generate(output_dir=args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
