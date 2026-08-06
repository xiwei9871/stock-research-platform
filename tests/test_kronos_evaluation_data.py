import json
import sys
import types
from contextlib import contextmanager

import pandas as pd
import pytest


try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    psycopg_stub = types.ModuleType("psycopg")
    psycopg_stub.Connection = object
    psycopg_stub.connect = lambda *args, **kwargs: None
    psycopg_rows_stub = types.ModuleType("psycopg.rows")
    psycopg_rows_stub.dict_row = object()
    psycopg_stub.rows = psycopg_rows_stub
    sys.modules["psycopg"] = psycopg_stub
    sys.modules["psycopg.rows"] = psycopg_rows_stub


from stock_research import kronos_evaluation_data as data
from stock_research.kronos_evaluation_types import thaw_json_value


HISTORY_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)


def make_daily_frame(
    asset_id="CN:SH:600418",
    *,
    start="2024-01-01",
    periods=20,
    close_offset=0.0,
):
    dates = pd.date_range(start=start, periods=periods, freq="D")
    index = pd.Series(range(periods), dtype=float)
    opens = 100.0 + index
    closes = opens + 0.5 + close_offset
    return pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": asset_id,
            "open": opens,
            "high": closes + 1.0,
            "low": opens - 1.0,
            "close": closes,
            "volume": 1_000.0 + index,
            "amount": 100_000.0 + index * 100.0,
            "trade_status": "normal",
            "is_st": False,
        }
    )


def make_trade_dates(periods=20, *, start="2024-01-01"):
    return [
        timestamp.strftime("%Y-%m-%d")
        for timestamp in pd.date_range(start=start, periods=periods, freq="D")
    ]


def test_build_snapshots_uses_only_bars_at_or_before_origin():
    frame = make_daily_frame(periods=20)
    frame.loc[frame["trade_date"] > pd.Timestamp("2024-01-15"), "close"] = 9_999.0
    frame.loc[frame["trade_date"] > pd.Timestamp("2024-01-15"), "high"] = 10_000.0

    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates=make_trade_dates(20),
        input_window=5,
        forecast_horizon=3,
    )

    snapshot = next(
        snapshot for snapshot in snapshots if snapshot.origin_date == "2024-01-15"
    )
    assert snapshot.status == "ready"
    assert [row["timestamp"] for row in snapshot.history] == [
        "2024-01-11",
        "2024-01-12",
        "2024-01-13",
        "2024-01-14",
        "2024-01-15",
    ]
    assert all(row["timestamp"] <= "2024-01-15" for row in snapshot.history)
    assert snapshot.history[-1]["close"] != 9_999.0
    assert snapshot.future_timestamps == (
        "2024-01-16",
        "2024-01-17",
        "2024-01-18",
    )


def test_missing_history_is_statused_without_padding():
    frame = make_daily_frame(periods=7)

    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates=make_trade_dates(7),
        input_window=5,
        forecast_horizon=3,
    )

    snapshot = next(
        snapshot for snapshot in snapshots if snapshot.origin_date == "2024-01-03"
    )
    assert snapshot.status == "insufficient_input"
    assert len(snapshot.history) == 3
    assert [row["timestamp"] for row in snapshot.history] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]
    assert "input_window" in snapshot.reason


def test_missing_truth_is_statused_without_padding():
    first_asset = make_daily_frame(periods=7)
    first_asset = first_asset[first_asset["trade_date"] != pd.Timestamp("2024-01-06")]
    second_asset = make_daily_frame("CN:SZ:000001", periods=7)
    frame = pd.concat([first_asset, second_asset], ignore_index=True)

    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates=make_trade_dates(7),
        input_window=3,
        forecast_horizon=3,
    )

    snapshot = next(
        snapshot
        for snapshot in snapshots
        if snapshot.asset_id == "CN:SH:600418" and snapshot.origin_date == "2024-01-03"
    )
    assert snapshot.status == "insufficient_truth"
    assert snapshot.future_timestamps == (
        "2024-01-04",
        "2024-01-05",
        "2024-01-06",
    )
    assert [row["timestamp"] for row in snapshot.realized] == [
        "2024-01-04",
        "2024-01-05",
    ]
    assert "2024-01-06" not in [row["timestamp"] for row in snapshot.realized]
    assert "missing" in snapshot.reason


def test_explicit_global_calendar_detects_missing_asset_truth_without_padding():
    frame = make_daily_frame(periods=7)
    frame = frame[frame["trade_date"] != pd.Timestamp("2024-01-04")]
    global_calendar = [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-06",
        "2024-01-07",
    ]

    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates=global_calendar,
        input_window=3,
        forecast_horizon=3,
    )
    snapshot = next(
        snapshot for snapshot in snapshots if snapshot.origin_date == "2024-01-03"
    )

    assert snapshot.future_timestamps == (
        "2024-01-04",
        "2024-01-05",
        "2024-01-06",
    )
    assert snapshot.status == "insufficient_truth"
    assert snapshot.realized == ()


def test_input_fingerprint_changes_when_a_history_value_changes():
    first_snapshots = data.build_rolling_snapshots(
        make_daily_frame(periods=10),
        trade_dates=make_trade_dates(10),
        input_window=5,
        forecast_horizon=1,
    )
    first = next(
        snapshot for snapshot in first_snapshots if snapshot.origin_date == "2024-01-06"
    )
    changed_frame = make_daily_frame(periods=10, close_offset=0.01)
    changed_snapshots = data.build_rolling_snapshots(
        changed_frame,
        trade_dates=make_trade_dates(10),
        input_window=5,
        forecast_horizon=1,
    )
    changed = next(
        snapshot
        for snapshot in changed_snapshots
        if snapshot.origin_date == "2024-01-06"
    )

    assert first.status == changed.status == "ready"
    assert first.input_fingerprint != changed.input_fingerprint
    assert set(thaw_json_value(first.history[0])) == set(HISTORY_COLUMNS)
    assert json.loads(json.dumps(thaw_json_value(first.history))) == thaw_json_value(
        first.history
    )


def test_multiple_assets_and_origins_have_deterministic_keys():
    frame = pd.concat(
        [make_daily_frame(), make_daily_frame("CN:SZ:000001")],
        ignore_index=True,
    )

    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates=make_trade_dates(),
        input_window=3,
        forecast_horizon=2,
        origin_dates=["2024-01-10", "2024-01-11"],
    )

    assert [snapshot.key for snapshot in snapshots] == [
        "CN:SH:600418|2024-01-10",
        "CN:SH:600418|2024-01-11",
        "CN:SZ:000001|2024-01-10",
        "CN:SZ:000001|2024-01-11",
    ]
    assert all(snapshot.status == "ready" for snapshot in snapshots)


@pytest.mark.parametrize(
    ("column", "value", "reason_fragment"),
    [
        ("high", 99.0, "OHLC"),
        ("open", float("nan"), "finite"),
    ],
)
def test_invalid_ohlc_or_nan_returns_invalid_input(column, value, reason_fragment):
    frame = make_daily_frame(periods=8)
    frame.loc[frame["trade_date"] == pd.Timestamp("2024-01-04"), column] = value

    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates=make_trade_dates(8),
        input_window=3,
        forecast_horizon=1,
    )
    snapshot = next(
        snapshot for snapshot in snapshots if snapshot.origin_date == "2024-01-05"
    )

    assert snapshot.status == "invalid_input"
    assert reason_fragment in snapshot.reason


def test_duplicate_asset_dates_are_invalid_input():
    frame = make_daily_frame(periods=8)
    frame = pd.concat([frame.iloc[:4], frame.iloc[[3]], frame.iloc[4:]], ignore_index=True)

    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates=make_trade_dates(8),
        input_window=3,
        forecast_horizon=1,
    )
    snapshot = next(
        snapshot for snapshot in snapshots if snapshot.origin_date == "2024-01-05"
    )

    assert snapshot.status == "invalid_input"
    assert snapshot.reason == "duplicate trade_date 2024-01-04 for asset CN:SH:600418"


def test_missing_required_column_is_rejected():
    frame = make_daily_frame(periods=8).drop(columns=["close"])

    with pytest.raises(ValueError, match="required columns.*close"):
        data.build_rolling_snapshots(
            frame,
            trade_dates=["2024-01-05"],
            input_window=3,
            forecast_horizon=1,
        )


def test_calendar_ordering_is_validated():
    frame = make_daily_frame(periods=8)

    with pytest.raises(ValueError, match="strictly increasing"):
        data.build_rolling_snapshots(
            frame,
            trade_dates=["2024-01-05", "2024-01-04"],
            input_window=3,
            forecast_horizon=1,
        )


def test_load_daily_bars_uses_normalized_ids_and_safe_sql(monkeypatch):
    calls = {}
    rows = [
        {
            "trade_date": "2024-01-02",
            "asset_id": "CN:SH:600418",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1_000.0,
            "amount": 100_000.0,
            "trade_status": "normal",
            "is_st": False,
        }
    ]

    @contextmanager
    def fake_connect(service):
        calls["service"] = service
        yield "connection"

    def fake_fetch_all(connection, sql, params):
        calls["connection"] = connection
        calls["sql"] = sql
        calls["params"] = params
        return rows

    monkeypatch.setattr(data, "connect", fake_connect)
    monkeypatch.setattr(data, "fetch_all", fake_fetch_all)

    result = data.load_daily_bars(("sh.600418",), "2024-01-31", "qfq", "research")

    assert calls["service"] == "research"
    assert calls["connection"] == "connection"
    assert " ".join(calls["sql"].split()) == (
        "SELECT trade_date::text AS trade_date, asset_id, open, high, low, close, "
        "volume, amount, trade_status, is_st FROM market_daily_bar WHERE "
        "adjust_type = %s AND trade_date <= %s AND asset_id = ANY(%s) ORDER BY "
        "asset_id, trade_date"
    )
    assert calls["params"] == ["qfq", "2024-01-31", ["CN:SH:600418"]]
    assert result.to_dict(orient="records") == rows


def test_load_global_trade_dates_returns_ordered_calendar(monkeypatch):
    calls = {}

    @contextmanager
    def fake_connect(service):
        calls["service"] = service
        yield "connection"

    def fake_fetch_all(connection, sql, params):
        calls["sql"] = sql
        calls["params"] = params
        return [
            {"trade_date": "2024-01-02"},
            {"trade_date": "2024-01-03"},
        ]

    monkeypatch.setattr(data, "connect", fake_connect)
    monkeypatch.setattr(data, "fetch_all", fake_fetch_all)

    result = data.load_global_trade_dates("qfq", "2024-01-31", "research")

    assert calls["service"] == "research"
    assert result == ["2024-01-02", "2024-01-03"]
    assert "SELECT DISTINCT trade_date::text AS trade_date" in " ".join(
        calls["sql"].split()
    )
    assert calls["params"] == ["qfq", "2024-01-31"]


def test_prepare_rolling_snapshots_loads_and_passes_global_calendar(monkeypatch):
    frame = make_daily_frame(periods=7)
    calls = []
    global_calendar = make_trade_dates(7)

    def fake_load_daily_bars(asset_ids, max_date, adjust_type, service):
        calls.append(("bars", asset_ids, max_date, adjust_type, service))
        return frame

    def fake_load_global_trade_dates(adjust_type, max_date, service):
        calls.append(("calendar", adjust_type, max_date, service))
        return global_calendar

    def fake_build_rolling_snapshots(
        loaded_frame,
        trade_dates,
        input_window,
        forecast_horizon,
        *,
        origin_dates=None,
    ):
        calls.append(
            (
                "build",
                loaded_frame,
                trade_dates,
                input_window,
                forecast_horizon,
                origin_dates,
            )
        )
        return ["prepared"]

    monkeypatch.setattr(data, "load_daily_bars", fake_load_daily_bars)
    monkeypatch.setattr(data, "load_global_trade_dates", fake_load_global_trade_dates)
    monkeypatch.setattr(data, "build_rolling_snapshots", fake_build_rolling_snapshots)

    result = data.prepare_rolling_snapshots(
        ("sh.600418",),
        "2024-01-31",
        "qfq",
        "research",
        3,
        2,
        origin_dates=["2024-01-03"],
    )

    assert result == ["prepared"]
    assert calls[0] == (
        "bars",
        ("sh.600418",),
        "2024-01-31",
        "qfq",
        "research",
    )
    assert calls[1] == ("calendar", "qfq", "2024-01-31", "research")
    assert calls[2][0] == "build"
    assert calls[2][1] is frame
    assert calls[2][2] == global_calendar
    assert calls[2][3:] == (3, 2, ["2024-01-03"])


def test_source_metadata_is_json_ready_and_preserves_query_timestamp():
    frame = make_daily_frame(periods=3)

    metadata = data.build_source_metadata(
        frame,
        adjust_type="qfq",
        query_timestamp="2026-08-06T05:00:00+00:00",
    )

    assert metadata == {
        "adjust_type": "qfq",
        "source_table": "market_daily_bar",
        "row_count": 3,
        "min_date": "2024-01-01",
        "max_date": "2024-01-03",
        "query_timestamp": "2026-08-06T05:00:00+00:00",
    }
    assert json.loads(json.dumps(metadata)) == metadata
