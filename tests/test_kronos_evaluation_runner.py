from __future__ import annotations

import csv
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest


try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")
    requests_stub.Session = object
    requests_stub.RequestException = Exception
    requests_stub.Timeout = TimeoutError
    sys.modules["requests"] = requests_stub

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
    ) -> None:
        self.model = model
        self.model_identity = model_identity
        self.weights_identity = f"weights-{model_identity}"
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
        self.calls: list[tuple[str, str, int, int | None]] = []

    def health(self) -> dict[str, Any]:
        if self.health_failure:
            raise RuntimeError("health unavailable")
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
        representative_path = [dict(row) for row in snapshot.realized]
        daily = {
            "p10": [102.0, 103.0],
            "p50": [103.0, 104.0],
            "p90": [104.0, 105.0],
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
            response["_kronos_raw_response"] = complete_response
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
    build_report(output_dir=output_dir)


def test_unknown_top_level_stale_entries_are_rejected(prepared_experiment):
    output_dir, config, _, _ = prepared_experiment
    (output_dir / "stale.tmp").write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown|stale|directory"):
        run_model(config, model="small", output_dir=output_dir, client=FakeClient())


def test_preparation_metadata_failure_leaves_destination_retryable(tmp_path, monkeypatch):
    config = make_config()
    snapshots = [
        make_snapshot("CN:SH:600418"),
        make_snapshot("CN:SZ:000001", close_offset=10.0),
    ]
    output_dir = tmp_path / "retryable"
    original_write_json = runner._atomic_write_json

    def fail_metadata(path, value):
        if path.name == runner.EXPERIMENT_FILENAME:
            raise OSError("injected metadata failure")
        return original_write_json(path, value)

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
