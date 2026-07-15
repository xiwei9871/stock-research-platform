import pytest

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


def test_sync_chinese_stock_names_from_akshare_upserts_public_and_core(monkeypatch):
    conn = FakeConnection()

    class FakeAk:
        @staticmethod
        def stock_info_a_code_name():
            import pandas as pd

            return pd.DataFrame(
                [
                    {"code": "001399", "name": "惠科股份"},
                    {"code": "688001", "name": "华兴源创"},
                ]
            )

    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "ak", FakeAk)

    count = core_data.sync_chinese_stock_names_from_akshare(conn)

    assert count == 2
    assert len(conn.executed_many) == 2
    public_sql, public_rows = conn.executed_many[0]
    core_sql, core_rows = conn.executed_many[1]
    assert "INSERT INTO asset_master" in public_sql
    assert "ON CONFLICT (asset_id) DO UPDATE" in public_sql
    assert "INSERT INTO core.asset_master" in core_sql
    assert "ON CONFLICT (asset_id) DO UPDATE" in core_sql
    assert "is_star" in core_sql
    assert public_rows[0] == (
        "CN:SZ:001399",
        core_data.SETTINGS.default_market,
        "001399",
        "SZ",
        "惠科股份",
        core_data.SETTINGS.default_currency,
    )
    assert core_rows[1] == (
        "CN:SH:688001",
        "688001.SH",
        "688001",
        "688001",
        "华兴源创",
        "SH",
        "STAR",
        True,
        False,
        True,
        False,
    )


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
    assert "market.lhb_top_list_daily" in sql
    assert "same_day_lhb_name" in sql
    assert "resolved_is_st" in sql
    assert "status_quality" in sql
    assert "b.adjust_type = %s" in sql
    assert "b.trade_date >= %s" in sql
    assert "b.trade_date <= %s" in sql
    assert "b.trade_status = '1'" in sql
    assert "b.trade_status <> '1'" in sql
    assert "b.pct_chg >= " in sql
    assert "b.pct_chg <= -" in sql
    assert "WHEN resolved_is_st THEN 4.8" in sql
    assert "WHEN is_beijing THEN 29.8" in sql
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


def test_asset_status_quality_rejects_zero_st_when_same_day_lhb_has_st(monkeypatch):
    monkeypatch.setattr(
        core_data,
        "fetch_all",
        lambda conn, sql, params: [
            {
                "trade_date": "2026-07-14",
                "lhb_st_count": 2,
                "asset_status_st_count": 0,
            }
        ],
    )

    with pytest.raises(RuntimeError, match="asset status ST quality violation"):
        core_data.assert_asset_status_daily_quality(
            object(),
            start_date="2026-07-14",
            end_date="2026-07-14",
        )


def test_asset_status_quality_accepts_nonzero_resolved_st(monkeypatch):
    monkeypatch.setattr(core_data, "fetch_all", lambda conn, sql, params: [])

    result = core_data.assert_asset_status_daily_quality(
        object(),
        start_date="2026-07-14",
        end_date="2026-07-14",
    )

    assert result["violation_count"] == 0


def test_asset_status_service_runs_quality_guard_after_build(monkeypatch):
    calls = []

    class ConnectionContext:
        def __enter__(self):
            return "conn"

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(core_data, "connect", lambda service: ConnectionContext())
    monkeypatch.setattr(
        core_data,
        "build_asset_status_daily",
        lambda conn, start_date, end_date, adjust_type: calls.append(("build", conn, start_date, end_date, adjust_type)),
    )
    monkeypatch.setattr(
        core_data,
        "assert_asset_status_daily_quality",
        lambda conn, start_date, end_date: calls.append(("quality", conn, start_date, end_date)),
    )

    core_data.build_asset_status_daily_for_service(
        start_date="2026-07-14",
        end_date="2026-07-14",
        adjust_type="hfq",
        service="stock_research",
    )

    assert calls == [
        ("build", "conn", "2026-07-14", "2026-07-14", "hfq"),
        ("quality", "conn", "2026-07-14", "2026-07-14"),
    ]


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
    assert ("CN:SH:688256", "ths", "309135", "人工智能", "2026-06-30", "akshare:concept_constituents") in membership_rows
    assert ("CN:SZ:000063", "ths", "309135", "人工智能", "2026-06-30", "akshare:concept_constituents") in membership_rows
    assert ("CN:SZ:300024", "ths", "300024", "机器人概念", "2026-06-30", "akshare:concept_constituents") in membership_rows
    assert any("UPDATE core.concept_membership" in sql for sql, _params in conn.executed)


def test_sync_concept_memberships_from_akshare_defaults_to_eastmoney_sources(monkeypatch):
    import pandas as pd

    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "execute", fake_execute)

    class FakeAk:
        @staticmethod
        def stock_board_concept_cons_em(symbol):
            assert symbol == "BK0545"
            return pd.DataFrame([{"代码": "300024", "名称": "机器人"}])

    monkeypatch.setattr(core_data, "ak", FakeAk)
    monkeypatch.setattr(
        core_data,
        "fetch_eastmoney_concept_boards_direct",
        lambda: pd.DataFrame([{"板块名称": "机器人概念", "板块代码": "BK0545"}]),
    )

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
    assert board_rows == [("em", "BK0545", "机器人概念", "eastmoney:qt_clist_concept_board", True)]
    assert membership_rows == [
        ("CN:SZ:300024", "em", "BK0545", "机器人概念", "2026-07-09", "akshare:stock_board_concept_cons_em")
    ]


def test_sync_concept_memberships_retries_board_fetch_once(monkeypatch):
    import pandas as pd

    conn = FakeConnection()
    calls = []
    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "execute", fake_execute)

    def flaky_board_fetcher():
        calls.append("board")
        if len(calls) == 1:
            raise ConnectionError("remote disconnected")
        return pd.DataFrame([{"板块名称": "机器人概念", "板块代码": "BK0545"}])

    def fake_constituent_fetcher(symbol):
        return pd.DataFrame([{"代码": "300024", "名称": "机器人"}])

    result = core_data.sync_concept_memberships_from_akshare(
        conn,
        trade_date="2026-07-09",
        concept_system="em",
        board_fetcher=flaky_board_fetcher,
        constituent_fetcher=fake_constituent_fetcher,
    )

    assert result == {"boards": 1, "memberships": 1, "failed_concepts": []}
    assert calls == ["board", "board"]


def test_sync_concept_memberships_reports_board_fetch_failure(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "execute", fake_execute)

    def failing_board_fetcher():
        raise ConnectionError("remote disconnected")

    result = core_data.sync_concept_memberships_from_akshare(
        conn,
        trade_date="2026-07-09",
        concept_system="em",
        board_fetcher=failing_board_fetcher,
        constituent_fetcher=lambda symbol: None,
    )

    assert result["boards"] == 0
    assert result["memberships"] == 0
    assert result["failed_concepts"] == ["board_fetch_failed: remote disconnected"]
    assert conn.executed_many == []


def test_fetch_eastmoney_concept_boards_direct_uses_curl_pages(monkeypatch):
    calls = []

    def fake_curl(urls, params, *, retries, retry_sleep_seconds, timeout_seconds=15):
        calls.append((urls, params, retries, retry_sleep_seconds, timeout_seconds))
        return {
            "data": {
                "total": 2,
                "diff": [
                    {"f12": "BK0545", "f14": "机器人概念"},
                    {"f12": "BK0800", "f14": "人工智能"},
                ],
            }
        }

    monkeypatch.setattr(core_data, "curl_eastmoney_json", fake_curl)

    frame = core_data.fetch_eastmoney_concept_boards_direct(page_size=100)

    assert frame.to_dict("records") == [
        {"板块名称": "机器人概念", "板块代码": "BK0545"},
        {"板块名称": "人工智能", "板块代码": "BK0800"},
    ]
    assert calls[0][1]["fs"] == "m:90 t:3 f:!50"
    assert calls[0][1]["fields"] == "f12,f14"
