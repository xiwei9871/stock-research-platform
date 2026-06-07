from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


FEATURES = [
    "mid_trend_funnel_score",
    "score_rank",
    "trend_r2_20_score",
    "ret_20_score",
    "volatility_20_score",
    "max_drawdown_20_score",
    "industry_mainline_score_v1",
]


def run_bad_rebalance_state_attribution(
    *,
    attribution_detail_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    attribution_detail = pd.read_csv(attribution_detail_path, low_memory=False)
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    return build_bad_rebalance_state_attribution_from_frames(
        attribution_detail=attribution_detail,
        funnel_detail=funnel_detail,
        output_dir=output_dir,
    )


def build_bad_rebalance_state_attribution_from_frames(
    *,
    attribution_detail: pd.DataFrame,
    funnel_detail: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    detail = _build_detail(attribution_detail, funnel_detail)
    feature_summary = _feature_summary(detail)
    report = _render_report(detail, feature_summary)
    result: dict[str, Any] = {
        "detail": detail,
        "feature_summary": feature_summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "bad_rebalance_state_attribution_detail.csv",
            "feature_summary": output / "bad_rebalance_state_attribution_feature_summary.csv",
            "report": output / "bad_rebalance_state_attribution_report.md",
        }
        detail.to_csv(paths["detail"], index=False)
        feature_summary.to_csv(paths["feature_summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_detail(attribution_detail: pd.DataFrame, funnel_detail: pd.DataFrame) -> pd.DataFrame:
    attribution = _normalize_attribution(attribution_detail)
    funnel = _normalize_funnel(funnel_detail)
    rows = []
    for _, item in attribution.iterrows():
        trade_date = str(item["trade_date"])
        sold_asset = str(item.get("sold_asset_id") or "")
        bought_asset = str(item.get("bought_asset_id") or "")
        sold = _state_for_asset(funnel, trade_date, sold_asset, "sold")
        bought = _state_for_asset(funnel, trade_date, bought_asset, "bought")
        row = {**item.to_dict(), **sold, **bought}
        row.update(_flags(row))
        rows.append(row)
    detail = pd.DataFrame(rows)
    for column in ["sold_still_strong", "bought_overheated", "bought_weak_mainline"]:
        if column in detail.columns:
            detail[column] = detail[column].astype(object)
    return detail


def _normalize_attribution(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.date.astype(str)
    if "bad_rebalance_flag" in result.columns:
        result = result[result["bad_rebalance_flag"].astype(str).str.lower().eq("true")].copy()
    for column in [
        "replacement_alpha_10d",
        "replacement_alpha_20d",
        "sold_next_10d_return",
        "bought_next_10d_return",
    ]:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.dropna(subset=["trade_date"])


def _normalize_funnel(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.date.astype(str)
    result["asset_id"] = result["asset_id"].astype(str)
    for column in FEATURES:
        if column not in result.columns:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in ["mid_trend_layer", "industry_name", "market_regime", "mainline_status", "mainline_context"]:
        if column not in result.columns:
            result[column] = ""
    return result.dropna(subset=["trade_date", "asset_id"]).copy()


def _state_for_asset(funnel: pd.DataFrame, trade_date: str, asset_id: str, prefix: str) -> dict[str, Any]:
    columns = {
        f"{prefix}_{feature}": np.nan
        for feature in FEATURES
    }
    columns.update(
        {
            f"{prefix}_mid_trend_layer": "",
            f"{prefix}_industry_name": "",
            f"{prefix}_market_regime": "",
            f"{prefix}_mainline_status": "",
            f"{prefix}_mainline_context": "",
            f"{prefix}_state_found": False,
        }
    )
    if funnel.empty or not asset_id:
        return columns
    exact = funnel[funnel["trade_date"].eq(trade_date) & funnel["asset_id"].eq(asset_id)]
    if exact.empty:
        prior = funnel[funnel["trade_date"].le(trade_date) & funnel["asset_id"].eq(asset_id)].sort_values("trade_date")
        exact = prior.tail(1)
    if exact.empty:
        return columns
    row = exact.iloc[0]
    for feature in FEATURES:
        columns[f"{prefix}_{feature}"] = row.get(feature)
    for column in ["mid_trend_layer", "industry_name", "market_regime", "mainline_status", "mainline_context"]:
        columns[f"{prefix}_{column}"] = row.get(column)
    columns[f"{prefix}_state_found"] = True
    return columns


def _flags(row: dict[str, Any]) -> dict[str, bool]:
    sold_still_strong = (
        _num(row.get("sold_trend_r2_20_score")) >= 80
        and _num(row.get("sold_ret_20_score")) >= 70
        and _num(row.get("sold_industry_mainline_score_v1")) >= 0.45
    )
    bought_overheated = (
        _num(row.get("bought_ret_20_score")) >= 90
        and _num(row.get("bought_volatility_20_score")) >= 80
        and _num(row.get("bought_max_drawdown_20_score")) <= 40
    )
    bought_weak_mainline = _num(row.get("bought_industry_mainline_score_v1")) < 0.45
    return {
        "sold_still_strong": bool(sold_still_strong),
        "bought_overheated": bool(bought_overheated),
        "bought_weak_mainline": bool(bought_weak_mainline),
    }


def _num(value: Any) -> float:
    try:
        if pd.isna(value):
            return np.nan
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _feature_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    rows = []
    groups = {
        "all_bad_rebalances": detail,
        "sell_fly": detail[detail.get("bad_rebalance_reasons", "").astype(str).str.contains("sell_fly", na=False)],
        "bad_buy": detail[detail.get("bad_rebalance_reasons", "").astype(str).str.contains("bad_buy", na=False)],
        "negative_alpha_10d": detail[pd.to_numeric(detail.get("replacement_alpha_10d"), errors="coerce") <= -0.05],
    }
    for group_name, group in groups.items():
        row = {"group": group_name, "sample_count": int(len(group))}
        if group.empty:
            rows.append(row)
            continue
        for side in ["sold", "bought"]:
            for feature in FEATURES:
                row[f"avg_{side}_{feature}"] = _mean(group.get(f"{side}_{feature}"))
        row["sold_still_strong_rate"] = _mean(group.get("sold_still_strong"))
        row["bought_overheated_rate"] = _mean(group.get("bought_overheated"))
        row["bought_weak_mainline_rate"] = _mean(group.get("bought_weak_mainline"))
        rows.append(row)
    return pd.DataFrame(rows)


def _mean(series: Any) -> float:
    if series is None:
        return np.nan
    values = pd.Series(series)
    if values.dtype == object:
        values = values.map(lambda value: 1.0 if value is True else 0.0 if value is False else value)
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _render_report(detail: pd.DataFrame, feature_summary: pd.DataFrame) -> str:
    worst = detail.sort_values("replacement_alpha_10d").head(30) if not detail.empty else detail
    columns = [
        "trade_date",
        "sold_asset_id",
        "bought_asset_id",
        "replacement_alpha_10d",
        "bad_rebalance_reasons",
        "sold_still_strong",
        "bought_overheated",
        "bought_weak_mainline",
        "sold_trend_r2_20_score",
        "sold_ret_20_score",
        "bought_ret_20_score",
        "bought_volatility_20_score",
    ]
    columns = [col for col in columns if col in worst.columns]
    lines = [
        "# Bad Rebalance State Attribution",
        "",
        "## 1. Scope",
        "对坏调仓发生前的卖出票和买入票状态做归因；不改变策略规则。",
        "",
        "## 2. Feature Summary",
        feature_summary.to_markdown(index=False) if not feature_summary.empty else "No summary rows.",
        "",
        "## 3. Worst Rows",
        worst[columns].to_markdown(index=False) if not worst.empty else "No detail rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
