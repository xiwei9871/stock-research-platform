from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.intraday_risk_control_v2 import (
    V2_FEATURES,
    build_intraday_risk_signals_v2,
    build_midtrend_risk_states,
    resolve_intraday_risk_control_v2_preset,
)
from stock_research.mid_trend_shadow_backtest import _load_prices
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.mid_trend_shadow_weekly_control import (
    _attach_st_status_flags,
    _hard_exclusions_by_date,
    _simulate_variant,
)
from stock_research.mid_trend_shadow_weekly_optimization import _prices_for_shadow


DEFAULT_BASE_VARIANT = "top5_weekly_max2_selective_trend_holding_protection_v1"
FILTERED_VARIANT_SUFFIX = "intraday_v2_2_midband"
HIGH_ONLY_FILTERED_VARIANT_SUFFIX = "intraday_v2_2_high_only_new_entry"


def apply_intraday_risk_filter_to_shadow_candidates(
    candidates: pd.DataFrame,
    states: pd.DataFrame,
    *,
    watch_rank_penalty: float = 3.0,
    high_rank_penalty: float = 8.0,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()

    frame = candidates.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["shadow_top10_rank"] = pd.to_numeric(frame["shadow_top10_rank"], errors="coerce")

    state_cols = ["trade_date", "asset_id", "midtrend_risk_level"]
    if states.empty:
        normalized_states = pd.DataFrame(columns=state_cols)
    else:
        normalized_states = states[state_cols].copy()
        normalized_states["trade_date"] = pd.to_datetime(
            normalized_states["trade_date"],
            errors="coerce",
        ).dt.date.astype(str)
        normalized_states["asset_id"] = normalized_states["asset_id"].astype(str)
        normalized_states = normalized_states.drop_duplicates(
            ["trade_date", "asset_id"],
            keep="last",
        )

    merged = frame.merge(normalized_states, on=["trade_date", "asset_id"], how="left")
    merged["midtrend_risk_level"] = merged["midtrend_risk_level"].fillna("none")
    merged["intraday_risk_rank_penalty"] = merged["midtrend_risk_level"].map(
        {
            "none": 0.0,
            "watch": float(watch_rank_penalty),
            "high": float(high_rank_penalty),
        }
    ).fillna(0.0)
    merged["intraday_risk_adjusted_rank"] = (
        merged["shadow_top10_rank"] + merged["intraday_risk_rank_penalty"]
    )
    merged = merged.sort_values(
        ["trade_date", "intraday_risk_adjusted_rank", "shadow_top10_rank", "asset_id"],
        ascending=[True, True, True, True],
    ).copy()
    merged["shadow_top10_rank_original"] = merged["shadow_top10_rank"]
    merged["shadow_top10_rank"] = merged.groupby("trade_date").cumcount() + 1
    merged["shadow_rule_version"] = (
        merged.get("shadow_rule_version", pd.Series("", index=merged.index))
        .fillna("")
        .astype(str)
        + "+intraday_risk_v2_2_midband"
    )
    return merged.reset_index(drop=True)


def apply_intraday_risk_high_only_new_entry_filter(
    candidates: pd.DataFrame,
    states: pd.DataFrame,
    *,
    top_n: int,
    high_rank_penalty: float = 8.0,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()

    frame = candidates.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["shadow_top10_rank"] = pd.to_numeric(frame["shadow_top10_rank"], errors="coerce")

    state_cols = ["trade_date", "asset_id", "midtrend_risk_level"]
    if states.empty:
        normalized_states = pd.DataFrame(columns=state_cols)
    else:
        normalized_states = states[state_cols].copy()
        normalized_states["trade_date"] = pd.to_datetime(
            normalized_states["trade_date"],
            errors="coerce",
        ).dt.date.astype(str)
        normalized_states["asset_id"] = normalized_states["asset_id"].astype(str)
        normalized_states = normalized_states.drop_duplicates(
            ["trade_date", "asset_id"],
            keep="last",
        )

    merged = frame.merge(normalized_states, on=["trade_date", "asset_id"], how="left")
    merged["midtrend_risk_level"] = merged["midtrend_risk_level"].fillna("none")
    is_top_candidate = merged["shadow_top10_rank"].le(int(top_n))
    is_high = merged["midtrend_risk_level"].eq("high")
    merged["intraday_risk_rank_penalty"] = 0.0
    merged.loc[is_top_candidate & is_high, "intraday_risk_rank_penalty"] = float(high_rank_penalty)
    merged["intraday_risk_adjusted_rank"] = (
        merged["shadow_top10_rank"] + merged["intraday_risk_rank_penalty"]
    )
    merged = merged.sort_values(
        ["trade_date", "intraday_risk_adjusted_rank", "shadow_top10_rank", "asset_id"],
        ascending=[True, True, True, True],
    ).copy()
    merged["shadow_top10_rank_original"] = merged["shadow_top10_rank"]
    merged["shadow_top10_rank"] = merged.groupby("trade_date").cumcount() + 1
    merged["shadow_rule_version"] = (
        merged.get("shadow_rule_version", pd.Series("", index=merged.index))
        .fillna("")
        .astype(str)
        + "+intraday_risk_v2_2_high_only_new_entry"
    )
    return merged.reset_index(drop=True)


def run_mid_trend_intraday_risk_overlay_backtest(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    base_variant_name: str = DEFAULT_BASE_VARIANT,
    risk_preset: str = "v2_2_midband",
    top_n: int = 5,
    buffer_rank: int = 10,
    max_weekly_replacements: int = 2,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
    intraday_freq: str = "5min",
    intraday_adjust_type: str = "raw",
    filter_mode: str = "high_only_new_entry",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    funnel_detail = _attach_st_status_flags(
        funnel_detail,
        start_date=start_date,
        end_date=end_date,
        service=service,
    )
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    features = _load_intraday_features(
        start_date=start_date,
        end_date=end_date,
        freq=intraday_freq,
        adjust_type=intraday_adjust_type,
        service=service,
    )
    return build_mid_trend_intraday_risk_overlay_backtest_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        intraday_features=features,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        base_variant_name=base_variant_name,
        risk_preset=risk_preset,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
        filter_mode=filter_mode,
    )


def build_mid_trend_intraday_risk_overlay_backtest_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    intraday_features: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    base_variant_name: str = DEFAULT_BASE_VARIANT,
    risk_preset: str = "v2_2_midband",
    top_n: int = 5,
    buffer_rank: int = 10,
    max_weekly_replacements: int = 2,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
    filter_mode: str = "high_only_new_entry",
) -> dict[str, Any]:
    preset = resolve_intraday_risk_control_v2_preset(risk_preset)
    hard_exclusions = _hard_exclusions_by_date(funnel_detail)
    signals = build_intraday_risk_signals_v2(
        intraday_features,
        lookback=20,
        zscore_threshold=1.5,
        tail_confirmation_zscore_threshold=preset.get("tail_confirmation_zscore_threshold"),
        reversal_zscore_threshold=preset.get("reversal_zscore_threshold"),
        reversal_afternoon_mode=str(preset.get("reversal_afternoon_mode", "zscore")),
    )
    states = build_midtrend_risk_states(
        signals,
        high_escalation_mode=str(preset.get("high_escalation_mode", "severe_only")),
    )

    primary = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
    buffer = build_mid_trend_shadow_top10_from_frame(
        funnel_detail,
        top_n=max(top_n, buffer_rank),
    )["top10"]
    if filter_mode == "rank_penalty":
        filtered_buffer = apply_intraday_risk_filter_to_shadow_candidates(buffer, states)
        filtered_variant_suffix = FILTERED_VARIANT_SUFFIX
    elif filter_mode == "high_only_new_entry":
        filtered_buffer = apply_intraday_risk_high_only_new_entry_filter(
            buffer,
            states,
            top_n=top_n,
        )
        filtered_variant_suffix = HIGH_ONLY_FILTERED_VARIANT_SUFFIX
    else:
        raise ValueError(f"Unsupported intraday risk overlay filter_mode: {filter_mode}")
    filtered_primary = filtered_buffer[
        pd.to_numeric(filtered_buffer["shadow_top10_rank"], errors="coerce").le(top_n)
    ].copy()

    scoped_prices = _prices_for_shadow(
        prices,
        pd.concat([primary, buffer, filtered_primary, filtered_buffer], ignore_index=True),
    )

    baseline = _simulate_variant(
        primary,
        buffer,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        variant_name=base_variant_name,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=transaction_cost_bps,
        hard_exclusions=hard_exclusions,
    )
    filtered = _simulate_variant(
        filtered_primary,
        filtered_buffer,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        variant_name=base_variant_name,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=transaction_cost_bps,
        hard_exclusions=hard_exclusions,
    )
    filtered_variant_name = f"{base_variant_name}_{filtered_variant_suffix}"
    _rename_result_variant(filtered, filtered_variant_name)

    summary = pd.DataFrame([baseline["summary"], filtered["summary"]])
    summary = _append_deltas(summary, baseline_variant_name=base_variant_name)
    equity_curve = pd.concat([baseline["equity_curve"], filtered["equity_curve"]], ignore_index=True)
    positions = pd.concat([baseline["positions"], filtered["positions"]], ignore_index=True)
    trades = pd.concat([baseline["trades"], filtered["trades"]], ignore_index=True)
    risk_distribution = _risk_distribution(states)
    report = _render_report(
        summary,
        risk_distribution=risk_distribution,
        start_date=start_date,
        end_date=end_date,
        risk_preset=risk_preset,
        filter_mode=filter_mode,
    )

    result: dict[str, Any] = {
        "summary": summary,
        "equity_curve": equity_curve,
        "positions": positions,
        "trades": trades,
        "signals": signals,
        "states": states,
        "filtered_candidates": filtered_buffer,
        "risk_distribution": risk_distribution,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "mid_trend_intraday_risk_overlay_summary.csv",
            "equity_curve": output / "mid_trend_intraday_risk_overlay_equity.csv",
            "positions": output / "mid_trend_intraday_risk_overlay_positions.csv",
            "trades": output / "mid_trend_intraday_risk_overlay_trades.csv",
            "signals": output / "mid_trend_intraday_risk_overlay_signals.csv",
            "states": output / "mid_trend_intraday_risk_overlay_states.csv",
            "filtered_candidates": output / "mid_trend_intraday_risk_overlay_filtered_candidates.csv",
            "risk_distribution": output / "mid_trend_intraday_risk_overlay_risk_distribution.csv",
            "report": output / "mid_trend_intraday_risk_overlay_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        equity_curve.to_csv(paths["equity_curve"], index=False)
        positions.to_csv(paths["positions"], index=False)
        trades.to_csv(paths["trades"], index=False)
        signals.to_csv(paths["signals"], index=False)
        states.to_csv(paths["states"], index=False)
        filtered_buffer.to_csv(paths["filtered_candidates"], index=False)
        risk_distribution.to_csv(paths["risk_distribution"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _load_intraday_features(
    *,
    start_date: str,
    end_date: str,
    freq: str,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, feature_name, feature_value
    FROM factor.stock_intraday_features_daily
    WHERE feature_name = ANY(%s)
      AND freq = %s
      AND adjust_type = %s
      AND trade_date BETWEEN %s AND %s
      AND calc_version = 'intraday_v1'
    ORDER BY trade_date, asset_id, feature_name
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [V2_FEATURES, freq, adjust_type, start_date, end_date])
    return pd.DataFrame(rows)


def _rename_result_variant(result: dict[str, Any], variant_name: str) -> None:
    result["summary"]["variant_name"] = variant_name
    for key in ["equity_curve", "positions", "trades"]:
        frame = result.get(key)
        if isinstance(frame, pd.DataFrame) and "variant_name" in frame.columns:
            frame["variant_name"] = variant_name


def _append_deltas(summary: pd.DataFrame, *, baseline_variant_name: str) -> pd.DataFrame:
    result = summary.copy()
    baseline = result[result["variant_name"].eq(baseline_variant_name)]
    if baseline.empty:
        result["total_return_delta_vs_baseline"] = 0.0
        result["max_drawdown_delta_vs_baseline"] = 0.0
        return result
    base = baseline.iloc[0]
    result["total_return_delta_vs_baseline"] = (
        pd.to_numeric(result["total_return"], errors="coerce") - float(base.get("total_return", 0.0))
    )
    result["max_drawdown_delta_vs_baseline"] = (
        pd.to_numeric(result["max_drawdown"], errors="coerce") - float(base.get("max_drawdown", 0.0))
    )
    return result


def _risk_distribution(states: pd.DataFrame) -> pd.DataFrame:
    if states.empty:
        return pd.DataFrame(columns=["midtrend_risk_level", "count", "pct"])
    counts = states["midtrend_risk_level"].value_counts(dropna=False).rename_axis("midtrend_risk_level")
    frame = counts.reset_index(name="count")
    frame["pct"] = frame["count"] / float(len(states))
    return frame


def _render_report(
    summary: pd.DataFrame,
    *,
    risk_distribution: pd.DataFrame,
    start_date: str,
    end_date: str,
    risk_preset: str,
    filter_mode: str,
) -> str:
    lines = [
        "# Mid Trend Intraday Risk Overlay Backtest",
        "",
        "## Scope",
        f"- period: {start_date} to {end_date}",
        f"- intraday risk preset: {risk_preset}",
        f"- filter mode: {filter_mode}",
        f"- base variant: {DEFAULT_BASE_VARIANT}",
        "",
        "## Summary",
        summary.to_markdown(index=False) if not summary.empty else "No summary rows.",
        "",
        "## Risk Distribution",
        risk_distribution.to_markdown(index=False) if not risk_distribution.empty else "No risk states.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"
