from stock_research.dashboard.schemas import BarPoint, ScoreRow, WatchlistSignalRow


def test_bar_point_to_dict_uses_chart_time_key():
    point = BarPoint(
        time="2026-05-29",
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=123000.0,
        amount=456000.0,
    )

    assert point.to_dict() == {
        "time": "2026-05-29",
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": 10.5,
        "volume": 123000.0,
        "amount": 456000.0,
    }


def test_score_row_preserves_components():
    row = ScoreRow(
        trade_date="2026-05-29",
        asset_id="000001.SZ",
        rank=3,
        score_total=88.5,
        score_version="manual_v1",
        score_components={"momentum": 90},
    )

    assert row.to_dict()["score_components"] == {"momentum": 90}


def test_watchlist_signal_row_preserves_tags():
    row = WatchlistSignalRow(
        watchlist_id="default",
        trade_date="2026-05-29",
        asset_id="000001.SZ",
        stock_code="000001",
        stock_name="平安银行",
        priority=10,
        signal_score=75.0,
        primary_signal="observe",
        signal_tags=["trend_ok"],
        risk_tags=["high_volatility"],
        must_watch=True,
        reason_json={"reason": "score"},
    )

    assert row.to_dict()["must_watch"] is True
    assert row.to_dict()["risk_tags"] == ["high_volatility"]
