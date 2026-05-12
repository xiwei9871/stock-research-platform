from stock_research import research_windows


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_market_date_bounds_reads_hfq_bar_range(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [
            {
                "min_date": "1990-12-19",
                "max_date": "2026-05-08",
                "date_count": 8200,
            }
        ]

    monkeypatch.setattr(research_windows, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_windows, "fetch_all", fake_fetch_all)

    bounds = research_windows.load_market_date_bounds(adjust_type="hfq")

    assert bounds == {
        "start_date": "1990-12-19",
        "end_date": "2026-05-08",
        "date_count": 8200,
    }
    assert "FROM market_daily_bar" in calls[0][0]
    assert calls[0][1] == ["hfq"]


def test_load_trade_dates_returns_ordered_market_dates(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [{"trade_date": "2026-05-01"}, {"trade_date": "2026-05-04"}]

    monkeypatch.setattr(research_windows, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_windows, "fetch_all", fake_fetch_all)

    dates = research_windows.load_trade_dates("2026-05-01", "2026-05-04")

    assert dates == ["2026-05-01", "2026-05-04"]
    assert "ORDER BY trade_date" in calls[0][0]
    assert calls[0][1] == ["hfq", "2026-05-01", "2026-05-04"]


def test_derive_feature_window_uses_required_history_bars(monkeypatch):
    monkeypatch.setattr(
        research_windows,
        "load_trade_dates",
        lambda start_date, end_date, adjust_type="hfq", service=None: [
            "1990-12-19",
            "1990-12-20",
            "1990-12-21",
            "1990-12-24",
        ],
    )

    window = research_windows.derive_feature_window(
        start_date="1990-12-19",
        end_date="1990-12-24",
        lookback_bars=3,
    )

    assert window == {
        "start_date": "1990-12-21",
        "end_date": "1990-12-24",
        "date_count": 2,
    }


def test_derive_label_window_excludes_dates_without_future_horizon(monkeypatch):
    monkeypatch.setattr(
        research_windows,
        "load_trade_dates",
        lambda start_date, end_date, adjust_type="hfq", service=None: [
            "2026-05-01",
            "2026-05-04",
            "2026-05-05",
            "2026-05-06",
            "2026-05-07",
        ],
    )

    window = research_windows.derive_label_window(
        start_date="2026-05-01",
        end_date="2026-05-07",
        horizons=[1, 2],
    )

    assert window == {
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "date_count": 3,
    }


def test_derive_windows_return_empty_when_history_is_too_short(monkeypatch):
    monkeypatch.setattr(
        research_windows,
        "load_trade_dates",
        lambda start_date, end_date, adjust_type="hfq", service=None: ["2026-05-01"],
    )

    assert research_windows.derive_feature_window(
        start_date="2026-05-01",
        end_date="2026-05-01",
        lookback_bars=2,
    ) == {"start_date": None, "end_date": None, "date_count": 0}
    assert research_windows.derive_label_window(
        start_date="2026-05-01",
        end_date="2026-05-01",
        horizons=[1],
    ) == {"start_date": None, "end_date": None, "date_count": 0}
