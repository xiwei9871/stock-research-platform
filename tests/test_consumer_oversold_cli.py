import pytest

from stock_research import cli


def _result(*, expected=None, early=None):
    return {
        "paths": {
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

    monkeypatch.setattr(cli, "run_consumer_oversold_weekly", fake_run)

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

    monkeypatch.setattr(cli, "run_consumer_oversold_weekly", fake_run)

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

    monkeypatch.setattr(cli, "run_consumer_oversold_weekly", fake_run)

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
        "run_consumer_oversold_weekly",
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


def test_consumer_oversold_weekly_does_not_hide_missing_result_keys(monkeypatch):
    result = _result()
    del result["paths"]["coverage"]
    monkeypatch.setattr(cli, "run_consumer_oversold_weekly", lambda **kwargs: result)

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


def test_existing_parser_command_still_parses():
    args = cli.build_parser().parse_args(["apply-schema"])

    assert args.command == "apply-schema"
