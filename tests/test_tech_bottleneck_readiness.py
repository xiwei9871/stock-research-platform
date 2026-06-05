from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.tech_bottleneck_readiness import (
    READINESS_FLAGS,
    build_readiness_audit,
    normalize_readiness_candidates,
)


def test_normalize_readiness_candidates_requires_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        normalize_readiness_candidates(
            pd.DataFrame([{"stock_name": "缺少代码"}]),
            run_date="2026-06-06",
            as_of_date=None,
            lookback_days=365,
        )


def test_normalize_readiness_candidates_fills_optional_columns_and_dates() -> None:
    candidates = normalize_readiness_candidates(
        pd.DataFrame(
            [
                {"asset_id": "CN:SH:688001", "stock_name": "示例光电", "trade_date": "2026-06-05", "rank": 1},
                {"asset_id": "CN:SZ:300001"},
            ]
        ),
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
    )

    rows = candidates.set_index("asset_id")
    assert rows.loc["CN:SH:688001", "as_of_date"] == "2026-06-05"
    assert rows.loc["CN:SZ:300001", "as_of_date"] == "2026-06-06"
    assert rows.loc["CN:SZ:300001", "stock_name"] == ""
    assert rows.loc["CN:SZ:300001", "candidate_source"] == ""
    assert rows.loc["CN:SZ:300001", "lookback_days"] == 365
