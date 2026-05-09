import pytest

from stock_research.market_data import latest_source_trade_date, normalize_source_row


def test_normalize_source_row_maps_real_source_fields():
    row = {
        "trade_date": "2026-05-06",
        "stock_code": "sh600000",
        "open_price": "10.10",
        "high_price": "10.50",
        "low_price": "10.00",
        "close_price": "10.30",
        "preclose_price": "10.00",
        "volume": "1000",
        "amount": "10300",
        "adjustflag": "1",
        "turnover": "0.5",
        "tradestatus": "1",
        "pctChg": "3.0",
        "isST": "0",
    }

    normalized = normalize_source_row(row, adjust_type="hfq")

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["trade_date"] == "2026-05-06"
    assert normalized["close"] == 10.30
    assert normalized["turnover_rate"] == 0.5
    assert normalized["is_st"] is False
    assert normalized["adjust_type"] == "hfq"


def test_latest_source_trade_date_rejects_invalid_table_name():
    with pytest.raises(ValueError, match="Invalid stock table name"):
        latest_source_trade_date("stock_hfq", table_name="stock_hfq.sh600000")
