from __future__ import annotations


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
    if sector_row is not None and int(sector_row.get("strength_rank", 0) or 0) >= 15:
        risks.append("sector_weakness")
    return sorted(set(risks))
