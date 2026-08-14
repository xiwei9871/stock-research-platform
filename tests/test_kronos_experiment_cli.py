from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
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
        filters={"market": "CN_A"},
        candidate_fingerprint="a" * 64,
        selection_fingerprint="b" * 64,
    )


def install_prepare_seams(cli, monkeypatch, *, calls):
    selection = fake_selection()

    def fake_select_universe(**kwargs):
        calls["selection"] = kwargs
        return selection

    def fake_prepare(config, *, output_dir, snapshot_loader):
        calls["prepare"] = {
            "config": config,
            "output_dir": output_dir,
            "snapshot_loader": snapshot_loader,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / cli.EXPERIMENT_FILENAME).write_text("{}", encoding="utf-8")
        return SimpleNamespace(snapshot_count=4, status_counts={"ready": 4})

    monkeypatch.setattr(cli, "select_universe", fake_select_universe)
    monkeypatch.setattr(cli, "prepare_experiment", fake_prepare)
    monkeypatch.setattr(cli, "resolve_latest_market_date", lambda **_: "2025-01-31")


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


def test_existing_directory_requires_resume(tmp_path, monkeypatch):
    cli = load_cli_module()
    config_path = write_config(tmp_path)
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path / "outputs")
    calls: dict[str, object] = {}
    install_prepare_seams(cli, monkeypatch, calls=calls)

    cli.run_experiment(config_path, stage="prepare")
    with pytest.raises(FileExistsError, match="use --resume"):
        cli.run_experiment(config_path, stage="prepare")


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

    summary = cli.run_experiment(config_path, stage="predict")
    assert summary["status"] == "ok"
    assert calls["assert_models"] == ["small"]


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
