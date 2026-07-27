import pytest

from stock_research.asset_identity import normalize_cn_equity_asset_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CN:SH:600000", "CN:SH:600000"),
        ("000001.SZ", "CN:SZ:000001"),
        ("600000.SSE", "CN:SH:600000"),
        ("600000.SHH", "CN:SH:600000"),
        ("000001.SZSE", "CN:SZ:000001"),
        ("000001.SHE", "CN:SZ:000001"),
        ("430001.BSE", "CN:BJ:430001"),
        ("830001.BJ", "CN:BJ:830001"),
        ("688001", "CN:SH:688001"),
        ("300001", "CN:SZ:300001"),
        ("430001", "CN:BJ:430001"),
    ],
)
def test_normalize_cn_equity_asset_id_supported_formats(value, expected):
    assert normalize_cn_equity_asset_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "CN:SH:",
        "CN:XX:000001",
        "ABC.SH",
        "12345.SH",
        "1234567.SH",
        "100001",
        "nan",
        "none",
        None,
        True,
    ],
)
def test_normalize_cn_equity_asset_id_rejects_invalid_values(value):
    assert normalize_cn_equity_asset_id(value) == ""
