from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.strong_winner_miss_analysis import enrich_bars_with_asset_identity
from stock_research.technical_method_validation import load_validation_bars


WINNER_TYPES = [
    "double_60d",
    "burst_30d",
    "burst_20d",
    "stable_trend_60d",
    "pullback_new_high",
]
V2_2_CANDIDATES = [
    "v2_final_baseline",
    "v2_1_quality_no_highvol_extremeamount",
    "v2_2_growth_trend_core",
    "v2_2_cyclical_trend_core",
    "v2_2_trend_continuation_boost",
    "v2_2_high_elasticity_shadow",
    "existing_trend_continuation_candidate",
]
TAXONOMY_COLUMNS = [
    "winner_id",
    "winner_type",
    "asset_id",
    "ts_code",
    "stock_name",
    "window_start",
    "window_end",
    "window_days",
    "max_return",
    "end_return",
    "max_drawdown",
    "rise_smoothness",
    "volatility",
    "industry_name",
    "market_regime",
    "mainline_context",
    "winner_definition",
]


def run_strong_winner_taxonomy_v2(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    adjust_type: str = "qfq",
    v2_detail_path: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    bars = load_validation_bars(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    bars = enrich_bars_with_asset_identity(bars, service=service)
    v2_detail = (
        pd.read_csv(v2_detail_path, low_memory=False)
        if v2_detail_path and Path(v2_detail_path).exists()
        else pd.DataFrame()
    )
    return build_strong_winner_taxonomy_v2_from_frames(
        bars=bars,
        v2_detail=v2_detail,
        output_dir=output_dir,
        start_date=start_date,
        end_date=end_date,
    )


def build_strong_winner_taxonomy_v2_from_frames(
    *,
    bars: pd.DataFrame,
    v2_detail: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    taxonomy = scan_strong_winner_taxonomy_v2(bars)
    context = _prepare_v2_context(v2_detail if v2_detail is not None else pd.DataFrame(), warnings)
    taxonomy = _attach_context(taxonomy, context)
    summary = _taxonomy_summary(taxonomy)
    v2_2_capture = _v2_2_capture(taxonomy, context)
    report = _render_report(
        taxonomy=taxonomy,
        summary=summary,
        v2_2_capture=v2_2_capture,
        warnings=warnings,
        start_date=start_date,
        end_date=end_date,
    )

    result: dict[str, Any] = {
        "taxonomy": taxonomy,
        "summary": summary,
        "v2_2_capture": v2_2_capture,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "taxonomy": output / "strong_winner_taxonomy_v2_2025_to_now.csv",
            "summary": output / "strong_winner_taxonomy_v2_summary.csv",
            "v2_2_capture": output / "strong_winner_taxonomy_v2_v2_2_capture.csv",
            "report": output / "strong_winner_taxonomy_v2_report.md",
        }
        taxonomy.to_csv(paths["taxonomy"], index=False)
        summary.to_csv(paths["summary"], index=False)
        v2_2_capture.to_csv(paths["v2_2_capture"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def scan_strong_winner_taxonomy_v2(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=TAXONOMY_COLUMNS)
    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for asset_id, group in frame.sort_values(["asset_id", "trade_date"]).groupby("asset_id", sort=False):
        asset = group.reset_index(drop=True)
        rows.extend(_scan_asset_taxonomy(str(asset_id), asset))
    taxonomy = pd.DataFrame(rows)
    if taxonomy.empty:
        return pd.DataFrame(columns=TAXONOMY_COLUMNS)
    taxonomy = taxonomy.sort_values(["winner_type", "window_start", "asset_id"]).reset_index(drop=True)
    taxonomy.insert(0, "winner_id", [f"SWTAX-{index + 1:05d}" for index in range(len(taxonomy))])
    return taxonomy.reindex(columns=TAXONOMY_COLUMNS)


def _scan_asset_taxonomy(asset_id: str, asset: pd.DataFrame) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    specs = [
        ("double_60d", 60, 1.0, "max_return>=100%_within_60d"),
        ("burst_30d", 30, 0.60, "max_return>=60%_within_30d"),
        ("burst_20d", 20, 0.40, "max_return>=40%_within_20d"),
        ("stable_trend_60d", 60, 0.50, "max_return>=50%_within_60d_and_drawdown<=25%"),
    ]
    for winner_type, window_days, threshold, definition in specs:
        best = _first_threshold_window(asset_id, asset, winner_type, window_days, threshold, definition)
        if best is None:
            continue
        if winner_type == "stable_trend_60d" and best["max_drawdown"] < -0.25:
            continue
        results.append(best)
    pullback = _first_pullback_new_high(asset_id, asset)
    if pullback is not None:
        results.append(pullback)
    return results


def _first_threshold_window(
    asset_id: str,
    asset: pd.DataFrame,
    winner_type: str,
    window_days: int,
    threshold: float,
    definition: str,
) -> dict[str, Any] | None:
    lows = pd.to_numeric(asset["low"], errors="coerce").to_numpy(dtype=float)
    highs = pd.to_numeric(asset["high"], errors="coerce").to_numpy(dtype=float)
    closes = pd.to_numeric(asset["close"], errors="coerce").to_numpy(dtype=float)
    dates = asset["trade_date"].to_list()
    for start in range(len(asset)):
        low = lows[start]
        if not np.isfinite(low) or low <= 0:
            continue
        end = min(len(asset), start + window_days + 1)
        segment_highs = highs[start:end]
        if segment_highs.size == 0 or np.all(np.isnan(segment_highs)):
            continue
        peak_offset = int(np.nanargmax(segment_highs))
        peak_index = start + peak_offset
        max_return = highs[peak_index] / low - 1.0
        if max_return < threshold:
            continue
        return _window_row(
            asset_id=asset_id,
            asset=asset,
            winner_type=winner_type,
            start=start,
            end=peak_index,
            window_days=window_days,
            winner_definition=definition,
        )
    return None


def _first_pullback_new_high(asset_id: str, asset: pd.DataFrame) -> dict[str, Any] | None:
    highs = pd.to_numeric(asset["high"], errors="coerce").to_numpy(dtype=float)
    lows = pd.to_numeric(asset["low"], errors="coerce").to_numpy(dtype=float)
    if len(asset) < 20:
        return None
    for start in range(len(asset)):
        end = min(len(asset), start + 61)
        if end - start < 20:
            continue
        segment_highs = highs[start:end]
        segment_lows = lows[start:end]
        if np.all(np.isnan(segment_highs)) or np.all(np.isnan(segment_lows)):
            continue
        base_low = segment_lows[0]
        if not np.isfinite(base_low) or base_low <= 0:
            continue
        peak_hits = np.flatnonzero(segment_highs / base_low - 1.0 >= 0.25)
        if peak_hits.size == 0:
            continue
        peak_offset = int(peak_hits[0])
        pullback_peak = float(np.nanmax(segment_highs[: peak_offset + 1]))
        if not np.isfinite(pullback_peak) or pullback_peak <= 0:
            continue
        post_peak_lows = segment_lows[peak_offset + 1 :]
        if post_peak_lows.size == 0:
            continue
        drawdowns = post_peak_lows / pullback_peak - 1.0
        trough_hits = np.flatnonzero((drawdowns <= -0.10) & (drawdowns >= -0.25))
        if trough_hits.size == 0:
            continue
        trough_offset = peak_offset + 1 + int(trough_hits[0])
        new_high_hits = np.flatnonzero(segment_highs[trough_offset + 1 :] > pullback_peak * 1.01)
        if new_high_hits.size == 0:
            continue
        new_high_offset = trough_offset + 1 + int(new_high_hits[0])
        return _window_row(
            asset_id=asset_id,
            asset=asset,
            winner_type="pullback_new_high",
            start=start,
            end=start + new_high_offset,
            window_days=60,
            winner_definition="gain>=25%_then_pullback_10_25%_then_new_high_within_60d",
        )
    return None


def _window_row(
    *,
    asset_id: str,
    asset: pd.DataFrame,
    winner_type: str,
    start: int,
    end: int,
    window_days: int,
    winner_definition: str,
) -> dict[str, Any]:
    segment = asset.iloc[start : end + 1]
    closes = pd.to_numeric(segment["close"], errors="coerce")
    highs = pd.to_numeric(segment["high"], errors="coerce")
    lows = pd.to_numeric(segment["low"], errors="coerce")
    start_low = float(lows.iloc[0])
    start_close = float(closes.iloc[0])
    peak_high = float(highs.max())
    end_close = float(closes.iloc[-1])
    max_return = peak_high / start_low - 1.0 if start_low > 0 else np.nan
    end_return = end_close / start_close - 1.0 if start_close > 0 else np.nan
    max_drawdown = _max_drawdown(closes)
    returns = closes.pct_change().dropna()
    volatility = float(returns.std()) if not returns.empty else 0.0
    rise_smoothness = _rise_smoothness(closes)
    return {
        "winner_type": winner_type,
        "asset_id": asset_id,
        "ts_code": _first_nonempty(asset.get("ts_code")),
        "stock_name": _first_nonempty(asset.get("stock_name")),
        "window_start": _date_string(segment["trade_date"].iloc[0]),
        "window_end": _date_string(segment["trade_date"].iloc[-1]),
        "window_days": int(window_days),
        "max_return": max_return,
        "end_return": end_return,
        "max_drawdown": max_drawdown,
        "rise_smoothness": rise_smoothness,
        "volatility": volatility,
        "industry_name": "",
        "market_regime": "",
        "mainline_context": "",
        "winner_definition": winner_definition,
    }


def _prepare_v2_context(v2_detail: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    columns = [
        "asset_id",
        "trade_date",
        "industry_name",
        "market_regime",
        "mainline_context",
        *V2_2_CANDIDATES,
    ]
    if v2_detail.empty:
        warnings.append("missing_v2_detail")
        return pd.DataFrame(columns=columns)
    context = v2_detail.copy()
    for column in columns:
        if column not in context.columns:
            context[column] = False if column in V2_2_CANDIDATES else ""
            warnings.append(f"missing_{column}")
    context["trade_date"] = pd.to_datetime(context["trade_date"], errors="coerce")
    context["asset_id"] = context["asset_id"].astype(str)
    for column in V2_2_CANDIDATES:
        context[column] = context[column].map(_bool)
    return context[columns]


def _attach_context(taxonomy: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    if taxonomy.empty or context.empty:
        return taxonomy.copy()
    out = taxonomy.copy()
    out["window_start_dt"] = pd.to_datetime(out["window_start"], errors="coerce")
    out["window_end_dt"] = pd.to_datetime(out["window_end"], errors="coerce")
    empty_context = context.iloc[0:0]
    context_by_asset = {asset_id: group.sort_values("trade_date") for asset_id, group in context.groupby("asset_id")}
    rows = []
    for _, winner in out.iterrows():
        asset_context = context_by_asset.get(str(winner["asset_id"]), empty_context)
        candidates = asset_context[
            (asset_context["trade_date"] >= winner["window_start_dt"])
            & (asset_context["trade_date"] <= winner["window_end_dt"])
        ]
        row = winner.to_dict()
        if not candidates.empty:
            first = candidates.iloc[0]
            for column in ["industry_name", "market_regime", "mainline_context"]:
                row[column] = first.get(column, "")
        rows.append(row)
    enriched = pd.DataFrame(rows).drop(columns=["window_start_dt", "window_end_dt"], errors="ignore")
    return enriched.reindex(columns=TAXONOMY_COLUMNS)


def _taxonomy_summary(taxonomy: pd.DataFrame) -> pd.DataFrame:
    if taxonomy.empty:
        return pd.DataFrame(columns=["winner_type", "winner_count", "avg_max_return", "avg_max_drawdown", "avg_volatility"])
    grouped = taxonomy.groupby("winner_type", dropna=False)
    return grouped.agg(
        winner_count=("winner_id", "count"),
        avg_max_return=("max_return", "mean"),
        avg_end_return=("end_return", "mean"),
        avg_max_drawdown=("max_drawdown", "mean"),
        avg_rise_smoothness=("rise_smoothness", "mean"),
        avg_volatility=("volatility", "mean"),
    ).reset_index()


def _v2_2_capture(taxonomy: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if taxonomy.empty:
        return pd.DataFrame(columns=["winner_type", "candidate_set", "winner_count", "captured_count", "capture_rate"])
    empty_context = context.iloc[0:0]
    context_by_asset = {asset_id: group.sort_values("trade_date") for asset_id, group in context.groupby("asset_id")}
    winner_flags = _winner_capture_flags(taxonomy, context_by_asset, empty_context)
    for winner_type, winners in taxonomy.groupby("winner_type", dropna=False):
        flags = winner_flags.loc[winners.index] if not winner_flags.empty else pd.DataFrame(index=winners.index)
        winner_count = len(winners)
        for candidate in V2_2_CANDIDATES:
            captured = int(flags[candidate].sum()) if candidate in flags.columns else 0
            rows.append(
                {
                    "winner_type": winner_type,
                    "candidate_set": candidate,
                    "winner_count": winner_count,
                    "captured_count": captured,
                    "capture_rate": captured / winner_count if winner_count else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _winner_capture_flags(
    taxonomy: pd.DataFrame,
    context_by_asset: dict[str, pd.DataFrame],
    empty_context: pd.DataFrame,
) -> pd.DataFrame:
    flags = pd.DataFrame(False, index=taxonomy.index, columns=V2_2_CANDIDATES)
    if taxonomy.empty:
        return flags
    for index, winner in taxonomy.iterrows():
        asset_context = context_by_asset.get(str(winner["asset_id"]), empty_context)
        if asset_context.empty:
            continue
        start = pd.to_datetime(winner["window_start"], errors="coerce")
        end = pd.to_datetime(winner["window_end"], errors="coerce")
        rows = asset_context[(asset_context["trade_date"] >= start) & (asset_context["trade_date"] <= end)]
        if rows.empty:
            continue
        for candidate in V2_2_CANDIDATES:
            flags.at[index, candidate] = bool(rows[candidate].any()) if candidate in rows.columns else False
    return flags


def _render_report(
    *,
    taxonomy: pd.DataFrame,
    summary: pd.DataFrame,
    v2_2_capture: pd.DataFrame,
    warnings: list[str],
    start_date: str | None,
    end_date: str | None,
) -> str:
    lines = [
        "# Strong Winner Taxonomy v2",
        "",
        "## 1. Scope",
        "将强票从单一 60 日翻倍扩展为多标签：60日翻倍、30日高弹性、20日爆发、稳定趋势、回撤后新高；仅用于诊断，不生成交易建议。",
        "",
        "## 2. Data Range",
        f"- start_date: {start_date or 'unknown'}",
        f"- end_date: {end_date or 'unknown'}",
        f"- taxonomy_rows: {len(taxonomy)}",
        "",
        "## 3. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 4. Taxonomy Summary",
        summary.to_markdown(index=False),
        "",
        "## 5. v2.2 Capture by Winner Type",
        v2_2_capture.to_markdown(index=False),
    ]
    return "\n".join(lines) + "\n"


def _max_drawdown(closes: pd.Series) -> float:
    values = pd.to_numeric(closes, errors="coerce").dropna()
    if values.empty:
        return np.nan
    running_high = values.cummax()
    drawdown = values / running_high - 1.0
    return float(drawdown.min())


def _rise_smoothness(closes: pd.Series) -> float:
    values = pd.to_numeric(closes, errors="coerce").dropna()
    if len(values) < 2:
        return 0.0
    positive_days = (values.diff().dropna() > 0).mean()
    return float(positive_days)


def _first_nonempty(series: Any) -> str:
    try:
        for value in series:
            if pd.notna(value) and str(value) != "":
                return str(value)
    except TypeError:
        pass
    return ""


def _date_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "f", "no", "n", "off", "none", "null", "nan"}:
            return False
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
    return bool(value)
