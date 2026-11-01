"""Input contracts for the unified backtest engine (fail-closed).

Signal schedule (one row per decision date; REQUIRED):
    signal_date, signal_ts            signal_ts must be timezone-aware
    optional: inputs_asof_ts          latest availability time of the inputs
                                      the decision used (declared by caller)
  A schedule date with no target rows means ALL_CASH_TARGET.
  A calendar date absent from the schedule means NO_SIGNAL (hold).

Target weights (one row per signal_date x asset_id):
    signal_date, asset_id, target_weight, strategy_id
    optional: score, rank, signal_provenance

Price bars (raw, unadjusted, one row per trade_date x asset_id):
    trade_date, asset_id, adjust_type='raw', open, high, low, close, volume,
    preclose, is_suspended, limit_up_price, limit_down_price, adj_factor
  limit price NaN = state unknown (fail-closed);
  limit_up_price=+inf / limit_down_price=0 = no price limit that day.
  Absent bar for an asset on a calendar day = not tradable that day.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

SCHEDULE_REQUIRED = ("signal_date", "signal_ts")
TARGET_REQUIRED = ("signal_date", "asset_id", "target_weight", "strategy_id")
BAR_REQUIRED = (
    "trade_date", "asset_id", "adjust_type", "open", "high", "low", "close", "volume",
    "preclose", "is_suspended", "limit_up_price", "limit_down_price", "adj_factor",
)
BAR_NUMERIC = (
    "open", "high", "low", "close", "volume", "preclose",
    "limit_up_price", "limit_down_price", "adj_factor",
)
WEIGHT_TOLERANCE = 1e-9
_TRUE = {"1", "true", "t", "yes", "y"}
_FALSE = {"0", "false", "f", "no", "n"}

INPUT_AVAILABILITY_DECLARED = "DECLARED_AND_CHECKED"
INPUT_AVAILABILITY_NOT_DECLARED = "NOT_DECLARED"


class ContractError(ValueError):
    """Input violates the engine contract (fail-closed)."""


def _iso(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _aware(value: object, field: str, tz: ZoneInfo) -> pd.Timestamp:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        raise ContractError(f"{field} is missing")
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} is not a valid timestamp: {value!r}") from exc
    if pd.isna(ts):
        raise ContractError(f"{field} is not a valid timestamp: {value!r}")
    if ts.tzinfo is None:
        raise ContractError(f"{field} must carry an explicit timezone offset: {value!r}")
    return ts.tz_convert(tz)


def validate_signal_schedule(
    frame: pd.DataFrame,
    *,
    signal_cutoff: str,
    timezone: str,
) -> tuple[pd.DataFrame, str]:
    """Return (schedule, input_availability_status)."""
    missing = [c for c in SCHEDULE_REQUIRED if c not in frame.columns]
    if missing:
        raise ContractError(f"signal schedule missing columns: {missing}")
    if frame.empty:
        raise ContractError("signal schedule is empty")
    tz = ZoneInfo(timezone)
    cutoff = dt.time.fromisoformat(signal_cutoff)
    out = frame.copy()
    out["signal_date"] = out["signal_date"].map(_iso)
    if out["signal_date"].duplicated().any():
        raise ContractError("duplicate signal_date in schedule")
    stamps = [_aware(v, "signal_ts", tz) for v in out["signal_ts"]]
    for day, ts in zip(out["signal_date"], stamps):
        if ts.date().isoformat() != day:
            raise ContractError(f"signal_ts {ts.isoformat()} is not on signal_date {day} ({timezone})")
        if ts.time() > cutoff:
            raise ContractError(f"signal_ts {ts.isoformat()} after cutoff {signal_cutoff} on {day}")
    out["signal_ts"] = [ts.isoformat() for ts in stamps]
    status = INPUT_AVAILABILITY_NOT_DECLARED
    if "inputs_asof_ts" in out.columns:
        asof = [_aware(v, "inputs_asof_ts", tz) for v in out["inputs_asof_ts"]]
        for day, a, s in zip(out["signal_date"], asof, stamps):
            if a > s:
                raise ContractError(
                    f"inputs_asof_ts {a.isoformat()} later than signal_ts {s.isoformat()} on {day}")
        out["inputs_asof_ts"] = [a.isoformat() for a in asof]
        status = INPUT_AVAILABILITY_DECLARED
    return out.sort_values("signal_date").reset_index(drop=True), status


def validate_target_weights(
    frame: pd.DataFrame,
    *,
    schedule_dates: set[str],
    max_gross_weight: float = 1.0,
) -> pd.DataFrame:
    missing = [c for c in TARGET_REQUIRED if c not in frame.columns]
    if missing:
        raise ContractError(f"target weights missing columns: {missing}")
    out = frame.copy()
    if out.empty:
        return out.assign(signal_date=pd.Series(dtype=str), asset_id=pd.Series(dtype=str),
                          target_weight=pd.Series(dtype=float))
    out["signal_date"] = out["signal_date"].map(_iso)
    out["asset_id"] = out["asset_id"].astype(str)
    out["target_weight"] = pd.to_numeric(out["target_weight"], errors="coerce")
    if out["target_weight"].isna().any():
        raise ContractError("target_weight must be numeric and non-null")
    if (out["target_weight"] < -WEIGHT_TOLERANCE).any():
        raise ContractError("negative target weights are not supported (long-only)")
    if out["strategy_id"].nunique() > 1:
        raise ContractError("one run must contain exactly one strategy_id")
    outside = sorted(set(out["signal_date"]) - schedule_dates)
    if outside:
        raise ContractError(f"target rows on a date absent from the signal schedule: {outside[0]}")
    dup = out.duplicated(["signal_date", "asset_id"], keep=False)
    if dup.any():
        conflict = out[dup].groupby(["signal_date", "asset_id"])["target_weight"].nunique()
        if (conflict > 1).any():
            raise ContractError("conflicting duplicate signals for the same date/asset")
        out = out.drop_duplicates(["signal_date", "asset_id"])
    gross = out.groupby("signal_date")["target_weight"].sum()
    over = gross[gross > max_gross_weight + WEIGHT_TOLERANCE]
    if not over.empty:
        raise ContractError(f"gross target weight exceeds {max_gross_weight} on {over.index[0]}")
    return out.sort_values(["signal_date", "asset_id"]).reset_index(drop=True)


def validate_price_bars(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in BAR_REQUIRED if c not in frame.columns]
    if missing:
        raise ContractError(f"price bars missing columns: {missing}")
    kinds = frame["adjust_type"].astype("string")
    if kinds.isna().any() or set(kinds) - {"raw"}:
        raise ContractError(
            f"execution requires raw (unadjusted) prices; got adjust_type={sorted(set(kinds.dropna()))}"
            + (" and missing values" if kinds.isna().any() else ""))
    out = frame.copy()
    out["trade_date"] = out["trade_date"].map(_iso)
    out["asset_id"] = out["asset_id"].astype(str)
    for col in BAR_NUMERIC:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["is_suspended"] = out["is_suspended"].map(parse_tristate)
    if out.duplicated(["trade_date", "asset_id"]).any():
        raise ContractError("duplicate price bars for the same date/asset")
    return out.sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def parse_tristate(value: object) -> bool | None:
    """True / False for recognized values; None (= unknown) otherwise."""
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return {1: True, 0: False}.get(value)
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in _TRUE:
            return True
        if norm in _FALSE:
            return False
    return None
