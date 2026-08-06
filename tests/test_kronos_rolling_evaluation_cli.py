from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_kronos_rolling_evaluation.py"
)


def load_cli_module():
    spec = importlib.util.spec_from_file_location(
        "run_kronos_rolling_evaluation",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_universe(path: Path, *asset_ids: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["asset_id", "name"])
        writer.writeheader()
        writer.writerows({"asset_id": asset_id, "name": asset_id} for asset_id in asset_ids)


def config_metadata() -> dict[str, object]:
    return {
        "schema_version": 3,
        "config": {
            "asset_ids": ["CN:SH:600418", "CN:SZ:000001"],
            "start_date": "2025-01-03",
            "end_date": "2025-01-03",
            "input_window": 3,
            "roll_step": 1,
            "forecast_horizon": 2,
            "evaluation_horizons": [1, 2],
            "sample_count": 20,
            "models": ["small", "base"],
            "adjust_type": "qfq",
            "db_service": "stock_research",
            "predict_url": "http://prepared.example",
            "token_env": "KRONOS_TEST_TOKEN",
            "timeout_seconds": 7.0,
            "seed": 7,
        },
        "universe": ["CN:SH:600418", "CN:SZ:000001"],
    }


def test_parser_accepts_exact_stages_and_all_stage_options():
    cli = load_cli_module()

    parser = cli.build_parser()
    prepare = parser.parse_args(
        [
            "prepare",
            "--universe-file",
            "universe.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            "out",
            "--input-window",
            "120",
            "--forecast-horizon",
            "10",
            "--horizons",
            "1,3,5,10",
            "--sample-count",
            "20",
            "--seed",
            "7",
            "--adjust-type",
            "qfq",
            "--db-service",
            "stock_research",
            "--timeout-seconds",
            "12.5",
            "--allow-smoke",
        ]
    )
    predict = parser.parse_args(
        [
            "predict",
            "--model",
            "base",
            "--output-dir",
            "out",
            "--predict-url",
            "http://kronos.test",
            "--token-env",
            "TOKEN",
        ]
    )
    report = parser.parse_args(["report", "--output-dir", "out"])

    assert prepare.stage == "prepare"
    assert prepare.horizons == ["1,3,5,10"]
    assert prepare.allow_smoke is True
    assert predict.stage == "predict"
    assert predict.model == "base"
    assert report.stage == "report"


@pytest.mark.parametrize(
    "args",
    [
        ["predict", "--model", "small", "--predict-url", "http://kronos.test"],
        [
            "predict",
            "--model",
            "unsupported",
            "--output-dir",
            "out",
            "--predict-url",
            "http://kronos.test",
        ],
    ],
)
def test_subprocess_parse_errors_emit_one_json_line_without_argparse_noise(args):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert completed.stderr == ""
    lines = completed.stdout.splitlines()
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["stage"] == "predict"
    assert summary["status"] == "error"
    assert summary["error"]


def test_prepare_rejects_non_twenty_universe_without_allow_smoke(tmp_path, monkeypatch, capsys):
    cli = load_cli_module()
    universe = tmp_path / "universe.csv"
    write_universe(universe, "CN:SH:600418", "CN:SZ:000001")

    def should_not_prepare(*args, **kwargs):
        raise AssertionError("prepare_experiment must not run for an invalid universe")

    monkeypatch.setattr(cli, "prepare_experiment", should_not_prepare)
    result = cli.main(
        [
            "prepare",
            "--universe-file",
            str(universe),
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert result != 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["stage"] == "prepare"
    assert summary["status"] == "error"


def test_prepare_allow_smoke_passes_normalized_config_and_prints_one_summary(
    tmp_path,
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    universe = tmp_path / "universe.csv"
    write_universe(universe, "sh.600418", "000001.SZ")
    captured: dict[str, object] = {}

    def fake_prepare(config, *, output_dir):
        captured["config"] = config
        captured["output_dir"] = output_dir
        return SimpleNamespace(
            snapshot_count=2,
            status_counts={"ready": 2},
        )

    monkeypatch.setattr(cli, "prepare_experiment", fake_prepare)
    result = cli.main(
        [
            "prepare",
            "--universe-file",
            str(universe),
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path / "out"),
            "--input-window",
            "120",
            "--forecast-horizon",
            "5",
            "--horizons",
            "1,3,5",
            "--sample-count",
            "20",
            "--seed",
            "7",
            "--allow-smoke",
        ]
    )

    assert result == 0
    config = captured["config"]
    assert config.asset_ids == ("CN:SH:600418", "CN:SZ:000001")
    assert config.input_window == 120
    assert config.forecast_horizon == 5
    assert config.evaluation_horizons == (1, 3, 5)
    assert config.seed == 7
    assert captured["output_dir"] == tmp_path / "out"
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "asset_count": 2,
        "output_dir": str(tmp_path / "out"),
        "snapshot_count": 2,
        "stage": "prepare",
        "status": "ok",
        "status_counts": {"ready": 2},
    }


@pytest.mark.parametrize(
    "extra",
    [
        ["--forecast-horizon", "0"],
        ["--forecast-horizon", "11"],
        ["--horizons", "1,11"],
    ],
)
def test_prepare_invalid_horizon_returns_nonzero(tmp_path, extra, capsys):
    cli = load_cli_module()
    universe = tmp_path / "universe.csv"
    write_universe(universe, "CN:SH:600418", "CN:SZ:000001")

    result = cli.main(
        [
            "prepare",
            "--universe-file",
            str(universe),
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path / "out"),
            "--allow-smoke",
            *extra,
        ]
    )

    assert result != 0
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_prepare_missing_universe_file_returns_nonzero(tmp_path, capsys):
    cli = load_cli_module()
    result = cli.main(
        [
            "prepare",
            "--universe-file",
            str(tmp_path / "missing.csv"),
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path / "out"),
            "--allow-smoke",
        ]
    )

    assert result != 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["stage"] == "prepare"
    assert "missing" in summary["error"]


class FakePredictClient:
    instances: list["FakePredictClient"] = []

    def __init__(self, base_url, *, token, timeout):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.asserted_models: list[str] = []
        self.closed = False
        self.__class__.instances.append(self)

    def assert_model(self, model):
        self.asserted_models.append(model)
        return {"status": "ok", "model": model}

    def close(self):
        self.closed = True


def test_predict_base_uses_only_base_and_frozen_experiment_metadata(
    tmp_path,
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    (output_dir / "experiment.json").write_text(
        json.dumps(config_metadata()),
        encoding="utf-8",
    )
    (output_dir / "input_snapshots").mkdir()
    calls: list[dict[str, object]] = []

    def fake_run_model(config, *, model, output_dir, client):
        calls.append(
            {
                "config": config,
                "model": model,
                "output_dir": output_dir,
                "client": client,
            }
        )
        return SimpleNamespace(
            attempted_count=2,
            cache_hit_count=0,
            skipped_count=0,
            status_counts={"success": 2},
        )

    FakePredictClient.instances.clear()
    monkeypatch.setattr(cli, "KronosClient", FakePredictClient)
    monkeypatch.setattr(cli, "run_model", fake_run_model)
    monkeypatch.setenv("KRONOS_TEST_TOKEN", "test-token")

    result = cli.main(
        [
            "predict",
            "--model",
            "base",
            "--output-dir",
            str(output_dir),
            "--predict-url",
            "http://kronos.test",
        ]
    )

    assert result == 0
    assert len(calls) == 1
    assert calls[0]["model"] == "base"
    assert calls[0]["output_dir"] == output_dir
    assert calls[0]["config"].asset_ids == ("CN:SH:600418", "CN:SZ:000001")
    client = FakePredictClient.instances[0]
    assert client.base_url == "http://kronos.test"
    assert client.token == "test-token"
    assert client.asserted_models == ["base"]
    summary = json.loads(capsys.readouterr().out)
    assert summary["stage"] == "predict"
    assert summary["model"] == "base"
    assert summary["status"] == "ok"


@pytest.mark.parametrize(
    ("status_counts", "expected_status", "expected_result"),
    [
        ({"unavailable": 2}, "error", 1),
        ({"success": 1, "unavailable": 1}, "partial", 0),
    ],
)
def test_predict_derives_summary_status_from_model_status_counts(
    tmp_path,
    monkeypatch,
    capsys,
    status_counts,
    expected_status,
    expected_result,
):
    cli = load_cli_module()
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    (output_dir / "experiment.json").write_text(
        json.dumps(config_metadata()),
        encoding="utf-8",
    )
    (output_dir / "input_snapshots").mkdir()

    monkeypatch.setattr(cli, "KronosClient", FakePredictClient)
    monkeypatch.setattr(
        cli,
        "run_model",
        lambda *args, **kwargs: SimpleNamespace(
            attempted_count=2,
            cache_hit_count=0,
            skipped_count=0,
            status_counts=status_counts,
        ),
    )
    monkeypatch.setenv("KRONOS_TEST_TOKEN", "test-token")

    result = cli.main(
        [
            "predict",
            "--model",
            "small",
            "--output-dir",
            str(output_dir),
            "--predict-url",
            "http://kronos.test",
        ]
    )

    assert result == expected_result
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == expected_status
    assert summary["status_counts"] == status_counts


def test_predict_rejects_symlink_output_dir_before_constructing_client(
    tmp_path,
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    real_output_dir = tmp_path / "real"
    real_output_dir.mkdir()
    (real_output_dir / "experiment.json").write_text(
        json.dumps(config_metadata()),
        encoding="utf-8",
    )
    (real_output_dir / "input_snapshots").mkdir()
    symlink_output_dir = tmp_path / "prepared"
    symlink_output_dir.symlink_to(real_output_dir, target_is_directory=True)
    constructed = False

    class MustNotConstruct:
        def __init__(self, *args, **kwargs):
            nonlocal constructed
            constructed = True
            raise AssertionError("client must not be constructed")

    monkeypatch.setattr(cli, "KronosClient", MustNotConstruct)
    monkeypatch.setenv("KRONOS_TEST_TOKEN", "test-token")

    result = cli.main(
        [
            "predict",
            "--model",
            "small",
            "--output-dir",
            str(symlink_output_dir),
            "--predict-url",
            "http://kronos.test",
        ]
    )

    assert result != 0
    assert constructed is False
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "error"
    assert "symlink" in summary["error"]


def test_predict_rejects_symlink_metadata_before_constructing_client(
    tmp_path,
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    metadata_source = tmp_path / "experiment.json"
    metadata_source.write_text(json.dumps(config_metadata()), encoding="utf-8")
    (output_dir / "experiment.json").symlink_to(metadata_source)
    (output_dir / "input_snapshots").mkdir()
    constructed = False

    class MustNotConstruct:
        def __init__(self, *args, **kwargs):
            nonlocal constructed
            constructed = True
            raise AssertionError("client must not be constructed")

    monkeypatch.setattr(cli, "KronosClient", MustNotConstruct)
    monkeypatch.setenv("KRONOS_TEST_TOKEN", "test-token")

    result = cli.main(
        [
            "predict",
            "--model",
            "small",
            "--output-dir",
            str(output_dir),
            "--predict-url",
            "http://kronos.test",
        ]
    )

    assert result != 0
    assert constructed is False
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "error"
    assert "symlink" in summary["error"]


def _predict_args(output_dir: Path) -> list[str]:
    return [
        "predict",
        "--model",
        "small",
        "--output-dir",
        str(output_dir),
        "--predict-url",
        "http://kronos.test",
    ]


def _assert_predict_tree_symlink_is_rejected(
    cli,
    output_dir: Path,
    monkeypatch,
    capsys,
) -> None:
    (output_dir / "experiment.json").write_text(
        json.dumps(config_metadata()),
        encoding="utf-8",
    )
    (output_dir / "input_snapshots").mkdir(exist_ok=True)
    FakePredictClient.instances.clear()
    monkeypatch.setattr(cli, "KronosClient", FakePredictClient)
    monkeypatch.setattr(
        cli,
        "run_model",
        lambda *args, **kwargs: pytest.fail("run_model must not run"),
    )
    monkeypatch.setenv("KRONOS_TEST_TOKEN", "test-token")

    result = cli.main(_predict_args(output_dir))

    assert result != 0
    assert (
        sum(len(instance.asserted_models) for instance in FakePredictClient.instances)
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "error"
    assert "symlink" in summary["error"]


def test_predict_rejects_symlinked_snapshot_file_before_assert_model(
    tmp_path,
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    snapshot_source = tmp_path / "snapshot-source.json"
    snapshot_source.write_text("{}", encoding="utf-8")
    (output_dir / "input_snapshots").mkdir()
    (output_dir / "input_snapshots" / "snapshot.json").symlink_to(snapshot_source)

    _assert_predict_tree_symlink_is_rejected(cli, output_dir, monkeypatch, capsys)


def test_predict_rejects_symlinked_top_level_artifact_before_assert_model(
    tmp_path,
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    artifact_source = tmp_path / "forecast-source.parquet"
    artifact_source.write_bytes(b"not parquet")
    (output_dir / "forecast_bars.parquet").symlink_to(artifact_source)

    _assert_predict_tree_symlink_is_rejected(cli, output_dir, monkeypatch, capsys)


def test_predict_rejects_symlinked_output_parent_before_assert_model(
    tmp_path,
    monkeypatch,
    capsys,
):
    cli = load_cli_module()
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    symlink_parent = tmp_path / "symlink-parent"
    symlink_parent.symlink_to(real_parent, target_is_directory=True)
    output_dir = symlink_parent / "prepared"
    output_dir.mkdir()

    _assert_predict_tree_symlink_is_rejected(cli, output_dir, monkeypatch, capsys)


def test_predict_refuses_missing_preparation_metadata(tmp_path, monkeypatch, capsys):
    cli = load_cli_module()
    monkeypatch.setattr(cli, "run_model", lambda *args, **kwargs: pytest.fail("must not run"))

    result = cli.main(
        [
            "predict",
            "--model",
            "small",
            "--output-dir",
            str(tmp_path / "missing"),
            "--predict-url",
            "http://kronos.test",
        ]
    )

    assert result != 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["stage"] == "predict"
    assert summary["status"] == "error"


def test_predict_refuses_health_model_mismatch(tmp_path, monkeypatch, capsys):
    cli = load_cli_module()
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    (output_dir / "experiment.json").write_text(
        json.dumps(config_metadata()),
        encoding="utf-8",
    )
    (output_dir / "input_snapshots").mkdir()

    class MismatchClient(FakePredictClient):
        def assert_model(self, model):
            raise RuntimeError("active Kronos model is small, requested base")

    monkeypatch.setattr(cli, "KronosClient", MismatchClient)
    monkeypatch.setattr(cli, "run_model", lambda *args, **kwargs: pytest.fail("must not run"))
    monkeypatch.setenv("KRONOS_TEST_TOKEN", "test-token")

    result = cli.main(
        [
            "predict",
            "--model",
            "base",
            "--output-dir",
            str(output_dir),
            "--predict-url",
            "http://kronos.test",
        ]
    )

    assert result != 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["stage"] == "predict"
    assert "active Kronos model" in summary["error"]


def test_report_calls_existing_runner_and_prints_one_json_line(tmp_path, monkeypatch, capsys):
    cli = load_cli_module()
    captured: list[Path] = []

    def fake_build_report(*, output_dir):
        captured.append(output_dir)
        return {"generation": "g1", "conclusion": "not_proven"}

    monkeypatch.setattr(cli, "build_report", fake_build_report)
    result = cli.main(["report", "--output-dir", str(tmp_path / "out")])

    assert result == 0
    assert captured == [tmp_path / "out"]
    assert json.loads(capsys.readouterr().out) == {
        "conclusion": "not_proven",
        "generation": "g1",
        "output_dir": str(tmp_path / "out"),
        "stage": "report",
        "status": "ok",
    }
