from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from stock_research import strategy_publication_artifacts as artifacts
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
)


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "equity": pd.DataFrame([{"trade_date": "2026-07-18", "equity": 1.01}]),
        "positions": pd.DataFrame([{"trade_date": "2026-07-18", "asset_id": "CN:SH:600000"}]),
        "trades": pd.DataFrame([{"trade_date": "2026-07-18", "asset_id": "CN:SH:600000"}]),
        "review": pd.DataFrame([{"trade_date": "2026-07-18", "asset_id": "CN:SH:600000"}]),
    }


def _write(tmp_path, **overrides):
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    kwargs = {
        "output_dir": tmp_path,
        "strategy_id": "mid_trend",
        "run_id": "strategy/eod retry #1",
        "started_at": datetime(2026, 7, 18, 8, 9, 10, tzinfo=timezone.utc),
        "publication_identity": identity,
        "frames": _frames(),
        "summary": {"total_return": 0.01, "publication_identity": identity},
        "config": {"top_n": 5},
        "compatibility_destinations": {
            name: tmp_path / f"strategy_mid_trend_{name}.csv"
            for name in ("equity", "positions", "trades", "review")
        },
    }
    kwargs.update(overrides)
    return artifacts.write_strategy_publication_artifacts(**kwargs)


def test_writer_creates_immutable_version_hashes_and_compatibility_mirrors(tmp_path):
    first = _write(tmp_path)
    second = _write(tmp_path)

    assert first["publish_id"] != second["publish_id"]
    assert first["version_dir"] != second["version_dir"]
    assert first["version_dir"].is_dir()
    assert second["version_dir"].is_dir()
    assert set(path.name for path in first["version_dir"].iterdir()) == {
        "equity.csv",
        "positions.csv",
        "trades.csv",
        "review.csv",
        "summary.json",
        "publication_manifest.json",
    }

    manifest = json.loads(first["publication_manifest_path"].read_text(encoding="utf-8"))
    assert manifest["artifact_version"] == artifacts.ARTIFACT_VERSION
    assert manifest["publish_id"] == first["publish_id"]
    assert manifest["publication_identity"] == first["publication_identity"]
    assert manifest["config"] == {"top_n": 5}
    assert first["output_paths"]["publication_manifest_path"] == first["publication_manifest_path"]
    for name in ("equity", "positions", "trades", "review", "summary"):
        path = first["output_paths"][f"{name}_path"]
        expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        assert first["file_hashes"][name] == expected_hash
        assert manifest["files"][name]["sha256"] == expected_hash
        assert manifest["files"][name]["relative_path"] == path.name
        assert manifest["files"][name]["absolute_path"] == str(path.resolve())

    persisted_summary = json.loads(first["output_paths"]["summary_path"].read_text(encoding="utf-8"))
    assert persisted_summary["artifact_version"] == artifacts.ARTIFACT_VERSION
    assert persisted_summary["publication_identity"] == first["publication_identity"]
    for name in ("equity", "positions", "trades", "review"):
        mirror = tmp_path / f"strategy_mid_trend_{name}.csv"
        assert mirror.read_bytes() == second["output_paths"][f"{name}_path"].read_bytes()


def test_failed_version_write_leaves_no_final_version_or_mirrors(tmp_path, monkeypatch):
    original = artifacts._write_frame

    def fail_on_trades(frame, path):
        if path.name == "trades.csv":
            raise OSError("disk full")
        return original(frame, path)

    monkeypatch.setattr(artifacts, "_write_frame", fail_on_trades)

    with pytest.raises(OSError, match="disk full"):
        _write(tmp_path)

    strategy_root = tmp_path / "strategy_runs" / "mid_trend"
    assert not strategy_root.exists() or not list(strategy_root.iterdir())
    assert not list(tmp_path.glob("strategy_mid_trend_*.csv"))


def test_invalid_mirror_destination_is_rejected_before_version_publication(tmp_path):
    with pytest.raises(ValueError, match="compatibility"):
        _write(
            tmp_path,
            compatibility_destinations={
                "equity": tmp_path / "equity.csv",
                "unknown": tmp_path / "unknown.csv",
            },
        )

    assert not (tmp_path / "strategy_runs").exists()


def test_mirror_staging_failure_leaves_all_existing_roots_unchanged(tmp_path, monkeypatch):
    mirrors = {
        name: tmp_path / f"strategy_mid_trend_{name}.csv"
        for name in ("equity", "positions", "trades", "review")
    }
    for name, path in mirrors.items():
        path.write_bytes(f"old-{name}".encode())
    original = artifacts._copy_file

    def fail_positions(source, destination):
        if source.name == "positions.csv":
            raise OSError("stage copy failed")
        return original(source, destination)

    monkeypatch.setattr(artifacts, "_copy_file", fail_positions)

    with pytest.raises(OSError, match="stage copy failed"):
        _write(tmp_path, compatibility_destinations=mirrors)

    assert {name: path.read_bytes() for name, path in mirrors.items()} == {
        name: f"old-{name}".encode() for name in mirrors
    }
    assert not list(tmp_path.glob(".*.stage-*"))
    assert not list(tmp_path.glob(".*.backup-*"))


def test_mid_replacement_failure_rolls_back_entire_mirror_generation(tmp_path, monkeypatch):
    mirrors = {
        name: tmp_path / f"strategy_mid_trend_{name}.csv"
        for name in ("equity", "positions", "trades", "review")
    }
    for name in ("positions", "trades", "review"):
        mirrors[name].write_bytes(f"old-{name}".encode())
    original = artifacts._replace_mirror

    def fail_trades(source, destination):
        if destination == mirrors["trades"]:
            raise OSError("replace failed")
        return original(source, destination)

    monkeypatch.setattr(artifacts, "_replace_mirror", fail_trades)

    with pytest.raises(OSError, match="replace failed"):
        _write(tmp_path, compatibility_destinations=mirrors)

    assert not mirrors["equity"].exists()
    assert {name: mirrors[name].read_bytes() for name in ("positions", "trades", "review")} == {
        name: f"old-{name}".encode() for name in ("positions", "trades", "review")
    }
    assert not list(tmp_path.glob(".*.stage-*"))
    assert not list(tmp_path.glob(".*.backup-*"))
