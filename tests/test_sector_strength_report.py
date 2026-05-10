import pandas as pd
import pytest

from stock_research.reports.sector_strength_report import calc_sector_strength


def _sector_bars() -> pd.DataFrame:
    rows = []
    for index in range(21):
        trade_date = f"2026-01-{index + 1:02d}"
        rows.extend(
            [
                {
                    "trade_date": trade_date,
                    "industry_system": "csrc",
                    "industry_code": "T",
                    "industry_name": "Tech",
                    "close": 100.0 + index * 2.0,
                    "amount": 1000.0 + index * 20.0,
                },
                {
                    "trade_date": trade_date,
                    "industry_system": "csrc",
                    "industry_code": "B",
                    "industry_name": "Bank",
                    "close": 100.0 + index * 0.5,
                    "amount": 1000.0,
                },
            ]
        )
    return pd.DataFrame(rows)


def test_calc_sector_strength_ranks_latest_industries():
    result = calc_sector_strength(_sector_bars(), trade_date="2026-01-21", top_n=2)

    assert list(result["industry_code"]) == ["T", "B"]
    tech = result.iloc[0]
    assert tech["trade_date"] == "2026-01-21"
    assert tech["industry_name"] == "Tech"
    assert tech["ret_5d"] == pytest.approx(140.0 / 130.0 - 1.0)
    assert tech["ret_20d"] == pytest.approx(140.0 / 100.0 - 1.0)
    assert tech["amount_ratio_5_20"] > 1.0
    assert tech["strength_rank"] == 1
    assert tech["strength_score"] > result.iloc[1]["strength_score"]
