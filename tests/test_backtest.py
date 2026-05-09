from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

import stock_research.cli as cli
import stock_research.backtest as backtest
from stock_research.backtest import (
    BacktestRun,
    BacktestBar,
    BacktestSelection,
    apply_buy_filter,
    build_equity_curve,
    load_backtest_inputs,
    make_run_id,
    max_drawdown_window,
    next_trade_date,
    quantiles,
    return_value,
    run_backtest_frame,
    run_top20_backtest,
    select_top_for_date,
    simulate_selection,
    sell_bar_for_holding,
    store_backtest_results,
    summarize_holding,
)


def test_next_trade_date_uses_trading_calendar_not_natural_days():
    dates = ["2026-05-08", "2026-05-11", "2026-05-12"]
    assert next_trade_date(dates, "2026-05-08") == "2026-05-11"


def test_next_trade_date_normalizes_supported_date_inputs_to_iso_strings():
    dates = [
        date(2026, 5, 8),
        pd.Timestamp("2026-05-11 15:00:00"),
        datetime(2026, 5, 12, 9, 30),
    ]

    assert next_trade_date(dates, date(2026, 5, 8)) == "2026-05-11"


def _selection(amount_20d_avg=100000000.0):
    return BacktestSelection(
        selection_date="2026-05-07",
        asset_id="CN:SH:600001",
        rank=1,
        score=10.0,
        ret_20d=0.30,
        amount_20d_avg=amount_20d_avg,
    )


def _bar(
    open=10.0,
    preclose=10.00,
    amount=100000000.0,
    trade_status="1",
    is_st=False,
):
    return BacktestBar(
        asset_id="CN:SH:600001",
        trade_date="2026-05-08",
        open=open,
        preclose=preclose,
        amount=amount,
        trade_status=trade_status,
        is_st=is_st,
    )


@pytest.mark.parametrize(
    ("selection", "bar", "skip_reason"),
    [
        (_selection(), _bar(open=10.96), "limit_up_open"),
        (_selection(amount_20d_avg=29999999.0), _bar(), "low_liquidity"),
        (_selection(amount_20d_avg=float("nan")), _bar(), "low_liquidity"),
        (_selection(), _bar(trade_status="0"), "suspended"),
        (_selection(), None, "suspended"),
        (_selection(), _bar(is_st=True), "st"),
        (_selection(), _bar(open=None), "missing_price"),
        (_selection(), _bar(preclose=None), "missing_price"),
        (_selection(), _bar(amount=29999999.0), "low_liquidity"),
        (_selection(), _bar(amount=None), "low_liquidity"),
        (_selection(), _bar(amount=float("nan")), "low_liquidity"),
    ],
)
def test_apply_buy_filter_rejects_unexecutable_open(selection, bar, skip_reason):
    decision = apply_buy_filter(selection, bar)

    assert decision.can_buy is False
    assert decision.skip_reason == skip_reason


def test_sell_bar_for_holding_rolls_forward_when_sell_day_suspended():
    bars = [
        BacktestBar("CN:SH:600001", "2026-05-08", 10.0, 9.9, 100000000.0, "1", False),
        BacktestBar("CN:SH:600001", "2026-05-11", 10.5, 10.2, 100000000.0, "1", False),
        BacktestBar("CN:SH:600001", "2026-05-12", None, 10.4, 0.0, "0", False),
        BacktestBar("CN:SH:600001", "2026-05-13", 11.0, 10.6, 100000000.0, "1", False),
    ]

    sell = sell_bar_for_holding(bars, buy_date="2026-05-08", holding_days=3)

    assert sell.trade_date == "2026-05-13"
    assert sell.open == 11.0


def test_return_value_uses_buy_and_sell_open():
    assert return_value(10.0, 11.0) == 0.10


def test_build_equity_curve_compounds_batch_returns_and_drawdowns():
    frame = build_equity_curve(
        [
            {"selection_date": "2026-05-07", "batch_return": 0.10, "closed_trades": 20},
            {"selection_date": "2026-05-08", "batch_return": -0.05, "closed_trades": 20},
        ],
        holding_days=3,
    )

    assert round(float(frame.iloc[-1]["equity_value"]), 4) == 1.045
    assert round(float(frame.iloc[-1]["drawdown"]), 4) == -0.05


def test_build_equity_curve_drops_invalid_batch_returns():
    frame = build_equity_curve(
        [
            {"selection_date": "2026-05-07", "batch_return": None, "closed_trades": 20},
            {"selection_date": "2026-05-08", "batch_return": "not-a-number", "closed_trades": 20},
            {"selection_date": "2026-05-11", "batch_return": 0.10, "closed_trades": 20},
        ],
        holding_days=3,
    )

    assert list(frame["selection_date"]) == ["2026-05-11"]
    assert frame.iloc[0]["equity_value"] == pytest.approx(1.10)
    assert frame.iloc[0]["drawdown"] == pytest.approx(0.0)


def test_build_equity_curve_handles_all_invalid_batch_returns():
    frame = build_equity_curve(
        [
            {"selection_date": "2026-05-07", "batch_return": None, "closed_trades": 20},
            {"selection_date": "2026-05-08", "batch_return": "not-a-number", "closed_trades": 20},
        ],
        holding_days=3,
    )

    assert frame.empty
    assert max_drawdown_window(frame) == {
        "max_batch_drawdown": 0.0,
        "max_drawdown_start_date": None,
        "max_drawdown_valley_date": None,
        "max_drawdown_recovery_date": None,
    }


def test_max_drawdown_window_returns_start_valley_and_recovery():
    frame = pd.DataFrame(
        [
            {"selection_date": "2026-05-07", "equity_value": 1.0, "drawdown": 0.0},
            {"selection_date": "2026-05-08", "equity_value": 1.2, "drawdown": 0.0},
            {"selection_date": "2026-05-11", "equity_value": 0.9, "drawdown": -0.25},
            {"selection_date": "2026-05-12", "equity_value": 1.21, "drawdown": 0.0},
        ]
    )

    window = max_drawdown_window(frame)

    assert window["max_batch_drawdown"] == -0.25
    assert window["max_drawdown_start_date"] == "2026-05-08"
    assert window["max_drawdown_valley_date"] == "2026-05-11"
    assert window["max_drawdown_recovery_date"] == "2026-05-12"


def test_max_drawdown_window_returns_zero_for_no_drawdown():
    frame = pd.DataFrame(
        [
            {"selection_date": "2026-05-07", "equity_value": 1.0, "drawdown": 0.0},
            {"selection_date": "2026-05-08", "equity_value": 1.1, "drawdown": 0.0},
        ]
    )

    window = max_drawdown_window(frame)

    assert window == {
        "max_batch_drawdown": 0.0,
        "max_drawdown_start_date": None,
        "max_drawdown_valley_date": None,
        "max_drawdown_recovery_date": None,
    }


def test_quantiles_excludes_median_field():
    result = quantiles([0.10, -0.02, -0.01, -0.03], "single_return")

    assert result == {
        "single_return_p10": pytest.approx(-0.027),
        "single_return_p25": pytest.approx(-0.0225),
        "single_return_p75": pytest.approx(0.0175),
        "single_return_p90": pytest.approx(0.067),
    }
    assert "single_return_p50" not in result


def test_summarize_holding_reports_distribution_and_losing_streak():
    trades = pd.DataFrame(
        [
            {"selection_date": "2026-05-07", "holding_days": 3, "status": "closed", "return_value": 0.10},
            {"selection_date": "2026-05-07", "holding_days": 3, "status": "closed", "return_value": -0.02},
            {"selection_date": "2026-05-08", "holding_days": 3, "status": "closed", "return_value": -0.01},
            {"selection_date": "2026-05-11", "holding_days": 3, "status": "closed", "return_value": -0.03},
            {"selection_date": "2026-05-12", "holding_days": 3, "status": "skipped", "return_value": None},
            {"selection_date": "2026-05-13", "holding_days": 3, "status": "unclosed", "return_value": None},
        ]
    )

    summary, curve = summarize_holding("run1", trades, holding_days=3)

    assert summary["closed_trades"] == 4
    assert summary["skipped_trades"] == 1
    assert summary["unclosed_trades"] == 1
    assert summary["mean_return"] == pytest.approx(0.01)
    assert summary["median_return"] == pytest.approx(-0.015)
    assert summary["win_rate"] == pytest.approx(0.25)
    assert summary["best_return"] == pytest.approx(0.10)
    assert summary["worst_return"] == pytest.approx(-0.03)
    assert summary["batch_mean_return"] == pytest.approx(0.0)
    assert summary["batch_win_rate"] == pytest.approx(1 / 3)
    assert summary["max_losing_streak"] == 2
    assert summary["max_batch_drawdown"] == pytest.approx(-0.0397, abs=0.0001)
    assert summary["max_drawdown_start_date"] == "2026-05-07"
    assert summary["max_drawdown_valley_date"] == "2026-05-11"
    assert summary["max_drawdown_recovery_date"] is None
    assert summary["single_return_p10"] == pytest.approx(-0.027)
    assert summary["single_return_p25"] == pytest.approx(-0.0225)
    assert summary["single_return_p75"] == pytest.approx(0.0175)
    assert summary["single_return_p90"] == pytest.approx(0.067)
    assert "single_return_p50" not in summary
    assert summary["batch_return_p10"] == pytest.approx(-0.026)
    assert summary["batch_return_p25"] == pytest.approx(-0.02)
    assert summary["batch_return_p75"] == pytest.approx(0.015)
    assert summary["batch_return_p90"] == pytest.approx(0.03)
    assert "batch_return_p50" not in summary
    assert len(curve) == 3


def test_summarize_holding_normalizes_selection_dates_before_grouping():
    trades = pd.DataFrame(
        [
            {
                "selection_date": pd.Timestamp("2026-05-07 09:30:00"),
                "holding_days": 3,
                "status": "closed",
                "return_value": 0.10,
            },
            {
                "selection_date": pd.Timestamp("2026-05-07 15:00:00"),
                "holding_days": 3,
                "status": "closed",
                "return_value": -0.02,
            },
        ]
    )

    summary, curve = summarize_holding("run1", trades, holding_days=3)

    assert summary["selection_days"] == 1
    assert len(curve) == 1
    assert curve.iloc[0]["selection_date"] == "2026-05-07"
    assert curve.iloc[0]["batch_return"] == pytest.approx(0.04)


def _feature_frame(rows):
    records = []
    for asset_id, trade_date, features in rows:
        for feature_name, feature_value in features.items():
            records.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "feature_name": feature_name,
                    "feature_value": feature_value,
                }
            )
    return pd.DataFrame(records)


def _complete_features(
    ret_20d,
    ret_60d,
    amount_20d_avg=100000000.0,
    volatility_20d=0.03,
    max_drawdown_20d=-0.05,
):
    return {
        "ret_20d": ret_20d,
        "ret_60d": ret_60d,
        "amount_20d_avg": amount_20d_avg,
        "volatility_20d": volatility_20d,
        "max_drawdown_20d": max_drawdown_20d,
    }


def _bar_frame(rows):
    return pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "trade_date": trade_date,
                "open": open_,
                "preclose": preclose,
                "amount": amount,
                "trade_status": trade_status,
                "is_st": is_st,
            }
            for asset_id, trade_date, open_, preclose, amount, trade_status, is_st in rows
        ]
    )


def _market_bar_rows(asset_id="CN:SH:600001", start="2026-01-01", days=70):
    dates = pd.bdate_range(start=start, periods=days)
    rows = []
    for index, trade_date in enumerate(dates):
        close = 10.0 + index * 0.1
        rows.append(
            {
                "asset_id": asset_id,
                "trade_date": trade_date.date(),
                "open": close,
                "preclose": close - 0.05,
                "close": close,
                "amount": 100000000.0 + index,
                "turnover_rate": 1.0,
                "trade_status": "1",
                "is_st": False,
            }
        )
    return rows


def test_select_top_for_date_scores_and_filters_selection_day_candidates():
    features = _feature_frame(
        [
            ("CN:SH:600003", "2026-05-07", _complete_features(0.20, 0.10)),
            ("CN:SH:600001", "2026-05-07", _complete_features(0.10, 0.10)),
            ("CN:SH:600002", "2026-05-07", _complete_features(0.10, 0.10)),
            ("CN:SH:600004", "2026-05-07", _complete_features(0.50, 0.50)),
            ("CN:SH:600005", "2026-05-07", _complete_features(0.40, 0.40)),
            ("CN:SH:600006", "2026-05-07", _complete_features(0.30, 0.30, amount_20d_avg=1000.0)),
            (
                "CN:SH:600007",
                "2026-05-07",
                {
                    "ret_20d": 0.30,
                    "ret_60d": 0.30,
                    "amount_20d_avg": 100000000.0,
                    "volatility_20d": 0.03,
                },
            ),
            ("CN:SH:600008", "2026-05-06", _complete_features(0.90, 0.90)),
        ]
    )
    bars = _bar_frame(
        [
            ("CN:SH:600001", "2026-05-07", 10.0, 9.9, 100000000.0, "1", False),
            ("CN:SH:600002", "2026-05-07", 10.0, 9.9, 100000000.0, "1", False),
            ("CN:SH:600003", "2026-05-07", 10.0, 9.9, 100000000.0, "1", False),
            ("CN:SH:600004", "2026-05-07", 10.0, 9.9, 100000000.0, "1", True),
            ("CN:SH:600005", "2026-05-07", 10.0, 9.9, 100000000.0, "0", False),
            ("CN:SH:600006", "2026-05-07", 10.0, 9.9, 100000000.0, "1", False),
            ("CN:SH:600007", "2026-05-07", 10.0, 9.9, 100000000.0, "1", False),
        ]
    )

    selected = select_top_for_date(features, bars, "2026-05-07", top_n=3)

    assert [row.asset_id for row in selected] == [
        "CN:SH:600003",
        "CN:SH:600001",
        "CN:SH:600002",
    ]
    assert [row.rank for row in selected] == [1, 2, 3]
    assert selected[0].score == pytest.approx(28.0)
    assert selected[0].ret_20d == pytest.approx(0.20)
    assert selected[0].amount_20d_avg == pytest.approx(100000000.0)


def test_simulate_selection_generates_closed_unclosed_and_skipped_trade_rows():
    selections = [
        BacktestSelection("2026-05-07", "CN:SH:600001", 1, 10.0, 0.10, 100000000.0),
        BacktestSelection("2026-05-07", "CN:SH:600002", 2, 9.0, 0.08, 100000000.0),
    ]
    bars_by_asset = {
        "CN:SH:600001": [
            BacktestBar("CN:SH:600001", "2026-05-08", 10.0, 9.8, 100000000.0, "1", False),
            BacktestBar("CN:SH:600001", "2026-05-11", 10.2, 10.0, 100000000.0, "1", False),
            BacktestBar("CN:SH:600001", "2026-05-12", 10.4, 10.2, 100000000.0, "1", False),
            BacktestBar("CN:SH:600001", "2026-05-13", 11.0, 10.4, 100000000.0, "1", False),
        ],
        "CN:SH:600002": [
            BacktestBar("CN:SH:600002", "2026-05-08", 10.96, 10.0, 100000000.0, "1", False),
            BacktestBar("CN:SH:600002", "2026-05-11", 11.0, 10.96, 100000000.0, "1", False),
        ],
    }

    trades = simulate_selection(
        selections,
        bars_by_asset,
        ["2026-05-07", "2026-05-08", "2026-05-11", "2026-05-12", "2026-05-13"],
        holding_days=[3, 5],
    )

    closed = next(
        row
        for row in trades
        if row["asset_id"] == "CN:SH:600001" and row["holding_days"] == 3
    )
    assert closed["selection_date"] == "2026-05-07"
    assert closed["rank"] == 1
    assert closed["buy_date"] == "2026-05-08"
    assert closed["buy_open"] == pytest.approx(10.0)
    assert closed["sell_date"] == "2026-05-13"
    assert closed["sell_open"] == pytest.approx(11.0)
    assert closed["return_value"] == pytest.approx(0.10)
    assert closed["status"] == "closed"
    assert closed["skip_reason"] is None

    unclosed = next(
        row
        for row in trades
        if row["asset_id"] == "CN:SH:600001" and row["holding_days"] == 5
    )
    assert unclosed["status"] == "unclosed"
    assert unclosed["sell_date"] is None
    assert unclosed["return_value"] is None

    skipped = [
        row for row in trades if row["asset_id"] == "CN:SH:600002"
    ]
    assert {row["holding_days"] for row in skipped} == {3, 5}
    assert {row["status"] for row in skipped} == {"skipped"}
    assert {row["skip_reason"] for row in skipped} == {"limit_up_open"}


def test_simulate_selection_skips_all_horizons_when_next_buy_date_is_missing():
    selection = [
        BacktestSelection("2026-05-13", "CN:SH:600001", 1, 10.0, 0.10, 100000000.0)
    ]

    trades = simulate_selection(
        selection,
        {"CN:SH:600001": []},
        ["2026-05-13"],
        holding_days=[3, 5],
    )

    assert [row["status"] for row in trades] == ["skipped", "skipped"]
    assert {row["skip_reason"] for row in trades} == {"missing_next_buy_date"}
    assert all(row["buy_date"] is None for row in trades)


def test_run_backtest_frame_rolls_selection_dates_and_returns_default_horizons():
    features = _feature_frame(
        [
            ("CN:SH:600001", "2026-05-07", _complete_features(0.20, 0.10)),
            ("CN:SH:600002", "2026-05-07", _complete_features(0.10, 0.10)),
            ("CN:SH:600001", "2026-05-08", _complete_features(0.25, 0.10)),
            ("CN:SH:600002", "2026-05-08", _complete_features(0.05, 0.10)),
            ("CN:SH:600001", "2026-05-13", _complete_features(0.90, 0.90)),
        ]
    )
    bars = _bar_frame(
        [
            ("CN:SH:600001", "2026-05-07", 10.0, 9.9, 100000000.0, "1", False),
            ("CN:SH:600002", "2026-05-07", 20.0, 19.9, 100000000.0, "1", False),
            ("CN:SH:600001", "2026-05-08", 10.0, 9.9, 100000000.0, "1", False),
            ("CN:SH:600002", "2026-05-08", 20.0, 19.9, 100000000.0, "1", False),
            ("CN:SH:600001", "2026-05-11", 10.2, 10.0, 100000000.0, "1", False),
            ("CN:SH:600002", "2026-05-11", 20.2, 20.0, 100000000.0, "1", False),
            ("CN:SH:600001", "2026-05-12", 10.4, 10.2, 100000000.0, "1", False),
            ("CN:SH:600002", "2026-05-12", 20.4, 20.2, 100000000.0, "1", False),
            ("CN:SH:600001", "2026-05-13", 11.0, 10.4, 100000000.0, "1", False),
            ("CN:SH:600002", "2026-05-13", 21.0, 20.4, 100000000.0, "1", False),
        ]
    )

    result = run_backtest_frame(
        features,
        bars,
        start_date="2026-05-07",
        end_date="2026-05-13",
        holding_days=[3, 5, 7, 10],
        top_n=1,
    )

    assert set(result["selection_date"]) == {"2026-05-07", "2026-05-08"}
    assert set(result["holding_days"]) == {3, 5, 7, 10}
    assert len(result) == 8
    assert set(result["asset_id"]) == {"CN:SH:600001"}
    closed = result[
        (result["selection_date"] == "2026-05-07")
        & (result["holding_days"] == 3)
    ].iloc[0]
    assert closed["status"] == "closed"
    assert closed["buy_date"] == "2026-05-08"
    assert closed["sell_date"] == "2026-05-13"
    assert closed["return_value"] == pytest.approx(0.10)
    assert result["rank"].tolist() == [1] * len(result)


def test_make_run_id_includes_backtest_parameters():
    assert (
        make_run_id("2026-05-01", "2026-05-08", top_n=5, holding_days=[10, 3, 3])
        == "top20:2026-05-01:2026-05-08:n5:h10-3-3:baseline_rules_v1"
    )


def test_load_backtest_inputs_queries_features_and_hfq_bars(monkeypatch):
    captured = []

    class FakeConnection:
        pass

    class FakeConnect:
        def __init__(self, service):
            captured.append(("service", service))

        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        return FakeConnect(service)

    def fake_fetch_all(conn, sql, params):
        captured.append(("query", sql, params))
        if "FROM feature_snapshot" in sql:
            return []
        if "FROM market_daily_bar" in sql:
            return [
                {
                    "asset_id": "CN:SH:600001",
                    "trade_date": date(2026, 5, 7),
                    "open": 10.0,
                    "preclose": 9.9,
                    "close": 10.1,
                    "amount": 100000000.0,
                    "turnover_rate": 1.0,
                    "trade_status": "1",
                    "is_st": False,
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(backtest, "connect", fake_connect)
    monkeypatch.setattr(backtest, "fetch_all", fake_fetch_all)

    features, bars = load_backtest_inputs(
        "2026-05-01",
        "2026-05-08",
        future_buffer_days=30,
        feature_lookback_days=220,
    )

    assert list(features.columns) == [
        "asset_id",
        "trade_date",
        "feature_name",
        "feature_value",
    ]
    assert list(bars.columns) == [
        "asset_id",
        "trade_date",
        "open",
        "preclose",
        "close",
        "amount",
        "turnover_rate",
        "trade_status",
        "is_st",
    ]
    feature_query = captured[1]
    bar_query = captured[2]
    assert "FROM feature_snapshot" in feature_query[1]
    assert "feature_set = 'p0_daily'" in feature_query[1]
    assert "feature_version = 'v1'" in feature_query[1]
    assert feature_query[2] == ["2026-05-01", "2026-05-08"]
    assert "FROM market_daily_bar" in bar_query[1]
    assert "adjust_type = 'hfq'" in bar_query[1]
    assert "close" in bar_query[1]
    assert "turnover_rate" in bar_query[1]
    assert bar_query[2] == ["2025-09-23", "2026-06-07"]


def test_load_backtest_inputs_computes_p0_features_from_market_bars(monkeypatch):
    captured = []

    class FakeConnection:
        pass

    class FakeConnect:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(conn, sql, params):
        captured.append(("query", sql, params))
        if "FROM feature_snapshot" in sql:
            return []
        if "FROM market_daily_bar" in sql:
            return _market_bar_rows(days=70)
        raise AssertionError(sql)

    monkeypatch.setattr(backtest, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(backtest, "fetch_all", fake_fetch_all)

    features, bars = load_backtest_inputs(
        "2026-03-26",
        "2026-04-08",
        future_buffer_days=5,
        feature_lookback_days=61,
    )

    feature_query = captured[0]
    bar_query = captured[1]
    assert feature_query[2] == ["2026-03-26", "2026-04-08"]
    assert bar_query[2] == ["2026-01-24", "2026-04-13"]
    assert not bars.empty

    scoped = features[features["trade_date"].map(str).between("2026-03-26", "2026-04-08")]
    assert not scoped.empty
    assert set(scoped["feature_name"]) >= {
        "ret_20d",
        "ret_60d",
        "amount_20d_avg",
        "volatility_20d",
        "max_drawdown_20d",
    }
    ret_60d = scoped[scoped["feature_name"] == "ret_60d"]
    assert not ret_60d.empty


def test_computed_loader_features_drive_backtest_without_snapshots(monkeypatch):
    class FakeConnection:
        pass

    class FakeConnect:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(conn, sql, params):
        if "FROM feature_snapshot" in sql:
            return []
        if "FROM market_daily_bar" in sql:
            return _market_bar_rows(days=75)
        raise AssertionError(sql)

    monkeypatch.setattr(backtest, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(backtest, "fetch_all", fake_fetch_all)

    features, bars = load_backtest_inputs(
        "2026-03-26",
        "2026-03-30",
        future_buffer_days=10,
        feature_lookback_days=61,
    )
    trades = run_backtest_frame(
        features,
        bars,
        start_date="2026-03-26",
        end_date="2026-03-30",
        holding_days=[3],
        top_n=1,
    )

    assert not trades.empty
    assert set(trades["selection_date"]) >= {"2026-03-26"}
    assert set(trades["status"]) == {"closed"}


def test_store_backtest_results_writes_four_tables_and_converts_nan(monkeypatch):
    captured = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            captured.append(("many", sql, list(rows)))

        def execute(self, sql, params):
            captured.append(("one", sql, list(params)))

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakeConnect:
        def __init__(self, service):
            captured.append(("service", service))

        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(backtest, "connect", lambda service: FakeConnect(service))

    run = BacktestRun(
        run_id="run1",
        score_version="baseline_rules_v1",
        start_date="2026-05-01",
        end_date="2026-05-08",
        top_n=20,
        holding_days=[3],
        buy_price_rule="next_open",
        sell_price_rule="holding_open",
        execution_profile="a_share_daily_v1",
    )
    trades = pd.DataFrame(
        [
            {
                "selection_date": "2026-05-07",
                "asset_id": "CN:SH:600001",
                "rank": 1,
                "score": 10.0,
                "holding_days": 3,
                "buy_date": "2026-05-08",
                "buy_open": 10.0,
                "sell_date": None,
                "sell_open": float("nan"),
                "return_value": None,
                "status": "unclosed",
                "skip_reason": None,
            }
        ]
    )
    summaries = pd.DataFrame(
        [
            {
                "run_id": "run1",
                "holding_days": 3,
                "selection_days": 1,
                "theoretical_trades": 1,
                "closed_trades": 0,
                "skipped_trades": 0,
                "unclosed_trades": 1,
                "mean_return": float("nan"),
                "median_return": None,
                "win_rate": None,
                "best_return": None,
                "worst_return": None,
                "batch_mean_return": None,
                "batch_win_rate": None,
                "max_batch_drawdown": 0.0,
                "max_drawdown_start_date": None,
                "max_drawdown_valley_date": None,
                "max_drawdown_recovery_date": None,
                "max_losing_streak": 0,
                "single_return_p10": None,
                "single_return_p25": None,
                "single_return_p75": None,
                "single_return_p90": None,
                "batch_return_p10": None,
                "batch_return_p25": None,
                "batch_return_p75": None,
                "batch_return_p90": None,
            }
        ]
    )
    curves = pd.DataFrame(
        [
            {
                "run_id": "run1",
                "holding_days": 3,
                "selection_date": "2026-05-07",
                "batch_return": float("nan"),
                "equity_value": 1.0,
                "drawdown": 0.0,
                "closed_trades": 0,
            }
        ]
    )

    store_backtest_results(run, trades, summaries, curves, report_path="/tmp/report.md")

    statements = captured[1:]
    assert [sql.split()[2] for kind, sql, rows in statements if kind == "many"] == [
        "backtest_run",
        "backtest_trade",
        "backtest_summary",
        "backtest_equity_curve",
    ]
    assert [sql for kind, sql, params in statements if kind == "one"] == [
        "DELETE FROM backtest_trade WHERE run_id = %s",
        "DELETE FROM backtest_summary WHERE run_id = %s",
        "DELETE FROM backtest_equity_curve WHERE run_id = %s",
    ]
    delete_indexes = [index for index, statement in enumerate(statements) if statement[0] == "one"]
    child_insert_indexes = [
        index
        for index, statement in enumerate(statements)
        if statement[0] == "many" and statement[1].split()[2] != "backtest_run"
    ]
    assert max(delete_indexes) < min(child_insert_indexes)
    many_statements = [statement for statement in statements if statement[0] == "many"]
    assert many_statements[0][2][0]["run_id"] == "run1"
    assert many_statements[0][2][0]["report_path"] == "/tmp/report.md"
    assert many_statements[1][2][0]["sell_open"] is None
    assert many_statements[2][2][0]["mean_return"] is None
    assert many_statements[3][2][0]["batch_return"] is None


def test_store_backtest_results_deletes_old_children_when_new_child_rows_are_empty(monkeypatch):
    captured = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            captured.append(("many", sql, list(rows)))

        def execute(self, sql, params):
            captured.append(("one", sql, list(params)))

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakeConnect:
        def __init__(self, service):
            captured.append(("service", service))

        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(backtest, "connect", lambda service: FakeConnect(service))
    run = BacktestRun(
        run_id="run1",
        score_version="baseline_rules_v1",
        start_date="2026-05-01",
        end_date="2026-05-08",
        top_n=20,
        holding_days=[3],
        buy_price_rule="next_open",
        sell_price_rule="holding_open",
        execution_profile="a_share_daily_v1",
    )

    store_backtest_results(
        run,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        report_path=None,
    )

    statements = captured[1:]
    assert [statement[0] for statement in statements] == ["many", "one", "one", "one"]
    assert statements[0][1].split()[2] == "backtest_run"
    assert [statement[1] for statement in statements[1:]] == [
        "DELETE FROM backtest_trade WHERE run_id = %s",
        "DELETE FROM backtest_summary WHERE run_id = %s",
        "DELETE FROM backtest_equity_curve WHERE run_id = %s",
    ]


def test_write_backtest_report_writes_markdown_and_csv_outputs(tmp_path):
    run = BacktestRun(
        run_id="run1",
        score_version="baseline_rules_v1",
        start_date="2026-05-01",
        end_date="2026-05-08",
        top_n=20,
        holding_days=[3, 5, 7, 10],
        buy_price_rule="next_open",
        sell_price_rule="holding_open",
        execution_profile="a_share_daily_v1",
    )
    trades = pd.DataFrame(
        [
            {
                "selection_date": "2026-05-07",
                "asset_id": "CN:SH:600001",
                "rank": 1,
                "score": 10.0,
                "holding_days": 3,
                "buy_date": "2026-05-08",
                "buy_open": 10.0,
                "sell_date": "2026-05-13",
                "sell_open": 9.8,
                "return_value": -0.02,
                "status": "closed",
                "skip_reason": None,
                "ret_20d": 0.30,
            },
            {
                "selection_date": "2026-05-07",
                "asset_id": "CN:SH:600002",
                "rank": 2,
                "score": 9.0,
                "holding_days": 3,
                "buy_date": "2026-05-08",
                "buy_open": None,
                "sell_date": None,
                "sell_open": None,
                "return_value": None,
                "status": "skipped",
                "skip_reason": "limit_up_open",
                "ret_20d": 0.40,
            },
        ]
    )
    summaries = pd.DataFrame(
        [
            {
                "run_id": "run1",
                "holding_days": horizon,
                "selection_days": 1,
                "theoretical_trades": 2,
                "closed_trades": 1,
                "skipped_trades": 1,
                "unclosed_trades": 0,
                "mean_return": -0.02,
                "median_return": -0.02,
                "win_rate": 0.0,
                "max_batch_drawdown": -0.02,
            }
            for horizon in [3, 5, 7, 10]
        ]
    )
    curves = pd.DataFrame(
        [
            {
                "run_id": "run1",
                "holding_days": horizon,
                "selection_date": "2026-05-07",
                "batch_return": -0.02,
                "equity_value": 0.98,
                "drawdown": -0.02,
                "closed_trades": 1,
            }
            for horizon in [3, 5, 7, 10]
        ]
    )

    paths = backtest.write_backtest_report(run, trades, summaries, curves, tmp_path)

    assert set(paths) == {
        "report_path",
        "equity_curve_path",
        "trades_path",
        "summary_path",
    }
    report_path = tmp_path / "run1.md"
    assert paths["report_path"] == str(report_path)
    markdown = report_path.read_text(encoding="utf-8")
    assert "Top 20 评分选股回测报告" in markdown
    for horizon in [3, 5, 7, 10]:
        assert f"持有 {horizon}" in markdown
    assert "收益率曲线" in markdown
    assert "回撤曲线" in markdown
    assert "样本剔除" in markdown
    assert "追高风险观察" in markdown
    assert "仅作为研究验证，不构成交易指令" in markdown
    assert "可能追高" in markdown
    assert "买入建议" not in markdown
    assert "卖出建议" not in markdown
    assert "仓位建议" not in markdown
    assert pd.read_csv(paths["equity_curve_path"]).equals(curves)
    assert pd.read_csv(paths["trades_path"]).shape == trades.shape
    assert pd.read_csv(paths["summary_path"]).shape == summaries.shape


def test_write_backtest_report_handles_empty_missing_column_frames(tmp_path):
    run = BacktestRun(
        run_id="top20:2026-05-01:2026-05-08:n5:h3:baseline_rules_v1",
        score_version="baseline_rules_v1",
        start_date="2026-05-01",
        end_date="2026-05-08",
        top_n=5,
        holding_days=[3],
        buy_price_rule="next_open",
        sell_price_rule="holding_open",
        execution_profile="a_share_daily_v1",
    )

    paths = backtest.write_backtest_report(
        run,
        trades=pd.DataFrame(),
        summaries=pd.DataFrame(),
        curves=pd.DataFrame(),
        reports_dir=tmp_path,
    )

    expected_stem = "top20_2026-05-01_2026-05-08_n5_h3_baseline_rules_v1"
    report_path = tmp_path / f"{expected_stem}.md"
    assert paths["report_path"] == str(report_path)
    assert paths["equity_curve_path"] == str(tmp_path / f"{expected_stem}_equity_curve.csv")
    assert paths["trades_path"] == str(tmp_path / f"{expected_stem}_trades.csv")
    assert paths["summary_path"] == str(tmp_path / f"{expected_stem}_summary.csv")
    markdown = report_path.read_text(encoding="utf-8")
    assert "无曲线样本" in markdown
    assert "暂不能判断追高风险" in markdown
    assert Path(paths["equity_curve_path"]).exists()
    assert Path(paths["trades_path"]).exists()
    assert Path(paths["summary_path"]).exists()


def test_write_backtest_report_handles_all_nan_equity_values(tmp_path):
    run = BacktestRun(
        run_id="run1",
        score_version="baseline_rules_v1",
        start_date="2026-05-01",
        end_date="2026-05-08",
        top_n=20,
        holding_days=[3],
        buy_price_rule="next_open",
        sell_price_rule="holding_open",
        execution_profile="a_share_daily_v1",
    )
    curves = pd.DataFrame(
        [
            {
                "run_id": "run1",
                "holding_days": 3,
                "selection_date": "2026-05-07",
                "batch_return": None,
                "equity_value": None,
                "drawdown": None,
                "closed_trades": 0,
            }
        ]
    )

    paths = backtest.write_backtest_report(
        run,
        trades=pd.DataFrame(),
        summaries=pd.DataFrame(),
        curves=curves,
        reports_dir=tmp_path,
    )

    markdown = Path(paths["report_path"]).read_text(encoding="utf-8")
    assert "无曲线样本" in markdown


def test_write_backtest_report_handles_empty_trades_missing_status_column(tmp_path):
    run = BacktestRun(
        run_id="run1",
        score_version="baseline_rules_v1",
        start_date="2026-05-01",
        end_date="2026-05-08",
        top_n=20,
        holding_days=[3],
        buy_price_rule="next_open",
        sell_price_rule="holding_open",
        execution_profile="a_share_daily_v1",
    )

    paths = backtest.write_backtest_report(
        run,
        trades=pd.DataFrame(columns=["return_value"]),
        summaries=pd.DataFrame(),
        curves=pd.DataFrame(columns=["holding_days", "equity_value"]),
        reports_dir=tmp_path,
    )

    markdown = Path(paths["report_path"]).read_text(encoding="utf-8")
    assert "暂不能判断追高风险" in markdown


def test_run_top20_backtest_orchestrates_load_calculate_summarize_and_store(monkeypatch):
    calls = []
    feature_frame = pd.DataFrame([{"asset_id": "CN:SH:600001"}])
    bar_frame = pd.DataFrame([{"asset_id": "CN:SH:600001"}])
    trades = pd.DataFrame(
        [
            {
                "selection_date": "2026-05-07",
                "asset_id": "CN:SH:600001",
                "rank": 1,
                "score": 10.0,
                "holding_days": 3,
                "status": "closed",
                "return_value": 0.1,
            }
        ]
    )

    def fake_load(start_date, end_date, future_buffer_days=30):
        calls.append(("load", start_date, end_date, future_buffer_days))
        return feature_frame, bar_frame

    def fake_run_frame(features, bars, start_date, end_date, holding_days, top_n):
        calls.append(("run_frame", features, bars, start_date, end_date, holding_days, top_n))
        return trades

    def fake_summarize(run_id, trade_frame, holding_days):
        calls.append(("summarize", run_id, trade_frame, holding_days))
        return (
            {
                "run_id": run_id,
                "holding_days": holding_days,
                "selection_days": 1,
                "theoretical_trades": 1,
                "closed_trades": 1,
                "skipped_trades": 0,
                "unclosed_trades": 0,
            },
            pd.DataFrame(
                [
                    {
                        "run_id": run_id,
                        "holding_days": holding_days,
                        "selection_date": "2026-05-07",
                    }
                ]
            ),
        )

    def fake_store(run, trade_frame, summaries, curves, report_path=None):
        calls.append(("store", run, trade_frame, summaries, curves, report_path))

    monkeypatch.setattr(backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(backtest, "run_backtest_frame", fake_run_frame)
    monkeypatch.setattr(backtest, "summarize_holding", fake_summarize)
    monkeypatch.setattr(backtest, "store_backtest_results", fake_store)

    result = run_top20_backtest(
        "2026-05-01",
        "2026-05-08",
        holding_days=[3],
        top_n=5,
        reports_dir=None,
    )

    assert calls[0] == ("load", "2026-05-01", "2026-05-08", 30)
    assert calls[1] == (
        "run_frame",
        feature_frame,
        bar_frame,
        "2026-05-01",
        "2026-05-08",
        [3],
        5,
    )
    assert calls[2][0] == "summarize"
    assert calls[2][3] == 3
    assert calls[3][0] == "store"
    assert calls[3][5] is None
    assert result["run"].run_id == "top20:2026-05-01:2026-05-08:n5:h3:baseline_rules_v1"
    assert result["trades"].equals(trades)
    assert result["summaries"].iloc[0]["holding_days"] == 3
    assert result["curves"].iloc[0]["holding_days"] == 3
    assert result["report_path"] is None


def test_run_top20_backtest_writes_report_before_storing_when_reports_dir_is_set(
    monkeypatch, tmp_path
):
    calls = []
    trades = pd.DataFrame(
        [
            {
                "selection_date": "2026-05-07",
                "asset_id": "CN:SH:600001",
                "rank": 1,
                "score": 10.0,
                "holding_days": 3,
                "status": "closed",
                "return_value": 0.1,
            }
        ]
    )

    monkeypatch.setattr(
        backtest,
        "load_backtest_inputs",
        lambda start_date, end_date, future_buffer_days=30: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(backtest, "run_backtest_frame", lambda *args, **kwargs: trades)
    monkeypatch.setattr(
        backtest,
        "summarize_holding",
        lambda run_id, trade_frame, holding_days: (
            {
                "run_id": run_id,
                "holding_days": holding_days,
                "selection_days": 1,
                "theoretical_trades": 1,
                "closed_trades": 1,
                "skipped_trades": 0,
                "unclosed_trades": 0,
            },
            pd.DataFrame([{"run_id": run_id, "holding_days": holding_days}]),
        ),
    )

    def fake_write(run, trade_frame, summaries, curves, reports_dir):
        calls.append(("write", run, trade_frame, summaries, curves, reports_dir))
        return {
            "report_path": str(tmp_path / "report.md"),
            "equity_curve_path": str(tmp_path / "equity.csv"),
            "trades_path": str(tmp_path / "trades.csv"),
            "summary_path": str(tmp_path / "summary.csv"),
        }

    def fake_store(run, trade_frame, summaries, curves, report_path=None):
        calls.append(("store", run, trade_frame, summaries, curves, report_path))

    monkeypatch.setattr(backtest, "write_backtest_report", fake_write)
    monkeypatch.setattr(backtest, "store_backtest_results", fake_store)

    result = run_top20_backtest(
        "2026-05-01",
        "2026-05-08",
        holding_days=[3],
        top_n=5,
        reports_dir=str(tmp_path),
    )

    assert [call[0] for call in calls] == ["write", "store"]
    assert calls[0][5] == str(tmp_path)
    assert calls[1][5] == str(tmp_path / "report.md")
    assert result["report_path"] == str(tmp_path / "report.md")
    assert result["report_paths"] == {
        "report_path": str(tmp_path / "report.md"),
        "equity_curve_path": str(tmp_path / "equity.csv"),
        "trades_path": str(tmp_path / "trades.csv"),
        "summary_path": str(tmp_path / "summary.csv"),
    }


def test_cli_parser_accepts_backtest_top20_arguments():
    args = cli.build_parser().parse_args(
        [
            "backtest-top20",
            "--start-date",
            "2024-05-01",
            "--end-date",
            "2026-05-07",
            "--holding-days",
            "3,5,7,10",
            "--top-n",
            "20",
        ]
    )

    assert args.command == "backtest-top20"
    assert args.holding_days == [3, 5, 7, 10]
    assert args.top_n == 20


@pytest.mark.parametrize("value", ["", ",,", "3,a", "3,,5", "3,", ",3"])
def test_cli_parser_rejects_invalid_holding_days(value):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(
            [
                "backtest-top20",
                "--start-date",
                "2024-05-01",
                "--end-date",
                "2026-05-07",
                "--holding-days",
                value,
            ]
        )

    assert exc.value.code == 2


def test_cli_main_runs_backtest_top20_and_prints_outputs(monkeypatch, capsys):
    calls = []

    class FakeRun:
        run_id = "run-1"

    def fake_run_top20_backtest(
        start_date,
        end_date,
        holding_days,
        top_n=20,
        reports_dir=None,
    ):
        calls.append((start_date, end_date, holding_days, top_n, reports_dir))
        return {
            "run": FakeRun(),
            "report_path": "/tmp/report.md",
            "trades": pd.DataFrame([{"trade": 1}, {"trade": 2}, {"trade": 3}]),
        }

    monkeypatch.setattr(cli, "run_top20_backtest", fake_run_top20_backtest, raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "backtest-top20",
            "--start-date",
            "2024-05-01",
            "--end-date",
            "2026-05-07",
            "--holding-days",
            "3,5,7,10",
        ],
    )

    cli.main()

    assert calls == [
        (
            "2024-05-01",
            "2026-05-07",
            [3, 5, 7, 10],
            20,
            "/Users/xiwei/stock_research/reports",
        )
    ]
    assert capsys.readouterr().out.splitlines() == [
        "backtest_run|run-1",
        "backtest_report|/tmp/report.md",
        "backtest_trades|3",
    ]
