import stock_research.strategy_eod_publish as strategy_eod_publish
from stock_research.strategy_eod_publish import _review_rows_from_result


def test_mid_trend_review_uses_latest_signal_score_for_continued_holdings():
    result = {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "positions": [
            {"rebalance_date": "2026-06-22", "asset_id": "CN:SH:603733", "weight": 0.2},
        ],
        "trades": [
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SH:603733",
                "target_weight": 0.2,
            }
        ],
        "signals": [
            {
                "trade_date": "2026-06-15",
                "asset_id": "CN:SH:603733",
                "mid_trend_funnel_score": 81.639212,
            }
        ],
    }

    review = _review_rows_from_result(result, trade_date="2026-06-29")

    assert review.loc[0, "asset_id"] == "CN:SH:603733"
    assert review.loc[0, "score_total"] == 81.639212
    assert review.loc[0, "score_source"] == "mid_trend_funnel_score"


def test_mid_trend_review_uses_current_daily_score_for_holding_missing_signal(monkeypatch):
    class DummyConnection:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_connect(service):
        return DummyConnection()

    def fake_fetch_all(conn, sql, params):
        assert params == ["manual_v1", "2026-06-30", ["CN:SH:603690"]]
        return [{"asset_id": "CN:SH:603690", "score_total": 75.4086865826214}]

    monkeypatch.setattr(strategy_eod_publish, "connect", fake_connect)
    monkeypatch.setattr(strategy_eod_publish, "fetch_all", fake_fetch_all)
    result = {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "positions": [
            {"rebalance_date": "2026-06-29", "asset_id": "CN:SH:603690", "weight": 0.2},
        ],
        "trades": [
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SH:603690",
                "target_weight": 0.2,
            }
        ],
        "signals": [],
    }

    review = _review_rows_from_result(result, trade_date="2026-06-30")

    assert review.loc[0, "asset_id"] == "CN:SH:603690"
    assert review.loc[0, "score_total"] == 75.4086865826214
    assert review.loc[0, "score_source"] == "mid_trend_funnel_score"
