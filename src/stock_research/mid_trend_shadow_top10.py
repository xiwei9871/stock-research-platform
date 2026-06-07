from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.mid_trend_shadow_stability import (
    _normalize,
    _positive_mainline_mask,
    _structured_top_n_by_day,
)


SHADOW_RULE_VERSION = "context_v2_structured_top10"


def run_mid_trend_shadow_top10(
    *,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    top_n: int = 10,
    trade_date: str | None = None,
) -> dict[str, Any]:
    detail = pd.read_csv(funnel_detail_path, low_memory=False)
    return build_mid_trend_shadow_top10_from_frame(
        detail,
        top_n=top_n,
        trade_date=trade_date,
        output_dir=output_dir,
    )


def build_mid_trend_shadow_top10_from_frame(
    detail: pd.DataFrame,
    *,
    top_n: int = 10,
    trade_date: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized = _normalize(detail)
    if trade_date:
        normalized = normalized[normalized["trade_date"].eq(pd.to_datetime(trade_date))].copy()
    top10 = _build_shadow_top10(normalized, top_n=top_n)
    daily_summary = _daily_summary(top10)
    industry_summary = _industry_summary(top10)
    report = _render_report(top10, daily_summary, industry_summary)

    result: dict[str, Any] = {
        "top10": top10,
        "daily_summary": daily_summary,
        "industry_summary": industry_summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "top10": output / "mid_trend_shadow_top10.csv",
            "daily_summary": output / "mid_trend_shadow_top10_daily_summary.csv",
            "industry_summary": output / "mid_trend_shadow_top10_industry_summary.csv",
            "report": output / "mid_trend_shadow_top10_report.md",
        }
        top10.to_csv(paths["top10"], index=False)
        daily_summary.to_csv(paths["daily_summary"], index=False)
        industry_summary.to_csv(paths["industry_summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_shadow_top10(detail: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    if detail.empty or top_n <= 0:
        return _empty_top10()
    source = detail[
        detail["market_regime"].astype(str).isin({"mainline", "rotation", "broad_market"})
        & (detail["volatility_20_score"] >= 15)
        & (detail["trend_r2_20_score"] >= 80)
        & _hard_eligible_mid_trend_mask(detail)
        & _positive_mainline_mask(detail)
    ].copy()
    selected = _structured_top_n_by_day(source, top_n)
    if selected.empty:
        return _empty_top10()
    selected["_shadow_selection_order"] = selected.groupby("trade_date").cumcount()
    selected = selected.sort_values(["trade_date", "_shadow_selection_order"], ascending=[True, True])
    selected["shadow_top10_rank"] = selected.groupby("trade_date").cumcount() + 1
    selected = selected.drop(columns=["_shadow_selection_order"])
    selected["ts_code"] = selected.apply(
        lambda row: row.get("ts_code") if _has_text(row.get("ts_code")) else _ts_code_from_asset_id(row.get("asset_id")),
        axis=1,
    )
    selected["shadow_rule_version"] = SHADOW_RULE_VERSION
    selected["shadow_watchlist_id"] = selected["trade_date"].dt.strftime("%Y-%m-%d") + "_mid_trend_shadow_top10"
    selected["shadow_note"] = selected.apply(_shadow_note, axis=1)
    preferred_columns = [
        "shadow_watchlist_id",
        "trade_date",
        "shadow_top10_rank",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "market_regime",
        "mainline_status",
        "mainline_context",
        "industry_mainline_score_v1",
        "mid_trend_layer",
        "structure_slot",
        "mid_trend_funnel_score",
        "score_rank",
        "volatility_20_score",
        "trend_r2_20_score",
        "ret_20_score",
        "max_drawdown_20_score",
        "shadow_rule_version",
        "shadow_note",
    ]
    return _ensure_columns(selected, preferred_columns)


def _hard_eligible_mid_trend_mask(detail: pd.DataFrame) -> pd.Series:
    mask = pd.Series(True, index=detail.index)
    if "mid_trend_layer" in detail.columns:
        mask &= ~detail["mid_trend_layer"].astype(str).eq("risk_exclusion_watch")
    if "stock_name" in detail.columns:
        mask &= ~detail["stock_name"].astype(str).str.contains(r"^\*?ST(?![A-Za-z])", case=False, regex=True, na=False)
    if "is_st" in detail.columns:
        st_values = detail["is_st"]
        if st_values.dtype == bool:
            mask &= ~st_values.fillna(False)
        else:
            mask &= ~st_values.astype(str).str.lower().isin({"true", "1", "yes", "y", "st"})
    return mask


def _daily_summary(top10: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "row_count",
        "unique_industry_count",
        "preferred_core_count",
        "controlled_high_odds_count",
        "weak_stability_industry_count",
        "market_regime",
    ]
    if top10.empty:
        return pd.DataFrame(columns=columns)
    weak = {"汽车制造业", "互联网和相关服务", "软件和信息技术服务业", "化学原料和化学制品制造业"}
    rows = []
    for trade_date, group in top10.groupby("trade_date", sort=True):
        rows.append(
            {
                "trade_date": trade_date,
                "row_count": int(len(group)),
                "unique_industry_count": int(group["industry_name"].nunique()),
                "preferred_core_count": int(group["structure_slot"].eq("preferred_mainline_core").sum()),
                "controlled_high_odds_count": int(group["structure_slot"].eq("controlled_high_odds").sum()),
                "weak_stability_industry_count": int(group["industry_name"].isin(weak).sum()),
                "market_regime": ",".join(sorted(set(group["market_regime"].dropna().astype(str)))),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _industry_summary(top10: pd.DataFrame) -> pd.DataFrame:
    columns = ["industry_name", "sample_count", "trade_date_count", "avg_rank", "slot_distribution"]
    if top10.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for industry, group in top10.groupby("industry_name", sort=True):
        rows.append(
            {
                "industry_name": industry,
                "sample_count": int(len(group)),
                "trade_date_count": int(group["trade_date"].nunique()),
                "avg_rank": float(pd.to_numeric(group["shadow_top10_rank"], errors="coerce").mean()),
                "slot_distribution": ";".join(
                    f"{slot}:{count}" for slot, count in group["structure_slot"].value_counts().sort_index().items()
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(["sample_count", "industry_name"], ascending=[False, True])


def _render_report(top10: pd.DataFrame, daily_summary: pd.DataFrame, industry_summary: pd.DataFrame) -> str:
    lines = [
        "# Mid Trend Shadow Top10",
        "",
        "## 1. Scope",
        "结构化中线 shadow Top10，仅用于观察和复盘，不生成交易建议，不替换正式 Top10。",
        "",
        "## 2. Rule",
        "- base: volatility_20_score >= 15 and trend_r2_20_score >= 80",
        "- context: mainline / rotation / broad_market, with positive mainline context",
        "- structure: preferred core, stable fill, controlled high-odds, rank fill",
        "",
        "## 3. Daily Summary",
        daily_summary.tail(20).to_markdown(index=False) if not daily_summary.empty else "No daily rows.",
        "",
        "## 4. Industry Summary",
        industry_summary.head(30).to_markdown(index=False) if not industry_summary.empty else "No industry rows.",
        "",
        "## 5. Guardrail",
        "本产物是 shadow watchlist；不包含买卖点、仓位或实盘执行建议。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _shadow_note(row: pd.Series) -> str:
    return (
        "shadow observation only; "
        f"slot={row.get('structure_slot')}; "
        f"regime={row.get('market_regime')}; "
        f"layer={row.get('mid_trend_layer')}"
    )


def _ts_code_from_asset_id(asset_id: Any) -> str:
    parts = str(asset_id or "").split(":")
    if len(parts) == 3 and parts[0] == "CN" and parts[1] in {"SH", "SZ", "BJ"}:
        return f"{parts[2]}.{parts[1]}"
    return ""


def _has_text(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"nan", "none", "nat"}


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = np.nan
    return result[columns].reset_index(drop=True)


def _empty_top10() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "shadow_watchlist_id",
            "trade_date",
            "shadow_top10_rank",
            "asset_id",
            "ts_code",
            "stock_name",
            "industry_name",
            "market_regime",
            "mid_trend_layer",
            "structure_slot",
            "shadow_rule_version",
            "shadow_note",
        ]
    )
