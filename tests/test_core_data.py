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


def test_sync_concept_memberships_from_akshare_defaults_to_ths_sources(monkeypatch):
    import pandas as pd

    conn = FakeConnection()
    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "execute", fake_execute)

    class FakeAk:
        @staticmethod
        def stock_board_concept_name_ths():
            return pd.DataFrame([{"name": "阿尔茨海默概念", "code": "308614"}])

    monkeypatch.setattr(core_data, "ak", FakeAk)
    monkeypatch.setattr(
        core_data,
        "fetch_ths_concept_constituents_direct",
        lambda symbol: pd.DataFrame([{"代码": "301015", "名称": "百洋医药"}]) if symbol == "308614" else pd.DataFrame(),
    )

    result = core_data.sync_concept_memberships_from_akshare(
        conn,
        trade_date="2026-07-09",
        concept_system="ths",
    )

    assert result == {"boards": 1, "memberships": 1, "failed_concepts": []}
    board_sql, board_rows = conn.executed_many[0]
    membership_sql, membership_rows = conn.executed_many[1]
    assert "INSERT INTO core.concept_board" in board_sql
    assert "INSERT INTO core.concept_membership" in membership_sql
    assert board_rows == [("ths", "308614", "阿尔茨海默概念", "akshare:stock_board_concept_name_ths", True)]
    assert membership_rows == [
        ("CN:SZ:301015", "ths", "308614", "阿尔茨海默概念", "2026-07-09", "ths:q.10jqka.com.cn_gn_detail")
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


def test_sync_concept_memberships_applies_offset_before_limit(monkeypatch):
    import pandas as pd

    conn = FakeConnection()
    seen_symbols = []
    monkeypatch.setattr(core_data, "execute_many", fake_execute_many)
    monkeypatch.setattr(core_data, "execute", fake_execute)

    def fake_board_fetcher():
        return pd.DataFrame(
            [
                {"板块名称": "跳过概念", "板块代码": "BK0001"},
                {"板块名称": "保留概念", "板块代码": "BK0002"},
                {"板块名称": "截断概念", "板块代码": "BK0003"},
            ]
        )

    def fake_constituent_fetcher(symbol):
        seen_symbols.append(symbol)
        return pd.DataFrame([{"代码": "300024", "名称": "机器人"}])

    result = core_data.sync_concept_memberships_from_akshare(
        conn,
        trade_date="2026-07-09",
        concept_system="em",
        board_fetcher=fake_board_fetcher,
        constituent_fetcher=fake_constituent_fetcher,
        max_concepts=1,
        offset=1,
    )

    assert result == {"boards": 1, "memberships": 1, "failed_concepts": []}
    assert seen_symbols == ["保留概念"]
    board_sql, board_rows = conn.executed_many[0]
    assert "INSERT INTO core.concept_board" in board_sql
    assert board_rows == [("em", "BK0002", "保留概念", "akshare:stock_board_concept_name_ths", True)]


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
    assert "https://33.push2.eastmoney.com/api/qt/clist/get" in calls[0][0]
    assert "https://82.push2.eastmoney.com/api/qt/clist/get" in calls[0][0]
    assert calls[0][1]["fs"] == "m:90 t:3 f:!50"
    assert calls[0][1]["fields"] == "f12,f14"


def test_fetch_ths_concept_constituents_direct_parses_stock_rows(monkeypatch):
    html = """
    <table>
      <thead><tr><th>序号</th><th>代码</th><th>名称</th><th>现价</th></tr></thead>
      <tbody>
        <tr><td>1</td><td><a>301015</a></td><td><a>百洋医药</a></td><td>22.00</td></tr>
        <tr><td>2</td><td><a>688271</a></td><td><a>联影医疗</a></td><td>105.55</td></tr>
      </tbody>
    </table>
    """
    calls = []

    class FakeResponse:
        text = html

    def fake_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return FakeResponse()

    monkeypatch.setattr(core_data.requests, "get", fake_get)

    frame = core_data.fetch_ths_concept_constituents_direct("308614")

    assert frame[["代码", "名称"]].to_dict("records") == [
        {"代码": "301015", "名称": "百洋医药"},
        {"代码": "688271", "名称": "联影医疗"},
    ]
    assert calls[0][0] == "http://q.10jqka.com.cn/gn/detail/field/199112/order/desc/page/1/ajax/1/code/308614"
