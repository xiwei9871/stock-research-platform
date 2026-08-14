from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from stock_research.kronos_experiment_universe import UniverseSelection


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kronos_experiment.py"
)


def load_cli_module():
    spec = importlib.util.spec_from_file_location("run_kronos_experiment", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_config(tmp_path: Path, *, model: str = "small") -> Path:
    payload = {
        "schema_version": 1,
        "experiment_id": "test-cli",
        "model": {
            "name": model,
            "fallback": False,
            "seed": 7,
            "sample_count": 20,
        },
        "data": {
            "frequency": "1d",
            "adjust_type": "qfq",
            "input_window": 3,
            "start_date": "2025-01-03",
            "end_date": "2025-01-31",
        },
        "universe": {
            "mode": "explicit",
            "count": 2,
            "seed": None,
            "market": "CN_A",
            "asset_ids": ["sh.600418", "000001.SZ"],
        },
        "prediction": {
            "forecast_horizon": 2,
            "report_horizons": [1, 2],
            "include_latest_forecast": True,
        },
        "evaluation": {"primary_horizon": 1, "baseline": "persistence"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def fake_selection() -> UniverseSelection:
    return UniverseSelection(
        asset_ids=("CN:SH:600418", "CN:SZ:000001"),
        candidates=(
            {"asset_id": "CN:SH:600418", "name": "A"},
            {"asset_id": "CN:SZ:000001", "name": "B"},
        ),
        selected_rows=(
            {"asset_id": "CN:SH:600418", "name": "A"},
            {"asset_id": "CN:SZ:000001", "name": "B"},
        ),
        candidate_count=2,
        selection_seed=None,
        filters={
            "mode": "explicit",
            "count": 2,
            "market": "CN_A",
            "adjust_type": "qfq",
            "input_window": 3,
            "cutoff_date": "2025-01-02",
        },
        candidate_fingerprint="a" * 64,
        selection_fingerprint="b" * 64,
    )


def install_prepare_seams(cli, monkeypatch, *, calls):
    selection = fake_selection()

    def fake_select_universe(**kwargs):
        calls["selection"] = kwargs
        return replace(
            selection,
            filters={
                "mode": kwargs["mode"],
                "count": kwargs["count"],
                "market": kwargs["market"],
                "adjust_type": kwargs["adjust_type"],
                "input_window": kwargs["input_window"],
                "cutoff_date": kwargs["cutoff_date"],
            },
        )

    def fake_prepare(config, *, output_dir, snapshot_loader):
        calls["prepare"] = {
            "config": config,
            "output_dir": output_dir,
            "snapshot_loader": snapshot_loader,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schema_version": 3,
            "config": {
                field.name: cli._jsonable(getattr(config, field.name))
                for field in fields(config)
            },
            "universe": list(config.asset_ids),
        }
        (output_dir / cli.EXPERIMENT_FILENAME).write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        return SimpleNamespace(snapshot_count=4, status_counts={"ready": 4})

    monkeypatch.setattr(cli, "select_universe", fake_select_universe)
    monkeypatch.setattr(cli, "prepare_experiment", fake_prepare)
    monkeypatch.setattr(cli, "resolve_latest_market_date", lambda **_: "2025-01-31")


def install_prediction_seams(cli, monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def assert_model(self, model):
            pass

        def close(self):
            pass

    monkeypatch.setattr(cli, "KronosClient", FakeClient)
    monkeypatch.setenv("KRONOS_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(
        cli,
        "run_model",
        lambda config, *, model, output_dir, client: SimpleNamespace(
            status_counts={"success": 1},
            attempted_count=1,
            cache_hit_count=0,
            skipped_count=0,
        ),
    )


def test_parser_accepts_all_configured_stages_and_resume():
    cli = load_cli_module()
    parser = cli.build_parser()

    for stage in ("prepare", "predict", "report", "run"):
        args = parser.parse_args(["--config", "config.json", "--stage", stage])
        assert args.stage == stage
        assert args.resume is False

    resumed = parser.parse_args(
        ["--config", "config.json", "--stage", "run", "--resume"]
    )
    assert resumed.resume is True


def test_run_dispatches_one_model_and_writes_sidecars(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)

    class FakeClient:
        def __init__(self, base_url, *, token, timeout):
            calls["client"] = (base_url, token, timeout)

        def assert_model(self, model):
            calls.setdefault("assert_models", []).append(model)
            return {"model": model}

        def close(self):
            calls["closed"] = True

    def fake_run_model(config, *, model, output_dir, client):
        calls["run_model"] = (config, model, output_dir, client)
        return SimpleNamespace(
            status_counts={"success": 4},
            attempted_count=4,
            cache_hit_count=0,
            skipped_count=0,
        )

    monkeypatch.setattr(cli, "KronosClient", FakeClient)
    monkeypatch.setattr(cli, "run_model", fake_run_model)
    monkeypatch.setattr(
        cli,
        "build_report",
        lambda *, output_dir: {"paths": {"report": str(output_dir / "report.md")}},
    )
    monkeypatch.setenv("KRONOS_INTERNAL_TOKEN", "test-token")

    summary = cli.run_experiment(config_path, stage="run")

    config = calls["prepare"]["config"]
    assert config.models == ("small",)
    assert config.fallback is False
    assert config.start_date == "2025-01-03"
    assert config.input_window == 3
    assert config.sample_count == 20
    assert config.evaluation_horizons == (1, 2)
    assert calls["assert_models"] == ["small"]
    assert calls["run_model"][1] == "small"
    assert summary["stage"] == "run"
    assert summary["status"] == "ok"

    output_dir = tmp_path / "outputs" / "test-cli"
    experiment_sidecar = json.loads(
        (output_dir / cli.EXPERIMENT_CONFIG_FILENAME).read_text(encoding="utf-8")
    )
    universe_sidecar = json.loads(
        (output_dir / cli.UNIVERSE_SELECTION_FILENAME).read_text(encoding="utf-8")
    )
    assert experiment_sidecar["config_fingerprint"] == config.config_fingerprint
    assert experiment_sidecar["provenance"]["model"] == "small"
    assert experiment_sidecar["provenance"]["frequency"] == "1d"
    assert universe_sidecar["asset_ids"] == list(config.asset_ids)
    assert (output_dir / cli.LATEST_FORECAST_FILENAME).is_file()


def test_changed_config_is_parameter_substitution_not_a_new_code_path(
    tmp_path, monkeypatch
):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["experiment_id"] = "test-cli-base"
    payload["model"]["name"] = "base"
    payload["data"]["start_date"] = "2025-01-06"
    payload["data"]["input_window"] = 4
    payload["model"]["sample_count"] = 11
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)

    summary = cli.run_experiment(config_path, stage="prepare")

    config = calls["prepare"]["config"]
    assert summary["status"] == "ok"
    assert config.models == ("base",)
    assert config.start_date == "2025-01-06"
    assert config.input_window == 4
    assert config.sample_count == 11


@pytest.mark.parametrize("stage", ["prepare", "run"])
def test_existing_directory_requires_resume(tmp_path, monkeypatch, stage):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)

    cli.run_experiment(config_path, stage="prepare")
    output_dir = tmp_path / "outputs" / "test-cli"
    before = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    with pytest.raises(FileExistsError, match="use --resume"):
        cli.run_experiment(config_path, stage=stage)
    after = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_resume_fingerprint_mismatch_fails_before_prepare(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)

    cli.run_experiment(config_path, stage="prepare")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["model"]["seed"] = 8
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        cli.run_experiment(config_path, stage="prepare", resume=True)


def test_prediction_requires_single_model_and_never_falls_back(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def assert_model(self, model):
            calls.setdefault("assert_models", []).append(model)

        def close(self):
            pass

    monkeypatch.setattr(cli, "KronosClient", FakeClient)
    monkeypatch.setenv("KRONOS_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(
        cli,
        "run_model",
        lambda config, *, model, output_dir, client: SimpleNamespace(
            status_counts={"success": 1},
            attempted_count=1,
            cache_hit_count=0,
            skipped_count=0,
        ),
    )

    summary = cli.run_experiment(config_path, stage="predict", resume=True)
    assert summary["status"] == "ok"
    assert calls["assert_models"] == ["small"]


@pytest.mark.parametrize("stage", ["predict", "report"])
def test_existing_write_stage_requires_resume_and_does_not_touch_files(
    tmp_path, monkeypatch, stage
):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")

    output_dir = tmp_path / "outputs" / "test-cli"
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("before", encoding="utf-8")
    before = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    monkeypatch.setenv("KRONOS_INTERNAL_TOKEN", "test-token")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls["client_called"] = True

        def assert_model(self, model):
            calls["assert_model_called"] = True

        def close(self):
            calls["client_closed"] = True

    monkeypatch.setattr(cli, "KronosClient", FakeClient)
    monkeypatch.setattr(
        cli,
        "run_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run_model must not run without --resume")
        ),
    )
    monkeypatch.setattr(
        cli,
        "build_report",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("build_report must not run without --resume")
        ),
    )

    with pytest.raises(FileExistsError, match="--resume"):
        cli.run_experiment(config_path, stage=stage)

    assert sentinel.read_text(encoding="utf-8") == "before"
    after = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert "client_called" not in calls
    assert "assert_model_called" not in calls


@pytest.mark.parametrize("stage", ["predict", "report"])
def test_existing_write_stage_resume_matching_fingerprint_succeeds(
    tmp_path, monkeypatch, stage
):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")
    output_dir = tmp_path / "outputs" / "test-cli"
    monkeypatch.setenv("KRONOS_INTERNAL_TOKEN", "test-token")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def assert_model(self, model):
            calls.setdefault("assert_models", []).append(model)

        def close(self):
            pass

    monkeypatch.setattr(cli, "KronosClient", FakeClient)
    monkeypatch.setattr(
        cli,
        "run_model",
        lambda config, *, model, output_dir, client: SimpleNamespace(
            status_counts={"success": 1},
            attempted_count=1,
            cache_hit_count=0,
            skipped_count=0,
        ),
    )
    monkeypatch.setattr(
        cli,
        "build_report",
        lambda *, output_dir: {"paths": {"report": str(output_dir / "report.md")}},
    )
    monkeypatch.setattr(
        cli,
        "write_latest_forecast",
        lambda output_dir, **kwargs: output_dir / cli.LATEST_FORECAST_FILENAME,
    )

    summary = cli.run_experiment(config_path, stage=stage, resume=True)

    assert summary["status"] == "ok"
    if stage == "predict":
        assert calls["assert_models"] == ["small"]
    else:
        assert summary["stage"] == "report"


@pytest.mark.parametrize("stage", ["predict", "report"])
def test_existing_write_stage_resume_fingerprint_mismatch_fails(
    tmp_path, monkeypatch, stage
):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["model"]["seed"] = 8
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        cli.run_experiment(config_path, stage=stage, resume=True)


def test_first_concurrent_prepare_cannot_bypass_output_lock(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    selection = fake_selection()
    monkeypatch.setattr(cli, "select_universe", lambda **kwargs: selection)
    monkeypatch.setattr(cli, "resolve_latest_market_date", lambda **_: "2025-01-31")
    entered = threading.Event()
    release = threading.Event()

    def blocking_prepare(config, *, output_dir, snapshot_loader):
        entered.set()
        assert release.wait(5), "blocking prepare was not released"
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schema_version": 3,
            "config": {
                field.name: cli._jsonable(getattr(config, field.name))
                for field in fields(config)
            },
            "universe": list(config.asset_ids),
        }
        (output_dir / cli.EXPERIMENT_FILENAME).write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        return SimpleNamespace(snapshot_count=1, status_counts={"ready": 1})

    monkeypatch.setattr(cli, "prepare_experiment", blocking_prepare)
    result: list[object] = []

    def first_runner():
        try:
            result.append(cli.run_experiment(config_path, stage="prepare"))
        except Exception as exc:  # pragma: no cover - assertion below reports it.
            result.append(exc)

    thread = threading.Thread(target=first_runner)
    thread.start()
    assert entered.wait(5), "first prepare did not reach the protected section"
    second_result: list[object] = []

    def second_runner():
        try:
            second_result.append(cli.run_experiment(config_path, stage="prepare"))
        except Exception as exc:  # pragma: no cover - assertion below reports it.
            second_result.append(exc)

    second_thread = threading.Thread(target=second_runner)
    second_thread.start()
    time.sleep(0.1)
    release.set()
    thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not thread.is_alive()
    assert not second_thread.is_alive()
    assert len(result) == 1
    assert not isinstance(result[0], Exception)
    assert len(second_result) == 1
    assert isinstance(second_result[0], FileExistsError)
    assert "locked" in str(second_result[0])
    assert (tmp_path / "outputs" / "test-cli" / cli.EXPERIMENT_CONFIG_FILENAME).is_file()


def test_process_death_releases_experiment_lock(tmp_path):
    cli = load_cli_module()
    if cli._LOCK_BACKEND == "exclusive":
        pytest.skip("platform has no process-lifetime file-lock primitive")
    output_dir = tmp_path / "outputs" / "process-lifecycle"
    marker = tmp_path / "lock-acquired"
    child_code = """
import importlib.util
import pathlib
import sys
import time

module_path = pathlib.Path(sys.argv[1])
output_dir = pathlib.Path(sys.argv[2])
marker = pathlib.Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("run_kronos_experiment_child", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with module._experiment_output_lock(output_dir):
    marker.write_text("ready", encoding="utf-8")
    time.sleep(30)
"""
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_code,
            str(SCRIPT_PATH),
            str(output_dir),
            str(marker),
        ],
        env={**os.environ, "PYTHONPATH": str(SCRIPT_PATH.parents[1] / "src")},
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), "child did not acquire the experiment lock"
        child.kill()
        child.wait(timeout=5)
        with cli._experiment_output_lock(output_dir):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_sidecar_write_failure_does_not_publish_resumeable_directory(
    tmp_path, monkeypatch
):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    original_atomic_create = cli._atomic_create_json

    def fail_on_universe(path, payload):
        if path.name == cli.UNIVERSE_SELECTION_FILENAME:
            raise OSError("simulated sidecar publication failure")
        return original_atomic_create(path, payload)

    monkeypatch.setattr(cli, "_atomic_create_json", fail_on_universe)

    with pytest.raises(OSError, match="simulated sidecar"):
        cli.run_experiment(config_path, stage="prepare")

    output_root = tmp_path / "outputs"
    assert not (output_root / "test-cli").exists()
    assert not list(output_root.glob(".test-cli.staging-*"))
    assert (output_root / ".test-cli.kronos-cli.lock").is_file()


def test_resume_rejects_universe_sidecar_asset_mismatch(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")
    selection_path = tmp_path / "outputs" / "test-cli" / cli.UNIVERSE_SELECTION_FILENAME
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["asset_ids"] = list(reversed(selection["asset_ids"]))
    selection_path.write_text(json.dumps(selection), encoding="utf-8")
    install_prediction_seams(cli, monkeypatch)

    with pytest.raises(ValueError, match="asset|universe"):
        cli.run_experiment(config_path, stage="predict", resume=True)


def test_resume_rejects_universe_sidecar_date_mismatch(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")
    selection_path = tmp_path / "outputs" / "test-cli" / cli.UNIVERSE_SELECTION_FILENAME
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["resolved_end_date"] = "2025-01-30"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")
    install_prediction_seams(cli, monkeypatch)

    with pytest.raises(ValueError, match="date"):
        cli.run_experiment(config_path, stage="predict", resume=True)


def test_resume_rejects_config_sidecar_provenance_mismatch(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")
    config_sidecar_path = tmp_path / "outputs" / "test-cli" / cli.EXPERIMENT_CONFIG_FILENAME
    config_sidecar = json.loads(config_sidecar_path.read_text(encoding="utf-8"))
    config_sidecar["provenance"]["asset_ids"] = ["CN:SH:600418"]
    config_sidecar_path.write_text(json.dumps(config_sidecar), encoding="utf-8")
    install_prediction_seams(cli, monkeypatch)

    with pytest.raises(ValueError, match="provenance|asset"):
        cli.run_experiment(config_path, stage="predict", resume=True)


def test_resume_rejects_frozen_experiment_metadata_universe_mismatch(
    tmp_path, monkeypatch
):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")
    metadata_path = tmp_path / "outputs" / "test-cli" / cli.EXPERIMENT_FILENAME
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["universe"] = ["CN:SH:600418"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    install_prediction_seams(cli, monkeypatch)

    with pytest.raises(ValueError, match="experiment metadata|universe"):
        cli.run_experiment(config_path, stage="predict", resume=True)


def test_resume_rejects_latest_forecast_sidecar_mismatch(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)
    cli.run_experiment(config_path, stage="prepare")
    output_dir = tmp_path / "outputs" / "test-cli"
    config_sidecar = json.loads(
        (output_dir / cli.EXPERIMENT_CONFIG_FILENAME).read_text(encoding="utf-8")
    )
    (output_dir / cli.LATEST_FORECAST_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "experiment_id": "test-cli",
                "config_fingerprint": config_sidecar["config_fingerprint"],
                "model": "base",
                "latest_origin": "2025-01-31",
                "snapshots": [],
            }
        ),
        encoding="utf-8",
    )
    install_prediction_seams(cli, monkeypatch)

    with pytest.raises(ValueError, match="latest_forecast"):
        cli.run_experiment(config_path, stage="predict", resume=True)


def test_cli_validation_errors_emit_exactly_one_json_line(tmp_path, capsys):
    cli = load_cli_module()
    result = cli.main(
        ["--config", str(tmp_path / "missing.json"), "--stage", "prepare"]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["stage"] == "prepare"
    assert summary["status"] == "error"
    assert summary["error"]
