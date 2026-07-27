from __future__ import annotations

import re
from typing import Any


_CANONICAL_ASSET_ID = re.compile(r"^CN:(SH|SZ|BJ):(\d{6})$")
_DOTTED_ASSET_ID = re.compile(
    r"^(\d{6})\.(SH|SZ|BJ|SSE|SZSE|BSE|SHH|SHE)$"
)
_BARE_SYMBOL = re.compile(r"^\d{6}$")
_EXCHANGE_ALIASES = {
    "SH": "SH",
    "SSE": "SH",
    "SHH": "SH",
    "SZ": "SZ",
    "SZSE": "SZ",
    "SHE": "SZ",
    "BJ": "BJ",
    "BSE": "BJ",
}


def normalize_cn_equity_asset_id(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip().upper()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return ""

    canonical = _CANONICAL_ASSET_ID.fullmatch(text)
    if canonical:
        exchange, symbol = canonical.groups()
        return f"CN:{exchange}:{symbol}"

    dotted = _DOTTED_ASSET_ID.fullmatch(text)
    if dotted:
        symbol, exchange = dotted.groups()
        return f"CN:{_EXCHANGE_ALIASES[exchange]}:{symbol}"

    if not _BARE_SYMBOL.fullmatch(text):
        return ""
    if text.startswith("92"):
        exchange = "BJ"
    elif text.startswith(("6", "90")):
        exchange = "SH"
    elif text.startswith(("0", "2", "3")):
        exchange = "SZ"
    elif text.startswith(("4", "8")):
        exchange = "BJ"
    else:
        return ""
    return f"CN:{exchange}:{text}"
