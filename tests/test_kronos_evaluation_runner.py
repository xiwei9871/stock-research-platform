from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import time
import types
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")
    requests_stub.Session = object
    requests_stub.RequestException = Exception
    requests_stub.Timeout = TimeoutError
    sys.modules["requests"] = requests_stub

try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    psycopg_stub = types.ModuleType("psycopg")
    psycopg_stub.Connection = object
    psycopg_stub.connect = lambda *args, **kwargs: None
    psycopg_rows_stub = types.ModuleType("psycopg.rows")
    psycopg_rows_stub.dict_row = object()
    psycopg_stub.rows = psycopg_rows_stub
    sys.modules["psycopg"] = psycopg_stub
    sys.modules["psycopg.rows"] = psycopg_rows_stub

from stock_research import kronos_evaluation_runner as runner
from stock_research.kronos_evaluation_types import (
    KronosEvaluationConfig,
    RollingSnapshot,
    canonical_json_fingerprint,
    snapshot_to_json_payload,
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


def make_long_snapshot(
    asset_id: str,
    *,
    status: str,
    realized_count: int,
) -> RollingSnapshot:
    base = make_snapshot(asset_id)
    future_timestamps = tuple(f"2025-01-{day:02d}" for day in range(4, 14))
    realized = tuple(
        {
            "timestamp": timestamp,
            "open": 102.0 + index,
            "high": 104.0 + index,
            "low": 101.0 + index,
            "close": 103.0 + index,
            "volume": 1_003.0 + index,
            "amount": 100_300.0 + index,
        }
        for index, timestamp in enumerate(future_timestamps[:realized_count])
    )
    return replace(
        base,
        future_timestamps=future_timestamps,
        realized=realized,
        status=status,
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


def test_config_from_payload_accepts_legacy_metadata_without_new_fields():
    config = make_config()
    payload = {
        field.name: runner._jsonable(getattr(config, field.name))
        for field in runner.fields(config)
        if field.name
        not in {
            "frequency",
            "primary_horizon",
            "include_latest_forecast",
            "fallback",
            "experiment_id",
            "config_fingerprint",
        }
    }

    restored = runner._config_from_payload(payload)

    assert restored.frequency == "1d"
    assert restored.primary_horizon == 1
    assert restored.include_latest_forecast is False
    assert restored.fallback is False
    assert restored.experiment_id == ""
    assert restored.config_fingerprint == ""


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
        health_weights_identity: str | None = None,
        omit_health_weights_identity: bool = False,
        fail: bool = False,
        malformed_asset: str | None = None,
        health_failure: bool = False,
        response_model: str | None = None,
        response_model_identity: str | None = None,
        response_weights_identity: str | None = None,
        include_representative_path: bool = True,
        include_response_identity: bool = True,
        response_result: dict[str, Any] | None = None,
        response_daily_overrides: dict[str, Any] | None = None,
        response_raw_overrides: dict[str, Any] | None = None,
        response_raw_collision: bool = False,
        omit_health_identity: bool = False,
    ) -> None:
        self.model = model
        self.model_identity = model_identity
        self.weights_identity = health_weights_identity or f"weights-{model_identity}"
        self.omit_health_weights_identity = omit_health_weights_identity
        self.fail = fail
        self.malformed_asset = malformed_asset
        self.health_failure = health_failure
        self.response_model = response_model
        self.response_model_identity = response_model_identity
        self.response_weights_identity = response_weights_identity
        self.include_representative_path = include_representative_path
        self.include_response_identity = include_response_identity
        self.response_result = response_result
        self.response_daily_overrides = response_daily_overrides
        self.response_raw_overrides = response_raw_overrides
        self.response_raw_collision = response_raw_collision
        self.omit_health_identity = omit_health_identity
        self.calls: list[tuple[str, str, int, int | None]] = []

    def health(self) -> dict[str, Any]:
        if self.health_failure:
            raise RuntimeError("health unavailable")
        health = {
            "status": "ok",
            "device": "cpu",
            "cuda": False,
        }
        if not self.omit_health_identity:
            health.update(
                {
                    "model": self.model,
                    "model_identity": self.model_identity,
                }
            )
            if not self.omit_health_weights_identity:
                health["weights_identity"] = self.weights_identity
        return health

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
        representative_path = [
            {
                "timestamp": timestamp,
                "open": 102.0 + index,
                "high": 104.0 + index,
                "low": 101.0 + index,
                "close": 103.0 + index,
                "volume": 1_003.0 + index,
                "amount": 100_300.0 + index,
            }
            for index, timestamp in enumerate(snapshot.future_timestamps)
        ]
        daily = {
            "p10": [102.0 + index for index in range(len(snapshot.future_timestamps))],
            "p50": [103.0 + index for index in range(len(snapshot.future_timestamps))],
            "p90": [104.0 + index for index in range(len(snapshot.future_timestamps))],
        }
        if self.include_representative_path:
            daily["representative_path"] = representative_path
        if self.response_daily_overrides:
            daily.update(self.response_daily_overrides)
        response_model = self.response_model or self.model
        response_model_identity = self.response_model_identity or self.model_identity
        response_weights_identity = (
            self.response_weights_identity or self.weights_identity
        )
        response = {
            "status": "succeeded",
            "sample_count": sample_count,
            "daily": daily,
            "raw_response": {
                "status": "succeeded",
                "sample_count": sample_count,
                "daily": daily,
            },
        }
        if self.include_response_identity:
            response.update(
                {
                    "model": response_model,
                    "model_identity": response_model_identity,
                    "weights_identity": response_weights_identity,
                }
            )
            response["raw_response"].update(
                {
                    "model": response_model,
                    "model_identity": response_model_identity,
                    "weights_identity": response_weights_identity,
                }
            )
        if self.response_result is not None:
            response["result"] = self.response_result
        if self.response_raw_overrides:
            response["raw_response"].update(self.response_raw_overrides)
        if self.response_raw_collision:
            complete_response = json.loads(json.dumps(response))
            response["raw_response"] = {"upstream": "nested raw response"}
            response["_kronos_raw_response"] = {"upstream": "reserved upstream"}
            response["__kronos_raw_response"] = {"upstream": "double reserved upstream"}
            response["__kronos_client_raw_response_slot__"] = "__kronos_complete_response__"
            response["__kronos_complete_response__"] = complete_response
        return response


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
    assert all(
        "snapshot_fingerprint" in item
        for item in metadata["snapshot_fingerprints"]
    )


def test_fresh_prepare_rejects_nonempty_output_without_experiment_metadata(
    tmp_path,
):
    output_dir = tmp_path / "nonempty"
    output_dir.mkdir()
    (output_dir / "input_snapshots").mkdir()
    (output_dir / "input_snapshots" / "stale.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="non-empty"):
        prepare_experiment(
            make_config(),
            output_dir=output_dir,
            snapshot_loader=make_loader([make_snapshot("CN:SH:600418")]),
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


def test_prediction_eligible_snapshot_statuses_write_forecasts_and_realized_prefixes(
    tmp_path,
):
    config = replace(
        make_config(),
        asset_ids=("CN:SH:600418", "CN:SZ:000001", "CN:SH:600519"),
    )
    partial_snapshot = make_snapshot("CN:SH:600418")
    snapshots = [
        replace(
            partial_snapshot,
            realized=partial_snapshot.realized[:1],
            status="partial_truth",
        ),
        replace(make_snapshot("CN:SZ:000001"), realized=(), status="forecast_only"),
        replace(make_snapshot("CN:SH:600519"), status="pending_calendar"),
    ]
    prepare_experiment(config, output_dir=tmp_path, snapshot_loader=make_loader(snapshots))

    client = FakeClient()
    result = run_model(config, model="small", output_dir=tmp_path, client=client)

    assert result.attempted_count == 2
    assert result.skipped_count == 1
    assert len(client.calls) == 2
    assert len(read_table_rows(tmp_path / runner.FORECAST_FILENAME)) == 4
    assert len(read_table_rows(tmp_path / runner.REALIZED_FILENAME)) == 1
    manifest = {
        row["snapshot_key"]: row
        for row in read_csv_rows(tmp_path / runner.MANIFEST_FILENAME)
        if row["model"] == "small"
    }
    assert manifest["CN:SH:600418|2025-01-03"]["status"] == "success"
    assert manifest["CN:SZ:000001|2025-01-03"]["status"] == "success"
    assert manifest["CN:SH:600519|2025-01-03"]["status"] == "pending_calendar"


def test_build_report_scores_partial_truth_by_available_horizon_and_preserves_coverage(
    tmp_path,
):
    config = replace(
        make_config(),
        asset_ids=("CN:SH:600418", "CN:SZ:000001", "CN:SH:600519"),
        forecast_horizon=10,
        evaluation_horizons=(1, 3, 5, 10),
    )
    snapshots = [
        make_long_snapshot("CN:SH:600418", status="partial_truth", realized_count=1),
        make_long_snapshot("CN:SZ:000001", status="forecast_only", realized_count=0),
        make_long_snapshot("CN:SH:600519", status="pending_calendar", realized_count=0),
    ]
    prepare_experiment(config, output_dir=tmp_path, snapshot_loader=make_loader(snapshots))
    run_model(config, model="small", output_dir=tmp_path, client=FakeClient())
    run_model(
        config,
        model="base",
        output_dir=tmp_path,
        client=FakeClient(model="base", model_identity="base-v1"),
    )

    summary = build_report(output_dir=tmp_path)
    metric_rows = read_csv_rows(tmp_path / runner.METRICS_BY_STOCK_FILENAME)
    partial_rows = [
        row
        for row in metric_rows
        if row["asset_id"] == "CN:SH:600418" and row["model"] == "small"
    ]
    forecast_only_rows = [
        row
        for row in metric_rows
        if row["asset_id"] == "CN:SZ:000001" and row["model"] == "small"
    ]
    pending_rows = [
        row
        for row in metric_rows
        if row["asset_id"] == "CN:SH:600519" and row["model"] == "small"
    ]

    assert json.loads(
        next(row for row in partial_rows if row["horizon"] == "1")["status_counts_json"]
    ) == {"success": 1}
    assert all(
        json.loads(
            next(row for row in partial_rows if row["horizon"] == horizon)[
                "status_counts_json"
            ]
        )
        == {"pending_truth": 1}
        for horizon in ("3", "5", "10")
    )
    assert all(
        json.loads(row["status_counts_json"]) == {"forecast_only": 1}
        for row in forecast_only_rows
    )
    assert all(
        json.loads(row["status_counts_json"]) == {"pending_calendar": 1}
        for row in pending_rows
    )
    assert all(row["mean_absolute_return_error"] == "" for row in forecast_only_rows)

    coverage = summary["coverage_by_model_horizon"]
    assert all(
        row["successful"] == 2
        for row in coverage
        if row["model"] == "small"
    )
    comparison = next(
        row for row in summary["comparisons"] if row["comparison"] == "base_minus_small"
    )
    assert comparison["paired_row_count"] == 1

    manifest = {
        row["run_key"]: row
        for row in read_csv_rows(tmp_path / runner.MANIFEST_FILENAME)
    }
    forecast_rows = read_table_rows(tmp_path / runner.FORECAST_FILENAME)
    realized_rows = read_table_rows(tmp_path / runner.REALIZED_FILENAME)
    metric_rows = runner._build_metric_rows(
        snapshots,
        manifest,
        forecast_rows,
        realized_rows,
        config.evaluation_horizons,
        runner._config_payload(config),
    )
    partial_small = [
        row
        for row in metric_rows
        if row["asset_id"] == "CN:SH:600418" and row["model"] == "small"
    ]
    assert all(row["primary_horizon"] == 1 for row in partial_small)
    assert next(row for row in partial_small if row["horizon"] == 1)["scored"] is True
    assert all(
        row["scored"] is False
        for row in partial_small
        if row["horizon"] in (3, 5, 10)
    )
    assert all(
        row["status"] == "pending_truth"
        for row in partial_small
        if row["horizon"] in (3, 5, 10)
    )
    assert not any(
        row["model"] in {"persistence", "drift"}
        and row["asset_id"] in {"CN:SZ:000001", "CN:SH:600519"}
        for row in metric_rows
    )
    assert any(
        row["model"] == "persistence"
        and row["asset_id"] == "CN:SH:600418"
        and row["horizon"] == 1
        and row["scored"] is True
        for row in metric_rows
    )

    primary_small = next(
        row for row in summary["primary_coverage"] if row["model"] == "small"
    )
    assert primary_small["total"] == 3
    assert primary_small["scored"] == 1
    assert primary_small["forecast_only"] == 1
    assert primary_small["pending_calendar"] == 1
    assert primary_small["coverage_rate"] == pytest.approx(1 / 3)
    assert summary["pending_counts"]["small"]["pending_truth"] == 0
    assert "forecast_only" in summary["metric_status_counts"]
    assert "pending_calendar" in summary["metric_status_counts"]

    with (tmp_path / runner.METRICS_BY_STOCK_FILENAME).open(
        newline="", encoding="utf-8"
    ) as handle:
        header = next(handle)
    assert header.strip().split(",") == list(runner._METRIC_OUTPUT_COLUMNS)
    report = (tmp_path / runner.REPORT_FILENAME).read_text(encoding="utf-8")
    assert "Primary horizon coverage" in report
    assert "Pending and forecast-only metric counts" in report


def test_runner_accepts_documented_sidecar_files(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    for filename in (
        runner.EXPERIMENT_CONFIG_FILENAME,
        runner.UNIVERSE_SELECTION_FILENAME,
        runner.LATEST_FORECAST_FILENAME,
    ):
        (output_dir / filename).write_text("{}", encoding="utf-8")

    result = run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    assert result.attempted_count == len(config.asset_ids)


def test_non_default_primary_horizon_controls_baseline_and_comparison(tmp_path):
    config = replace(
        make_config(),
        forecast_horizon=2,
        evaluation_horizons=(1, 2),
        primary_horizon=2,
    )
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    prepare_experiment(config, output_dir=tmp_path, snapshot_loader=make_loader(snapshots))
    run_model(config, model="small", output_dir=tmp_path, client=FakeClient())
    run_model(
        config,
        model="base",
        output_dir=tmp_path,
        client=FakeClient(model="base", model_identity="base-v1"),
    )

    summary = build_report(output_dir=tmp_path)
    manifest = {
        row["run_key"]: row
        for row in read_csv_rows(tmp_path / runner.MANIFEST_FILENAME)
    }
    metric_rows = runner._build_metric_rows(
        snapshots,
        manifest,
        read_table_rows(tmp_path / runner.FORECAST_FILENAME),
        read_table_rows(tmp_path / runner.REALIZED_FILENAME),
        config.evaluation_horizons,
        runner._config_payload(config),
    )

    assert all(row["primary_horizon"] == 2 for row in metric_rows)
    assert all(
        row["scored"] is True
        for row in metric_rows
        if row["model"] in {"small", "base", "persistence", "drift"}
    )
    baseline_horizons = {
        row["horizon"]
        for row in metric_rows
        if row["model"] == "persistence"
    }
    assert baseline_horizons == {1, 2}
    comparison = next(
        row for row in summary["comparisons"] if row["comparison"] == "base_minus_small"
    )
    assert comparison["paired_count"] == 2
    assert comparison["paired_row_count"] == 2
    assert next(
        row for row in summary["primary_coverage"] if row["model"] == "small"
    )["horizon"] == 2


def test_existing_experiment_accepts_legacy_config_fields_with_defaults(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    metadata_path = output_dir / runner.EXPERIMENT_FILENAME
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for field_name in (
        "frequency",
        "primary_horizon",
        "include_latest_forecast",
        "fallback",
        "experiment_id",
        "config_fingerprint",
    ):
        metadata["config"].pop(field_name, None)
    immutable = {
        key: value
        for key, value in metadata.items()
        if key not in {"created_at", "experiment_fingerprint"}
    }
    metadata["experiment_fingerprint"] = canonical_json_fingerprint(immutable)
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    result = prepare_experiment(
        config,
        output_dir=output_dir,
        snapshot_loader=make_loader([make_snapshot(asset_id) for asset_id in config.asset_ids]),
    )

    assert result.snapshot_count == len(config.asset_ids)


@pytest.mark.parametrize(
    "changed_config",
    [
        lambda config: replace(config, primary_horizon=2),
        lambda config: replace(config, config_fingerprint="a" * 64),
    ],
)
def test_existing_experiment_rejects_primary_horizon_or_config_fingerprint_change(
    prepared_experiment, changed_config
):
    output_dir, config, _, _ = prepared_experiment

    with pytest.raises(FileExistsError, match="incompatible"):
        prepare_experiment(
            changed_config(config),
            output_dir=output_dir,
            snapshot_loader=make_loader([make_snapshot(asset_id) for asset_id in config.asset_ids]),
        )


def test_resume_skips_completed_keys_with_matching_fingerprint_identity_and_parameters(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient()
    run_model(config, model="small", output_dir=output_dir, client=first_client)
    before_manifest = (output_dir / "run_manifest.csv").read_bytes()

    resume_client = FakeClient()
    result = run_model(config, model="small", output_dir=output_dir, client=resume_client)

    assert result.cache_hit_count == 2
    assert result.attempted_count == 0
    assert resume_client.calls == []
    assert (output_dir / "run_manifest.csv").read_bytes() == before_manifest


def test_health_failure_preserves_completed_rows_and_artifacts_on_resume(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient()
    run_model(config, model="small", output_dir=output_dir, client=first_client)
    before_manifest = (output_dir / "run_manifest.csv").read_bytes()
    before_forecast = (output_dir / "forecast_bars.parquet").read_bytes()
    before_realized = (output_dir / "realized_bars.parquet").read_bytes()

    unavailable_client = FakeClient(health_failure=True)
    result = run_model(
        config,
        model="small",
        output_dir=output_dir,
        client=unavailable_client,
    )

    assert result.cache_hit_count == 2
    assert result.attempted_count == 0
    assert unavailable_client.calls == []
    assert (output_dir / "run_manifest.csv").read_bytes() == before_manifest
    assert (output_dir / "forecast_bars.parquet").read_bytes() == before_forecast
    assert (output_dir / "realized_bars.parquet").read_bytes() == before_realized


@pytest.mark.parametrize("field", ["future_timestamps", "realized"])
def test_tampered_full_snapshot_payload_is_rejected(prepared_experiment, field):
    output_dir, config, _, _ = prepared_experiment
    snapshot_path = output_dir / "input_snapshots" / "CN:SH:600418__2025-01-03.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if field == "future_timestamps":
        payload[field][0] = "2025-01-06"
    else:
        payload[field][0]["close"] += 0.25
    snapshot_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot|fingerprint"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_frozen_snapshot_rejects_unknown_json_keys(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    snapshot_path = output_dir / "input_snapshots" / "CN:SH:600418__2025-01-03.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["unexpected"] = "tampered"
    snapshot_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


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


def test_response_model_identity_mismatch_is_recorded_without_forecast_rows(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient(
        response_model="base",
        response_model_identity="base-v1",
        response_weights_identity="base-v1",
    )

    result = run_model(config, model="small", output_dir=output_dir, client=client)

    assert result.attempted_count == 2
    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"model_error"}
    assert {row["error_category"] for row in rows} == {"model"}
    assert len(read_table_rows(output_dir / "forecast_bars.parquet")) == 0


def test_nested_response_model_conflict_is_recorded_without_success(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient(response_result={"model": "base"})

    result = run_model(config, model="small", output_dir=output_dir, client=client)

    assert result.attempted_count == 2
    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"model_error"}
    assert {row["error_code"] for row in rows} == {"model_identity_mismatch"}


def test_health_and_response_version_mismatch_is_recorded_without_success(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient(
        model_identity="small-v1",
        response_model_identity="small-v2",
    )

    run_model(config, model="small", output_dir=output_dir, client=client)

    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"model_error"}


def test_opaque_weights_identity_is_preserved_as_metadata(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient(response_weights_identity="build-2026-08-06-gpu-a")

    run_model(config, model="small", output_dir=output_dir, client=client)

    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"success"}
    assert {row["weights_identity"] for row in rows} == {"weights-small-v1"}
    assert {row["health_weights_identity"] for row in rows} == {"weights-small-v1"}
    assert {row["response_weights_identity"] for row in rows} == {
        "build-2026-08-06-gpu-a"
    }


def test_response_without_identity_uses_passed_health(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient(include_response_identity=False)

    run_model(config, model="small", output_dir=output_dir, client=client)

    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"success"}


def test_opaque_response_weight_build_id_does_not_break_resume(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient(response_weights_identity="build-2026-08-06-gpu-a")
    run_model(config, model="small", output_dir=output_dir, client=first_client)

    resume_client = FakeClient(response_weights_identity="build-2026-08-06-gpu-b")
    result = run_model(config, model="small", output_dir=output_dir, client=resume_client)

    assert result.cache_hit_count == 2
    assert result.attempted_count == 0
    assert resume_client.calls == []


def test_opaque_response_build_identity_is_audit_metadata_when_family_is_valid(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient(response_model="small", response_model_identity="build-small-2026")

    run_model(config, model="small", output_dir=output_dir, client=client)

    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"success"}
    assert {row["health_model_identity"] for row in rows} == {"small-v1"}
    assert {row["response_model_identity"] for row in rows} == {"build-small-2026"}


def test_family_only_response_identity_resumes_against_versioned_health(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient(
        model_identity="small-v1",
        response_model_identity="small",
    )
    run_model(config, model="small", output_dir=output_dir, client=first_client)

    resume_client = FakeClient(
        model_identity="small-v1",
        response_model_identity="small",
    )
    result = run_model(config, model="small", output_dir=output_dir, client=resume_client)

    assert result.cache_hit_count == 2
    assert result.attempted_count == 0
    assert resume_client.calls == []


def test_changed_frozen_input_fingerprint_is_rejected_as_tampering(prepared_experiment):
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
    with pytest.raises(ValueError, match="experiment|snapshot|fingerprint"):
        run_model(config, model="small", output_dir=output_dir, client=changed_client)

    assert changed_client.calls == []
    assert snapshots[0].input_fingerprint != payload["input_fingerprint"]


def test_run_model_rejects_tampered_experiment_self_fingerprint(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    path = output_dir / "experiment.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["source"]["row_count"] += 1
    path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="experiment fingerprint"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_run_model_rejects_extra_snapshot_file_and_manifest_key(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    extra = make_snapshot("CN:SH:600419")
    extra_path = output_dir / "input_snapshots" / "CN:SH:600419__2025-01-03.json"
    extra_path.write_text(
        json.dumps(snapshot_to_json_payload(extra), sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="snapshot"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    extra_path.unlink()
    manifest_path = output_dir / "run_manifest.csv"
    rows = read_csv_rows(manifest_path)
    rows.append(dict(rows[0], run_key="unexpected|small"))
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="manifest"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_modified_same_count_forecast_artifact_fails_authenticated_generation(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient()
    run_model(config, model="small", output_dir=output_dir, client=first_client)

    import pyarrow as pa
    import pyarrow.parquet as parquet

    forecast_path = output_dir / "forecast_bars.parquet"
    table = parquet.read_table(forecast_path)
    rows = table.to_pylist()
    rows[0]["p50"] += 0.5
    parquet.write_table(pa.Table.from_pylist(rows, schema=table.schema), forecast_path)

    with pytest.raises(ValueError, match="generation|digest|authenticated"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_manifest_tampering_preserving_generation_marker_fails_closed(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    rows = read_csv_rows(output_dir / "run_manifest.csv")
    rows[0]["health_metadata_json"] = '{"tampered":true}'
    with (output_dir / "run_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=runner.MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="generation|digest|authenticated"):
        build_report(output_dir=output_dir)


@pytest.mark.parametrize("mutation", ["forecast", "realized", "delete_forecast", "delete_realized"])
def test_build_report_fails_closed_on_tampered_or_missing_success_artifacts(
    prepared_experiment,
    mutation,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    import pyarrow as pa
    import pyarrow.parquet as parquet

    if mutation == "forecast":
        path = output_dir / "forecast_bars.parquet"
        table = parquet.read_table(path)
        rows = table.to_pylist()
        rows[0]["p50"] += 0.5
        parquet.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    elif mutation == "realized":
        path = output_dir / "realized_bars.parquet"
        table = parquet.read_table(path)
        rows = table.to_pylist()
        rows[0]["close"] += 0.5
        parquet.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    else:
        (output_dir / ("forecast_bars.parquet" if mutation == "delete_forecast" else "realized_bars.parquet")).unlink()

    with pytest.raises((FileNotFoundError, RuntimeError, ValueError), match="artifact|Parquet|fingerprint|generation|schema"):
        build_report(output_dir=output_dir)


def test_partial_commit_recovers_on_next_run_and_retry_publishes_one_generation(
    prepared_experiment,
    monkeypatch,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    original_commit = runner._commit_staged_artifacts

    def partial_commit(staged_paths, final_paths):
        original_commit(staged_paths[:1], final_paths[:1])
        raise OSError("injected commit failure")

    monkeypatch.setattr(runner, "_commit_staged_artifacts", partial_commit)
    with pytest.raises(OSError, match="injected"):
        run_model(
            config,
            model="small",
            output_dir=output_dir,
            client=FakeClient(model_identity="small-v2"),
        )

    monkeypatch.undo()
    retry_client = FakeClient(model_identity="small-v2")
    result = run_model(config, model="small", output_dir=output_dir, client=retry_client)

    assert result.attempted_count == 2
    assert len(retry_client.calls) == 2
    assert not (output_dir / runner.TRANSACTION_FILENAME).exists()


def test_prejournal_backup_failure_publishes_recoverable_plan_and_retry(
    prepared_experiment,
    monkeypatch,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    original_copy = runner._copy_file_durable

    def fail_backup_copy(source, destination):
        if destination.name.endswith(".backup"):
            raise OSError("injected backup copy failure")
        return original_copy(source, destination)

    monkeypatch.setattr(runner, "_copy_file_durable", fail_backup_copy)
    with pytest.raises(OSError, match="backup copy"):
        run_model(
            config,
            model="small",
            output_dir=output_dir,
            client=FakeClient(model_identity="small-v2"),
        )

    transaction_path = output_dir / runner.TRANSACTION_FILENAME
    assert transaction_path.exists()
    journal = json.loads(transaction_path.read_text(encoding="utf-8"))
    assert journal["state"] == "prepared"
    assert journal["owner"]["owner_id"] == journal["transaction_id"]
    assert all(entry["stage"] and entry["backup"] for entry in journal["files"])

    monkeypatch.undo()
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from stock_research import kronos_evaluation_runner as runner; "
                "runner._recover_pending_transaction(Path(__import__('sys').argv[1]))"
            ),
            str(output_dir),
        ],
        cwd=Path.cwd(),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(Path(__file__).resolve().parents[1] / "src"), os.environ.get("PYTHONPATH", "")]
            ),
        },
        check=True,
    )
    assert not transaction_path.exists()

    retry_client = FakeClient(model_identity="small-v2")
    result = run_model(config, model="small", output_dir=output_dir, client=retry_client)
    assert result.attempted_count == 2
    assert len(retry_client.calls) == 2


def test_prejournal_fsync_failure_leaves_journal_for_restart_recovery(
    prepared_experiment,
    monkeypatch,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    def fail_fsync(path):
        raise OSError("injected journal fsync failure")

    monkeypatch.setattr(runner, "_fsync_directory", fail_fsync)
    with pytest.raises(OSError, match="journal fsync"):
        run_model(
            config,
            model="small",
            output_dir=output_dir,
            client=FakeClient(model_identity="small-v2"),
        )

    assert (output_dir / runner.TRANSACTION_FILENAME).exists()
    monkeypatch.undo()
    runner._recover_pending_transaction(output_dir)
    assert not (output_dir / runner.TRANSACTION_FILENAME).exists()


def test_overlapping_prepare_does_not_delete_active_stage(tmp_path):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    output_dir = tmp_path / "locked"
    active_stage = tmp_path / ".locked.prepare-active"
    active_stage.mkdir()

    errors = []

    def overlap():
        try:
            prepare_experiment(
                config,
                output_dir=output_dir,
                snapshot_loader=make_loader(snapshots),
            )
        except Exception as exc:  # noqa: BLE001 - assertion below checks category.
            errors.append(exc)

    with runner._writer_lock(output_dir):
        thread = threading.Thread(target=overlap)
        thread.start()
        thread.join(timeout=0.2)
        assert thread.is_alive()

    thread.join(timeout=10)

    assert active_stage.exists()
    assert not errors
    assert (output_dir / runner.EXPERIMENT_FILENAME).exists()


def test_run_model_holds_output_lock_across_health_and_prediction(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    entered_health = threading.Event()
    release_health = threading.Event()
    first_result: list[Any] = []
    first_error: list[BaseException] = []

    class BlockingClient(FakeClient):
        def health(self):
            entered_health.set()
            assert release_health.wait(5)
            return super().health()

    def run_small():
        try:
            first_result.append(
                run_model(
                    config,
                    model="small",
                    output_dir=output_dir,
                    client=BlockingClient(),
                )
            )
        except BaseException as exc:  # noqa: BLE001 - asserted below.
            first_error.append(exc)

    small_thread = threading.Thread(target=run_small)
    small_thread.start()
    assert entered_health.wait(5)

    second_done = threading.Event()
    second_result: list[Any] = []

    def run_base():
        second_result.append(
            run_model(
                config,
                model="base",
                output_dir=output_dir,
                client=FakeClient(model="base", model_identity="base-v1"),
            )
        )
        second_done.set()

    base_thread = threading.Thread(target=run_base)
    base_thread.start()
    time.sleep(0.2)
    assert not second_done.is_set()

    release_health.set()
    small_thread.join(timeout=10)
    base_thread.join(timeout=10)
    assert not first_error
    assert len(first_result) == 1
    assert len(second_result) == 1
    rows = read_csv_rows(output_dir / runner.MANIFEST_FILENAME)
    assert {row["model"] for row in rows if row["status"] == "success"} == {"small", "base"}


def test_writer_lock_contention_raises_writer_lock_error(tmp_path):
    output_dir = tmp_path / "contended"
    ready = tmp_path / "lock-ready"
    script = "\n".join(
        [
            "from pathlib import Path",
            "import sys",
            "from stock_research import kronos_evaluation_runner as runner",
            "with runner._writer_lock(Path(sys.argv[1])):",
            "    Path(sys.argv[2]).write_text('ready')",
            "    sys.stdin.read()",
        ]
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(output_dir), str(ready)],
        cwd=Path.cwd(),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(Path(__file__).resolve().parents[1] / "src"), os.environ.get("PYTHONPATH", "")]
            ),
        },
        stdin=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.02)
        assert ready.exists()
        with pytest.raises(runner.WriterLockError):
            with runner._writer_lock(output_dir):
                pass
    finally:
        if process.stdin is not None:
            try:
                process.stdin.write(b"stop")
                process.stdin.close()
            except BrokenPipeError:
                pass
        process.wait(timeout=10)


def test_preparation_stage_does_not_leak_per_stage_writer_lock(tmp_path):
    output_dir = tmp_path / "prepared"
    prepare_experiment(
        make_config(),
        output_dir=output_dir,
        snapshot_loader=make_loader(
            [
                make_snapshot("CN:SH:600418"),
                make_snapshot("CN:SZ:000001", close_offset=10.0),
            ]
        ),
    )

    assert not list(tmp_path.glob(".*.prepare-*.kronos-writer.lock"))


def test_hard_kill_after_first_replace_recovers_and_cleans_root_temp(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    pid = os.fork()
    if pid == 0:
        original_commit = runner._commit_staged_artifacts

        def kill_after_first_replace(staged_paths, final_paths):
            (output_dir / ".forecast_bars.parquet.crash.tmp").write_text(
                "partial",
                encoding="utf-8",
            )
            os.replace(staged_paths[0], final_paths[0])
            os._exit(77)

        runner._commit_staged_artifacts = kill_after_first_replace
        try:
            run_model(
                config,
                model="small",
                output_dir=output_dir,
                client=FakeClient(model_identity="small-v2"),
            )
        finally:
            original_commit  # keep the child branch explicit for coverage tools.
            os._exit(78)
    _, status = os.waitpid(pid, 0)
    assert os.WEXITSTATUS(status) == 77

    retry = run_model(
        config,
        model="small",
        output_dir=output_dir,
        client=FakeClient(model_identity="small-v2"),
    )
    assert retry.attempted_count == 2
    assert not (output_dir / ".forecast_bars.parquet.crash.tmp").exists()
    assert not list(output_dir.glob(".*.tmp"))


def test_artifact_commit_crash_recovers_report_invalidation_intent(
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
    build_report(output_dir=output_dir)

    child_pid = os.fork()
    if child_pid == 0:
        original_commit = runner._commit_staged_artifacts

        def kill_after_artifact_commit(staged_paths, final_paths):
            original_commit(staged_paths, final_paths)
            os._exit(79)

        runner._commit_staged_artifacts = kill_after_artifact_commit
        try:
            runner._run_model_locked(
                config,
                model="base",
                output_dir=output_dir,
                client=FakeClient(model="base", model_identity="base-v2"),
            )
        finally:
            os._exit(80)

    _, status = os.waitpid(child_pid, 0)
    assert os.WIFEXITED(status)
    assert os.WEXITSTATUS(status) == 79
    assert (output_dir / runner.REPORT_INVALIDATION_FILENAME).exists()

    summary = build_report(output_dir=output_dir)

    assert summary["generation"]
    assert not (output_dir / runner.REPORT_INVALIDATION_FILENAME).exists()
    assert (output_dir / runner.REPORT_DIGEST_FILENAME).exists()


def test_transaction_recovery_is_idempotent_after_one_backup_delete_and_retry(
    prepared_experiment,
    monkeypatch,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    original_commit = runner._commit_staged_artifacts

    def partial_commit(staged_paths, final_paths):
        original_commit(staged_paths[:1], final_paths[:1])
        raise OSError("injected commit interruption")

    monkeypatch.setattr(runner, "_commit_staged_artifacts", partial_commit)
    with pytest.raises(OSError, match="interruption"):
        run_model(
            config,
            model="small",
            output_dir=output_dir,
            client=FakeClient(model_identity="small-v2"),
        )

    monkeypatch.undo()
    original_unlink = runner._unlink_transaction_path
    deleted_backup = False

    def fail_after_backup_delete(path):
        nonlocal deleted_backup
        if not deleted_backup and path.name.endswith(".backup"):
            deleted_backup = True
            path.unlink(missing_ok=True)
            raise OSError("injected backup cleanup interruption")
        return original_unlink(path)

    monkeypatch.setattr(runner, "_unlink_transaction_path", fail_after_backup_delete)
    with pytest.raises(OSError, match="backup cleanup"):
        runner._recover_pending_transaction(output_dir)
    assert deleted_backup
    assert (output_dir / runner.TRANSACTION_FILENAME).exists()

    monkeypatch.undo()
    retry_client = FakeClient(model_identity="small-v2")
    result = run_model(config, model="small", output_dir=output_dir, client=retry_client)

    assert result.attempted_count == 2
    assert len(retry_client.calls) == 2
    assert not (output_dir / runner.TRANSACTION_FILENAME).exists()
    assert not list(output_dir.glob(".*.backup"))
    assert not list(output_dir.glob(".*.stage"))


def test_unknown_top_level_stale_entries_are_rejected(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    (output_dir / "stale.tmp").write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown|stale|directory"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_orphan_preparation_stage_is_cleaned_before_retry(tmp_path):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    output_dir = tmp_path / "retryable"
    orphan = tmp_path / ".retryable.prepare-dead"
    orphan.mkdir()
    (orphan / "partial.json").write_text("{}", encoding="utf-8")
    (orphan / runner._PREPARATION_OWNER_FILENAME).write_text(
        json.dumps(
            {
                "owner_id": "dead-owner",
                "pid": 999999,
                "output_dir": str(output_dir.resolve()),
            }
        ),
        encoding="utf-8",
    )

    prepare_experiment(
        config,
        output_dir=output_dir,
        snapshot_loader=make_loader(snapshots),
    )

    assert not orphan.exists()
    assert not list(tmp_path.glob(".retryable.prepare-*"))
    assert (output_dir / runner.EXPERIMENT_FILENAME).exists()


def test_preparation_journal_recovers_stage_before_owner_marker(tmp_path):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    output_dir = tmp_path / "retryable"
    stage = tmp_path / ".retryable.prepare-hard-death"
    stage.mkdir()
    journal = {
        "schema_version": runner._PREPARATION_JOURNAL_SCHEMA_VERSION,
        "state": "staging",
        "owner_id": "dead-owner",
        "pid": 999999,
        "output_dir": str(output_dir.resolve()),
        "lock_path": str(runner._writer_lock_path(output_dir).resolve()),
        "stage_dir": stage.name,
    }
    runner._atomic_write_json(runner._preparation_journal_path(output_dir), journal)

    prepare_experiment(
        config,
        output_dir=output_dir,
        snapshot_loader=make_loader(snapshots),
    )

    assert not stage.exists()
    assert not runner._preparation_journal_path(output_dir).exists()
    assert (output_dir / runner.EXPERIMENT_FILENAME).exists()


def test_report_rejects_nonterminal_manifest_status(prepared_experiment):
    output_dir, _, _, _ = prepared_experiment

    with pytest.raises(ValueError, match="terminal|status"):
        build_report(output_dir=output_dir)


@pytest.mark.parametrize("snapshot_status", ["partial_truth", "forecast_only", "pending_calendar"])
def test_task3_snapshot_statuses_are_terminal_for_report_validation(tmp_path, snapshot_status):
    config = make_config()
    snapshots = [
        replace(make_snapshot("CN:SH:600418"), status=snapshot_status),
        replace(make_snapshot("CN:SZ:000001", close_offset=10.0), status=snapshot_status),
    ]
    prepare_experiment(
        config,
        output_dir=tmp_path,
        snapshot_loader=make_loader(snapshots),
    )

    manifest = {
        row["run_key"]: row
        for row in read_csv_rows(tmp_path / runner.MANIFEST_FILENAME)
    }
    runner._validate_report_artifacts(config=config, snapshots=snapshots, manifest=manifest, forecast_rows=[], realized_rows=[])


def test_default_snapshot_loader_returns_complete_source_metadata_without_duplicate_queries(
    monkeypatch,
):
    config = make_config()
    calls = {"bars": 0, "calendar": 0, "build": 0}
    frame = pd.DataFrame({"trade_date": ["2025-01-01", "2025-01-05"]})
    trade_dates = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"]
    snapshots = [
        replace(make_snapshot("CN:SH:600418"), status="partial_truth"),
        replace(make_snapshot("CN:SZ:000001", close_offset=10.0), status="forecast_only"),
    ]

    def fake_load_daily_bars(asset_ids, max_date, adjust_type, service):
        calls["bars"] += 1
        assert max_date == "2025-01-17"
        return frame

    def fake_load_global_trade_dates(adjust_type, start_date, max_date, service):
        calls["calendar"] += 1
        assert max_date == "2025-01-17"
        return trade_dates

    def fake_build(*args, **kwargs):
        calls["build"] += 1
        assert kwargs["origin_dates"] == ["2025-01-03"]
        return snapshots

    monkeypatch.setattr("stock_research.kronos_evaluation_data.load_daily_bars", fake_load_daily_bars)
    monkeypatch.setattr("stock_research.kronos_evaluation_data.load_global_trade_dates", fake_load_global_trade_dates)
    monkeypatch.setattr("stock_research.kronos_evaluation_data.build_rolling_snapshots", fake_build)

    loaded_snapshots, source_metadata = runner._default_snapshot_loader(config)

    assert loaded_snapshots == snapshots
    assert calls == {"bars": 1, "calendar": 1, "build": 1}
    assert source_metadata["calendar_min_date"] == "2025-01-01"
    assert source_metadata["calendar_max_date"] == "2025-01-05"
    assert source_metadata["minimum_truth_horizon"] == config.forecast_horizon
    assert source_metadata["status_counts"] == {
        "forecast_only": 1,
        "partial_truth": 1,
    }


def test_missing_health_identity_fails_preflight_without_synthesizing_requested_model(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    client = FakeClient(omit_health_identity=True)

    result = run_model(config, model="small", output_dir=output_dir, client=client)

    assert result.attempted_count == 2
    assert client.calls == []
    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"unavailable"}
    assert all(row["model_identity"] == "" for row in rows)
    assert all(row["health_model_identity"] == "" for row in rows)
    assert all(row["cache_hit"] == "false" for row in rows)


def test_equivalent_versioned_health_identities_are_one_cache_identity(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient(
        model_identity="Kronos-small-v1",
        health_weights_identity="weights-small-v1",
    )
    run_model(config, model="small", output_dir=output_dir, client=first_client)

    resume_client = FakeClient(
        model_identity="small-v1",
        health_weights_identity="weights-small-v1",
    )
    result = run_model(config, model="small", output_dir=output_dir, client=resume_client)

    assert result.cache_hit_count == 2
    assert result.attempted_count == 0
    assert resume_client.calls == []


def test_missing_health_weights_disables_cache_but_preserves_successful_artifacts(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    first_client = FakeClient(omit_health_weights_identity=True)
    first = run_model(config, model="small", output_dir=output_dir, client=first_client)
    manifest_before = [
        row for row in read_csv_rows(output_dir / runner.MANIFEST_FILENAME)
        if row["model"] == "small"
    ]
    forecast_before = read_table_rows(output_dir / runner.FORECAST_FILENAME)
    realized_before = read_table_rows(output_dir / runner.REALIZED_FILENAME)

    second_client = FakeClient(omit_health_weights_identity=True)
    second = run_model(config, model="small", output_dir=output_dir, client=second_client)

    assert first.attempted_count == second.attempted_count == 2
    assert second.cache_hit_count == 0
    assert len(second_client.calls) == 2
    assert all(row["status"] == "success" for row in manifest_before)
    assert len(forecast_before) == len(read_table_rows(output_dir / runner.FORECAST_FILENAME))
    assert len(realized_before) == len(read_table_rows(output_dir / runner.REALIZED_FILENAME))


def test_changed_health_weights_build_cannot_cache_hit(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    run_model(
        config,
        model="small",
        output_dir=output_dir,
        client=FakeClient(health_weights_identity="weights-small-build-a"),
    )
    changed = FakeClient(health_weights_identity="weights-small-build-b")

    result = run_model(config, model="small", output_dir=output_dir, client=changed)

    assert result.cache_hit_count == 0
    assert result.attempted_count == 2
    assert len(changed.calls) == 2


def test_report_rejects_forged_success_identity_without_live_health(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())
    run_model(
        config,
        model="base",
        output_dir=output_dir,
        client=FakeClient(model="base", model_identity="base-v1"),
    )

    import pyarrow as pa
    import pyarrow.parquet as parquet

    manifest_rows = read_csv_rows(output_dir / runner.MANIFEST_FILENAME)
    forecast_rows = read_table_rows(output_dir / runner.FORECAST_FILENAME)
    realized_rows = read_table_rows(output_dir / runner.REALIZED_FILENAME)
    forged_key = next(row["run_key"] for row in manifest_rows if row["model"] == "small")

    def forge(value):
        if isinstance(value, Mapping):
            return {key: forge(item) for key, item in value.items()}
        if isinstance(value, list):
            return [forge(item) for item in value]
        if isinstance(value, str):
            return (
                value.replace("weights-small-v1", "weights-base-v1")
                .replace("small-v1", "base-v1")
                .replace("small", "base")
            )
        return value

    for row in manifest_rows:
        if row["run_key"] != forged_key:
            continue
        for field in (
            "model_identity",
            "weights_identity",
            "health_model_identity",
            "health_weights_identity",
            "health_model_raw_identity",
            "health_weights_raw_identity",
            "response_model_identity",
            "response_weights_identity",
        ):
            row[field] = forge(row[field])
        row["health_metadata_json"] = json.dumps(forge(json.loads(row["health_metadata_json"])), sort_keys=True, separators=(",", ":"))
        row["raw_response_json"] = json.dumps(forge(json.loads(row["raw_response_json"])), sort_keys=True, separators=(",", ":"))
    for rows in (forecast_rows, realized_rows):
        for row in rows:
            if row["run_key"] == forged_key:
                row["model_identity"] = "base-v1"
                row["weights_identity"] = "weights-base-v1"

    forecast_path = output_dir / runner.FORECAST_FILENAME
    realized_path = output_dir / runner.REALIZED_FILENAME
    for path, rows in ((forecast_path, forecast_rows), (realized_path, realized_rows)):
        table = parquet.read_table(path)
        metadata = dict(table.schema.metadata or {})
        rewritten = pa.Table.from_pylist(rows, schema=table.schema)
        rewritten = rewritten.replace_schema_metadata(metadata)
        parquet.write_table(rewritten, path)

    forecast_schema = runner._schema_signature(
        runner._artifact_schema(pa, runner.FORECAST_COLUMNS)
    )
    realized_schema = runner._schema_signature(
        runner._artifact_schema(pa, runner.REALIZED_COLUMNS)
    )
    generation = runner._artifact_generation(
        manifest_rows,
        forecast_rows,
        realized_rows,
        forecast_schema=forecast_schema,
        realized_schema=realized_schema,
    )
    for row in manifest_rows:
        row["generation"] = generation
    runner._atomic_write_csv(
        output_dir / runner.MANIFEST_FILENAME,
        manifest_rows,
        runner.MANIFEST_COLUMNS,
    )
    for path in (forecast_path, realized_path):
        table = parquet.read_table(path)
        metadata = dict(table.schema.metadata or {})
        metadata[b"kronos_generation"] = generation.encode("utf-8")
        parquet.write_table(table.replace_schema_metadata(metadata), path)

    with pytest.raises(ValueError, match="identity|model"):
        build_report(output_dir=output_dir)

@pytest.mark.parametrize("relative", ["universe.csv", "forecast_bars.parquet", "report.md"])
def test_known_output_symlinks_are_rejected(prepared_experiment, relative):
    output_dir, config, _, _ = prepared_experiment
    target = output_dir.parent / f"outside-{relative.replace('.', '-') }"
    target.write_text("external", encoding="utf-8")
    path = output_dir / relative
    path.unlink(missing_ok=True)
    path.symlink_to(target)

    with pytest.raises(ValueError, match="symlink|regular"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_snapshot_directory_and_file_symlinks_are_rejected(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    snapshot_dir = output_dir / runner.SNAPSHOT_DIRECTORY
    external_dir = output_dir.parent / "outside-snapshots"
    external_dir.mkdir()
    for path in snapshot_dir.iterdir():
        path.unlink()
    snapshot_dir.rmdir()
    snapshot_dir.symlink_to(external_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink|regular"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_snapshot_file_symlink_is_rejected(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    snapshot_path = output_dir / runner.SNAPSHOT_DIRECTORY / "CN:SH:600418__2025-01-03.json"
    target = output_dir.parent / "outside-snapshot.json"
    target.write_bytes(snapshot_path.read_bytes())
    snapshot_path.unlink()
    snapshot_path.symlink_to(target)

    with pytest.raises(ValueError, match="symlink|regular"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_transaction_symlink_is_rejected(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())
    target = output_dir.parent / "outside-transaction.json"
    target.write_text("{}", encoding="utf-8")
    transaction = output_dir / runner.TRANSACTION_FILENAME
    transaction.symlink_to(target)

    with pytest.raises(ValueError, match="symlink|regular"):
        runner._recover_pending_transaction(output_dir)


def test_runner_allows_benign_symlink_parent_for_real_prepare_and_run(tmp_path):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    parent_alias = tmp_path / "parent-alias"
    parent_alias.symlink_to(real_parent, target_is_directory=True)
    output_dir = parent_alias / "prepared"

    preparation = prepare_experiment(
        config,
        output_dir=output_dir,
        snapshot_loader=make_loader(snapshots),
    )
    result = run_model(
        config,
        model="small",
        output_dir=output_dir,
        client=FakeClient(),
    )

    assert preparation.snapshot_count == len(snapshots)
    assert result.status_counts == {"success": len(snapshots)}
    assert output_dir.is_dir()


def test_preparation_metadata_failure_leaves_destination_retryable(tmp_path, monkeypatch):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    output_dir = tmp_path / "retryable"
    original_write_json = runner._atomic_write_json

    def fail_metadata(path, value, **kwargs):
        if path.name == runner.EXPERIMENT_FILENAME:
            raise OSError("injected metadata failure")
        return original_write_json(path, value, **kwargs)

    monkeypatch.setattr(runner, "_atomic_write_json", fail_metadata)
    with pytest.raises(OSError, match="metadata"):
        prepare_experiment(
            config,
            output_dir=output_dir,
            snapshot_loader=make_loader(snapshots),
        )

    assert not output_dir.exists() or not any(output_dir.iterdir())
    monkeypatch.undo()
    prepare_experiment(
        config,
        output_dir=output_dir,
        snapshot_loader=make_loader(snapshots),
    )
    assert (output_dir / runner.EXPERIMENT_FILENAME).exists()


def test_runner_manifest_prefers_reserved_complete_raw_response_slot(
    prepared_experiment,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(
        config,
        model="small",
        output_dir=output_dir,
        client=FakeClient(response_raw_collision=True),
    )

    row = next(row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small")
    raw_response = json.loads(row["raw_response_json"])
    assert raw_response["status"] == "succeeded"
    assert raw_response["raw_response"]["status"] == "succeeded"


def test_forecast_artifact_contains_representative_ohlcv_and_path(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())

    row = read_table_rows(output_dir / "forecast_bars.parquet")[0]
    assert {
        "representative_open",
        "representative_high",
        "representative_low",
        "representative_close",
        "representative_volume",
        "representative_amount",
        "representative_path_json",
    }.issubset(row)
    assert json.loads(row["representative_path_json"])[0]["timestamp"] == "2025-01-04"


def test_client_accepted_result_summary_envelope_is_runner_accepted(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    from stock_research.kronos_evaluation_client import KronosClient

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Session:
        def get(self, url, *, headers, timeout):
            return Response(
                {
                    "status": "ok",
                    "model": "Kronos-small",
                    "model_identity": "small-v1",
                    "weights_identity": "weights-small-v1",
                    "device": "cpu",
                    "cuda": False,
                }
            )

        def post(self, url, *, headers, json, timeout):
            timestamps = json["daily"]["future_timestamps"]
            path = [
                {
                    "timestamp": timestamp,
                    "open": 102.0 + index,
                    "high": 104.0 + index,
                    "low": 101.0 + index,
                    "close": 103.0 + index,
                    "volume": 1000.0 + index,
                    "amount": 100000.0 + index,
                }
                for index, timestamp in enumerate(timestamps)
            ]
            quantiles = {
                "p10": [101.0 + index for index in range(len(path))],
                "p50": [103.0 + index for index in range(len(path))],
                "p90": [105.0 + index for index in range(len(path))],
            }
            return Response(
                {
                    "status": "succeeded",
                    "model": "small",
                    "model_identity": "small-v1",
                    "weights_identity": "weights-small-v1",
                    "sample_count": json["sample_count"],
                    "result": {
                        "summary": {"close": quantiles},
                        "daily": {"representative_path": path},
                    },
                }
            )

        def close(self):
            return None

    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=Session(),
    )
    result = run_model(config, model="small", output_dir=output_dir, client=client)

    assert result.attempted_count == 2
    assert {row["status"] for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"} == {"success"}


def test_missing_representative_path_is_protocol_failure(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    run_model(
        config,
        model="small",
        output_dir=output_dir,
        client=FakeClient(include_representative_path=False),
    )

    rows = [row for row in read_csv_rows(output_dir / "run_manifest.csv") if row["model"] == "small"]
    assert {row["status"] for row in rows} == {"protocol_error"}
    assert len(read_table_rows(output_dir / "forecast_bars.parquet")) == 0


def test_extract_quantiles_supports_result_summary_branch():
    quantiles = {"p10": [1.0], "p50": [1.5], "p90": [2.0]}
    response = {
        "status": "succeeded",
        "daily": {"representative_path": []},
        "result": {"summary": {"close": quantiles}},
    }

    assert runner._extract_quantiles(response) == quantiles


def test_extract_quantiles_supports_result_summary_without_top_level_daily():
    quantiles = {"p10": [1.0], "p50": [1.5], "p90": [2.0]}
    response = {
        "status": "succeeded",
        "result": {"summary": {"close": quantiles}},
    }

    assert runner._extract_quantiles(response) == quantiles


def test_parquet_dependency_failure_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)

    with pytest.raises(RuntimeError, match="pyarrow"):
        runner._atomic_write_table(
            tmp_path / "forecast_bars.parquet",
            [],
            runner.FORECAST_COLUMNS,
        )
    assert not (tmp_path / "forecast_bars.parquet").exists()


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


def test_report_outputs_record_authenticated_artifact_generation(
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
    generation = summary["generation"]
    assert generation
    for filename in (
        runner.METRICS_BY_STOCK_FILENAME,
        runner.METRICS_BY_MODEL_FILENAME,
        runner.MODEL_COMPARISON_FILENAME,
    ):
        rows = read_csv_rows(output_dir / filename)
        assert all(row["generation"] == generation for row in rows)
    assert f"Artifact generation: `{generation}`" in (
        output_dir / runner.REPORT_FILENAME
    ).read_text(encoding="utf-8")


def test_directory_only_fsync_failure_is_propagated(tmp_path, monkeypatch):
    def fail_directory_fsync(_descriptor):
        raise OSError("injected directory fsync failure")

    monkeypatch.setattr(runner.os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError, match="directory fsync"):
        runner._fsync_directory(tmp_path)


def test_report_rejects_tampered_derived_generation_marker(
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
    build_report(output_dir=output_dir)

    metrics_path = output_dir / runner.METRICS_BY_MODEL_FILENAME
    rows = read_csv_rows(metrics_path)
    rows[0]["generation"] = "forged-generation"
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="generation|derived|report"):
        build_report(output_dir=output_dir)


def test_report_rejects_tampered_derived_numeric_content(
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
    build_report(output_dir=output_dir)

    metrics_path = output_dir / runner.METRICS_BY_MODEL_FILENAME
    rows = read_csv_rows(metrics_path)
    rows[0]["mean_absolute_return_error"] = "999999.0"
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="digest|content|derived|report"):
        build_report(output_dir=output_dir)
    with pytest.raises(ValueError, match="digest|content|derived|report"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_legacy_four_file_report_migrates_to_authenticated_digest(
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
    build_report(output_dir=output_dir)
    (output_dir / runner.REPORT_DIGEST_FILENAME).unlink()

    summary = build_report(output_dir=output_dir)

    assert summary["generation"]
    digest = json.loads(
        (output_dir / runner.REPORT_DIGEST_FILENAME).read_text(encoding="utf-8")
    )
    assert digest["schema_version"] == 2


def test_run_model_migrates_legacy_report_bundle_without_build_report(
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
    build_report(output_dir=output_dir)
    (output_dir / runner.REPORT_DIGEST_FILENAME).unlink()

    result = run_model(
        config,
        model="small",
        output_dir=output_dir,
        client=FakeClient(),
    )

    assert result.cache_hit_count == len(config.asset_ids)
    for filename in runner._REPORT_PUBLISHED_FILENAMES:
        assert not (output_dir / filename).exists()


def test_run_model_rejects_tampered_legacy_report_bundle_without_digest(
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
    build_report(output_dir=output_dir)
    (output_dir / runner.REPORT_DIGEST_FILENAME).unlink()
    metrics_path = output_dir / runner.METRICS_BY_MODEL_FILENAME
    rows = read_csv_rows(metrics_path)
    rows[0]["mean_absolute_return_error"] = "999999.0"
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    tampered_bytes = metrics_path.read_bytes()

    with pytest.raises(ValueError, match="legacy|content|report"):
        run_model(
            config,
            model="small",
            output_dir=output_dir,
            client=FakeClient(),
        )

    assert metrics_path.read_bytes() == tampered_bytes
    assert not (output_dir / runner.REPORT_DIGEST_FILENAME).exists()


def test_legacy_same_generation_report_tampering_is_not_overwritten(
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
    build_report(output_dir=output_dir)
    (output_dir / runner.REPORT_DIGEST_FILENAME).unlink()
    metrics_path = output_dir / runner.METRICS_BY_MODEL_FILENAME
    rows = read_csv_rows(metrics_path)
    rows[0]["mean_absolute_return_error"] = "999999.0"
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="legacy|digest|content|report"):
        build_report(output_dir=output_dir)


def test_v1_report_digest_migrates_after_hash_validation(
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
    build_report(output_dir=output_dir)

    digest_path = output_dir / runner.REPORT_DIGEST_FILENAME
    digest = json.loads(digest_path.read_text(encoding="utf-8"))
    digest["schema_version"] = 1
    runner._atomic_write_json(digest_path, digest)

    build_report(output_dir=output_dir)

    migrated = json.loads(digest_path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2


def test_v1_report_journal_and_digest_migrate_to_current_format(
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
    build_report(output_dir=output_dir)

    digest_path = output_dir / runner.REPORT_DIGEST_FILENAME
    digest = json.loads(digest_path.read_text(encoding="utf-8"))
    digest["schema_version"] = 1
    runner._atomic_write_json(digest_path, digest)

    transaction_id = "legacy-v1"
    stage_dir = output_dir / f".{runner.REPORT_TRANSACTION_FILENAME}.{transaction_id}.stage"
    stage_dir.mkdir()
    transaction = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "journal_temp": f".{runner.REPORT_TRANSACTION_FILENAME}.{transaction_id}.tmp",
        "state": "prepared",
        "owner": {
            "owner_id": transaction_id,
            "writer_owner_id": "legacy-writer",
            "pid": os.getpid(),
            "output_dir": str(output_dir.resolve()),
            "lock_path": str(runner._writer_lock_path(output_dir).resolve()),
        },
        "stage_dir": stage_dir.name,
        "files": [
            {"final": filename, "stage": filename}
            for filename in runner._DERIVED_REPORT_FILENAMES
        ],
    }
    runner._atomic_write_json(output_dir / runner.REPORT_TRANSACTION_FILENAME, transaction)

    summary = build_report(output_dir=output_dir)

    assert summary["generation"]
    assert not (output_dir / runner.REPORT_TRANSACTION_FILENAME).exists()
    assert not stage_dir.exists()
    migrated_digest = json.loads(digest_path.read_text(encoding="utf-8"))
    assert migrated_digest["schema_version"] == 2


def test_new_model_run_invalidates_derived_report_outputs(
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
    build_report(output_dir=output_dir)
    assert (output_dir / runner.REPORT_FILENAME).exists()

    run_model(
        config,
        model="base",
        output_dir=output_dir,
        client=FakeClient(model="base", model_identity="base-v2"),
    )

    assert not any(
        (output_dir / filename).exists()
        for filename in (
            runner.METRICS_BY_STOCK_FILENAME,
            runner.METRICS_BY_MODEL_FILENAME,
            runner.MODEL_COMPARISON_FILENAME,
            runner.REPORT_FILENAME,
            runner.REPORT_DIGEST_FILENAME,
        )
    )


def test_report_invalidation_recovers_after_mid_delete_hard_kill(
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
    build_report(output_dir=output_dir)

    child_pid = os.fork()
    if child_pid == 0:
        try:
            original_unlink = runner._unlink_report_invalidation_path

            def kill_after_first_delete(path):
                original_unlink(path)
                os._exit(73)

            runner._unlink_report_invalidation_path = kill_after_first_delete
            runner._invalidate_derived_report_artifacts_locked(output_dir)
        except BaseException:
            os._exit(74)
        os._exit(75)

    _, status = os.waitpid(child_pid, 0)
    assert os.WIFEXITED(status)
    assert os.WEXITSTATUS(status) == 73
    assert (output_dir / runner.REPORT_INVALIDATION_FILENAME).exists()

    summary = build_report(output_dir=output_dir)

    assert summary["generation"]
    assert not (output_dir / runner.REPORT_INVALIDATION_FILENAME).exists()
    assert all(
        (output_dir / filename).exists()
        for filename in (
            runner.METRICS_BY_STOCK_FILENAME,
            runner.METRICS_BY_MODEL_FILENAME,
            runner.MODEL_COMPARISON_FILENAME,
            runner.REPORT_FILENAME,
        )
    )


def test_build_report_holds_output_lock_across_derivation(
    prepared_experiment,
    monkeypatch,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())
    run_model(
        config,
        model="base",
        output_dir=output_dir,
        client=FakeClient(model="base", model_identity="base-v1"),
    )
    entered = threading.Event()
    release = threading.Event()
    original_builder = runner._build_metric_rows

    def blocking_builder(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(runner, "_build_metric_rows", blocking_builder)
    errors: list[BaseException] = []

    def report_thread():
        try:
            build_report(output_dir=output_dir)
        except BaseException as exc:  # noqa: BLE001 - assertion below.
            errors.append(exc)

    thread = threading.Thread(target=report_thread)
    thread.start()
    assert entered.wait(5)
    run_done = threading.Event()

    def model_thread():
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())
        run_done.set()

    contender = threading.Thread(target=model_thread)
    contender.start()
    time.sleep(0.2)
    assert not run_done.is_set()
    release.set()
    thread.join(timeout=10)
    contender.join(timeout=10)
    assert not errors


def test_report_publish_failure_recovers_on_retry(
    prepared_experiment,
    monkeypatch,
):
    output_dir, config, _, _ = prepared_experiment
    run_model(config, model="small", output_dir=output_dir, client=FakeClient())
    run_model(
        config,
        model="base",
        output_dir=output_dir,
        client=FakeClient(model="base", model_identity="base-v1"),
    )
    original_write_text = runner._atomic_write_text

    def fail_report_stage(path, value, *, temporary_path=None):
        if path.name == runner.REPORT_FILENAME:
            raise OSError("injected report stage write failure")
        return original_write_text(path, value, temporary_path=temporary_path)

    monkeypatch.setattr(runner, "_atomic_write_text", fail_report_stage)
    with pytest.raises(OSError, match="report stage"):
        build_report(output_dir=output_dir)
    assert (output_dir / runner.REPORT_TRANSACTION_FILENAME).exists()

    monkeypatch.undo()
    summary = build_report(output_dir=output_dir)
    assert summary["generation"]
    assert not (output_dir / runner.REPORT_TRANSACTION_FILENAME).exists()
    assert not list(output_dir.glob(".*.stage"))


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
