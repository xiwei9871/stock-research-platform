import os
import subprocess
import sys
from pathlib import Path

import pytest

from stock_research import cli


def _result(*, expected=None, early=None):
    return {
        "paths": {
            "evidence": "/tmp/consumer/evidence.csv",
            "expected": "/tmp/consumer/expected.csv",
            "early": "/tmp/consumer/early.csv",
            "scores": "/tmp/consumer/scores.csv",
            "exclusions": "/tmp/consumer/exclusions.csv",
            "coverage": "/tmp/consumer/coverage.json",
            "report": "/tmp/consumer/report.md",
        },
        "expected": [1, 2] if expected is None else expected,
        "early": [1] if early is None else early,
    }


def _evaluation_result():
    return {
        "paths": {
            "detail": "/tmp/evaluation/detail.csv",
            "summary": "/tmp/evaluation/summary.csv",
            "report": "/tmp/evaluation/report.md",
        }
    }


def test_consumer_oversold_evaluate_dispatches_and_prints_machine_lines(monkeypatch, capsys):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _evaluation_result()

    monkeypatch.setattr(cli, "_run_consumer_oversold_evaluation", fake_run)

    cli.main_for_args(
        [
            "consumer-oversold-evaluate",
            "--snapshots-root",
            "/tmp/snapshots",
            "--end-date",
            "2026-07-30",
            "--output-dir",
            "/tmp/evaluation",
            "--service",
            "research_custom",
        ]
    )

    assert captured == {
        "snapshots_root": "/tmp/snapshots",
        "end_date": "2026-07-30",
        "output_dir": "/tmp/evaluation",
        "service": "research_custom",
    }
    assert capsys.readouterr().out.splitlines() == [
        "consumer_oversold_evaluation|detail|/tmp/evaluation/detail.csv",
        "consumer_oversold_evaluation|summary|/tmp/evaluation/summary.csv",
        "consumer_oversold_evaluation|report|/tmp/evaluation/report.md",
    ]


@pytest.mark.parametrize(
    ("option", "unsafe_value"),
    [
        ("--snapshots-root", "snapshots|forged"),
        ("--snapshots-root", "snapshots\rforged"),
        ("--output-dir", "output\nconsumer_oversold_evaluation|report|forged"),
    ],
)
def test_consumer_oversold_evaluate_rejects_unsafe_paths_before_runner(
    monkeypatch, capsys, option, unsafe_value
):
    called = False

    def fake_run(**kwargs):
        nonlocal called
        called = True
        return _evaluation_result()

    monkeypatch.setattr(cli, "_run_consumer_oversold_evaluation", fake_run)
    argv = [
        "consumer-oversold-evaluate",
        "--snapshots-root",
        "snapshots",
        "--end-date",
        "2026-07-30",
        "--output-dir",
        "evaluation",
    ]
    argv[argv.index(option) + 1] = unsafe_value

    with pytest.raises(ValueError, match="must not contain"):
        cli.main_for_args(argv)

    assert called is False
    assert capsys.readouterr().out == ""


def test_consumer_oversold_weekly_dispatches_and_prints_machine_lines(monkeypatch, capsys):
    captured = {}

    def fake_run(*, trade_date, evidence_path, output_dir, service):
        captured.update(
            trade_date=trade_date,
            evidence_path=evidence_path,
            output_dir=output_dir,
            service=service,
        )
        return _result()

    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", fake_run)

    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--trade-date",
            "2026-07-29",
            "--evidence-path",
            "/tmp/evidence.csv",
            "--output-dir",
            "/tmp/consumer",
            "--service",
            "research_custom",
        ]
    )

    assert captured == {
        "trade_date": "2026-07-29",
        "evidence_path": "/tmp/evidence.csv",
        "output_dir": "/tmp/consumer",
        "service": "research_custom",
    }
    assert capsys.readouterr().out.splitlines() == [
        "consumer_oversold|evidence|/tmp/consumer/evidence.csv",
        "consumer_oversold|expected|/tmp/consumer/expected.csv",
        "consumer_oversold|early|/tmp/consumer/early.csv",
        "consumer_oversold|scores|/tmp/consumer/scores.csv",
        "consumer_oversold|exclusions|/tmp/consumer/exclusions.csv",
        "consumer_oversold|coverage|/tmp/consumer/coverage.json",
        "consumer_oversold|report|/tmp/consumer/report.md",
        "consumer_oversold|expected_rows|2",
        "consumer_oversold|early_rows|1",
    ]


def test_consumer_oversold_weekly_defaults_to_configured_service(monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _result(expected=[], early=[])

    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", fake_run)

    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--trade-date",
            "2026-07-29",
            "--evidence-path",
            "evidence.csv",
            "--output-dir",
            "output",
        ]
    )

    assert captured["service"] == cli.SETTINGS.research_service


@pytest.mark.parametrize("missing_option", ["--trade-date", "--evidence-path", "--output-dir"])
def test_consumer_oversold_weekly_requires_inputs(missing_option):
    argv = [
        "consumer-oversold-weekly",
        "--trade-date",
        "2026-07-29",
        "--evidence-path",
        "evidence.csv",
        "--output-dir",
        "output",
    ]
    option_index = argv.index(missing_option)
    del argv[option_index : option_index + 2]

    with pytest.raises(SystemExit):
        cli.main_for_args(argv)


def test_consumer_oversold_weekly_propagates_runner_exception(monkeypatch):
    def fake_run(**kwargs):
        raise RuntimeError("weekly pipeline failed")

    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", fake_run)

    with pytest.raises(RuntimeError, match="weekly pipeline failed"):
        cli.main_for_args(
            [
                "consumer-oversold-weekly",
                "--trade-date",
                "2026-07-29",
                "--evidence-path",
                "evidence.csv",
                "--output-dir",
                "output",
            ]
        )


def test_consumer_oversold_weekly_prints_zero_for_empty_rankings(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_run_consumer_oversold_weekly",
        lambda **kwargs: _result(expected=[], early=[]),
    )

    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--trade-date",
            "2026-07-29",
            "--evidence-path",
            "evidence.csv",
            "--output-dir",
            "output",
        ]
    )

    assert capsys.readouterr().out.splitlines()[-2:] == [
        "consumer_oversold|expected_rows|0",
        "consumer_oversold|early_rows|0",
    ]


def test_consumer_oversold_weekly_does_not_hide_missing_result_keys(monkeypatch, capsys):
    result = _result()
    del result["paths"]["coverage"]
    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", lambda **kwargs: result)

    with pytest.raises(KeyError, match="coverage"):
        cli.main_for_args(
            [
                "consumer-oversold-weekly",
                "--trade-date",
                "2026-07-29",
                "--evidence-path",
                "evidence.csv",
                "--output-dir",
                "output",
            ]
        )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("option", "unsafe_value"),
    [
        ("--evidence-path", "evidence|forged.csv"),
        ("--evidence-path", "evidence\rforged.csv"),
        ("--output-dir", "output\nconsumer_oversold|report|forged"),
    ],
)
def test_consumer_oversold_weekly_rejects_unsafe_input_paths_before_runner(
    monkeypatch, capsys, option, unsafe_value
):
    called = False

    def fake_run(**kwargs):
        nonlocal called
        called = True
        return _result()

    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", fake_run)
    argv = [
        "consumer-oversold-weekly",
        "--trade-date",
        "2026-07-29",
        "--evidence-path",
        "evidence.csv",
        "--output-dir",
        "output",
    ]
    argv[argv.index(option) + 1] = unsafe_value

    with pytest.raises(ValueError, match="must not contain"):
        cli.main_for_args(argv)

    assert called is False
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "mutate",
    [
        lambda result: result.update(paths=[]),
        lambda result: result["paths"].update(expected=123),
        lambda result: result["paths"].update(report="report|forged.md"),
        lambda result: result["paths"].update(coverage="coverage\rforged.json"),
        lambda result: result["paths"].update(scores="scores\nforged.csv"),
        lambda result: result["paths"].update(extra="extra.csv"),
    ],
)
def test_consumer_oversold_weekly_validates_all_result_paths_before_printing(
    monkeypatch, capsys, mutate
):
    result = _result()
    mutate(result)
    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", lambda **kwargs: result)

    with pytest.raises(ValueError):
        cli.main_for_args(
            [
                "consumer-oversold-weekly",
                "--trade-date",
                "2026-07-29",
                "--evidence-path",
                "evidence.csv",
                "--output-dir",
                "output",
            ]
        )

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("ranking_key", ["expected", "early"])
def test_consumer_oversold_weekly_validates_row_counts_before_printing(
    monkeypatch, capsys, ranking_key
):
    result = _result()
    result[ranking_key] = object()
    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", lambda **kwargs: result)

    with pytest.raises(TypeError):
        cli.main_for_args(
            [
                "consumer-oversold-weekly",
                "--trade-date",
                "2026-07-29",
                "--evidence-path",
                "evidence.csv",
                "--output-dir",
                "output",
            ]
        )

    assert capsys.readouterr().out == ""


def test_existing_parser_command_still_parses():
    args = cli.build_parser().parse_args(["apply-schema"])

    assert args.command == "apply-schema"


def test_unrelated_parser_import_does_not_load_consumer_pipeline():
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from stock_research import cli; "
                "cli.build_parser().parse_args(['apply-schema']); "
                "assert 'stock_research.consumer_oversold.pipeline' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(project_root / "src")},
    )

    assert completed.returncode == 0, completed.stderr
