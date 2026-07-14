from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

import pandas as pd


NEAR_LIMIT_DOWN_RISK_CODE = "near_limit_down_followthrough_risk"


@dataclass(frozen=True)
class PriceLimitDecision:
    regime: str
    threshold: float
    near_limit_down: bool
    data_status: str


def is_valid_stock_name(value: object, *, asset_id: str = "") -> bool:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return False
    return text != str(asset_id or "").strip()


def classify_price_limit(
    *,
    asset_id: str,
    stock_name: object,
    pct_chg: object,
) -> PriceLimitDecision:
    regime, threshold = _price_limit_regime(asset_id=asset_id, stock_name=stock_name)
    change = _optional_float(pct_chg)
    if change is None:
        return PriceLimitDecision(
            regime=regime,
            threshold=threshold,
            near_limit_down=False,
            data_status="pct_chg_missing",
        )
    return PriceLimitDecision(
        regime=regime,
        threshold=threshold,
        near_limit_down=change <= threshold,
        data_status="complete",
    )


def apply_lhb_top5_gate(frame: pd.DataFrame, *, top_n: int = 5) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy()

    result = frame.copy()
    result["score_total"] = pd.to_numeric(result.get("score_total"), errors="coerce")
    result["raw_score"] = result["score_total"]
    result["asset_id"] = result.get("asset_id", "").fillna("").astype(str)
    if "stock_name" not in result.columns:
        result["stock_name"] = ""
    if "pct_chg" not in result.columns:
        result["pct_chg"] = pd.NA

    decisions = [
        classify_price_limit(
            asset_id=str(row.get("asset_id") or ""),
            stock_name=row.get("stock_name"),
            pct_chg=row.get("pct_chg"),
        )
        for row in result.to_dict("records")
    ]
    result["top5_eligible"] = [not decision.near_limit_down for decision in decisions]
    result["risk_gate_code"] = [
        NEAR_LIMIT_DOWN_RISK_CODE if decision.near_limit_down else "" for decision in decisions
    ]
    result["risk_gate_reason"] = [
        _risk_gate_reason(decision=decision, pct_chg=pct_chg)
        for decision, pct_chg in zip(decisions, result["pct_chg"], strict=True)
    ]
    result["price_limit_regime"] = [decision.regime for decision in decisions]
    result["near_limit_down_threshold"] = [decision.threshold for decision in decisions]

    result = result.sort_values(
        ["score_total", "asset_id"],
        ascending=[False, True],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    result["source_rank"] = range(1, len(result) + 1)

    eligible_rank = 0
    ranks: list[int] = []
    tiers: list[str] = []
    for row in result.to_dict("records"):
        if bool(row["top5_eligible"]):
            eligible_rank += 1
            ranks.append(eligible_rank)
            tiers.append("top5_focus" if eligible_rank <= top_n else "watch")
        else:
            ranks.append(int(row["source_rank"]))
            tiers.append("risk_watch")
    result["rank"] = ranks
    result["review_tier"] = tiers
    return result


def _price_limit_regime(*, asset_id: str, stock_name: object) -> tuple[str, float]:
    name = str(stock_name or "").strip().upper()
    if re.match(r"^(?:\*?ST|S\*ST)", name):
        return "st", -4.8

    symbol, exchange = _symbol_and_exchange(asset_id)
    if exchange == "BJ" or symbol.startswith(("43", "83", "87", "92")):
        return "beijing", -29.0
    if exchange == "SH" and symbol.startswith("688"):
        return "star", -19.0
    if exchange == "SZ" and symbol.startswith(("300", "301", "302")):
        return "chinext", -19.0
    return "main_board", -9.5


def _symbol_and_exchange(asset_id: str) -> tuple[str, str]:
    text = str(asset_id or "").strip().upper()
    if text.startswith("CN:"):
        parts = text.split(":")
        if len(parts) >= 3:
            return parts[-1].zfill(6), parts[-2]
    if "." in text:
        symbol, exchange = text.split(".", 1)
        return symbol.zfill(6), exchange
    return text.zfill(6), ""


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _risk_gate_reason(*, decision: PriceLimitDecision, pct_chg: object) -> str:
    if decision.data_status == "pct_chg_missing":
        return "pct_chg_missing"
    if not decision.near_limit_down:
        return ""
    change = _optional_float(pct_chg)
    return (
        f"当日涨跌幅 {change:.2f}% 触及 {decision.regime} "
        f"接近跌停阈值 {decision.threshold:.2f}%"
    )
