from __future__ import annotations

import pandas as pd

from stock_research.rolling_oversold.gap_backfill import audit_sector_target_gaps


def test_target_sector_gap_audit_separates_membership_from_non_target_history():
    result = audit_sector_target_gaps(
        target_codes={"300238", "309268"},
        sector_rows=pd.DataFrame(
            [
                {
                    "sector_system": "ths",
                    "sector_code": "300238",
                    "membership_count": 0,
                    "history_observations": 280,
                    "sector_feature_data_status": "ok",
                },
                {
                    "sector_system": "ths",
                    "sector_code": "309268",
                    "membership_count": 49,
                    "history_observations": 22,
                    "sector_feature_data_status": "ok",
                },
                {
                    "sector_system": "em",
                    "sector_code": "BK0425",
                    "membership_count": 66,
                    "history_observations": 17,
                    "sector_feature_data_status": "insufficient_history",
                },
            ]
        ),
    )

    assert result["target_membership_gap_codes"] == ["300238"]
    assert result["target_history_gap_codes"] == []
    assert result["target_volume_gap_codes"] == []
    assert result["deferred_non_target_gap_rows"] == 1
    assert result["deferred_non_target_history_gap_rows"] == 1
    assert result["deferred_non_target_volume_gap_rows"] == 0
    assert result["deferred_non_target_membership_gap_rows"] == 0


def test_target_audit_does_not_invent_long_history_or_drop_volume_bucket():
    result = audit_sector_target_gaps(
        target_codes={"309268", "309269"},
        sector_rows=pd.DataFrame(
            [
                {
                    "sector_system": "ths",
                    "sector_code": "309268",
                    "membership_count": 4,
                    "history_observations": 6,
                    "sector_feature_data_status": "ok",
                },
                {
                    "sector_system": "ths",
                    "sector_code": "309269",
                    "membership_count": 4,
                    "history_observations": 22,
                    "sector_feature_data_status": "missing_volume",
                },
            ]
        ),
    )

    assert result["target_membership_gap_codes"] == []
    assert result["target_history_gap_codes"] == []
    assert result["target_volume_gap_codes"] == ["309269"]
