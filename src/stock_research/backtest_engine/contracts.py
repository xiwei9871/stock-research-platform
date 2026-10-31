"""Input contracts for the unified backtest engine.

Target weights (one row per signal_date x asset_id):
    signal_date, asset_id, target_weight, strategy_id
    optional: signal_ts, score, rank

Price bars (raw, unadjusted, one row per trade_date x asset_id):
    trade_date, asset_id, open, high, low, close, volume, preclose,
    is_suspended, limit_up_price, limit_down_price, adj_factor
    optional: adjust_type (must be 'raw'), amount

Absent bar for an asset on a calendar day = not tradable that day.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

TARGET_REQUIRED = ("signal_date", "asset_id", "target_weight", "strategy_id")
BAR_REQUIRED = (
    "trade_date", "asset_id", "open", "high", "low", "close", "volume",
    "preclose", "is_suspended", "limit_up_price", "limit_down_price", "adj_factor",
)
BAR_NUMERIC = (
    "open", "high", "low", "close", "volume", "preclose",
    "limit_up_price", "limit_down_price", "adj_factor",
)
WEIGHT_TOLERANCE = 1e-9


class ContractError(ValueError):
    """Input violates the engine contract (fail-closed)."""


def _iso(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def validate_target_weights(
    frame: pd.DataFrame,
    *,
    max_gross_weight: float = 1.0,
    signal_cutoff: str | None = None,
) -> pd.DataFrame:
    missing = [c for c in TARGET_REQUIRED if c not in frame.columns]
    if missing:
        raise ContractError(f"target weights missing columns: {missing}")
    out = frame.copy()
    out["signal_date"] = out["signal_date"].map(_iso)
    out["asset_id"] = out["asset_id"].astype(str)
    out["target_weight"] = pd.to_numeric(out["target_weight"], errors="coerce")
    if out["target_weight"].isna().any():
        raise ContractError("target_weight must be numeric and non-null")
    if (out["target_weight"] < -WEIGHT_TOLERANCE).any():
        raise ContractError("negative target weights are not supported (long-only)")
    if out["strategy_id"].nunique() > 1:
        raise ContractError("one run must contain exactly one strategy_id")
    dup = out.duplicated(["signal_date", "asset_id"], keep=False)
    if dup.any():
        conflict = out[dup].groupby(["signal_date", "asset_id"])["target_weight"].nunique()
        if (conflict > 1).any():
            raise ContractError("conflicting duplicate signals for the same date/asset")
        out = out.drop_duplicates(["signal_date", "asset_id"])
    gross = out.groupby("signal_date")["target_weight"].sum()
    if (gross > max_gross_weight + WEIGHT_TOLERANCE).any():
        bad = gross[gross > max_gross_weight + WEIGHT_TOLERANCE].index[0]
        raise ContractError(f"gross target weight exceeds {max_gross_weight} on {bad}")
    if signal_cutoff is not None and "signal_ts" in out.columns:
        cutoff = dt.time.fromisoformat(signal_cutoff)
        ts = pd.to_datetime(out["signal_ts"], errors="coerce")
        limit = pd.to_datetime(out["signal_date"]) + pd.to_timedelta(
            cutoff.hour * 3600 + cutoff.minute * 60, unit="s"
        )
        late = ts.notna() & (ts > limit)
        if late.any():
            row = out[late].iloc[0]
            raise ContractError(
                f"signal_ts after cutoff {signal_cutoff} on {row['signal_date']} for {row['asset_id']}"
            )
    return out.sort_values(["signal_date", "asset_id"]).reset_index(drop=True)


def validate_price_bars(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in BAR_REQUIRED if c not in frame.columns]
    if missing:
        raise ContractError(f"price bars missing columns: {missing}")
    if "adjust_type" in frame.columns:
        kinds = set(frame["adjust_type"].dropna().astype(str))
        if kinds - {"raw"}:
            raise ContractError(
                f"execution requires raw (unadjusted) prices; got adjust_type={sorted(kinds)}"
            )
    out = frame.copy()
    out["trade_date"] = out["trade_date"].map(_iso)
    out["asset_id"] = out["asset_id"].astype(str)
    for col in BAR_NUMERIC:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["is_suspended"] = out["is_suspended"].map(_to_bool_or_none)
    if out.duplicated(["trade_date", "asset_id"]).any():
        raise ContractError("duplicate price bars for the same date/asset")
    return out.sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def _to_bool_or_none(value: object) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)
