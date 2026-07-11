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
    monkeypatch.setattr(
        watchlist,
        "enrich_watchlist_rows",
        lambda rows: [
            {
                **row,
                "theme_research_context": {
                    "status": "not_mapped",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                },
            }
            for row in rows
        ],
    )

    result = watchlist.load_watchlist_signals_for_dashboard("default", "2026-05-29")

    assert result[0]["asset_id"] == "000001.SZ"
    assert result[0]["signal_tags"] == ["trend_ok"]
    assert result[0]["must_watch"] is True
    assert result[0]["theme_research_context"]["status"] == "not_mapped"


def test_watchlist_theme_context_does_not_change_signal_fields(monkeypatch):
    original = _signal_row_data(
        asset_id="CN:SZ:002837",
        stock_code="002837",
        stock_name="英维克",
    )
    signal_fields = {
        key: original[key]
        for key in (
            "priority",
            "signal_score",
            "primary_signal",
            "signal_tags",
            "risk_tags",
            "must_watch",
            "reason_json",
        )
    }

    monkeypatch.setattr(watchlist, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(watchlist, "fetch_all", lambda conn, sql, params: [original])
    monkeypatch.setattr(
        watchlist,
        "enrich_watchlist_rows",
        lambda rows: [
            {
                **rows[0],
                "theme_research_context": {
                    "status": "reviewed_context_available",
                    "theme_count": 1,
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                },
            }
        ],
    )

    result = watchlist.load_watchlist_signals_for_dashboard("default", "2026-05-29")

    assert [{key: row[key] for key in signal_fields} for row in result] == [signal_fields]
    assert result[0]["theme_research_context"]["theme_count"] == 1


def test_watchlist_loader_can_return_raw_signal_rows_for_invariance_checks(monkeypatch):
    original = _signal_row_data()
    monkeypatch.setattr(watchlist, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(watchlist, "fetch_all", lambda conn, sql, params: [original])
    monkeypatch.setattr(
        watchlist,
        "enrich_watchlist_rows",
        lambda rows: pytest.fail("raw mode must not enrich theme context"),
    )

    result = watchlist.load_watchlist_signals_for_dashboard(
        "default",
        "2026-05-29",
        include_theme_research=False,
    )

    assert result == [watchlist._signal_row(original).to_dict()]


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
