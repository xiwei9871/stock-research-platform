from pathlib import Path

import pandas as pd


SECTOR_STRENGTH_COLUMNS = [
    "trade_date",
    "industry_system",
    "industry_code",
    "industry_name",
    "ret_5d",
    "ret_20d",
    "amount_ratio_5_20",
    "strength_score",
    "strength_rank",
]


def calc_sector_strength(
    bars: pd.DataFrame,
    trade_date: str,
    top_n: int = 20,
) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=SECTOR_STRENGTH_COLUMNS)

    frame = bars.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame = frame.sort_values(["industry_system", "industry_code", "trade_date"])

    grouped = frame.groupby(["industry_system", "industry_code"], group_keys=False)
    frame["ret_5d"] = grouped["close"].pct_change(5)
    frame["ret_20d"] = grouped["close"].pct_change(20)
    amount_5 = grouped["amount"].rolling(5).mean().reset_index(level=[0, 1], drop=True)
    amount_20 = grouped["amount"].rolling(20).mean().reset_index(level=[0, 1], drop=True)
    frame["amount_ratio_5_20"] = amount_5 / amount_20

    latest = frame[frame["trade_date"] == _iso_date(trade_date)].copy()
    if latest.empty:
        return pd.DataFrame(columns=SECTOR_STRENGTH_COLUMNS)

    latest["ret_5d_rank_score"] = _rank_score(latest["ret_5d"])
    latest["ret_20d_rank_score"] = _rank_score(latest["ret_20d"])
    latest["amount_rank_score"] = _rank_score(latest["amount_ratio_5_20"])
    latest["strength_score"] = (
        latest["ret_20d_rank_score"] * 0.5
        + latest["ret_5d_rank_score"] * 0.3
        + latest["amount_rank_score"] * 0.2
    )
    latest = latest.sort_values(
        ["strength_score", "ret_20d", "ret_5d", "industry_code"],
        ascending=[False, False, False, True],
    ).head(top_n)
    latest["strength_rank"] = range(1, len(latest) + 1)
    return latest[SECTOR_STRENGTH_COLUMNS].reset_index(drop=True)


def _rank_score(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True, ascending=True).fillna(0.0) * 100.0


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
