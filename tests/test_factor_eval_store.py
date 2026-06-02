from decimal import Decimal

from pandas.api.types import is_float_dtype

from stock_research import factor_eval_store


def test_load_factor_eval_inputs_queries_factor_and_label_tables(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "factor.factor_daily" in sql:
            return [{"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0}]
        return [{"trade_date": "2026-01-01", "asset_id": "A", "forward_return": 0.02}]

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_eval_store, "fetch_all", fake_fetch_all)

    factors, returns = factor_eval_store.load_factor_eval_inputs(
        factor_name="ret_20",
        start_date="2026-01-01",
        end_date="2026-02-01",
        horizon=5,
    )

    assert factors.iloc[0]["factor_value"] == 1.0
    assert returns.iloc[0]["forward_return_5d"] == 0.02
    assert len(calls) == 2
    assert calls[0][1] == ["ret_20", "v1", "2026-01-01", "2026-02-01"]


def test_load_multi_horizon_factor_eval_inputs_pivots_return_columns(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "factor.factor_daily" in sql:
            return [{"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0}]
        return [
            {"trade_date": "2026-01-01", "asset_id": "A", "horizon": 5, "forward_return": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "A", "horizon": 10, "forward_return": 0.04},
        ]

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_eval_store, "fetch_all", fake_fetch_all)

    factors, returns = factor_eval_store.load_multi_horizon_factor_eval_inputs(
        factor_name="ret_20",
        start_date="2026-01-01",
        end_date="2026-02-01",
        horizons=[5, 10],
    )

    assert factors.iloc[0]["factor_value"] == 1.0
    assert returns.iloc[0]["forward_return_5d"] == 0.02
    assert returns.iloc[0]["forward_return_10d"] == 0.04
    assert calls[1][1] == [
        "forward_return",
        "v1",
        [5, 10],
        "2026-01-01",
        "2026-02-01",
    ]


def test_load_multi_horizon_factor_eval_inputs_normalizes_decimal_columns_to_float(monkeypatch):
    def fake_fetch_all(conn, sql, params=None):
        if "factor.factor_daily" in sql:
            return [
                {
                    "trade_date": "2026-01-01",
                    "asset_id": "A",
                    "factor_value": Decimal("1.25"),
                }
            ]
        return [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "horizon": 5,
                "forward_return": Decimal("0.02"),
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "horizon": 10,
                "forward_return": Decimal("0.04"),
            },
        ]

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_eval_store, "fetch_all", fake_fetch_all)

    factors, returns = factor_eval_store.load_multi_horizon_factor_eval_inputs(
        factor_name="ret_20",
        start_date="2026-01-01",
        end_date="2026-02-01",
        horizons=[5, 10],
    )

    assert is_float_dtype(factors["factor_value"])
    assert is_float_dtype(returns["forward_return_5d"])
    assert is_float_dtype(returns["forward_return_10d"])
    assert factors.iloc[0]["factor_value"] == 1.25
    assert returns.iloc[0]["forward_return_5d"] == 0.02
    assert returns.iloc[0]["forward_return_10d"] == 0.04


def test_store_factor_eval_run_writes_metrics_json(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))

    class Conn:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(Conn()))

    factor_eval_store.store_factor_eval_run(
        run_id="run-1",
        factor_name="ret_20",
        calc_version="v1",
        start_date="2026-01-01",
        end_date="2026-02-01",
        horizons=[5, 10],
        primary_horizon=5,
        status="approved",
        reason="passed_thresholds",
        metrics={"mean_ic": 0.03},
    )

    assert "INSERT INTO factor.factor_eval_run" in calls[0][0]
    assert calls[0][1]["metrics"] == '{"mean_ic": 0.03}'


def test_store_factor_approval_upserts_status(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))

    class Conn:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(Conn()))

    factor_eval_store.store_factor_approval(
        factor_name="ret_20",
        calc_version="v1",
        score_version="manual_v1",
        status="approved",
        reason="passed_thresholds",
        eval_run_id="run-1",
    )

    assert "INSERT INTO factor.factor_approval" in calls[0][0]
    assert calls[0][1]["score_version"] == "manual_v1"


def test_load_factor_eval_metadata_frame_returns_registry_rows():
    frame = factor_eval_store.load_factor_eval_metadata_frame(["ret_20"])

    assert list(frame["factor_name"]) == ["ret_20"]
    assert frame.iloc[0]["factor_group"] == "momentum"
    assert frame.iloc[0]["direction"] == "higher"


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
