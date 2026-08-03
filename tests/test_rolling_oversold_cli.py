from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

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

    batch = parser.parse_args(
        [
            "rolling-sector-oversold-batch",
            "--anchor-date",
            "2026-07-31",
            "--output-dir",
            "/tmp/full",
        ]
    )
    assert batch.anchor_date == "2026-07-31"
    assert batch.sector_stock_top_n == 10
    assert batch.runtime_budget_seconds == 3600


def test_batch_cli_runs_one_batch_and_publishes_report_paths(monkeypatch, tmp_path, capsys):
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        board = pd.DataFrame(
            [
                {
                    "sector_system": "ths",
                    "sector_code": "300238",
                    "sector_name": "核电",
                    "sector_recovery_state": "confirmed_repair",
                    "sector_oversold_score": 88.0,
                    "sector_repairability_score": 91.0,
                    "sector_direction_score": 83.0,
                    "sector_research_eligibility": "eligible",
                },
                {
                    "sector_system": "ths",
                    "sector_code": "300239",
                    "sector_name": "半导体",
                    "sector_recovery_state": "expected_repair",
                    "sector_oversold_score": 94.0,
                    "sector_repairability_score": 79.0,
                    "sector_direction_score": 73.0,
                    "sector_research_eligibility": "eligible",
                },
            ]
        )
        stocks = pd.DataFrame(
            [
                {
                    "asset_id": "A",
                    "sector_system": "ths",
                    "sector_code": "300238",
                    "sector_name": "核电",
                    "sector_stock_rank": 1,
                    "stock_lifecycle": "confirmed_repair",
                    "stock_score": 90.0,
                }
            ]
        )
        return {
            "blocked": False,
            "snapshot": {
                "snapshot_id": "rolling_oversold_v2|2026-07-31",
                "anchor_date": "2026-07-31",
                "sector_states": board,
                "stock_candidates": stocks,
                "preflight": {},
                "backfill_requests": pd.DataFrame(),
            },
            "sector_states": board,
            "sector_daily_board": board,
            "stock_candidates": stocks,
            "sector_stock_candidates": stocks,
            "paths": {
                "manifest": str(tmp_path / "manifest.json"),
                "sector_daily_board": str(tmp_path / "sector_daily_board.csv"),
                "sector_stock_candidates": str(tmp_path / "sector_stock_candidates.csv"),
                "backfill_requests": str(tmp_path / "backfill_requests.csv"),
            },
            "runtime_seconds": 0.25,
        }

    monkeypatch.setattr(cli, "run_sector_batch", fake_run, raising=False)
    monkeypatch.setattr(
        cli,
        "evaluate_sector_batch_outcomes",
        lambda *args, **kwargs: {"detail": pd.DataFrame(), "summary": pd.DataFrame()},
        raising=False,
    )

    cli.main_for_args(
        [
            "rolling-sector-oversold-batch",
            "--anchor-date",
            "2026-07-31",
            "--output-dir",
            str(tmp_path),
            "--service",
            "research-test",
            "--sector-stock-top-n",
            "7",
            "--runtime-budget-seconds",
            "42",
        ]
    )

    assert captured["service"] == "research-test"
    assert captured["anchor_date"] == date(2026, 7, 31)
    assert captured["config"].sector_output_top_n == 7
    assert captured["config"].runtime_budget_seconds == 42
    lines = {
        line.split("|", 2)[1]: line.split("|", 2)[2]
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("rolling_sector_oversold|")
    }
    assert lines["sector_daily_board"] == str(tmp_path / "sector_daily_board.csv")
    assert lines["sector_stock_candidates"] == str(tmp_path / "sector_stock_candidates.csv")
    assert lines["sector_repair_summary"].endswith("sector_repair_summary.md")


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
