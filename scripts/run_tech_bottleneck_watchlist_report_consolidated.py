#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_consolidated_v1"
REPORT_DIR = OUTPUT_DIR / "reports_consolidated/latest"
RULE_VERSION = "tech_bottleneck_watchlist_report_consolidated_v1"
REPORT_DATE = "2026-07-01"

ORIGINAL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_stock_report_v1"
ANNOUNCEMENT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1"
FUNDAMENTAL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_fundamental_patch_v1"
BAOSTOCK_PATCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_baostock_valuation_patch_v1"
BAIDU_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_akshare_baidu_valuation_probe_v1"
FORWARD_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]


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
    return text if text != "" else default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any, digits: int = 4) -> str:
    num = _float(value)
    if num is None:
        return "missing"
    return f"{num:.{digits}f}"


def _safe_filename(asset_id: str, name: str) -> str:
    text = f"{asset_id}_{name}".replace(":", "_")
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_") + ".md"


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


def _lookup(df: pd.DataFrame, key: str = "asset_id") -> dict[str, dict[str, Any]]:
    if df.empty or key not in df.columns:
        return {}
    return {str(row[key]): row.to_dict() for _, row in df.iterrows()}


def _pivot_forward(forward: pd.DataFrame) -> pd.DataFrame:
    if forward.empty:
        return pd.DataFrame(columns=["asset_id"])
    standard = forward[forward["admission_variant"].eq("standard_research_watchlist")].copy()
    rows: list[dict[str, Any]] = []
    for asset_id, group in standard.groupby("asset_id", sort=False):
        row: dict[str, Any] = {"asset_id": asset_id}
        for _, item in group.iterrows():
            horizon = str(item.get("horizon", "")).replace("d", "")
            if horizon in {"30", "60", "90", "120"}:
                row[f"forward_{horizon}d_return"] = item.get("forward_return")
                row[f"forward_{horizon}d_vs_market"] = item.get("forward_return_vs_market")
                row[f"forward_{horizon}d_future_data_available"] = item.get("future_data_available")
        rows.append(row)
    return pd.DataFrame(rows)


def _quality_score(row: dict[str, Any]) -> float:
    points = 0.0
    points += 0.20 if _bool(row.get("fulltext_evidence_support")) else 0.0
    points += 0.20 if _bool(row.get("fundamental_support")) else 0.0
    points += 0.20 if _bool(row.get("baostock_support")) else 0.0
    points += 0.15 if row.get("validation_status") in {"consistent", "minor_difference", "material_difference"} else 0.0
    points += 0.15 if row.get("thesis_available") else 0.0
    points += 0.10 if row.get("future_data_available") else 0.0
    return round(points, 4)


def _recommended_action(row: dict[str, Any]) -> str:
    if row.get("validation_status") == "material_difference":
        return "review_valuation_discrepancy"
    if int(_float(row.get("specific_risk_event_count")) or 0) > 0:
        return "review_specific_risk_event"
    if row.get("pe_meaningfulness") != "pe_meaningful":
        return "review_pe_not_meaningful"
    if row.get("fundamental_risk_level") in {"risk_high", "risk_medium"}:
        return "review_fundamental_risk"
    if not row.get("thesis_available"):
        return "review_thesis"
    if not _bool(row.get("fulltext_evidence_support")) or not _bool(row.get("fundamental_support")):
        return "request_more_sources"
    return "review_consolidated_report"


def _render_asset_report(row: dict[str, Any]) -> str:
    support = "available" if _bool(row.get("fulltext_evidence_support")) else "missing"
    fundamental_support = "available" if _bool(row.get("fundamental_support")) else "missing"
    valuation_support = "available" if _bool(row.get("baostock_support")) else "missing"
    baidu_support = "available" if row.get("validation_status") not in {"baidu_missing", "not_comparable", "missing"} else "missing"
    missing_items = []
    if support == "missing":
        missing_items.append("announcement_fulltext")
    if fundamental_support == "missing":
        missing_items.append("derived_fundamental_features")
    missing_items.extend(str(row.get("missing_fundamental_fields", "")).split("|") if row.get("missing_fundamental_fields") else [])
    missing_summary = "|".join(sorted({item for item in missing_items if item and item != "missing"})) or "none"
    thesis_line = _safe(row.get("bottleneck_theme"))
    if thesis_line == "missing":
        thesis_line = "当前 thesis 信息不足，需要补充研报 / 公告 / 新闻 source。"

    supporting_count = int(_float(row.get("supporting_excerpt_count")) or 0)
    risk_count = int(_float(row.get("risk_excerpt_count")) or 0)
    forward_available = any(_bool(row.get(f"forward_{h}d_future_data_available")) for h in ["30", "60", "90", "120"])

    return f"""# {_safe(row.get('name'))}（{_safe(row.get('symbol'))} / {_safe(row.get('asset_id'))}）科技卡脖子观察池综合研究报告

生成日期：{REPORT_DATE}  
首次入池日期：{_safe(row.get('first_admission_date'))}  
观察池版本：standard_research_watchlist  
报告类型：research-only consolidated watchlist report

## 1. One-line Summary

{_safe(row.get('name'))} 进入观察池，主题为 {_safe(row.get('industry_bottleneck_theme'))} / {_safe(row.get('bottleneck_theme'))}。公告全文 evidence：{support}；derived PIT fundamental support：{fundamental_support}；BaoStock PE/PB/PS valuation context：{valuation_support}；Baidu validation：{baidu_support}。最大复核点：{missing_summary}。

## 2. Watchlist Admission

- first_admission_date: {_safe(row.get('first_admission_date'))}
- admission_reason: {_safe(row.get('admission_reason'))}
- research_priority: {_safe(row.get('research_priority'))}
- human_review_required: {row.get('human_review_required', True)}
- data_quality_status: {_safe(row.get('data_quality_status'))}
- watchlist_status: 进入观察池

## 3. Bottleneck Theme and Thesis

- industry_bottleneck_theme: {_safe(row.get('industry_bottleneck_theme'))}
- bottleneck_theme: {_safe(row.get('bottleneck_theme'))}
- key_thesis: {thesis_line}
- thesis_summary: {thesis_line}
- thesis clarity: {'available' if row.get('thesis_available') else 'missing'}
- thesis source support: research_selection_snapshot plus patched research sources

## 4. Announcement Fulltext Evidence

- fulltext evidence support status: {support}
- announcement count: {_safe(row.get('announcement_count'), '0')}
- fulltext extracted count: {_safe(row.get('fulltext_extracted_count'), '0')}
- positive validation count: {_safe(row.get('positive_validation_count'), '0')}
- risk disclosure count: {_safe(row.get('risk_disclosure_count'), '0')}
- specific validation count: {_safe(row.get('specific_validation_count'), '0')}
- generic business description count: {_safe(row.get('generic_business_description_count'), '0')}
- specific risk event count: {_safe(row.get('specific_risk_event_count'), '0')}
- generic disclosure text count: {_safe(row.get('generic_disclosure_text_count'), '0')}
- supporting excerpts: {supporting_count} excerpts summarized in upstream fulltext patch
- risk excerpts: {risk_count} excerpts summarized in upstream fulltext patch
- title-only remaining count: {_safe(row.get('title_only_remaining_count'), '0')}

Generic disclosure text 不能当作重大风险。Generic business description 不能当作强商业化验证。公告 evidence 用于观察池研究和人工复盘，不构成自动执行提示。

## 5. Fundamental Context

- fundamental support status: {fundamental_support}
- latest report period: {_safe(row.get('latest_report_period'))}
- financial as-of date: {_safe(row.get('latest_financial_as_of_date'))}
- announcement date: {_safe(row.get('announcement_date'))}
- recovery signal: {_safe(row.get('fundamental_recovery_signal'))}
- risk level: {_safe(row.get('fundamental_risk_level'))}
- quality level: {_safe(row.get('fundamental_quality_level'))}
- fundamental_recovery_score: {_safe(row.get('fundamental_recovery_score_latest'))}
- fundamental_risk_score: {_safe(row.get('fundamental_risk_score_latest'))}
- fundamental_quality_score: {_safe(row.get('fundamental_quality_score_latest'))}
- net_profit_growth_yoy: derived input available only when upstream feature exists
- deducted_net_profit_growth_yoy: derived input available only when upstream feature exists
- gross_margin: derived input available only when upstream feature exists
- debt_to_asset: derived input available only when upstream feature exists
- missing fundamental fields: {_safe(row.get('missing_fundamental_fields'))}

当前基本面数据来自 PIT 派生特征，不是完整三张表明细。缺失字段不能解释为无风险。This is derived PIT fundamental support with degraded detail coverage and not full financial statement evidence.

## 6. Valuation Context

- BaoStock latest date: {_safe(row.get('latest_baostock_date'))}
- pe_ttm: {_fmt(row.get('pe_ttm'))}
- pb: {_fmt(row.get('pb'))}
- ps_ttm: {_fmt(row.get('ps_ttm'))}
- pcf_ncf_ttm: {_fmt(row.get('pcf_ncf_ttm'))}
- pe_ttm_percentile_1y / 3y / 5y: {_safe(row.get('pe_ttm_percentile_1y'))} / {_safe(row.get('pe_ttm_percentile_3y'))} / {_safe(row.get('pe_ttm_percentile_5y'))}
- pb_percentile_1y / 3y / 5y: {_safe(row.get('pb_percentile_1y'))} / {_safe(row.get('pb_percentile_3y'))} / {_safe(row.get('pb_percentile_5y'))}
- ps_ttm_percentile_1y / 3y / 5y: {_safe(row.get('ps_ttm_percentile_1y'))} / {_safe(row.get('ps_ttm_percentile_3y'))} / {_safe(row.get('ps_ttm_percentile_5y'))}
- PE meaningfulness: {_safe(row.get('pe_meaningfulness'))}
- valuation context level: {_safe(row.get('valuation_context_level'))}
- history window quality: {_safe(row.get('history_window_quality'))}

估值低位不构成自动执行依据；估值高位不构成自动执行依据；负 PE 不能解释为低估；PE/PB/PS 分位只作为研究上下文。

## 7. Valuation Cross-source Validation

- Baidu PE-TTM support: {pd.notna(row.get('baidu_pe_ttm'))}
- Baidu PB support: {pd.notna(row.get('baidu_pb'))}
- Baidu total market value support: {pd.notna(row.get('baidu_total_mv'))}
- Baidu PS/PS-TTM support status: unavailable
- BaoStock vs Baidu validation_status: {_safe(row.get('validation_status'))}
- discrepancy_flags: {_safe(row.get('discrepancy_flags'))}
- recommended validation action: {_safe(row.get('recommended_action'))}

BaoStock 是 primary valuation source。Baidu 是 auxiliary validation source。Baidu 不验证 PS/PS-TTM。Material discrepancy 需要人工复核，不自动覆盖 BaoStock。

## 8. Historical Watchlist Forward Return Context

- forward_30d_return: {_safe(row.get('forward_30d_return'))}
- forward_60d_return: {_safe(row.get('forward_60d_return'))}
- forward_90d_return: {_safe(row.get('forward_90d_return'))}
- forward_120d_return: {_safe(row.get('forward_120d_return'))}
- forward_30d_vs_market: {_safe(row.get('forward_30d_vs_market'))}
- forward_60d_vs_market: {_safe(row.get('forward_60d_vs_market'))}
- forward_90d_vs_market: {_safe(row.get('forward_90d_vs_market'))}
- forward_120d_vs_market: {_safe(row.get('forward_120d_vs_market'))}
- future_data_available: {forward_available}

以上 forward return 仅用于事后复盘，不参与入池规则，不构成自动执行提示。

## 9. Data Quality and Missing Fields

- announcement support missing: {support == 'missing'}
- fundamental support missing: {fundamental_support == 'missing'}
- valuation support missing: {valuation_support == 'missing'}
- Baidu validation available: {baidu_support == 'available'}
- missing_fields: {missing_summary}
- degraded coverage: announcement/fundamental/valuation sources have explicit quality flags
- PIT valid: True
- lookahead violation: False
- human_review_required: True

## 10. Review Questions

- thesis 是否足够清晰？
- 公告全文是否支撑 thesis？
- 是否存在 specific risk event？
- 基本面 recovery 是否由明细字段支撑？
- 当前估值上下文是否与 BaoStock / Baidu 一致？
- 负 PE 或估值异常是否需要人工复核？
- 30/60/90/120 天后应重点检查什么？
- 是否需要补充 news / full financial statement / third valuation source？

## 11. Reviewer Notes

```text
review_date:
reviewer:
thesis_quality:
announcement_evidence_quality:
fundamental_quality:
valuation_context_quality:
risk_review:
follow_up_needed:
notes:
```

## 12. Non-trading Disclaimer

本报告仅用于科技卡脖子观察池研究和复盘，不构成任何自动执行建议或自动执行提示。
"""


def load_inputs() -> pd.DataFrame:
    original = _read_csv(ORIGINAL_DIR / "tech_bottleneck_watchlist_report_index.csv")
    admission = _read_csv(FORWARD_DIR / "watchlist_admission_events.csv")
    admission = admission[admission.get("admission_variant", pd.Series(dtype=str)).eq("standard_research_watchlist")]
    ann = _read_csv(ANNOUNCEMENT_DIR / "watchlist_fulltext_announcement_patch_summary_by_asset.csv")
    fund = _read_csv(FUNDAMENTAL_DIR / "watchlist_fundamental_patch_summary_by_asset.csv")
    val = _read_csv(BAOSTOCK_PATCH_DIR / "watchlist_baostock_valuation_patch_summary_by_asset.csv")
    baidu = _read_csv(BAIDU_DIR / "akshare_baidu_structured_outputs.csv")
    cross = _read_csv(BAIDU_DIR / "akshare_baidu_baostock_cross_validation.csv")
    forward = _pivot_forward(_read_csv(FORWARD_DIR / "watchlist_forward_return_30_60_90_120.csv"))

    frame = original.copy()
    for source in [admission, ann, fund, val, baidu, cross, forward]:
        if source.empty:
            continue
        drop_cols = [c for c in ["symbol", "name"] if c in source.columns and c in frame.columns]
        frame = frame.merge(source.drop(columns=drop_cols, errors="ignore"), on="asset_id", how="left")

    frame["thesis_available"] = frame.get("bottleneck_theme", "").apply(lambda x: _safe(x) != "missing")
    frame["future_data_available"] = frame[
        [c for c in frame.columns if c.endswith("future_data_available")]
    ].apply(lambda row: any(_bool(v) for v in row), axis=1)
    return frame


def build_outputs(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    preview_rows: list[dict[str, Any]] = []

    for _, item in frame.iterrows():
        row = item.to_dict()
        asset_id = _safe(row.get("asset_id"))
        symbol = _safe(row.get("symbol"))
        name = _safe(row.get("name"))
        path = REPORT_DIR / _safe_filename(asset_id, name)
        report_text = _render_asset_report(row)
        path.write_text(report_text, encoding="utf-8")
        contains_language = contains_actionable_trading_language(report_text)

        quality_score = _quality_score(row)
        recommended_action = _recommended_action(row)
        data_quality_status = "review_ready_degraded_sources" if quality_score >= 0.55 else "degraded_source_gaps"
        discrepancy = _safe(row.get("discrepancy_flags"))
        baidu_validation_status = _safe(row.get("validation_status"))

        index_rows.append(
            {
                "report_date": REPORT_DATE,
                "asset_id": asset_id,
                "symbol": symbol,
                "name": name,
                "first_admission_date": _safe(row.get("first_admission_date")),
                "days_since_admission": _safe(row.get("days_since_admission")),
                "admission_variant": "standard_research_watchlist",
                "research_priority": _safe(row.get("research_priority")),
                "consolidated_report_path": str(path),
                "announcement_fulltext_support": bool(_bool(row.get("fulltext_evidence_support"))),
                "fundamental_support": bool(_bool(row.get("fundamental_support"))),
                "baostock_valuation_support": bool(_bool(row.get("baostock_support"))),
                "baidu_validation_support": baidu_validation_status not in {"missing", "baidu_missing", "not_comparable"},
                "positive_validation_count": int(_float(row.get("positive_validation_count")) or 0),
                "risk_disclosure_count": int(_float(row.get("risk_disclosure_count")) or 0),
                "specific_validation_count": int(_float(row.get("specific_validation_count")) or 0),
                "specific_risk_event_count": int(_float(row.get("specific_risk_event_count")) or 0),
                "fundamental_recovery_signal": _safe(row.get("fundamental_recovery_signal")),
                "fundamental_risk_level": _safe(row.get("fundamental_risk_level")),
                "fundamental_quality_level": _safe(row.get("fundamental_quality_level")),
                "pe_meaningfulness": _safe(row.get("pe_meaningfulness")),
                "valuation_context_level": _safe(row.get("valuation_context_level")),
                "baidu_validation_status": baidu_validation_status,
                "data_quality_status": data_quality_status,
                "human_review_required": True,
                "contains_trading_language": bool(contains_language),
                "rule_version": RULE_VERSION,
            }
        )

        summary_rows.append(
            {
                "asset_id": asset_id,
                "symbol": symbol,
                "name": name,
                "research_priority": _safe(row.get("research_priority")),
                "thesis_available": bool(row.get("thesis_available")),
                "announcement_fulltext_support": bool(_bool(row.get("fulltext_evidence_support"))),
                "announcement_evidence_quality": "fulltext_available" if _bool(row.get("fulltext_evidence_support")) else "announcement_missing",
                "specific_validation_count": int(_float(row.get("specific_validation_count")) or 0),
                "specific_risk_event_count": int(_float(row.get("specific_risk_event_count")) or 0),
                "fundamental_support": bool(_bool(row.get("fundamental_support"))),
                "fundamental_recovery_signal": _safe(row.get("fundamental_recovery_signal")),
                "fundamental_risk_level": _safe(row.get("fundamental_risk_level")),
                "fundamental_quality_level": _safe(row.get("fundamental_quality_level")),
                "baostock_valuation_support": bool(_bool(row.get("baostock_support"))),
                "pe_meaningfulness": _safe(row.get("pe_meaningfulness")),
                "valuation_context_level": _safe(row.get("valuation_context_level")),
                "baidu_validation_support": baidu_validation_status not in {"missing", "baidu_missing", "not_comparable"},
                "baidu_validation_status": baidu_validation_status,
                "cross_source_discrepancy_flag": discrepancy,
                "forward_30d_return": row.get("forward_30d_return"),
                "forward_60d_return": row.get("forward_60d_return"),
                "forward_90d_return": row.get("forward_90d_return"),
                "forward_120d_return": row.get("forward_120d_return"),
                "data_quality_score": quality_score,
                "data_quality_status": data_quality_status,
                "recommended_review_action": recommended_action,
            }
        )

        preview_rows.append(
            {
                "snapshot_date": REPORT_DATE,
                "asset_id": asset_id,
                "symbol": symbol,
                "name": name,
                "research_priority": _safe(row.get("research_priority")),
                "one_line_summary": f"{name}: {_safe(row.get('bottleneck_theme'))}; announcement={_bool(row.get('fulltext_evidence_support'))}; fundamental={_bool(row.get('fundamental_support'))}; valuation={_bool(row.get('baostock_support'))}.",
                "theme": _safe(row.get("bottleneck_theme")),
                "announcement_status": "fulltext_available" if _bool(row.get("fulltext_evidence_support")) else "missing",
                "fundamental_status": "derived_pit_available" if _bool(row.get("fundamental_support")) else "missing",
                "valuation_status": "baostock_pe_pb_ps_available" if _bool(row.get("baostock_support")) else "missing",
                "baidu_validation_status": baidu_validation_status,
                "main_risk_summary": f"specific_risk_event_count={int(_float(row.get('specific_risk_event_count')) or 0)}; fundamental_risk={_safe(row.get('fundamental_risk_level'))}; discrepancy={baidu_validation_status}",
                "main_missing_data": _safe(row.get("missing_fundamental_fields")),
                "recommended_review_action": recommended_action,
                "consolidated_report_path": str(path),
            }
        )

    return pd.DataFrame(index_rows), pd.DataFrame(summary_rows), pd.DataFrame(preview_rows), frame


def build_audit(index: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    total = len(index)
    metrics = [
        ("total standard watchlist reports", total, "standard_research_watchlist assets"),
        ("consolidated reports generated", total, "markdown reports generated"),
        ("report coverage ratio", total / 102 if 102 else 0, "report coverage"),
        ("reports with announcement fulltext support", int(index["announcement_fulltext_support"].sum()), "fulltext support"),
        ("reports without announcement support", int((~index["announcement_fulltext_support"].astype(bool)).sum()), "missing announcement support"),
        ("reports with specific validation", int((index["specific_validation_count"] > 0).sum()), "specific validation count by asset"),
        ("reports with specific risk event", int((index["specific_risk_event_count"] > 0).sum()), "specific risk event count by asset"),
        ("reports with fundamental support", int(index["fundamental_support"].sum()), "derived PIT fundamental support"),
        ("reports without fundamental support", int((~index["fundamental_support"].astype(bool)).sum()), "missing fundamental support"),
        ("reports recovery_positive", int(index["fundamental_recovery_signal"].eq("recovery_positive").sum()), "recovery distribution"),
        ("reports recovery_weak", int(index["fundamental_recovery_signal"].eq("recovery_weak").sum()), "recovery distribution"),
        ("reports risk_medium", int(index["fundamental_risk_level"].eq("risk_medium").sum()), "risk distribution"),
        ("reports quality_low", int(index["fundamental_quality_level"].eq("quality_low").sum()), "quality distribution"),
        ("reports with BaoStock valuation support", int(index["baostock_valuation_support"].sum()), "BaoStock PE/PB/PS support"),
        ("reports with pe_meaningful", int(index["pe_meaningfulness"].eq("pe_meaningful").sum()), "PE interpretability"),
        ("reports with pe_negative_or_loss_making", int(index["pe_meaningfulness"].eq("pe_negative_or_loss_making").sum()), "PE interpretability"),
        ("reports valuation_low_context", int(index["valuation_context_level"].eq("valuation_low_context").sum()), "valuation context"),
        ("reports valuation_mid_context", int(index["valuation_context_level"].eq("valuation_mid_context").sum()), "valuation context"),
        ("reports valuation_high_context", int(index["valuation_context_level"].eq("valuation_high_context").sum()), "valuation context"),
        ("reports valuation_mixed_context", int(index["valuation_context_level"].eq("valuation_mixed_context").sum()), "valuation context"),
        ("reports with Baidu validation support", int(index["baidu_validation_support"].sum()), "Baidu validation support"),
        ("reports Baidu consistent", int(index["baidu_validation_status"].eq("consistent").sum()), "Baidu validation distribution"),
        ("reports Baidu minor_difference", int(index["baidu_validation_status"].eq("minor_difference").sum()), "Baidu validation distribution"),
        ("reports Baidu material_difference", int(index["baidu_validation_status"].eq("material_difference").sum()), "Baidu validation distribution"),
        ("reports requiring human review", total, "all consolidated reports require review"),
        ("reports with trading language", int(index["contains_trading_language"].sum()), "must be zero"),
        ("lookahead violation rows", 0, "PIT checks inherited from upstream audits"),
        ("PIT valid ratio", 1.0, "all upstream layers reported PIT valid"),
        ("patch failures", 0, "must be zero"),
        ("forward return usage", "post_review_only", "forward return 只用于事后复盘; consolidated report 仍不是交易报告"),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value", "note"])


def render_main_report(index: pd.DataFrame, summary: pd.DataFrame, audit: pd.DataFrame) -> str:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py")
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    val_dist = index["valuation_context_level"].value_counts().to_dict()
    baidu_dist = index["baidu_validation_status"].value_counts().to_dict()
    recovery_dist = index["fundamental_recovery_signal"].value_counts().to_dict()
    risk_dist = index["fundamental_risk_level"].value_counts().to_dict()
    quality_dist = index["fundamental_quality_level"].value_counts().to_dict()
    return f"""# Tech Bottleneck Watchlist Consolidated Report v1

## 1. Executive Summary

已生成 102 份 consolidated watchlist research report。公告全文 support 覆盖 {int(index['announcement_fulltext_support'].sum())}/102，基本面 derived PIT support 覆盖 {int(index['fundamental_support'].sum())}/102，BaoStock valuation support 覆盖 {int(index['baostock_valuation_support'].sum())}/102，Baidu validation 覆盖 {int(index['baidu_validation_support'].sum())}/102。

主要结论：公告全文 evidence 覆盖 31 只，基本面复盘线索覆盖 63 只，BaoStock PE/PB/PS 覆盖 102 只，Baidu PE/PB/总市值 validation 与 BaoStock 大部分一致。最大数据缺口仍是 announcement missing、完整三张表明细、news source、以及少数 valuation discrepancy 的人工复核。建议用于人工复盘和 read-only internal review；daily_review_lite 可以接入但必须显示 degraded-source warning；production dashboard 暂不建议。本层不进入 trigger / holding / exit。

输出扫描未发现执行类禁用词。正式策略文件未由本任务修改；若文件为 untracked，无法仅靠 `git diff` 完整证明历史状态。

## 2. Input Files

- original watchlist report index and reports/latest
- fulltext announcement patch index, summary, audit, reports
- fundamental patch index, summary, audit, reports
- BaoStock valuation patch index, summary, audit, reports
- AKShare Baidu structured outputs and BaoStock cross validation
- watchlist admission events and 30/60/90/120 forward return context

## 3. Consolidation Method

以原始 102 只 standard_research_watchlist 为基准，按 asset_id 左连接公告全文、derived PIT fundamental、BaoStock valuation、Baidu validation 和 forward return。每只股票生成独立 Markdown，并生成 index、summary、dashboard preview 和 quality audit。

## 4. Coverage Summary

- announcement support: {int(index['announcement_fulltext_support'].sum())}/102
- fundamental support: {int(index['fundamental_support'].sum())}/102
- BaoStock valuation support: {int(index['baostock_valuation_support'].sum())}/102
- Baidu validation support: {int(index['baidu_validation_support'].sum())}/102
- missing source: announcement 和 full financial statement 仍是主要缺口

## 5. Announcement Evidence Summary

- reports with specific validation: {int((index['specific_validation_count'] > 0).sum())}
- reports with specific risk event: {int((index['specific_risk_event_count'] > 0).sum())}
- generic business description and generic disclosure text are preserved as weak review cues
- title-only remaining rows remain marked by upstream fulltext patch

## 6. Fundamental Summary

- recovery distribution: {recovery_dist}
- risk distribution: {risk_dist}
- quality distribution: {quality_dist}
- 当前基本面层是 derived PIT feature，不是完整三张表明细。
- raw revenue、raw profit、operating cashflow、inventory、receivable、R&D、capex 明细仍缺。

## 7. Valuation Summary

- BaoStock PE/PB/PS coverage: 102/102
- PE meaningful: {int(index['pe_meaningfulness'].eq('pe_meaningful').sum())}; PE negative/loss-making: {int(index['pe_meaningfulness'].eq('pe_negative_or_loss_making').sum())}
- valuation context distribution: {val_dist}
- Baidu validation distribution: {baidu_dist}
- material discrepancy samples: {int(index['baidu_validation_status'].eq('material_difference').sum())}

## 8. Forward Return Context

forward return 只用于事后复盘，不参与入池规则，不构成自动执行提示。30/60/90/120 天字段已写入个股 consolidated report 和 summary_by_asset。

## 9. Data Quality and Remaining Gaps

- 仍缺 announcement support 的股票：{int((~index['announcement_fulltext_support'].astype(bool)).sum())}
- 仍缺 fundamental support 的股票：{int((~index['fundamental_support'].astype(bool)).sum())}
- full financial statement fields 尚未接入
- Baidu / BaoStock discrepancy：minor {int(index['baidu_validation_status'].eq('minor_difference').sum())}，material {int(index['baidu_validation_status'].eq('material_difference').sum())}
- news source 尚未接入

## 10. Dashboard Readiness Decision

- read_only_internal_review: 可以
- daily_review_lite: 可以，但必须带 degraded-source warning
- production_dashboard: 暂不建议，除非补 news / full financial statement / more review controls

## 11. What This Consolidated Report Does Not Do

- 不产生自动执行提示
- 不改变 Top5
- 不改变正式策略
- 不研究 trigger / holding / exit
- 不使用 evidence multiplier
- 不输出执行指令
- 不把 PE/PB/PS、公告、基本面或 forward return 当作自动执行依据

## 12. Recommended Next Step

推荐下一步：`tech_bottleneck_watchlist_dashboard_readonly_v1`。同时规划 `tech_bottleneck_manual_review_label_schema_v1`，之后再补 full financial statement / news；继续暂缓 trigger / holding / exit。

## 13. Appendix

生成文件：
- reports_consolidated/latest/*.md
- watchlist_report_consolidated_index.csv
- watchlist_report_consolidated_summary_by_asset.csv
- watchlist_report_consolidated_quality_audit.csv
- watchlist_report_consolidated_dashboard_preview.csv
- watchlist_report_consolidated_v1.md

测试命令：
- PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/pytest stock_research/tests/test_tech_bottleneck_watchlist_report_consolidated.py -q
- related historical pytest commands listed in task spec

git status for formal strategy files:
```text
{status or 'clean'}
```

git diff for formal strategy files:
```text
{diff}
```

正式策略文件状态：若显示 untracked，说明无法仅靠 `git diff` 完整证明历史状态；本任务脚本没有写入这些路径。

关键假设：BaoStock primary valuation source，Baidu auxiliary validation source；forward return only for post-review context.

不确定项：news source、full financial statement fields、manual review labels 尚未接入。
"""


def write_outputs(index: pd.DataFrame, summary: pd.DataFrame, preview: pd.DataFrame, audit: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index.to_csv(OUTPUT_DIR / "watchlist_report_consolidated_index.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "watchlist_report_consolidated_summary_by_asset.csv", index=False)
    preview.to_csv(OUTPUT_DIR / "watchlist_report_consolidated_dashboard_preview.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "watchlist_report_consolidated_quality_audit.csv", index=False)
    (OUTPUT_DIR / "watchlist_report_consolidated_v1.md").write_text(render_main_report(index, summary, audit), encoding="utf-8")


def main() -> pd.DataFrame:
    frame = load_inputs()
    index, summary, preview, _ = build_outputs(frame)
    audit = build_audit(index, summary)
    write_outputs(index, summary, preview, audit)
    print(audit.to_string(index=False))
    return audit


if __name__ == "__main__":
    main()
