"""P1d.1 adversarial gate tests (pure fixtures).

Covers the acceptance matrix in the P1d.1 spec §9: historical status_class
rules, real listing-session index, fail-closed semantics, legal-price limit
detection, order-time information constraints, minute-key gating, POST_DIFF
isolation, and idempotency. Real-DB boundary samples live in
tests/test_tradeability_p1d1_db.py and scripts/p1d1_audit.py.
"""

import datetime as dt

import pytest

from stock_research.tradeability import (
    LIMIT_RULES,
    RULE_UNKNOWN,
    Attemptability,
    Eligibility,
    LedgerMinuteQualificationProvider,
    LimitClass,
    TradeabilityContext,
    classify_limit_day,
    legal_limit_price,
    resolve_limit_rule,
    tradeability_at,
)


def ctx(**kw):
    base = dict(
        asset_id="CN:SZ:000001",
        trade_date=dt.date(2021, 6, 15),
        list_date=dt.date(1991, 4, 3),
        symbol="000001",
        exchange="SZ",
        exchange_open=True,
        listing_age_trading_days=7000,
        listing_age_known=True,
        status_present=True,
        is_trade=True,
        is_st=False,
        is_suspended=False,
        stored_is_limit_up=False,
        stored_is_limit_down=False,
        status_source="baostock:test",
        bar_present=True,
        preclose_raw=20.0,
        open_raw=20.2,
        high_raw=20.4,
        low_raw=20.0,
        close_raw=20.3,
        pct_chg=1.5,
        amount=1e8,
        trade_status="1",
        daily_bar_rows=1,
        minute_bar_rows=48,
        minute_qualified=True,
        minute_qualified_sources=("baostock",),
        minute_version="r2_minute_v1",
    )
    base.update(kw)
    return TradeabilityContext(**base)


# --- P0-A: historical status_class rules -------------------------------------


def test_chinext_st_was_5pct_before_20200824():
    # 深证上〔2020〕620号 第一条: reform-before ChiNext risk-warning = ±5%.
    c = ctx(asset_id="CN:SZ:300104", trade_date=dt.date(2020, 1, 15),
            symbol="300104", exchange="SZ", is_chinext=True, board="chinext",
            is_st=True)
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "chinext_st_5pct_pre_20200824"
    assert r.details["limit_up_pct"] == 5.0


def test_chinext_st_is_20pct_after_20200824():
    c = ctx(asset_id="CN:SZ:300104", trade_date=dt.date(2020, 9, 1),
            symbol="300104", exchange="SZ", is_chinext=True, board="chinext",
            is_st=True)
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "chinext_st_20pct_from_20200824"
    assert r.details["limit_up_pct"] == 20.0


def test_chinext_delisting_arrangement_crossing_reform_keeps_10pct():
    # Entered arrangement before 2020-08-24, still inside at reform -> ±10%
    # for the whole arrangement (620号 第一条).
    c = ctx(asset_id="CN:SZ:300090", trade_date=dt.date(2020, 9, 10),
            symbol="300090", exchange="SZ", is_chinext=True, board="chinext",
            delisting_arrangement_entered=dt.date(2020, 8, 10))
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "chinext_delist_arr_pre_reform_10pct"
    assert r.details["limit_up_pct"] == 10.0
    assert "delisting_arrangement_period" in r.restriction_reasons


def test_chinext_delisting_arrangement_entered_after_reform_is_20pct():
    c = ctx(asset_id="CN:SZ:300090", trade_date=dt.date(2021, 3, 1),
            symbol="300090", exchange="SZ", is_chinext=True, board="chinext",
            delisting_arrangement_entered=dt.date(2021, 2, 10))
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "chinext_delist_arr_post_reform_20pct"


def test_chinext_delisting_arrangement_unknown_entry_is_rule_unknown():
    c = ctx(asset_id="CN:SZ:300090", trade_date=dt.date(2020, 9, 10),
            symbol="300090", exchange="SZ", is_chinext=True, board="chinext",
            delisting_arrangement_entered=None,
            status_class_override="delisting_arrangement")
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "rule_unknown"
    assert r.buy_state == "UNKNOWN"


def test_main_board_prereg_ipo_day1_dedicated_cap():
    # Day-1 cap is +44%/-36%, not the ordinary 10%: +11% day-1 is NOT limit,
    # +44% day-1 IS limit-locked.
    c = ctx(trade_date=dt.date(2020, 5, 6), list_date=dt.date(2020, 5, 6),
            listing_event="ipo", listing_age_trading_days=1,
            preclose_raw=10.0, open_raw=12.0, high_raw=11.5, low_raw=11.0,
            close_raw=11.1, pct_chg=11.0)
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "main_ipo_day1_prereg_cap"
    assert r.limit_class_up == LimitClass.NOT_LIMIT.value
    assert r.can_attempt_buy is True

    c2 = ctx(trade_date=dt.date(2020, 5, 6), list_date=dt.date(2020, 5, 6),
             listing_event="ipo", listing_age_trading_days=1,
             preclose_raw=10.0, open_raw=12.0, high_raw=14.4, low_raw=11.8,
             close_raw=14.4, pct_chg=44.0)
    r2 = tradeability_at(c2, side="buy")
    assert r2.limit_class_up == LimitClass.CLOSE_AT_LIMIT.value
    assert r2.can_attempt_buy is False
    assert "limit_up" in r2.restriction_reasons


def test_main_board_prereg_ipo_day2_ordinary_10pct():
    c = ctx(trade_date=dt.date(2020, 5, 7), list_date=dt.date(2020, 5, 6),
            listing_event="ipo", listing_age_trading_days=2,
            preclose_raw=11.0, open_raw=12.0, high_raw=12.1, low_raw=11.9,
            close_raw=12.1, pct_chg=10.0)
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "main_ipo_day1_prereg_cap"  # ipo-event rule, 10% normal days
    assert r.can_attempt_buy is False  # +10% day2 = ordinary limit


def test_main_board_fullreg_ipo_first5_no_limit():
    c = ctx(trade_date=dt.date(2026, 4, 21), list_date=dt.date(2026, 4, 21),
            listing_event="ipo", listing_age_trading_days=1,
            preclose_raw=None, pct_chg=66.32,
            open_raw=30.0, high_raw=35.0, low_raw=28.0, close_raw=33.5)
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "main_ipo_fullreg_window5"
    assert r.limit_class_up == LimitClass.NO_LIMIT_REGIME.value
    assert r.can_attempt_buy is True


def test_star_ipo_day5_and_day6_boundary():
    base = dict(asset_id="CN:SH:688001", symbol="688001", exchange="SH",
                is_star=True, board="star", list_date=dt.date(2020, 7, 16),
                listing_event="ipo", preclose_raw=50.0)
    d5 = ctx(trade_date=dt.date(2020, 7, 23), listing_age_trading_days=5,
             pct_chg=25.0, open_raw=55.0, high_raw=62.5, low_raw=54.0,
             close_raw=62.5, **base)
    r5 = tradeability_at(d5, side="buy")
    assert r5.limit_class_up == LimitClass.NO_LIMIT_REGIME.value
    assert r5.can_attempt_buy is True
    d6 = ctx(trade_date=dt.date(2020, 7, 24), listing_age_trading_days=6,
             pct_chg=20.0, open_raw=58.0, high_raw=60.0, low_raw=57.0,
             close_raw=60.0, **base)
    r6 = tradeability_at(d6, side="buy")
    assert r6.limit_class_up == LimitClass.CLOSE_AT_LIMIT.value
    assert r6.can_attempt_buy is False


def test_beijing_day1_no_limit_then_30pct():
    base = dict(asset_id="CN:BJ:830799", symbol="830799", exchange="BJ",
                is_beijing=True, board="beijing", list_date=dt.date(2021, 11, 15),
                listing_event="ipo")
    d1 = ctx(trade_date=dt.date(2021, 11, 15), listing_age_trading_days=1,
             pct_chg=180.0, open_raw=30.0, high_raw=50.0, low_raw=28.0,
             close_raw=48.0, **base)
    r1 = tradeability_at(d1, side="buy")
    assert r1.limit_rule_id == "beijing_ipo_day1_no_limit"
    assert r1.can_attempt_buy is True
    dn = ctx(trade_date=dt.date(2021, 11, 16), listing_age_trading_days=2,
             pct_chg=30.0, preclose_raw=48.0, open_raw=60.0, high_raw=62.4,
             low_raw=59.0, close_raw=62.4, **base)
    rn = tradeability_at(dn, side="buy")
    assert rn.limit_rule_id == "beijing_30pct_since_20211115"
    assert rn.can_attempt_buy is False


def test_main_delisting_arrangement_is_10pct():
    c = ctx(delisting_arrangement_entered=dt.date(2021, 6, 1),
            trade_date=dt.date(2021, 6, 15))
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "main_delisting_arrangement_10pct"


def test_unknown_special_case_is_not_silently_tradable():
    rule = resolve_limit_rule(board="main", status_class="relisting_unknown_class",
                              event_class="continuous", trade_date=dt.date(2021, 6, 15))
    assert rule is RULE_UNKNOWN
    c = ctx(status_class_override="relisting_unknown_class")
    r = tradeability_at(c, side="buy")
    assert r.buy_state == "UNKNOWN"
    assert r.can_attempt_buy is False
    assert "rule_unknown" in r.restriction_reasons


# --- P0-B: real listing-session index ----------------------------------------


def test_listing_age_window_spanning_weekend():
    # IPO Friday 2020-07-17; sessions: 17,20,21,22,23 are the first 5.
    # Session 5 is Thursday 23rd — inside window. Session 6 Monday 27th — out.
    base = dict(asset_id="CN:SH:688002", symbol="688002", exchange="SH",
                is_star=True, board="star", list_date=dt.date(2020, 7, 17),
                listing_event="ipo", preclose_raw=50.0)
    s5 = ctx(trade_date=dt.date(2020, 7, 23), listing_age_trading_days=5,
             pct_chg=25.0, close_raw=62.5, high_raw=62.5, open_raw=55.0,
             low_raw=54.0, **base)
    assert tradeability_at(s5, side="buy").limit_class_up == LimitClass.NO_LIMIT_REGIME.value
    s6 = ctx(trade_date=dt.date(2020, 7, 27), listing_age_trading_days=6,
             pct_chg=20.0, close_raw=60.0, high_raw=60.0, open_raw=58.0,
             low_raw=57.0, **base)
    r6 = tradeability_at(s6, side="buy")
    assert r6.limit_class_up == LimitClass.CLOSE_AT_LIMIT.value
    assert r6.can_attempt_buy is False


def test_listing_age_unknown_fails_closed_not_normal_rule():
    # Window rule resolvable but session index unknowable -> UNKNOWN, not
    # silently "normal limit applies".
    c = ctx(asset_id="CN:SH:688003", symbol="688003", exchange="SH",
            is_star=True, board="star", list_date=dt.date(2020, 7, 10),
            listing_event="ipo", trade_date=dt.date(2020, 7, 16),
            listing_age_trading_days=None, listing_age_known=False,
            pct_chg=25.0, close_raw=62.5, high_raw=62.5, open_raw=55.0, low_raw=54.0,
            preclose_raw=50.0)
    r = tradeability_at(c, side="buy")
    assert r.buy_state == "UNKNOWN"
    assert r.can_attempt_buy is False
    assert "listing_session_index_unknown" in r.restriction_reasons


# --- P0-C: fail-closed tri-state ---------------------------------------------


def test_missing_list_date_universe_unknown():
    c = ctx(list_date=None)
    r = tradeability_at(c, side="buy")
    assert r.universe_state == "UNKNOWN"
    assert r.eligible_for_universe is None
    assert r.can_attempt_buy is False


def test_missing_calendar_universe_unknown():
    c = ctx(exchange_open=None)
    r = tradeability_at(c, side="buy")
    assert r.universe_state == "UNKNOWN"
    assert "exchange_calendar_missing" in r.restriction_reasons
    assert r.buy_state == "UNKNOWN"


def test_missing_status_row_unknown_not_warning():
    c = ctx(status_present=False, is_st=None, is_suspended=None, is_trade=None,
            trade_status=None)
    r = tradeability_at(c, side="buy")
    assert r.buy_state == "UNKNOWN"
    assert "status_row_missing" in r.restriction_reasons
    assert r.can_attempt_buy is False


def test_missing_bar_unknown_not_tradable():
    c = ctx(bar_present=False, daily_bar_rows=0, open_raw=None, high_raw=None,
            low_raw=None, close_raw=None, pct_chg=None)
    r = tradeability_at(c, side="buy")
    assert r.buy_state == "UNKNOWN"
    assert r.can_attempt_buy is False


def test_suspended_is_restricted_not_unknown():
    c = ctx(is_suspended=True, is_trade=False, trade_status="0")
    r = tradeability_at(c, side="buy")
    assert r.buy_state == "RESTRICTED"
    assert "suspended" in r.restriction_reasons


# --- P0-D: legal price + order-time ------------------------------------------


def test_legal_limit_price_rounding():
    # 8.99 * 1.10 = 9.889 -> legal 9.89 (round to 0.01 tick)
    assert legal_limit_price(8.99, 10.0, "up") == 9.89
    assert legal_limit_price(8.99, 10.0, "down") == 8.09
    assert legal_limit_price(None, 10.0, "up") is None


def test_near_pct_but_below_legal_price_is_not_limit():
    # pct_chg 9.97% but close 21.96 < legal 22.00 -> NOT limit (proves the
    # band-based shortcut would over-report).
    c = ctx(pct_chg=9.8, preclose_raw=20.0, open_raw=21.5, high_raw=21.98,
            low_raw=21.4, close_raw=21.96)
    r = tradeability_at(c, side="buy")
    assert r.limit_class_up == LimitClass.NOT_LIMIT.value
    assert r.can_attempt_buy is True


def test_one_way_locked_distinguished():
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=22.0, high_raw=22.0,
            low_raw=22.0, close_raw=22.0)
    r = tradeability_at(c, side="buy")
    assert r.limit_class_up == LimitClass.ONE_WAY_LOCKED.value
    assert r.can_attempt_buy is False


def test_touched_intraday_but_closed_off_is_not_blocked():
    c = ctx(pct_chg=8.0, preclose_raw=20.0, open_raw=21.5, high_raw=22.0,
            low_raw=21.3, close_raw=21.6)
    r = tradeability_at(c, side="buy")
    assert r.limit_class_up == LimitClass.TOUCHED_INTRADAY_ONLY.value
    assert r.can_attempt_buy is True  # queue could have filled at limit print


def test_pct_only_near_limit_is_unverified_and_restricted():
    c = ctx(pct_chg=10.02, open_raw=None, high_raw=None, low_raw=None,
            close_raw=None, preclose_raw=None)
    r = tradeability_at(c, side="buy")
    assert r.limit_class_up == LimitClass.PCT_NEAR_LIMIT_UNVERIFIED.value
    assert r.can_attempt_buy is False
    assert "possible_limit_lock_unverified" in r.restriction_reasons


def test_open_order_cannot_use_same_day_close():
    # Day ends at limit but opened off-limit: an 'open' order was fillable.
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=21.5, high_raw=22.0,
            low_raw=21.4, close_raw=22.0)
    r_close = tradeability_at(c, side="buy", order_time="close")
    assert r_close.can_attempt_buy is False
    r_open = tradeability_at(c, side="buy", order_time="open")
    assert r_open.can_attempt_buy is True  # close-at-limit is future data at open
    # But a one-way-locked day restricts even the open order.
    c2 = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=22.0, high_raw=22.0,
             low_raw=22.0, close_raw=22.0)
    r_open2 = tradeability_at(c2, side="buy", order_time="open")
    assert r_open2.can_attempt_buy is False


def test_buy_and_sell_sides_independent():
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=21.9, high_raw=22.0,
            low_raw=21.8, close_raw=22.0)
    r = tradeability_at(c, side="buy")
    assert r.can_attempt_buy is False
    assert r.sell_state == "ATTEMPTABLE"  # limit-up day does not restrict sell


# --- P0-E: minute qualification binding --------------------------------------


def test_minute_gap_asset_not_released_by_rowcount_or_feature_pin():
    c = ctx(asset_id="CN:SH:603213", minute_bar_rows=33408,
            minute_qualified=False, minute_qualified_sources=(),
            minute_version="factor_gap_residual",
            data_quality_blocks=("minute_factor_gap",))
    r = tradeability_at(c, side="buy", data_version="full_history_v1")
    assert r.data_ready_minute is False
    assert r.data_ready_daily is True
    assert "residual_factor_gap_minute" in r.restriction_reasons


def test_minute_qualified_alt_source_reported():
    c = ctx(asset_id="CN:SH:605077", minute_qualified=True,
            minute_qualified_sources=("akshare",), minute_version="r2_minute_v1",
            minute_bar_rows=40000)
    r = tradeability_at(c, side="buy")
    assert r.data_ready_minute is True
    assert r.details["minute_qualified_sources"] == ["akshare"]


def test_minute_no_done_key_not_released_by_rows():
    c = ctx(asset_id="CN:SH:600590", minute_bar_rows=50000,
            minute_qualified=False, minute_qualified_sources=(),
            minute_version="no_minute_key")
    r = tradeability_at(c, side="buy")
    assert r.data_ready_minute is False


def test_post_diff_asset_stays_isolated():
    prov = LedgerMinuteQualificationProvider(
        done_keys={"CN:SH:600153": ["CN:SH:600153|5min|baostock"]},
        residual_gap_assets=set(),
        post_diff_assets={"CN:SH:600153"})
    q, src, ver, blocks = prov.verdict("CN:SH:600153")
    assert q is False and "post_diff_isolated" in blocks


def test_ledger_provider_verdicts():
    prov = LedgerMinuteQualificationProvider(
        done_keys={"CN:SH:600001": ["CN:SH:600001|5min|baostock",
                                    "CN:SH:600001|5min|akshare"],
                   "CN:SH:605077": ["CN:SH:605077|5min|akshare"]},
        residual_gap_assets={"CN:SH:605077", "CN:SH:600590"})
    q1, s1, _, b1 = prov.verdict("CN:SH:600001")
    assert q1 is True and set(s1) == {"baostock", "akshare"} and not b1
    q2, s2, _, b2 = prov.verdict("CN:SH:605077")  # alt-source covered
    assert q2 is True and s2 == ("akshare",) and b2 == ("minute_factor_gap",)
    q3, s3, v3, _ = prov.verdict("CN:SH:600590")  # terminal gap, no key
    assert q3 is False and v3 == "factor_gap_residual"
    q4, _, v4, _ = prov.verdict("CN:SH:999999")  # unknown asset
    assert q4 is None and v4 == "no_minute_key"


# --- misc gates ---------------------------------------------------------------


def test_idempotent_repeatable():
    c = ctx(pct_chg=10.0)
    assert tradeability_at(c, side="buy") == tradeability_at(c, side="buy")


def test_boolean_mirrors_map_unknown_fail_closed():
    c = ctx(exchange_open=None)
    r = tradeability_at(c, side="buy")
    assert r.eligible_for_universe is None   # UNKNOWN mirror
    assert r.can_attempt_buy is False        # fail-closed
    assert r.can_attempt_sell is False
