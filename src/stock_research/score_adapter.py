import pandas as pd


def stock_scores_to_retention_candidates(scores: pd.DataFrame) -> pd.DataFrame:
    result = scores.copy().rename(columns={"score_total": "score"})
    result["hard_filter_pass"] = True
    result["board_filter_pass"] = True
    result["market_filter_pass"] = True
    return result[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score",
            "hard_filter_pass",
            "board_filter_pass",
            "market_filter_pass",
        ]
    ]
