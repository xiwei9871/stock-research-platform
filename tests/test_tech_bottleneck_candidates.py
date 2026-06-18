from __future__ import annotations

import inspect

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
                    "candidate_trade_date": "2025-01-02",
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
                    "candidate_trade_date": "2025-01-04",
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
                    "candidate_trade_date": "2025-01-02",
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
                {"asset_id": f"A{i}", "stock_name": f"Name{i}", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 10 - i}
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


def test_future_candidate_does_not_change_past_candidate_score() -> None:
    base_candidate = {
        "asset_id": "A",
        "stock_name": "Alpha",
        "first_hit_date": "2025-01-01",
        "candidate_trade_date": "2025-01-01",
        "hit_count": 2,
    }
    baseline = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame([base_candidate]),
        prices=_prices(["A", "B"], "2025-01-01", 4),
        start_date="2025-01-01",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-test",
    )
    with_future_candidate = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                base_candidate,
                {
                    "asset_id": "B",
                    "stock_name": "Beta",
                    "first_hit_date": "2025-01-03",
                    "candidate_trade_date": "2025-01-03",
                    "hit_count": 1000,
                },
            ]
        ),
        prices=_prices(["A", "B"], "2025-01-01", 4),
        start_date="2025-01-01",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-test",
    )

    baseline_score = baseline.loc[baseline["trade_date"].eq("2025-01-01"), "bottleneck_score"].iloc[0]
    with_future_score = with_future_candidate.loc[
        with_future_candidate["trade_date"].eq("2025-01-01"), "bottleneck_score"
    ].iloc[0]

    assert with_future_score == pytest.approx(baseline_score)
    assert with_future_candidate["asset_id"].unique().tolist() == ["A"]
    assert with_future_candidate["filter_reason"].unique().tolist() == ["static_source_hit_count_conservative_1"]


def test_static_hit_count_uses_conservative_one_without_changing_historical_score_or_rank() -> None:
    low_static = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 1}]
        ),
        prices=_prices(["A"], "2025-01-01", 2),
        start_date="2025-01-02",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-low",
    )
    high_static = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 1000}]
        ),
        prices=_prices(["A"], "2025-01-01", 2),
        start_date="2025-01-02",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-high",
    )

    assert high_static["hit_count_as_of_date"].tolist() == [1.0]
    assert high_static["filter_reason"].tolist() == ["static_source_hit_count_conservative_1"]
    assert high_static["bottleneck_score"].tolist() == pytest.approx(low_static["bottleneck_score"].tolist())
    assert high_static["bottleneck_rank"].tolist() == low_static["bottleneck_rank"].tolist()


def test_one_day_snapshot_score_matches_full_rebuild_with_same_price_history() -> None:
    candidates = pd.DataFrame(
        [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 3}]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "open": 100.0, "high": 100.0, "low": 99.0, "close": 100.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "open": 50.0, "high": 50.0, "low": 49.0, "close": 50.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "open": 20.0, "high": 20.0, "low": 19.0, "close": 20.0},
            {"trade_date": "2025-01-04", "asset_id": "A", "open": 10.0, "high": 10.0, "low": 9.0, "close": 10.0},
            {"trade_date": "2025-01-05", "asset_id": "A", "open": 10.0, "high": 10.0, "low": 9.0, "close": 10.0},
        ]
    )
    full_rebuild = build_point_in_time_candidate_snapshots(
        base_candidates=candidates,
        prices=prices,
        start_date="2025-01-01",
        end_date="2025-01-05",
        run_id="tech-bt-20250105-full",
    )
    one_day = build_point_in_time_candidate_snapshots(
        base_candidates=candidates,
        prices=prices,
        start_date="2025-01-05",
        end_date="2025-01-05",
        run_id="tech-bt-20250105-daily",
    )

    full_score = full_rebuild.loc[full_rebuild["trade_date"].eq("2025-01-05"), "bottleneck_score"].iloc[0]
    one_day_score = one_day.loc[one_day["trade_date"].eq("2025-01-05"), "bottleneck_score"].iloc[0]

    assert one_day_score == pytest.approx(full_score)


def test_explicit_hit_count_as_of_date_is_used_without_static_filter_reason() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {
                    "asset_id": "A",
                    "stock_name": "Alpha",
                    "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                    "trade_date": "2025-01-01",
                    "hit_count_as_of_date": 3,
                }
            ]
        ),
        prices=_prices(["A"], "2025-01-01", 1),
        start_date="2025-01-01",
        end_date="2025-01-01",
        run_id="tech-bt-20250101-test",
    )

    assert snapshots["hit_count_as_of_date"].tolist() == [3.0]
    assert snapshots["filter_reason"].tolist() == [""]


def test_explicit_hit_count_as_of_date_preserves_existing_filter_reason() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {
                    "asset_id": "A",
                    "stock_name": "Alpha",
                    "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                    "trade_date": "2025-01-01",
                    "hit_count_as_of_date": 3,
                    "filter_reason": "source_note",
                }
            ]
        ),
        prices=_prices(["A"], "2025-01-01", 1),
        start_date="2025-01-01",
        end_date="2025-01-01",
        run_id="tech-bt-20250101-test",
    )

    assert snapshots["filter_reason"].tolist() == ["source_note"]


def test_dated_hit_count_as_of_date_carries_forward_from_candidate_as_of_date() -> None:
    low_static = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 1}]
        ),
        prices=_prices(["A"], "2025-01-01", 2),
        start_date="2025-01-02",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-low",
    )
    high_static = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 99}]
        ),
        prices=_prices(["A"], "2025-01-01", 2),
        start_date="2025-01-02",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-high",
    )

    assert low_static["hit_count_as_of_date"].tolist() == [1.0]
    assert high_static["hit_count_as_of_date"].tolist() == [99.0]
    assert high_static["filter_reason"].tolist() == [""]
    assert high_static["bottleneck_score"].iloc[0] > low_static["bottleneck_score"].iloc[0]
    assert high_static["bottleneck_rank"].tolist() == low_static["bottleneck_rank"].tolist()


def test_dated_hit_count_as_of_rows_update_score_only_from_candidate_as_of_date() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {
                    "asset_id": "A",
                    "stock_name": "Alpha",
                    "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                    "hit_count_as_of_date": 1,
                },
                {
                    "asset_id": "A",
                    "stock_name": "Alpha",
                    "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-03",
                    "hit_count_as_of_date": 9,
                },
                {
                    "asset_id": "B",
                    "stock_name": "Beta",
                    "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                    "hit_count_as_of_date": 9,
                },
            ]
        ),
        prices=_prices(["A", "B"], "2025-01-01", 3),
        start_date="2025-01-01",
        end_date="2025-01-03",
        run_id="tech-bt-20250103-test",
    )

    by_date = snapshots[snapshots["asset_id"] == "A"].set_index("trade_date")
    assert by_date.at["2025-01-01", "hit_count_as_of_date"] == 1.0
    assert by_date.at["2025-01-02", "hit_count_as_of_date"] == 1.0
    assert by_date.at["2025-01-03", "hit_count_as_of_date"] == 9.0
    assert by_date.at["2025-01-03", "bottleneck_score"] > by_date.at["2025-01-02", "bottleneck_score"]


def test_build_snapshot_normalizes_api_boundary_dates() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 2}]
        ),
        prices=_prices(["A"], "2025-01-01", 3),
        start_date="2025-1-2",
        end_date="2025-1-2",
        run_id="tech-bt-20250102-test",
    )

    assert snapshots["trade_date"].unique().tolist() == ["2025-01-02"]


def test_snapshot_requires_candidate_pit_date() -> None:
    with pytest.raises(ValueError, match="candidate_as_of_date missing: provide trade_date or candidate_trade_date"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01", "hit_count": 3}]
            ),
            prices=_prices(["A"], "2025-01-01", 1),
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def test_snapshot_emits_candidate_only_when_asset_has_same_day_price() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 2},
                {"asset_id": "B", "stock_name": "Beta", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 2},
            ]
        ),
        prices=pd.DataFrame(
            [
                {"trade_date": "2025-01-01", "asset_id": "A", "open": 10.0, "high": 10.0, "low": 9.0, "close": 10.0},
                {"trade_date": "2025-01-01", "asset_id": "B", "open": 10.0, "high": 10.0, "low": 9.0, "close": 10.0},
                {"trade_date": "2025-01-02", "asset_id": "B", "open": 11.0, "high": 11.0, "low": 10.0, "close": 11.0},
            ]
        ),
        start_date="2025-01-02",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-test",
    )

    assert snapshots["trade_date"].unique().tolist() == ["2025-01-02"]
    assert snapshots["asset_id"].tolist() == ["B"]


def test_explicit_hit_count_as_of_date_must_be_numeric() -> None:
    with pytest.raises(ValueError, match="hit_count_as_of_date must be numeric"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [
                    {
                        "asset_id": "A",
                        "stock_name": "Alpha",
                        "first_hit_date": "2025-01-01",
                        "candidate_trade_date": "2025-01-01",
                        "hit_count_as_of_date": "many",
                    }
                ]
            ),
            prices=_prices(["A"], "2025-01-01", 1),
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def test_validate_candidate_snapshot_frame_rejects_future_dates() -> None:
    frame = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-04",
                    "candidate_trade_date": "2025-01-04",
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


def test_validate_candidate_snapshot_frame_rejects_invalid_dates() -> None:
    frame = _valid_snapshot_frame()
    frame.loc[0, "trade_date"] = "not-a-date"

    with pytest.raises(ValueError, match="invalid date in candidate snapshot: trade_date"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_stale_data_as_of_date() -> None:
    frame = _valid_snapshot_frame()
    frame.loc[0, "data_as_of_date"] = "2025-01-02"

    with pytest.raises(ValueError, match="data_as_of_date must equal trade_date"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_duplicate_trade_date_asset_id() -> None:
    frame = pd.concat([_valid_snapshot_frame(), _valid_snapshot_frame()], ignore_index=True)
    frame.loc[1, "bottleneck_rank"] = 2

    with pytest.raises(ValueError, match="duplicate candidate snapshot rows for trade_date and asset_id"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_duplicate_rank_within_trade_date() -> None:
    frame = _ranked_snapshot_frame([1, 1])

    with pytest.raises(ValueError, match="duplicate bottleneck_rank within trade_date"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_non_contiguous_ranks() -> None:
    frame = _ranked_snapshot_frame([1, 3])

    with pytest.raises(ValueError, match="bottleneck_rank must be contiguous within trade_date"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_rank_order_mismatch() -> None:
    frame = _ranked_snapshot_frame([1, 2])
    frame.loc[0, "bottleneck_score"] = 0.1
    frame.loc[1, "bottleneck_score"] = 0.9

    with pytest.raises(ValueError, match="bottleneck_rank must match score ordering"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_top5_mismatch() -> None:
    frame = _ranked_snapshot_frame([1, 2])
    frame.loc[0, "is_top5"] = False

    with pytest.raises(ValueError, match="is_top5 must equal bottleneck_rank <= 5"):
        validate_candidate_snapshot_frame(frame)


@pytest.mark.parametrize("column", ["bottleneck_score", "hit_count_as_of_date"])
def test_validate_candidate_snapshot_frame_rejects_non_numeric_metrics(column: str) -> None:
    frame = _valid_snapshot_frame()
    frame[column] = frame[column].astype(object)
    frame.loc[0, column] = "not-a-number"

    with pytest.raises(ValueError, match=f"{column} must be numeric"):
        validate_candidate_snapshot_frame(frame)


@pytest.mark.parametrize("column", ["bottleneck_score", "hit_count_as_of_date", "bottleneck_rank"])
def test_validate_candidate_snapshot_frame_rejects_non_finite_numeric_metrics(column: str) -> None:
    frame = _valid_snapshot_frame()
    frame[column] = frame[column].astype(object)
    frame.loc[0, column] = float("inf")

    with pytest.raises(ValueError, match=f"{column} must be finite"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_negative_hit_count() -> None:
    frame = _valid_snapshot_frame()
    frame.loc[0, "hit_count_as_of_date"] = -1

    with pytest.raises(ValueError, match="hit_count_as_of_date must be >= 0"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_negative_score() -> None:
    frame = _valid_snapshot_frame()
    frame.loc[0, "bottleneck_score"] = -0.1

    with pytest.raises(ValueError, match="bottleneck_score must be >= 0"):
        validate_candidate_snapshot_frame(frame)


@pytest.mark.parametrize("rank", [0, 1.5])
def test_validate_candidate_snapshot_frame_rejects_non_positive_or_decimal_rank(rank: float) -> None:
    frame = _valid_snapshot_frame()
    frame["bottleneck_rank"] = frame["bottleneck_rank"].astype(object)
    frame.loc[0, "bottleneck_rank"] = rank

    with pytest.raises(ValueError, match="bottleneck_rank must be finite positive integer"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_invalid_filter_decision() -> None:
    frame = _valid_snapshot_frame()
    frame.loc[0, "filter_decision"] = "maybe"

    with pytest.raises(ValueError, match="filter_decision must be one of"):
        validate_candidate_snapshot_frame(frame)


@pytest.mark.parametrize("column", ["asset_id", "engine_version", "run_id"])
@pytest.mark.parametrize("value", ["", None])
def test_validate_candidate_snapshot_frame_rejects_missing_identity_fields(column: str, value) -> None:
    frame = _valid_snapshot_frame()
    frame[column] = frame[column].astype(object)
    frame.loc[0, column] = value

    with pytest.raises(ValueError, match=f"{column} must be non-empty"):
        validate_candidate_snapshot_frame(frame)


def test_validate_candidate_snapshot_frame_rejects_wrong_engine_version() -> None:
    frame = _valid_snapshot_frame()
    frame.loc[0, "engine_version"] = "other-engine"

    with pytest.raises(ValueError, match="engine_version must equal"):
        validate_candidate_snapshot_frame(frame)


def test_write_and_read_candidate_snapshots_round_trip(tmp_path) -> None:
    frame = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 3}]
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


def test_read_candidate_snapshots_normalizes_api_boundary_dates(tmp_path) -> None:
    frame = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 3}]
        ),
        prices=_prices(["A"], "2025-01-01", 2),
        start_date="2025-01-01",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-test",
    )
    path = tmp_path / "tech_bottleneck_daily_candidates.csv"

    write_candidate_snapshots(frame, path)
    loaded = read_candidate_snapshots(path, start_date="2025-1-2", end_date="2025-1-2")

    assert loaded["trade_date"].unique().tolist() == ["2025-01-02"]


def test_validate_base_candidate_source_requires_fresh_generation_date() -> None:
    stale = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "source_latest_trade_date": "2025-01-02",
            }
        ]
    )

    with pytest.raises(ValueError, match="base candidate source is stale"):
        validate_base_candidate_source_freshness(stale, end_date="2025-01-03")


def test_validate_base_candidate_source_rejects_invalid_freshness_metadata() -> None:
    invalid = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "source_latest_trade_date": "not-a-date",
            }
        ]
    )

    with pytest.raises(ValueError, match="invalid base candidate freshness metadata: source_latest_trade_date"):
        validate_base_candidate_source_freshness(invalid, end_date="2025-01-03")


def test_validate_base_candidate_source_checks_all_present_freshness_metadata() -> None:
    invalid_later_column = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "source_latest_trade_date": "2025-01-03",
                "data_as_of_date": "not-a-date",
            }
        ]
    )

    with pytest.raises(ValueError, match="invalid base candidate freshness metadata: data_as_of_date"):
        validate_base_candidate_source_freshness(invalid_later_column, end_date="2025-01-03")


def test_validate_base_candidate_source_rejects_stale_row_even_when_another_row_is_fresh() -> None:
    mixed = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "source_latest_trade_date": "2025-01-02",
            },
            {
                "asset_id": "B",
                "stock_name": "Beta",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "source_latest_trade_date": "2025-01-03",
            },
        ]
    )

    with pytest.raises(ValueError, match="base candidate source is stale"):
        validate_base_candidate_source_freshness(mixed, end_date="2025-01-03")


def test_validate_base_candidate_source_rejects_stale_coverage_even_with_fresh_generation_date() -> None:
    stale_coverage = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "data_as_of_date": "2025-01-02",
                "generated_trade_date": "2025-01-03",
            }
        ]
    )

    with pytest.raises(ValueError, match="base candidate source is stale"):
        validate_base_candidate_source_freshness(stale_coverage, end_date="2025-01-03")


def test_validate_base_candidate_source_rejects_stale_generated_trade_date() -> None:
    stale_generated = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "data_as_of_date": "2025-01-03",
                "generated_trade_date": "2025-01-02",
            }
        ]
    )

    with pytest.raises(ValueError, match="generated_trade_date is stale"):
        validate_base_candidate_source_freshness(stale_generated, end_date="2025-01-03")


def test_validate_base_candidate_source_rejects_generated_date_before_coverage_date() -> None:
    contradictory = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "data_as_of_date": "2025-01-03",
                "generated_trade_date": "2025-01-02",
            }
        ]
    )

    with pytest.raises(ValueError, match="generated_trade_date must be >= coverage date"):
        validate_base_candidate_source_freshness(contradictory, end_date="2025-01-02")


def test_validate_base_candidate_source_rejects_generation_only_freshness_metadata() -> None:
    generation_only = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "generated_trade_date": "2025-01-03",
            }
        ]
    )

    with pytest.raises(ValueError, match="base candidate source freshness metadata missing"):
        validate_base_candidate_source_freshness(generation_only, end_date="2025-01-03")


def test_validate_base_candidate_source_normalizes_api_end_date() -> None:
    fresh = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01",
                "hit_count": 3,
                "data_as_of_date": "2025-01-02",
            }
        ]
    )

    validate_base_candidate_source_freshness(fresh, end_date="2025-1-2")


def test_validate_base_candidate_source_requires_formal_freshness_metadata() -> None:
    missing = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-05",
                    "candidate_trade_date": "2025-01-05",
                "hit_count": 3,
            }
        ]
    )

    with pytest.raises(ValueError, match="base candidate source freshness metadata missing"):
        validate_base_candidate_source_freshness(missing, end_date="2025-01-03")


def test_snapshot_rejects_duplicate_price_rows() -> None:
    prices = _prices(["A"], "2025-01-01", 1)
    prices = pd.concat([prices, prices], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate price rows for trade_date and asset_id"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 3}]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def test_snapshot_rejects_duplicate_price_rows_before_dropping_missing_close() -> None:
    prices = _prices(["A"], "2025-01-01", 1)
    duplicate_missing_close = prices.copy()
    duplicate_missing_close.loc[0, "close"] = None
    prices = pd.concat([prices, duplicate_missing_close], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate price rows for trade_date and asset_id"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 3}]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def test_snapshot_rejects_invalid_price_trade_date() -> None:
    prices = _prices(["A"], "2025-01-01", 1)
    prices.loc[0, "trade_date"] = "not-a-date"

    with pytest.raises(ValueError, match="invalid price date: trade_date"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 3}]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def test_snapshot_always_uses_formal_engine_version() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 3}]
        ),
        prices=_prices(["A"], "2025-01-01", 1),
        start_date="2025-01-01",
        end_date="2025-01-01",
        run_id="tech-bt-20250101-test",
    )

    assert snapshots["engine_version"].unique().tolist() == [TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION]


def test_snapshot_builder_does_not_expose_engine_version_override() -> None:
    assert "engine_version" not in inspect.signature(build_point_in_time_candidate_snapshots).parameters


@pytest.mark.parametrize("start_date,end_date", [("2025-01-03", "2025-01-02"), ("2025-1-3", "2025-1-2")])
def test_snapshot_builder_rejects_start_date_after_end_date(start_date: str, end_date: str) -> None:
    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count_as_of_date": 3}]
            ),
            prices=_prices(["A"], "2025-01-01", 1),
            start_date=start_date,
            end_date=end_date,
            run_id="tech-bt-20250101-test",
        )


def test_read_candidate_snapshots_rejects_start_date_after_end_date(tmp_path) -> None:
    frame = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 3}]
        ),
        prices=_prices(["A"], "2025-01-01", 1),
        start_date="2025-01-01",
        end_date="2025-01-01",
        run_id="tech-bt-20250101-test",
    )
    path = tmp_path / "tech_bottleneck_daily_candidates.csv"
    write_candidate_snapshots(frame, path)

    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        read_candidate_snapshots(path, start_date="2025-01-03", end_date="2025-01-02")


@pytest.mark.parametrize(
    ("close", "message"),
    [
        ("bad-close", "close must be numeric"),
        (float("inf"), "close must be finite"),
        (0.0, "close must be > 0"),
        (-1.0, "close must be > 0"),
    ],
)
def test_snapshot_rejects_invalid_price_close_values(close, message: str) -> None:
    prices = _prices(["A"], "2025-01-01", 1)
    prices["close"] = prices["close"].astype(object)
    prices.loc[0, "close"] = close

    with pytest.raises(ValueError, match=message):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 3}]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


@pytest.mark.parametrize("column", ["high", "low"])
def test_snapshot_rejects_missing_price_ohlc_columns(column: str) -> None:
    prices = _prices(["A"], "2025-01-01", 1).drop(columns=[column])

    with pytest.raises(ValueError, match=f"price input missing columns: \\['{column}'\\]"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [
                    {
                        "asset_id": "A",
                        "stock_name": "Alpha",
                        "first_hit_date": "2025-01-01",
                        "candidate_trade_date": "2025-01-01",
                        "hit_count": 3,
                    }
                ]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


@pytest.mark.parametrize("open_price", [0.0, -1.0])
def test_snapshot_rejects_non_positive_price_open_values(open_price: float) -> None:
    prices = _prices(["A"], "2025-01-01", 1)
    prices.loc[0, "open"] = open_price

    with pytest.raises(ValueError, match="open must be > 0"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01",
                    "candidate_trade_date": "2025-01-01", "hit_count": 3}]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def test_snapshot_rejects_price_high_below_close() -> None:
    prices = _prices(["A"], "2025-01-01", 1)
    prices.loc[0, "high"] = prices.loc[0, "close"] - 0.01

    with pytest.raises(ValueError, match="high must be >= max\\(open, close, low\\)"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [
                    {
                        "asset_id": "A",
                        "stock_name": "Alpha",
                        "first_hit_date": "2025-01-01",
                        "candidate_trade_date": "2025-01-01",
                        "hit_count": 3,
                    }
                ]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def test_snapshot_rejects_price_low_above_close() -> None:
    prices = _prices(["A"], "2025-01-01", 1)
    prices.loc[0, "low"] = prices.loc[0, "close"] + 0.01

    with pytest.raises(ValueError, match="low must be <= min\\(open, close, high\\)"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame(
                [
                    {
                        "asset_id": "A",
                        "stock_name": "Alpha",
                        "first_hit_date": "2025-01-01",
                        "candidate_trade_date": "2025-01-01",
                        "hit_count": 3,
                    }
                ]
            ),
            prices=prices,
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


@pytest.mark.parametrize(
    "column",
    ["first_hit_date", "candidate_trade_date", "financial_as_of_date", "technical_as_of_date"],
)
def test_snapshot_rejects_invalid_base_candidate_dates(column: str) -> None:
    candidate = {
        "asset_id": "A",
        "stock_name": "Alpha",
        "first_hit_date": "2025-01-01",
        "candidate_trade_date": "2025-01-01",
        "hit_count": 3,
        "financial_as_of_date": "2025-01-01",
        "technical_as_of_date": "2025-01-01",
    }
    candidate[column] = "not-a-date"

    with pytest.raises(ValueError, match=f"invalid base candidate date: {column}"):
        build_point_in_time_candidate_snapshots(
            base_candidates=pd.DataFrame([candidate]),
            prices=_prices(["A"], "2025-01-01", 1),
            start_date="2025-01-01",
            end_date="2025-01-01",
            run_id="tech-bt-20250101-test",
        )


def _valid_snapshot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-02",
                    "candidate_trade_date": "2025-01-02",
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


def _ranked_snapshot_frame(ranks: list[int]) -> pd.DataFrame:
    rows = []
    for index, rank in enumerate(ranks):
        row = _valid_snapshot_frame().iloc[0].to_dict()
        row["asset_id"] = f"A{index}"
        row["stock_name"] = f"Name{index}"
        row["bottleneck_rank"] = rank
        row["is_top5"] = rank <= 5
        rows.append(row)
    return pd.DataFrame(rows)


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
