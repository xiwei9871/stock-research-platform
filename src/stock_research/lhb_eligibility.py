from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


LHB_ELIGIBILITY_CONTRACT_VERSION = "lhb_eligibility_v2"
PUMP_WARNING_THRESHOLD = 0.75
PUMP_REJECT_THRESHOLD = 0.90
LARGE_DRAWDOWN_WARNING_THRESHOLD = 0.08


@dataclass(frozen=True)
class PriceLimitState:
    regime: str
    near_limit_down_threshold: float | None
    near_limit_down: bool
    is_st: bool | None
    status_source: str
    data_quality_status: str
    pct_chg: float | None


def resolve_price_limit_state(
    *,
    trade_date: str,
    ts_code: str,
    same_day_name: object,
    current_name: object,
    pct_chg: object,
    stored_is_st: object,
    stored_status_quality: str,
    list_date: object,
    listing_age_trading_days: object = None,
) -> PriceLimitState:
    del trade_date, current_name, list_date
    is_st, status_source = _resolve_point_in_time_st(
        same_day_name=same_day_name,
        stored_is_st=stored_is_st,
        stored_status_quality=stored_status_quality,
    )
    listing_age = _optional_int(listing_age_trading_days)
    if listing_age is not None and 0 <= listing_age <= 5:
        regime = "listing_no_limit"
        threshold = None
    else:
        regime, threshold = _regime_and_threshold(ts_code=ts_code, is_st=is_st)

    change = _optional_float(pct_chg)
    if change is None:
        quality = "pct_chg_missing"
    elif is_st is None:
        quality = "st_status_unknown"
    else:
        quality = "complete"
    near_limit_down = bool(change is not None and threshold is not None and change <= threshold)
    return PriceLimitState(
        regime=regime,
        near_limit_down_threshold=threshold,
        near_limit_down=near_limit_down,
        is_st=is_st,
        status_source=status_source,
        data_quality_status=quality,
        pct_chg=change,
    )


def _resolve_point_in_time_st(
    *,
    same_day_name: object,
    stored_is_st: object,
    stored_status_quality: str,
) -> tuple[bool | None, str]:
    name = str(same_day_name or "").strip().upper()
    if name and name != "NAN":
        return bool(re.match(r"^(?:\*?ST|S\*ST)", name)), "same_day_lhb_name"
    if str(stored_status_quality or "").strip().lower() == "trusted":
        parsed = _optional_bool(stored_is_st)
        if parsed is not None:
            return parsed, "asset_status_daily"
    return None, "unavailable"


def _regime_and_threshold(*, ts_code: str, is_st: bool | None) -> tuple[str, float]:
    if is_st is True:
        return "st", -4.8
    text = str(ts_code or "").strip().upper()
    symbol, exchange = (text.split(".", 1) + [""])[:2] if "." in text else (text, "")
    symbol = symbol.zfill(6)
    if exchange == "BJ" or symbol.startswith(("43", "83", "87", "92")):
        return "beijing", -29.0
    if exchange == "SH" and symbol.startswith("688"):
        return "star", -19.0
    if exchange == "SZ" and symbol.startswith(("300", "301", "302")):
        return "chinext", -19.0
    return "main_board", -9.5


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
