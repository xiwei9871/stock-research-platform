from stock_research import corporate_actions


class FakeConnection:
    def __init__(self):
        self.executed = []


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def fake_execute(conn, sql, params=None):
    conn.executed.append((sql, params))


def test_build_adjustment_factors_uses_qfq_hfq_when_raw_bars_are_missing(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(corporate_actions, "execute", fake_execute)

    corporate_actions.build_adjustment_factors(
        conn,
        start_date="2024-05-27",
        end_date="2024-05-31",
        source_version="derived_v1",
    )

    sql, params = conn.executed[0]
    assert "INSERT INTO market.adjustment_factor" in sql
    assert "FROM market_daily_bar qfq" in sql
    assert "JOIN market_daily_bar hfq" in sql
    assert "LEFT JOIN market_daily_bar raw" in sql
    assert "hfq.adjust_type = 'hfq'" in sql
    assert "qfq.adjust_type = 'qfq'" in sql
    assert "raw.adjust_type = 'raw'" in sql
    assert "COALESCE(qfq.close / NULLIF(raw.close, 0), 1.0)" in sql
    assert "COALESCE(hfq.close / NULLIF(raw.close, 0), hfq.close / NULLIF(qfq.close, 0))" in sql
    assert "qfq.trade_date >= %s" in sql
    assert "qfq.trade_date <= %s" in sql
    assert "ON CONFLICT (asset_id, trade_date, source_version) DO UPDATE" in sql
    assert params == ["derived_v1", "2024-05-27", "2024-05-31"]


def test_build_adjustment_factors_allows_open_date_range(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(corporate_actions, "execute", fake_execute)

    corporate_actions.build_adjustment_factors(conn)

    sql, params = conn.executed[0]
    assert "qfq.trade_date >=" not in sql
    assert "qfq.trade_date <=" not in sql
    assert params == ["derived_market_daily_bar_v1"]


def test_build_corporate_actions_from_factors_detects_factor_changes(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(corporate_actions, "execute", fake_execute)

    corporate_actions.build_corporate_actions_from_factors(
        conn,
        start_date="2024-05-27",
        end_date="2024-05-31",
        source_version="derived_actions_v1",
        factor_source_version="derived_factors_v1",
    )

    sql, params = conn.executed[0]
    assert "INSERT INTO market.corporate_action" in sql
    assert "lag(hfq_factor) OVER" in sql
    assert "source_version = %s" in sql
    assert "factor_after IS DISTINCT FROM factor_before" in sql
    assert "'adjustment_factor_change' AS action_type" in sql
    assert "event_date >= %s" in sql
    assert "event_date <= %s" in sql
    assert "ON CONFLICT (asset_id, event_date, action_type, source_version) DO UPDATE" in sql
    assert params == [
        "derived_actions_v1",
        "derived_factors_v1",
        "2024-05-27",
        "2024-05-31",
    ]


def test_service_wrappers_open_connection(monkeypatch):
    conn = FakeConnection()
    calls = []

    monkeypatch.setattr(corporate_actions, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(
        corporate_actions,
        "build_adjustment_factors",
        lambda opened, **kwargs: calls.append(("factors", opened, kwargs)),
    )
    monkeypatch.setattr(
        corporate_actions,
        "build_corporate_actions_from_factors",
        lambda opened, **kwargs: calls.append(("actions", opened, kwargs)),
    )

    corporate_actions.build_adjustment_factors_for_service(
        start_date="2024-05-27",
        source_version="derived_v1",
        service="research",
    )
    corporate_actions.build_corporate_actions_from_factors_for_service(
        end_date="2024-05-31",
        source_version="actions_v1",
        factor_source_version="factors_v1",
        service="research",
    )

    assert calls == [
        (
            "factors",
            conn,
            {
                "start_date": "2024-05-27",
                "end_date": None,
                "source_version": "derived_v1",
            },
        ),
        (
            "actions",
            conn,
            {
                "start_date": None,
                "end_date": "2024-05-31",
                "source_version": "actions_v1",
                "factor_source_version": "factors_v1",
            },
        ),
    ]
