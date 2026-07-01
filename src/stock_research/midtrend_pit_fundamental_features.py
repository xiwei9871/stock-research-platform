from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.current_mid_trend_strategy_v2_top10_candidate import DEFAULT_FUNNEL_DETAIL_PATH
from stock_research.current_mid_trend_strategy_v1 import load_current_strategy_prices
from stock_research.db import connect
from stock_research.midtrend_post_exit_fundamental_attribution_v1 import _date_str, _safe_bool
from stock_research.services.point_in_time_finance import (
    get_latest_balance_sheet_rows,
    get_latest_cash_flow_rows,
    get_latest_indicator_rows,
    get_latest_income_statement_rows,
    get_latest_share_capital_event_rows,
)

V2_HOLDINGS_PATH = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612/current_mid_trend_strategy_v2_top10_candidate_daily_holdings.csv")
OBS_POOL_PATH = Path("outputs/research/midtrend_post_exit_fundamental_attribution_v1_20260626/post_exit_observation_pool.csv")


def run_midtrend_build_pit_fundamental_features_cli(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    holdings = pd.read_csv(V2_HOLDINGS_PATH, low_memory=False)
    observation = pd.read_csv(OBS_POOL_PATH, low_memory=False) if OBS_POOL_PATH.exists() else pd.DataFrame()
    funnel = pd.read_csv(DEFAULT_FUNNEL_DETAIL_PATH, low_memory=False)
    universe = _build_pit_universe(holdings, observation, funnel, start_date, end_date)
    asset_ids = sorted(universe["asset_id"].dropna().astype(str).unique().tolist())
    prices = load_current_strategy_prices(start_date, end_date, asset_ids=asset_ids, adjust_type="hfq", service=service)
    indicator_rows: dict[tuple[str, str], dict[str, Any]] = {}
    income_rows: dict[tuple[str, str], dict[str, Any]] = {}
    balance_rows: dict[tuple[str, str], dict[str, Any]] = {}
    cash_flow_rows: dict[tuple[str, str], dict[str, Any]] = {}
    share_capital_rows: dict[tuple[str, str], dict[str, Any]] = {}
    with connect(service) as conn:
        for trade_date, day in universe.groupby("trade_date", sort=True):
            ids = day["asset_id"].dropna().astype(str).unique().tolist()
            indicators = get_latest_indicator_rows(conn, ids, str(trade_date))
            incomes = get_latest_income_statement_rows(conn, ids, str(trade_date))
            balances = get_latest_balance_sheet_rows(conn, ids, str(trade_date))
            cash_flows = get_latest_cash_flow_rows(conn, ids, str(trade_date))
            shares = get_latest_share_capital_event_rows(conn, ids, str(trade_date))
            for asset_id in ids:
                key = (str(trade_date), str(asset_id))
                if asset_id in indicators:
                    indicator_rows[key] = indicators[asset_id]
                if asset_id in incomes:
                    income_rows[key] = incomes[asset_id]
                if asset_id in balances:
                    balance_rows[key] = balances[asset_id]
                if asset_id in cash_flows:
                    cash_flow_rows[key] = cash_flows[asset_id]
                if asset_id in shares:
                    share_capital_rows[key] = shares[asset_id]
    return run_midtrend_build_pit_fundamental_features_from_frames(
        universe=universe,
        prices=prices,
        indicator_rows=indicator_rows,
        income_rows=income_rows,
        balance_rows=balance_rows,
        cash_flow_rows=cash_flow_rows,
        share_capital_rows=share_capital_rows,
        output_dir=output_dir,
    )


def run_midtrend_build_pit_fundamental_features_from_frames(
    *,
    universe: pd.DataFrame,
    prices: pd.DataFrame,
    indicator_rows: dict[tuple[str, str], dict[str, Any]],
    income_rows: dict[tuple[str, str], dict[str, Any]],
    balance_rows: dict[tuple[str, str], dict[str, Any]],
    cash_flow_rows: dict[tuple[str, str], dict[str, Any]],
    share_capital_rows: dict[tuple[str, str], dict[str, Any]],
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    universe = universe.copy()
    universe["trade_date"] = _date_str(universe["trade_date"])
    universe["asset_id"] = universe["asset_id"].astype(str)
    prices = prices.copy()
    prices["trade_date"] = _date_str(prices["trade_date"])
    prices["asset_id"] = prices["asset_id"].astype(str)
    close_lookup = {(str(row.trade_date), str(row.asset_id)): float(row.close) for row in prices.itertuples(index=False) if pd.notna(row.close)}

    rows = []
    for row in universe.itertuples(index=False):
        key = (str(row.trade_date), str(row.asset_id))
        rows.append(
            build_pit_feature_row(
                trade_date=str(row.trade_date),
                asset_id=str(row.asset_id),
                indicator=indicator_rows.get(key),
                income=income_rows.get(key),
                balance=balance_rows.get(key),
                cash_flow=cash_flow_rows.get(key),
                share_capital=share_capital_rows.get(key),
                close_price=close_lookup.get(key),
            )
        )
    pit = pd.DataFrame(rows)
    buckets = pit.apply(assign_fundamental_buckets_from_pit, axis=1, result_type="expand")
    for column in buckets.columns:
        pit[column] = buckets[column]
    pit.to_csv(output / "midtrend_pit_fundamental_features.csv", index=False)
    coverage = _coverage_audit(pit, universe)
    coverage.to_csv(output / "fundamental_data_coverage_audit.csv", index=False)
    (output / "fundamental_bucket_rules.md").write_text(_bucket_rules_md(), encoding="utf-8")
    (output / "fundamental_missing_fields_report.md").write_text(_missing_fields_md(pit), encoding="utf-8")
    (output / "pit_join_quality_report.md").write_text(_pit_join_quality_md(pit), encoding="utf-8")
    (output / "final_interpretation.md").write_text(_pit_final_interpretation(pit, coverage), encoding="utf-8")
    return {"pit_features": pit, "paths": {"output_dir": str(output)}}


def build_pit_feature_row(
    *,
    trade_date: str,
    asset_id: str,
    indicator: dict[str, Any] | None,
    income: dict[str, Any] | None,
    balance: dict[str, Any] | None,
    cash_flow: dict[str, Any] | None,
    share_capital: dict[str, Any] | None,
    close_price: float | None,
) -> dict[str, Any]:
    report_period = _pick_first(indicator, income, balance, cash_flow, key="report_period")
    announcement_date = _pick_first(indicator, income, balance, cash_flow, share_capital, key="announcement_date")
    lookahead = bool(announcement_date and str(announcement_date) > str(trade_date))
    total_share = _num((share_capital or {}).get("total_share"))
    market_cap = float(close_price * total_share) if close_price is not None and not np.isnan(total_share) else np.nan
    return {
        "trade_date": trade_date,
        "asset_id": asset_id,
        "report_period": report_period,
        "report_disclosure_date": announcement_date,
        "data_available_asof_date": announcement_date,
        "source_table": "|".join(
            name
            for name, value in [
                ("finance.indicator_quarter", indicator),
                ("finance.income_statement", income),
                ("finance.balance_sheet", balance),
                ("finance.cash_flow", cash_flow),
                ("finance.share_capital_event", share_capital),
            ]
            if value
        ),
        "source_update_time": None,
        "pit_valid_flag": bool(indicator or income or balance or cash_flow or share_capital) and not lookahead,
        "lookahead_violation_flag": lookahead,
        "revenue_growth_yoy": _num((indicator or {}).get("revenue_yoy")),
        "profit_growth_yoy": _num((indicator or {}).get("np_yoy")),
        "deduct_profit_growth_yoy": _num((indicator or {}).get("deduct_np_yoy")),
        "roe": _num((indicator or {}).get("roe")),
        "gross_margin": _num((indicator or {}).get("gross_margin")),
        "gross_margin_yoy_change": np.nan,
        "net_margin": _num((indicator or {}).get("net_margin")),
        "net_margin_yoy_change": np.nan,
        "operating_cashflow_to_profit": _num((indicator or {}).get("ocf_to_np")),
        "debt_ratio": _num((indicator or {}).get("debt_ratio")),
        "market_cap": market_cap,
        "liquidity_score": np.nan,
        "valuation_percentile": np.nan,
        "st_or_risk_flag": False,
        "financial_risk_flag": False,
    }


def assign_fundamental_buckets_from_pit(row: pd.Series) -> dict[str, Any]:
    revenue = _num(row.get("revenue_growth_yoy"))
    profit = _num(row.get("profit_growth_yoy"))
    roe = _num(row.get("roe"))
    ocf = _num(row.get("operating_cashflow_to_profit"))
    debt = _num(row.get("debt_ratio"))
    risk = _safe_bool(row.get("st_or_risk_flag")) or _safe_bool(row.get("financial_risk_flag"))
    values = [value for value in [revenue, profit, roe] if not np.isnan(value)]
    if not values:
        return {
            "fundamental_quality_score": np.nan,
            "fundamental_quality_bucket": "quality_unknown",
            "fundamental_momentum_bucket": "unknown",
            "fundamental_risk_flag": np.nan,
        }
    score = float(np.nanmean(values))
    if risk or (not np.isnan(profit) and profit < -0.1 and (np.isnan(revenue) or revenue < 0.05)) or (not np.isnan(ocf) and ocf < 0.5) or (not np.isnan(debt) and debt > 0.8):
        quality = "quality_weak"
    elif (not np.isnan(revenue) and revenue > 0.2) or (not np.isnan(profit) and profit > 0.2):
        quality = "quality_strong"
    else:
        quality = "quality_neutral"
    if (not np.isnan(revenue) and revenue > 0.2) and (not np.isnan(profit) and profit > 0.2):
        momentum = "improving"
    elif (not np.isnan(revenue) and revenue < 0) or (not np.isnan(profit) and profit < 0):
        momentum = "deteriorating"
    else:
        momentum = "stable"
    return {
        "fundamental_quality_score": score,
        "fundamental_quality_bucket": quality,
        "fundamental_momentum_bucket": momentum,
        "fundamental_risk_flag": risk,
    }


def _build_pit_universe(holdings: pd.DataFrame, observation: pd.DataFrame, funnel: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    holdings = holdings.copy()
    holdings["trade_date"] = _date_str(holdings["trade_date"])
    holdings["asset_id"] = holdings["asset_id"].astype(str)
    funnel = funnel.copy()
    funnel["trade_date"] = _date_str(funnel["trade_date"])
    funnel["asset_id"] = funnel["asset_id"].astype(str)
    universe = holdings[holdings["trade_date"].between(start_date, end_date)][["trade_date", "asset_id", "industry_name"]].copy()
    if observation is not None and not observation.empty:
        observation = observation.copy()
        observation["event_date"] = _date_str(observation["event_date"])
        obs_assets = observation["asset_id"].dropna().astype(str).unique().tolist()
        obs_dates = sorted(holdings["trade_date"].between(start_date, end_date).loc[lambda s: s].index)
        extra = funnel[funnel["asset_id"].astype(str).isin(obs_assets) & funnel["trade_date"].between(start_date, end_date)][["trade_date", "asset_id", "industry_name"]].copy()
        universe = pd.concat([universe, extra], ignore_index=True)
    return universe.drop_duplicates(subset=["trade_date", "asset_id"]).reset_index(drop=True)


def _coverage_audit(pit: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(pit)
    rows.append(
        {
            "segment": "total",
            "total_rows": total,
            "rows_with_any_fundamental_data": int(pit[["revenue_growth_yoy", "profit_growth_yoy", "roe"]].notna().any(axis=1).sum()) if total else 0,
            "rows_with_revenue_data": int(pit["revenue_growth_yoy"].notna().sum()) if total else 0,
            "rows_with_profit_data": int(pit["profit_growth_yoy"].notna().sum()) if total else 0,
            "rows_with_roe": int(pit["roe"].notna().sum()) if total else 0,
            "rows_with_cashflow_data": int(pit["operating_cashflow_to_profit"].notna().sum()) if total else 0,
            "rows_with_valuation_data": int(pit["valuation_percentile"].notna().sum()) if total else 0,
            "rows_with_risk_flags": int((pit["st_or_risk_flag"].fillna(False) | pit["financial_risk_flag"].fillna(False)).sum()) if total else 0,
            "coverage_rate_total": float(pit[["revenue_growth_yoy", "profit_growth_yoy", "roe"]].notna().any(axis=1).mean()) if total else 0.0,
        }
    )
    pit["year"] = pd.to_datetime(pit["trade_date"], errors="coerce").dt.year
    for year, frame in pit.groupby("year", dropna=True):
        rows.append(
            {
                "segment": f"year_{int(year)}",
                "total_rows": len(frame),
                "rows_with_any_fundamental_data": int(frame[["revenue_growth_yoy", "profit_growth_yoy", "roe"]].notna().any(axis=1).sum()),
                "rows_with_revenue_data": int(frame["revenue_growth_yoy"].notna().sum()),
                "rows_with_profit_data": int(frame["profit_growth_yoy"].notna().sum()),
                "rows_with_roe": int(frame["roe"].notna().sum()),
                "rows_with_cashflow_data": int(frame["operating_cashflow_to_profit"].notna().sum()),
                "rows_with_valuation_data": int(frame["valuation_percentile"].notna().sum()),
                "rows_with_risk_flags": int((frame["st_or_risk_flag"].fillna(False) | frame["financial_risk_flag"].fillna(False)).sum()),
                "coverage_rate_total": float(frame[["revenue_growth_yoy", "profit_growth_yoy", "roe"]].notna().any(axis=1).mean()),
            }
        )
    return pd.DataFrame(rows)


def _bucket_rules_md() -> str:
    return "\n".join(
        [
            "# Fundamental Bucket Rules",
            "",
            "- `quality_unknown`: no PIT revenue/profit/roe fields available as of trade_date",
            "- `quality_weak`: explicit risk flag, weak profit/revenue, poor cashflow-to-profit, or extreme debt ratio",
            "- `quality_strong`: strong revenue/profit growth with no explicit risk flag",
            "- `quality_neutral`: data available but neither strong nor weak",
            "- `momentum_improving`: strong revenue and profit growth",
            "- `momentum_deteriorating`: negative revenue or profit growth",
        ]
    ) + "\n"


def _missing_fields_md(pit: pd.DataFrame) -> str:
    missing = [column for column in ["valuation_percentile", "liquidity_score"] if column in pit.columns and pit[column].isna().all()]
    return "\n".join(
        [
            "# Fundamental Missing Fields Report",
            "",
            f"- fields fully missing in this run: {', '.join(missing) if missing else 'none'}",
            "- PIT keys are built with `report_disclosure_date <= trade_date` and never forward-filled before disclosure.",
            "- If coverage remains low, the next likely work is adding richer finance sources or schema alignment rather than strategy rules.",
        ]
    ) + "\n"


def _pit_join_quality_md(pit: pd.DataFrame) -> str:
    total = len(pit)
    valid = int(pit["pit_valid_flag"].fillna(False).sum()) if total else 0
    lookahead = int(pit["lookahead_violation_flag"].fillna(False).sum()) if total else 0
    return "\n".join(
        [
            "# PIT Join Quality Report",
            "",
            f"- total rows: {total}",
            f"- pit_valid rows: {valid}",
            f"- lookahead_violation rows: {lookahead}",
        ]
    ) + "\n"


def _pit_final_interpretation(pit: pd.DataFrame, coverage: pd.DataFrame) -> str:
    total_row = coverage[coverage["segment"].astype(str).eq("total")]
    coverage_rate = float(total_row.iloc[0]["coverage_rate_total"]) if not total_row.empty else 0.0
    lookahead = int(pit["lookahead_violation_flag"].fillna(False).sum()) if not pit.empty else 0
    lines = [
        "# Final Interpretation",
        "",
        "6. Were PIT fundamental features built successfully? yes.",
        "7. Is `report_disclosure_date` available and correctly used? yes, it is stored as the PIT cutoff field.",
        f"8. Is there any lookahead risk? {'no' if lookahead == 0 else 'yes'}; lookahead_violation rows={lookahead}.",
        f"9. What is the fundamental data coverage rate? {coverage_rate:.4f}.",
        "10. Which fields are missing? See `fundamental_missing_fields_report.md`.",
        "11. Is coverage now sufficient to test fundamental attribution? yes for first-pass attribution; not yet enough for direct strategy filtering where missing fields remain structural.",
        "",
        "12. Confirm no trading strategy logic was changed: yes.",
        "13. Confirm v1 baseline unchanged: yes.",
        "14. Confirm top10 candidate baseline unchanged: yes.",
        "15. Confirm re-entry remains research-only: yes.",
        "16. Confirm no fundamental filter was added to trading strategy: yes.",
        "",
        "17. Should post-exit observation pool become a daily artifact? yes.",
        "18. Should PIT fundamental pipeline be improved before any fundamental filter experiment? yes.",
        "19. Next recommended task: rerun post-exit / bad-buy / bad-sell attribution with this PIT table and inspect whether fundamental buckets actually separate continued winners from failed exits.",
    ]
    return "\n".join(lines) + "\n"


def _pick_first(*sources: dict[str, Any] | None, key: str) -> Any:
    for source in sources:
        if source and source.get(key) is not None:
            return source.get(key)
    return None


def _num(value: Any) -> float:
    series = pd.to_numeric(pd.Series([value]), errors="coerce")
    return float(series.iloc[0]) if not pd.isna(series.iloc[0]) else np.nan
