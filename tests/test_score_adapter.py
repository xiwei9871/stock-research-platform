import pandas as pd

from stock_research.score_adapter import stock_scores_to_retention_candidates


def test_stock_scores_to_retention_candidates_shapes_cache_like_frame():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-08", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-08", "asset_id": "B", "rank": 2, "score_total": 80.0},
        ]
    )

    result = stock_scores_to_retention_candidates(scores)

    assert list(result.columns) == [
        "trade_date",
        "asset_id",
        "rank",
        "score",
        "hard_filter_pass",
        "board_filter_pass",
        "market_filter_pass",
    ]
    assert result.iloc[0]["score"] == 90.0
