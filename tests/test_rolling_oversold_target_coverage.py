from datetime import date, timedelta

import pandas as pd

from stock_research.rolling_oversold.gap_backfill import audit_target_asset_coverage


def _complete_market_rows(asset_id: str) -> pd.DataFrame:
    dates = [date(2026, 7, 29) + timedelta(days=offset) for offset in range(3)]
    return pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "trade_date": trade_date,
                "adjust_type": "qfq",
                "close": 10.0 + offset,
                "amount": 100.0,
            }
            for offset, trade_date in enumerate(dates)
        ]
    )


def _complete_status_rows(asset_id: str) -> pd.DataFrame:
    dates = [date(2026, 7, 29) + timedelta(days=offset) for offset in range(3)]
    return pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "trade_date": trade_date,
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
            }
            for trade_date in dates
        ]
    )


def test_target_coverage_reports_only_confirmed_missing_rows():
    result = audit_target_asset_coverage(
        asset_ids={"CN:SZ:000001"},
        market_rows=_complete_market_rows("CN:SZ:000001"),
        status_rows=_complete_status_rows("CN:SZ:000001"),
        finance_rows=pd.DataFrame(),
        valuation_rows=pd.DataFrame(),
        start_date=date(2026, 7, 29),
        end_date=date(2026, 7, 31),
    )

    assert result["market_missing_assets"] == []
    assert result["status_missing_assets"] == []
    assert result["finance_missing_assets"] == ["CN:SZ:000001"]
    assert result["valuation_missing_assets"] == ["CN:SZ:000001"]


def test_target_coverage_excludes_bse_and_ineligible_status_from_market_gaps():
    asset_id = "CN:SZ:000001"
    result = audit_target_asset_coverage(
        asset_ids={asset_id, "CN:BJ:920001"},
        market_rows=pd.DataFrame(
            [
                {
                    "asset_id": asset_id,
                    "trade_date": date(2026, 7, 31),
                    "adjust_type": "qfq",
                    "close": 10.0,
                    "amount": 100.0,
                }
            ]
        ),
        status_rows=pd.DataFrame(
            [
                {
                    "asset_id": asset_id,
                    "trade_date": date(2026, 7, 31),
                    "is_trade": False,
                    "is_st": False,
                    "is_suspended": True,
                }
            ]
        ),
        finance_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "announcement_date": date(2026, 7, 31),
                "roe": 0.1,
                "total_share": 100.0,
            }]
        ),
        valuation_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "valuation_date": date(2026, 7, 31),
                "pe_ttm": None,
                "ps_ttm": 2.0,
            }]
        ),
        start_date=date(2026, 7, 31),
        end_date=date(2026, 7, 31),
    )

    assert result["eligible_asset_ids"] == [asset_id]
    assert result["excluded_bse_assets"] == ["CN:BJ:920001"]
    assert result["market_missing_assets"] == []
    assert result["status_missing_assets"] == []
    assert result["finance_missing_assets"] == []
    assert result["valuation_missing_assets"] == []


def test_target_coverage_reports_missing_active_market_and_status_dates():
    asset_id = "CN:SZ:000001"
    result = audit_target_asset_coverage(
        asset_ids={asset_id},
        market_rows=pd.DataFrame(
            [
                {
                    "asset_id": asset_id,
                    "trade_date": date(2026, 7, 29),
                    "adjust_type": "qfq",
                    "close": 10.0,
                    "amount": 100.0,
                },
                {
                    "asset_id": asset_id,
                    "trade_date": date(2026, 7, 31),
                    "adjust_type": "qfq",
                    "close": 11.0,
                    "amount": 100.0,
                },
            ]
        ),
        status_rows=pd.DataFrame(
            [
                {
                    "asset_id": asset_id,
                    "trade_date": date(2026, 7, 29),
                    "is_trade": True,
                    "is_st": False,
                    "is_suspended": False,
                },
                {
                    "asset_id": asset_id,
                    "trade_date": date(2026, 7, 30),
                    "is_trade": True,
                    "is_st": False,
                    "is_suspended": False,
                },
            ]
        ),
        finance_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "announcement_date": date(2026, 7, 31),
                "roe": 0.1,
                "total_share": 100.0,
            }]
        ),
        valuation_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "valuation_date": date(2026, 7, 31),
                "pe_ttm": 10.0,
                "ps_ttm": None,
            }]
        ),
        start_date=date(2026, 7, 29),
        end_date=date(2026, 7, 31),
    )

    assert result["market_missing_assets"] == [asset_id]
    assert result["status_missing_assets"] == [asset_id]
    assert result["finance_missing_assets"] == []
    assert result["valuation_missing_assets"] == []


def test_target_coverage_requires_expected_cutoff_status_and_market_date():
    asset_id = "CN:SZ:000001"
    result = audit_target_asset_coverage(
        asset_ids={asset_id},
        market_rows=_complete_market_rows(asset_id).iloc[[0]],
        status_rows=_complete_status_rows(asset_id).iloc[[0]],
        finance_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "announcement_date": date(2026, 7, 31),
                "roe": 0.1,
                "total_share": 100.0,
            }]
        ),
        valuation_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "valuation_date": date(2026, 7, 31),
                "pe_ttm": 10.0,
                "ps_ttm": None,
            }]
        ),
        start_date=date(2026, 7, 29),
        end_date=date(2026, 7, 31),
        expected_trade_dates=[date(2026, 7, 29), date(2026, 7, 31)],
    )

    assert result["market_missing_assets"] == []
    assert result["status_missing_assets"] == [asset_id]


def test_target_coverage_applies_pit_cutoff_to_finance_and_valuation():
    asset_id = "CN:SZ:000001"
    result = audit_target_asset_coverage(
        asset_ids={asset_id},
        market_rows=_complete_market_rows(asset_id).iloc[[-1]],
        status_rows=_complete_status_rows(asset_id).iloc[[-1]],
        finance_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "announcement_date": date(2026, 8, 1),
                "roe": 0.1,
                "total_share": 100.0,
            }]
        ),
        valuation_rows=pd.DataFrame(
            [{
                "asset_id": asset_id,
                "valuation_date": date(2026, 8, 1),
                "pe_ttm": 10.0,
                "ps_ttm": None,
            }]
        ),
        start_date=date(2026, 7, 31),
        end_date=date(2026, 7, 31),
        expected_trade_dates=[date(2026, 7, 31)],
    )

    assert result["finance_missing_assets"] == [asset_id]
    assert result["valuation_missing_assets"] == [asset_id]
