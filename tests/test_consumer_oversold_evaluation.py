from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import (
    LEGACY_OUTPUT_FILENAMES,
    UNIFIED_OUTPUT_FILENAMES,
)
from stock_research.consumer_oversold.evaluation import (
    EVALUATION_FILENAMES,
    _discover_snapshots,
    _load_evaluation_bars,
    _publish,
    _verified_release,
    evaluate_consumer_oversold_snapshots,
    run_consumer_oversold_evaluation,
)


def _path(asset_id: str, snapshot_date: str, subindustry: str, closes: dict[int, float], periods: int = 121):
    dates = pd.bdate_range(snapshot_date, periods=periods)
    values = [100.0] * periods
    for index, close in closes.items():
        if index < periods:
            values[index] = close
    return pd.DataFrame(
        {
            "snapshot_trade_date": snapshot_date,
            "asset_id": asset_id,
            "consumer_subindustry": subindustry,
            "trade_date": dates,
            "close": values,
        }
    )


def _snapshots() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "asset_id": "A",
                "stock_code": "000001",
                "stock_name": "Alpha",
                "consumer_subindustry": "food",
                "repair_bucket": "expected_repair",
            },
            {
                "trade_date": "2026-01-12",
                "asset_id": "B",
                "stock_code": "000002",
                "stock_name": "Beta",
                "consumer_subindustry": "retail",
                "repair_bucket": "early_validation",
            },
        ]
    )


def _bars(periods: int = 121) -> pd.DataFrame:
    return pd.concat(
        [
            _path("A", "2026-01-05", "food", {10: 80.0, 20: 120.0, 60: 130.0, 120: 140.0}, periods),
            _path("A_PEER", "2026-01-05", "food", {20: 90.0, 60: 110.0, 120: 120.0}, periods),
            _path("B", "2026-01-12", "retail", {20: 110.0, 60: 120.0, 120: 130.0}, periods),
            _path("B_PEER", "2026-01-12", "retail", {20: 100.0, 60: 110.0, 120: 120.0}, periods),
        ],
        ignore_index=True,
    )


def _manifest(release: Path, filenames=LEGACY_OUTPUT_FILENAMES) -> None:
    lines = []
    for filename in sorted(filenames.values()):
        path = release / filename
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {filename}")
        path.chmod(0o444)
    manifest = release / ".manifest.sha256"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest.chmod(0o444)
    release.chmod(0o555)


def _sealed_release(
    parent: Path,
    name: str,
    trade_date: str,
    asset_id: str,
    bucket: str,
    stock_name: str | None = None,
) -> Path:
    release = parent / ".releases" / name
    release.mkdir(parents=True)
    selected = pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "stock_code": asset_id[-6:].zfill(6),
                "stock_name": stock_name or asset_id,
                "consumer_subindustry": "food",
                "repair_bucket": bucket,
                "bucket_rank": 1,
            }
        ]
    )
    empty = selected.iloc[0:0].copy()
    selected.to_csv(
        release / LEGACY_OUTPUT_FILENAMES["expected" if bucket == "expected_repair" else "early"],
        index=False,
    )
    empty.to_csv(
        release / LEGACY_OUTPUT_FILENAMES["early" if bucket == "expected_repair" else "expected"],
        index=False,
    )
    scores = pd.concat(
        [
            selected,
            pd.DataFrame(
                [
                    {
                        "asset_id": f"{asset_id}_PEER",
                        "stock_code": "999999",
                        "stock_name": "Peer",
                        "consumer_subindustry": "food",
                        "repair_bucket": "",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    scores.to_csv(release / LEGACY_OUTPUT_FILENAMES["scores"], index=False)
    pd.DataFrame(columns=["asset_id", "exclusion_reasons"]).to_csv(
        release / LEGACY_OUTPUT_FILENAMES["exclusions"], index=False
    )
    evidence = selected.loc[:, ["asset_id", "stock_code", "repair_bucket"]].copy()
    evidence.to_csv(release / LEGACY_OUTPUT_FILENAMES["evidence"], index=False)
    (release / LEGACY_OUTPUT_FILENAMES["coverage"]).write_text(
        json.dumps({"trade_date": trade_date}), encoding="utf-8"
    )
    (release / LEGACY_OUTPUT_FILENAMES["report"]).write_text("weekly report\n", encoding="utf-8")
    _manifest(release)
    return release


def _sealed_unified_release(
    parent: Path,
    name: str,
    trade_date: str,
    *,
    count: int = 20,
    publication_status: str = "ready",
) -> Path:
    release = parent / ".releases" / name
    release.mkdir(parents=True)
    selected = pd.DataFrame(
        [
            {
                "asset_id": f"U{rank:02d}",
                "stock_code": f"{rank:06d}",
                "stock_name": f"Unified {rank}",
                "consumer_subindustry": "food",
                "repair_bucket": "expected_repair" if rank % 2 else "early_validation",
                "final_rank": rank,
            }
            for rank in range(1, count + 1)
        ]
    )
    selected.to_csv(release / UNIFIED_OUTPUT_FILENAMES["top20"], index=False)
    scores = pd.concat(
        [
            selected.drop(columns="final_rank"),
            pd.DataFrame(
                [{
                    "asset_id": "PEER",
                    "stock_code": "999999",
                    "stock_name": "Peer",
                    "consumer_subindustry": "food",
                    "repair_bucket": "",
                }]
            ),
        ],
        ignore_index=True,
    )
    scores.to_csv(release / UNIFIED_OUTPUT_FILENAMES["scores"], index=False)
    selected.loc[:, ["asset_id", "stock_code", "repair_bucket"]].to_csv(
        release / UNIFIED_OUTPUT_FILENAMES["evidence"], index=False
    )
    pd.DataFrame(columns=["asset_id", "exclusion_reasons"]).to_csv(
        release / UNIFIED_OUTPUT_FILENAMES["exclusions"], index=False
    )
    for key in ("reserve", "preaudit", "comparison"):
        pd.DataFrame(columns=["asset_id"]).to_csv(
            release / UNIFIED_OUTPUT_FILENAMES[key], index=False
        )
    (release / UNIFIED_OUTPUT_FILENAMES["coverage"]).write_text(
        json.dumps(
            {
                "trade_date": trade_date,
                "publication_status": publication_status,
                "final_top_n": count,
            }
        ),
        encoding="utf-8",
    )
    (release / UNIFIED_OUTPUT_FILENAMES["report"]).write_text(
        "weekly report\n", encoding="utf-8"
    )
    _manifest(release, UNIFIED_OUTPUT_FILENAMES)
    return release


def _rewrite_csv(release: Path, filenames, key: str, frame: pd.DataFrame) -> None:
    release.chmod(0o755)
    artifact = release / filenames[key]
    artifact.chmod(0o644)
    (release / ".manifest.sha256").chmod(0o644)
    frame.to_csv(artifact, index=False)
    _manifest(release, filenames)


def test_forward_evaluation_computes_absolute_excess_and_path_drawdown():
    result = evaluate_consumer_oversold_snapshots(_snapshots(), _bars())

    assert set(result["detail"]["horizon"]) == {5, 20}

    row = result["detail"].query("asset_id == 'A' and horizon == 20").iloc[0]
    assert row["repair_bucket"] == "expected_repair"
    assert row["evaluation_status"] == "completed"
    assert row["forward_return"] == pytest.approx(0.20)
    assert row["industry_forward_return"] == pytest.approx(0.05)
    assert row["excess_return"] == pytest.approx(0.15)
    assert row["path_max_drawdown"] == pytest.approx(-0.20)
    assert bool(row["excess_win"])


def test_forward_evaluation_keeps_incomplete_horizons_pending_and_summarizes():
    result = evaluate_consumer_oversold_snapshots(
        _snapshots(), _bars(periods=61), horizons=(120, 60, 20)
    )

    assert result["detail"]["horizon"].drop_duplicates().tolist() == [20, 60, 120]
    pending = result["detail"].query("asset_id == 'A' and horizon == 120").iloc[0]
    assert pending["evaluation_status"] == "pending"
    assert pd.isna(pending["forward_return"])
    summary = result["summary"].query(
        "repair_bucket == 'expected_repair' and horizon == 20"
    ).iloc[0]
    assert summary["completed_count"] == 1
    assert summary["pending_count"] == 0
    assert summary["win_rate"] == pytest.approx(1.0)
    assert summary["median_return"] == pytest.approx(0.20)
    assert summary["median_excess_return"] == pytest.approx(0.15)
    assert summary["median_path_max_drawdown"] == pytest.approx(-0.20)


def test_horizon_uses_shared_market_trading_date_and_does_not_shift_for_suspension():
    bars = _bars()
    market_day_20 = pd.bdate_range("2026-01-05", periods=21)[-1]
    bars = bars.loc[
        ~(
            bars["snapshot_trade_date"].eq("2026-01-05")
            & bars["asset_id"].eq("A")
            & bars["trade_date"].eq(market_day_20)
        )
    ].copy()

    result = evaluate_consumer_oversold_snapshots(_snapshots(), bars, horizons=(20,))

    row = result["detail"].query("asset_id == 'A' and horizon == 20").iloc[0]
    assert row["evaluation_status"] == "pending"
    assert pd.isna(row["forward_return"])


def test_snapshot_calendar_uses_all_memberships_before_subindustry_filtering():
    snapshots = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "asset_id": "R",
                "stock_code": "000001",
                "stock_name": "Retail",
                "consumer_subindustry": "retail",
                "repair_bucket": "expected_repair",
            },
            {
                "trade_date": "2026-01-05",
                "asset_id": "F",
                "stock_code": "000002",
                "stock_name": "Food",
                "consumer_subindustry": "food",
                "repair_bucket": "early_validation",
            },
        ]
    )
    bars = pd.DataFrame(
        [
            ["2026-01-05", "R", "retail", "2026-01-05", 100.0],
            ["2026-01-05", "R", "retail", "2026-01-06", 110.0],
            ["2026-01-05", "R_PEER", "retail", "2026-01-05", 100.0],
            ["2026-01-05", "R_PEER", "retail", "2026-01-06", 100.0],
            ["2026-01-05", "F", "food", "2026-01-05", 100.0],
            ["2026-01-05", "F", "food", "2026-01-07", 120.0],
            ["2026-01-05", "F_PEER", "food", "2026-01-05", 100.0],
            ["2026-01-05", "F_PEER", "food", "2026-01-07", 110.0],
        ],
        columns=[
            "snapshot_trade_date",
            "asset_id",
            "consumer_subindustry",
            "trade_date",
            "close",
        ],
    )

    detail = evaluate_consumer_oversold_snapshots(snapshots, bars, horizons=(1,))["detail"]

    retail = detail.set_index("asset_id").loc["R"]
    food = detail.set_index("asset_id").loc["F"]
    assert retail["evaluation_status"] == "completed"
    assert retail["horizon_trade_date"] == "2026-01-06"
    assert food["evaluation_status"] == "pending"


def test_two_buckets_in_same_week_share_one_snapshot_calendar():
    snapshots = pd.DataFrame(
        [
            ["2026-01-05", "E", "000001", "Expected", "retail", "expected_repair"],
            ["2026-01-05", "V", "000002", "Validation", "food", "early_validation"],
        ],
        columns=_snapshots().columns,
    )
    bars = pd.DataFrame(
        [
            ["2026-01-05", "E", "retail", "2026-01-05", 100.0],
            ["2026-01-05", "E", "retail", "2026-01-07", 110.0],
            ["2026-01-05", "V", "food", "2026-01-05", 100.0],
            ["2026-01-05", "V", "food", "2026-01-06", 110.0],
        ],
        columns=[
            "snapshot_trade_date",
            "asset_id",
            "consumer_subindustry",
            "trade_date",
            "close",
        ],
    )

    detail = evaluate_consumer_oversold_snapshots(snapshots, bars, horizons=(1,))["detail"]

    by_asset = detail.set_index("asset_id")
    assert by_asset.loc["E", "evaluation_status"] == "pending"
    assert by_asset.loc["V", "evaluation_status"] == "completed"
    assert by_asset.loc["V", "horizon_trade_date"] == "2026-01-06"


def test_different_snapshot_weeks_build_independent_calendars():
    snapshots = pd.DataFrame(
        [
            ["2026-01-05", "A", "000001", "Alpha", "food", "expected_repair"],
            ["2026-01-12", "B", "000002", "Beta", "food", "early_validation"],
        ],
        columns=_snapshots().columns,
    )
    bars = pd.DataFrame(
        [
            ["2026-01-05", "A", "food", "2026-01-05", 100.0],
            ["2026-01-05", "A", "food", "2026-01-06", 110.0],
            ["2026-01-12", "B", "food", "2026-01-12", 100.0],
            ["2026-01-12", "B", "food", "2026-01-14", 120.0],
        ],
        columns=[
            "snapshot_trade_date",
            "asset_id",
            "consumer_subindustry",
            "trade_date",
            "close",
        ],
    )

    detail = evaluate_consumer_oversold_snapshots(snapshots, bars, horizons=(1,))["detail"]

    by_asset = detail.set_index("asset_id")
    assert by_asset.loc["A", "horizon_trade_date"] == "2026-01-06"
    assert by_asset.loc["B", "horizon_trade_date"] == "2026-01-14"


def test_run_prefers_current_sealed_release_and_deduplicates_trade_date(tmp_path, monkeypatch):
    week = tmp_path / "snapshots" / "2026-01-05"
    old = _sealed_release(week, "consumer-oversold-old", "2026-01-05", "OLD", "expected_repair")
    current = _sealed_release(week, "consumer-oversold-current", "2026-01-05", "A", "expected_repair")
    (week / "current").symlink_to(Path(".releases") / current.name, target_is_directory=True)
    loose = week / LEGACY_OUTPUT_FILENAMES["expected"]
    loose.write_text("asset_id,repair_bucket\nLOOSE,expected_repair\n", encoding="utf-8")
    raw_bars = _bars().drop(columns=["snapshot_trade_date", "consumer_subindustry"])
    monkeypatch.setattr(
        "stock_research.consumer_oversold.evaluation._load_evaluation_bars",
        lambda **kwargs: raw_bars,
    )

    result = run_consumer_oversold_evaluation(
        snapshots_root=tmp_path / "snapshots",
        end_date="2026-07-30",
        output_dir=tmp_path / "evaluation",
        service="test",
    )

    assert set(result["detail"]["asset_id"]) == {"A"}
    assert "OLD" not in set(result["detail"]["asset_id"])
    assert "LOOSE" not in set(result["detail"]["asset_id"])
    assert old != current


def test_run_accepts_a_current_symlink_as_snapshots_root(tmp_path, monkeypatch):
    week = tmp_path / "week"
    release = _sealed_release(
        week, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    current = week / "current"
    current.symlink_to(Path(".releases") / release.name, target_is_directory=True)
    raw_bars = _bars().drop(columns=["snapshot_trade_date", "consumer_subindustry"])
    monkeypatch.setattr(
        "stock_research.consumer_oversold.evaluation._load_evaluation_bars",
        lambda **kwargs: raw_bars,
    )

    result = run_consumer_oversold_evaluation(
        snapshots_root=current,
        end_date="2026-07-30",
        output_dir=tmp_path / "evaluation",
        service="test",
    )

    assert set(result["detail"]["asset_id"]) == {"A"}


def test_run_rejects_tampered_release_and_overlapping_paths(tmp_path, monkeypatch):
    week = tmp_path / "snapshots" / "2026-01-05"
    release = _sealed_release(week, "consumer-oversold-current", "2026-01-05", "A", "expected_repair")
    (week / "current").symlink_to(Path(".releases") / release.name, target_is_directory=True)
    evidence = release / LEGACY_OUTPUT_FILENAMES["evidence"]
    evidence.chmod(0o644)
    evidence.write_text(evidence.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    monkeypatch.setattr(
        "stock_research.consumer_oversold.evaluation._load_evaluation_bars",
        lambda **kwargs: pd.DataFrame(),
    )

    with pytest.raises(ValueError, match="no valid sealed consumer oversold snapshots"):
        run_consumer_oversold_evaluation(
            snapshots_root=tmp_path / "snapshots",
            end_date="2026-07-30",
            output_dir=tmp_path / "evaluation",
            service="test",
        )


def test_verified_release_rejects_writable_release_directory(tmp_path):
    release = _sealed_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    release.chmod(0o755)

    assert _verified_release(release) is None


@pytest.mark.parametrize(
    "filename",
    [".manifest.sha256", *LEGACY_OUTPUT_FILENAMES.values()],
)
def test_verified_release_rejects_writable_manifest_or_artifact(tmp_path, filename):
    release = _sealed_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    (release / filename).chmod(0o644)

    assert _verified_release(release) is None


def test_verified_release_rejects_symlink_artifact_even_when_hash_matches(tmp_path):
    release = _sealed_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    artifact = release / LEGACY_OUTPUT_FILENAMES["evidence"]
    external = tmp_path / "external-evidence.csv"
    external.write_bytes(artifact.read_bytes())
    external.chmod(0o444)
    release.chmod(0o755)
    artifact.unlink()
    artifact.symlink_to(external)
    release.chmod(0o555)

    assert _verified_release(release) is None
    with pytest.raises(ValueError, match="must not overlap"):
        run_consumer_oversold_evaluation(
            snapshots_root=tmp_path / "snapshots",
            end_date="2026-07-30",
            output_dir=tmp_path / "snapshots" / "evaluation",
            service="test",
        )


def test_verified_release_identifies_exact_legacy_and_unified_schemas(tmp_path):
    legacy = _sealed_release(
        tmp_path / "legacy", "consumer-oversold-legacy", "2026-01-05", "A", "expected_repair"
    )
    unified = _sealed_unified_release(
        tmp_path / "unified", "consumer-oversold-unified", "2026-01-12"
    )

    assert _verified_release(legacy) == "legacy"
    assert _verified_release(unified) == "unified"


@pytest.mark.parametrize("mutation", ["extra", "missing", "hybrid"])
def test_verified_release_rejects_non_exact_manifest_file_sets(tmp_path, mutation):
    release = _sealed_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    release.chmod(0o755)
    manifest = release / ".manifest.sha256"
    manifest.chmod(0o644)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if mutation == "missing":
        lines.pop()
    else:
        name = (
            "unexpected.csv"
            if mutation == "extra"
            else UNIFIED_OUTPUT_FILENAMES["top20"]
        )
        artifact = release / name
        artifact.write_text("asset_id\n", encoding="utf-8")
        artifact.chmod(0o444)
        lines.append(f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest.chmod(0o444)
    release.chmod(0o555)

    assert _verified_release(release) is None


def test_discovery_reads_unified_top20_with_fixed_membership_and_final_rank(tmp_path):
    week = tmp_path / "snapshots" / "2026-01-05"
    release = _sealed_unified_release(
        week, "consumer-oversold-unified", "2026-01-05"
    )
    (week / "current").symlink_to(Path(".releases") / release.name, target_is_directory=True)

    snapshots, membership = _discover_snapshots(tmp_path / "snapshots", "2026-07-29")

    assert len(snapshots) == 20
    assert snapshots["snapshot_rank"].tolist() == list(range(1, 21))
    assert set(snapshots["repair_bucket"]) == {"expected_repair", "early_validation"}
    assert set(membership["asset_id"]) == {*(f"U{rank:02d}" for rank in range(1, 21)), "PEER"}


@pytest.mark.parametrize("rank", ["1.0", "1e0", "+1", "", "-1", "0"])
def test_discovery_rejects_noncanonical_unified_final_rank(tmp_path, rank):
    release = _sealed_unified_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", count=1
    )
    selected = pd.read_csv(release / UNIFIED_OUTPUT_FILENAMES["top20"], dtype=str)
    selected.loc[0, "final_rank"] = rank
    _rewrite_csv(release, UNIFIED_OUTPUT_FILENAMES, "top20", selected)

    with pytest.raises(ValueError, match="no valid sealed"):
        _discover_snapshots(tmp_path, "2026-07-29")


@pytest.mark.parametrize("ranks", [[1, 1, 3], [1, 3, 4], [-1, 1, 2], [0, 1, 2]])
def test_discovery_rejects_duplicate_gapped_or_nonpositive_unified_ranks(tmp_path, ranks):
    release = _sealed_unified_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", count=3
    )
    selected = pd.read_csv(release / UNIFIED_OUTPUT_FILENAMES["top20"], dtype=str)
    selected["final_rank"] = ranks
    _rewrite_csv(release, UNIFIED_OUTPUT_FILENAMES, "top20", selected)

    with pytest.raises(ValueError, match="no valid sealed"):
        _discover_snapshots(tmp_path, "2026-07-29")


def test_discovery_normalizes_unified_rows_by_final_rank(tmp_path):
    release = _sealed_unified_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", count=3
    )
    selected = pd.read_csv(release / UNIFIED_OUTPUT_FILENAMES["top20"], dtype=str)
    selected = selected.iloc[[2, 0, 1]].reset_index(drop=True)
    _rewrite_csv(release, UNIFIED_OUTPUT_FILENAMES, "top20", selected)

    snapshots, _ = _discover_snapshots(tmp_path, "2026-07-29")

    assert snapshots["asset_id"].tolist() == ["U01", "U02", "U03"]
    assert snapshots["snapshot_rank"].tolist() == [1, 2, 3]


@pytest.mark.parametrize("ranks", [[1, 1], [1, 3], [0, 1], [-1, 1]])
def test_discovery_rejects_invalid_legacy_bucket_rank_sequence(tmp_path, ranks):
    release = _sealed_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    expected = pd.read_csv(release / LEGACY_OUTPUT_FILENAMES["expected"], dtype=str)
    duplicate = expected.iloc[[0, 0]].copy()
    duplicate["asset_id"] = ["A", "B"]
    duplicate["stock_code"] = ["000001", "000002"]
    duplicate["bucket_rank"] = ranks
    scores = pd.read_csv(release / LEGACY_OUTPUT_FILENAMES["scores"], dtype=str)
    scores = pd.concat([scores, duplicate.iloc[[1]]], ignore_index=True)
    evidence = duplicate.loc[:, ["asset_id", "stock_code", "repair_bucket"]]
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "expected", duplicate)
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "scores", scores)
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "evidence", evidence)

    with pytest.raises(ValueError, match="no valid sealed"):
        _discover_snapshots(tmp_path, "2026-07-29")


def test_discovery_normalizes_legacy_rows_by_bucket_rank(tmp_path):
    release = _sealed_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    expected = pd.read_csv(release / LEGACY_OUTPUT_FILENAMES["expected"], dtype=str)
    second = expected.copy()
    second["asset_id"] = "B"
    second["stock_code"] = "000002"
    expected = pd.concat([second.assign(bucket_rank="2"), expected.assign(bucket_rank="1")])
    scores = pd.read_csv(release / LEGACY_OUTPUT_FILENAMES["scores"], dtype=str)
    scores = pd.concat([scores, second], ignore_index=True)
    evidence = pd.read_csv(release / LEGACY_OUTPUT_FILENAMES["evidence"], dtype=str)
    evidence = pd.concat(
        [evidence, second.loc[:, ["asset_id", "stock_code", "repair_bucket"]]],
        ignore_index=True,
    )
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "expected", expected)
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "scores", scores)
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "evidence", evidence)

    snapshots, _ = _discover_snapshots(tmp_path, "2026-07-29")

    assert snapshots["asset_id"].tolist() == ["A", "B"]
    assert snapshots["snapshot_rank"].tolist() == [1, 2]


@pytest.mark.parametrize("mutation", ["duplicate", "empty_asset", "empty_subindustry"])
def test_discovery_rejects_invalid_scores_membership(tmp_path, mutation):
    release = _sealed_unified_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", count=2
    )
    scores = pd.read_csv(release / UNIFIED_OUTPUT_FILENAMES["scores"], dtype=str)
    if mutation == "duplicate":
        scores = pd.concat([scores, scores.iloc[[0]]], ignore_index=True)
    elif mutation == "empty_asset":
        scores.loc[0, "asset_id"] = ""
    else:
        scores.loc[0, "consumer_subindustry"] = ""
    _rewrite_csv(release, UNIFIED_OUTPUT_FILENAMES, "scores", scores)

    with pytest.raises(ValueError, match="no valid sealed"):
        _discover_snapshots(tmp_path, "2026-07-29")


def test_discovery_rejects_selected_scores_subindustry_mismatch(tmp_path):
    release = _sealed_unified_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", count=2
    )
    scores = pd.read_csv(release / UNIFIED_OUTPUT_FILENAMES["scores"], dtype=str)
    scores.loc[scores["asset_id"].eq("U01"), "consumer_subindustry"] = "retail"
    _rewrite_csv(release, UNIFIED_OUTPUT_FILENAMES, "scores", scores)

    with pytest.raises(ValueError, match="no valid sealed"):
        _discover_snapshots(tmp_path, "2026-07-29")


def test_discovery_rejects_legacy_asset_selected_in_both_buckets(tmp_path):
    release = _sealed_release(
        tmp_path, "consumer-oversold-current", "2026-01-05", "A", "expected_repair"
    )
    expected = pd.read_csv(release / LEGACY_OUTPUT_FILENAMES["expected"], dtype=str)
    early = expected.assign(repair_bucket="early_validation")
    evidence = pd.concat(
        [
            expected.loc[:, ["asset_id", "stock_code", "repair_bucket"]],
            early.loc[:, ["asset_id", "stock_code", "repair_bucket"]],
        ],
        ignore_index=True,
    )
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "early", early)
    _rewrite_csv(release, LEGACY_OUTPUT_FILENAMES, "evidence", evidence)

    with pytest.raises(ValueError, match="no valid sealed"):
        _discover_snapshots(tmp_path, "2026-07-29")


def test_discovery_prefers_current_unified_release_over_legacy_on_same_date(tmp_path):
    week = tmp_path / "snapshots" / "2026-01-05"
    _sealed_release(week, "consumer-oversold-old", "2026-01-05", "OLD", "expected_repair")
    current = _sealed_unified_release(
        week, "consumer-oversold-current", "2026-01-05", count=2
    )
    (week / "current").symlink_to(Path(".releases") / current.name, target_is_directory=True)

    snapshots, _ = _discover_snapshots(tmp_path / "snapshots", "2026-07-29")

    assert set(snapshots["asset_id"]) == {"U01", "U02"}


@pytest.mark.parametrize("invalid", ["status", "count"])
def test_discovery_rejects_unready_or_mismatched_unified_release(tmp_path, invalid):
    release = _sealed_unified_release(
        tmp_path, "consumer-oversold-current", "2026-01-05",
        publication_status="draft" if invalid == "status" else "ready",
    )
    if invalid == "count":
        coverage = release / UNIFIED_OUTPUT_FILENAMES["coverage"]
        release.chmod(0o755)
        coverage.chmod(0o644)
        payload = json.loads(coverage.read_text(encoding="utf-8"))
        payload["final_top_n"] = 19
        coverage.write_text(json.dumps(payload), encoding="utf-8")
        (release / ".manifest.sha256").chmod(0o644)
        _manifest(release, UNIFIED_OUTPUT_FILENAMES)

    with pytest.raises(ValueError, match="no valid sealed"):
        _discover_snapshots(tmp_path, "2026-07-29")


def test_end_date_before_five_day_horizon_leaves_twenty_members_pending(tmp_path):
    snapshots = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-29",
                "asset_id": f"U{rank:02d}",
                "stock_code": f"{rank:06d}",
                "stock_name": f"Unified {rank}",
                "consumer_subindustry": "food",
                "repair_bucket": "expected_repair" if rank % 2 else "early_validation",
                "snapshot_rank": rank,
            }
            for rank in range(1, 21)
        ]
    )
    bars = pd.DataFrame(
        [
            ["2026-07-29", row.asset_id, "food", "2026-07-29", 100.0]
            for row in snapshots.itertuples()
        ],
        columns=["snapshot_trade_date", "asset_id", "consumer_subindustry", "trade_date", "close"],
    )

    detail = evaluate_consumer_oversold_snapshots(snapshots, bars)["detail"]

    assert len(detail) == 40
    assert set(detail["horizon"]) == {5, 20}
    assert detail["evaluation_status"].eq("pending").all()


def test_db_loader_uses_hfq_and_strict_end_date(monkeypatch):
    captured = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_fetch_all(conn, sql, params):
        captured.update(sql=sql, params=params)
        return [
            {"asset_id": "A", "trade_date": "2026-01-05", "close": 100.0},
            {"asset_id": "A", "trade_date": "2026-08-01", "close": 999.0},
        ]

    monkeypatch.setattr("stock_research.consumer_oversold.evaluation.connect", lambda service: Connection())
    monkeypatch.setattr("stock_research.consumer_oversold.evaluation.fetch_all", fake_fetch_all)

    result = _load_evaluation_bars(
        asset_ids=["A"], start_date="2026-01-05", end_date="2026-07-30", service="test"
    )

    assert "adjust_type = 'hfq'" in captured["sql"]
    assert captured["params"] == ["2026-01-05", "2026-07-30", ["A"]]
    assert result["trade_date"].tolist() == ["2026-01-05"]


def test_run_atomically_writes_safe_read_only_artifacts(tmp_path, monkeypatch):
    week = tmp_path / "snapshots" / "2026-01-05"
    release = _sealed_release(
        week,
        "consumer-oversold-current",
        "2026-01-05",
        "A",
        "expected_repair",
        stock_name="=cmd",
    )
    (week / "current").symlink_to(Path(".releases") / release.name, target_is_directory=True)
    raw_bars = _bars().drop(columns=["snapshot_trade_date", "consumer_subindustry"])
    monkeypatch.setattr(
        "stock_research.consumer_oversold.evaluation._load_evaluation_bars",
        lambda **kwargs: raw_bars,
    )

    result = run_consumer_oversold_evaluation(
        snapshots_root=tmp_path / "snapshots",
        end_date="2026-07-30",
        output_dir=tmp_path / "evaluation",
        service="test",
    )

    assert set(result["paths"]) == set(EVALUATION_FILENAMES)
    assert (tmp_path / "evaluation" / "current").is_symlink()
    release = (tmp_path / "evaluation" / "current").resolve()
    manifest = release / ".manifest.sha256"
    assert stat.S_IMODE(release.stat().st_mode) == 0o555
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o444
    manifest_entries = {
        filename: digest
        for digest, filename in (
            line.split("  ", 1)
            for line in manifest.read_text(encoding="utf-8").splitlines()
        )
    }
    assert set(manifest_entries) == set(EVALUATION_FILENAMES.values())
    for path in result["paths"].values():
        artifact = Path(path)
        assert artifact.exists()
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o444
        assert manifest_entries[artifact.name] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert "前瞻评估" in Path(result["paths"]["report"]).read_text(encoding="utf-8")
    detail = pd.read_csv(result["paths"]["detail"])
    assert detail.loc[0, "stock_name"] == "'=cmd"


def _fail_first_output_dir_fsync(monkeypatch, output_dir: Path):
    import stock_research.consumer_oversold.evaluation as evaluation

    real_fsync = evaluation._fsync_dir
    failed = False

    def fail_once(path):
        nonlocal failed
        if Path(path) == output_dir and not failed:
            failed = True
            raise OSError("post-switch fsync failed")
        return real_fsync(path)

    monkeypatch.setattr(evaluation, "_fsync_dir", fail_once)


def test_post_switch_fsync_failure_restores_existing_current(tmp_path, monkeypatch):
    output_dir = tmp_path / "evaluation"
    detail = pd.DataFrame([{"asset_id": "old"}])
    summary = pd.DataFrame([{"completed_count": 1}])
    _publish(output_dir, detail, summary, "old report\n")
    old_target = os.readlink(output_dir / "current")
    _fail_first_output_dir_fsync(monkeypatch, output_dir)

    with pytest.raises(OSError, match="post-switch fsync failed"):
        _publish(
            output_dir,
            pd.DataFrame([{"asset_id": "new"}]),
            summary,
            "new report\n",
        )

    assert os.readlink(output_dir / "current") == old_target
    releases = [
        path
        for path in (output_dir / ".releases").iterdir()
        if path.name.startswith("consumer-oversold-evaluation-")
    ]
    assert len(releases) == 1
    assert not list(output_dir.glob(".consumer-oversold-evaluation-current-*"))


def test_post_switch_fsync_failure_removes_first_current(tmp_path, monkeypatch):
    output_dir = tmp_path / "evaluation"
    output_dir.mkdir()
    _fail_first_output_dir_fsync(monkeypatch, output_dir)

    with pytest.raises(OSError, match="post-switch fsync failed"):
        _publish(
            output_dir,
            pd.DataFrame([{"asset_id": "new"}]),
            pd.DataFrame([{"completed_count": 1}]),
            "new report\n",
        )

    assert not (output_dir / "current").exists()
    assert not list((output_dir / ".releases").glob("consumer-oversold-evaluation-*"))
    assert not list(output_dir.glob(".consumer-oversold-evaluation-current-*"))


def test_publish_locks_before_observing_current_for_failure_rollback(tmp_path, monkeypatch):
    import stock_research.consumer_oversold.evaluation as evaluation

    output_dir = tmp_path / "evaluation"
    summary = pd.DataFrame([{"completed_count": 1}])
    _publish(output_dir, pd.DataFrame([{"asset_id": "old"}]), summary, "old\n")
    old_target = os.readlink(output_dir / "current")
    _publish(output_dir, pd.DataFrame([{"asset_id": "winner"}]), summary, "winner\n")
    winner_target = os.readlink(output_dir / "current")
    replacement = output_dir / ".reset-current"
    replacement.symlink_to(old_target)
    os.replace(replacement, output_dir / "current")

    lock_calls = []

    def fake_flock(fd, operation):
        lock_calls.append(operation)
        if operation == evaluation.fcntl.LOCK_EX:
            concurrent = output_dir / ".concurrent-current"
            concurrent.symlink_to(winner_target)
            os.replace(concurrent, output_dir / "current")

    monkeypatch.setattr(evaluation.fcntl, "flock", fake_flock)
    _fail_first_output_dir_fsync(monkeypatch, output_dir)

    with pytest.raises(OSError, match="post-switch fsync failed"):
        _publish(output_dir, pd.DataFrame([{"asset_id": "failed"}]), summary, "failed\n")

    assert lock_calls == [evaluation.fcntl.LOCK_EX, evaluation.fcntl.LOCK_UN]
    assert os.readlink(output_dir / "current") == winner_target
