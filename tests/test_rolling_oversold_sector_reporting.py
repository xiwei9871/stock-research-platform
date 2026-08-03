from __future__ import annotations

import pandas as pd

from stock_research.rolling_oversold.reporting import write_sector_repair_summary


def test_sector_repair_summary_contains_nuclear_and_repair_labels_and_is_sorted(tmp_path):
    sectors = pd.DataFrame(
        [
            {
                "sector_system": "ths",
                "sector_code": "300239",
                "sector_name": "半导体",
                "sector_recovery_state": "expected_repair",
                "sector_oversold_score": 94.0,
                "sector_repairability_score": 79.0,
                "sector_direction_score": 73.0,
                "sector_drawdown_60d": -0.39,
                "sector_research_eligibility": "eligible",
            },
            {
                "sector_system": "ths",
                "sector_code": "300238",
                "sector_name": "核电",
                "sector_recovery_state": "confirmed_repair",
                "sector_oversold_score": 88.0,
                "sector_repairability_score": 91.0,
                "sector_direction_score": 83.0,
                "sector_drawdown_60d": -0.44,
                "sector_research_eligibility": "eligible",
            },
        ]
    )
    stocks = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "sector_system": "ths",
                "sector_code": "300238",
                "sector_name": "核电",
                "sector_stock_rank": 1,
                "stock_lifecycle": "confirmed_repair",
                "stock_score": 90.0,
            },
            {
                "asset_id": "B",
                "sector_system": "ths",
                "sector_code": "300239",
                "sector_name": "半导体",
                "sector_stock_rank": 1,
                "stock_lifecycle": "expected_repair",
                "stock_score": 82.0,
            },
        ]
    )

    report = write_sector_repair_summary(
        output_dir=tmp_path,
        sector_board=sectors,
        stock_candidates=stocks,
        backfill_requests=pd.DataFrame(
            [{"dataset": "sector_features", "asset_id": "ths:300240", "reason": "missing_volume"}]
        ),
        anchor_date="2026-07-31",
    )

    text = report.read_text(encoding="utf-8")
    assert report.name == "sector_repair_summary.md"
    assert "核电" in text
    assert "confirmed_repair" in text
    assert "expected_repair" in text
    assert "backfill" in text.lower()
    assert text.index("confirmed_repair") < text.index("expected_repair")
