from __future__ import annotations

from decimal import Decimal
from numbers import Integral, Real
from typing import Any


def classify_watchlist_risks(
    *,
    feature_values: dict[str, float],
    market_state: dict[str, object],
    sector_row: dict[str, object] | None,
) -> list[str]:
    risks: list[str] = []
    if market_state.get("entry_allowed") is False:
        risks.append("risk_excluded")
    if float(feature_values.get("ret_5d", 0.0) or 0.0) >= 0.15:
        risks.append("overheat")
    if float(feature_values.get("max_drawdown_20d", 0.0) or 0.0) <= -0.15:
        risks.append("risk_excluded")
    if _is_sector_weak(sector_row):
        risks.append("sector_weakness")
    return sorted(set(risks))


def _is_sector_weak(sector_row: dict[str, object] | None) -> bool:
    if sector_row is None:
        return False

    strength_rank = _coerce_int(sector_row.get("strength_rank"))
    sector_strength_count = _coerce_int(
        sector_row.get("sector_strength_count")
        or sector_row.get("sector_count")
        or sector_row.get("total_sectors")
    )
    if strength_rank is None or sector_strength_count is None or sector_strength_count <= 0:
        return False
    return strength_rank > (sector_strength_count / 2.0)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, Real):
        return int(value)
    try:
        if value != value:
            return None
    except Exception:
        pass
    try:
        return int(value)
    except Exception:
        return None
