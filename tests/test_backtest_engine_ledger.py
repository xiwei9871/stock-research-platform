import math

import pandas as pd
import pytest

from stock_research.backtest_engine import (
    ContractError,
    RealisticExecutionConfig,
    execute_target_weights,
    summarize,
)

DAYS = ["2023-08-21", "2023-08-22", "2023-08-23", "2023-08-24", "2023-08-25",
        "2023-08-28", "2023-08-29", "2023-08-30"]


def series(asset, closes, opens=None, *, start=0, suspended=None, adj=None,
           preclose=None, limit_pct=10.0, base_preclose=None):
    """Raw daily bars; preclose defaults to the previous raw close."""
    rows = []
    prev = base_preclose if base_preclose is not None else closes[0]
    for k, close in enumerate(closes):
        day = DAYS[start + k]
        pc = preclose[k] if preclose and preclose[k] is not None else prev
        op = opens[k] if opens else close
        rows.append({
            "trade_date": day, "asset_id": asset, "open": op, "high": max(op, close),
            "low": min(op, close), "close": close, "volume": 1e6, "preclose": pc,
            "is_suspended": suspended[k] if suspended else False,
            "limit_up_price": round(pc * (1 + limit_pct / 100) + 1e-9, 2),
            "limit_down_price": round(pc * (1 - limit_pct / 100) + 1e-9, 2),
            "adj_factor": adj[k] if adj else 1.0,
        })
        prev = close
    return rows


def bars(*groups):
    return pd.DataFrame([row for group in groups for row in group])


def targets(rows):
    return pd.DataFrame(
        [{"signal_date": d, "asset_id": a, "target_weight": w, "strategy_id": "t"} for d, a, w in rows]
    )


def run(tw, px, **cfg):
    config = RealisticExecutionConfig(**cfg)
    return execute_target_weights(tw, px, DAYS, config), config


def trades_of(result, side=None):
    t = result["trades"]
    return t if side is None else t[t["side"] == side]


NO_COST = dict(commission_bps=0.0, min_commission=0.0, slippage_bps=0.0)


def test_t01_signal_on_t_fills_on_t_plus_1_open():
    px = bars(series("A", [10, 10, 11, 11], opens=[10, 10.5, 11, 11]))
    res, _ = run(targets([(DAYS[0], "A", 1.0)]), px, **NO_COST)
    buys = trades_of(res, "buy")
    assert list(buys["execution_date"]) == [DAYS[1]]
    assert buys.iloc[0]["fill_price"] == pytest.approx(10.5)
    assert res["equity"].iloc[0]["market_value"] == 0.0


def test_t02_weights_drift_with_prices():
    px = bars(series("A", [10, 10, 10, 10]), series("B", [10, 10, 12, 12]))
    res, _ = run(targets([(DAYS[0], "A", 0.5), (DAYS[0], "B", 0.5)]), px, **NO_COST)
    pos = res["positions"]
    b1 = pos[(pos.date == DAYS[1]) & (pos.asset_id == "B")].iloc[0]
    b2 = pos[(pos.date == DAYS[2]) & (pos.asset_id == "B")].iloc[0]
    assert b1["weight"] == pytest.approx(0.5, abs=1e-3)
    assert b2["weight"] == pytest.approx(12 / 22, abs=1e-3)
    assert not (trades_of(res)["execution_date"] == DAYS[2]).any()


def test_t03_limit_up_open_blocks_buy_and_keeps_cash():
    px = bars(series("A", [10, 11, 11], opens=[10, 11, 11]))
    res, cfg = run(targets([(DAYS[0], "A", 1.0)]), px, **NO_COST)
    row = trades_of(res, "buy").iloc[0]
    assert row["execution_status"] == "rejected"
    assert row["rejection_reason"] == "limit_up_at_fill"
    assert res["equity"].iloc[-1]["cash"] == pytest.approx(cfg.initial_cash)


def test_t04_limit_down_keeps_position_and_retries():
    px = bars(series("A", [10, 10, 9, 9.5], opens=[10, 10, 9, 9.2]))
    tw = targets([(DAYS[0], "A", 1.0)])
    tw = pd.concat([tw, pd.DataFrame([{"signal_date": DAYS[1], "asset_id": "A",
                                       "target_weight": 0.0, "strategy_id": "t"}])])
    res, _ = run(tw, px, **NO_COST)
    sells = trades_of(res, "sell")
    assert list(sells["execution_status"]) == ["rejected", "filled"]
    assert sells.iloc[0]["rejection_reason"] == "limit_down_at_fill"
    assert sells.iloc[1]["execution_date"] == DAYS[3]
    pos = res["positions"]
    assert (pos.date == DAYS[2]).any() and not (pos.date == DAYS[3]).any()


def test_t05_suspended_does_not_trade():
    px = bars(series("A", [10, 10, 10], suspended=[False, True, False]))
    res, _ = run(targets([(DAYS[0], "A", 1.0)]), px, **NO_COST)
    assert trades_of(res, "buy").iloc[0]["rejection_reason"] == "suspended"


def test_t06_stamp_duty_switches_on_2023_08_28():
    px = bars(series("A", [10] * 8))
    tw = targets([(DAYS[0], "A", 1.0), (DAYS[3], "A", 0.5), (DAYS[4], "A", 0.0)])
    res, _ = run(tw, px, commission_bps=0.0, min_commission=0.0, slippage_bps=0.0)
    sells = trades_of(res, "sell").set_index("execution_date")
    before = sells.loc[DAYS[4]]  # 2023-08-25
    after = sells.loc[DAYS[5]]   # 2023-08-28
    assert before["stamp_duty"] == pytest.approx(before["transaction_value"] * 10e-4)
    assert after["stamp_duty"] == pytest.approx(after["transaction_value"] * 5e-4)


def test_t07_non_equal_weights():
    px = bars(series("A", [10] * 3), series("B", [20] * 3))
    res, cfg = run(targets([(DAYS[0], "A", 0.6), (DAYS[0], "B", 0.3)]), px, **NO_COST)
    pos = res["positions"][res["positions"].date == DAYS[1]].set_index("asset_id")
    assert pos.loc["A", "weight"] == pytest.approx(0.6, abs=1e-3)
    assert pos.loc["B", "weight"] == pytest.approx(0.3, abs=1e-3)
    assert res["equity"].iloc[1]["cash"] == pytest.approx(0.1 * cfg.initial_cash, rel=1e-2)


def test_t08_insufficient_cash_never_goes_negative():
    px = bars(series("A", [99.9] * 3))
    res, _ = run(targets([(DAYS[0], "A", 1.0)]), px, initial_cash=10_000.0)
    row = trades_of(res, "buy").iloc[0]
    assert row["rejection_reason"] == "insufficient_cash"
    assert (res["equity"]["cash"] >= 0).all()
    assert res["positions"].empty


def test_t09_missing_tradeability_state_fails_closed():
    a = series("A", [10] * 3, suspended=[False, None, False])
    b = series("B", [10] * 3)
    b[1]["limit_up_price"] = float("nan")
    res, _ = run(targets([(DAYS[0], "A", 0.5), (DAYS[0], "B", 0.5)]), bars(a, b), **NO_COST)
    reasons = dict(zip(trades_of(res, "buy")["asset_id"], trades_of(res, "buy")["rejection_reason"]))
    assert reasons == {"A": "suspension_state_missing", "B": "limit_state_missing"}


def test_t10_deterministic():
    px = bars(series("A", [10, 10.4, 9.8, 10.1, 10.6]), series("B", [5, 5.2, 5.1, 4.9, 5.3]))
    tw = targets([(DAYS[0], "A", 0.5), (DAYS[0], "B", 0.5), (DAYS[2], "A", 0.8), (DAYS[2], "B", 0.0)])
    r1, _ = run(tw, px)
    r2, _ = run(tw, px)
    for key in ("equity", "positions", "trades"):
        pd.testing.assert_frame_equal(r1[key], r2[key])


def test_t13_no_same_day_round_trip():
    px = bars(series("A", [10] * 4))
    tw = targets([(DAYS[0], "A", 1.0), (DAYS[1], "A", 0.0)])
    res, _ = run(tw, px, **NO_COST)
    filled = trades_of(res)[trades_of(res)["execution_status"] == "filled"]
    by_day = filled.groupby(["execution_date", "asset_id"])["side"].nunique()
    assert (by_day == 1).all()
    assert filled[filled.side == "sell"].iloc[0]["execution_date"] == DAYS[2]


def test_t14_ex_dividend_has_no_spurious_jump():
    adj = [1.0, 1.0, 10 / 9.5, 10 / 9.5]
    px = bars(series("A", [10, 10, 9.5, 9.5], preclose=[None, None, 9.5, None], adj=adj))
    res, _ = run(targets([(DAYS[0], "A", 1.0)]), px, **NO_COST)
    eq = res["equity"].set_index("date")
    assert eq.loc[DAYS[2], "nav_close"] == pytest.approx(eq.loc[DAYS[1], "nav_close"], rel=1e-9)
    ca = res["corporate_actions"]
    assert len(ca) == 1 and ca.iloc[0]["factor_ratio"] == pytest.approx(10 / 9.5)


def test_t14b_fail_closed_policy_rejects_missing_factor():
    adj = [1.0, 1.0, float("nan")]
    px = bars(series("A", [10, 10, 10], adj=adj))
    with pytest.raises(ContractError):
        run(targets([(DAYS[0], "A", 1.0)]), px, corporate_action_policy="fail_closed", **NO_COST)


def test_t15_adjusted_prices_rejected():
    px = bars(series("A", [10] * 3))
    px["adjust_type"] = "hfq"
    with pytest.raises(ContractError, match="raw"):
        run(targets([(DAYS[0], "A", 1.0)]), px)


def test_t16_signal_after_cutoff_rejected():
    px = bars(series("A", [10] * 3))
    tw = targets([(DAYS[0], "A", 1.0)])
    tw["signal_ts"] = f"{DAYS[0]} 15:30:00"
    with pytest.raises(ContractError, match="cutoff"):
        run(tw, px)
    tw["signal_ts"] = f"{DAYS[0]} 15:00:00"
    run(tw, px)
    run(pd.DataFrame(tw.assign(signal_ts=f"{DAYS[0]} 18:00:00")), px, signal_cutoff="20:30")


def test_t17_blocked_sell_then_target_change_updates_order():
    px = bars(series("A", [10, 10, 9, 9, 9], opens=[10, 10, 9, 9, 9]))
    tw = targets([(DAYS[0], "A", 1.0), (DAYS[1], "A", 0.0), (DAYS[2], "A", 0.5)])
    res, _ = run(tw, px, **NO_COST)
    sells = trades_of(res, "sell")
    assert list(sells["execution_status"]) == ["rejected", "filled"]
    pos = res["positions"].set_index(["date", "asset_id"])
    assert pos.loc[(DAYS[3], "A"), "weight"] == pytest.approx(0.5, abs=0.02)


def test_t18_cash_and_nav_reconcile():
    px = bars(series("A", [10, 10.3, 9.9, 10.2, 10.8, 10.5]),
              series("B", [7, 7.1, 7.4, 7.0, 6.8, 7.2], adj=[1, 1, 1, 1.1, 1.1, 1.1],
                     preclose=[None, None, None, 7.4 / 1.1, None, None]))
    tw = targets([(DAYS[0], "A", 0.4), (DAYS[0], "B", 0.5), (DAYS[2], "A", 0.7), (DAYS[2], "B", 0.2),
                  (DAYS[4], "A", 0.0), (DAYS[4], "B", 0.9)])
    res, cfg = run(tw, px)
    t = res["trades"]
    f = t[t["execution_status"].isin(["filled", "partial"])]
    buys, sells = f[f.side == "buy"], f[f.side == "sell"]
    cash = (cfg.initial_cash - (buys.transaction_value + buys.commission).sum()
            + (sells.transaction_value - sells.commission - sells.stamp_duty).sum())
    eq = res["equity"]
    assert eq.iloc[-1]["cash"] == pytest.approx(cash, rel=1e-12)
    for day, frame in res["positions"].groupby("date"):
        row = eq[eq.date == day].iloc[0]
        assert row["market_value"] == pytest.approx((frame.shares * frame.price).sum())
        assert row["nav_close"] == pytest.approx(row["cash"] + row["market_value"])
    assert eq["nav_close"].map(math.isfinite).all()
    assert (eq["cash"] >= -1e-6).all()
    s = summarize(res, initial_cash=cfg.initial_cash)
    assert s["total_cost"] > 0 and s["fill_rate"] == pytest.approx(1.0)


def test_contract_rejects_bad_targets():
    px = bars(series("A", [10] * 3))
    with pytest.raises(ContractError, match="negative"):
        run(targets([(DAYS[0], "A", -0.1)]), px)
    with pytest.raises(ContractError, match="gross"):
        run(targets([(DAYS[0], "A", 0.7), (DAYS[0], "B", 0.7)]), px)
    with pytest.raises(ContractError, match="conflicting"):
        run(targets([(DAYS[0], "A", 0.5), (DAYS[0], "A", 0.6)]), px)
