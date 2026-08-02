from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import stock_research.rolling_oversold.gap_backfill as gap_backfill_module
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


def test_write_gap_workplan_supports_plain_dict_copy_with_explicit_gap_rows(
    tmp_path: Path,
):
    workplan = build_gap_workplan(
        gaps=[_gap("market_daily_bar", "CN:SZ:000001")],
        asset_master={"CN:SZ:000001"},
    )
    plain_copy = dict(workplan)

    paths = write_gap_workplan(plain_copy, tmp_path)

    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["buckets"]["market_bar_backfill"] == ["CN:SZ:000001"]
    assert payload["gap_rows"][0]["reason"] == "missing_market_daily_bar"


def test_write_gap_workplan_rejects_nonempty_plain_dict_without_gap_rows(
    tmp_path: Path,
):
    workplan = {
        "invalid_membership": [],
        "market_bar_backfill": ["CN:SZ:000001"],
        "finance_backfill": [],
        "valuation_backfill": [],
        "index_backfill": [],
        "derived_backfill": [],
        "out_of_scope_bse": [],
        "out_of_scope_index": [],
    }

    with pytest.raises(ValueError, match="gap_rows"):
        write_gap_workplan(workplan, tmp_path)


def test_write_gap_workplan_serializes_empty_workplan(tmp_path: Path):
    empty = dict(build_gap_workplan(gaps=[], asset_master=set()))

    paths = write_gap_workplan(empty, tmp_path)

    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["summary"]["total_gap_rows"] == 0
    assert payload["gap_rows"] == []
    assert all(not values for values in payload["buckets"].values())
    with Path(paths["csv"]).open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == []


def test_build_gap_workplan_is_deterministic_with_shuffle_and_duplicates():
    first = _gap("market_daily_bar", "CN:SZ:000002")
    second = _gap("market_daily_bar", "CN:SZ:000001")

    forward = build_gap_workplan(
        gaps=[first, second, first],
        asset_master={"CN:SZ:000001", "CN:SZ:000002"},
    )
    reverse = build_gap_workplan(
        gaps=[first, second, first][::-1],
        asset_master={"CN:SZ:000001", "CN:SZ:000002"},
    )

    assert forward == reverse
    assert forward["market_bar_backfill"] == ["CN:SZ:000001", "CN:SZ:000002"]
    assert len(forward["gap_rows"]) == 3


@pytest.mark.parametrize(
    ("gap", "message"),
    [
        (
            {
                "asset_id": "CN:SZ:000001",
                "reason": "missing",
                "expected_rows": 1,
                "actual_rows": 0,
            },
            "dataset",
        ),
        (
            {
                "dataset": "market.concept_daily_bar",
                "asset_id": None,
                "reason": "missing",
                "expected_rows": 1,
                "actual_rows": 0,
            },
            "asset/sector key",
        ),
        (
            {
                "dataset": "market_daily_bar",
                "asset_id": "CN:SZ:000001",
                "reason": " ",
                "expected_rows": 1,
                "actual_rows": 0,
            },
            "reason",
        ),
        (
            {
                "dataset": "market_daily_bar",
                "asset_id": "CN:SZ:000001",
                "reason": "missing",
                "start_date": 20260721,
                "expected_rows": 1,
                "actual_rows": 0,
            },
            "start_date",
        ),
        (
            {
                "dataset": "market_daily_bar",
                "asset_id": "CN:SZ:000001",
                "reason": "missing",
                "end_date": "2026-02-30",
                "expected_rows": 1,
                "actual_rows": 0,
            },
            "end_date",
        ),
        (
            {
                "dataset": "market_daily_bar",
                "asset_id": "CN:SZ:000001",
                "reason": "missing",
                "expected_rows": True,
                "actual_rows": 0,
            },
            "expected_rows",
        ),
        (
            {
                "dataset": "market_daily_bar",
                "asset_id": "CN:SZ:000001",
                "reason": "missing",
                "expected_rows": 1,
                "actual_rows": -1,
            },
            "actual_rows",
        ),
    ],
)
def test_build_gap_workplan_rejects_malformed_gap_like_rows(gap, message):
    with pytest.raises(ValueError, match=message):
        build_gap_workplan(gaps=[gap], asset_master={"CN:SZ:000001"})


def test_write_gap_workplan_leaves_no_temporary_files(tmp_path: Path):
    workplan = build_gap_workplan(
        gaps=[_gap("market_daily_bar", "CN:SZ:000001")],
        asset_master={"CN:SZ:000001"},
    )

    write_gap_workplan(workplan, tmp_path)

    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "gap_workplan.csv",
        "gap_workplan.json",
    ]


def test_write_gap_workplan_rejects_malformed_explicit_gap_rows(tmp_path: Path):
    workplan = dict(
        build_gap_workplan(
            gaps=[_gap("market_daily_bar", "CN:SZ:000001")],
            asset_master={"CN:SZ:000001"},
        )
    )
    workplan["gap_rows"][0]["reason"] = ""

    with pytest.raises(ValueError, match="reason"):
        write_gap_workplan(workplan, tmp_path)


def test_write_gap_workplan_publishes_both_files_with_os_replace(
    tmp_path: Path, monkeypatch
):
    workplan = build_gap_workplan(
        gaps=[_gap("market_daily_bar", "CN:SZ:000001")],
        asset_master={"CN:SZ:000001"},
    )
    replacements: list[tuple[str, str]] = []
    real_replace = gap_backfill_module.os.replace

    def recording_replace(source, destination):
        replacements.append((Path(source).name, Path(destination).name))
        real_replace(source, destination)

    monkeypatch.setattr(gap_backfill_module.os, "replace", recording_replace)

    write_gap_workplan(workplan, tmp_path)

    assert [destination for _, destination in replacements] == [
        "gap_workplan.json",
        "gap_workplan.csv",
    ]
    assert all(source.startswith(".gap_workplan.") for source, _ in replacements)
