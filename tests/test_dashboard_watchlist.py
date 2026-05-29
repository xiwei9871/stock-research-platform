import pytest

from stock_research.dashboard import watchlist


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_watchlist_signals_maps_json_tags(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        return [
            {
                "watchlist_id": "default",
                "trade_date": "2026-05-29",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "平安银行",
                "priority": 10,
                "signal_score": 81.5,
                "primary_signal": "observe",
                "signal_tags": ["trend_ok"],
                "risk_tags": ["overheated"],
                "must_watch": True,
                "reason_json": {"score": 81.5},
            }
        ]

    monkeypatch.setattr(watchlist, "connect", fake_connect)
    monkeypatch.setattr(watchlist, "fetch_all", fake_fetch_all)

    result = watchlist.load_watchlist_signals_for_dashboard("default", "2026-05-29")

    assert result[0]["asset_id"] == "000001.SZ"
    assert result[0]["signal_tags"] == ["trend_ok"]
    assert result[0]["must_watch"] is True


def test_signal_row_defaults_nullable_json_fields():
    row = _signal_row_data(
        signal_score=None,
        signal_tags=None,
        risk_tags=None,
        reason_json=None,
    )

    result = watchlist._signal_row(row).to_dict()

    assert result["signal_score"] is None
    assert result["signal_tags"] == []
    assert result["risk_tags"] == []
    assert result["reason_json"] == {}


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("signal_tags", {"trend": "ok"}),
        ("signal_tags", "trend_ok"),
        ("risk_tags", {"risk": "high"}),
        ("risk_tags", "overheated"),
        ("reason_json", ["score", 81.5]),
        ("reason_json", "score"),
    ],
)
def test_signal_row_rejects_wrong_json_field_shapes(field_name, value):
    row = _signal_row_data(**{field_name: value})

    with pytest.raises(ValueError, match=field_name):
        watchlist._signal_row(row)


def _signal_row_data(**overrides):
    row = {
        "watchlist_id": "default",
        "trade_date": "2026-05-29",
        "asset_id": "000001.SZ",
        "stock_code": "000001",
        "stock_name": "平安银行",
        "priority": 10,
        "signal_score": 81.5,
        "primary_signal": "observe",
        "signal_tags": ["trend_ok"],
        "risk_tags": ["overheated"],
        "must_watch": True,
        "reason_json": {"score": 81.5},
    }
    row.update(overrides)
    return row
