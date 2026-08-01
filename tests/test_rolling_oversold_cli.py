from __future__ import annotations

from datetime import date
from pathlib import Path

from stock_research import cli


def test_parser_accepts_all_rolling_sector_oversold_commands_with_explicit_date():
    parser = cli.build_parser()

    replay = parser.parse_args(
        [
            "rolling-sector-oversold-replay",
            "--anchor-start-date",
            "2026-07-21",
            "--anchor-end-date",
            "2026-07-22",
            "--output-dir",
            "/tmp/rolling",
            "--adjust-type",
            "raw",
        ]
    )
    daily = parser.parse_args(
        [
            "rolling-sector-oversold-daily",
            "--trade-date",
            "2026-07-21",
            "--output-dir",
            "/tmp/rolling",
        ]
    )
    report = parser.parse_args(
        [
            "rolling-sector-oversold-report",
            "--snapshot-dir",
            "/tmp/snapshot",
            "--focus-patterns",
            "alpha,theme",
            "--output-dir",
            "/tmp/report",
        ]
    )

    assert replay.anchor_start_date == "2026-07-21"
    assert replay.anchor_end_date == "2026-07-22"
    assert replay.sector_top_n == 30
    assert replay.stock_top_n == 20
    assert replay.score_version == "rolling_oversold_v1"
    assert replay.adjust_type == "raw"
    assert daily.trade_date == "2026-07-21"
    assert daily.adjust_type == "qfq"
    assert report.focus_patterns == "alpha,theme"


def test_replay_cli_dispatches_without_database_and_prints_required_machine_keys(
    monkeypatch, capsys
):
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "snapshot_ids": ["rolling_oversold_v1|2026-07-21"],
            "anchors_processed": 1,
            "blocked": 0,
            "runtime_seconds": 0.25,
            "all_sector_rows_have_status": True,
            "anchors": [
                {
                    "paths": {
                        "snapshot_manifest": "/tmp/snapshot/manifest.json",
                        "market_regime": "/tmp/snapshot/market_regime.csv",
                        "sector_states": "/tmp/snapshot/sector_states.csv",
                        "stock_candidates": "/tmp/snapshot/stock_candidates.csv",
                        "evaluation": "/tmp/snapshot/evaluation_detail.csv",
                        "preflight": "/tmp/snapshot/preflight.json",
                        "backfill_requests": "/tmp/snapshot/backfill_requests.csv",
                    }
                }
            ],
        }

    monkeypatch.setattr(cli, "run_rolling_replay", fake_run, raising=False)

    cli.main_for_args(
        [
            "rolling-sector-oversold-replay",
            "--anchor-start-date",
            "2026-07-21",
            "--output-dir",
            "/tmp/rolling",
            "--service",
            "research-test",
        ]
    )

    assert captured["config"].anchor_start_date == date(2026, 7, 21)
    assert captured["service"] == "research-test"
    keys = {line.split("|", 2)[1] for line in capsys.readouterr().out.splitlines()}
    assert {
        "snapshot_manifest",
        "market_regime",
        "sector_states",
        "stock_candidates",
        "evaluation",
        "preflight",
        "backfill_requests",
        "runtime_seconds",
        "blocked",
    }.issubset(keys)


def test_daily_cli_preserves_persisted_history_start_for_blocked_guard(
    monkeypatch, tmp_path
):
    first = date(2026, 7, 21)
    blocked_dir = (
        Path(tmp_path)
        / "rolling_sector_oversold"
        / "blocked"
        / f"anchor={first.isoformat()}"
        / "version=rolling_oversold_v1"
    )
    blocked_dir.mkdir(parents=True)
    (blocked_dir / "preflight.json").write_text('{"blocked": true}\n', encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"blocked": True, "runtime_seconds": 0.01, "paths": {}}

    monkeypatch.setattr(cli, "run_rolling_daily", fake_run, raising=False)

    cli.main_for_args(
        [
            "rolling-sector-oversold-daily",
            "--trade-date",
            "2026-07-22",
            "--output-dir",
            str(tmp_path),
            "--service",
            "research-test",
        ]
    )

    assert captured["config"].anchor_start_date == first


def test_report_cli_machine_evaluation_path_uses_latest_revision(monkeypatch, tmp_path, capsys):
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    (snapshot_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    (snapshot_dir / "evaluation_detail.csv").write_text(
        "asset_id,evaluation_status\nA,pending\n", encoding="utf-8"
    )
    revision_dir = snapshot_dir / "evaluation_revision=0001"
    revision_dir.mkdir()
    (revision_dir / "evaluation_detail.csv").write_text(
        "asset_id,evaluation_status\nA,complete\n", encoding="utf-8"
    )
    (revision_dir / "evaluation_summary.csv").write_text(
        "forward_horizon_days,complete_count\n1,1\n", encoding="utf-8"
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "load_rolling_oversold_snapshot",
        lambda path: {
            "manifest": {"runtime_metadata": {"runtime_seconds": 0.2}},
            "preflight": {},
            "snapshot_id": "snapshot",
        },
    )
    monkeypatch.setattr(
        cli,
        "write_rolling_sector_oversold_report",
        lambda **kwargs: captured.update(kwargs) or tmp_path / "report.md",
    )

    cli.main_for_args(
        [
            "rolling-sector-oversold-report",
            "--snapshot-dir",
            str(snapshot_dir),
            "--output-dir",
            str(tmp_path / "report"),
        ]
    )

    assert captured["snapshot_dir"] == snapshot_dir.resolve()
    lines = {
        line.split("|", 2)[1]: line.split("|", 2)[2]
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("rolling_sector_oversold|")
    }
    assert lines["evaluation"] == str(revision_dir / "evaluation_detail.csv")
