from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.market_regime_confirmation_v1 import _weekly_effective_exposure
from stock_research.market_style_switch_v1 import (
    _build_strategy_selection,
    _filter_date_range,
    _simulate_equal_weight_daily,
    _summarize_equity,
    build_growth_momentum_candidates,
)
from stock_research.mid_trend_stock_protection_v1 import (
    StockProtectionConfig,
    apply_stock_protection_to_selection,
    compute_atr20,
)


DEFAULT_PROTECTION_CONFIG = StockProtectionConfig(
    variant_name="C2_atr2p5_rank20",
    atr_multiple=2.5,
    score_break_rank=20,
    rank_break_days=1,
    score_decline_days=2,
)


def build_current_mid_trend_strategy_v1_from_frames(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    asset_names: pd.DataFrame | None = None,
    top_n: int = 5,
    protection_config: StockProtectionConfig = DEFAULT_PROTECTION_CONFIG,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized_regime = _filter_date_range(regime, start_date, end_date)
    growth = _filter_date_range(build_growth_momentum_candidates(funnel, top_n=max(top_n, 10)), start_date, end_date)
    prices_with_atr = _ensure_atr20(prices)

    selection = _build_regime_selection(normalized_regime, growth, top_n=top_n)
    protected = apply_stock_protection_to_selection(
        selection,
        prices_with_atr,
        funnel,
        protection_config,
    )
    protected["strategy_family"] = "current_mid_trend_strategy_v1"
    protected["stock_protection_variant"] = protection_config.variant_name
    protected["confirmed_regime_state"] = protected["trade_date"].map(
        normalized_regime.set_index("trade_date")["confirmed_regime_state"].to_dict()
        if "confirmed_regime_state" in normalized_regime.columns
        else {}
    ).fillna("")

    holdings = _build_daily_holdings(
        protected,
        funnel,
        normalized_regime,
        asset_names=asset_names,
        protection_variant=protection_config.variant_name,
    )
    equity = _simulate_equal_weight_daily(
        prices_with_atr,
        protected,
        strategy_family="current_mid_trend_strategy_v1",
    )
    summary = _summarize_equity(equity)
    trades = _build_trade_changes(holdings)
    holding_summary = _build_holding_summary(holdings, normalized_regime)
    annual = _period_summary(equity, "Y")
    quarterly = _period_summary(equity, "Q")
    industry_exposure = _build_industry_exposure(holdings)
    protection_events = holdings[holdings["protection_reason"].astype(str).ne("")].copy()

    paths: dict[str, Path] = {}
    if output_dir is not None:
        paths = write_current_mid_trend_strategy_v1_outputs(
            output_dir=output_dir,
            equity=equity,
            summary=summary,
            holdings=holdings,
            trades=trades,
            holding_summary=holding_summary,
            annual=annual,
            quarterly=quarterly,
            industry_exposure=industry_exposure,
            protection_events=protection_events,
            params=_run_params(start_date, end_date, top_n, protection_config),
        )

    return {
        "regime": normalized_regime,
        "selection": selection,
        "protected_selection": protected,
        "holdings": holdings,
        "equity": equity,
        "summary": summary,
        "trades": trades,
        "holding_summary": holding_summary,
        "annual": annual,
        "quarterly": quarterly,
        "industry_exposure": industry_exposure,
        "protection_events": protection_events,
        "paths": paths,
    }


def run_current_mid_trend_strategy_v1_backtest(
    *,
    start_date: str,
    end_date: str,
    regime_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    top_n: int = 5,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    regime = pd.read_csv(regime_path)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    asset_ids = _candidate_asset_ids(funnel, start_date, end_date, top_n=max(top_n, 10))
    prices = load_current_strategy_prices(
        start_date,
        end_date,
        asset_ids=asset_ids,
        adjust_type=adjust_type,
        service=service,
    )
    asset_names = load_asset_names(asset_ids=asset_ids, service=service)
    return build_current_mid_trend_strategy_v1_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        asset_names=asset_names,
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        output_dir=output_dir,
    )


def load_current_strategy_prices(
    start_date: str,
    end_date: str,
    *,
    asset_ids: list[str],
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["trade_date", "asset_id", "high", "low", "close"])
    sql = """
        SELECT trade_date::text AS trade_date, asset_id, high, low, close
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
          AND asset_id = ANY(%s)
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date, asset_ids])
    return pd.DataFrame(rows)


def load_asset_names(
    *,
    asset_ids: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["asset_id", "stock_name"])
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT asset_id, name AS stock_name
            FROM core.asset_master
            WHERE asset_id = ANY(%s)
            """,
            [asset_ids],
        )
    return pd.DataFrame(rows)


def write_current_mid_trend_strategy_v1_outputs(
    *,
    output_dir: str | Path,
    equity: pd.DataFrame,
    summary: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    holding_summary: pd.DataFrame,
    annual: pd.DataFrame,
    quarterly: pd.DataFrame,
    industry_exposure: pd.DataFrame,
    protection_events: pd.DataFrame,
    params: pd.DataFrame,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "equity": output / "current_mid_trend_strategy_v1_equity.csv",
        "summary": output / "current_mid_trend_strategy_v1_summary.csv",
        "holdings": output / "current_mid_trend_strategy_v1_daily_holdings.csv",
        "trades": output / "current_mid_trend_strategy_v1_trade_changes.csv",
        "holding_summary": output / "current_mid_trend_strategy_v1_daily_holding_summary.csv",
        "annual": output / "current_mid_trend_strategy_v1_annual_summary.csv",
        "quarterly": output / "current_mid_trend_strategy_v1_quarterly_summary.csv",
        "industry_exposure": output / "current_mid_trend_strategy_v1_industry_exposure.csv",
        "protection_events": output / "current_mid_trend_strategy_v1_protection_events.csv",
        "params": output / "current_mid_trend_strategy_v1_run_params.csv",
        "report": output / "current_mid_trend_strategy_v1_report.md",
    }
    equity.to_csv(paths["equity"], index=False)
    summary.to_csv(paths["summary"], index=False)
    holdings.to_csv(paths["holdings"], index=False)
    trades.to_csv(paths["trades"], index=False)
    holding_summary.to_csv(paths["holding_summary"], index=False)
    annual.to_csv(paths["annual"], index=False)
    quarterly.to_csv(paths["quarterly"], index=False)
    industry_exposure.to_csv(paths["industry_exposure"], index=False)
    protection_events.to_csv(paths["protection_events"], index=False)
    params.to_csv(paths["params"], index=False)
    paths["report"].write_text(
        _render_report(summary, annual, quarterly, holding_summary, params),
        encoding="utf-8",
    )
    return paths


def _build_regime_selection(regime: pd.DataFrame, growth: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    if regime.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "strategy_family", "selection_style", "invested_weight"])
    style_state = regime[["trade_date"]].copy()
    for column in ["emotion_state", "risk_state", "emotion_score"]:
        style_state[column] = regime[column] if column in regime.columns else pd.NA
    style_state["style_state"] = "growth_momentum"
    style_state["position_budget_hint"] = "full"
    empty = pd.DataFrame(columns=growth.columns)
    selection = _build_strategy_selection(
        style_state,
        growth,
        empty,
        empty,
        "fixed_mid_trend",
        top_n,
    )
    exposure = _weekly_effective_exposure(regime).to_dict()
    confirmed = regime.set_index("trade_date")["confirmed_regime_state"].to_dict() if "confirmed_regime_state" in regime.columns else {}
    selection["strategy_family"] = "current_mid_trend_strategy_v1"
    selection["invested_weight"] = selection["trade_date"].map(exposure).astype(float).fillna(0.6)
    selection["confirmed_regime_state"] = selection["trade_date"].map(confirmed).fillna("")
    return selection


def _build_daily_holdings(
    protected: pd.DataFrame,
    funnel: pd.DataFrame,
    regime: pd.DataFrame,
    *,
    asset_names: pd.DataFrame | None,
    protection_variant: str,
) -> pd.DataFrame:
    holdings = protected.copy()
    meta = _candidate_meta(funnel)
    holdings = holdings.merge(meta, on=["trade_date", "asset_id"], how="left")
    names = _normalize_asset_names(asset_names)
    if not names.empty:
        holdings = holdings.merge(names, on="asset_id", how="left", suffixes=("", "_master"))
        if "stock_name_master" in holdings.columns:
            holdings["stock_name"] = holdings.get("stock_name", pd.Series(index=holdings.index)).fillna(holdings["stock_name_master"])
            holdings = holdings.drop(columns=["stock_name_master"])
    if "stock_name" not in holdings.columns:
        holdings["stock_name"] = ""
    holdings["stock_protection_variant"] = protection_variant
    holdings["target_weight"] = _target_weights(holdings)
    holdings["cash_weight"] = 1.0 - holdings.groupby("trade_date")["target_weight"].transform("sum")
    regime_cols = [
        column
        for column in [
            "trade_date",
            "emotion_score",
            "emotion_state",
            "risk_state",
            "confirmed_regime_state",
            "target_exposure",
            "rebalance_allowed",
            "transition_reason",
        ]
        if column in regime.columns
    ]
    if regime_cols:
        holdings = holdings.merge(regime[regime_cols], on="trade_date", how="left", suffixes=("", "_regime"))
        if "confirmed_regime_state_regime" in holdings.columns:
            holdings["confirmed_regime_state"] = holdings["confirmed_regime_state"].where(
                holdings["confirmed_regime_state"].astype(str).ne(""),
                holdings["confirmed_regime_state_regime"],
            )
            holdings = holdings.drop(columns=["confirmed_regime_state_regime"])
    return holdings.sort_values(["trade_date", "target_weight", "asset_id"], ascending=[True, False, True]).reset_index(drop=True)


def _build_trade_changes(holdings: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    previous: dict[str, float] = {}
    previous_date: str | None = None
    meta_by_asset = _latest_meta_by_asset(holdings)
    for trade_date, day in holdings.groupby("trade_date", sort=True):
        current = {
            str(row.asset_id): float(row.target_weight)
            for row in day.itertuples(index=False)
            if pd.notna(row.asset_id) and float(row.target_weight) > 0
        }
        for asset_id in sorted(set(previous) | set(current)):
            previous_weight = previous.get(asset_id, 0.0)
            target_weight = current.get(asset_id, 0.0)
            delta = target_weight - previous_weight
            if abs(delta) < 1e-12:
                continue
            row = _trade_meta(day, meta_by_asset, asset_id)
            rows.append(
                {
                    "trade_date": trade_date,
                    "previous_trade_date": previous_date,
                    "asset_id": asset_id,
                    "stock_name": row.get("stock_name", ""),
                    "industry_name": row.get("industry_name", ""),
                    "action": _trade_action(previous_weight, target_weight),
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "delta_weight": delta,
                    "confirmed_regime_state": row.get("confirmed_regime_state", ""),
                    "mid_trend_funnel_score": row.get("mid_trend_funnel_score", pd.NA),
                    "score_rank": row.get("score_rank", pd.NA),
                    "mid_trend_layer": row.get("mid_trend_layer", ""),
                    "protection_reason": row.get("protection_reason", ""),
                }
            )
        previous = current
        previous_date = str(trade_date)
    return pd.DataFrame(rows)


def _build_holding_summary(holdings: pd.DataFrame, regime: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame()
    summary = holdings.groupby("trade_date").agg(
        holdings_count=("asset_id", lambda values: int(values.notna().sum())),
        target_exposure=("target_weight", "sum"),
        cash_weight=("cash_weight", "max"),
        protection_triggers=("protection_reason", lambda values: int(values.astype(str).ne("").sum())),
    ).reset_index()
    regime_cols = [
        column
        for column in [
            "trade_date",
            "emotion_score",
            "emotion_state",
            "risk_state",
            "confirmed_regime_state",
            "target_exposure",
            "rebalance_allowed",
            "transition_reason",
        ]
        if column in regime.columns
    ]
    return summary.merge(regime[regime_cols], on="trade_date", how="left", suffixes=("_actual", "_regime")) if regime_cols else summary


def _period_summary(equity: pd.DataFrame, frequency: str) -> pd.DataFrame:
    columns = ["period", "start_date", "end_date", "days", "return", "max_drawdown"]
    if equity.empty:
        return pd.DataFrame(columns=columns)
    frame = equity.copy()
    frame["trade_date_dt"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["period"] = frame["trade_date_dt"].dt.to_period(frequency).astype(str)
    rows = []
    for period, group in frame.dropna(subset=["trade_date_dt"]).groupby("period", sort=True):
        curve = group["equity"].astype(float)
        rows.append(
            {
                "period": period,
                "start_date": group["trade_date"].iloc[0],
                "end_date": group["trade_date"].iloc[-1],
                "days": int(len(group)),
                "return": float(curve.iloc[-1] / curve.iloc[0] - 1.0),
                "max_drawdown": _max_drawdown(curve),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _build_industry_exposure(holdings: pd.DataFrame) -> pd.DataFrame:
    active = holdings[holdings["asset_id"].notna()].copy()
    if active.empty:
        return pd.DataFrame(columns=["trade_date", "industry_name", "weight", "stock_names"])
    return active.groupby(["trade_date", "industry_name"], dropna=False).agg(
        weight=("target_weight", "sum"),
        stock_names=("stock_name", lambda values: ";".join(str(value) for value in values.dropna())),
    ).reset_index()


def _ensure_atr20(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    if "atr20" in frame.columns:
        return frame
    return frame.merge(compute_atr20(frame), on=["trade_date", "asset_id"], how="left")


def _candidate_asset_ids(funnel: pd.DataFrame, start_date: str, end_date: str, *, top_n: int) -> list[str]:
    growth = _filter_date_range(build_growth_momentum_candidates(funnel, top_n=max(top_n, 10)), start_date, end_date)
    return sorted(growth["asset_id"].dropna().astype(str).unique().tolist()) if not growth.empty else []


def _candidate_meta(funnel: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "mid_trend_funnel_score",
        "score_rank",
        "mid_trend_layer",
        "mainline_status",
        "industry_mainline_score_v1",
        "ret_20_score",
        "ret_60_score",
        "max_drawdown_20_score",
        "atr_pct_score",
        "stock_excess_ret_20_score",
    ]
    frame = funnel.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    return frame[columns].drop_duplicates(["trade_date", "asset_id"], keep="first")


def _normalize_asset_names(asset_names: pd.DataFrame | None) -> pd.DataFrame:
    if asset_names is None or asset_names.empty or "asset_id" not in asset_names.columns:
        return pd.DataFrame(columns=["asset_id", "stock_name"])
    frame = asset_names.copy()
    if "stock_name" not in frame.columns and "name" in frame.columns:
        frame = frame.rename(columns={"name": "stock_name"})
    if "stock_name" not in frame.columns:
        frame["stock_name"] = ""
    frame["asset_id"] = frame["asset_id"].astype(str)
    return frame[["asset_id", "stock_name"]].drop_duplicates("asset_id", keep="first")


def _target_weights(holdings: pd.DataFrame) -> pd.Series:
    counts = holdings.groupby("trade_date")["asset_id"].transform(lambda values: int(values.notna().sum()))
    invested = pd.to_numeric(holdings["invested_weight"], errors="coerce").fillna(0.0)
    active = holdings["asset_id"].notna() & counts.gt(0)
    weights = pd.Series(0.0, index=holdings.index)
    weights.loc[active] = invested.loc[active] / counts.loc[active].astype(float)
    return weights


def _latest_meta_by_asset(holdings: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    active = holdings[holdings["asset_id"].notna()]
    for row in active.to_dict("records"):
        result[str(row["asset_id"])] = row
    return result


def _trade_meta(day: pd.DataFrame, meta_by_asset: dict[str, dict[str, Any]], asset_id: str) -> dict[str, Any]:
    active = day[day["asset_id"].astype(str).eq(asset_id)]
    if not active.empty:
        return active.iloc[0].to_dict()
    return meta_by_asset.get(asset_id, {})


def _trade_action(previous_weight: float, target_weight: float) -> str:
    if previous_weight == 0.0 and target_weight > 0.0:
        return "buy"
    if previous_weight > 0.0 and target_weight == 0.0:
        return "sell"
    return "increase" if target_weight > previous_weight else "decrease"


def _max_drawdown(curve: pd.Series) -> float:
    if curve.empty:
        return 0.0
    normalized = curve.astype(float).reset_index(drop=True)
    full = pd.concat([pd.Series([1.0]), normalized], ignore_index=True)
    return float((full / full.cummax() - 1.0).min())


def _run_params(
    start_date: str,
    end_date: str,
    top_n: int,
    protection_config: StockProtectionConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"key": "strategy", "value": "current_mid_trend_strategy_v1"},
            {"key": "start_date", "value": start_date},
            {"key": "end_date", "value": end_date},
            {"key": "top_n", "value": top_n},
            {"key": "market_regime_preset", "value": "tight3b_bt100"},
            {"key": "stock_protection_variant", "value": protection_config.variant_name},
            {"key": "atr_multiple", "value": protection_config.atr_multiple},
            {"key": "score_break_rank", "value": protection_config.score_break_rank},
            {"key": "rank_break_days", "value": protection_config.rank_break_days},
            {"key": "score_decline_days", "value": protection_config.score_decline_days},
            {"key": "return_model", "value": "close_to_next_close research approximation"},
        ]
    )


def _render_report(
    summary: pd.DataFrame,
    annual: pd.DataFrame,
    quarterly: pd.DataFrame,
    holding_summary: pd.DataFrame,
    params: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# Current Mid Trend Strategy V1",
            "",
            "## Params",
            params.to_markdown(index=False) if not params.empty else "No params.",
            "",
            "## Summary",
            summary.to_markdown(index=False) if not summary.empty else "No summary.",
            "",
            "## Annual",
            annual.to_markdown(index=False) if not annual.empty else "No annual rows.",
            "",
            "## Quarterly",
            quarterly.to_markdown(index=False) if not quarterly.empty else "No quarterly rows.",
            "",
            "## Latest Holding Summary",
            holding_summary.tail(20).to_markdown(index=False) if not holding_summary.empty else "No holding summary.",
            "",
        ]
    )
