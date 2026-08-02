from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from stock_research.rolling_oversold.gap_backfill import (
    build_gap_workplan,
    classify_asset_gap,
    load_preflight_gaps,
    write_gap_workplan,
)
from stock_research.strategy_data_policy import DataGap


def _gap(dataset: str, asset_id: str) -> DataGap:
    return DataGap(
        dataset,
        asset_id,
        "2026-07-21",
        "2026-07-21",
        1,
        0,
        f"missing_{dataset}",
    )


def test_build_gap_workplan_separates_invalid_memberships_from_real_backfills():
    result = build_gap_workplan(
        gaps=[
            DataGap(
                "market_daily_bar",
                "CN:BJ:900901",
                "2026-07-21",
                "2026-07-21",
                1,
                0,
                "missing_cutoff_bar",
            ),
            DataGap(
                "market_daily_bar",
                "CN:BJ:920001",
                "2026-07-21",
                "2026-07-21",
                1,
                0,
                "missing_cutoff_bar",
            ),
            DataGap(
                "market_daily_bar",
                "CN:SZ:000001",
                "2026-07-21",
                "2026-07-21",
                1,
                0,
                "missing_cutoff_bar",
            ),
            DataGap(
                "market.index_daily_bar",
                "BSE_50",
                None,
                "2026-07-21",
                252,
                21,
                "insufficient_252_session_history",
            ),
        ],
        asset_master={"CN:BJ:920001", "CN:SZ:000001"},
    )

    assert result["invalid_membership"] == ["CN:BJ:900901"]
    assert result["out_of_scope_bse"] == ["CN:BJ:920001"]
    assert result["market_bar_backfill"] == ["CN:SZ:000001"]
    assert result["out_of_scope_index"] == ["BSE_50"]


def test_classify_asset_gap_rejects_non_bj_asset_outside_cutoff_lifecycle():
    assert (
        classify_asset_gap(
            dataset="market_daily_bar",
            asset_id="CN:SZ:000001",
            asset_master_present=True,
            list_date=date(2026, 7, 22),
            delist_date=None,
            cutoff=date(2026, 7, 21),
        )
        == "invalid_membership"
    )
    assert (
        classify_asset_gap(
            dataset="core.asset_status_daily",
            asset_id="CN:SH:600001",
            asset_master_present=True,
            list_date=date(1990, 1, 1),
            delist_date=date(2026, 7, 21),
            cutoff=date(2026, 7, 21),
        )
        == "invalid_membership"
    )


def test_build_gap_workplan_classifies_all_dataset_families_and_keeps_derived_keys():
    derived_without_asset_id = SimpleNamespace(
        dataset="market.industry_daily_bar",
        asset_id=None,
        sector_system="csrc",
        sector_code="C36",
        start_date="2026-07-21",
        end_date="2026-07-21",
        expected_rows=1,
        actual_rows=0,
        reason="missing_cutoff_sector_bar",
    )
    result = build_gap_workplan(
        gaps=[
            _gap("core.asset_status_daily", "CN:SZ:000001"),
            _gap("finance_history", "CN:SZ:000001"),
            _gap("valuation_history", "CN:SZ:000001"),
            DataGap(
                "market.index_daily_bar",
                "STAR_50",
                None,
                "2026-07-21",
                252,
                21,
                "insufficient_252_session_history",
            ),
            _gap("market.concept_daily_bar", "em:BK0425"),
            derived_without_asset_id,
        ],
        asset_master={"CN:SZ:000001"},
    )

    assert result["market_bar_backfill"] == ["CN:SZ:000001"]
    assert result["finance_backfill"] == ["CN:SZ:000001"]
    assert result["valuation_backfill"] == ["CN:SZ:000001"]
    assert result["index_backfill"] == ["STAR_50"]
    assert result["derived_backfill"] == ["csrc:C36", "em:BK0425"]


def test_load_preflight_gaps_accepts_committed_json_shape(tmp_path: Path):
    expected = DataGap(
        "market_daily_bar",
        "CN:SZ:000001",
        "2026-07-21",
        "2026-07-21",
        1,
        0,
        "missing_cutoff_bar",
    )
    path = tmp_path / "preflight.json"
    path.write_text(
        json.dumps(
            {
                "anchor_date": "2026-07-21",
                "blocked": True,
                "gaps": [asdict(expected)],
            }
        ),
        encoding="utf-8",
    )

    assert load_preflight_gaps(path) == (expected,)


def test_write_gap_workplan_persists_auditable_json_and_csv(tmp_path: Path):
    gap = DataGap(
        "market_daily_bar",
        "CN:SZ:000001",
        "2026-07-21",
        "2026-07-21",
        1,
        0,
        "missing_cutoff_bar",
    )
    workplan = build_gap_workplan(
        gaps=[gap],
        asset_master={"CN:SZ:000001"},
    )

    paths = write_gap_workplan(workplan, tmp_path)

    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["schema_version"] == "rolling_oversold_gap_workplan_v1"
    assert payload["buckets"]["market_bar_backfill"] == ["CN:SZ:000001"]
    assert payload["summary"]["total_gap_rows"] == 1
    assert payload["gap_rows"] == [
        {
            "actual_rows": 0,
            "asset_or_key": "CN:SZ:000001",
            "bucket": "market_bar_backfill",
            "dataset": "market_daily_bar",
            "end_date": "2026-07-21",
            "expected_rows": 1,
            "proposed_next_task": "backfill_market_daily_bar",
            "reason": "missing_cutoff_bar",
            "start_date": "2026-07-21",
        }
    ]

    with Path(paths["csv"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "bucket": "market_bar_backfill",
            "dataset": "market_daily_bar",
            "asset_or_key": "CN:SZ:000001",
            "start_date": "2026-07-21",
            "end_date": "2026-07-21",
            "expected_rows": "1",
            "actual_rows": "0",
            "reason": "missing_cutoff_bar",
            "proposed_next_task": "backfill_market_daily_bar",
        }
    ]
