from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.mid_trend_shadow_backtest import _load_prices


CANDIDATE_VARIANT = "top5_adaptive_daily_check_max2_v1"
LOOKBACKS = [5, 10, 20, 40, 60]


def run_mid_trend_entry_timing_attribution(
    *,
    attribution_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    prices_path: str | Path | None = None,
    valuation_path: str | Path | None = None,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    attribution_detail = pd.read_csv(attribution_detail_path, low_memory=False)
    if prices_path:
        prices = pd.read_csv(prices_path, low_memory=False)
    else:
        lookback_start = (pd.Timestamp(start_date) - timedelta(days=140)).date().isoformat()
        prices = _load_prices(
            start_date=lookback_start,
            end_date=end_date,
            adjust_type=adjust_type,
            service=service,
        )
    valuation = pd.DataFrame()
    if valuation_path:
        path = Path(valuation_path)
        if path.exists():
            valuation = pd.read_csv(path, low_memory=False)
    return build_mid_trend_entry_timing_attribution_from_frames(
        attribution_detail=attribution_detail,
        prices=prices,
        valuation=valuation,
        output_dir=output_dir,
    )


def build_mid_trend_entry_timing_attribution_from_frames(
    *,
    attribution_detail: pd.DataFrame,
    prices: pd.DataFrame,
    valuation: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    attribution = _normalize_attribution(attribution_detail)
    close = _close_matrix(prices)
    pe = _pe_matrix(valuation if valuation is not None else pd.DataFrame(), close)
    detail = _build_detail(attribution, close, pe)
    contrast = _feature_contrast(detail)
    report = _render_report(detail, contrast, has_valuation=not pe.empty)
    result: dict[str, Any] = {
        "entry_timing_detail": detail,
        "entry_timing_contrast": contrast,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "entry_timing_detail": output / "mid_trend_entry_timing_detail.csv",
            "entry_timing_contrast": output / "mid_trend_entry_timing_contrast.csv",
            "report": output / "mid_trend_entry_timing_attribution_report.md",
        }
        detail.to_csv(paths["entry_timing_detail"], index=False)
        contrast.to_csv(paths["entry_timing_contrast"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize_attribution(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    result["variant_name"] = result.get("variant_name", CANDIDATE_VARIANT).astype(str)
    result = result[result["variant_name"].eq(CANDIDATE_VARIANT)].copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.date.astype(str)
    result["bought_asset_id"] = result.get("bought_asset_id", "").astype(str)
    result = result[result["bought_asset_id"].ne("")].copy()
    for column in ["bought_next_10d_return", "replacement_alpha_10d"]:
        result[column] = pd.to_numeric(result.get(column), errors="coerce")
    result["bad_buy_label"] = result.get("bad_rebalance_reasons", "").astype(str).str.contains("bad_buy", na=False)
    result["bad_buy_label"] = result["bad_buy_label"] | result["bought_next_10d_return"].le(-0.05)
    return result.dropna(subset=["trade_date", "bought_asset_id"])


def _close_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "asset_id", "close"])
    return frame.pivot_table(index="trade_date", columns="asset_id", values="close", aggfunc="last").sort_index()


def _pe_matrix(valuation: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    if valuation.empty:
        return pd.DataFrame()
    frame = valuation.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    pe_column = "pe_ttm" if "pe_ttm" in frame.columns else "pe" if "pe" in frame.columns else ""
    if pe_column:
        frame["pe_ttm"] = pd.to_numeric(frame[pe_column], errors="coerce")
    elif {"total_share", "np_parent_ttm"}.issubset(frame.columns) and not close.empty:
        shares = frame.pivot_table(
            index="trade_date",
            columns="asset_id",
            values="total_share",
            aggfunc="last",
        ).sort_index()
        earnings = frame.pivot_table(
            index="trade_date",
            columns="asset_id",
            values="np_parent_ttm",
            aggfunc="last",
        ).sort_index()
        shares = shares.apply(pd.to_numeric, errors="coerce")
        earnings = earnings.apply(pd.to_numeric, errors="coerce")
        aligned_close = close.reindex(index=earnings.index, columns=earnings.columns).ffill()
        market_cap_proxy = aligned_close * shares
        pe_proxy = market_cap_proxy / earnings.where(earnings > 0)
        pe_proxy = pe_proxy.replace([np.inf, -np.inf], np.nan)
        return pe_proxy.dropna(axis=0, how="all").sort_index()
    else:
        return pd.DataFrame()
    frame = frame.dropna(subset=["trade_date", "asset_id", "pe_ttm"])
    return frame.pivot_table(index="trade_date", columns="asset_id", values="pe_ttm", aggfunc="last").sort_index()


def _build_detail(attribution: pd.DataFrame, close: pd.DataFrame, pe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, item in attribution.iterrows():
        asset_id = str(item["bought_asset_id"])
        trade_date = str(item["trade_date"])
        row = item.to_dict()
        row.update(_price_timing_metrics(close, asset_id, trade_date))
        row.update(_pe_timing_metrics(pe, asset_id, trade_date))
        row["entry_timing_risk_label"] = _entry_timing_label(row)
        rows.append(row)
    result = pd.DataFrame(rows)
    for column in ["bad_buy_label", "entry_up_100pct_60d", "entry_near_60d_high"]:
        if column in result.columns:
            result[column] = result[column].map(lambda value: bool(value) if pd.notna(value) else False).astype(object)
    return result


def _price_timing_metrics(close: pd.DataFrame, asset_id: str, trade_date: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entry_close": np.nan,
        "entry_up_100pct_60d": False,
        "entry_near_60d_high": False,
        "entry_distance_from_60d_high": np.nan,
        "entry_position_in_60d_range": np.nan,
    }
    for lookback in LOOKBACKS:
        result[f"entry_ret_{lookback}d"] = np.nan
    for ma in [20, 60]:
        result[f"entry_close_vs_ma{ma}"] = np.nan
    if close.empty or asset_id not in close.columns or trade_date not in close.index:
        return result
    idx = close.index.get_loc(trade_date)
    current = close.iloc[idx][asset_id]
    if pd.isna(current) or float(current) == 0:
        return result
    current = float(current)
    result["entry_close"] = current
    series = close[asset_id].iloc[: idx + 1].dropna()
    for lookback in LOOKBACKS:
        if len(series) > lookback:
            base = float(series.iloc[-lookback - 1])
            result[f"entry_ret_{lookback}d"] = current / base - 1.0 if base else np.nan
        window = series.tail(min(lookback + 1, len(series)))
        if lookback == 60 and not window.empty:
            low = float(window.min())
            high = float(window.max())
            result["entry_up_100pct_60d"] = bool(low > 0 and current / low - 1.0 >= 1.0)
            result["entry_distance_from_60d_high"] = current / high - 1.0 if high else np.nan
            result["entry_near_60d_high"] = bool(high > 0 and current / high >= 0.95)
            result["entry_position_in_60d_range"] = (current - low) / (high - low) if high > low else np.nan
    for ma in [20, 60]:
        window = series.tail(ma)
        if len(window) >= max(5, min(ma, len(series))):
            avg = float(window.mean())
            result[f"entry_close_vs_ma{ma}"] = current / avg - 1.0 if avg else np.nan
    return result


def _pe_timing_metrics(pe: pd.DataFrame, asset_id: str, trade_date: str) -> dict[str, Any]:
    result: dict[str, Any] = {"entry_pe_ttm": np.nan}
    for lookback in [20, 40, 60]:
        result[f"entry_pe_ttm_change_{lookback}d"] = np.nan
    if pe.empty or asset_id not in pe.columns or trade_date not in pe.index:
        return result
    idx = pe.index.get_loc(trade_date)
    current = pe.iloc[idx][asset_id]
    if pd.isna(current) or float(current) == 0:
        return result
    current = float(current)
    result["entry_pe_ttm"] = current
    series = pe[asset_id].iloc[: idx + 1].dropna()
    for lookback in [20, 40, 60]:
        if len(series) > lookback:
            base = float(series.iloc[-lookback - 1])
            result[f"entry_pe_ttm_change_{lookback}d"] = current / base - 1.0 if base else np.nan
    return result


def _entry_timing_label(row: dict[str, Any]) -> str:
    price_extended = bool(row.get("entry_up_100pct_60d")) or _num(row.get("entry_ret_40d")) >= 1.0
    pe_expanded = max(
        _num(row.get("entry_pe_ttm_change_20d")),
        _num(row.get("entry_pe_ttm_change_40d")),
        _num(row.get("entry_pe_ttm_change_60d")),
    ) >= 1.0
    near_high = bool(row.get("entry_near_60d_high"))
    if price_extended and pe_expanded:
        return "extended_price_and_pe"
    if price_extended and near_high:
        return "extended_price_near_high"
    if price_extended:
        return "extended_price"
    if pe_expanded:
        return "pe_expansion"
    return "normal_timing"


def _feature_contrast(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    groups = {
        "adaptive_bad_buy": detail[detail["bad_buy_label"].astype(bool)],
        "adaptive_other_buys": detail[~detail["bad_buy_label"].astype(bool)],
    }
    rows = []
    for group_name, group in groups.items():
        row: dict[str, Any] = {"group": group_name, "sample_count": int(len(group))}
        if not group.empty:
            row["avg_bought_next_10d_return"] = _mean(group.get("bought_next_10d_return"))
            row["avg_replacement_alpha_10d"] = _mean(group.get("replacement_alpha_10d"))
            row["entry_up_100pct_60d_rate"] = _mean(group.get("entry_up_100pct_60d"))
            row["entry_near_60d_high_rate"] = _mean(group.get("entry_near_60d_high"))
            row["extended_price_or_pe_rate"] = float(
                group["entry_timing_risk_label"].astype(str).str.startswith(("extended", "pe_expansion")).mean()
            )
            for column in [
                "entry_ret_5d",
                "entry_ret_10d",
                "entry_ret_20d",
                "entry_ret_40d",
                "entry_ret_60d",
                "entry_close_vs_ma20",
                "entry_close_vs_ma60",
                "entry_pe_ttm",
                "entry_pe_ttm_change_20d",
                "entry_pe_ttm_change_40d",
                "entry_pe_ttm_change_60d",
            ]:
                row[f"avg_{column}"] = _mean(group.get(column))
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


def _num(value: Any) -> float:
    try:
        if pd.isna(value):
            return -np.inf
        return float(value)
    except (TypeError, ValueError):
        return -np.inf


def _render_report(detail: pd.DataFrame, contrast: pd.DataFrame, *, has_valuation: bool) -> str:
    worst = (
        detail[detail.get("bad_buy_label", pd.Series(dtype=bool)).astype(bool)]
        .sort_values("bought_next_10d_return")
        .head(30)
        if not detail.empty
        else detail
    )
    columns = [
        "trade_date",
        "bought_asset_id",
        "bought_next_10d_return",
        "replacement_alpha_10d",
        "entry_ret_20d",
        "entry_ret_40d",
        "entry_ret_60d",
        "entry_up_100pct_60d",
        "entry_near_60d_high",
        "entry_pe_ttm",
        "entry_pe_ttm_change_40d",
        "entry_timing_risk_label",
    ]
    columns = [column for column in columns if column in worst.columns]
    lines = [
        "# Mid Trend Entry Timing Attribution",
        "",
        "## 1. Scope",
        "只分析 top5_adaptive_daily_check_max2_v1 的买入时机，不新增交易规则，不生成交易建议。",
        "",
        "## 2. Valuation Coverage",
        "Valuation metrics included." if has_valuation else "No valuation input provided; PE timing metrics skipped.",
        "",
        "## 3. Bad-Buy vs Other-Buys",
        contrast.to_markdown(index=False) if not contrast.empty else "No contrast rows.",
        "",
        "## 4. Worst Entry Timing Rows",
        worst[columns].to_markdown(index=False) if not worst.empty else "No bad-buy rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
