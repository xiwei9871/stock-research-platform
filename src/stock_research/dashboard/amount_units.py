from __future__ import annotations

from decimal import Decimal
from typing import Any


TUSHARE_AMOUNT_TO_YUAN = Decimal("1000")


def storage_amount_to_yuan(value: Any) -> Any:
    """Convert stored daily amount values from Tushare's thousand-yuan unit."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value * TUSHARE_AMOUNT_TO_YUAN
    return value * float(TUSHARE_AMOUNT_TO_YUAN)
