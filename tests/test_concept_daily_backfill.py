from datetime import date

import pandas as pd
import pytest

from stock_research.concept_daily_backfill import (
    backfill_concept_daily_bars,
    build_upsert_rows,
    normalize_concept_history,
)


def test_normalize_concept_history_maps_vendor_columns_and_derives_preclose():
    frame = pd.DataFrame(
        {
            "日期": ["2024-01-04", "2024-01-02", "2024-01-03"],
            "开盘价": [12.0, 10.0, 11.0],
            "最高价": [13.0, 11.0, 12.0],
            "最低价": [11.5, 9.5, 10.5],
            "收盘价": [12.5, 10.0, 11.0],
            "成交量": [300.0, 100.0, 200.0],
            "成交额": [3000.0, 1000.0, 2000.0],
        }
    )

    rows = normalize_concept_history(
        frame,
        concept_system="ths",
        concept_code="300816",
        concept_name="机器人概念",
        source="akshare:stock_board_concept_index_ths",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 4),
    )

    assert [row["trade_date"] for row in rows] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    ]
    assert [row["preclose"] for row in rows] == [None, 10.0, 11.0]
    assert rows[-1]["close"] == 12.5
    assert rows[-1]["concept_code"] == "300816"
    assert rows[-1]["concept_name"] == "机器人概念"


def test_normalize_concept_history_drops_invalid_rows_and_leaves_breadth_null():
    frame = pd.DataFrame(
        {
            "日期": ["2024-01-02", "not-a-date", "2024-01-04"],
            "开盘价": [10.0, 20.0, 12.0],
            "最高价": [11.0, 21.0, 13.0],
            "最低价": [9.0, 19.0, 11.0],
            "收盘价": [10.0, 20.0, None],
            "成交量": [100.0, 200.0, 300.0],
            "成交额": [1000.0, 2000.0, 3000.0],
        }
    )

    rows = normalize_concept_history(
        frame,
        concept_system="ths",
        concept_code="300816",
        concept_name="机器人概念",
        source="akshare:stock_board_concept_index_ths",
    )

    assert len(rows) == 1
    assert rows[0]["trade_date"] == date(2024, 1, 2)
    assert rows[0]["stock_count"] is None
    assert rows[0]["up_count"] is None
    assert rows[0]["down_count"] is None


def test_build_upsert_rows_returns_database_ordered_values():
    rows = [
        {
            "concept_system": "ths",
            "concept_code": "300816",
            "concept_name": "机器人概念",
            "trade_date": date(2024, 1, 2),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "preclose": None,
            "volume": 100.0,
            "amount": 1000.0,
            "stock_count": None,
            "up_count": None,
            "down_count": None,
            "source": "akshare:stock_board_concept_index_ths",
        }
    ]

    payload = build_upsert_rows(rows)

    assert payload == [
        (
            "ths",
            "300816",
            "机器人概念",
            date(2024, 1, 2),
            10.0,
            11.0,
            9.0,
            10.0,
            None,
            100.0,
            1000.0,
            None,
            None,
            None,
            "akshare:stock_board_concept_index_ths",
        )
    ]


def test_backfill_rejects_thread_workers_for_mini_racer_safety():
    with pytest.raises(ValueError, match="workers=1"):
        backfill_concept_daily_bars(
            start_date=date(2024, 1, 1),
            workers=2,
        )
