"""DATA-R3-P1d.1: point-in-time tradeability qualification (read-only gate).

v2 contract — fixes found in the P1d audit:

- Real historical rule matrix (P0-A): board × status_class × listing-event ×
  effective-dated rows, sourced to exchange documents (see
  docs/research_upgrade/p1d1/HISTORICAL_RULE_MATRIX.csv). ChiNext pre-2020-08-24
  risk-warning stocks were ±5% (深证上〔2020〕620号), post-reform 20%; ChiNext
  stocks that entered their delisting-arrangement period before the reform and
  were still inside it keep the old ±10% arrangement rules; pre-registration
  main-board/ChiNext IPO day-1 had a dedicated +44%/-36% cap (not the ordinary
  10% rule); full-registration main-board IPOs get a 5-session no-limit window
  from 2023-04-10. Unknown/special cases resolve to ``rule_unknown`` — never to
  a silently-tradable default.
- Real listing-session index (P0-B): ``listing_age_trading_days`` is computed
  from market.trading_calendar open days between list_date and trade_date,
  not calendar-day arithmetic. Missing list_date / calendar coverage makes the
  no-limit-window verdict UNKNOWN, which is fail-closed.
- Fail-closed semantics (P0-C): universe eligibility and per-side attemptability
  use tri-state enums (ELIGIBLE/INELIGIBLE/UNKNOWN and
  ATTEMPTABLE/RESTRICTED/UNKNOWN). Legacy boolean mirrors are kept
  (``eligible_for_universe`` maps UNKNOWN -> None) but nothing unknown is
  treated as tradable.
- Legal limit price (P0-D): limit-lock is detected against the *legal* limit
  price recomputed from the raw (unadjusted) preclose and the effective rule,
  with exchange rounding to the 0.01 tick. Close-at-limit, touched-intraday,
  one-way-locked (一字) and no-limit-regime are distinct classifications.
  ``order_time`` restricts which fields may be used: 'open' decisions may only
  use facts knowable at the open (preclose-derived legal limit, open print,
  status); close/intraday marks of the same day are future data there.
- Minute qualification (P0-E): data_ready_minute is bound to the actual
  R2/P1c data chain (done-ledger keys per source, residual FACTOR_GAP list,
  rebuild state, POST_DIFF isolation) via an injectable provider — never to a
  bare row count, and never released by a features pin.

Still strictly read-only: no writes, no changes to production fill logic.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .backtest_constraints import BacktestExecutionConstraints, can_close_long, can_open_long

TRADEABILITY_CONTRACT_VERSION = "tradeability_pit_v2"

PRICE_LIMIT_INTRODUCED = dt.date(1996, 12, 16)  # A-share ±10% regime starts
ST_REGIME_INTRODUCED = dt.date(1998, 4, 22)     # ST risk-warning regime
MAIN_IPO_DAY1_CAP_START = dt.date(2014, 1, 17)  # 新股首日 +44%/-36% 申报上限 era
FULL_REGISTRATION_DATE = dt.date(2023, 4, 10)  # 主板全面注册制
CHINEXT_REFORM_DATE = dt.date(2020, 8, 24)     # 创业板交易特别规定施行
STAR_MARKET_OPEN = dt.date(2019, 7, 22)
BSE_MARKET_OPEN = dt.date(2021, 11, 15)

TICK_SIZE = 0.01


class StatusClass(str, Enum):
    NORMAL = "normal"
    RISK_WARNING = "risk_warning"          # ST / *ST
    DELISTING_ARRANGEMENT = "delisting_arrangement"  # 退市整理期
    UNKNOWN = "unknown"


class ListingEvent(str, Enum):
    CONTINUOUS = "continuous"   # ordinary session (no listing event at/near date)
    IPO = "ipo"                 # first public listing
    RELISTING = "relisting"     # 重新上市 after delisting/suspension
    UNKNOWN = "unknown"


class Eligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class Attemptability(str, Enum):
    ATTEMPTABLE = "ATTEMPTABLE"
    RESTRICTED = "RESTRICTED"
    UNKNOWN = "UNKNOWN"


class LimitClass(str, Enum):
    CLOSE_AT_LIMIT = "CLOSE_AT_LIMIT"
    ONE_WAY_LOCKED = "ONE_WAY_LOCKED"            # 一字涨/跌停 all session
    TOUCHED_INTRADAY_ONLY = "TOUCHED_INTRADAY_ONLY"
    NOT_LIMIT = "NOT_LIMIT"
    NOT_LIMIT_UNVERIFIED = "NOT_LIMIT_UNVERIFIED"  # pct far from limit, raw price absent
    PCT_NEAR_LIMIT_UNVERIFIED = "PCT_NEAR_LIMIT_UNVERIFIED"  # pct near limit, no legal-price proof
    NO_LIMIT_REGIME = "NO_LIMIT_REGIME"          # inside no-limit window
    RULE_UNKNOWN = "RULE_UNKNOWN"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class OrderTime(str, Enum):
    OPEN = "open"          # order placed at/around the open auction
    CLOSE = "close"        # order placed at/after close knowledge (next-day fill)
    UNKNOWN = "unknown"    # cannot prove when in the day the order exists


# ---------------------------------------------------------------------------
# Rule matrix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LimitRule:
    rule_id: str
    exchange: str            # SH | SZ | BJ | ANY
    board: str               # main | chinext | star | beijing | any
    status_class: str        # StatusClass value
    event_class: str         # ListingEvent value ('any' allowed)
    effective_from: dt.date | None
    effective_to: dt.date | None
    up_limit_pct: float | None
    down_limit_pct: float | None
    no_limit_window_days: int = 0
    day1_up_pct: float | None = None     # dedicated day-1 cap if any
    day1_down_pct: float | None = None
    source_doc: str = ""
    doc_number: str = ""
    verified: bool = True                # False -> RULE_UNKNOWN surfacing

    def covers(self, trade_date: dt.date) -> bool:
        if self.effective_from and trade_date < self.effective_from:
            return False
        if self.effective_to and trade_date > self.effective_to:
            return False
        return True


ANY = "any"

# Full matrix lives in docs/research_upgrade/p1d1/HISTORICAL_RULE_MATRIX.csv;
# ids must stay aligned with that file.
LIMIT_RULES: tuple[LimitRule, ...] = (
    # --- pre-limit era (all boards) ---
    LimitRule("pre_19961216_no_limit", ANY, ANY, "normal", "any",
              None, dt.date(1996, 12, 13), None, None,
              source_doc="1996-12-16 起 A 股恢复 ±10% 涨跌幅，此前无涨跌幅限制",
              doc_number="交易所交易规则沿革"),
    # --- main board ---
    LimitRule("main_10pct", ANY, "main", "normal", "any",
              PRICE_LIMIT_INTRODUCED, None, 10.0, 10.0,
              source_doc="上交所/深交所交易规则 主板 ±10%",
              doc_number="交易规则"),
    LimitRule("main_st_5pct", ANY, "main", "risk_warning", "any",
              ST_REGIME_INTRODUCED, None, 5.0, 5.0,
              source_doc="沪深交易所风险警示板 ST/*ST ±5%",
              doc_number="交易规则/风险警示板安排"),
    LimitRule("main_delisting_arrangement_10pct", ANY, "main", "delisting_arrangement", "any",
              None, None, 10.0, 10.0,
              source_doc="退市整理期交易机制 ±10%",
              doc_number="交易所退市整理期安排", verified=True),
    LimitRule("main_ipo_day1_prereg_cap", ANY, "main", "normal", "ipo",
              MAIN_IPO_DAY1_CAP_START, dt.date(2023, 4, 7), 10.0, 10.0,
              day1_up_pct=44.0, day1_down_pct=36.0,
              source_doc="主板新股首日有效申报价格上限+44%/下限-36%(2014-01 起)",
              doc_number="交易所新股上市首日交易机制"),
    LimitRule("main_ipo_fullreg_window5", ANY, "main", "normal", "ipo",
              FULL_REGISTRATION_DATE, None, 10.0, 10.0,
              no_limit_window_days=5,
              source_doc="全面注册制:主板新股上市前5个交易日不设涨跌幅",
              doc_number="沪深主板注册制交易规则 2023-04-10"),
    LimitRule("main_relisting_day1_no_limit", ANY, "main", "normal", "relisting",
              None, None, 10.0, 10.0,
              no_limit_window_days=1,
              source_doc="退市公司重新上市实施办法:重新上市首日不设涨跌幅",
              doc_number="上交所/深交所重新上市实施办法"),
    # --- ChiNext ---
    LimitRule("chinext_10pct_pre_20200824", "SZ", "chinext", "normal", "any",
              None, dt.date(2020, 8, 21), 10.0, 10.0,
              source_doc="注册制前创业板适用 ±10%",
              doc_number="深交所交易规则(注册制前)"),
    LimitRule("chinext_ipo_day1_prereg_cap", "SZ", "chinext", "normal", "ipo",
              MAIN_IPO_DAY1_CAP_START, dt.date(2020, 8, 21), 10.0, 10.0,
              day1_up_pct=44.0, day1_down_pct=36.0,
              source_doc="创业板注册制前新股首日上限+44%/-36%",
              doc_number="深交所新股上市首日交易机制"),
    LimitRule("chinext_st_5pct_pre_20200824", "SZ", "chinext", "risk_warning", "any",
              None, dt.date(2020, 8, 21), 5.0, 5.0,
              source_doc="创业板风险警示股票改革前适用交易规则3.3.15 ±5%",
              doc_number="深证上〔2020〕620号 第一条"),
    LimitRule("chinext_20pct_from_20200824", "SZ", "chinext", "normal", "any",
              CHINEXT_REFORM_DATE, None, 20.0, 20.0,
              source_doc="创业板交易特别规定2.1:竞价交易涨跌幅20%",
              doc_number="深证上〔2020〕515号"),
    LimitRule("chinext_ipo_window5_from_20200824", "SZ", "chinext", "normal", "ipo",
              CHINEXT_REFORM_DATE, None, 20.0, 20.0,
              no_limit_window_days=5,
              source_doc="创业板交易特别规定2.1:IPO前5个交易日不设涨跌幅",
              doc_number="深证上〔2020〕515号"),
    LimitRule("chinext_st_20pct_from_20200824", "SZ", "chinext", "risk_warning", "any",
              CHINEXT_REFORM_DATE, None, 20.0, 20.0,
              source_doc="创业板风险警示股票改革后适用20%",
              doc_number="深证上〔2020〕620号 第二条"),
    # ChiNext delisting-arrangement transition (620号 第一条):
    # entered arrangement BEFORE the reform and still inside at 2020-08-24 ->
    # keep old 交易规则 ±10% for the whole arrangement; entered after -> 20%.
    # Resolution needs the arrangement entry date; the resolver receives it
    # via context (`delisting_arrangement_entered`) and picks between:
    LimitRule("chinext_delist_arr_pre_reform_10pct", "SZ", "chinext", "delisting_arrangement", "any",
              None, None, 10.0, 10.0,
              source_doc="改革实施前已进入且实施时仍处退市整理期:维持±10%",
              doc_number="深证上〔2020〕620号 第一条"),
    LimitRule("chinext_delist_arr_post_reform_20pct", "SZ", "chinext", "delisting_arrangement", "any",
              None, None, 20.0, 20.0,
              source_doc="改革实施后进入退市整理期:适用20%",
              doc_number="深证上〔2020〕620号 第二条"),
    # --- STAR ---
    LimitRule("star_20pct_since_20190722", "SH", "star", "normal", "any",
              STAR_MARKET_OPEN, None, 20.0, 20.0,
              source_doc="科创板交易特别规定第十八条:±20%",
              doc_number="上证发〔2019〕23号"),
    LimitRule("star_ipo_window5", "SH", "star", "normal", "ipo",
              STAR_MARKET_OPEN, None, 20.0, 20.0,
              no_limit_window_days=5,
              source_doc="科创板交易特别规定:IPO前5个交易日不设涨跌幅",
              doc_number="上证发〔2019〕23号"),
    LimitRule("star_st_20pct", "SH", "star", "risk_warning", "any",
              STAR_MARKET_OPEN, None, 20.0, 20.0,
              source_doc="科创板风险警示股票适用板块 ±20%",
              doc_number="科创板交易特别规定"),
    LimitRule("star_delist_arr_20pct", "SH", "star", "delisting_arrangement", "any",
              STAR_MARKET_OPEN, None, 20.0, 20.0,
              source_doc="科创板退市整理期适用板块 ±20%",
              doc_number="科创板交易特别规定"),
    # --- BSE ---
    LimitRule("beijing_30pct_since_20211115", "BJ", "beijing", "normal", "any",
              BSE_MARKET_OPEN, None, 30.0, 30.0,
              source_doc="北交所交易规则(试行):±30%",
              doc_number="北证公告〔2021〕"),
    LimitRule("beijing_ipo_day1_no_limit", "BJ", "beijing", "normal", "ipo",
              BSE_MARKET_OPEN, None, 30.0, 30.0,
              no_limit_window_days=1,
              source_doc="北交所新股上市首日不设涨跌幅",
              doc_number="北交所交易规则(试行)"),
    LimitRule("beijing_st_30pct", "BJ", "beijing", "risk_warning", "any",
              BSE_MARKET_OPEN, None, 30.0, 30.0,
              source_doc="北交所风险警示股票适用板块 ±30%",
              doc_number="北交所交易规则(试行)", verified=False),
)

RULE_UNKNOWN = LimitRule(
    "rule_unknown", ANY, ANY, "unknown", "any", None, None, None, None,
    source_doc="no verified rule for this board/status/date combination",
    doc_number="", verified=False,
)


def classify_board(*, symbol: str, exchange: str, is_star: bool, is_chinext: bool,
                   is_beijing: bool, board: str | None) -> str:
    """Same board taxonomy as lhb_eligibility / asset_master flags."""
    if is_beijing or exchange == "BJ" or (board or "").lower() == "beijing":
        return "beijing"
    if is_star or (board or "").lower() == "star":
        return "star"
    if is_chinext or (board or "").lower() == "chinext":
        return "chinext"
    return "main"


def _rule_matches(rule: LimitRule, *, exchange: str, board: str,
                  status_class: str, event_class: str, trade_date: dt.date) -> bool:
    if exchange and rule.exchange not in {ANY, exchange}:
        return False
    if rule.board not in {ANY, board}:
        return False
    if rule.status_class != status_class:
        return False
    if rule.event_class not in {ANY, "any", event_class}:
        return False
    return rule.covers(trade_date)


def resolve_limit_rule(
    *,
    board: str | None = None,
    is_st: bool | None = None,
    trade_date: dt.date,
    exchange: str = "",
    status_class: str | None = None,
    event_class: str = "continuous",
    delisting_arrangement_entered: dt.date | None = None,
    listing_age_trading_days: int | None = None,
    # legacy compat: callers may pass is_st/board only
) -> LimitRule:
    """Effective-rule resolution (P0-A). Never invents a threshold."""
    if status_class is None:
        status_class = StatusClass.RISK_WARNING.value if is_st else StatusClass.NORMAL.value
    if board is None:
        board = "main"

    candidates = [r for r in LIMIT_RULES if _rule_matches(
        r, exchange=exchange, board=board, status_class=status_class,
        event_class=event_class, trade_date=trade_date)]

    # ChiNext delisting-arrangement transition: pick by entry date.
    if status_class == StatusClass.DELISTING_ARRANGEMENT.value and board == "chinext":
        if delisting_arrangement_entered is None:
            return RULE_UNKNOWN
        if delisting_arrangement_entered < CHINEXT_REFORM_DATE:
            candidates = [r for r in candidates
                          if r.rule_id == "chinext_delist_arr_pre_reform_10pct"]
        else:
            candidates = [r for r in candidates
                          if r.rule_id == "chinext_delist_arr_post_reform_20pct"]

    if not candidates:
        return RULE_UNKNOWN
    # Most-specific wins: an event-specific rule (ipo/relisting) beats the
    # generic 'any'-event row for the same board/status/date.
    candidates.sort(key=lambda r: 0 if r.event_class not in {ANY, "any"} else 1)
    rule = candidates[0]
    # An event rule whose only distinction is a no-limit window stops applying
    # once the known session index exceeds that window — fall back to the
    # ordinary continuous rule (e.g. BJ day-2, IPO window was day-1 only).
    if (
        rule.event_class not in {ANY, "any"}
        and rule.no_limit_window_days > 0
        and listing_age_trading_days is not None
        and listing_age_trading_days > rule.no_limit_window_days
        and rule.day1_up_pct is None
    ):
        fallback = [r for r in candidates if r.event_class in {ANY, "any"}]
        if fallback:
            rule = fallback[0]
    if not rule.verified:
        return RULE_UNKNOWN
    return rule


# ---------------------------------------------------------------------------
# Context / result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionPolicy:
    """Configurable conservative execution assumptions (P0-3/P0-D)."""

    block_limit_up_buy: bool = True
    block_limit_down_sell: bool = True
    block_suspended: bool = True
    assume_limit_locked_unfillable: bool = True
    min_amount: float | None = None
    # When order_time is 'open'/'unknown', an order is restricted whenever the
    # day ENDS at a one-way lock the order could not reasonably have escaped —
    # conservative, since queue position is unprovable either way.
    restrict_when_session_locked: bool = True


DEFAULT_POLICY = ExecutionPolicy()


@dataclass(frozen=True)
class TradeabilityContext:
    """Point-in-time inputs for one (asset, trade_date). Pure data — no IO."""

    asset_id: str
    trade_date: dt.date
    # master / lifecycle
    list_date: dt.date | None = None
    delist_date: dt.date | None = None
    listing_event: str = "continuous"          # ipo | relisting | continuous
    delisting_arrangement_entered: dt.date | None = None
    status_class_override: str | None = None   # explicit override wins
    symbol: str = ""
    exchange: str = ""
    board: str | None = None
    is_star: bool = False
    is_chinext: bool = False
    is_beijing: bool = False
    # calendar
    exchange_open: bool | None = None
    listing_age_trading_days: int | None = None  # real session index (P0-B)
    listing_age_known: bool = False
    # per-day status (core.asset_status_daily)
    status_present: bool = False
    is_trade: bool | None = None
    is_st: bool | None = None
    is_suspended: bool | None = None
    stored_is_limit_up: bool | None = None
    stored_is_limit_down: bool | None = None
    stored_limit_up_price: float | None = None
    stored_limit_down_price: float | None = None
    status_source: str = "absent"
    # raw-bar facts (unadjusted prices are required for legal-limit math)
    bar_present: bool = False
    open_raw: float | None = None
    high_raw: float | None = None
    low_raw: float | None = None
    close_raw: float | None = None
    preclose_raw: float | None = None
    pct_chg: float | None = None
    amount: float | None = None
    trade_status: str | None = None
    # data readiness
    daily_bar_rows: int = 0
    minute_bar_rows: int = 0
    minute_qualified: bool | None = None       # P0-E provider verdict
    minute_qualified_sources: tuple[str, ...] = ()
    minute_version: str | None = None
    # P1d.2a C: None = no date binding asked; True = date_verified;
    # False = key-level done but the DATE could not be proven.
    minute_date_verified: bool | None = None
    minute_provider_configured: bool = False   # fail-closed selector
    minute_required_source: str | None = None
    data_quality_blocks: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeabilityResult:
    asset_id: str
    trade_date: str
    side: str
    data_version: str
    order_time: str
    # dimension 1
    universe_state: str
    # dimension 2
    data_ready_daily: bool | None
    data_ready_minute: bool | None
    # dimension 3
    buy_state: str
    sell_state: str
    # compat mirrors (P1d callers)
    eligible_for_universe: bool | None
    can_attempt_buy: bool
    can_attempt_sell: bool
    restriction_reasons: tuple[str, ...]
    status_source: str
    effective_date: str | None
    rule_version: str = TRADEABILITY_CONTRACT_VERSION
    limit_regime: str = ""
    limit_rule_id: str = ""
    limit_class_up: str = ""
    limit_class_down: str = ""
    legal_limit_up_price: float | None = None
    legal_limit_down_price: float | None = None
    stored_flag_disagrees: bool = False
    status_class: str = "normal"
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Legal limit math (P0-D)
# ---------------------------------------------------------------------------


def legal_limit_price(preclose_raw: float | None, pct: float | None,
                      direction: str) -> float | None:
    """Exchange legal limit price: preclose * (1 +/- pct) rounded to the tick."""
    if preclose_raw is None or pct is None or math.isnan(preclose_raw):
        return None
    raw = preclose_raw * (1 + pct / 100.0) if direction == "up" \
        else preclose_raw * (1 - pct / 100.0)
    # exchange rounds to the 0.01 tick (round-half-even per exchange spec is
    # immaterial at cent scale vs our classification tolerances)
    return round(raw + 1e-9, 2)


def _price_at(value: float | None, target: float | None) -> bool:
    if value is None or target is None:
        return False
    return abs(value - target) <= TICK_SIZE / 2 + 1e-9


def classify_limit_day(
    *,
    open_raw: float | None,
    high_raw: float | None,
    low_raw: float | None,
    close_raw: float | None,
    legal_limit_price_value: float | None,
    pct_chg: float | None = None,
    rule_up_pct: float | None = None,
    rule_down_pct: float | None = None,
    side: str,
    no_limit_window: bool,
    rule: LimitRule,
) -> str:
    """CLOSE_AT_LIMIT / ONE_WAY_LOCKED / TOUCHED_INTRADAY_ONLY / NOT_LIMIT /
    NO_LIMIT_REGIME / RULE_UNKNOWN / DATA_INSUFFICIENT (P0-D).

    When raw prices are absent, pct_chg can still *clear* a day from limit
    (far from the bound) but can never *prove* a limit-locked close — those
    stay PCT_NEAR_LIMIT_UNVERIFIED and are treated as restricted-but-suspect.
    """
    if rule is RULE_UNKNOWN or rule.up_limit_pct is None:
        return LimitClass.RULE_UNKNOWN.value
    if no_limit_window:
        return LimitClass.NO_LIMIT_REGIME.value
    target = legal_limit_price_value
    if close_raw is None or target is None:
        if pct_chg is not None:
            bound = (rule_up_pct if rule_up_pct is not None else rule.up_limit_pct) \
                if side == "buy" else (
                    rule_down_pct if rule_down_pct is not None else rule.down_limit_pct)
            if bound is not None:
                if side == "buy" and pct_chg >= bound - 0.05:
                    return LimitClass.PCT_NEAR_LIMIT_UNVERIFIED.value
                if side == "sell" and pct_chg <= -bound + 0.05:
                    return LimitClass.PCT_NEAR_LIMIT_UNVERIFIED.value
                return LimitClass.NOT_LIMIT_UNVERIFIED.value
        return LimitClass.DATA_INSUFFICIENT.value
    if side == "buy":
        touched = _price_at(high_raw, target) if high_raw is not None else _price_at(close_raw, target)
    else:
        touched = _price_at(low_raw, target) if low_raw is not None else _price_at(close_raw, target)
    at_close = _price_at(close_raw, target)
    if at_close:
        one_way = all(
            _price_at(v, target)
            for v in (open_raw, high_raw, low_raw, close_raw)
            if v is not None
        ) and open_raw is not None and high_raw is not None and low_raw is not None
        if one_way:
            return LimitClass.ONE_WAY_LOCKED.value
        return LimitClass.CLOSE_AT_LIMIT.value
    if touched:
        return LimitClass.TOUCHED_INTRADAY_ONLY.value
    return LimitClass.NOT_LIMIT.value


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def _as_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _in_no_limit_window(ctx: TradeabilityContext, rule: LimitRule) -> bool | None:
    """Tri-state: True / False / None(cannot determine)."""
    if not rule.no_limit_window_days:
        return False
    if ctx.listing_age_known and ctx.listing_age_trading_days is not None:
        return 1 <= ctx.listing_age_trading_days <= rule.no_limit_window_days
    if ctx.listing_event == ListingEvent.IPO.value and ctx.list_date is not None \
            and ctx.trade_date == ctx.list_date:
        return True
    # age required but unknowable -> fail closed (None), not a normal-rule guess
    return None


def _status_class(ctx: TradeabilityContext) -> str:
    if ctx.status_class_override:
        return ctx.status_class_override
    if ctx.delisting_arrangement_entered is not None:
        return StatusClass.DELISTING_ARRANGEMENT.value
    if ctx.is_st is True:
        return StatusClass.RISK_WARNING.value
    if ctx.is_st is False:
        return StatusClass.NORMAL.value
    return StatusClass.NORMAL.value if ctx.status_present else StatusClass.UNKNOWN.value


def _event_class(ctx: TradeabilityContext, rule_window_hint: int = 0) -> str:
    ev = (ctx.listing_event or "continuous").lower()
    if ev in {ListingEvent.IPO.value, ListingEvent.RELISTING.value}:
        # event stays "ipo"/"relisting" only inside the early sessions; for
        # known ages beyond any possible window it's a continuous session.
        if ctx.listing_age_known and ctx.listing_age_trading_days is not None:
            return ev if ctx.listing_age_trading_days <= 5 else "continuous"
        return ev
    return "continuous"


def _eval_universe(ctx: TradeabilityContext, reasons: list[str]) -> Eligibility:
    if ctx.exchange_open is None:
        reasons.append("exchange_calendar_missing")
        cal_unknown = True
    elif ctx.exchange_open is False:
        reasons.append("exchange_closed")
        return Eligibility.INELIGIBLE
    else:
        cal_unknown = False

    if ctx.list_date is None:
        reasons.append("list_date_missing")
        return Eligibility.UNKNOWN
    if ctx.trade_date < ctx.list_date:
        reasons.append("not_yet_listed")
        return Eligibility.INELIGIBLE
    if ctx.delist_date is not None and ctx.trade_date > ctx.delist_date:
        reasons.append("delisted")
        return Eligibility.INELIGIBLE
    if cal_unknown:
        return Eligibility.UNKNOWN
    return Eligibility.ELIGIBLE


def _effective_pct(ctx: TradeabilityContext, rule: LimitRule, side: str) -> float | None:
    """Day-1 dedicated caps override the ordinary bound when applicable."""
    if ctx.listing_age_known and ctx.listing_age_trading_days == 1:
        cap = rule.day1_up_pct if side == "buy" else rule.day1_down_pct
        if cap is not None:
            return cap
    return rule.up_limit_pct if side == "buy" else rule.down_limit_pct


def _eval_side(
    ctx: TradeabilityContext,
    *,
    side: str,
    policy: ExecutionPolicy,
    order_time: OrderTime,
    rule: LimitRule,
    no_limit_window: bool | None,
    reasons: list[str],
) -> tuple[str, str, float | None]:
    """Returns (Attemptability, limit_class, legal_price_for_side)."""
    eff_pct = _effective_pct(ctx, rule, side)
    legal_price = legal_limit_price(ctx.preclose_raw, eff_pct, "up" if side == "buy" else "down")

    limit_class = classify_limit_day(
        open_raw=ctx.open_raw, high_raw=ctx.high_raw, low_raw=ctx.low_raw,
        close_raw=ctx.close_raw, legal_limit_price_value=legal_price,
        pct_chg=ctx.pct_chg,
        rule_up_pct=_effective_pct(ctx, rule, "buy"),
        rule_down_pct=_effective_pct(ctx, rule, "sell"),
        side=side, no_limit_window=(no_limit_window is True), rule=rule,
    )

    # Order-time information constraint (P0-D/A3): an 'open' order may only
    # use facts knowable AT the open — open price itself, never the day's
    # high/low/close. Reading h/l/c to reclassify here would leak future data
    # into the open-time decision. The only close-data usage allowed is the
    # explicit ex-post conservative rule below, which is labelled as such.
    ex_post_assumption = False
    if order_time is OrderTime.OPEN:
        if ctx.open_raw is not None and _price_at(ctx.open_raw, legal_price):
            # provable at the open: the order opens AT the statutory limit
            limit_class = LimitClass.CLOSE_AT_LIMIT.value
        else:
            # close/intraday marks are future data for an open order; cannot
            # prove the order was unfillable -> attemptable unless other gates
            limit_class = LimitClass.NOT_LIMIT.value
    elif order_time is OrderTime.UNKNOWN:
        if ctx.open_raw is not None and _price_at(ctx.open_raw, legal_price):
            limit_class = LimitClass.CLOSE_AT_LIMIT.value
        elif policy.restrict_when_session_locked and \
                limit_class == LimitClass.ONE_WAY_LOCKED.value:
            # ex_post_execution_assumption: "an all-day one-way lock cannot
            # have been filled" uses close-of-day knowledge an order of
            # unknown timing could not have had. Conservative direction
            # (restricts), retained only under the explicit policy flag and
            # labelled in restriction_reasons/details.
            ex_post_assumption = True
        else:
            limit_class = LimitClass.NOT_LIMIT.value
    if ex_post_assumption:
        reasons.append("ex_post_execution_assumption")

    # Certain restrictions first: suspension is provable without any rule.
    if ctx.is_suspended is True or (ctx.trade_status is not None and ctx.trade_status != "1") \
            or (ctx.is_trade is False):
        reasons.append("suspended")
        return Attemptability.RESTRICTED.value, limit_class, legal_price
    # Unknowns are accumulated (not one-at-a-time) so every missing fact is
    # visible in restriction_reasons; all of them fail closed.
    unknowns: list[str] = []
    if ctx.status_present is False:
        unknowns.append("status_row_missing")
    if ctx.bar_present is False:
        unknowns.append("no_daily_bar")
    if rule is RULE_UNKNOWN:
        unknowns.append("rule_unknown")
    if no_limit_window is None:
        unknowns.append("listing_session_index_unknown")
    if unknowns:
        reasons.extend(unknowns)
        return Attemptability.UNKNOWN.value, limit_class, legal_price

    block = (
        (side == "buy" and policy.block_limit_up_buy)
        or (side == "sell" and policy.block_limit_down_sell)
    ) and policy.assume_limit_locked_unfillable
    if block and limit_class in {
        LimitClass.CLOSE_AT_LIMIT.value,
        LimitClass.ONE_WAY_LOCKED.value,
    }:
        reasons.append("limit_up" if side == "buy" else "limit_down")
        return Attemptability.RESTRICTED.value, limit_class, legal_price
    if block and limit_class == LimitClass.PCT_NEAR_LIMIT_UNVERIFIED.value:
        # Cannot prove queue execution either way -> conservative restrict.
        reasons.append("possible_limit_lock_unverified")
        return Attemptability.RESTRICTED.value, limit_class, legal_price
    if policy.min_amount is not None and (
        ctx.amount is None or (isinstance(ctx.amount, float) and math.isnan(ctx.amount))
        or ctx.amount < policy.min_amount
    ):
        reasons.append("low_amount")
        return Attemptability.RESTRICTED.value, limit_class, legal_price
    return Attemptability.ATTEMPTABLE.value, limit_class, legal_price


def tradeability_at(
    ctx: TradeabilityContext,
    *,
    side: str = "buy",
    data_version: str = "daily",
    policy: ExecutionPolicy = DEFAULT_POLICY,
    order_time: str = "close",
) -> TradeabilityResult:
    """Point-in-time qualification for one (asset, date, side)."""
    if side not in {"buy", "sell"}:
        raise ValueError(f"unsupported side: {side}")
    try:
        ot = OrderTime(order_time)
    except ValueError:
        ot = OrderTime.UNKNOWN

    reasons: list[str] = []
    board = classify_board(symbol=ctx.symbol, exchange=ctx.exchange,
                           is_star=ctx.is_star, is_chinext=ctx.is_chinext,
                           is_beijing=ctx.is_beijing, board=ctx.board)
    status_class = _status_class(ctx)
    event_class = _event_class(ctx)
    rule = resolve_limit_rule(
        board=board, exchange=ctx.exchange, status_class=status_class,
        event_class=event_class, trade_date=ctx.trade_date,
        delisting_arrangement_entered=ctx.delisting_arrangement_entered,
        listing_age_trading_days=(
            ctx.listing_age_trading_days if ctx.listing_age_known else None),
    )
    if status_class == StatusClass.UNKNOWN.value:
        rule = RULE_UNKNOWN
    no_limit_window = _in_no_limit_window(ctx, rule)

    # --- dimension 1 ---
    universe = _eval_universe(ctx, reasons)
    effective_date: str | None = None
    if universe is Eligibility.INELIGIBLE:
        effective_date = (
            ctx.delist_date.isoformat() if ctx.delist_date and ctx.trade_date > ctx.delist_date
            else (ctx.list_date.isoformat() if ctx.list_date else None)
        )
    elif ctx.list_date is not None:
        effective_date = ctx.list_date.isoformat()

    # --- dimension 2 ---
    data_ready_daily: bool | None = ctx.daily_bar_rows > 0 or ctx.bar_present
    if ctx.minute_qualified is not None or ctx.minute_provider_configured:
        # Provider-configured path is fail-closed: qualified=True is required;
        # None (no ledger evidence) and False both mean NOT ready — never
        # fall back to minute row counts as proof of qualification.
        data_ready_minute = ctx.minute_qualified is True
        if ctx.minute_qualified is not True:
            reasons.append("minute_key_not_qualified")
            if ctx.minute_version == "no_minute_key":
                reasons.append("no_minute_key")
            elif ctx.minute_version in {"post_diff_isolated",
                                        "factor_gap_residual",
                                        "required_source_missing"}:
                reasons.append(ctx.minute_version)
        # date-level readiness: a qualified asset whose minute bars are
        # absent on a day the status table says it traded is NOT date-ready.
        if (data_ready_minute and ctx.minute_bar_rows == 0
                and ctx.is_trade is True and ctx.status_present):
            data_ready_minute = False
            reasons.append("minute_rows_missing_for_date")
        # P1d.2a C: a traded day where the provider could NOT verify the
        # required source/freq/adjust data at THIS date is fail-closed —
        # key-level done never self-declares per-day completeness.
        if (data_ready_minute and ctx.minute_date_verified is False
                and ctx.is_trade is True and ctx.status_present):
            data_ready_minute = False
            reasons.append("minute_date_unverified")
    else:
        # No provider configured: readiness unknown, not row-count-derived.
        data_ready_minute = None
    if "minute_factor_gap" in ctx.data_quality_blocks:
        # audit-visible: the baostock gap marker is preserved even when an
        # alternate source qualifies the asset — it does NOT mask readiness
        # granted by a qualified source, and does not silently disappear.
        if data_ready_minute is True:
            reasons.append("factor_gap_covered_by_alt_source")
        else:
            data_ready_minute = False
            reasons.append("residual_factor_gap_minute")
    if "post_diff_isolated" in ctx.data_quality_blocks:
        reasons.append("post_diff_isolated")
    if not ctx.bar_present:
        reasons.append("no_daily_bar")
    if not ctx.status_present:
        reasons.append("no_status_row")

    # --- dimension 3 (both sides evaluated independently) ---
    buy_state, limit_class_up, legal_up = _eval_side(
        ctx, side="buy", policy=policy, order_time=ot, rule=rule,
        no_limit_window=no_limit_window, reasons=reasons)
    sell_state, limit_class_down, legal_down = _eval_side(
        ctx, side="sell", policy=policy, order_time=ot, rule=rule,
        no_limit_window=no_limit_window, reasons=reasons)
    if universe is Eligibility.INELIGIBLE:
        buy_state = Attemptability.RESTRICTED.value
        sell_state = Attemptability.RESTRICTED.value
    elif universe is Eligibility.UNKNOWN:
        buy_state = Attemptability.UNKNOWN.value
        sell_state = Attemptability.UNKNOWN.value
    if no_limit_window is True:
        reasons.append("ipo_no_limit_window")
    if status_class == StatusClass.RISK_WARNING.value:
        reasons.append("st_risk_warning")
    if status_class == StatusClass.DELISTING_ARRANGEMENT.value:
        reasons.append("delisting_arrangement_period")

    stored_flag = ctx.stored_is_limit_up if side == "buy" else ctx.stored_is_limit_down
    hist_hit = (limit_class_up if side == "buy" else limit_class_down) in {
        LimitClass.CLOSE_AT_LIMIT.value, LimitClass.ONE_WAY_LOCKED.value}
    stored_flag_disagrees = bool(stored_flag is not None and bool(stored_flag) != hist_hit)
    if stored_flag_disagrees:
        reasons.append("stored_flag_disagrees_with_effective_rule")

    return TradeabilityResult(
        asset_id=ctx.asset_id,
        trade_date=ctx.trade_date.isoformat(),
        side=side,
        data_version=data_version,
        order_time=ot.value,
        universe_state=universe.value,
        data_ready_daily=data_ready_daily,
        data_ready_minute=data_ready_minute,
        buy_state=buy_state,
        sell_state=sell_state,
        eligible_for_universe=(
            True if universe is Eligibility.ELIGIBLE
            else False if universe is Eligibility.INELIGIBLE else None),
        can_attempt_buy=buy_state == Attemptability.ATTEMPTABLE.value,
        can_attempt_sell=sell_state == Attemptability.ATTEMPTABLE.value,
        restriction_reasons=tuple(dict.fromkeys(reasons)),
        status_source=ctx.status_source,
        effective_date=effective_date,
        limit_regime=board,
        limit_rule_id=rule.rule_id,
        limit_class_up=limit_class_up,
        limit_class_down=limit_class_down,
        legal_limit_up_price=legal_up,
        legal_limit_down_price=legal_down,
        stored_flag_disagrees=stored_flag_disagrees,
        status_class=status_class,
        details={
            "limit_rule_source": rule.source_doc,
            "limit_rule_doc": rule.doc_number,
            "limit_rule_verified": rule.verified,
            "limit_up_pct": rule.up_limit_pct,
            "limit_down_pct": rule.down_limit_pct,
            "day1_up_pct": rule.day1_up_pct,
            "day1_down_pct": rule.day1_down_pct,
            "no_limit_window_days": rule.no_limit_window_days,
            "no_limit_window": no_limit_window,
            "in_no_limit_window": (no_limit_window is True),
            "listing_age_trading_days": ctx.listing_age_trading_days,
            "listing_age_known": ctx.listing_age_known,
            "listing_event": event_class,
            "minute_qualified_sources": list(ctx.minute_qualified_sources),
            "minute_version": ctx.minute_version,
            "minute_date_verified": ctx.minute_date_verified,
            "data_quality_blocks": list(ctx.data_quality_blocks),
            "stored_limit_flag_side": stored_flag,
            # A3 information tiers: 'open' decisions consume only open-knowable
            # facts; 'close' decisions consume close-confirmed facts; any
            # close-data usage behind an open-time gate is labelled ex-post.
            "information_tier": (
                "open_pit" if ot is OrderTime.OPEN else
                "close_pit" if ot is OrderTime.CLOSE else "unknown_pit"),
            "ex_post_execution_assumption":
                "ex_post_execution_assumption" in reasons,
        },
    )


# ---------------------------------------------------------------------------
# Minute qualification provider (P0-E) — injectable adapter over the real
# R2/P1c chain. Default reads the on-disk ledgers produced by the rebuilds.
# ---------------------------------------------------------------------------


class MinuteQualificationProvider:
    def verdict(self, asset_id: str,
                trade_date: object = None,
                required_source: str | None = None,
                ) -> tuple[bool | None, tuple[str, ...], str | None, tuple[str, ...]]:
        """-> (qualified, qualified_sources, version, blocking_reasons).

        qualified tri-state:
          True  — at least one done key covers this asset (and required_source
                  when given); date-level readiness is evaluated separately.
          False — proven unqualified (terminal factor gap / post_diff
                  isolation / done keys exist but none satisfy required_source).
          None  — no ledger evidence at all (asset outside the rebuilt
                  universe); callers MUST fail closed on None, never fall back
                  to minute row counts.
        """
        raise NotImplementedError


class LedgerMinuteQualificationProvider(MinuteQualificationProvider):
    """Binds minute readiness to the actual rebuild ledgers:

    - done keys per source in r2_downstream_minute_done.json
      (key = asset|freq|source; value carries raw_sig/factor_sig versions)
    - terminal factor-gap assets in factor_gap_155_reconciliation.json
    - POST_DIFF audit isolation (600153) — never released here

    Alt-source coverage does NOT erase the original baostock gap: assets
    qualified only via akshare/eastmoney keep `minute_factor_gap` in
    blocking_reasons for audit visibility.
    """

    def __init__(self, done_keys: dict[str, dict] | dict[str, list],
                 residual_gap_assets: set[str],
                 post_diff_assets: set[str] | None = None):
        # done_keys: asset_id -> {key: meta} | legacy asset_id -> [key, ...]
        normalized: dict[str, dict] = {}
        for asset, val in done_keys.items():
            if isinstance(val, dict):
                normalized[asset] = dict(val)
            else:
                normalized[asset] = {k: {} for k in val}
        self._done = normalized
        self._gap = residual_gap_assets
        self._post_diff = post_diff_assets or set()
        # P1d.2a C: optional (asset_id, trade_date, freq, source) -> bool|None
        # checker proving that the matching source/freq/adjust data actually
        # exists for THAT date (the ledger only proves key-level completion).
        self._date_checker = None

    def set_date_checker(self, fn) -> None:
        """Bind a date-level evidence checker, e.g. an EXISTS query against
        market.stock_minute_bar for (asset, date, freq, source, qfq)."""
        self._date_checker = fn

    @classmethod
    def from_repo(cls, base: str = "outputs/research/data01r1_finance_q2_20261020") -> "LedgerMinuteQualificationProvider":
        import json
        done_led = json.load(open(f"{base}/r2_downstream_minute_done.json"))
        done_keys: dict[str, dict] = {}
        for k, meta in done_led.items():
            done_keys.setdefault(k.split("|")[0], {})[k] = meta
        gap = set(json.load(open(f"{base}/factor_gap_155_reconciliation.json"))
                  ["minute_residual_gap_assets"])
        return cls(done_keys, gap, post_diff_assets={"CN:SH:600153"})

    def key_versions(self, asset_id: str) -> dict[str, dict]:
        """Traceable per-key version evidence (raw_sig/factor_sig)."""
        return dict(self._done.get(asset_id, {}))

    def verdict(self, asset_id: str, trade_date: object = None,
                required_source: str | None = None):
        if asset_id in self._post_diff:
            return False, (), "post_diff_isolated", ("post_diff_isolated",)
        keys = self._done.get(asset_id, {})
        if required_source is not None:
            keys = {k: v for k, v in keys.items()
                    if k.split("|")[2] == required_source}
        sources = tuple(sorted({k.split("|")[2] for k in keys}))
        if not keys:
            if required_source is not None and self._done.get(asset_id):
                # done via other sources but NOT the required one
                return False, (), "required_source_missing", (
                    "required_source_missing",
                    *(("minute_factor_gap",) if asset_id in self._gap else ()))
            if asset_id in self._gap:
                return False, (), "factor_gap_residual", ("minute_factor_gap",)
            return None, (), "no_minute_key", ("no_minute_key",)
        # version = newest factor_sig timestamp across satisfying keys —
        # the factor-signature rebuild time IS the data version for that key.
        vers = sorted(
            str((v or {}).get("factor_sig") or "") for v in keys.values())[-1]
        blocking = ("minute_factor_gap",) if asset_id in self._gap else ()
        # P1d.2a C: key-level done does NOT prove date-level completeness.
        # If trade_date is given, verify per-key (freq, source) against the
        # bound checker; without one, emit the degraded 'key_level' tier.
        if trade_date is None:
            return True, sources, f"r2_minute_v1:{vers}", blocking
        if self._date_checker is None:
            return True, sources, f"r2_minute_v1:{vers}:key_level", (
                *blocking, "minute_date_unverified")
        ok_keys = [
            k for k in keys
            if self._date_checker(
                asset_id, trade_date, k.split("|")[1], k.split("|")[2])
        ]
        if not ok_keys:
            return True, sources, f"r2_minute_v1:{vers}:key_level_unverified_date", (
                *blocking, "minute_date_unverified")
        sources = tuple(sorted({k.split("|")[2] for k in ok_keys}))
        return True, sources, f"r2_minute_v1:{vers}:date_verified", blocking


# ---------------------------------------------------------------------------
# Thin DB loader — read-only, reuses core tables only.
# ---------------------------------------------------------------------------

_CTX_SQL = """
SELECT
    a.asset_id,
    a.symbol, a.exchange, a.board, a.is_star, a.is_chinext, a.is_beijing,
    a.name, a.list_date, a.delist_date,
    cal.is_open AS exchange_open,
    (SELECT count(*) FROM market.trading_calendar c2
      WHERE c2.exchange = a.exchange AND c2.is_open
        AND c2.trade_date >= a.list_date AND c2.trade_date <= %(trade_date)s
    ) AS listing_age_trading_days,
    s.is_trade, s.is_st, s.is_suspended, s.is_limit_up, s.is_limit_down,
    s.limit_up_price, s.limit_down_price,
    s.source AS status_source,
    b.open, b.high, b.low, b.close, b.preclose,
    b.pct_chg, b.amount, b.trade_status,
    (b.asset_id IS NOT NULL) AS bar_present,
    (s.asset_id IS NOT NULL) AS status_present,
    COALESCE(m.cnt, 0) AS minute_bar_rows,
    (SELECT count(*) FROM core.asset_lifecycle_event le
      WHERE le.asset_id = a.asset_id AND le.event_type = 'listed'
        AND le.event_date <= %(trade_date)s) AS listing_event_count
FROM core.asset_master a
LEFT JOIN market.trading_calendar cal
  ON cal.exchange = a.exchange AND cal.trade_date = %(trade_date)s
LEFT JOIN core.asset_status_daily s
  ON s.asset_id = a.asset_id AND s.trade_date = %(trade_date)s
LEFT JOIN public.market_daily_bar b
  ON b.asset_id = a.asset_id AND b.trade_date = %(trade_date)s
 AND b.adjust_type = 'raw'
LEFT JOIN (
    SELECT asset_id, count(*) AS cnt FROM market.stock_minute_bar
    WHERE asset_id = %(asset_id)s AND trade_date = %(trade_date)s
    GROUP BY asset_id
) m ON m.asset_id = a.asset_id
WHERE a.asset_id = %(asset_id)s
"""


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def load_tradeability_context(
    conn,
    asset_id: str,
    trade_date: str,
    *,
    minute_provider: MinuteQualificationProvider | None = None,
    minute_required_source: str | None = None,
    data_quality_blocks: Iterable[str] = (),
) -> TradeabilityContext | None:
    """Read-only PIT context from existing core tables.

    Uses the RAW (unadjusted) bar for legal-limit math — hfq prices are
    adjusted and must not be compared to legal limit prices (P0-D).
    Returns None if the asset is not in core.asset_master at all."""
    from .db import fetch_all

    rows = fetch_all(
        conn, _CTX_SQL,
        {"asset_id": asset_id, "trade_date": trade_date},
    )
    if not rows:
        return None
    r = rows[0]
    list_date = _as_date(r.get("list_date"))
    age = r.get("listing_age_trading_days")
    listing_age_known = list_date is not None and age is not None and int(age) > 0
    ev_count = int(r.get("listing_event_count") or 0)
    name = str(r.get("name") or "").upper()
    listing_event = "continuous"
    if list_date is not None and _as_date(trade_date) is not None:
        span = (_as_date(trade_date) - list_date).days
        if span <= 15:
            listing_event = "relisting" if ev_count >= 2 else "ipo"
    minute_q, minute_src, minute_ver, minute_blocks = (None, (), None, ())
    minute_date_verified = None
    if minute_provider is not None:
        # P1d.2a C: bind a real per-(asset,date,freq,source) existence check
        # against market.stock_minute_bar so the provider never claims
        # date-level readiness from key-level done alone.
        if hasattr(minute_provider, "set_date_checker"):
            def _check_minute_source(a_id, t_date, freq, source):
                hit = fetch_all(conn, """
                    SELECT 1 FROM market.stock_minute_bar
                    WHERE asset_id = %s AND trade_date = %s
                      AND freq = %s AND adjust_type = 'qfq' AND source = %s
                    LIMIT 1""", (a_id, t_date, freq, source))
                return bool(hit)
            minute_provider.set_date_checker(_check_minute_source)
        minute_q, minute_src, minute_ver, minute_blocks = minute_provider.verdict(
            asset_id, trade_date=_as_date(trade_date),
            required_source=minute_required_source)
        if minute_ver is not None:
            if str(minute_ver).endswith(":date_verified"):
                minute_date_verified = True
            elif ":key_level" in str(minute_ver):
                minute_date_verified = False
    return TradeabilityContext(
        asset_id=asset_id,
        trade_date=_as_date(trade_date),
        list_date=list_date,
        delist_date=_as_date(r.get("delist_date")),
        listing_event=listing_event,
        symbol=str(r.get("symbol") or ""),
        exchange=str(r.get("exchange") or ""),
        board=r.get("board"),
        is_star=bool(r.get("is_star")),
        is_chinext=bool(r.get("is_chinext")),
        is_beijing=bool(r.get("is_beijing")),
        exchange_open=r.get("exchange_open"),
        listing_age_trading_days=int(age) if age is not None else None,
        listing_age_known=listing_age_known,
        status_present=bool(r.get("status_present")),
        is_trade=r.get("is_trade"),
        is_st=r.get("is_st"),
        is_suspended=r.get("is_suspended"),
        stored_is_limit_up=r.get("is_limit_up"),
        stored_is_limit_down=r.get("is_limit_down"),
        stored_limit_up_price=_num(r.get("limit_up_price")),
        stored_limit_down_price=_num(r.get("limit_down_price")),
        status_source=str(r.get("status_source") or "absent"),
        bar_present=bool(r.get("bar_present")),
        open_raw=_num(r.get("open")),
        high_raw=_num(r.get("high")),
        low_raw=_num(r.get("low")),
        close_raw=_num(r.get("close")),
        preclose_raw=_num(r.get("preclose")),
        pct_chg=_num(r.get("pct_chg")),
        amount=_num(r.get("amount")),
        trade_status=str(r.get("trade_status")) if r.get("trade_status") is not None else None,
        daily_bar_rows=1 if r.get("bar_present") else 0,
        minute_bar_rows=int(r.get("minute_bar_rows") or 0),
        minute_qualified=minute_q,
        minute_qualified_sources=tuple(minute_src),
        minute_version=minute_ver,
        minute_date_verified=minute_date_verified,
        minute_provider_configured=minute_provider is not None,
        minute_required_source=minute_required_source,
        data_quality_blocks=tuple(data_quality_blocks) + tuple(minute_blocks),
    )


# ---------------------------------------------------------------------------
# P1d.2a D — shared PIT limit-flag recompute
# Single source of truth for corrected flags: consumed by the corrected_shadow
# loader path AND the shadow scripts. Not a parallel system — it wraps the
# same LIMIT_RULES / resolve_limit_rule / legal_limit_price engine.
# ---------------------------------------------------------------------------

_FLAGS_CONTEXT_SQL = """
SELECT s.asset_id, s.trade_date::text AS trade_date,
       a.symbol, a.exchange, a.board, a.is_star, a.is_chinext, a.is_beijing,
       a.list_date::text AS list_date,
       s.is_st, s.is_suspended,
       b.close AS close_raw, b.preclose AS preclose_raw
FROM core.asset_status_daily s
JOIN core.asset_master a ON a.asset_id = s.asset_id
LEFT JOIN public.market_daily_bar b
  ON b.asset_id = a.asset_id AND b.trade_date = s.trade_date
 AND b.adjust_type = 'raw'
WHERE s.trade_date BETWEEN %s AND %s
"""


def compute_pit_limit_flags(conn, start: str, end: str,
                            open_days: dict[str, list] | None = None):
    """Recompute is_limit_up/down per (asset_id, trade_date) under the
    historically effective rule. rule_unknown rows are marked
    shadow_rule_unknown=True — fail-closed, never silently tradable.

    open_days: {exchange: sorted open dates} — loaded once by the caller from
    market.trading_calendar; loaded here when None (needs conn).
    """
    import bisect as _bisect
    from decimal import Decimal as _Decimal
    from functools import lru_cache as _lru

    import pandas as pd

    from .db import fetch_all

    def _f(v):
        if v is None:
            return None
        if isinstance(v, _Decimal):
            return float(v)
        try:
            f = float(v)
            return None if f != f else f
        except (TypeError, ValueError):
            return None

    @_lru(maxsize=None)
    def _rule(board, exchange, status_class, event, date_iso, sess_idx):
        return resolve_limit_rule(
            board=board, exchange=exchange, status_class=status_class,
            event_class=event, trade_date=dt.date.fromisoformat(date_iso),
            listing_age_trading_days=sess_idx,
        )

    if open_days is None:
        open_days = {}
        for r in fetch_all(
                conn,
                "select exchange, trade_date::text d from market.trading_calendar "
                "where is_open order by exchange, trade_date"):
            open_days.setdefault(r["exchange"], []).append(
                dt.date.fromisoformat(r["d"]))

    rows = fetch_all(conn, _FLAGS_CONTEXT_SQL, [start, end])
    recs = []
    for r in rows:
        board = classify_board(
            symbol=str(r.get("symbol") or ""),
            exchange=str(r.get("exchange") or ""),
            is_star=bool(r.get("is_star")), is_chinext=bool(r.get("is_chinext")),
            is_beijing=bool(r.get("is_beijing")), board=r.get("board"))
        trade_date = _as_date(r["trade_date"])
        list_date = _as_date(r.get("list_date"))
        exchange = str(r.get("exchange") or "")
        status_class = "risk_warning" if r.get("is_st") else "normal"
        sess_idx = None
        if list_date is not None and open_days.get(exchange):
            days = open_days[exchange]
            lo = _bisect.bisect_left(days, list_date)
            hi = _bisect.bisect_right(days, trade_date)
            sess_idx = hi - lo if hi > lo else None
        if sess_idx is not None:
            event = "ipo" if sess_idx <= 10 else "continuous"
        else:
            event = ("ipo" if list_date and (trade_date - list_date).days <= 30
                     else "continuous")
        rule = _rule(board, exchange, status_class, event,
                     trade_date.isoformat(), sess_idx)
        close_raw = _f(r.get("close_raw"))
        preclose_raw = _f(r.get("preclose_raw"))
        no_limit = bool(
            rule.no_limit_window_days
            and event in {"ipo", "relisting"}
            and sess_idx is not None
            and 1 <= sess_idx <= rule.no_limit_window_days)
        unknown = rule.rule_id == "rule_unknown" or not rule.verified
        if unknown or close_raw is None or preclose_raw is None:
            recs.append({
                "asset_id": r["asset_id"], "trade_date": r["trade_date"],
                "shadow_limit_up": False, "shadow_limit_down": False,
                "shadow_rule_unknown": True, "shadow_rule_id": rule.rule_id})
            continue
        lim_up = lim_dn = False
        if not no_limit:
            eff_up = (rule.day1_up_pct if sess_idx == 1
                      and rule.day1_up_pct is not None else rule.up_limit_pct)
            eff_dn = (rule.day1_down_pct if sess_idx == 1
                      and rule.day1_down_pct is not None else rule.down_limit_pct)
            legal_up = legal_limit_price(preclose_raw, eff_up, "up")
            legal_dn = legal_limit_price(preclose_raw, eff_dn, "down")
            lim_up = legal_up is not None and close_raw >= legal_up - 1e-9
            lim_dn = legal_dn is not None and close_raw <= legal_dn + 1e-9
        recs.append({
            "asset_id": r["asset_id"], "trade_date": r["trade_date"],
            "shadow_limit_up": lim_up, "shadow_limit_down": lim_dn,
            "shadow_rule_unknown": False, "shadow_rule_id": rule.rule_id})
    return pd.DataFrame(recs)


def apply_pit_flags(prices, flags):
    """Overlay corrected flags onto a prices frame (corrected_shadow mode).

    rule_unknown and flag-absent rows fail closed: both limit flags forced
    True so can_open_long/can_close_long block the attempt. Stored v1 flags
    are NEVER consulted as corrected truth.
    """
    import pandas as pd

    flags = flags.copy()
    flags["trade_date"] = pd.to_datetime(flags["trade_date"])
    merged = prices.copy()
    merged["trade_date"] = pd.to_datetime(merged["trade_date"])
    merged = merged.merge(
        flags[["asset_id", "trade_date", "shadow_limit_up",
               "shadow_limit_down", "shadow_rule_unknown", "shadow_rule_id"]],
        on=["asset_id", "trade_date"], how="left")
    for col in ("shadow_limit_up", "shadow_limit_down", "shadow_rule_unknown"):
        merged[col] = merged[col].fillna(False).astype(bool)
    merged["is_limit_up"] = merged["shadow_limit_up"] | merged["shadow_rule_unknown"]
    merged["is_limit_down"] = merged["shadow_limit_down"] | merged["shadow_rule_unknown"]
    merged["limit_state_missing"] = merged["shadow_rule_unknown"]
    merged = merged.rename(columns={"shadow_rule_id": "limit_rule_id"})
    return merged.drop(columns=["shadow_limit_up", "shadow_limit_down",
                                "shadow_rule_unknown"])
