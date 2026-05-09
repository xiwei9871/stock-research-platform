import pandas as pd
import pytest

from stock_research.factor_eval.period import summarize_ic_by_year, summarize_spread_by_year
from stock_research.factor_eval.segment import summarize_return_by_segment


def test_summarize_ic_by_year_groups_ic_values():
    ic_frame = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "ic": 0.1},
            {"trade_date": "2025-01-02", "ic": 0.3},
            {"trade_date": "2026-01-01", "ic": -0.2},
        ]
    )

    result = summarize_ic_by_year(ic_frame, ic_col="ic")

    assert result.to_dict("records") == [
        {"year": 2025, "mean_ic": 0.2, "ic_count": 2},
        {"year": 2026, "mean_ic": -0.2, "ic_count": 1},
    ]


def test_summarize_spread_by_year_groups_top_bottom_spread():
    spread = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "top_bottom_spread": 0.05},
            {"trade_date": "2025-01-02", "top_bottom_spread": 0.03},
            {"trade_date": "2026-01-01", "top_bottom_spread": -0.01},
        ]
    )

    result = summarize_spread_by_year(spread)

    assert result.set_index("year").loc[2025, "mean_top_bottom_spread"] == pytest.approx(0.04)
    assert result.set_index("year").loc[2026, "spread_count"] == 1


def test_summarize_return_by_segment_joins_segment_labels():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.03},
        ]
    )
    segments = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "market_state": "weak"},
            {"trade_date": "2026-01-01", "asset_id": "B", "market_state": "strong"},
        ]
    )

    result = summarize_return_by_segment(
        factors,
        returns,
        segments,
        segment_col="market_state",
        return_col="forward_return_5d",
    )

    assert result.set_index("market_state").loc["strong", "mean_return"] == pytest.approx(0.03)
    assert result.set_index("market_state").loc["weak", "count"] == 1
