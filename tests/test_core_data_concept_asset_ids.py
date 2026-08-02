from __future__ import annotations

import pytest

from stock_research.core_data import _asset_id_from_cn_stock_code


@pytest.mark.parametrize(
    ("raw_code", "expected"),
    [
        ("900001", None),
        ("SH.900001", None),
        ("900001.SH", None),
        ("920001", "CN:BJ:920001"),
        ("BJ.920001", "CN:BJ:920001"),
        ("920001.BJ", "CN:BJ:920001"),
    ],
)
def test_asset_id_from_cn_stock_code_handles_900_and_920_codes(raw_code, expected):
    assert _asset_id_from_cn_stock_code(raw_code) == expected
