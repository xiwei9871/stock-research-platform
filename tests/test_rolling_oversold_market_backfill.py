from __future__ import annotations

import csv
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from stock_research import cli
from stock_research.rolling_oversold import market_backfill


class _FakeConnection:
    pass


@contextmanager
def _connection(conn):
    yield conn


def _master_row(
    asset_id: str,
    *,
    exchange: str,
    list_date: str | None = "2020-01-01",
    delist_date: str | None = None,
    is_active: bool | None = None,
    is_beijing: bool | None = None,
) -> dict[str, object]:
    row = {
        "asset_id": asset_id,
        "exchange": exchange,
        "list_date": list_date,
        "delist_date": delist_date,
    }
    if is_active is not None:
        row["is_active"] = is_active
    if is_beijing is not None:
        row["is_beijing"] = is_beijing
    return row


def _bar(asset_id: str, trade_date: date, adjust_type: str) -> dict[str, object]:
    ts_code = f"{asset_id.rsplit(':', 1)[-1]}.{asset_id.split(':')[1]}"
    return {
        "ts_code": ts_code,
        "asset_id": asset_id,
        "trade_date": trade_date,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "preclose": 10.0,
        "volume": 1000.0,
        "amount": 10000.0,
        "turnover_rate": 1.0,
        "pct_chg": 5.0,
        "trade_status": "1",
        "is_st": False,
        "adjust_type": adjust_type,
    }


def test_market_backfill_dry_run_is_pit_read_only_and_rejects_invalid_assets(
    monkeypatch, tmp_path: Path
):
    conn = _FakeConnection()
    masters = [
        _master_row("CN:SH:600000", exchange="SH"),
        _master_row("CN:BJ:920001", exchange="BJ", is_beijing=True),
        _master_row("CN:SZ:000001", exchange="SZ", delist_date="2026-07-28"),
    ]
    monkeypatch.setattr(market_backfill, "connect", lambda service: _connection(conn))
    monkeypatch.setattr(market_backfill, "fetch_all", lambda opened, sql, params: masters)
    monkeypatch.setattr(
        market_backfill,
        "fetch_akshare_daily_rows",
        lambda **kwargs: pytest.fail("dry-run must not call an external source"),
    )
    monkeypatch.setattr(
        market_backfill,
        "execute_many",
        lambda *args, **kwargs: pytest.fail("dry-run must not write to the database"),
    )

    result = market_backfill.run_market_backfill(
        asset_ids=[
            "CN:SH:600000",
            "CN:BJ:920001",
            "CN:SZ:000001",
            "CN:SZ:000002",
        ],
        start_date="2026-07-29",
        end_date="2026-07-30",
        adjust_types=("raw", "qfq", "hfq"),
        source="akshare",
        dry_run=True,
        output_dir=tmp_path,
    )

    assert result["dry_run"] is True
    assert result["raw_rows"] == 0
    assert result["bar_rows"] == 0
    assert result["paths"]["json"]
    assert result["paths"]["csv"]
    report = json.loads(Path(result["paths"]["json"]).read_text(encoding="utf-8"))
    statuses = {(row["asset_id"], row["status"]) for row in report["rows"]}
    assert ("CN:BJ:920001", "out_of_scope_bse") in statuses
    assert ("CN:SZ:000002", "missing_master") in statuses
    assert ("CN:SZ:000001", "inactive_pit") in statuses
    assert ("CN:SH:600000", "planned") in statuses


def test_market_backfill_rejects_currently_inactive_non_bse_master(
    monkeypatch, tmp_path: Path
):
    conn = _FakeConnection()
    monkeypatch.setattr(market_backfill, "connect", lambda service: _connection(conn))
    monkeypatch.setattr(
        market_backfill,
        "fetch_all",
        lambda opened, sql, params: [
            _master_row("CN:SZ:000001", exchange="SZ", is_active=False)
        ],
    )
    monkeypatch.setattr(
        market_backfill,
        "fetch_akshare_daily_rows",
        lambda **kwargs: pytest.fail("inactive assets must not reach the source"),
    )

    result = market_backfill.run_market_backfill(
        asset_ids=["CN:SZ:000001"],
        start_date="2026-07-29",
        end_date="2026-07-29",
        adjust_types=("raw",),
        source="akshare",
        dry_run=True,
        output_dir=tmp_path,
    )

    assert result["status_counts"] == {"inactive_pit": 1}


def test_market_backfill_writes_raw_and_bars_with_canonical_conflicts(
    monkeypatch, tmp_path: Path
):
    conn = _FakeConnection()
    execute_many_calls: list[tuple[str, list[dict[str, object]]]] = []
    source_calls = []
    monkeypatch.setattr(market_backfill, "connect", lambda service: _connection(conn))
    monkeypatch.setattr(
        market_backfill,
        "fetch_all",
        lambda opened, sql, params: [_master_row("CN:SH:600000", exchange="SH")],
    )

    def fake_fetch(**kwargs):
        source_calls.append(kwargs)
        trade_date = kwargs["trade_date"]
        return [
            _bar("CN:SH:600000", trade_date, "raw"),
            _bar("CN:SH:600000", trade_date, "qfq"),
        ]

    monkeypatch.setattr(market_backfill, "fetch_akshare_daily_rows", fake_fetch)
    monkeypatch.setattr(
        market_backfill,
        "execute_many",
        lambda conn, sql, rows: execute_many_calls.append((sql, list(rows))),
    )

    result = market_backfill.run_market_backfill(
        asset_ids=["CN:SH:600000"],
        start_date="2026-07-29",
        end_date="2026-07-29",
        adjust_types=("raw", "qfq"),
        source="akshare",
        dry_run=False,
        output_dir=tmp_path,
    )

    assert result["raw_rows"] == 2
    assert result["bar_rows"] == 2
    assert result["upsert_conflict_key"] == [
        "asset_id",
        "trade_date",
        "adjust_type",
    ]
    assert len(source_calls) == 1
    assert source_calls[0]["ts_codes"] == ["600000.SH"]
    assert len(execute_many_calls) == 2
    raw_sql, raw_rows = execute_many_calls[0]
    bar_sql, bar_rows = execute_many_calls[1]
    assert "INSERT INTO raw_baostock.daily_bar_payload" in raw_sql
    assert "ON CONFLICT (source_service, source_table, adjust_type, trade_date, asset_id)" in raw_sql
    assert "ON CONFLICT (asset_id, trade_date, adjust_type)" in bar_sql
    assert len(raw_rows) == len(bar_rows) == 2
    assert all(row["payload_hash"] for row in raw_rows)
    assert {row["adjust_type"] for row in bar_rows} == {"raw", "qfq"}


def test_market_backfill_reports_missing_and_retryable_failures(
    monkeypatch, tmp_path: Path
):
    conn = _FakeConnection()
    monkeypatch.setattr(market_backfill, "connect", lambda service: _connection(conn))
    monkeypatch.setattr(
        market_backfill,
        "fetch_all",
        lambda opened, sql, params: [_master_row("CN:SH:600000", exchange="SH")],
    )
    attempts: dict[str, int] = {}

    def fake_fetch(**kwargs):
        key = str(kwargs["trade_date"])
        attempts[key] = attempts.get(key, 0) + 1
        if key == "2026-07-29":
            return []
        raise RuntimeError("temporary source outage")

    monkeypatch.setattr(market_backfill, "fetch_akshare_daily_rows", fake_fetch)
    monkeypatch.setattr(market_backfill, "execute_many", lambda *args: pytest.fail("no rows expected"))

    result = market_backfill.run_market_backfill(
        asset_ids=["CN:SH:600000"],
        start_date="2026-07-29",
        end_date="2026-07-30",
        adjust_types=("raw",),
        source="akshare",
        dry_run=False,
        output_dir=tmp_path,
    )

    with Path(result["paths"]["csv"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["status"] for row in rows} == {"missing", "retryable_failure"}
    assert result["raw_rows"] == result["bar_rows"] == 0
    assert attempts["2026-07-30"] > 1


def test_cli_wires_gap_workplan_market_backfill_to_current_source(
    monkeypatch, tmp_path: Path
):
    gap_workplan = tmp_path / "gap_workplan.json"
    gap_workplan.write_text(
        json.dumps(
            {
                "buckets": {"market_bar_backfill": ["CN:SH:600000"]},
                "gap_rows": [
                    {
                        "bucket": "market_bar_backfill",
                        "dataset": "market_daily_bar",
                        "asset_or_key": "CN:SH:600000",
                        "start_date": "2026-07-29",
                        "end_date": "2026-07-29",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(
        cli,
        "load_market_backfill_asset_ids",
        lambda path, dataset: ["CN:SH:600000"],
    )
    monkeypatch.setattr(
        cli,
        "run_market_backfill",
        lambda **kwargs: captured.update(kwargs)
        or {"paths": {"json": str(tmp_path / "report.json"), "csv": str(tmp_path / "report.csv")}},
    )

    args = cli.build_parser().parse_args(
        [
            "rolling-sector-oversold-backfill",
            "--dataset",
            "market_daily_bar",
            "--gap-workplan",
            str(gap_workplan),
            "--start-date",
            "2026-07-29",
            "--end-date",
            "2026-07-29",
            "--adjust-types",
            "raw,qfq,hfq",
            "--source",
            "akshare",
            "--service",
            "stock_research",
            "--dry-run",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert args.command == "rolling-sector-oversold-backfill"
    argv = [
        "rolling-sector-oversold-backfill",
        "--dataset",
        "market_daily_bar",
        "--gap-workplan",
        str(gap_workplan),
        "--start-date",
        "2026-07-29",
        "--end-date",
        "2026-07-29",
        "--adjust-types",
        "raw,qfq,hfq",
        "--source",
        "akshare",
        "--service",
        "stock_research",
        "--dry-run",
        "--output-dir",
        str(tmp_path / "reports"),
    ]
    cli.main_for_args(argv)

    assert captured["asset_ids"] == ["CN:SH:600000"]
    assert captured["adjust_types"] == ("raw", "qfq", "hfq")
    assert captured["source"] == "akshare"
    assert captured["dry_run"] is True


def test_workplan_loader_only_returns_eligible_market_bucket_and_summarizes_bse(
    tmp_path: Path,
):
    workplan = tmp_path / "gap_workplan.json"
    workplan.write_text(
        json.dumps(
            {
                "buckets": {
                    "invalid_membership": ["CN:SZ:000002"],
                    "market_bar_backfill": ["CN:SH:600000"],
                    "out_of_scope_bse": ["CN:BJ:920001"],
                },
                "gap_rows": [
                    {
                        "bucket": "invalid_membership",
                        "dataset": "market_daily_bar",
                        "asset_or_key": "CN:SZ:000002",
                    },
                    {
                        "bucket": "out_of_scope_bse",
                        "dataset": "market_daily_bar",
                        "asset_or_key": "CN:BJ:920001",
                    },
                    {
                        "bucket": "market_bar_backfill",
                        "dataset": "finance_history",
                        "asset_or_key": "CN:SZ:000003",
                    },
                    {
                        "bucket": "market_bar_backfill",
                        "dataset": "market_daily_bar",
                        "asset_or_key": "CN:SH:600000",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert market_backfill.load_gap_workplan_asset_ids(workplan) == [
        "CN:SH:600000"
    ]
    assert market_backfill.load_gap_workplan_exclusions(workplan) == {
        "out_of_scope_bse": ["CN:BJ:920001"],
        "out_of_scope_bse_count": 1,
        "invalid_membership": ["CN:SZ:000002"],
        "invalid_membership_count": 1,
    }


def test_workplan_loader_legacy_buckets_never_falls_back_to_bse_or_invalid(
    tmp_path: Path,
):
    workplan = tmp_path / "legacy_gap_workplan.json"
    workplan.write_text(
        json.dumps(
            {
                "buckets": {
                    "invalid_membership": ["CN:SZ:000002"],
                    "market_bar_backfill": ["CN:SH:600000"],
                    "out_of_scope_bse": ["CN:BJ:920001"],
                }
            }
        ),
        encoding="utf-8",
    )

    assert market_backfill.load_gap_workplan_asset_ids(workplan) == [
        "CN:SH:600000"
    ]
    assert market_backfill.load_gap_workplan_exclusions(workplan) == {
        "out_of_scope_bse": ["CN:BJ:920001"],
        "out_of_scope_bse_count": 1,
        "invalid_membership": ["CN:SZ:000002"],
        "invalid_membership_count": 1,
    }


def test_workplan_loader_falls_back_to_buckets_when_gap_rows_have_no_target_dataset(
    tmp_path: Path,
):
    workplan = tmp_path / "mixed_gap_workplan.json"
    workplan.write_text(
        json.dumps(
            {
                "buckets": {
                    "invalid_membership": ["CN:SZ:000002"],
                    "market_bar_backfill": ["CN:SH:600000"],
                    "out_of_scope_bse": ["CN:BJ:920001"],
                },
                "gap_rows": [
                    {
                        "bucket": "finance_backfill",
                        "dataset": "finance_history",
                        "asset_or_key": "CN:SZ:000003",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert market_backfill.load_gap_workplan_asset_ids(workplan) == [
        "CN:SH:600000"
    ]
    assert market_backfill.load_gap_workplan_exclusions(workplan) == {
        "out_of_scope_bse": ["CN:BJ:920001"],
        "out_of_scope_bse_count": 1,
        "invalid_membership": ["CN:SZ:000002"],
        "invalid_membership_count": 1,
    }


def test_cli_reports_workplan_bse_count_without_expanding_exclusions(
    monkeypatch, tmp_path: Path, capsys
):
    workplan = tmp_path / "gap_workplan.json"
    workplan.write_text(
        json.dumps(
            {
                "buckets": {
                    "invalid_membership": ["CN:SZ:000002"],
                    "market_bar_backfill": ["CN:SH:600000"],
                    "out_of_scope_bse": ["CN:BJ:920001"],
                },
                "gap_rows": [
                    {
                        "bucket": "invalid_membership",
                        "dataset": "market_daily_bar",
                        "asset_or_key": "CN:SZ:000002",
                    },
                    {
                        "bucket": "out_of_scope_bse",
                        "dataset": "market_daily_bar",
                        "asset_or_key": "CN:BJ:920001",
                    },
                    {
                        "bucket": "market_bar_backfill",
                        "dataset": "market_daily_bar",
                        "asset_or_key": "CN:SH:600000",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli,
        "run_market_backfill",
        lambda **kwargs: captured.update(kwargs)
        or {
            "paths": {
                "json": str(tmp_path / "report.json"),
                "csv": str(tmp_path / "report.csv"),
            },
            "status_counts": {},
        },
    )

    cli.main_for_args(
        [
            "rolling-sector-oversold-backfill",
            "--dataset",
            "market_daily_bar",
            "--gap-workplan",
            str(workplan),
            "--start-date",
            "2026-07-29",
            "--end-date",
            "2026-07-30",
            "--adjust-types",
            "raw,qfq,hfq",
            "--source",
            "akshare",
            "--service",
            "stock_research",
            "--dry-run",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert captured["asset_ids"] == ["CN:SH:600000"]
    output = capsys.readouterr().out
    assert "rolling_sector_oversold_backfill|workplan_out_of_scope_bse|1" in output
    assert "rolling_sector_oversold_backfill|workplan_invalid_membership|1" in output
