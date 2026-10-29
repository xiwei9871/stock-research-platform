"""Read-only Market Monitor V2 regime-state service.

Serves a frozen PIT snapshot built by
``docs/market_monitor_v2/build_snapshot.py`` from the M1/M2/R3.1 research
artifacts.  The service never touches the production database and never
exposes forward-looking columns — every daily row in the snapshot was
computed from information available on that date only.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "docs/market_monitor_v2/data"
SNAPSHOT_DIR_ENV = "MARKET_REGIME_SNAPSHOT_DIR"

MARKETS = ("alla", "sse", "szse", "cyb")
ETF_GROUPS = ("g1", "g2", "g3")


def _snapshot_dir() -> Path:
    return Path(os.environ.get(SNAPSHOT_DIR_ENV, str(DEFAULT_SNAPSHOT_DIR)))


def _num(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=8)
def _load_market_snapshot(snapshot_dir: str) -> pd.DataFrame:
    df = pd.read_parquet(
        Path(snapshot_dir) / "market_regime_snapshot.parquet")
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


@lru_cache(maxsize=8)
def _load_etf_history(snapshot_dir: str) -> pd.DataFrame:
    df = pd.read_parquet(Path(snapshot_dir) / "etf_flow_history.parquet")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


@lru_cache(maxsize=8)
def _load_cycles(snapshot_dir: str) -> dict:
    p = Path(snapshot_dir) / "etf_cycles.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _resolve_trade_date(df: pd.DataFrame, trade_date: str | None) -> pd.Timestamp | None:
    if not len(df):
        return None
    if trade_date:
        ts = pd.Timestamp(trade_date)
        if ts in df.index:
            return ts
        prior = df.index[df.index <= ts]
        return prior.max() if len(prior) else None
    return df.index.max()


def _continuity_block(row: pd.Series) -> dict[str, Any]:
    missing = [c for c in ("amt", "amt_ratio_5_20", "lowvol_streak",
                           "pct_ma60", "pct_ma60_d20") if pd.isna(row.get(c))]
    return {
        "status": "READY" if not missing else "PARTIAL",
        "missing_fields": missing,
        "total_amount": _num(row.get("amt")),
        "amount_ratio_5_20": _num(row.get("amt_ratio_5_20")),
        "amount_ratio_20_60": _num(row.get("amt_ratio_20_60")),
        "amount_pct20": _num(row.get("amt_pct20")),
        "lowvol_streak": _num(row.get("lowvol_streak")),
        "lowvol20_share": _num(row.get("lowvol20")),
        "pct_above_ma60": _num(row.get("pct_ma60")),
        "pct_ma60_20": _num(row.get("pct_ma60_20")),
        "pct_ma60_d20": _num(row.get("pct_ma60_d20")),
        "breadth_bad_streak": _num(row.get("breadth_bad_streak")),
        "up_share": _num(row.get("up_share")),
        "up_share20": _num(row.get("up_share20")),
        "mcc_osc": _num(row.get("mcc_osc")),
        "mcc_sum": _num(row.get("mcc_sum")),
        "pct_hi20": _num(row.get("pct_hi20")),
        "explanation": (
            "Continuity metrics describe how long a condition has persisted; "
            "they do not forecast future returns."
        ),
    }


def _emotion_block(row: pd.Series) -> dict[str, Any]:
    if pd.isna(row.get("emotion")):
        return {"status": "DATA_MISSING", "missing_fields": ["emotion"]}
    return {
        "status": "READY",
        "emotion_score": _num(row.get("emotion")),
        "emotion20": _num(row.get("emotion20")),
        "emotion_d5": _num(row.get("emotion_d5")),
        "emotion_down_streak": _num(row.get("emotion_down_streak")),
        "source": "market_emotion_state_v1 replay (unchanged formula)",
    }


def _etf_block(trade_date: pd.Timestamp, snapshot_dir: str,
               history_days: int) -> dict[str, Any]:
    hist = _load_etf_history(snapshot_dir)
    cycles = _load_cycles(snapshot_dir)
    day = hist[hist.trade_date <= trade_date]
    if not len(day):
        return {"status": "DATA_MISSING", "groups": {}, "history": {}}
    latest_date = day.trade_date.max()
    stale = latest_date < trade_date
    groups: dict[str, Any] = {}
    for g in ETF_GROUPS:
        gday = day[day.gkey == g]
        if not len(gday):
            groups[g] = {"status": "DATA_MISSING"}
            continue
        last = gday.iloc[-1]
        flow20 = gday.tail(20).flow
        groups[g] = {
            "status": "READY",
            "daily_flow": _num(last.flow),
            "flow20": _num(flow20.sum()) if not flow20.isna().all() else None,
            "cycle_id": str(last.pcyc),
            "state": str(last.pstate),
            "cum_flow": _num(last.cum_flow),
            "cum_depth_pct": _num(last.cum_depth_pct),
            "cum_withdrawal_pct_aum0": _num(
                last.cum_withdrawal_pct_aum0),
            "ddur_days": _num(last.ddur),
            "vel20": _num(last.vel20),
            "vel5": _num(last.vel5),
            "outshare20": _num(last.outshare20),
            "cycle_aum": _num(last.aum),
            "max_depth_pct": (cycles.get(g) or {}).get("max_depth_pct"),
            "inflow_diffusion": "DATA_MISSING",
            "outflow_diffusion": "DATA_MISSING",
        }
    history: dict[str, list] = {}
    if history_days:
        for g in ETF_GROUPS:
            gday = day[day.gkey == g].tail(history_days)
            history[g] = [
                {
                    "date": str(r.trade_date)[:10],
                    "flow": _num(r.flow),
                    "cum_flow": _num(r.cum_flow),
                    "cum_depth_pct": _num(r.cum_depth_pct),
                    "cum_withdrawal_pct_aum0": _num(
                        r.cum_withdrawal_pct_aum0),
                    "state": str(r.pstate),
                }
                for r in gday.itertuples()
            ]
    return {
        "status": "STALE" if stale else "READY",
        "latest_etf_date": str(latest_date)[:10],
        "groups": groups,
        "history": history,
        "note": (
            "cum_depth_pct is cumulative net redemption relative to AUM at "
            "the cycle start; >100% does not imply holdings sold more than "
            "once. Diffusion metrics are not yet verified and are reported "
            "as DATA_MISSING rather than zero."
        ),
    }


def _regime_one(row: pd.Series, market: str) -> dict[str, Any]:
    dd = row.get(f"{market}_dd120")
    if pd.isna(dd):
        return {"status": "DATA_MISSING"}
    return {
        "status": "READY",
        "ret20": _num(row.get(f"{market}_ret20")),
        "ret60": _num(row.get(f"{market}_ret60")),
        "dd120": _num(dd),
        "vol60": _num(row.get(f"{market}_vol60")),
        "trend": _num(row.get(f"{market}_trend")),
        "regime": str(row.get(f"{market}_regime")),
        "regime_days": _num(row.get(f"{market}_regime_days")),
    }


def _regime_block(row: pd.Series, market: str) -> dict[str, Any]:
    blk = _regime_one(row, market)
    blk["all_markets"] = {m: _regime_one(row, m) for m in MARKETS}
    blk["note"] = (
        "Regime labels describe the current 120-trading-day drawdown "
        "state only; DECLINE does not imply the decline will continue.")
    return blk


def _history_rows(df: pd.DataFrame, end: pd.Timestamp, market: str,
                  history_days: int) -> list[dict[str, Any]]:
    sub = df.loc[:end].tail(history_days)
    cols = [f"{market}_dd120", f"{market}_ret20", "amt_ratio_5_20",
            "lowvol_streak", "pct_ma60", "pct_ma60_d20", "mcc_osc",
            "up_share", "emotion"]
    rows = []
    for ts, r in sub.iterrows():
        rows.append({
            "date": str(ts)[:10],
            **{c: _num(r.get(c)) for c in cols if c in sub.columns},
        })
    return rows


def regime_state(
    trade_date: str | None = None,
    market: str = "alla",
    history_days: int = 120,
    *,
    snapshot_dir: str | None = None,
) -> dict[str, Any]:
    snap_dir = snapshot_dir or str(_snapshot_dir())
    if market not in MARKETS:
        market = "alla"
    df = _load_market_snapshot(snap_dir)
    resolved = _resolve_trade_date(df, trade_date)
    if resolved is None:
        return {
            "market": market,
            "requested_date": trade_date,
            "status": "DATA_MISSING",
            "modules": {},
        }
    row = df.loc[resolved]
    history_days = max(0, min(int(history_days or 0), 1500))
    etf = _etf_block(resolved, snap_dir, history_days)
    return {
        "market": market,
        "requested_date": trade_date,
        "trade_date": str(resolved)[:10],
        "data_range": {
            "market": [str(df.index.min())[:10], str(df.index.max())[:10]],
            "etf_latest": etf.get("latest_etf_date"),
        },
        "modules": {
            "identity": {
                "status": "READY",
                "market": market,
                "trade_date": str(resolved)[:10],
                "source": "frozen PIT research snapshot "
                          "(M1/M2/R3.1 baseline 2a03051d)",
            },
            "emotion": _emotion_block(row),
            "continuity": _continuity_block(row),
            "etf_flow": etf,
            "regime": _regime_block(row, market),
            "history": {
                "status": "READY",
                "rows": _history_rows(df, resolved, market, history_days),
            },
        },
        "boundaries": {
            "advance_warning": "NOT_EVALUATED",
            "probability_calibration": "NOT_CALIBRATED",
            "predictive_models": "FROZEN (M2.1 research freeze)",
        },
    }


def clear_snapshot_caches() -> None:
    _load_market_snapshot.cache_clear()
    _load_etf_history.cache_clear()
    _load_cycles.cache_clear()
