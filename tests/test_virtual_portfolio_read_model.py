import json

from stock_research.simulation.virtual_portfolio_read_model import (
    import_virtual_portfolio_review,
    load_virtual_portfolio_read_model_rows,
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


def _review_payload() -> dict:
    return {
        "trade_date": "2026-05-29",
        "portfolio_id": "p2_smoke_demo",
        "status": "manual_review_required",
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
        "history_rows": [
            {
                "trade_date": "2026-05-28",
                "strategy_id": "p2_smoke:demo",
                "cash": 42000.0,
                "market_value": 58000.0,
                "equity": 100000.0,
                "drawdown": -0.04,
                "exposure_pct": 0.58,
                "open_position_count": 1,
                "risk_level": "normal",
                "source_artifact_path": "outputs/p2_smoke/state_2026-05-28.json",
            },
            {
                "trade_date": "2026-05-29",
                "strategy_id": "p2_smoke:demo",
                "cash": 38000.0,
                "market_value": 59000.0,
                "equity": 97000.0,
                "drawdown": -0.11,
                "exposure_pct": 0.61,
                "open_position_count": 1,
                "risk_level": "warning",
                "source_artifact_path": "outputs/p2_smoke/state_2026-05-29.json",
            },
        ],
        "latest_positions": [
            {
                "trade_date": "2026-05-29",
                "strategy_id": "p2_smoke:demo",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001",
                "stock_name": "P2 Smoke A",
                "quantity": 1000,
                "market_value": 59000.0,
                "weight": 0.61,
                "cost_basis": 56000.0,
                "unrealized_pnl": 3000.0,
            }
        ],
    }


def test_load_virtual_portfolio_read_model_rows_preserves_state_and_position_paths(tmp_path):
    json_path = tmp_path / "virtual_portfolio_review_2026-05-29_p2_smoke_demo.json"
    json_path.write_text(json.dumps(_review_payload()), encoding="utf-8")

    rows = load_virtual_portfolio_read_model_rows(json_path)

    assert rows["states"][0]["portfolio_id"] == "p2_smoke_demo"
    assert rows["states"][1]["trade_date"] == "2026-05-29"
    assert rows["states"][1]["risk_level"] == "warning"
    assert rows["states"][1]["review_status"] == "manual_review_required"
    assert rows["states"][1]["source_artifact_path"].endswith("state_2026-05-29.json")
    assert rows["positions"][0]["stock_code"] == "600001"
    assert rows["positions"][0]["source_artifact_path"] == str(json_path)


def test_load_virtual_portfolio_read_model_rows_defaults_confirmation_to_required(tmp_path):
    payload = _review_payload()
    payload.pop("human_confirmation_required")
    json_path = tmp_path / "virtual_portfolio_review_2026-05-29_p2_smoke_demo.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = load_virtual_portfolio_read_model_rows(json_path)

    assert rows["states"][0]["human_confirmation_required"] is True


def test_import_virtual_portfolio_review_upserts_states_and_positions(monkeypatch, tmp_path):
    from stock_research.simulation import virtual_portfolio_read_model

    json_path = tmp_path / "virtual_portfolio_review_2026-05-29_p2_smoke_demo.json"
    json_path.write_text(json.dumps(_review_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(
        virtual_portfolio_read_model,
        "connect",
        lambda service: _Context(conn),
    )

    result = import_virtual_portfolio_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["state_count"] == 2
    assert result["position_count"] == 1
    assert result["portfolio_ids"] == ["p2_smoke_demo"]
    state_sql, state_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO simulation.virtual_portfolio_state_daily" in state_sql
    assert "ON CONFLICT (portfolio_id, trade_date, strategy_id)" in state_sql
    assert state_params["portfolio_id"] == "p2_smoke_demo"
    assert state_params["review_status"] == "manual_review_required"
    position_sql, position_params = conn.cursor_obj.calls[2]
    assert "INSERT INTO simulation.virtual_portfolio_position_daily" in position_sql
    assert "ON CONFLICT (portfolio_id, trade_date, strategy_id, stock_code)" in position_sql
    assert position_params["stock_code"] == "600001"


def test_import_virtual_portfolio_review_accepts_directory(monkeypatch, tmp_path):
    from stock_research.simulation import virtual_portfolio_read_model

    first = _review_payload()
    second = {
        **_review_payload(),
        "trade_date": "2026-05-30",
        "portfolio_id": "p2_smoke_demo_2",
    }
    (tmp_path / "virtual_portfolio_review_2026-05-29_p2_smoke_demo.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "virtual_portfolio_review_2026-05-30_p2_smoke_demo_2.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    (tmp_path / "ignore_me.json").write_text(json.dumps(first), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(
        virtual_portfolio_read_model,
        "connect",
        lambda service: _Context(conn),
    )

    result = import_virtual_portfolio_review(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["portfolio_ids"] == ["p2_smoke_demo", "p2_smoke_demo_2"]
