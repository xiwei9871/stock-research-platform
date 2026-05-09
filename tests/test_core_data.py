from stock_research import core_data


class FakeConnection:
    def __init__(self):
        self.executed = []


def fake_execute(conn, sql, params=None):
    conn.executed.append((sql, params))


def test_sync_core_asset_master_maps_existing_public_assets(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute", fake_execute)

    core_data.sync_core_asset_master(conn)

    sql, params = conn.executed[0]
    assert "INSERT INTO core.asset_master" in sql
    assert "FROM asset_master" in sql
    assert "lower(exchange) || '.' || symbol" in sql
    assert "exchange = 'BJ'" in sql
    assert "exchange = 'SH' AND symbol LIKE '688%'" in sql
    assert "exchange = 'SZ' AND symbol ~ '^(300|301|302)'" in sql
    assert "ON CONFLICT (asset_id) DO UPDATE" in sql
    assert params is None


def test_build_asset_status_daily_uses_point_in_time_daily_bars(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute", fake_execute)

    core_data.build_asset_status_daily(
        conn,
        start_date="2026-05-06",
        end_date="2026-05-08",
    )

    sql, params = conn.executed[0]
    assert "INSERT INTO core.asset_status_daily" in sql
    assert "FROM market_daily_bar b" in sql
    assert "LEFT JOIN core.asset_master a" in sql
    assert "b.adjust_type = %s" in sql
    assert "b.trade_date >= %s" in sql
    assert "b.trade_date <= %s" in sql
    assert "b.trade_status = '1'" in sql
    assert "b.trade_status <> '1'" in sql
    assert "b.pct_chg >= " in sql
    assert "b.pct_chg <= -" in sql
    assert "ON CONFLICT (trade_date, asset_id) DO UPDATE" in sql
    assert params == ["hfq", "2026-05-06", "2026-05-08"]


def test_build_asset_status_daily_allows_open_date_range(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute", fake_execute)

    core_data.build_asset_status_daily(conn, adjust_type="qfq")

    sql, params = conn.executed[0]
    assert "b.trade_date >=" not in sql
    assert "b.trade_date <=" not in sql
    assert params == ["qfq"]


def test_build_industry_daily_bars_uses_historical_membership_windows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute", fake_execute)

    core_data.build_industry_daily_bars(
        conn,
        start_date="2026-05-01",
        end_date="2026-05-08",
        industry_system="csrc",
    )

    sql, params = conn.executed[0]
    assert "INSERT INTO market.industry_daily_bar" in sql
    assert "FROM market_daily_bar b" in sql
    assert "JOIN core.industry_membership m" in sql
    assert "m.start_date <= b.trade_date" in sql
    assert "(m.end_date IS NULL OR b.trade_date < m.end_date)" in sql
    assert "m.industry_system = %s" in sql
    assert "b.adjust_type = %s" in sql
    assert "b.trade_date >= %s" in sql
    assert "b.trade_date <= %s" in sql
    assert "ON CONFLICT (industry_system, industry_code, trade_date) DO UPDATE" in sql
    assert params == ["csrc", "hfq", "2026-05-01", "2026-05-08"]
