from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import OUTPUT_FILENAMES
from stock_research.consumer_oversold.evaluation import (
    EVALUATION_FILENAMES,
    _load_evaluation_bars,
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


def _manifest(release: Path) -> None:
    lines = []
    for filename in sorted(OUTPUT_FILENAMES.values()):
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
            }
        ]
    )
    empty = selected.iloc[0:0].copy()
    selected.to_csv(
        release / OUTPUT_FILENAMES["expected" if bucket == "expected_repair" else "early"],
        index=False,
    )
    empty.to_csv(
        release / OUTPUT_FILENAMES["early" if bucket == "expected_repair" else "expected"],
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
    scores.to_csv(release / OUTPUT_FILENAMES["scores"], index=False)
    pd.DataFrame(columns=["asset_id", "exclusion_reasons"]).to_csv(
        release / OUTPUT_FILENAMES["exclusions"], index=False
    )
    evidence = selected.loc[:, ["asset_id", "stock_code", "repair_bucket"]].copy()
    evidence.to_csv(release / OUTPUT_FILENAMES["evidence"], index=False)
    (release / OUTPUT_FILENAMES["coverage"]).write_text(
        json.dumps({"trade_date": trade_date}), encoding="utf-8"
    )
    (release / OUTPUT_FILENAMES["report"]).write_text("weekly report\n", encoding="utf-8")
    _manifest(release)
    return release


def test_forward_evaluation_computes_absolute_excess_and_path_drawdown():
    result = evaluate_consumer_oversold_snapshots(_snapshots(), _bars())

    row = result["detail"].query("asset_id == 'A' and horizon == 20").iloc[0]
    assert row["repair_bucket"] == "expected_repair"
    assert row["evaluation_status"] == "completed"
    assert row["forward_return"] == pytest.approx(0.20)
    assert row["industry_forward_return"] == pytest.approx(0.05)
    assert row["excess_return"] == pytest.approx(0.15)
    assert row["path_max_drawdown"] == pytest.approx(-0.20)
    assert bool(row["excess_win"])


def test_forward_evaluation_keeps_incomplete_horizons_pending_and_summarizes():
    result = evaluate_consumer_oversold_snapshots(_snapshots(), _bars(periods=61))

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


def test_run_prefers_current_sealed_release_and_deduplicates_trade_date(tmp_path, monkeypatch):
    week = tmp_path / "snapshots" / "2026-01-05"
    old = _sealed_release(week, "consumer-oversold-old", "2026-01-05", "OLD", "expected_repair")
    current = _sealed_release(week, "consumer-oversold-current", "2026-01-05", "A", "expected_repair")
    (week / "current").symlink_to(Path(".releases") / current.name, target_is_directory=True)
    loose = week / OUTPUT_FILENAMES["expected"]
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
    evidence = release / OUTPUT_FILENAMES["evidence"]
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
    with pytest.raises(ValueError, match="must not overlap"):
        run_consumer_oversold_evaluation(
            snapshots_root=tmp_path / "snapshots",
            end_date="2026-07-30",
            output_dir=tmp_path / "snapshots" / "evaluation",
            service="test",
        )


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
    for path in result["paths"].values():
        artifact = Path(path)
        assert artifact.exists()
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o444
    assert "前瞻评估" in Path(result["paths"]["report"]).read_text(encoding="utf-8")
    detail = pd.read_csv(result["paths"]["detail"])
    assert detail.loc[0, "stock_name"] == "'=cmd"
