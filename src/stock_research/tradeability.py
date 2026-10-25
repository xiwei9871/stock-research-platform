"""DATA-R3-P1d: point-in-time tradeability qualification (read-only audit layer).

Purpose
-------
Give backtests a single, explicit answer to "could this order/universe
membership legitimately exist at this historical date?" — WITHOUT creating a
parallel status/rules mechanism. Everything here composes infrastructure that
already exists:

- ``market.trading_calendar``      exchange open days
- ``core.asset_master``            list_date / delist_date / board flags
- ``core.asset_status_daily``      per-day is_trade / is_st / is_suspended /
                                   is_limit_up / is_limit_down / limit prices
- ``backtest_constraints``         existing execution gate (suspension,
                                   limit-up buy block, limit-down sell block)
- ``lhb_eligibility``              board limit taxonomy (star/chinext/beijing/
                                   st/main_board, listing_no_limit)

Three dimensions are kept strictly separate — none may substitute another:

1. ``eligible_for_universe``  — was the security a member of the tradable A-share
   universe at that date (listed, not yet delisted, exchange open).
2. ``data_ready_daily`` / ``data_ready_minute`` — does the platform actually hold
   the market data needed to reason about that date (bars / minute bars /
   declared data-quality blocks such as residual FACTOR_GAP keys).
3. ``can_attempt_buy`` / ``can_attempt_sell`` — order-level executability under
   the *historical* rules in force on that date.

Historical rule correctness
---------------------------
``core.asset_status_daily.is_limit_up`` / ``is_limit_down`` were built with a
static, current-board threshold table (ST 4.8, BJ 29.8, STAR/ChiNext 19.8,
else 9.8). They are NOT date-aware: ChiNext was ±10% before 2020-08-24, and a
number of other regime boundaries exist. This module therefore re-derives the
limit regime from ``LIMIT_RULES`` (effective-dated) and reports
``rule_version`` plus ``stored_flag_disagrees`` when the stored flag and the
historically correct flag diverge. ``REGRESSION_DIFF``-style rows are the audit
output; no stored data is rewritten here.

Execution assumptions are deliberately conservative and configurable:
a limit-locked day blocks the corresponding side unless the caller explicitly
relaxes ``ExecutionPolicy``. Reaching the limit price is not equated with
guaranteed zero execution, and a limit-price queue position is never assumed
to fill — when queue/execution cannot be proven the result is a *restricted*
state, not a silent pass or a silent fail.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any, Iterable

from .backtest_constraints import BacktestExecutionConstraints, can_close_long, can_open_long

TRADEABILITY_CONTRACT_VERSION = "tradeability_pit_v1"

# ---------------------------------------------------------------------------
# Effective-dated price-limit rule table (P0-3).
# `effective_from`/`effective_to` are inclusive date bounds (None = open).
# Threshold is the *positive* limit in percent used to detect limit-locked
# closes from pct_chg. `no_limit_window_days` marks IPO/relisting sessions
# where no ordinary limit applies at all.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LimitRule:
    rule_id: str
    board: str  # main | chinext | star | beijing | st_main | any_st_override
    effective_from: dt.date | None
    effective_to: dt.date | None
    up_limit_pct: float | None
    down_limit_pct: float | None
    no_limit_window_days: int = 0  # first N listing sessions have no limit
    source_doc: str = ""

    def covers(self, trade_date: dt.date) -> bool:
        if self.effective_from and trade_date < self.effective_from:
            return False
        if self.effective_to and trade_date > self.effective_to:
            return False
        return True


# Sources for each rule live in historical_rule_sources.csv; keep ids aligned.
LIMIT_RULES: tuple[LimitRule, ...] = (
    LimitRule("chinext_10pct_pre_20200824", "chinext", None, dt.date(2020, 8, 21), 10.0, 10.0,
              source_doc="深交所创业板交易规则(2019修订)/注册制前 ±10%"),
    LimitRule("chinext_20pct_from_20200824", "chinext", dt.date(2020, 8, 24), None, 20.0, 20.0,
              no_limit_window_days=5,
              source_doc="深交所创业板交易特别规定 2020-08-24 注册制改革"),
    LimitRule("star_20pct_since_20190722", "star", dt.date(2019, 7, 22), None, 20.0, 20.0,
              no_limit_window_days=5,
              source_doc="上交所科创板股票交易特别规定 2019-07-22 开板"),
    LimitRule("beijing_30pct_since_20211115", "beijing", dt.date(2021, 11, 15), None, 30.0, 30.0,
              no_limit_window_days=1,
              source_doc="北京证券交易所交易规则(试行) 2021-11-15 开市"),
    LimitRule("st_main_5pct", "st_main", None, None, 5.0, 5.0,
              source_doc="沪深交易所风险警示板交易规则 ST/*ST ±5%"),
    # Main-board IPO treatment differs across regimes: before the 2023-04-10
    # full-registration switch the first session had a +44%/-36% cap
    # (functionally limit-locked at cap — reaching it blocks the buy side
    # under the conservative policy); from 2023-04-10 the first 5 sessions
    # carry no ordinary limit at all.
    LimitRule("main_10pct_pre_20230410", "main", None, dt.date(2023, 4, 7), 10.0, 10.0,
              source_doc="上交所/深交所交易规则 主板 ±10%;首日+44%/-36%上限"),
    LimitRule("main_10pct_from_20230410", "main", dt.date(2023, 4, 10), None, 10.0, 10.0,
              no_limit_window_days=5,
              source_doc="全面注册制交易规则 2023-04-10 起主板新股前5日无涨跌幅"),
)


def classify_board(*, symbol: str, exchange: str, is_star: bool, is_chinext: bool,
                   is_beijing: bool, board: str | None) -> str:
    """Reuse the same board taxonomy as lhb_eligibility / asset_master flags."""
    if is_beijing or exchange == "BJ" or (board or "").lower() == "beijing":
        return "beijing"
    if is_star or (board or "").lower() == "star":
        return "star"
    if is_chinext or (board or "").lower() == "chinext":
        return "chinext"
    return "main"


def resolve_limit_rule(*, board: str, is_st: bool | None, trade_date: dt.date) -> LimitRule:
    """Date-aware rule resolution.

    ST on the main board keeps the ±5% risk-warning regime. ST/*ST on ChiNext /
    STAR / BJ keep their *board* limit (20%/30%) — the exchange applies the
    board regime to risk-warning stocks there.
    """
    key = "st_main" if (is_st and board == "main") else board
    candidates = [r for r in LIMIT_RULES if r.board == key and r.covers(trade_date)]
    if not candidates:
        # Open-interval fallback: treat as unrestricted rather than guessing.
        return LimitRule("unrestricted_unknown_period", key, None, None, None, None,
                         source_doc="no effective rule found for date")
    return candidates[0]


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionPolicy:
    """Configurable conservative execution assumptions (P0-3)."""

    block_limit_up_buy: bool = True
    block_limit_down_sell: bool = True
    block_suspended: bool = True
    # When a day is limit-locked but real fills may have occurred intraday,
    # we still cannot *prove* queue execution — keep blocking (conservative).
    assume_limit_locked_unfillable: bool = True
    min_amount: float | None = None


DEFAULT_POLICY = ExecutionPolicy()


@dataclass(frozen=True)
class TradeabilityContext:
    """Point-in-time inputs for one (asset, trade_date). Pure data — no IO."""

    asset_id: str
    trade_date: dt.date
    # master
    list_date: dt.date | None = None
    delist_date: dt.date | None = None
    symbol: str = ""
    exchange: str = ""
    board: str | None = None
    is_star: bool = False
    is_chinext: bool = False
    is_beijing: bool = False
    # calendar
    exchange_open: bool | None = None
    # per-day status (core.asset_status_daily)
    status_present: bool = False
    is_trade: bool | None = None
    is_st: bool | None = None
    is_suspended: bool | None = None
    stored_is_limit_up: bool | None = None
    stored_is_limit_down: bool | None = None
    status_source: str = "absent"
    # bar facts
    bar_present: bool = False
    pct_chg: float | None = None
    amount: float | None = None
    trade_status: str | None = None  # raw bar trade_status if known ('1' = traded)
    # data readiness
    daily_bar_rows: int = 0
    minute_bar_rows: int = 0
    data_quality_blocks: tuple[str, ...] = ()
    # listing-session index if known (for IPO no-limit windows); else computed
    listing_age_trading_days: int | None = None


@dataclass(frozen=True)
class TradeabilityResult:
    asset_id: str
    trade_date: str
    side: str
    data_version: str
    eligible_for_universe: bool | None
    data_ready_daily: bool | None
    data_ready_minute: bool | None
    can_attempt_buy: bool
    can_attempt_sell: bool
    restriction_reasons: tuple[str, ...]
    status_source: str
    effective_date: str | None
    rule_version: str = TRADEABILITY_CONTRACT_VERSION
    limit_regime: str = ""
    limit_rule_id: str = ""
    stored_flag_disagrees: bool = False
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def _as_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _locked_by_limit(*, pct_chg: float | None, rule: LimitRule, side: str) -> bool:
    """Historical limit-lock detection under the *effective* rule."""
    if pct_chg is None or rule.up_limit_pct is None or math.isnan(pct_chg):
        return False
    if side == "buy":
        return pct_chg >= rule.up_limit_pct - 0.05
    return pct_chg <= -rule.down_limit_pct + 0.05


def _in_no_limit_window(ctx: TradeabilityContext, rule: LimitRule) -> bool:
    if not rule.no_limit_window_days:
        return False
    age = ctx.listing_age_trading_days
    if age is not None:
        return 1 <= age <= rule.no_limit_window_days
    # Fall back to calendar distance only when session count unavailable.
    if ctx.list_date is not None and rule.no_limit_window_days >= 1:
        return ctx.trade_date == ctx.list_date
    return False


def tradeability_at(
    ctx: TradeabilityContext,
    *,
    side: str = "buy",
    data_version: str = "daily",
    policy: ExecutionPolicy = DEFAULT_POLICY,
) -> TradeabilityResult:
    """Point-in-time qualification for one (asset, date, side)."""
    if side not in {"buy", "sell"}:
        raise ValueError(f"unsupported side: {side}")

    reasons: list[str] = []
    board = classify_board(symbol=ctx.symbol, exchange=ctx.exchange,
                           is_star=ctx.is_star, is_chinext=ctx.is_chinext,
                           is_beijing=ctx.is_beijing, board=ctx.board)
    rule = resolve_limit_rule(board=board, is_st=ctx.is_st, trade_date=ctx.trade_date)
    no_limit_window = _in_no_limit_window(ctx, rule)

    # --- dimension 1: universe eligibility (independent of data readiness) ---
    eligible: bool | None
    effective_date: str | None = None
    if ctx.exchange_open is False:
        eligible = False
        reasons.append("exchange_closed")
    else:
        if ctx.list_date is None:
            eligible = None
            reasons.append("list_date_unknown")
        elif ctx.trade_date < ctx.list_date:
            eligible = False
            reasons.append("not_yet_listed")
            effective_date = ctx.list_date.isoformat()
        else:
            eligible = True
            effective_date = ctx.list_date.isoformat()
        if ctx.delist_date is not None and ctx.trade_date > ctx.delist_date:
            eligible = False
            reasons.append("delisted")
            effective_date = ctx.delist_date.isoformat()

    # --- dimension 2: data readiness (independent of eligibility) ---
    data_ready_daily: bool | None = ctx.daily_bar_rows > 0
    data_ready_minute: bool | None = ctx.minute_bar_rows > 0
    if "minute_factor_gap" in ctx.data_quality_blocks:
        data_ready_minute = False
        reasons.append("residual_factor_gap_minute")
    if not ctx.bar_present:
        reasons.append("no_daily_bar")
    if not ctx.status_present:
        reasons.append("no_status_row")

    # --- dimension 3: order-level executability (historical rules) ---
    stored_limit_flag = ctx.stored_is_limit_up if side == "buy" else ctx.stored_is_limit_down
    hist_limit_hit = (not no_limit_window) and _locked_by_limit(
        pct_chg=ctx.pct_chg, rule=rule, side=side)
    stored_flag_disagrees = bool(
        stored_limit_flag is not None and hist_limit_hit is not None
        and bool(stored_limit_flag) != hist_limit_hit)

    bar: dict[str, Any] = {
        "is_suspended": bool(ctx.is_suspended) if ctx.is_suspended is not None else None,
        "trade_status": ctx.trade_status if ctx.trade_status is not None else (
            "1" if ctx.is_trade else "0"),
        "is_limit_up": hist_limit_hit if side == "buy" else bool(stored_limit_flag),
        "is_limit_down": hist_limit_hit if side == "sell" else bool(stored_limit_flag),
        "amount": ctx.amount,
    }
    constraints = BacktestExecutionConstraints(
        block_suspended=policy.block_suspended,
        block_limit_up_buy=policy.block_limit_up_buy and policy.assume_limit_locked_unfillable,
        block_limit_down_sell=policy.block_limit_down_sell and policy.assume_limit_locked_unfillable,
        min_amount=policy.min_amount,
    )
    if side == "buy":
        ok, gate_reason = can_open_long(bar, constraints)
    else:
        ok, gate_reason = can_close_long(bar, constraints)

    can_attempt = bool(ok)
    if gate_reason:
        reasons.append(gate_reason)
    if no_limit_window:
        reasons.append("ipo_no_limit_window")
    if stored_flag_disagrees:
        reasons.append("stored_flag_disagrees_with_effective_rule")
    if ctx.is_st:
        reasons.append("st_risk_warning")
    if eligible is False:
        can_attempt = False
    if ctx.exchange_open is False:
        can_attempt = False
    if data_ready_daily is False and not ctx.bar_present:
        # No bar: cannot prove the order could exist; restricted, not tradable.
        can_attempt = False

    return TradeabilityResult(
        asset_id=ctx.asset_id,
        trade_date=ctx.trade_date.isoformat(),
        side=side,
        data_version=data_version,
        eligible_for_universe=eligible,
        data_ready_daily=data_ready_daily,
        data_ready_minute=data_ready_minute,
        can_attempt_buy=can_attempt if side == "buy" else _other_side(ctx, "sell", policy, hist_limit_hit, no_limit_window, stored_flag_disagrees),
        can_attempt_sell=can_attempt if side == "sell" else _other_side(ctx, "buy", policy, hist_limit_hit, no_limit_window, stored_flag_disagrees),
        restriction_reasons=tuple(dict.fromkeys(reasons)),
        status_source=ctx.status_source,
        effective_date=effective_date,
        limit_regime=rule.board,
        limit_rule_id=rule.rule_id,
        stored_flag_disagrees=stored_flag_disagrees,
        details={
            "limit_rule_source": rule.source_doc,
            "limit_up_pct": rule.up_limit_pct,
            "limit_down_pct": rule.down_limit_pct,
            "no_limit_window_days": rule.no_limit_window_days,
            "in_no_limit_window": no_limit_window,
            "hist_limit_hit_side": hist_limit_hit,
            "stored_limit_flag_side": stored_limit_flag,
            "data_quality_blocks": list(ctx.data_quality_blocks),
        },
    )


def _other_side(ctx: TradeabilityContext, side: str, policy: ExecutionPolicy,
                _hist_hit: bool, _nlw: bool, _dis: bool) -> bool:
    """Evaluate the opposite side so callers always get both booleans."""
    res = _eval_side(ctx, side=side, policy=policy)
    return res


def _eval_side(ctx: TradeabilityContext, *, side: str, policy: ExecutionPolicy) -> bool:
    board = classify_board(symbol=ctx.symbol, exchange=ctx.exchange,
                           is_star=ctx.is_star, is_chinext=ctx.is_chinext,
                           is_beijing=ctx.is_beijing, board=ctx.board)
    rule = resolve_limit_rule(board=board, is_st=ctx.is_st, trade_date=ctx.trade_date)
    if _in_no_limit_window(ctx, rule):
        hist_hit = False
    else:
        hist_hit = _locked_by_limit(pct_chg=ctx.pct_chg, rule=rule, side=side)
    stored = ctx.stored_is_limit_up if side == "buy" else ctx.stored_is_limit_down
    bar = {
        "is_suspended": bool(ctx.is_suspended) if ctx.is_suspended is not None else None,
        "trade_status": ctx.trade_status if ctx.trade_status is not None else (
            "1" if ctx.is_trade else "0"),
        "is_limit_up": hist_hit if side == "buy" else bool(stored),
        "is_limit_down": hist_hit if side == "sell" else bool(stored),
        "amount": ctx.amount,
    }
    constraints = BacktestExecutionConstraints(
        block_suspended=policy.block_suspended,
        block_limit_up_buy=policy.block_limit_up_buy and policy.assume_limit_locked_unfillable,
        block_limit_down_sell=policy.block_limit_down_sell and policy.assume_limit_locked_unfillable,
        min_amount=policy.min_amount,
    )
    if side == "buy":
        ok, _ = can_open_long(bar, constraints)
    else:
        ok, _ = can_close_long(bar, constraints)
    if ctx.delist_date is not None and ctx.trade_date > ctx.delist_date:
        ok = False
    if ctx.list_date is not None and ctx.trade_date < ctx.list_date:
        ok = False
    if ctx.exchange_open is False:
        ok = False
    if not ctx.bar_present:
        ok = False
    return bool(ok)


# ---------------------------------------------------------------------------
# Thin DB loader — read-only, reuses core tables only.
# ---------------------------------------------------------------------------

_CTX_SQL = """
SELECT
    a.asset_id,
    a.symbol, a.exchange, a.board, a.is_star, a.is_chinext, a.is_beijing,
    a.list_date, a.delist_date,
    cal.is_open AS exchange_open,
    s.is_trade, s.is_st, s.is_suspended, s.is_limit_up, s.is_limit_down,
    s.source AS status_source,
    b.pct_chg, b.amount, b.trade_status,
    (b.asset_id IS NOT NULL) AS bar_present,
    (s.asset_id IS NOT NULL) AS status_present,
    COALESCE(m.cnt, 0) AS minute_bar_rows
FROM core.asset_master a
LEFT JOIN market.trading_calendar cal
  ON cal.exchange = a.exchange AND cal.trade_date = %(trade_date)s
LEFT JOIN core.asset_status_daily s
  ON s.asset_id = a.asset_id AND s.trade_date = %(trade_date)s
LEFT JOIN public.market_daily_bar b
  ON b.asset_id = a.asset_id AND b.trade_date = %(trade_date)s
 AND b.adjust_type = %(adjust_type)s
LEFT JOIN (
    SELECT asset_id, count(*) AS cnt FROM market.stock_minute_bar
    WHERE asset_id = %(asset_id)s AND trade_date = %(trade_date)s
    GROUP BY asset_id
) m ON m.asset_id = a.asset_id
WHERE a.asset_id = %(asset_id)s
"""


def load_tradeability_context(conn, asset_id: str, trade_date: str,
                              *, adjust_type: str = "hfq",
                              data_quality_blocks: Iterable[str] = ()) -> TradeabilityContext | None:
    """Read-only PIT context from existing core tables. Returns None if the
    asset is not in core.asset_master at all."""
    from .db import fetch_all

    rows = fetch_all(
        conn, _CTX_SQL,
        {"asset_id": asset_id, "trade_date": trade_date, "adjust_type": adjust_type},
    )
    if not rows:
        return None
    r = rows[0]
    pct = r.get("pct_chg")
    amt = r.get("amount")
    return TradeabilityContext(
        asset_id=asset_id,
        trade_date=_as_date(trade_date),
        list_date=_as_date(r.get("list_date")),
        delist_date=_as_date(r.get("delist_date")),
        symbol=str(r.get("symbol") or ""),
        exchange=str(r.get("exchange") or ""),
        board=r.get("board"),
        is_star=bool(r.get("is_star")),
        is_chinext=bool(r.get("is_chinext")),
        is_beijing=bool(r.get("is_beijing")),
        exchange_open=r.get("exchange_open"),
        status_present=bool(r.get("status_present")),
        is_trade=r.get("is_trade"),
        is_st=r.get("is_st"),
        is_suspended=r.get("is_suspended"),
        stored_is_limit_up=r.get("is_limit_up"),
        stored_is_limit_down=r.get("is_limit_down"),
        status_source=str(r.get("status_source") or "absent"),
        bar_present=bool(r.get("bar_present")),
        pct_chg=float(pct) if pct is not None and not (isinstance(pct, float) and math.isnan(pct)) else None,
        amount=float(amt) if amt is not None and not (isinstance(amt, float) and math.isnan(amt)) else None,
        trade_status=str(r.get("trade_status")) if r.get("trade_status") is not None else None,
        daily_bar_rows=1 if r.get("bar_present") else 0,
        minute_bar_rows=int(r.get("minute_bar_rows") or 0),
        data_quality_blocks=tuple(data_quality_blocks),
    )
