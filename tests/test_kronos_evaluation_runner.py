from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from stock_research.kronos_evaluation_types import (
    KronosEvaluationConfig,
    RollingSnapshot,
    canonical_json_fingerprint,
)
from stock_research.kronos_evaluation_runner import (
    build_report,
    prepare_experiment,
    run_model,
)


def make_snapshot(asset_id: str, *, close_offset: float = 0.0) -> RollingSnapshot:
    history = [
        {
            "timestamp": "2025-01-01",
            "open": 99.0 + close_offset,
            "high": 101.0 + close_offset,
            "low": 98.0 + close_offset,
            "close": 100.0 + close_offset,
            "volume": 1_000.0,
            "amount": 100_000.0,
        },
        {
            "timestamp": "2025-01-02",
            "open": 100.0 + close_offset,
            "high": 102.0 + close_offset,
            "low": 99.0 + close_offset,
            "close": 101.0 + close_offset,
            "volume": 1_001.0,
            "amount": 100_100.0,
        },
        {
            "timestamp": "2025-01-03",
            "open": 101.0 + close_offset,
            "high": 103.0 + close_offset,
            "low": 100.0 + close_offset,
            "close": 102.0 + close_offset,
            "volume": 1_002.0,
            "amount": 100_200.0,
        },
    ]
    realized = [
        {
            "timestamp": "2025-01-04",
            "open": 102.0 + close_offset,
            "high": 104.0 + close_offset,
            "low": 101.0 + close_offset,
            "close": 103.0 + close_offset,
            "volume": 1_003.0,
            "amount": 100_300.0,
        },
        {
            "timestamp": "2025-01-05",
            "open": 103.0 + close_offset,
            "high": 105.0 + close_offset,
            "low": 102.0 + close_offset,
            "close": 104.0 + close_offset,
            "volume": 1_004.0,
            "amount": 100_400.0,
        },
    ]
    fingerprint = canonical_json_fingerprint(
        {
            "asset_id": asset_id,
            "origin_date": "2025-01-03",
            "history": history,
        }
    )
    return RollingSnapshot(
        asset_id=asset_id,
        origin_date="2025-01-03",
        history=tuple(history),
        future_timestamps=("2025-01-04", "2025-01-05"),
        realized=tuple(realized),
        input_fingerprint=fingerprint,
        status="ready",
    )


def make_config() -> KronosEvaluationConfig:
    return KronosEvaluationConfig(
        asset_ids=("CN:SH:600418", "CN:SZ:000001"),
        start_date="2025-01-03",
        end_date="2025-01-03",
        input_window=3,
        forecast_horizon=2,
        evaluation_horizons=(1, 2),
        sample_count=2,
        seed=7,
    )


def make_loader(snapshots):
    def loader(config):
        assert tuple(snapshot.asset_id for snapshot in snapshots) == config.asset_ids
        return snapshots, {
            "adjust_type": config.adjust_type,
            "source_table": "test.market_daily_bar",
            "row_count": len(snapshots) * 5,
            "min_date": "2025-01-01",
            "max_date": "2025-01-05",
            "query_timestamp": "2026-08-06T00:00:00+00:00",
        }

    return loader


class FakeClient:
    def __init__(
        self,
        *,
        model: str = "small",
        model_identity: str = "small-v1",
        fail: bool = False,
        malformed_asset: str | None = None,
    ) -> None:
        self.model = model
        self.model_identity = model_identity
        self.weights_identity = f"weights-{model_identity}"
        self.fail = fail
        self.malformed_asset = malformed_asset
        self.calls: list[tuple[str, str, int, int | None]] = []

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "model": self.model,
            "model_identity": self.model_identity,
            "weights_identity": self.weights_identity,
            "device": "cpu",
            "cuda": False,
        }

    def predict_daily(
        self,
        snapshot: RollingSnapshot,
        *,
        model: str,
        sample_count: int,
        seed: int | None,
    ) -> dict[str, Any]:
        self.calls.append((snapshot.key, model, sample_count, seed))
        if self.fail:
            return {
                "status": "error",
                "error": "synthetic model failure",
                "error_category": "model",
                "error_code": "model_error",
            }
        if snapshot.asset_id == self.malformed_asset:
            return {
                "status": "succeeded",
                "sample_count": sample_count,
                "daily": {"p50": [103.0, 104.0]},
            }
        return {
            "status": "succeeded",
            "sample_count": sample_count,
            "daily": {
                "p10": [102.0, 103.0],
                "p50": [103.0, 104.0],
                "p90": [104.0, 105.0],
            },
            "raw_response": {
                "status": "succeeded",
                "model": self.model,
                "model_identity": self.model_identity,
                "weights_identity": self.weights_identity,
                "sample_count": sample_count,
                "daily": {
                    "p10": [102.0, 103.0],
                    "p50": [103.0, 104.0],
                    "p90": [104.0, 105.0],
                },
            },
        }


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_table_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ModuleNotFoundError:
        return read_csv_rows(path)
    try:
        return parquet.read_table(path).to_pylist()
    except Exception:
        return read_csv_rows(path)


@pytest.fixture
def prepared_experiment(tmp_path):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    preparation = prepare_experiment(
        config,
        output_dir=tmp_path,
        snapshot_loader=make_loader(snapshots),
    )
    return tmp_path, config, snapshots, preparation


def test_preparation_writes_frozen_metadata_universe_snapshots_and_empty_artifacts(
    prepared_experiment,
):
    output_dir, config, snapshots, result = prepared_experiment

    assert result.snapshot_count == 2
    assert (output_dir / "experiment.json").exists()
    assert (output_dir / "universe.csv").exists()
    assert (output_dir / "run_manifest.csv").exists()
    assert (output_dir / "forecast_bars.parquet").exists()
    assert (output_dir / "realized_bars.parquet").exists()
    assert sorted(path.name for path in (output_dir / "input_snapshots").glob("*.json")) == [
        "CN:SH:600418__2025-01-03.json",
        "CN:SZ:000001__2025-01-03.json",
    ]

    metadata = json.loads((output_dir / "experiment.json").read_text(encoding="utf-8"))
    assert metadata["config"]["sample_count"] == config.sample_count
    assert metadata["universe"] == list(config.asset_ids)
    assert metadata["snapshot_count"] == len(snapshots)
    assert [item["key"] for item in metadata["snapshot_fingerprints"]] == [
        snapshot.key for snapshot in snapshots
    ]
    assert [item["input_fingerprint"] for item in metadata["snapshot_fingerprints"]] == [
        snapshot.input_fingerprint for snapshot in snapshots
    ]
    assert read_csv_rows(output_dir / "universe.csv")[0]["asset_id"] == config.asset_ids[0]
    assert all(
        row["input_fingerprint"] in {snapshot.input_fingerprint for snapshot in snapshots}
        for row in read_csv_rows(output_dir / "run_manifest.csv")
    )


def test_artifact_replacement_is_atomic_and_leaves_no_temp_files(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient()

    first = run_model(config, model="small", output_dir=output_dir, client=client)
    first_manifest = (output_dir / "run_manifest.csv").read_bytes()
    client.model_identity = "small-v2"
    client.weights_identity = "weights-small-v2"
    second = run_model(config, model="small", output_dir=output_dir, client=client)

    assert first.attempted_count == second.attempted_count == 2
    assert (output_dir / "run_manifest.csv").read_bytes() != first_manifest
    assert not list(output_dir.rglob("*.tmp"))
    assert not [path for path in output_dir.rglob(".*") if path.name not in {".", ".."}]


def test_prediction_persists_rows_and_manifest_after_each_attempt(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient()

    result = run_model(config, model="small", output_dir=output_dir, client=client)

    assert result.attempted_count == 2
    assert len(client.calls) == 2
    manifest = read_csv_rows(output_dir / "run_manifest.csv")
    small_rows = [row for row in manifest if row["model"] == "small"]
    assert {row["status"] for row in small_rows} == {"success"}
    assert all(row["forecast_artifact"] == "forecast_bars.parquet" for row in small_rows)
    assert all(row["realized_artifact"] == "realized_bars.parquet" for row in small_rows)
    assert all(json.loads(row["raw_response_json"])["status"] == "succeeded" for row in small_rows)
    assert len(read_table_rows(output_dir / "forecast_bars.parquet")) == 4
    assert len(read_table_rows(output_dir / "realized_bars.parquet")) == 4


def test_resume_skips_completed_keys_with_matching_fingerprint_identity_and_parameters(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient()
    run_model(config, model="small", output_dir=output_dir, client=first_client)

    resume_client = FakeClient()
    result = run_model(config, model="small", output_dir=output_dir, client=resume_client)

    assert result.cache_hit_count == 2
    assert result.attempted_count == 0
    assert resume_client.calls == []
    assert all(row["cache_hit"] == "true" for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small")


def test_changed_model_identity_forces_rerun(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient()
    run_model(config, model="small", output_dir=output_dir, client=first_client)

    changed_client = FakeClient(model_identity="small-v2")
    result = run_model(config, model="small", output_dir=output_dir, client=changed_client)

    assert result.attempted_count == 2
    assert result.cache_hit_count == 0
    assert len(changed_client.calls) == 2
    assert {row["model_identity"] for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"} == {"small-v2"}


def test_changed_frozen_input_fingerprint_forces_rerun(prepared_experiment):
    output_dir, config, snapshots, _ = prepared_experiment
    first_client = FakeClient()
    run_model(config, model="small", output_dir=output_dir, client=first_client)

    snapshot_path = output_dir / "input_snapshots" / "CN:SH:600418__2025-01-03.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["history"][0]["close"] += 0.25
    payload["input_fingerprint"] = canonical_json_fingerprint(
        {
            "asset_id": payload["asset_id"],
            "origin_date": payload["origin_date"],
            "history": payload["history"],
        }
    )
    snapshot_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    changed_client = FakeClient()
    result = run_model(config, model="small", output_dir=output_dir, client=changed_client)

    assert result.attempted_count == 1
    assert len(changed_client.calls) == 1
    assert changed_client.calls[0][0] == snapshots[0].key
    assert snapshots[0].input_fingerprint != payload["input_fingerprint"]


def test_small_model_error_remains_visible_and_does_not_fallback_to_base(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    failing_small = FakeClient(fail=True)

    small_result = run_model(config, model="small", output_dir=output_dir, client=failing_small)
    small_rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]

    assert small_result.attempted_count == 2
    assert len(failing_small.calls) == 2
    assert {row["status"] for row in small_rows} == {"model_error"}
    assert {row["error_category"] for row in small_rows} == {"model"}
    assert {row["error_code"] for row in small_rows} == {"model_error"}

    base_client = FakeClient(model="base", model_identity="base-v1")
    run_model(config, model="base", output_dir=output_dir, client=base_client)
    assert all(call[1] == "base" for call in base_client.calls)
    assert not any(call[1] == "base" for call in failing_small.calls)


def test_malformed_result_is_recorded_and_other_snapshots_continue(prepared_experiment):
    output_dir, config, snapshots, _ = prepared_experiment
    client = FakeClient(malformed_asset=snapshots[0].asset_id)

    result = run_model(config, model="small", output_dir=output_dir, client=client)

    assert result.attempted_count == 2
    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    statuses = {row["asset_id"]: row["status"] for row in rows}
    assert statuses[snapshots[0].asset_id] == "protocol_error"
    assert statuses[snapshots[1].asset_id] == "success"
    assert len(read_table_rows(output_dir / "forecast_bars.parquet")) == 2


def test_report_combines_models_metrics_baselines_coverage_latency_and_fixed_conclusion(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())
    run_model(
        config,
        model="base",
        output_dir=output_dir,
        client=FakeClient(model="base", model_identity="base-v1"),
    )

    summary = build_report(output_dir=output_dir)

    assert summary["conclusion"] == "not_proven"
    assert summary["counts"]["runs"] == 4
    assert summary["counts"]["successful_runs"] == 4
    assert set(summary["paths"]) == {
        "metrics_by_stock_horizon",
        "metrics_by_model_horizon",
        "model_comparison",
        "report",
    }
    assert all(Path(path).exists() for path in summary["paths"].values())
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "persistence" in report
    assert "drift" in report
    assert "base-minus-small" in report
    assert "coverage" in report.lower()
    assert "latency" in report.lower()
    assert "not_proven" in report


def test_frozen_snapshot_json_is_not_mutated_by_prediction(prepared_experiment):
    output_dir, config, snapshots, _ = prepared_experiment
    before = {
        path.name: path.read_bytes()
        for path in (output_dir / "input_snapshots").glob("*.json")
    }

    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    after = {
        path.name: path.read_bytes()
        for path in (output_dir / "input_snapshots").glob("*.json")
    }
    assert after == before
    assert all(snapshot.history[-1]["close"] < 200.0 for snapshot in snapshots)


def test_repeated_deterministic_inputs_and_artifacts_have_stable_serialization(tmp_path):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    output_dirs = [tmp_path / "first", tmp_path / "second"]
    for output_dir in output_dirs:
        prepare_experiment(
            config,
            output_dir=output_dir,
            snapshot_loader=make_loader(snapshots),
        )
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    for filename in (
        "universe.csv",
        "forecast_bars.parquet",
        "realized_bars.parquet",
    ):
        assert (output_dirs[0] / filename).read_bytes() == (output_dirs[1] / filename).read_bytes()
    assert sorted(
        path.read_bytes() for path in (output_dirs[0] / "input_snapshots").glob("*.json")
    ) == sorted(
        path.read_bytes() for path in (output_dirs[1] / "input_snapshots").glob("*.json")
    )

    first_metadata = json.loads((output_dirs[0] / "experiment.json").read_text(encoding="utf-8"))
    second_metadata = json.loads((output_dirs[1] / "experiment.json").read_text(encoding="utf-8"))
    first_metadata.pop("created_at")
    second_metadata.pop("created_at")
    assert first_metadata == second_metadata
