import pytest

from stock_research.assets import (
    asset_id_from_baostock_code,
    baostock_code_from_table,
    is_stock_table,
    table_from_baostock_code,
)


def test_asset_id_from_baostock_code():
    assert asset_id_from_baostock_code("sh.600000") == "CN:SH:600000"
    assert asset_id_from_baostock_code("sh.689009") == "CN:SH:689009"
    assert asset_id_from_baostock_code("sz.000001") == "CN:SZ:000001"
    assert asset_id_from_baostock_code("bj.430047") == "CN:BJ:430047"


def test_table_from_baostock_code():
    assert table_from_baostock_code("sh.600000") == "sh600000"
    assert table_from_baostock_code("sh.689009") == "sh689009"
    assert table_from_baostock_code("sz.000001") == "sz000001"
    assert table_from_baostock_code("bj.430047") == "bj430047"


def test_baostock_code_from_table():
    assert baostock_code_from_table("sh600000") == "sh.600000"
    assert baostock_code_from_table("sz000001") == "sz.000001"
    assert baostock_code_from_table("bj430047") == "bj.430047"


def test_is_stock_table_rejects_non_stock_tables():
    assert is_stock_table("sh_meta") is False
    assert is_stock_table("sz_index") is False
    assert is_stock_table("bjABCDEF") is False


def test_table_from_baostock_code_rejects_invalid_exchange():
    with pytest.raises(ValueError):
        table_from_baostock_code("xx.123456")
