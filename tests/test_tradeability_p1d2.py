"""DATA-R3-P1d.2 tests.

A1 real-DB minute-qualification adversarial cases (require the R2 ledgers on
disk; skipped when absent), plus pure-Python coverage of the P1d.2 semantics.
"""

import json
import os

import pytest

from stock_research.tradeability import (
    LedgerMinuteQualificationProvider,
    TradeabilityContext,
    tradeability_at,
)
import datetime as dt

LEDGER_BASE = "outputs/research/data01r1_finance_q2_20261020"
NEEDS_LEDGERS = pytest.mark.skipif(
    not os.path.exists(f"{LEDGER_BASE}/r2_downstream_minute_done.json"),
    reason="R2 minute ledgers not present")


def ctx(**kw):
    base = dict(
        asset_id="CN:SZ:000001",
        trade_date=dt.date(2021, 6, 15),
        list_date=dt.date(1991, 4, 3),
        symbol="000001", exchange="SZ",
        exchange_open=True, status_present=True, is_trade=True,
        is_st=False, is_suspended=False,
        stored_is_limit_up=False, stored_is_limit_down=False,
        status_source="baostock:test", bar_present=True, pct_chg=1.0,
        amount=1e8, trade_status="1", daily_bar_rows=1, minute_bar_rows=48,
    )
    base.update(kw)
    return TradeabilityContext(**base)


# --- A1: provider semantics (pure) -------------------------------------------


def test_provider_required_source_filter():
    prov = LedgerMinuteQualificationProvider(
        done_keys={"CN:SH:605077": {"CN:SH:605077|5min|akshare":
                                    {"factor_sig": "100:t0"}}},
        residual_gap_assets={"CN:SH:605077"})
    # alt-source qualifies the asset…
    q, src, ver, blocks = prov.verdict("CN:SH:605077")
    assert q is True and src == ("akshare",)
    # …but the baostock gap stays visible in audit blocks…
    assert "minute_factor_gap" in blocks
    # …and a baostock-required verdict fails closed.
    q2, src2, ver2, blocks2 = prov.verdict(
        "CN:SH:605077", required_source="baostock")
    assert q2 is False and ver2 == "required_source_missing"
    assert "required_source_missing" in blocks2


def test_provider_no_key_is_not_qualified():
    prov = LedgerMinuteQualificationProvider(
        done_keys={}, residual_gap_assets=set())
    q, src, ver, blocks = prov.verdict("CN:SH:600590")
    assert q is None and ver == "no_minute_key"  # unknown — never row-derived
    # through the context: provider configured + None verdict -> not ready
    c = ctx(asset_id="CN:SH:600590", minute_qualified=None,
            minute_provider_configured=True, minute_version="no_minute_key",
            minute_bar_rows=50000)
    r = tradeability_at(c, side="buy")
    assert r.data_ready_minute is False
    assert "no_minute_key" in r.restriction_reasons


def test_provider_none_verdict_never_falls_back_to_rows():
    c = ctx(minute_qualified=None, minute_provider_configured=True,
            minute_version="no_minute_key", minute_bar_rows=999999)
    r = tradeability_at(c, side="buy")
    assert r.data_ready_minute is False


def test_minute_date_level_rows_missing():
    # qualified key but zero minute rows on a day the stock actually traded
    c = ctx(minute_qualified=True, minute_provider_configured=True,
            minute_qualified_sources=("baostock",), minute_version="r2_minute_v1",
            minute_bar_rows=0, is_trade=True, status_present=True)
    r = tradeability_at(c, side="buy")
    assert r.data_ready_minute is False
    assert "minute_rows_missing_for_date" in r.restriction_reasons


def test_minute_zero_rows_ok_when_not_trading():
    # suspended day: zero minute rows is legitimate, key still qualified
    c = ctx(minute_qualified=True, minute_provider_configured=True,
            minute_qualified_sources=("baostock",), minute_version="r2_minute_v1",
            minute_bar_rows=0, is_trade=False, is_suspended=True,
            trade_status="0")
    r = tradeability_at(c, side="buy")
    assert r.data_ready_minute is True
    assert r.can_attempt_buy is False  # still suspended


def test_alt_source_keeps_gap_audit_marker():
    c = ctx(minute_qualified=True, minute_provider_configured=True,
            minute_qualified_sources=("akshare",), minute_version="r2_minute_v1",
            minute_bar_rows=40000,
            data_quality_blocks=("minute_factor_gap",))
    r = tradeability_at(c, side="buy")
    assert r.data_ready_minute is True
    assert "factor_gap_covered_by_alt_source" in r.restriction_reasons


# --- A1: real-DB adversarial checks ------------------------------------------


@NEEDS_LEDGERS
def test_real_ledger_post_diff_and_gap_sets():
    prov = LedgerMinuteQualificationProvider.from_repo(LEDGER_BASE)
    # 600153 stays isolated even though it may hold ledger keys
    q, src, ver, blocks = prov.verdict("CN:SH:600153")
    assert q is False and ver == "post_diff_isolated"
    # the 15 no-done-key assets never pass
    gap = set(json.load(open(f"{LEDGER_BASE}/factor_gap_155_reconciliation.json"))
              ["minute_residual_gap_assets"])
    done_led = json.load(open(f"{LEDGER_BASE}/r2_downstream_minute_done.json"))
    done_assets = {k.split("|")[0] for k in done_led}
    no_key = sorted(gap - done_assets)
    assert len(no_key) == 15
    for a in no_key:
        q, _, ver, _ = prov.verdict(a)
        assert q is False and ver == "factor_gap_residual"
    # alt-source covered assets qualify AND keep the gap marker
    alt = sorted(gap & done_assets)
    assert len(alt) == 59
    for a in alt:
        q, src, ver, blocks = prov.verdict(a)
        assert q is True and src and "minute_factor_gap" in blocks
        # but not when the gap source itself is required
        qb, _, verb, _ = prov.verdict(a, required_source="baostock")
        assert qb is False and verb == "required_source_missing"


@NEEDS_LEDGERS
def test_minute_universe_relationship_2293_vs_2308():
    import csv
    done_led = json.load(open(f"{LEDGER_BASE}/r2_downstream_minute_done.json"))
    done_assets = {k.split("|")[0] for k in done_led}
    assert len(done_led) == 3077 and len(done_assets) == 2293
    # matrix: minute-eligible == ledger-done set; all minute assets are
    # daily-eligible; the 15 no-key assets stay daily-but-not-minute.
    matrix = list(csv.DictReader(
        open("docs/research_upgrade/p1d/p1c_asset_key_matrix.csv")))
    daily = {r["asset_id"] for r in matrix
             if r["daily_research_eligible"] == "True"}
    minute = {r["asset_id"] for r in matrix
              if r["minute_research_eligible"] == "True"}
    assert minute == done_assets
    assert done_assets <= daily
    gap = set(json.load(open(f"{LEDGER_BASE}/factor_gap_155_reconciliation.json"))
              ["minute_residual_gap_assets"])
    no_key = gap - done_assets
    assert no_key <= daily and not (no_key & minute)


# --- A3: order-time lookahead guard ------------------------------------------


def test_open_order_ignores_future_close():
    # close hits the limit but open is below it and day is NOT one-way locked:
    # an open-time order must not be blocked by close-of-day information.
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=21.0,
            high_raw=22.0, low_raw=20.9, close_raw=22.0)
    r = tradeability_at(c, side="buy", order_time="open")
    assert r.can_attempt_buy is True
    assert r.details["information_tier"] == "open_pit"


def test_open_order_open_at_limit_is_restricted():
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=22.0,
            high_raw=22.0, low_raw=21.9, close_raw=22.0)
    r = tradeability_at(c, side="buy", order_time="open")
    assert r.can_attempt_buy is False


def test_open_order_oneway_lock_provable_not_expost():
    # a genuine all-day lock opens AT the limit — provable at the open,
    # restricted without any ex-post label.
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=22.0,
            high_raw=22.0, low_raw=22.0, close_raw=22.0)
    r = tradeability_at(c, side="buy", order_time="open")
    assert r.can_attempt_buy is False
    assert "ex_post_execution_assumption" not in r.restriction_reasons


def test_unknown_time_close_at_limit_not_blocked_without_open_proof():
    # order_time=unknown, open below the limit, day closes at limit but is
    # NOT one-way-locked: no provable restriction -> attemptable, and the
    # decision must not silently use close data (no ex-post label needed).
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=21.0,
            high_raw=22.0, low_raw=20.9, close_raw=22.0)
    r = tradeability_at(c, side="buy", order_time="unknown")
    assert r.can_attempt_buy is True
    assert r.details["ex_post_execution_assumption"] is False


def test_ex_post_branch_unreachable_on_coherent_bars():
    # ONE_WAY_LOCKED requires open==limit in classify_limit_day, so the
    # labelled ex-post policy branch cannot fire on coherent data: an
    # unknown-time order on a coherent one-way day is provably restricted
    # via the open-at-limit path, with NO ex-post label.
    c = ctx(pct_chg=10.0, preclose_raw=20.0, open_raw=22.0,
            high_raw=22.0, low_raw=22.0, close_raw=22.0)
    r = tradeability_at(c, side="buy", order_time="unknown")
    assert r.can_attempt_buy is False
    assert "ex_post_execution_assumption" not in r.restriction_reasons
    assert r.details["ex_post_execution_assumption"] is False


# ---------------------------------------------------------------------------
# B: consumer data chain — missing state must not silently pass
# ---------------------------------------------------------------------------

def test_constraints_block_missing_limit_state():
    from stock_research.backtest_constraints import (
        BacktestExecutionConstraints, can_close_long, can_open_long,
    )
    bar = {"trade_status": "1", "is_limit_up": False, "is_limit_down": False,
           "is_suspended": False, "limit_state_missing": True}
    default = BacktestExecutionConstraints()
    assert can_open_long(bar, default)[0] is True   # legacy default preserved
    strict = BacktestExecutionConstraints(block_missing_limit_state=True)
    allowed, reason = can_open_long(bar, strict)
    assert (allowed, reason) == (False, "limit_state_missing")
    allowed, reason = can_close_long(bar, strict)
    assert (allowed, reason) == (False, "limit_state_missing")
    bar["limit_state_missing"] = False
    assert can_open_long(bar, strict)[0] is True


def test_normalize_prices_computes_limit_state_missing():
    import pandas as pd
    from stock_research.vectorized_topn_backtest import _normalize_prices
    frame = pd.DataFrame({
        "trade_date": ["2024-01-02"] * 3,
        "asset_id": ["A", "B", "C"],
        "open": [10.0, 10.0, 10.0],
        "close": [10.0, 10.0, 10.0],
        "amount": [1e8, 1e8, 1e8],
        "trade_status": ["1", "1", "1"],
        "is_limit_up": [True, None, False],
        "is_limit_down": [False, None, False],
        "is_suspended": [False, None, False],
    })
    out = _normalize_prices(frame)
    # no limit_state_missing column -> computed from all-NaN flag rows
    assert out.loc[out.asset_id == "A", "limit_state_missing"].iloc[0] is False or \
        not bool(out.loc[out.asset_id == "A", "limit_state_missing"].iloc[0])
    assert bool(out.loc[out.asset_id == "B", "limit_state_missing"].iloc[0]) is True
    assert bool(out.loc[out.asset_id == "C", "limit_state_missing"].iloc[0]) is False
    # absent flag columns -> everything missing
    frame2 = frame.drop(columns=["is_limit_up", "is_limit_down", "is_suspended"])
    out2 = _normalize_prices(frame2)
    assert out2["limit_state_missing"].all()


def test_backtest_bar_status_flags_path():
    from stock_research.backtest import (
        BacktestBar, BacktestSelection, apply_buy_filter, sell_bar_for_holding,
    )
    sel = BacktestSelection("2024-01-02", "A", 1, 1.0, amount_20d_avg=1e9)
    missing = BacktestBar("A", "2024-01-02", 10.0, 9.0, 1e9, "1", False)
    assert missing.limit_state_missing is True  # fail-closed default
    d = apply_buy_filter(sel, missing, use_status_flags=True)
    assert (d.can_buy, d.skip_reason) == (False, "limit_state_missing")
    # legacy heuristic path unchanged
    d = apply_buy_filter(sel, missing)
    assert d.can_buy is False and d.skip_reason == "low_liquidity" or \
        d.skip_reason in {"limit_up_open", "low_liquidity"}
    flagged = BacktestBar("A", "2024-01-02", 10.0, 9.0, 1e9, "1", False,
                          is_limit_up=True, limit_state_missing=False)
    d = apply_buy_filter(sel, flagged, use_status_flags=True)
    assert (d.can_buy, d.skip_reason) == (False, "limit_up")
    ok = BacktestBar("A", "2024-01-03", 10.0, 9.0, 1e9, "1", False,
                     limit_state_missing=False)
    assert apply_buy_filter(sel, ok, use_status_flags=True).can_buy is True
    # sell roll-forward skips limit-down days when flags enabled
    bars = [BacktestBar("A", "2024-01-04", 10.0, 9.0, 1e9, "1", False,
                        is_limit_down=True, limit_state_missing=False),
            BacktestBar("A", "2024-01-05", 10.0, 9.0, 1e9, "1", False,
                        limit_state_missing=False)]
    got = sell_bar_for_holding(bars, "2024-01-03", 1, use_status_flags=True)
    assert got is not None and got.trade_date == "2024-01-05"


def test_dragon_limit_up_uses_historical_rules():
    import pandas as pd
    from stock_research.dragon_case_library import _is_limit_up
    rows = [
        # ChiNext post-reform: +9.6% is NOT a limit day (rule is 20%)
        ("300001.SZ", "2021-01-04", False, 0.096, False),
        # ChiNext post-reform: +19.9% IS a limit day
        ("300001.SZ", "2021-01-05", False, 0.199, True),
        # ChiNext pre-reform: +9.9% IS a limit day (10% rule)
        ("300001.SZ", "2019-01-04", False, 0.099, True),
        # ChiNext pre-reform ST: 5% rule — +9.9% is way over (limit)
        ("300001.SZ", "2019-01-07", True, 0.049, True),
        # ChiNext post-reform ST: 20% — +9.9% not a limit
        ("300001.SZ", "2021-01-08", True, 0.099, False),
        # main board normal: +9.9% is a limit (10% rule)
        ("600000.SH", "2021-01-04", False, 0.099, True),
        # pre-1996 no-limit era: +20% is NOT a limit day
        ("600000.SH", "1995-01-04", False, 0.20, False),
    ]
    frame = pd.DataFrame({
        "ts_code": [r[0] for r in rows],
        "is_st": [r[2] for r in rows],
        "trade_date": [r[1] for r in rows],
        "daily_return": [r[3] for r in rows],
    })
    out = _is_limit_up(frame)
    assert list(out) == [r[4] for r in rows]
    # traceability columns
    assert "limit_rule_id" in frame.columns
    assert frame.loc[0, "limit_rule_id"] == "chinext_20pct_from_20200824"
    assert frame.loc[6, "limit_rule_id"] == "pre_19961216_no_limit"


def test_dragon_limit_up_unverified_rule_fails_closed():
    import pandas as pd
    from stock_research.dragon_case_library import _is_limit_up
    frame = pd.DataFrame({
        "ts_code": ["600000.SH", "600000.SH"],
        "is_st": [True, True],
        "trade_date": ["1990-12-19", "not-a-date"],
        "daily_return": [0.10, 0.10],
    })
    out = _is_limit_up(frame)
    assert list(out) == [False, False]
    assert list(frame["limit_day_verified"]) == [False, False]
