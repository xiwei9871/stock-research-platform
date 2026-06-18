from __future__ import annotations

import pandas as pd
import pytest

from stock_research.tech_bottleneck_candidates import (
    TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
    build_point_in_time_candidate_snapshots,
    read_candidate_snapshots,
    validate_base_candidate_source_freshness,
    validate_candidate_snapshot_frame,
    write_candidate_snapshots,
)


def test_snapshot_excludes_future_first_hit_and_future_as_of_dates() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {
                    "asset_id": "A",
                    "stock_name": "Alpha",
                    "first_hit_date": "2025-01-02",
                    "hit_count": 5,
                    "primary_chain_id": "chain-a",
                    "primary_chain_name": "算力",
                    "financial_as_of_date": "2025-01-02",
                    "technical_as_of_date": "2025-01-02",
                },
                {
                    "asset_id": "B",
                    "stock_name": "Beta",
                    "first_hit_date": "2025-01-04",
                    "hit_count": 9,
                    "primary_chain_id": "chain-b",
                    "primary_chain_name": "半导体",
                    "financial_as_of_date": "2025-01-04",
                    "technical_as_of_date": "2025-01-04",
                },
                {
                    "asset_id": "C",
                    "stock_name": "Gamma",
                    "first_hit_date": "2025-01-02",
                    "hit_count": 7,
                    "primary_chain_id": "chain-c",
                    "primary_chain_name": "PCB",
                    "financial_as_of_date": "2025-01-05",
                    "technical_as_of_date": "2025-01-02",
                },
            ]
        ),
        prices=_prices(["A", "B", "C"], "2025-01-02", 4),
        start_date="2025-01-02",
        end_date="2025-01-03",
        run_id="tech-bt-20250103-test",
    )

    assert set(snapshots["trade_date"]) == {"2025-01-02", "2025-01-03"}
    assert snapshots[snapshots["trade_date"] == "2025-01-02"]["asset_id"].tolist() == ["A"]
    assert set(snapshots["asset_id"]) == {"A"}
    assert snapshots["data_as_of_date"].max() <= "2025-01-03"
    assert snapshots["engine_version"].unique().tolist() == [TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION]
    assert snapshots["filter_decision"].unique().tolist() == ["pass"]


def test_snapshot_ranks_are_daily_and_top5_flag_is_per_trade_date() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {"asset_id": f"A{i}", "stock_name": f"Name{i}", "first_hit_date": "2025-01-01", "hit_count": 10 - i}
                for i in range(1, 8)
            ]
        ),
        prices=_prices([f"A{i}" for i in range(1, 8)], "2025-01-01", 3),
        start_date="2025-01-01",
        end_date="2025-01-03",
        run_id="tech-bt-20250103-test",
    )

    day = snapshots[snapshots["trade_date"] == "2025-01-03"].sort_values("bottleneck_rank")
    assert day["bottleneck_rank"].tolist() == [1, 2, 3, 4, 5, 6, 7]
    assert day["is_top5"].tolist() == [True, True, True, True, True, False, False]
    assert day.iloc[0]["hit_count_as_of_date"] >= day.iloc[-1]["hit_count_as_of_date"]


def test_validate_candidate_snapshot_frame_rejects_future_dates() -> None:
    frame = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-04",
                "hit_count_as_of_date": 1,
                "primary_chain_id": "",
                "primary_chain_name": "",
                "matched_bottleneck_dimensions": "",
                "financial_as_of_date": "2025-01-03",
                "technical_as_of_date": "2025-01-03",
                "data_as_of_date": "2025-01-03",
                "filter_decision": "pass",
                "filter_reason": "",
                "bottleneck_score": 0.5,
                "bottleneck_rank": 1,
                "is_top5": True,
                "engine_version": TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
                "run_id": "run-a",
            }
        ]
    )

    with pytest.raises(ValueError, match="first_hit_date must be <= trade_date"):
        validate_candidate_snapshot_frame(frame)


def test_write_and_read_candidate_snapshots_round_trip(tmp_path) -> None:
    frame = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01", "hit_count": 3}]
        ),
        prices=_prices(["A"], "2025-01-01", 2),
        start_date="2025-01-01",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-test",
    )
    path = tmp_path / "tech_bottleneck_daily_candidates.csv"

    write_candidate_snapshots(frame, path)
    loaded = read_candidate_snapshots(path, start_date="2025-01-02", end_date="2025-01-02")

    assert loaded["trade_date"].unique().tolist() == ["2025-01-02"]
    assert loaded["asset_id"].tolist() == ["A"]
    assert loaded["bottleneck_rank"].tolist() == [1]


def test_validate_base_candidate_source_requires_fresh_generation_date() -> None:
    stale = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                "hit_count": 3,
                "source_latest_trade_date": "2025-01-02",
            }
        ]
    )

    with pytest.raises(ValueError, match="base candidate source is stale"):
        validate_base_candidate_source_freshness(stale, end_date="2025-01-03")


def _prices(asset_ids: list[str], start_date: str, periods: int) -> pd.DataFrame:
    rows = []
    for offset, trade_date in enumerate(pd.date_range(start_date, periods=periods, freq="D")):
        for asset_index, asset_id in enumerate(asset_ids, start=1):
            close = 10.0 + asset_index + offset
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)
