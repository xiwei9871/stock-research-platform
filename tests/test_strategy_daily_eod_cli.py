import pytest

from stock_research import cli
from stock_research import strategy_eod_publish


def test_cli_accepts_run_strategy_daily_eod_command():
    args = cli.build_parser().parse_args(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    assert args.command == "run-strategy-daily-eod"
    assert args.trade_date == "2026-06-24"
    assert args.output_root is None


def test_cli_defaults_strategy_output_to_runtime_release_root(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cli,
        "runtime_provenance",
        lambda: {"source_root": "/tmp/clean-release"},
    )
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **kwargs: captured.update(kwargs) or {
            "status": "success",
            "trade_date": "2026-06-24",
            "output_dir": "/tmp/clean-release/outputs/research/strategy_daily_eod/2026-06-24",
            "review_rows": 15,
            "summary_path": "/tmp/summary.json",
            "dependency_reason": None,
            "dependency_check": {},
            "strategy_status": {},
        },
    )

    assert cli.main(["run-strategy-daily-eod", "--trade-date", "2026-06-24"]) == 0
    assert captured["output_root"] == "/tmp/clean-release/outputs/research/strategy_daily_eod"
    assert captured["release_root"] == "/tmp/clean-release"


@pytest.mark.parametrize("cwd_suffix", ["outside", "release/subdir"])
def test_cli_anchors_relative_strategy_output_to_runtime_release_root(
    tmp_path, cwd_suffix, monkeypatch
):
    release = tmp_path / "release"
    cwd = tmp_path / cwd_suffix
    cwd.mkdir(parents=True)
    captured = {}
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(cli, "runtime_provenance", lambda: {"source_root": str(release)})
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **kwargs: captured.update(kwargs) or {
            "status": "success",
            "trade_date": "2026-06-24",
            "dependency_check": {},
            "strategy_status": {},
        },
    )

    assert cli.main(
        [
            "run-strategy-daily-eod",
            "--trade-date",
            "2026-06-24",
            "--output-root",
            "outputs/custom-strategy",
        ]
    ) == 0
    assert captured["output_root"] == str(release / "outputs/custom-strategy")
    assert captured["release_root"] == str(release)


@pytest.mark.parametrize("cwd_suffix", ["outside", "release/subdir"])
def test_legacy_cli_anchors_relative_base_output_to_runtime_release_root(
    tmp_path, cwd_suffix, monkeypatch
):
    release = tmp_path / "release"
    cwd = tmp_path / cwd_suffix
    cwd.mkdir(parents=True)
    captured = []
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        "stock_research.runtime_provenance.runtime_provenance",
        lambda: {"source_root": str(release)},
    )
    monkeypatch.setattr(
        "stock_research.strategy_daily_eod.run_strategy_daily_eod",
        lambda **kwargs: captured.append(kwargs) or {"status": "success"},
    )

    assert strategy_eod_publish._main(
        ["--trade-date", "2026-06-24", "--output-root", "outputs-alt"]
    ) == 0
    assert captured[0]["output_root"] == (
        release / "outputs-alt" / "research" / "strategy_daily_eod"
    )
    assert captured[0]["release_root"] == release


def test_legacy_strategy_publish_cli_forwards_once_to_official_runner(
    tmp_path, monkeypatch, capsys
):
    captured = []
    monkeypatch.setattr(
        "stock_research.runtime_provenance.runtime_provenance",
        lambda: {"source_root": str(tmp_path)},
    )
    monkeypatch.setattr(
        "stock_research.strategy_daily_eod.run_strategy_daily_eod",
        lambda **kwargs: captured.append(kwargs) or {"status": "success"},
    )

    rc = strategy_eod_publish._main(
        ["--trade-date", "2026-06-24", "--output-root", str(tmp_path / "outputs")]
    )

    assert rc == 0
    assert captured == [
        {
            "trade_date": "2026-06-24",
            "output_root": tmp_path / "outputs" / "research" / "strategy_daily_eod",
            "release_root": tmp_path,
        }
    ]
    assert "deprecated" in capsys.readouterr().err.lower()


def test_cli_run_strategy_daily_eod_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **_kwargs: {
            "status": "success",
            "trade_date": "2026-06-24",
            "output_dir": "/tmp/out",
            "review_rows": 15,
            "summary_path": "/tmp/out/strategy_eod_publish_summary.json",
            "dependency_reason": None,
            "dependency_check": {
                "common": {"status": "success"},
                "intraday": {"status": "success"},
            },
            "strategy_status": {
                "lhb_shortline": "success",
                "mid_trend": "success",
                "midtrend_artifacts": "success",
                "tech_bottleneck": "success",
            },
        },
    )

    rc = cli.main(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "strategy_daily_eod|status|success" in out
    assert "strategy_daily_eod|lhb_shortline_status|success" in out
    assert "strategy_daily_eod|mid_trend_status|success" in out
    assert "strategy_daily_eod|strategy_midtrend_artifacts_status|success" in out
    assert "strategy_daily_eod|tech_bottleneck_status|success" in out
    assert "strategy_daily_eod|dependency_common_status|success" in out
    assert "strategy_daily_eod|dependency_intraday_status|success" in out


@pytest.mark.parametrize(
    ("status", "expected_rc"),
    [("success", 0), ("partial", 1), ("failed", 1)],
)
def test_cli_run_strategy_daily_eod_returns_business_status_exit_code(
    monkeypatch, status, expected_rc
):
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **_kwargs: {
            "status": status,
            "trade_date": "2026-06-24",
            "output_dir": "/tmp/out",
            "review_rows": 0,
            "summary_path": "/tmp/out/summary.json",
            "dependency_reason": "dependency failed" if status != "success" else None,
            "dependency_check": {
                "common": {"status": "success"},
                "intraday": {"status": "failed" if status != "success" else "success"},
            },
            "strategy_status": {
                "lhb_shortline": "blocked" if status != "success" else "success",
                "mid_trend": "success",
                "midtrend_artifacts": "success",
                "tech_bottleneck": "success",
            },
        },
    )

    assert cli.main(["run-strategy-daily-eod", "--trade-date", "2026-06-24"]) == expected_rc
