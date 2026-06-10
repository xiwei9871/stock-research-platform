import json

from stock_research.strategy_backtest_read_model import (
    import_strategy_backtest_replay_payload,
    load_strategy_backtest_replay_payload,
    replay_payload_to_read_model_rows,
)


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def _payload() -> dict:
    return {
        "strategy_id": "lhb_shortline",
        "strategy_name": "LHB Shortline Combo",
        "read_only": True,
        "config": {
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 20,
            "rebalance_frequency": "weekly",
        },
        "summary": {
            "combo_scheme": "lhb_shortline_combo_v1",
            "evidence_source": "phase16c fixture",
            "final_equity": 3.1279,
            "total_return": 2.1279,
            "max_drawdown": -0.044,
        },
        "equity_curve": [
            {"date": "2026-06-05", "equity": 2.9, "drawdown": -0.01, "net_return": 0.02},
            {"trade_date": "2026-06-08", "equity": 3.1279, "drawdown": 0.0, "turnover": 0.5},
        ],
        "positions": [
            {"rebalance_date": "2026-06-08", "asset_id": "CN:SZ:300615", "weight": 0.1, "rank": 1}
        ],
        "trades": [
            {"trade_date": "2026-06-08", "asset_id": "CN:SZ:300615", "side": "buy", "weight": 0.1}
        ],
    }


def test_replay_payload_to_read_model_rows_normalizes_run_and_child_rows():
    rows = replay_payload_to_read_model_rows(_payload())

    assert rows["run"]["run_id"] == "lhb_shortline:lhb_shortline_combo_v1:2026-01-01:2026-06-08"
    assert rows["run"]["strategy_id"] == "lhb_shortline"
    assert rows["run"]["combo_scheme"] == "lhb_shortline_combo_v1"
    assert rows["run"]["summary_json"]["final_equity"] == 3.1279
    assert rows["equity"][0]["trade_date"] == "2026-06-05"
    assert rows["equity"][1]["trade_date"] == "2026-06-08"
    assert rows["positions"][0]["asset_id"] == "CN:SZ:300615"
    assert rows["positions"][0]["row_index"] == 0
    assert rows["trades"][0]["side"] == "buy"


def test_import_strategy_backtest_replay_payload_upserts_all_tables(monkeypatch):
    from stock_research import strategy_backtest_read_model

    conn = _Connection()
    monkeypatch.setattr(strategy_backtest_read_model, "connect", lambda service: _Context(conn))

    result = import_strategy_backtest_replay_payload(_payload(), service="stock_research_test")

    assert result == {
        "run_id": "lhb_shortline:lhb_shortline_combo_v1:2026-01-01:2026-06-08",
        "equity_rows": 2,
        "position_rows": 1,
        "trade_rows": 1,
    }
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO backtest.strategy_backtest_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert json.loads(run_params["summary_json"])["final_equity"] == 3.1279
    sql_calls = [sql for sql, _params in conn.cursor_obj.calls]
    assert any("DELETE FROM backtest.strategy_backtest_equity" in sql for sql in sql_calls)
    assert any("INSERT INTO backtest.strategy_backtest_equity" in sql for sql in sql_calls)
    assert any("INSERT INTO backtest.strategy_backtest_position" in sql for sql in sql_calls)
    assert any("INSERT INTO backtest.strategy_backtest_trade" in sql for sql in sql_calls)


def test_load_strategy_backtest_replay_payload_rebuilds_dashboard_shape(monkeypatch):
    from stock_research import strategy_backtest_read_model

    def fake_fetch_all(conn, sql, params=None):
        if "FROM backtest.strategy_backtest_run" in sql:
            return [
                {
                    "run_id": "run-1",
                    "strategy_id": "mid_trend",
                    "strategy_name": "Mid Trend Combo",
                    "combo_scheme": "mid_trend_combo_v1",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-08",
                    "summary_json": {"combo_scheme": "mid_trend_combo_v1", "final_equity": 4.2},
                    "config_json": {"top_n": 5},
                }
            ]
        if "FROM backtest.strategy_backtest_equity" in sql:
            return [{"row_json": {"date": "2026-06-08", "equity": 4.2}}]
        if "FROM backtest.strategy_backtest_position" in sql:
            return [{"row_json": {"rebalance_date": "2026-06-08", "asset_id": "CN:SZ:000001", "weight": 0.2}}]
        if "FROM backtest.strategy_backtest_trade" in sql:
            return [{"row_json": {"trade_date": "2026-06-08", "asset_id": "CN:SZ:000001", "side": "buy"}}]
        return []

    monkeypatch.setattr(strategy_backtest_read_model, "connect", lambda service: _Context(_Connection()))
    monkeypatch.setattr(strategy_backtest_read_model, "fetch_all", fake_fetch_all)

    payload = load_strategy_backtest_replay_payload(
        "mid_trend",
        start_date="2026-01-01",
        end_date="2026-06-08",
        service="stock_research_test",
    )

    assert payload is not None
    assert payload["strategy_id"] == "mid_trend"
    assert payload["strategy_name"] == "Mid Trend Combo"
    assert payload["summary"]["final_equity"] == 4.2
    assert payload["equity_curve"] == [{"date": "2026-06-08", "equity": 4.2}]
    assert payload["positions"][0]["asset_id"] == "CN:SZ:000001"
    assert payload["trades"][0]["side"] == "buy"


def test_load_strategy_backtest_replay_payload_rebases_summary_to_requested_window(monkeypatch):
    from stock_research import strategy_backtest_read_model

    def fake_fetch_all(conn, sql, params=None):
        if "FROM backtest.strategy_backtest_run" in sql:
            return [
                {
                    "run_id": "run-1",
                    "strategy_id": "mid_trend",
                    "strategy_name": "Mid Trend Combo",
                    "combo_scheme": "mid_trend_combo_v1",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-08",
                    "summary_json": {
                        "combo_scheme": "mid_trend_combo_v1",
                        "start_date": "2025-01-01",
                        "end_date": "2026-06-02",
                        "actual_start_date": "2025-01-02",
                        "actual_end_date": "2026-06-02",
                        "periods": 340,
                        "final_equity": 4.2,
                        "total_return": 3.2,
                        "max_drawdown": -0.3,
                    },
                    "config_json": {"start_date": "2026-01-01", "end_date": "2026-06-08", "top_n": 20},
                }
            ]
        if "FROM backtest.strategy_backtest_equity" in sql:
            return [
                {"row_json": {"date": "2026-01-05", "equity": 2.0}},
                {"row_json": {"date": "2026-01-06", "equity": 3.0}},
                {"row_json": {"date": "2026-01-07", "equity": 2.4}},
            ]
        if "FROM backtest.strategy_backtest_position" in sql:
            return []
        if "FROM backtest.strategy_backtest_trade" in sql:
            return []
        return []

    monkeypatch.setattr(strategy_backtest_read_model, "connect", lambda service: _Context(_Connection()))
    monkeypatch.setattr(strategy_backtest_read_model, "fetch_all", fake_fetch_all)

    payload = load_strategy_backtest_replay_payload(
        "mid_trend",
        start_date="2026-01-01",
        end_date="2026-06-08",
        service="stock_research_test",
    )

    assert payload["summary"]["start_date"] == "2026-01-01"
    assert payload["summary"]["end_date"] == "2026-06-08"
    assert payload["summary"]["actual_start_date"] == "2026-01-05"
    assert payload["summary"]["actual_end_date"] == "2026-01-07"
    assert payload["summary"]["periods"] == 3
    assert payload["summary"]["final_equity"] == 1.2
    assert payload["summary"]["total_return"] == 0.2
    assert payload["summary"]["max_drawdown"] == -0.2
    assert [row["equity"] for row in payload["equity_curve"]] == [1.0, 1.5, 1.2]


def test_load_strategy_backtest_replay_payload_rebases_account_components_with_equity(monkeypatch):
    from stock_research import strategy_backtest_read_model

    def fake_fetch_all(conn, sql, params=None):
        if "FROM backtest.strategy_backtest_run" in sql:
            return [
                {
                    "run_id": "run-1",
                    "strategy_id": "lhb_shortline",
                    "strategy_name": "LHB Shortline Combo",
                    "combo_scheme": "lhb_shortline_combo_v1",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-08",
                    "summary_json": {"combo_scheme": "lhb_shortline_combo_v1", "final_equity": 3.0},
                    "config_json": {"start_date": "2026-01-01", "end_date": "2026-06-08"},
                }
            ]
        if "FROM backtest.strategy_backtest_equity" in sql:
            return [
                {"row_json": {"trade_date": "2026-01-05", "equity": 2.0, "cash": 1.4, "invested_notional": 0.6}},
                {"row_json": {"trade_date": "2026-01-06", "equity": 3.0, "cash": 2.1, "invested_notional": 0.9}},
            ]
        if "FROM backtest.strategy_backtest_position" in sql or "FROM backtest.strategy_backtest_trade" in sql:
            return []
        return []

    monkeypatch.setattr(strategy_backtest_read_model, "connect", lambda service: _Context(_Connection()))
    monkeypatch.setattr(strategy_backtest_read_model, "fetch_all", fake_fetch_all)

    payload = load_strategy_backtest_replay_payload(
        "lhb_shortline",
        start_date="2026-01-01",
        end_date="2026-06-08",
        service="stock_research_test",
    )

    assert payload["equity_curve"][0]["equity"] == 1.0
    assert payload["equity_curve"][0]["cash"] == 0.7
    assert payload["equity_curve"][0]["invested_notional"] == 0.3
    assert payload["equity_curve"][1]["equity"] == 1.5
    assert payload["equity_curve"][1]["cash"] == 1.05
    assert payload["equity_curve"][1]["invested_notional"] == 0.45
