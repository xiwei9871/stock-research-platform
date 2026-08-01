import os
import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from stock_research import cli


def _result(*, top20=None, reserve=None, preaudit=None, ranking_version="v1"):
    paths = {
        "evidence": "/tmp/consumer/evidence.csv",
        "scores": "/tmp/consumer/scores.csv",
        "exclusions": "/tmp/consumer/exclusions.csv",
        "coverage": "/tmp/consumer/coverage.json",
        "report": "/tmp/consumer/report.md",
        "top20": "/tmp/consumer/top20.csv",
        "reserve": "/tmp/consumer/reserve.csv",
        "preaudit": "/tmp/consumer/preaudit.csv",
        "comparison": "/tmp/consumer/comparison.csv",
    }
    if ranking_version == "v2":
        paths.update(
            top30="/tmp/consumer/top30.csv",
            ranked_pool="/tmp/consumer/ranked_pool.csv",
        )
    return {
        "paths": paths,
        "top20": [1, 2] if top20 is None else top20,
        "top30": [1, 2, 3] if ranking_version == "v2" else [],
        "ranked_pool": [1, 2, 3, 4] if ranking_version == "v2" else [],
        "reserve": [1] if reserve is None else reserve,
        "preaudit": [1, 2, 3] if preaudit is None else preaudit,
        "coverage": {
            "publication_status": "ready",
            "ranking_version": ranking_version,
        },
        "as_of_trade_date": "2026-07-29",
        "date_mode": "explicit_backtest",
        "publication_status": "ready",
    }


def _evaluation_result():
    return {
        "paths": {
            "detail": "/tmp/evaluation/detail.csv",
            "summary": "/tmp/evaluation/summary.csv",
            "report": "/tmp/evaluation/report.md",
        }
    }


def _blocked_result(*, ranking_version="v1", status="blocked_missing_data"):
    return {
        "paths": {
            "coverage": "/tmp/gap/coverage.json",
            "backfill_request": "/tmp/gap/backfill.json",
            "report": "/tmp/gap/report.md",
        },
        "top20": [],
        "reserve": [],
        "preaudit": [],
        "coverage": {
            "ranking_version": ranking_version,
            "publication_status": status,
        },
        "as_of_trade_date": "2026-07-29",
        "date_mode": "explicit_backtest",
        "publication_status": status,
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

    def fake_run(
        *, trade_date, evidence_path, output_dir, service, preaudit_only, ranking_version
    ):
        captured.update(
            trade_date=trade_date,
            evidence_path=evidence_path,
            output_dir=output_dir,
            service=service,
            preaudit_only=preaudit_only,
            ranking_version=ranking_version,
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
        "preaudit_only": False,
        "ranking_version": "v1",
    }
    assert capsys.readouterr().out.splitlines() == [
        "consumer_oversold|evidence|/tmp/consumer/evidence.csv",
        "consumer_oversold|scores|/tmp/consumer/scores.csv",
        "consumer_oversold|exclusions|/tmp/consumer/exclusions.csv",
        "consumer_oversold|coverage|/tmp/consumer/coverage.json",
        "consumer_oversold|report|/tmp/consumer/report.md",
        "consumer_oversold|top20|/tmp/consumer/top20.csv",
        "consumer_oversold|reserve|/tmp/consumer/reserve.csv",
        "consumer_oversold|preaudit|/tmp/consumer/preaudit.csv",
        "consumer_oversold|comparison|/tmp/consumer/comparison.csv",
        "consumer_oversold|ranking_version|v1",
        "consumer_oversold|top20_rows|2",
        "consumer_oversold|reserve_rows|1",
        "consumer_oversold|preaudit_rows|3",
        "consumer_oversold|as_of_trade_date|2026-07-29",
        "consumer_oversold|date_mode|explicit_backtest",
        "consumer_oversold|publication_status|ready",
    ]


def test_consumer_oversold_weekly_blocked_result_prints_gap_artifacts(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        cli,
        "_run_consumer_oversold_weekly",
        lambda **kwargs: _blocked_result(),
    )

    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--trade-date",
            "2026-07-29",
            "--evidence-path",
            "/tmp/gap/evidence.csv",
            "--output-dir",
            "/tmp/gap",
        ]
    )

    assert capsys.readouterr().out.splitlines() == [
        "consumer_oversold|coverage|/tmp/gap/coverage.json",
        "consumer_oversold|backfill_request|/tmp/gap/backfill.json",
        "consumer_oversold|report|/tmp/gap/report.md",
        "consumer_oversold|ranking_version|v1",
        "consumer_oversold|publication_status|blocked_missing_data",
    ]


def test_consumer_oversold_weekly_omitted_date_uses_latest_complete_resolver(
    monkeypatch, capsys
):
    captured = {}

    def fake_resolver(*, service):
        captured["resolver_service"] = service
        return "2026-07-30"

    monkeypatch.setattr(cli, "_resolve_latest_complete_consumer_trade_date", fake_resolver)

    def fake_run(**kwargs):
        captured.update(kwargs)
        result = _result()
        result["coverage"]["publication_status"] = "coverage_insufficient"
        return result

    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", fake_run)
    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--evidence-path",
            "evidence.csv",
            "--output-dir",
            "output",
            "--service",
            "research_custom",
        ]
    )

    assert captured["resolver_service"] == "research_custom"
    assert captured["trade_date"] == "2026-07-30"
    assert capsys.readouterr().out.splitlines()[-3:] == [
        "consumer_oversold|as_of_trade_date|2026-07-30",
        "consumer_oversold|date_mode|latest_complete_daily",
        "consumer_oversold|publication_status|coverage_insufficient",
    ]


def test_consumer_oversold_weekly_explicit_date_skips_resolver(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_resolve_latest_complete_consumer_trade_date",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("resolver must not run")),
    )
    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", lambda **kwargs: _result())

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


def test_consumer_oversold_weekly_rejects_invalid_explicit_date_before_runner(
    monkeypatch,
):
    monkeypatch.setattr(
        cli,
        "_resolve_latest_complete_consumer_trade_date",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("resolver must not run")),
    )
    monkeypatch.setattr(
        cli,
        "_run_consumer_oversold_weekly",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("runner must not run")),
    )

    with pytest.raises(ValueError, match="trade_date"):
        cli.main_for_args(
            [
                "consumer-oversold-weekly",
                "--trade-date",
                "20260729",
                "--evidence-path",
                "evidence.csv",
                "--output-dir",
                "output",
            ]
        )


def test_consumer_oversold_weekly_preaudit_flag_reaches_runner(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cli,
        "_resolve_latest_complete_consumer_trade_date",
        lambda *, service: "2026-07-30",
    )

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _result(top20=[], reserve=[])

    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", fake_run)
    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--evidence-path",
            "evidence.csv",
            "--output-dir",
            "output",
            "--preaudit-only",
        ]
    )

    assert captured["preaudit_only"] is True


def test_consumer_oversold_weekly_defaults_to_configured_service(monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _result(top20=[], reserve=[], preaudit=[])

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


@pytest.mark.parametrize("missing_option", ["--evidence-path", "--output-dir"])
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
        lambda **kwargs: _result(top20=[], reserve=[], preaudit=[]),
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

    assert capsys.readouterr().out.splitlines()[-6:-3] == [
        "consumer_oversold|top20_rows|0",
        "consumer_oversold|reserve_rows|0",
        "consumer_oversold|preaudit_rows|0",
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


def test_consumer_oversold_weekly_rejects_runner_ranking_version_mismatch(
    monkeypatch, capsys
):
    result = _result()
    result["coverage"]["ranking_version"] = "v2"
    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", lambda **kwargs: result)

    with pytest.raises(ValueError, match="ranking_version"):
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
        lambda result: result["paths"].update(top20=123),
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


@pytest.mark.parametrize("ranking_key", ["top20", "reserve", "preaudit"])
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


@pytest.mark.parametrize(
    "mutate",
    [
        lambda result: result.pop("as_of_trade_date"),
        lambda result: result.update(as_of_trade_date="20260730"),
        lambda result: result.update(date_mode="latest_complete_daily\nforged"),
        lambda result: result.update(publication_status="ready|forged"),
    ],
)
def test_consumer_oversold_machine_lines_reject_invalid_metadata(mutate):
    result = _result()
    mutate(result)

    with pytest.raises((KeyError, ValueError)):
        cli._consumer_oversold_machine_lines(result)


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


def test_consumer_oversold_weekly_accepts_v2_and_isolates_output_dir(
    monkeypatch, capsys
):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _result(ranking_version="v2")

    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", fake_run)
    monkeypatch.setattr(
        cli,
        "_validate_consumer_oversold_retrospective_evidence",
        lambda **kwargs: {
            "evidence_reconstruction_mode": "retrospective_point_in_time",
            "evidence_information_cutoff": "2026-07-27",
        },
    )

    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--trade-date",
            "2026-07-27",
            "--ranking-version",
            "v2",
            "--evidence-path",
            "evidence.csv",
            "--output-dir",
            "output",
        ]
    )

    assert captured["ranking_version"] == "v2"
    assert captured["output_dir"] == str(Path("output") / "v2")
    assert captured["evidence_reconstruction_mode"] == "retrospective_point_in_time"
    assert captured["evidence_information_cutoff"] == "2026-07-27"
    output = capsys.readouterr().out.splitlines()
    assert "consumer_oversold|top30|/tmp/consumer/top30.csv" in output
    assert "consumer_oversold|ranking_version|v2" in output


def test_consumer_oversold_weekly_rejects_non_lowercase_ranking_version():
    with pytest.raises(SystemExit):
        cli.main_for_args(
            [
                "consumer-oversold-weekly",
                "--trade-date",
                "2026-07-27",
                "--ranking-version",
                "V2",
                "--evidence-path",
                "evidence.csv",
                "--output-dir",
                "output",
            ]
        )


def test_consumer_oversold_v2_output_never_nests_inside_v1_directory():
    assert cli._consumer_oversold_output_dir("output/2026-07-27/v1", "v2") == (
        "output/2026-07-27/v2"
    )
    assert cli._consumer_oversold_output_dir("output/2026-07-27/v2", "v2") == (
        "output/2026-07-27/v2"
    )
    assert cli._consumer_oversold_output_dir("output/2026-07-27/v1", "v1") == (
        "output/2026-07-27/v1"
    )


def test_retrospective_evidence_rejects_any_future_underlying_publication(tmp_path):
    evidence_path = tmp_path / "evidence.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "A",
                "source_publish_date": "2026-07-20",
                "audit_review_source_publish_date": "2026-07-21",
                "pledge_debt_review_source_publish_date": "2026-07-28",
                "permanent_impairment_source_publish_date": "2026-07-22",
            }
        ]
    ).to_csv(evidence_path, index=False)

    with pytest.raises(ValueError, match="future evidence publication"):
        cli._validate_consumer_oversold_retrospective_evidence(
            evidence_path=str(evidence_path), information_cutoff="2026-07-27"
        )


def test_retrospective_evidence_returns_point_in_time_provenance(tmp_path):
    evidence_path = tmp_path / "evidence.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "A",
                "evidence_as_of_date": "2026-07-31",
                "source_publish_date": "2026-07-20",
                "audit_review_source_publish_date": "2026-07-21",
                "pledge_debt_review_source_publish_date": "2026-07-22",
                "permanent_impairment_source_publish_date": "2026-07-23",
            }
        ]
    ).to_csv(evidence_path, index=False)

    assert cli._validate_consumer_oversold_retrospective_evidence(
        evidence_path=str(evidence_path), information_cutoff="2026-07-27"
    ) == {
        "evidence_reconstruction_mode": "retrospective_point_in_time",
        "evidence_information_cutoff": "2026-07-27",
    }


def _sealed_v2_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    root = tmp_path / "snapshot"
    release = root / ".releases" / "consumer-oversold-test"
    release.mkdir(parents=True)
    for filename in V2_OUTPUT_FILENAMES.values():
        (release / filename).write_text("payload\n", encoding="utf-8")
    manifest_lines = [
        f"{hashlib.sha256((release / filename).read_bytes()).hexdigest()}  {filename}"
        for filename in sorted(V2_OUTPUT_FILENAMES.values())
    ]
    manifest = release / ".manifest.sha256"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    for path in release.iterdir():
        path.chmod(0o444)
    release.chmod(0o555)
    (root / "current").symlink_to(Path(".releases") / release.name)
    return root / "current", release


def _valid_v2_snapshot_rank_frames(
    *, pool_size: int = 3, trade_date: str = "2026-07-29"
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    rows = []
    for rank in range(1, pool_size + 1):
        repair_percentile = 101.0 - rank
        activation_percentile = 96.0 - rank
        rows.append(
            {
                "asset_id": f"A{rank}",
                "final_rank": rank,
                "trade_date": trade_date,
                "ranking_version": "v2",
                "final_rank_score_v2": (
                    0.55 * repair_percentile + 0.45 * activation_percentile
                ),
                "repair_rank_percentile": repair_percentile,
                "activation_rank_percentile": activation_percentile,
                "composite_score": 60.0,
                "activation_score": 67.5,
                "technical_readiness_score": 75.0,
                "continuation_character_score": 70.0,
                "residual_price_space_score": 65.0,
                "capital_efficiency_score": 60.0,
                "catalyst_timing_score": 55.0,
                "evidence_complete": True,
                "eligible": True,
                "activation_coverage": True,
                "activation_eligible": True,
                "activation_exclusion_reasons": "",
                "falling_knife": False,
                "overextended": False,
            }
        )
    ranked_pool = pd.DataFrame(rows)
    frames = {
        "ranked_pool": ranked_pool,
        "top20": ranked_pool.iloc[: min(20, pool_size)].copy(deep=True),
        "top30": ranked_pool.iloc[: min(30, pool_size)].copy(deep=True),
    }
    coverage = {
        "trade_date": trade_date,
        "ranking_version": "v2",
        "final_top_n": 20,
        "reserve_top_n": 20,
        "v2_ranked_pool_count": pool_size,
        "v2_top30_count": min(30, pool_size),
        "v2_rank_weights": {"repair": 0.55, "activation": 0.45},
        "v2_activation_weights": {
            "technical_readiness": 0.30,
            "continuation_character": 0.25,
            "residual_price_space": 0.20,
            "capital_efficiency": 0.15,
            "catalyst_timing": 0.10,
        },
    }
    return frames, coverage


def _write_snapshot_rank_frames(
    release: Path,
    frames: dict[str, pd.DataFrame],
    coverage: dict[str, object],
) -> None:
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    (release / V2_OUTPUT_FILENAMES["coverage"]).write_text(
        json.dumps(coverage), encoding="utf-8"
    )
    for key, frame in frames.items():
        frame.to_csv(release / V2_OUTPUT_FILENAMES[key], index=False)


def test_v2_snapshot_requires_verified_read_only_current_release(tmp_path):
    current, release = _sealed_v2_snapshot(tmp_path)
    try:
        assert cli._verified_consumer_oversold_v2_release(str(current)) == release.resolve()
        release.chmod(0o755)
        with pytest.raises(ValueError, match="sealed V2 snapshot"):
            cli._verified_consumer_oversold_v2_release(str(current))
    finally:
        release.chmod(0o755)
        for path in release.iterdir():
            path.chmod(0o644)


def test_v2_snapshot_rejects_manifest_tampering(tmp_path):
    current, release = _sealed_v2_snapshot(tmp_path)
    try:
        artifact = next(
            path for path in release.iterdir() if path.name != ".manifest.sha256"
        )
        artifact.chmod(0o644)
        artifact.write_text("tampered\n", encoding="utf-8")
        artifact.chmod(0o444)
        with pytest.raises(ValueError, match="sealed V2 snapshot"):
            cli._verified_consumer_oversold_v2_release(str(current))
    finally:
        release.chmod(0o755)
        for path in release.iterdir():
            path.chmod(0o644)


def test_v2_snapshot_rejects_symlinked_releases_directory(tmp_path):
    current, release = _sealed_v2_snapshot(tmp_path)
    releases_dir = current.parent / ".releases"
    real_releases_dir = tmp_path / "real-releases"
    releases_dir.rename(real_releases_dir)
    releases_dir.symlink_to(real_releases_dir, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="sealed V2 snapshot"):
            cli._verified_consumer_oversold_v2_release(str(current))
    finally:
        releases_dir.unlink()
        real_releases_dir.rename(releases_dir)
        release.chmod(0o755)
        for path in release.iterdir():
            path.chmod(0o644)


def test_v2_snapshot_rejects_symlinked_release_alias(tmp_path):
    current, release = _sealed_v2_snapshot(tmp_path)
    real_release = tmp_path / "real-release"
    release.chmod(0o755)
    release.rename(real_release)
    release.symlink_to(real_release, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="sealed V2 snapshot"):
            cli._verified_consumer_oversold_v2_release(str(current))
    finally:
        release.unlink()
        real_release.rename(release)
        release.chmod(0o755)
        for path in release.iterdir():
            path.chmod(0o644)


def test_v2_snapshot_requires_retrospective_provenance_for_2026_07_27(
    monkeypatch, tmp_path
):
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    release = tmp_path / "release"
    release.mkdir()
    (release / V2_OUTPUT_FILENAMES["coverage"]).write_text(
        json.dumps({"trade_date": "2026-07-27", "ranking_version": "v2"}),
        encoding="utf-8",
    )
    for key in ("top20", "top30", "ranked_pool"):
        pd.DataFrame(
            {"trade_date": ["2026-07-27"], "asset_id": ["A"], "final_rank": [1]}
        ).to_csv(release / V2_OUTPUT_FILENAMES[key], index=False)
    (release / ".manifest.sha256").write_text("manifest\n", encoding="utf-8")
    monkeypatch.setattr(
        cli, "_verified_consumer_oversold_v2_release", lambda snapshot_dir: release
    )

    with pytest.raises(ValueError, match="retrospective evidence provenance"):
        cli._load_consumer_oversold_v2_snapshot("snapshot/current")


def test_v2_snapshot_revalidates_underlying_evidence_not_only_provenance(
    monkeypatch, tmp_path
):
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    release = tmp_path / "release"
    release.mkdir()
    (release / V2_OUTPUT_FILENAMES["coverage"]).write_text(
        json.dumps(
            {
                "trade_date": "2026-07-27",
                "ranking_version": "v2",
                "evidence_reconstruction_mode": "retrospective_point_in_time",
                "evidence_information_cutoff": "2026-07-27",
            }
        ),
        encoding="utf-8",
    )
    for key in ("top20", "top30", "ranked_pool"):
        pd.DataFrame(
            {"trade_date": ["2026-07-27"], "asset_id": ["A"], "final_rank": [1]}
        ).to_csv(release / V2_OUTPUT_FILENAMES[key], index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "A",
                "source_publish_date": "2026-07-20",
                "audit_review_source_publish_date": "2026-07-20",
                "pledge_debt_review_source_publish_date": "2026-07-28",
                "permanent_impairment_source_publish_date": "2026-07-20",
            }
        ]
    ).to_csv(release / V2_OUTPUT_FILENAMES["evidence"], index=False)
    (release / ".manifest.sha256").write_text("manifest\n", encoding="utf-8")
    monkeypatch.setattr(
        cli, "_verified_consumer_oversold_v2_release", lambda snapshot_dir: release
    )

    with pytest.raises(ValueError, match="future evidence publication"):
        cli._load_consumer_oversold_v2_snapshot("snapshot/current")


def test_v2_snapshot_reports_corrupt_csv_as_sealed_artifact_error(
    monkeypatch, tmp_path
):
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    release = tmp_path / "release"
    release.mkdir()
    for filename in V2_OUTPUT_FILENAMES.values():
        (release / filename).write_text("payload\n", encoding="utf-8")
    (release / V2_OUTPUT_FILENAMES["coverage"]).write_text(
        json.dumps({"trade_date": "2026-07-29", "ranking_version": "v2"}),
        encoding="utf-8",
    )
    valid_ranking = pd.DataFrame(
        {"trade_date": ["2026-07-29"], "asset_id": ["A"], "final_rank": [1]}
    )
    for key in ("top20", "top30", "ranked_pool"):
        valid_ranking.to_csv(release / V2_OUTPUT_FILENAMES[key], index=False)
    (release / V2_OUTPUT_FILENAMES["top30"]).write_bytes(b"\xff\xfe")
    monkeypatch.setattr(
        cli, "_verified_consumer_oversold_v2_release", lambda snapshot_dir: release
    )

    with pytest.raises(ValueError, match="sealed V2 snapshot artifact content is invalid"):
        cli._load_consumer_oversold_v2_snapshot("snapshot/current")


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("ranking_version", "v1"), ("trade_date", "2026-07-30")],
)
def test_v2_snapshot_rejects_self_consistent_row_metadata_mismatch(
    monkeypatch, tmp_path, field, bad_value
):
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    release = tmp_path / "release"
    release.mkdir()
    frames, coverage = _valid_v2_snapshot_rank_frames()
    for frame in frames.values():
        frame.loc[0, field] = bad_value
    _write_snapshot_rank_frames(release, frames, coverage)
    for filename in V2_OUTPUT_FILENAMES.values():
        path = release / filename
        if not path.exists():
            path.write_text("payload\n", encoding="utf-8")
    monkeypatch.setattr(
        cli, "_verified_consumer_oversold_v2_release", lambda snapshot_dir: release
    )

    with pytest.raises(ValueError, match="sealed V2 snapshot"):
        cli._load_consumer_oversold_v2_snapshot("snapshot/current")


def test_v2_snapshot_rejects_non_continuous_rank_and_cardinality(monkeypatch, tmp_path):
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    release = tmp_path / "release"
    release.mkdir()
    frames, coverage = _valid_v2_snapshot_rank_frames(pool_size=25)
    frames["ranked_pool"].loc[1, "final_rank"] = 3
    frames["top20"] = frames["ranked_pool"].iloc[:19].copy(deep=True)
    frames["top30"] = frames["ranked_pool"].iloc[:25].copy(deep=True)
    _write_snapshot_rank_frames(release, frames, coverage)
    for filename in V2_OUTPUT_FILENAMES.values():
        path = release / filename
        if not path.exists():
            path.write_text("payload\n", encoding="utf-8")
    monkeypatch.setattr(
        cli, "_verified_consumer_oversold_v2_release", lambda snapshot_dir: release
    )

    with pytest.raises(ValueError, match="sealed V2 snapshot"):
        cli._load_consumer_oversold_v2_snapshot("snapshot/current")


def test_v2_snapshot_rejects_selection_that_is_not_ranked_pool_slice(
    monkeypatch, tmp_path
):
    from stock_research.consumer_oversold.contracts import V2_OUTPUT_FILENAMES

    release = tmp_path / "release"
    release.mkdir()
    frames, coverage = _valid_v2_snapshot_rank_frames(pool_size=3)
    frames["top20"].loc[0, "composite_score"] = 61.0
    _write_snapshot_rank_frames(release, frames, coverage)
    for filename in V2_OUTPUT_FILENAMES.values():
        path = release / filename
        if not path.exists():
            path.write_text("payload\n", encoding="utf-8")
    monkeypatch.setattr(
        cli, "_verified_consumer_oversold_v2_release", lambda snapshot_dir: release
    )

    with pytest.raises(ValueError, match="sealed V2 snapshot"):
        cli._load_consumer_oversold_v2_snapshot("snapshot/current")


def test_consumer_oversold_v2_evaluate_dispatches_and_prints_paths(
    monkeypatch, capsys
):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
                "paths": {
                    "detail": "/tmp/evaluation/detail.csv",
                    "daily_detail": "/tmp/evaluation/daily_detail.csv",
                    "summary": "/tmp/evaluation/summary.csv",
                    "v1_v2_comparison": "/tmp/evaluation/v1_v2_comparison.csv",
                    "minute_detail": "/tmp/evaluation/minute.csv",
                "coverage": "/tmp/evaluation/coverage.json",
                "report": "/tmp/evaluation/report.md",
            }
        }

    monkeypatch.setattr(cli, "_run_consumer_oversold_v2_evaluation", fake_run)
    cli.main_for_args(
        [
            "consumer-oversold-v2-evaluate",
            "--snapshot-dir",
            "/tmp/snapshot/current",
            "--end-date",
            "2026-07-30",
            "--output-dir",
            "/tmp/evaluation",
            "--service",
            "research_custom",
        ]
    )

    assert captured == {
        "snapshot_dir": "/tmp/snapshot/current",
        "end_date": "2026-07-30",
        "output_dir": "/tmp/evaluation",
        "service": "research_custom",
    }
    assert capsys.readouterr().out.splitlines()[-1] == (
        "consumer_oversold_v2_evaluation|report|/tmp/evaluation/report.md"
    )


def test_v2_evaluate_rejects_outcome_on_or_before_snapshot(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_load_consumer_oversold_v2_snapshot",
        lambda snapshot_dir: {
            "trade_date": "2026-07-27",
            "top20": pd.DataFrame(),
            "top30": pd.DataFrame(),
            "ranked_pool": pd.DataFrame(),
            "coverage": {},
            "release": Path(snapshot_dir),
        },
    )

    with pytest.raises(ValueError, match="end_date must be after snapshot_trade_date"):
        cli._run_consumer_oversold_v2_evaluation(
            snapshot_dir="snapshot",
            end_date="2026-07-27",
            output_dir="evaluation",
            service="stock_research",
        )


def test_v2_evaluate_uses_explicit_outcome_window_without_recomputing_snapshot(
    monkeypatch, tmp_path
):
    top30 = pd.DataFrame(
        {"trade_date": ["2026-07-27", "2026-07-27"], "asset_id": ["A", "B"], "final_rank": [1, 2]}
    )
    ranked_pool = top30.copy(deep=True)
    frozen_top30 = top30.copy(deep=True)
    frozen_pool = ranked_pool.copy(deep=True)
    rank_comparison = pd.DataFrame(
        {
            "asset_id": ["A", "B", "C"],
            "v1_rank": [2, 3, 1],
            "v2_rank": [1, 2, pd.NA],
        }
    )
    frozen_comparison = rank_comparison.copy(deep=True)
    captured = {}
    release = tmp_path / "snapshot-release"
    release.mkdir()
    monkeypatch.setattr(
        cli,
        "_load_consumer_oversold_v2_snapshot",
        lambda snapshot_dir: {
            "trade_date": "2026-07-27",
            "top20": top30.iloc[:1].copy(deep=True),
            "top30": top30,
            "ranked_pool": ranked_pool,
            "comparison": rank_comparison,
            "coverage": {
                "evidence_reconstruction_mode": "retrospective_point_in_time",
                "evidence_information_cutoff": "2026-07-27",
            },
            "release": release,
            "manifest_sha256": "a" * 64,
        },
    )
    def fake_calendar(**kwargs):
        captured["calendar"] = kwargs
        return ["2026-07-28", "2026-07-29", "2026-07-30"]

    monkeypatch.setattr(cli, "_load_consumer_v2_outcome_calendar", fake_calendar)
    hfq = pd.DataFrame(
        {
            "asset_id": ["A"],
            "trade_date": ["2026-07-27"],
            "hfq_close": [10.0],
        }
    )
    raw = pd.DataFrame(
        {
            "asset_id": ["A"],
            "trade_date": ["2026-07-27"],
            "raw_open": [10.0],
            "raw_high": [10.0],
            "raw_low": [10.0],
            "raw_close": [10.0],
        }
    )
    def fake_hfq(**kwargs):
        captured["hfq"] = kwargs
        return hfq.copy(deep=True)

    def fake_raw(**kwargs):
        captured["raw"] = kwargs
        return raw.copy(deep=True)

    def fake_minute(**kwargs):
        captured["minute"] = kwargs
        return pd.DataFrame()

    monkeypatch.setattr(cli, "_load_consumer_v2_hfq_daily_closes", fake_hfq)
    monkeypatch.setattr(cli, "_load_consumer_v2_raw_daily_bars", fake_raw)
    monkeypatch.setattr(cli, "_load_consumer_v2_minute_outcome_bars", fake_minute)

    def fake_evaluate(**kwargs):
        captured["evaluate"] = kwargs
        return {
            "detail": pd.DataFrame(),
            "summary": pd.DataFrame(),
            "minute_detail": pd.DataFrame(),
            "coverage": {
                "snapshot_trade_date": "2026-07-27",
                "evaluation_status": "daily_incomplete",
                "selected_asset_count": 2,
                "qualified_pool_count": 2,
            },
        }

    monkeypatch.setattr(cli, "_evaluate_consumer_oversold_v2_snapshot", fake_evaluate)
    def fake_publish(**kwargs):
        captured["publish"] = kwargs
        return {
            key: str(tmp_path / filename)
            for key, filename in cli._CONSUMER_OVERSOLD_V2_EVALUATION_FILENAMES.items()
        }

    monkeypatch.setattr(cli, "_publish_consumer_oversold_v2_evaluation", fake_publish)

    result = cli._run_consumer_oversold_v2_evaluation(
        snapshot_dir="snapshot/current",
        end_date="2026-07-30",
        output_dir=str(tmp_path / "evaluation"),
        service="research_custom",
    )

    assert captured["calendar"] == {
        "start_date": "2026-07-28",
        "end_date": "2026-07-30",
        "service": "research_custom",
    }
    assert captured["hfq"]["start_date"] == "2026-07-27"
    assert captured["hfq"]["asset_ids"] == ["A", "B", "C"]
    assert captured["raw"]["end_date"] == "2026-07-30"
    assert captured["minute"]["start_date"] == "2026-07-28"
    assert captured["minute"]["end_date"] == "2026-07-30"
    assert captured["evaluate"]["outcome_dates"] == (
        "2026-07-28",
        "2026-07-29",
        "2026-07-30",
    )
    pdt.assert_frame_equal(
        captured["evaluate"]["rank_comparison"], frozen_comparison
    )
    assert result["coverage"]["evidence_reconstruction_mode"] == (
        "retrospective_point_in_time"
    )
    assert result["coverage"]["evidence_information_cutoff"] == "2026-07-27"
    pdt.assert_frame_equal(top30, frozen_top30)
    pdt.assert_frame_equal(ranked_pool, frozen_pool)
    pdt.assert_frame_equal(rank_comparison, frozen_comparison)


def test_v2_evaluate_cli_deduplicates_calendar_rows_without_shifting_window(
    monkeypatch, tmp_path, capsys
):
    from contextlib import contextmanager
    from datetime import date

    from stock_research.consumer_oversold import loaders

    members = pd.DataFrame(
        {"trade_date": ["2026-07-27"], "asset_id": ["A"], "final_rank": [1]}
    )
    release = tmp_path / "snapshot-release"
    release.mkdir()
    monkeypatch.setattr(
        cli,
        "_load_consumer_oversold_v2_snapshot",
        lambda snapshot_dir: {
            "trade_date": "2026-07-27",
            "top20": members,
            "top30": members,
            "ranked_pool": members,
            "coverage": {},
            "release": release,
            "manifest_sha256": "a" * 64,
        },
    )
    raw_calendar_rows = [
        {"trade_date": date(2026, 7, 28)},
        {"trade_date": date(2026, 7, 28)},
        {"trade_date": date(2026, 7, 29)},
        {"trade_date": date(2026, 7, 29)},
        {"trade_date": date(2026, 7, 30)},
        {"trade_date": date(2026, 7, 30)},
    ]

    @contextmanager
    def fake_connect(service):
        assert service == "research_custom"
        yield object()

    def fake_fetch_all(conn, sql, params=None):
        normalized = " ".join(sql.split())
        if "SELECT DISTINCT trade_date" not in normalized:
            return raw_calendar_rows
        return [
            raw_calendar_rows[index]
            for index in range(0, len(raw_calendar_rows), 2)
        ]

    monkeypatch.setattr(loaders, "connect", fake_connect)
    monkeypatch.setattr(loaders, "fetch_all", fake_fetch_all)
    empty_hfq = pd.DataFrame(columns=["asset_id", "trade_date", "hfq_close"])
    empty_raw = pd.DataFrame(
        columns=[
            "asset_id",
            "trade_date",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
        ]
    )
    monkeypatch.setattr(
        cli, "_load_consumer_v2_hfq_daily_closes", lambda **kwargs: empty_hfq
    )
    monkeypatch.setattr(
        cli, "_load_consumer_v2_raw_daily_bars", lambda **kwargs: empty_raw
    )
    monkeypatch.setattr(
        cli, "_load_consumer_v2_minute_outcome_bars", lambda **kwargs: pd.DataFrame()
    )
    captured = {}

    def fake_evaluate(**kwargs):
        captured["outcome_dates"] = kwargs["outcome_dates"]
        return {
            "detail": pd.DataFrame(),
            "summary": pd.DataFrame(),
            "minute_detail": pd.DataFrame(),
            "coverage": {
                "snapshot_trade_date": "2026-07-27",
                "evaluation_status": "daily_incomplete",
                "selected_asset_count": 1,
                "qualified_pool_count": 1,
            },
        }

    monkeypatch.setattr(cli, "_evaluate_consumer_oversold_v2_snapshot", fake_evaluate)
    monkeypatch.setattr(
        cli,
        "_publish_consumer_oversold_v2_evaluation",
        lambda **kwargs: {
            key: str(tmp_path / filename)
            for key, filename in cli._CONSUMER_OVERSOLD_V2_EVALUATION_FILENAMES.items()
        },
    )

    cli.main_for_args(
        [
            "consumer-oversold-v2-evaluate",
            "--snapshot-dir",
            str(tmp_path / "snapshot" / "current"),
            "--end-date",
            "2026-07-30",
            "--output-dir",
            str(tmp_path / "evaluation"),
            "--service",
            "research_custom",
        ]
    )

    assert captured["outcome_dates"] == (
        "2026-07-28",
        "2026-07-29",
        "2026-07-30",
    )
    assert "consumer_oversold_v2_evaluation|report|" in capsys.readouterr().out


def test_v2_evaluate_rejects_authoritative_calendar_beyond_end_date(monkeypatch, tmp_path):
    members = pd.DataFrame(
        {"trade_date": ["2026-07-27"], "asset_id": ["A"], "final_rank": [1]}
    )
    release = tmp_path / "snapshot-release"
    release.mkdir()
    monkeypatch.setattr(
        cli,
        "_load_consumer_oversold_v2_snapshot",
        lambda snapshot_dir: {
            "trade_date": "2026-07-27",
            "top20": members,
            "top30": members,
            "ranked_pool": members,
            "coverage": {},
            "release": release,
            "manifest_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(
        cli,
        "_load_consumer_v2_outcome_calendar",
        lambda **kwargs: ["2026-07-28", "2026-07-31"],
    )
    monkeypatch.setattr(
        cli,
        "_load_consumer_v2_hfq_daily_closes",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("daily loader must not run")),
    )

    with pytest.raises(ValueError, match="outcome date window"):
        cli._run_consumer_oversold_v2_evaluation(
            snapshot_dir="snapshot/current",
            end_date="2026-07-30",
            output_dir=str(tmp_path / "evaluation"),
            service="research_custom",
        )


def test_v2_evaluation_publication_is_manifested_deterministic_and_immutable(tmp_path):
    evaluated = {
        "detail": pd.DataFrame([{"asset_id": "A", "forward_return": 0.1}]),
        "daily_detail": pd.DataFrame(
            [{"asset_id": "A", "outcome_trade_date": "2026-07-30"}]
        ),
        "summary": pd.DataFrame([{"group": "top20", "rising_ratio": 1.0}]),
        "v1_v2_comparison": pd.DataFrame(
            [{"cohort": "v2_top20", "mean_return_delta_vs_v1": 0.01}]
        ),
        "minute_detail": pd.DataFrame([{"asset_id": "A", "bar_count": 48}]),
        "coverage": {"snapshot_trade_date": "2026-07-27", "end_date": "2026-07-30"},
    }
    frozen = {key: value.copy(deep=True) for key, value in evaluated.items() if isinstance(value, pd.DataFrame)}

    first = cli._publish_consumer_oversold_v2_evaluation(
        output_dir=str(tmp_path), evaluated=evaluated, report="report\n"
    )
    first_bytes = {key: Path(path).read_bytes() for key, path in first.items()}
    second = cli._publish_consumer_oversold_v2_evaluation(
        output_dir=str(tmp_path), evaluated=evaluated, report="report\n"
    )

    assert first == second
    assert first_bytes == {key: Path(path).read_bytes() for key, path in second.items()}
    release = (tmp_path / "current").resolve()
    manifest = release / ".manifest.sha256"
    assert stat.S_IMODE(release.stat().st_mode) == 0o555
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o444
    assert set(path.name for path in release.iterdir()) == {
        ".manifest.sha256",
        *cli._CONSUMER_OVERSOLD_V2_EVALUATION_FILENAMES.values(),
    }
    assert {
        "daily_detail",
        "v1_v2_comparison",
    }.issubset(cli._CONSUMER_OVERSOLD_V2_EVALUATION_FILENAMES)
    for key, expected in frozen.items():
        pdt.assert_frame_equal(evaluated[key], expected)


def test_consumer_v2_cli_contains_no_stock_specific_branches():
    source = Path(cli.__file__).read_text(encoding="utf-8")
    for stock_name in ("北汽蓝谷", "赛力斯", "舍得酒业", "江淮汽车"):
        assert stock_name not in source
