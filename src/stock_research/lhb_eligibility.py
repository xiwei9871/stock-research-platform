from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import math
import re
from typing import Any

from stock_research.tradeability import classify_board, resolve_limit_rule


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


@dataclass(frozen=True)
class EligibilityDecision:
    eligibility_status: str
    top5_eligible: bool
    backtest_entry_eligible: bool
    buy_signal_status: str
    reason_codes: tuple[str, ...]
    reason_texts: tuple[str, ...]
    warning_codes: tuple[str, ...]
    price_limit_regime: str
    near_limit_down_threshold: float | None
    data_quality_status: str
    contract_version: str = LHB_ELIGIBILITY_CONTRACT_VERSION


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
    del current_name, list_date
    is_st, status_source = _resolve_point_in_time_st(
        same_day_name=same_day_name,
        stored_is_st=stored_is_st,
        stored_status_quality=stored_status_quality,
    )
    listing_age = _optional_int(listing_age_trading_days)
    regime, threshold = _regime_and_threshold(
        ts_code=ts_code,
        is_st=is_st,
        trade_date=trade_date,
        listing_age_trading_days=listing_age,
    )

    change = _optional_float(pct_chg)
    if change is None:
        quality = "pct_chg_missing"
    elif is_st is None:
        quality = "st_status_unknown"
    elif regime == "rule_unknown":
        quality = "rule_unknown"
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


def evaluate_lhb_eligibility(
    *,
    trade_date: str,
    ts_code: str,
    lhb_reason: object,
    price_limit_state: PriceLimitState,
    pump_risk: object,
    high_to_close_drawdown: object,
    institution_net_buy: object,
    security_state: object = None,
) -> EligibilityDecision:
    del trade_date, ts_code
    warnings: list[str] = []
    if price_limit_state.is_st is True:
        warnings.append("st_high_risk")
    if _optional_float(institution_net_buy) is None:
        warnings.append("institution_activity_unknown")

    reason = str(lhb_reason or "")
    if _contains_delisting_marker(reason) or _contains_delisting_marker(security_state):
        return _decision(
            status="hard_reject",
            reason_code="delisting_period",
            reason_text="证券处于退市整理阶段",
            warnings=warnings,
            price_limit_state=price_limit_state,
        )
    if price_limit_state.data_quality_status != "complete":
        return _decision(
            status="risk_watch",
            reason_code=price_limit_state.data_quality_status,
            reason_text="涨跌停制度或涨跌幅数据不完整",
            warnings=warnings,
            price_limit_state=price_limit_state,
        )
    if price_limit_state.regime == "listing_no_limit":
        return _decision(
            status="risk_watch",
            reason_code="listing_no_limit_regime",
            reason_text="上市初期无普通涨跌幅限制",
            warnings=warnings,
            price_limit_state=price_limit_state,
        )
    if price_limit_state.near_limit_down:
        return _decision(
            status="risk_watch",
            reason_code="near_limit_down_followthrough_risk",
            reason_text="接近跌停，禁止进入跟随和回测交易",
            warnings=warnings,
            price_limit_state=price_limit_state,
        )

    pump = _optional_float(pump_risk)
    if pump is None:
        return _decision(
            status="risk_watch",
            reason_code="pump_risk_missing",
            reason_text="一日游风险数据缺失",
            warnings=warnings,
            price_limit_state=price_limit_state,
            data_quality_status="pump_risk_missing",
        )
    if pump >= PUMP_REJECT_THRESHOLD:
        return _decision(
            status="hard_reject",
            reason_code="extreme_one_day_pump_risk",
            reason_text="一日游风险达到硬拒绝阈值",
            warnings=warnings,
            price_limit_state=price_limit_state,
        )
    if pump >= PUMP_WARNING_THRESHOLD:
        warnings.append("high_elasticity_pump_risk")

    drawdown = _optional_float(high_to_close_drawdown)
    if drawdown is not None and drawdown >= LARGE_DRAWDOWN_WARNING_THRESHOLD:
        warnings.append("large_high_to_close_drawdown")
    return EligibilityDecision(
        eligibility_status="eligible",
        top5_eligible=True,
        backtest_entry_eligible=True,
        buy_signal_status="tradable",
        reason_codes=(),
        reason_texts=(),
        warning_codes=tuple(warnings),
        price_limit_regime=price_limit_state.regime,
        near_limit_down_threshold=price_limit_state.near_limit_down_threshold,
        data_quality_status=price_limit_state.data_quality_status,
    )


def _contains_delisting_marker(value: object) -> bool:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return any(
        marker in text
        for marker in (
            "退市",
            "delisting",
            "delist",
            "listing_termination",
            "termination_listing",
        )
    )


def _decision(
    *,
    status: str,
    reason_code: str,
    reason_text: str,
    warnings: list[str],
    price_limit_state: PriceLimitState,
    data_quality_status: str | None = None,
) -> EligibilityDecision:
    return EligibilityDecision(
        eligibility_status=status,
        top5_eligible=False,
        backtest_entry_eligible=False,
        buy_signal_status="research_only",
        reason_codes=(reason_code,),
        reason_texts=(reason_text,),
        warning_codes=tuple(warnings),
        price_limit_regime=price_limit_state.regime,
        near_limit_down_threshold=price_limit_state.near_limit_down_threshold,
        data_quality_status=data_quality_status or price_limit_state.data_quality_status,
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


def _regime_and_threshold(
    *,
    ts_code: str,
    is_st: bool | None,
    trade_date: object = None,
    listing_age_trading_days: int | None = None,
) -> tuple[str, float | None]:
    """Near-limit-down regime via the shared P1d.1 historical rule engine.

    Previously this returned static board thresholds (-4.8/-9.5/-19/-29) with
    trade_date discarded, which mis-stated ChiNext pre-2020-08-24 (should be
    10% normal / 5% ST), ChiNext+STAR ST under the 20% regime, pre-reform
    main IPO days 2-5 (10%-limited, not no-limit), and gave rule_unknown
    cases a fabricated threshold. The rule engine is now the single source
    of truth; the returned near-limit margin preserves the prior semantics
    (~0.2pt under a 5% bound, ~0.5pt under 10%, ~1pt under 20-30%).
    """
    text = str(ts_code or "").strip().upper()
    symbol, exchange = (text.split(".", 1) + [""])[:2] if "." in text else (text, "")
    symbol = symbol.zfill(6)
    is_star = exchange == "SH" and symbol.startswith("688")
    is_chinext = exchange == "SZ" and symbol.startswith(("300", "301", "302"))
    is_beijing = exchange == "BJ" or symbol.startswith(("43", "83", "87", "92"))
    board = classify_board(
        symbol=symbol, exchange=exchange, is_star=is_star,
        is_chinext=is_chinext, is_beijing=is_beijing, board=None,
    )
    date_obj = None
    if trade_date:
        try:
            date_obj = dt.date.fromisoformat(str(trade_date)[:10])
        except ValueError:
            date_obj = None
    if date_obj is None:
        return "rule_unknown", None
    event = ("ipo" if listing_age_trading_days is not None
             and listing_age_trading_days <= 10 else "continuous")
    rule = resolve_limit_rule(
        board=board,
        exchange=exchange,
        status_class="risk_warning" if is_st is True else "normal",
        event_class=event,
        trade_date=date_obj,
        listing_age_trading_days=listing_age_trading_days,
    )
    if rule.rule_id == "rule_unknown" or not rule.verified:
        return "rule_unknown", None
    if (rule.no_limit_window_days and event in {"ipo", "relisting"}
            and listing_age_trading_days is not None
            and 1 <= listing_age_trading_days <= rule.no_limit_window_days):
        return "listing_no_limit", None
    down_pct = rule.down_limit_pct
    if (listing_age_trading_days == 1
            and rule.day1_down_pct is not None):
        down_pct = rule.day1_down_pct
    if down_pct is None:
        return "rule_unknown", None
    margin = 0.2 if down_pct <= 5 else (0.5 if down_pct <= 10 else 1.0)
    if is_st is True:
        return "st", -(down_pct - margin)
    if is_beijing:
        return "beijing", -(down_pct - margin)
    if is_star:
        return "star", -(down_pct - margin)
    if is_chinext:
        return "chinext", -(down_pct - margin)
    return "main_board", -(down_pct - margin)


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
