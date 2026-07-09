from stock_research import core_data


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.executed_many = []


def fake_execute(conn, sql, params=None):
    conn.executed.append((sql, params))


def fake_execute_many(conn, sql, rows):
    conn.executed_many.append((sql, list(rows)))


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


def test_sync_core_asset_master_does_not_overwrite_existing_region(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute", fake_execute)

    core_data.sync_core_asset_master(conn)

    sql, _params = conn.executed[0]
    assert "NULL AS region" not in sql
    assert "region = EXCLUDED.region" not in sql
    assert "region = COALESCE(NULLIF(a.region, ''), EXCLUDED.region)" in sql


def test_sync_chinese_stock_names_from_akshare_updates_public_and_core(monkeypatch):
    conn = FakeConnection()

    class FakeAk:
        @staticmethod
        def stock_info_a_code_name():
            import pandas as pd

            return pd.DataFrame(
                [
                    {"code": "002484", "name": "江海股份"},
                    {"code": "600183", "name": "生益科技"},
                ]
            )

    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "ak", FakeAk)

    count = core_data.sync_chinese_stock_names_from_akshare(conn)

    assert count == 2
    assert len(conn.executed_many) == 2
    public_sql, public_rows = conn.executed_many[0]
    core_sql, core_rows = conn.executed_many[1]
    assert "UPDATE asset_master" in public_sql
    assert "name = data.name" in public_sql
    assert "UPDATE core.asset_master" in core_sql
    assert "ts_code = data.ts_code" in core_sql
    assert public_rows[0] == ("002484", "江海股份", "002484.SZ")
    assert core_rows[1] == ("600183", "生益科技", "600183.SH")


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
    assert "GROUP BY" in sql
    assert "m.asset_id" in sql
    assert "m.level = 1" in sql
    assert "m.start_date <= b.trade_date" in sql
    assert "(m.end_date IS NULL OR b.trade_date < m.end_date)" in sql
    assert "m.industry_system = %s" in sql
    assert "b.adjust_type = %s" in sql
    assert "b.trade_date >= %s" in sql
    assert "b.trade_date <= %s" in sql
    assert "ON CONFLICT (industry_system, industry_code, trade_date) DO UPDATE" in sql
    assert params == ["csrc", "hfq", "2026-05-01", "2026-05-08"]


def test_build_concept_daily_bars_uses_point_in_time_memberships(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute", fake_execute)

    core_data.build_concept_daily_bars(
        conn,
        start_date="2026-06-26",
        end_date="2026-06-26",
        concept_system="ths",
        adjust_type="qfq",
    )

    sql, params = conn.executed[0]
    assert "INSERT INTO market.concept_daily_bar" in sql
    assert "FROM market_daily_bar b" in sql
    assert "JOIN core.concept_membership m" in sql
    assert "m.start_date <= b.trade_date" in sql
    assert "(m.end_date IS NULL OR b.trade_date < m.end_date)" in sql
    assert "m.concept_system = %s" in sql
    assert "b.adjust_type = %s" in sql
    assert "b.trade_date >= %s" in sql
    assert "b.trade_date <= %s" in sql
    assert "ON CONFLICT (concept_system, concept_code, trade_date) DO UPDATE" in sql
    assert params == ["ths", "qfq", "2026-06-26", "2026-06-26"]


def test_sync_concept_memberships_from_akshare_upserts_boards_and_members(monkeypatch):
    import pandas as pd

    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "execute", fake_execute)

    def fake_board_fetcher():
        return pd.DataFrame(
            [
                {"name": "人工智能", "code": "309135"},
                {"name": "机器人概念", "code": "300024"},
            ]
        )

    def fake_constituent_fetcher(concept_name):
        if concept_name == "人工智能":
            return pd.DataFrame(
                [
                    {"代码": "688256", "名称": "寒武纪"},
                    {"代码": "000063", "名称": "中兴通讯"},
                ]
            )
        return pd.DataFrame([{"代码": "300024", "名称": "机器人"}])

    result = core_data.sync_concept_memberships_from_akshare(
        conn,
        trade_date="2026-06-30",
        concept_system="ths",
        board_fetcher=fake_board_fetcher,
        constituent_fetcher=fake_constituent_fetcher,
    )

    assert result == {"boards": 2, "memberships": 3, "failed_concepts": []}
    board_sql, board_rows = conn.executed_many[0]
    membership_sql, membership_rows = conn.executed_many[1]
    assert "INSERT INTO core.concept_board" in board_sql
    assert "INSERT INTO core.concept_membership" in membership_sql
    assert board_rows[0] == ("ths", "309135", "人工智能", "akshare:stock_board_concept_name_ths", True)
    assert ("688256.SH", "ths", "309135", "人工智能", "2026-06-30", "akshare:concept_constituents") in membership_rows
    assert ("000063.SZ", "ths", "309135", "人工智能", "2026-06-30", "akshare:concept_constituents") in membership_rows
    assert ("300024.SZ", "ths", "300024", "机器人概念", "2026-06-30", "akshare:concept_constituents") in membership_rows
    assert any("UPDATE core.concept_membership" in sql for sql, _params in conn.executed)


def test_sync_concept_memberships_from_akshare_defaults_to_eastmoney_sources(monkeypatch):
    import pandas as pd

    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "execute", fake_execute)

    class FakeAk:
        @staticmethod
        def stock_board_concept_name_em():
            return pd.DataFrame([{"板块名称": "机器人概念", "板块代码": "BK0545"}])

        @staticmethod
        def stock_board_concept_cons_em(symbol):
            assert symbol == "BK0545"
            return pd.DataFrame([{"代码": "300024", "名称": "机器人"}])

    monkeypatch.setattr(core_data, "ak", FakeAk)

    result = core_data.sync_concept_memberships_from_akshare(
        conn,
        trade_date="2026-07-09",
        concept_system="em",
    )

    assert result == {"boards": 1, "memberships": 1, "failed_concepts": []}
    board_sql, board_rows = conn.executed_many[0]
    membership_sql, membership_rows = conn.executed_many[1]
    assert "INSERT INTO core.concept_board" in board_sql
    assert "INSERT INTO core.concept_membership" in membership_sql
    assert board_rows == [("em", "BK0545", "机器人概念", "akshare:stock_board_concept_name_em", True)]
    assert membership_rows == [
        ("300024.SZ", "em", "BK0545", "机器人概念", "2026-07-09", "akshare:stock_board_concept_cons_em")
    ]
