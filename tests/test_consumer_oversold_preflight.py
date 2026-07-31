from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.preflight import run_consumer_preflight


def _included(asset_id: str, *, list_date: str = "2020-01-01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": [asset_id],
            "list_date": [list_date],
        }
    )


def _bars(asset_id: str, rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": [asset_id] * rows,
            "trade_date": pd.bdate_range(end="2026-07-29", periods=rows),
            "close": np.linspace(10.0, 20.0, rows),
        }
    )


def _shares(asset_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"asset_id": [asset_id], "total_share": [100.0], "float_share": [80.0]}
    )


def _finance(asset_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": [asset_id],
            "report_period": ["2026-06-30"],
            "announcement_date": ["2026-07-20"],
        }
    )


def _valuation(asset_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"asset_id": [asset_id], "valuation_date": ["2026-07-29"]}
    )


def _complete_frames(asset_id: str) -> dict[str, pd.DataFrame]:
    return {
        "included": _included(asset_id),
        "bars": _bars(asset_id, 504),
        "share_capacity": _shares(asset_id),
        "finance": _finance(asset_id),
        "valuation_history": _valuation(asset_id),
    }


def test_complete_consumer_frames_pass_preflight():
    result = run_consumer_preflight(
        **_complete_frames("A"),
        trade_date="2026-07-29",
    )
    assert result.status == "passed"
    assert result.gaps == ()


@pytest.mark.parametrize(
    "frame_name", ["bars", "share_capacity", "finance", "valuation_history"]
)
def test_missing_required_frame_blocks_and_reports_asset(frame_name):
    frames = _complete_frames("A")
    frames[frame_name] = frames[frame_name].iloc[0:0]
    result = run_consumer_preflight(**frames, trade_date="2026-07-29")
    assert result.status == "blocked_missing_data"
    assert result.gaps[0].asset_id == "A"
    assert result.gaps[0].dataset


def test_new_listing_short_history_is_not_reported_as_backfill_gap():
    frames = _complete_frames("NEW")
    frames["included"] = _included("NEW", list_date="2026-07-10")
    frames["bars"] = _bars("NEW", 20)
    result = run_consumer_preflight(**frames, trade_date="2026-07-29")
    assert result.status == "passed"
