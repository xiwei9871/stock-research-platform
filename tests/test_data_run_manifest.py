from stock_research import data_run_manifest


def test_load_recent_data_run_manifest_trade_date_fetches_latest_row_per_module(monkeypatch):
    calls = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        calls["service"] = service
        return FakeConnection()

    def fake_fetch_all(conn, sql, params):
        calls["sql"] = sql
        calls["params"] = params
        return [{"module": "strategy_lhb_shortline", "source": "strategy_eod"}]

    monkeypatch.setattr(data_run_manifest, "connect", fake_connect)
    monkeypatch.setattr(data_run_manifest, "fetch_all", fake_fetch_all)

    rows = data_run_manifest.load_recent_data_run_manifest(trade_date="2026-07-02", service="research")

    assert rows == [{"module": "strategy_lhb_shortline", "source": "strategy_eod"}]
    assert calls["service"] == "research"
    assert calls["params"] == {"trade_date": "2026-07-02"}
    assert "PARTITION BY module, source" in calls["sql"]
    assert "run_id = (SELECT run_id FROM latest)" not in calls["sql"]


def test_load_strategy_publication_manifest_is_bound_to_trade_date_and_run_id(monkeypatch):
    calls = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(data_run_manifest, "connect", lambda service: FakeConnection())
    monkeypatch.setattr(
        data_run_manifest,
        "fetch_all",
        lambda _conn, sql, params: calls.update(sql=sql, params=params) or [],
    )

    rows = data_run_manifest.load_strategy_publication_manifest(
        trade_date="2026-07-24",
        run_id="strategy-eod-2026-07-24-local",
        service="research",
    )

    assert rows == []
    assert calls["params"] == {
        "trade_date": "2026-07-24",
        "run_id": "strategy-eod-2026-07-24-local",
    }
    assert "trade_date = %(trade_date)s" in calls["sql"]
    assert "run_id = %(run_id)s" in calls["sql"]
    for module in (
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    ):
        assert module in calls["sql"]
