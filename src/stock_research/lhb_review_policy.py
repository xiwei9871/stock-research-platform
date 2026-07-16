from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

import pandas as pd

from stock_research.lhb_eligibility import (
    LHB_ELIGIBILITY_CONTRACT_VERSION,
    evaluate_lhb_eligibility,
    resolve_price_limit_state,
)


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
    provided_rank = pd.to_numeric(
        result.get("source_rank", result.get("rank", pd.Series(pd.NA, index=result.index))),
        errors="coerce",
    )
    result["_provided_rank"] = provided_rank
    if "stock_name" not in result.columns:
        result["stock_name"] = ""
    if "pct_chg" not in result.columns:
        result["pct_chg"] = pd.NA

    decision_rows = [_lhb_review_contract_fields(row) for row in result.to_dict("records")]
    for column in [
        "eligibility_status",
        "top5_eligible",
        "backtest_entry_eligible",
        "buy_signal_status",
        "eligibility_reason_codes",
        "eligibility_reason_texts",
        "eligibility_warning_codes",
        "eligibility_contract_version",
        "price_limit_regime",
        "near_limit_down_threshold",
        "data_quality_status",
        "risk_gate_code",
        "risk_gate_reason",
    ]:
        result[column] = [decision[column] for decision in decision_rows]

    result = result.sort_values(
        ["score_total", "asset_id"],
        ascending=[False, True],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    provided_rank = pd.to_numeric(result.pop("_provided_rank"), errors="coerce")
    fallback_rank = pd.Series(range(1, len(result) + 1), index=result.index, dtype="int64")
    result["source_rank"] = provided_rank.fillna(fallback_rank).astype(int)

    ranks: list[int] = []
    tiers: list[str] = []
    for row in result.to_dict("records"):
        original_rank = int(row["source_rank"])
        ranks.append(original_rank)
        if bool(row["top5_eligible"]):
            tiers.append("top5_focus" if original_rank <= top_n else "watch")
        else:
            tiers.append("risk_watch")
    result["rank"] = ranks
    result["review_tier"] = tiers
    return result


def _lhb_review_contract_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw_version = row.get("eligibility_contract_version")
    version = "" if pd.isna(raw_version) else str(raw_version or "").strip()
    if version:
        if version != LHB_ELIGIBILITY_CONTRACT_VERSION:
            raise ValueError("LHB eligibility parity violation: unsupported contract version")
        status = str(row.get("eligibility_status") or "").strip()
        top5 = _optional_bool(row.get("top5_eligible"))
        entry = _optional_bool(row.get("backtest_entry_eligible"))
        expected = status == "eligible"
        if status not in {"eligible", "risk_watch", "hard_reject"} or top5 is None or entry is None:
            raise ValueError("LHB eligibility parity violation: incomplete upstream decision")
        if top5 is not expected or entry is not expected:
            raise ValueError("LHB eligibility parity violation: contradictory upstream decision")
        reason_codes = _list_value(row.get("eligibility_reason_codes"))
        reason_texts = _list_value(row.get("eligibility_reason_texts"))
        warning_codes = _list_value(row.get("eligibility_warning_codes"))
        return {
            "eligibility_status": status,
            "top5_eligible": top5,
            "backtest_entry_eligible": entry,
            "buy_signal_status": row.get("buy_signal_status") or ("tradable" if entry else "research_only"),
            "eligibility_reason_codes": reason_codes,
            "eligibility_reason_texts": reason_texts,
            "eligibility_warning_codes": warning_codes,
            "eligibility_contract_version": version,
            "price_limit_regime": row.get("price_limit_regime") or "",
            "near_limit_down_threshold": row.get("near_limit_down_threshold"),
            "data_quality_status": row.get("data_quality_status") or "",
            "risk_gate_code": reason_codes[0] if reason_codes else "",
            "risk_gate_reason": reason_texts[0] if reason_texts else "",
        }

    asset_id = str(row.get("asset_id") or "")
    state = resolve_price_limit_state(
        trade_date=str(row.get("trade_date") or ""),
        ts_code=_contract_ts_code(asset_id),
        same_day_name=row.get("stock_name"),
        current_name=None,
        pct_chg=row.get("pct_chg"),
        stored_is_st=False,
        stored_status_quality="trusted",
        list_date=None,
    )
    decision = evaluate_lhb_eligibility(
        trade_date=str(row.get("trade_date") or ""),
        ts_code=_contract_ts_code(asset_id),
        lhb_reason=row.get("lhb_reason"),
        price_limit_state=state,
        pump_risk=row.get("lhb_one_day_pump_risk", 0.0),
        high_to_close_drawdown=row.get("high_to_close_drawdown", 0.0),
        institution_net_buy=row.get("institution_net_buy", 0.0),
        security_state=row.get("stock_name"),
    )
    return {
        "eligibility_status": decision.eligibility_status,
        "top5_eligible": decision.top5_eligible,
        "backtest_entry_eligible": decision.backtest_entry_eligible,
        "buy_signal_status": decision.buy_signal_status,
        "eligibility_reason_codes": list(decision.reason_codes),
        "eligibility_reason_texts": list(decision.reason_texts),
        "eligibility_warning_codes": list(decision.warning_codes),
        "eligibility_contract_version": decision.contract_version,
        "price_limit_regime": decision.price_limit_regime,
        "near_limit_down_threshold": decision.near_limit_down_threshold,
        "data_quality_status": decision.data_quality_status,
        "risk_gate_code": decision.reason_codes[0] if decision.reason_codes else "",
        "risk_gate_reason": decision.reason_texts[0] if decision.reason_texts else "",
    }


def _contract_ts_code(asset_id: str) -> str:
    symbol, exchange = _symbol_and_exchange(asset_id)
    return f"{symbol}.{exchange}" if exchange else symbol


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _list_value(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        import json

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return [text]


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
