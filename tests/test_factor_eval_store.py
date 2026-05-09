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


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
