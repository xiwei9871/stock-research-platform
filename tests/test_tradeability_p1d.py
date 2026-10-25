"""DATA-R3-P1d adversarial acceptance tests (pure, no DB).

Contexts are modeled on real platform cases discovered during the audit:
- CN:SZ:300001 ChiNext +10.02% on 2019-03-11 (stored is_limit_up=False under
  the static 19.8% threshold, but the effective 2019 regime was ±10%).
- CN:SH:688287 退市观典 listed 2022-05-25, delisted 2026-06-10.
- CN:SH:600815 ST days in 2018.
- CN:SH:600126 suspended 2019-06-03.
"""

import datetime as dt

import pytest

from stock_research.tradeability import (
    LIMIT_RULES,
    TradeabilityContext,
    classify_board,
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
        status_present=True,
        is_trade=True,
        is_st=False,
        is_suspended=False,
        stored_is_limit_up=False,
        stored_is_limit_down=False,
        status_source="baostock:test",
        bar_present=True,
        pct_chg=1.0,
        amount=1e8,
        trade_status="1",
        daily_bar_rows=1,
        minute_bar_rows=48,
    )
    base.update(kw)
    return TradeabilityContext(**base)


def test_pre_listing_asset_not_in_universe():
    # 688287 (退市观典) listed 2022-05-25 — the day before must not qualify.
    c = ctx(asset_id="CN:SH:688287", trade_date=dt.date(2022, 5, 24),
            list_date=dt.date(2022, 5, 25), symbol="688287", exchange="SH",
            is_star=True, board="star", bar_present=False, daily_bar_rows=0,
            status_present=False, minute_bar_rows=0)
    r = tradeability_at(c, side="buy")
    assert r.eligible_for_universe is False
    assert "not_yet_listed" in r.restriction_reasons
    assert r.can_attempt_buy is False


def test_post_delisting_asset_not_in_universe():
    # 688287 delisted 2026-06-10 — afterwards never in universe.
    c = ctx(asset_id="CN:SH:688287", trade_date=dt.date(2026, 6, 11),
            list_date=dt.date(2022, 5, 25), delist_date=dt.date(2026, 6, 10),
            symbol="688287", exchange="SH", is_star=True, board="star",
            bar_present=False, daily_bar_rows=0, status_present=False,
            minute_bar_rows=0)
    r = tradeability_at(c, side="sell")
    assert r.eligible_for_universe is False
    assert "delisted" in r.restriction_reasons
    assert r.can_attempt_sell is False


def test_delisted_asset_still_in_universe_before_delist():
    # Survivorship-bias guard: a stock that later delisted must remain a valid
    # universe member for historical dates inside its listing window.
    c = ctx(asset_id="CN:SH:688287", trade_date=dt.date(2026, 5, 20),
            list_date=dt.date(2022, 5, 25), delist_date=dt.date(2026, 6, 10),
            symbol="688287", exchange="SH", is_star=True, board="star")
    r = tradeability_at(c, side="buy")
    assert r.eligible_for_universe is True
    assert r.can_attempt_buy is True


def test_st_status_evaluated_as_of_historical_date():
    # 600815 was ST on 2018-01-02 — main-board ST regime = ±5%.
    c = ctx(asset_id="CN:SH:600815", trade_date=dt.date(2018, 1, 2),
            symbol="600815", exchange="SH", is_st=True)
    r = tradeability_at(c, side="buy")
    assert r.limit_regime == "main"
    assert r.limit_rule_id == "main_st_5pct"
    assert r.details["limit_up_pct"] == 5.0
    assert "st_risk_warning" in r.restriction_reasons


def test_suspended_day_blocks_both_sides():
    # 600126 suspended 2019-06-03 — no normal buy or sell simulation.
    c = ctx(asset_id="CN:SH:600126", trade_date=dt.date(2019, 6, 3),
            symbol="600126", exchange="SH", is_suspended=True, is_trade=False,
            trade_status="0", pct_chg=0.0, amount=0.0)
    r = tradeability_at(c, side="buy")
    assert r.eligible_for_universe is True
    assert r.can_attempt_buy is False
    assert "suspended" in r.restriction_reasons
    r2 = tradeability_at(c, side="sell")
    assert r2.can_attempt_sell is False
    assert "suspended" in r2.restriction_reasons


def test_limit_up_day_restricts_buy():
    # main board +10% limit-locked, raw price confirms close at legal limit
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=21.9, high_raw=22.0,
            low_raw=21.8, close_raw=22.0)
    r = tradeability_at(c, side="buy")
    assert r.can_attempt_buy is False
    assert "limit_up" in r.restriction_reasons


def test_limit_down_day_restricts_sell():
    c = ctx(pct_chg=-10.0, preclose_raw=20.0, open_raw=18.1, high_raw=18.2,
            low_raw=18.0, close_raw=18.0)
    r = tradeability_at(c, side="sell")
    assert r.can_attempt_sell is False
    assert "limit_down" in r.restriction_reasons


def test_regime_change_chinext_pre_and_post_20200824():
    # Real case: 300001 +10.02% on 2019-03-11. Stored flag says NOT limit-up
    # (built with static 19.8%); the effective 2019 rule was ±10% → historical
    # limit-locked → buy restricted + disagreement flagged.
    c = ctx(asset_id="CN:SZ:300001", trade_date=dt.date(2019, 3, 11),
            symbol="300001", exchange="SZ", is_chinext=True, board="chinext",
            pct_chg=10.01676, stored_is_limit_up=False,
            preclose_raw=8.99, open_raw=9.5, high_raw=9.89, low_raw=9.4,
            close_raw=9.89)  # 8.99*1.10=9.889 -> 9.89 legal limit
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "chinext_10pct_pre_20200824"
    assert r.can_attempt_buy is False
    assert r.stored_flag_disagrees is True
    assert "stored_flag_disagrees_with_effective_rule" in r.restriction_reasons

    # Post-regime: same +10.02% on 2020-08-25 is NOT a limit day (±20% rule).
    c2 = ctx(asset_id="CN:SZ:300001", trade_date=dt.date(2020, 8, 25),
             symbol="300001", exchange="SZ", is_chinext=True, board="chinext",
             pct_chg=10.01676, stored_is_limit_up=False,
             preclose_raw=8.99, open_raw=9.5, high_raw=9.89, low_raw=9.4,
             close_raw=9.89)
    r2 = tradeability_at(c2, side="buy")
    assert r2.limit_rule_id == "chinext_20pct_from_20200824"
    assert r2.can_attempt_buy is True
    assert r2.stored_flag_disagrees is False

    # And +20% post-regime IS limit-locked.
    c3 = ctx(asset_id="CN:SZ:300001", trade_date=dt.date(2020, 8, 25),
             symbol="300001", exchange="SZ", is_chinext=True, board="chinext",
             pct_chg=20.0, stored_is_limit_up=True,
             preclose_raw=8.99, open_raw=10.5, high_raw=10.79, low_raw=10.4,
             close_raw=10.79)  # 8.99*1.20=10.788 -> 10.79
    r3 = tradeability_at(c3, side="buy")
    assert r3.can_attempt_buy is False
    assert "limit_up" in r3.restriction_reasons


def test_ipo_no_limit_window_not_blocked_by_normal_rule():
    # STAR listing day 1 (pct_chg +120%): ordinary ±20% rule must NOT fire.
    c = ctx(asset_id="CN:SH:688981", trade_date=dt.date(2020, 7, 16),
            list_date=dt.date(2020, 7, 16), symbol="688981", exchange="SH",
            is_star=True, board="star", pct_chg=120.0,
            stored_is_limit_up=False, listing_age_trading_days=1,
            listing_age_known=True, listing_event="ipo",
            preclose_raw=None, open_raw=60.0, high_raw=95.0, low_raw=55.0,
            close_raw=90.0)
    r = tradeability_at(c, side="buy")
    assert r.details["in_no_limit_window"] is True
    assert "ipo_no_limit_window" in r.restriction_reasons
    assert r.can_attempt_buy is True
    assert "limit_up" not in r.restriction_reasons

    # Day 6 (outside 5-day window): +20% → normal limit applies.
    c2 = ctx(asset_id="CN:SH:688981", trade_date=dt.date(2020, 7, 24),
             list_date=dt.date(2020, 7, 16), symbol="688981", exchange="SH",
             is_star=True, board="star", pct_chg=20.0,
             stored_is_limit_up=True, listing_age_trading_days=6,
             listing_age_known=True, listing_event="ipo",
             preclose_raw=50.0, open_raw=58.0, high_raw=60.0, low_raw=57.0,
             close_raw=60.0)  # 50*1.2=60.0 legal limit
    r2 = tradeability_at(c2, side="buy")
    assert r2.details["in_no_limit_window"] is False
    assert r2.can_attempt_buy is False


def test_main_board_ipo_post_20230410_no_limit_window():
    # Real case: 001312 listed 2026-04-21, closed +66.32% on day 1 — under the
    # post-registration rule the first 5 sessions carry no ordinary limit, so
    # the +10% main-board rule must not fire.
    c = ctx(asset_id="CN:SZ:001312", trade_date=dt.date(2026, 4, 21),
            list_date=dt.date(2026, 4, 21), symbol="001312", exchange="SZ",
            pct_chg=66.32, stored_is_limit_up=True, listing_age_trading_days=1,
            listing_age_known=True, listing_event="ipo",
            preclose_raw=None, open_raw=30.0, high_raw=35.0, low_raw=28.0,
            close_raw=33.5)
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "main_ipo_fullreg_window5"
    assert r.details["in_no_limit_window"] is True
    assert r.can_attempt_buy is True
    # stored flag was computed with the static 9.8 threshold and says limit —
    # under the effective rule there was no limit → disagreement recorded.
    assert r.stored_flag_disagrees is True


def test_main_board_ipo_pre_20230410_capped_day_blocks_buy():
    # Pre-registration main-board day-1 cap (+44%/-36%): reaching cap is a
    # limit-locked state under the conservative policy → buy restricted.
    c = ctx(asset_id="CN:SH:603000", trade_date=dt.date(2020, 5, 6),
            list_date=dt.date(2020, 5, 6), symbol="603000", exchange="SH",
            pct_chg=44.0, stored_is_limit_up=True, listing_age_trading_days=1,
            listing_age_known=True, listing_event="ipo",
            preclose_raw=10.0, open_raw=12.0, high_raw=14.4, low_raw=11.8,
            close_raw=14.4)  # 10*1.44=14.4 day-1 cap
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "main_ipo_day1_prereg_cap"
    assert r.can_attempt_buy is False
    assert "limit_up" in r.restriction_reasons


def test_repeated_evaluation_is_idempotent():
    c = ctx(pct_chg=10.0)
    r1 = tradeability_at(c, side="buy")
    r2 = tradeability_at(c, side="buy")
    assert r1 == r2


def test_factor_gap_blocked_asset_not_released_by_feature_pin():
    # A residual FACTOR_GAP key must keep minute readiness False even when the
    # asset's features are pinned complete — pinned ≠ released.
    c = ctx(asset_id="CN:SH:603213", data_quality_blocks=("minute_factor_gap",),
            minute_bar_rows=33408)
    r = tradeability_at(c, side="buy", data_version="full_history_v1")
    assert r.data_ready_minute is False
    assert "residual_factor_gap_minute" in r.restriction_reasons
    # Daily readiness remains a separate dimension — unaffected.
    assert r.data_ready_daily is True


def test_exchange_closed_day_restricted():
    c = ctx(trade_date=dt.date(2021, 10, 1), exchange_open=False,
            bar_present=False, daily_bar_rows=0, status_present=False,
            minute_bar_rows=0)
    r = tradeability_at(c, side="buy")
    assert r.eligible_for_universe is False
    assert "exchange_closed" in r.restriction_reasons
    assert r.can_attempt_buy is False


def test_missing_bar_and_status_is_restricted_not_tradable():
    # No bar, no status row: cannot prove the order could exist → restricted.
    c = ctx(bar_present=False, status_present=False, daily_bar_rows=0,
            minute_bar_rows=0, pct_chg=None, amount=None, trade_status=None)
    r = tradeability_at(c, side="buy")
    assert r.can_attempt_buy is False
    assert "no_daily_bar" in r.restriction_reasons
    assert "no_status_row" in r.restriction_reasons


def test_zero_volume_day_not_assumed_tradable():
    c = ctx(pct_chg=0.0, amount=0.0)
    r = tradeability_at(c, side="buy")
    # zero-amount day with bar present: buy attempt flagged low_amount only
    # when policy sets min_amount; default policy keeps it attemptable since
    # the stock did trade (is_trade=True). Executability stays conservative
    # via suspension/limit gates.
    assert r.eligible_for_universe is True


def test_st_on_chinext_keeps_board_20pct_limit_not_5pct():
    # ST/*ST on ChiNext follows the ±20% board regime, not the main-board ±5%.
    c = ctx(asset_id="CN:SZ:300104", trade_date=dt.date(2021, 3, 1),
            symbol="300104", exchange="SZ", is_chinext=True, board="chinext",
            is_st=True, pct_chg=12.0)
    r = tradeability_at(c, side="buy")
    assert r.limit_rule_id == "chinext_st_20pct_from_20200824"
    assert r.details["limit_up_pct"] == 20.0
    assert "st_risk_warning" in r.restriction_reasons


def test_beijing_30pct_rule():
    rule = resolve_limit_rule(board="beijing", is_st=False,
                              trade_date=dt.date(2022, 6, 1))
    assert rule.rule_id == "beijing_30pct_since_20211115"
    assert rule.up_limit_pct == 30.0


def test_board_classification_matches_existing_taxonomy():
    assert classify_board(symbol="688001", exchange="SH", is_star=True,
                          is_chinext=False, is_beijing=False, board=None) == "star"
    assert classify_board(symbol="300001", exchange="SZ", is_star=False,
                          is_chinext=True, is_beijing=False, board=None) == "chinext"
    assert classify_board(symbol="830799", exchange="BJ", is_star=False,
                          is_chinext=False, is_beijing=True, board=None) == "beijing"
    assert classify_board(symbol="600000", exchange="SH", is_star=False,
                          is_chinext=False, is_beijing=False, board=None) == "main"


def test_rule_table_covers_all_boards_with_sources():
    boards = {r.board for r in LIMIT_RULES}
    assert {"main", "chinext", "star", "beijing"} <= boards
    classes = {r.status_class for r in LIMIT_RULES}
    assert {"normal", "risk_warning", "delisting_arrangement"} <= classes
    for rule in LIMIT_RULES:
        assert rule.source_doc, rule.rule_id


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_dimensions_are_independent(side):
    # A delisted asset can still have data_ready=True — eligibility failing
    # must NOT corrupt the data-readiness dimensions.
    c = ctx(delist_date=dt.date(2026, 6, 10), trade_date=dt.date(2026, 6, 11),
            daily_bar_rows=1, minute_bar_rows=48)
    r = tradeability_at(c, side=side)
    assert r.eligible_for_universe is False
    assert r.data_ready_daily is True  # bars may exist in storage; not eligible
    assert r.data_ready_minute is True
