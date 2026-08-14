import json
import re
from pathlib import Path

import pytest

from stock_research import kronos_experiment_universe as universe


def _bar(asset_id, trade_date, *, is_st=False, trade_status="1", close=10.0):
    return {
        "asset_id": asset_id,
        "trade_date": trade_date,
        "adjust_type": "qfq",
        "is_st": is_st,
        "trade_status": trade_status,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
    }


class FakeDB:
    def __init__(self):
        self.calls = []
        self.rows = {
            "latest": [{"trade_date": "2025-01-06"}, {"trade_date": "2025-01-08"}],
            "candidates": [
                {"asset_id": "b", "market": "CN_A", "status": "listed", "name": "Beta"},
                {"asset_id": "a", "market": "CN_A", "status": "listed", "name": "Alpha"},
            ],
            "bars": [
                _bar("a", "2025-01-02"),
                _bar("a", "2025-01-03"),
                _bar("b", "2025-01-02"),
                _bar("b", "2025-01-03"),
            ],
            "calendar": [{"trade_date": "2025-01-02", "exchange": "SH", "is_open": True}],
            "fallback": [{"trade_date": "2025-01-03"}, {"trade_date": "2025-01-02"}],
        }

    def fetch_all(self, _conn, sql, params=None):
        self.calls.append((sql, params))
        if "MAX(trade_date)" in sql:
            return self.rows["latest"]
        if "asset_master" in sql:
            return self.rows["candidates"]
        if "FROM market.trading_calendar" in sql:
            return self.rows["calendar"]
        if "FROM market_daily_bar" in sql and "trade_date >=" in sql:
            return self.rows["fallback"]
        if "FROM market_daily_bar" in sql:
            return self.rows["bars"]
        raise AssertionError(sql)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(universe, "connect", lambda service: _connection())
    monkeypatch.setattr(universe, "fetch_all", db.fetch_all)
    return db


class _connection:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return False


def test_random_selection_is_deterministic_and_uses_sorted_sampling(fake_db):
    first = universe.select_universe(
        mode="random", count=1, seed=7, market="CN_A", asset_ids=None,
        adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
    )
    second = universe.select_universe(
        mode="random", count=1, seed=7, market="CN_A", asset_ids=None,
        adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
    )
    assert first.asset_ids == second.asset_ids
    assert first.candidate_count == 2
    candidate_sql = next(sql for sql, _ in fake_db.calls if "asset_master" in sql)
    assert "ORDER BY random" not in candidate_sql.upper()
    assert "ORDER BY asset_id" in candidate_sql
    assert any(params.get("market") == "CN_A" for _, params in fake_db.calls if isinstance(params, dict))


def test_explicit_mode_normalizes_ids_preserves_order_and_requires_matching_count(fake_db):
    selected = universe.select_universe(
        mode="explicit", count=2, seed=None, market="CN_A", asset_ids=[" b ", "A"],
        adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
    )
    assert selected.asset_ids == ("b", "a")
    with pytest.raises(ValueError, match="count"):
        universe.select_universe(
            mode="explicit", count=1, seed=None, market="CN_A", asset_ids=["a", "b"],
            adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
        )


def test_explicit_mode_rejects_duplicate_normalized_ids(fake_db):
    with pytest.raises(ValueError, match="duplicate"):
        universe.select_universe(
            mode="explicit", count=2, seed=None, market="CN_A", asset_ids=[" A ", "a"],
            adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
        )


def test_latest_market_date_is_maximum(fake_db):
    assert universe.resolve_latest_market_date(adjust_type="qfq", service="test") == "2025-01-08"


def test_calendar_uses_exchange_rows_then_daily_bar_fallback(fake_db):
    assert universe.load_trade_calendar_dates("qfq", "2025-01-01", "2025-01-05", "test") == ["2025-01-02"]
    fake_db.rows["calendar"] = []
    assert universe.load_trade_calendar_dates("hfq", "2025-01-01", "2025-01-05", "test") == ["2025-01-02", "2025-01-03"]
    fallback_call = next((params for sql, params in fake_db.calls if "SELECT DISTINCT trade_date" in sql), None)
    assert fallback_call["adjust_type"] == "qfq"


def test_candidates_exclude_nonlisted_delisted_and_other_markets(fake_db):
    fake_db.rows["candidates"] = [
        {"asset_id": "listed", "market": "CN_A", "status": "listed", "delist_date": None, "name": "Listed"},
        {"asset_id": "unlisted", "market": "CN_A", "status": "pending", "delist_date": None, "name": "Pending"},
        {"asset_id": "delisted", "market": "CN_A", "status": "listed", "delist_date": "2024-01-01", "name": "Gone"},
        {"asset_id": "other-market", "market": "US", "status": "listed", "delist_date": None, "name": "Other"},
    ]
    fake_db.rows["bars"] = [
        _bar("listed", "2025-01-02"), _bar("listed", "2025-01-03"),
        _bar("unlisted", "2025-01-02"), _bar("unlisted", "2025-01-03"),
        _bar("delisted", "2025-01-02"), _bar("delisted", "2025-01-03"),
        _bar("other-market", "2025-01-02"), _bar("other-market", "2025-01-03"),
    ]
    selection = universe.select_universe(
        mode="random", count=1, seed=1, market="CN_A", asset_ids=None,
        adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
    )
    assert selection.asset_ids == ("listed",)


def test_filters_st_and_bad_or_insufficient_bars(fake_db):
    fake_db.rows["candidates"] = [
        {"asset_id": "st", "market": "CN_A", "status": "listed", "name": "*ST Risk"},
        {"asset_id": "bad", "market": "CN_A", "status": "listed", "name": "Bad"},
        {"asset_id": "ok", "market": "CN_A", "status": "listed", "name": "Okay"},
    ]
    fake_db.rows["bars"] = [
        _bar("st", "2025-01-02"), _bar("st", "2025-01-03"),
        _bar("bad", "2025-01-02"),
        _bar("ok", "2025-01-02"), _bar("ok", "2025-01-03"), _bar("ok", "2025-01-04"),
    ]
    fake_db.rows["bars"][2]["high"] = float("nan")
    selected = universe.select_universe(
        mode="random", count=1, seed=1, market="CN_A", asset_ids=None,
        adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
    )
    assert selected.asset_ids == ("ok",)
    assert any("is_st" in sql and "trade_status" in sql for sql, _ in fake_db.calls)


def test_any_pre_cutoff_st_bar_excludes_candidate(fake_db):
    fake_db.rows["candidates"] = [
        {"asset_id": "ok", "market": "CN_A", "status": "listed", "name": "Okay"},
        {"asset_id": "historical-st", "market": "CN_A", "status": "listed", "name": "Former Risk"},
    ]
    fake_db.rows["bars"] = [
        _bar("ok", "2025-01-02"), _bar("ok", "2025-01-03"),
        _bar("historical-st", "2025-01-02", is_st=True),
        _bar("historical-st", "2025-01-03"), _bar("historical-st", "2025-01-04"),
    ]
    selected = universe.select_universe(
        mode="random", count=1, seed=1, market="CN_A", asset_ids=None,
        adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
    )
    assert selected.asset_ids == ("ok",)


def test_fingerprints_and_json_are_stable(fake_db, tmp_path: Path):
    selection = universe.select_universe(
        mode="random", count=1, seed=7, market="CN_A", asset_ids=None,
        adjust_type="qfq", input_window=2, cutoff_date="2025-01-04", service="test",
    )
    path = tmp_path / "universe.json"
    universe.write_universe_selection(path, selection)
    payload = json.loads(path.read_text())
    assert payload["candidate_fingerprint"] == selection.candidate_fingerprint
    assert payload["selection_fingerprint"] == selection.selection_fingerprint
    assert payload["candidates"] == list(selection.candidates)
    assert payload["selected_rows"] == list(selection.selected_rows)
    assert re.fullmatch(r"[0-9a-f]{64}", selection.candidate_fingerprint)
    assert re.fullmatch(r"[0-9a-f]{64}", selection.selection_fingerprint)
    assert path.read_text().endswith("\n")
