from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from stock_research import cli
from stock_research.loaders import baostock_ingestion
from stock_research.rolling_oversold import derived_backfill


def _write_workplan(path: Path, *, include_gap_rows: bool = True) -> None:
    payload = {
        "buckets": {
            "derived_backfill": ["csrc:C1:Industry", "em:BK0001"],
            "index_backfill": ["STAR_50"],
            "out_of_scope_index": ["BSE_50"],
        }
    }
    if include_gap_rows:
        payload["gap_rows"] = [
            {
                "bucket": "derived_backfill",
                "dataset": "market.industry_daily_bar",
                "asset_or_key": "csrc:C1:Industry",
            },
            {
                "bucket": "derived_backfill",
                "dataset": "market.concept_daily_bar",
                "asset_or_key": "em:BK0001",
            },
            {
                "bucket": "index_backfill",
                "dataset": "market.index_daily_bar",
                "asset_or_key": "STAR_50",
            },
            {
                "bucket": "out_of_scope_index",
                "dataset": "market.index_daily_bar",
                "asset_or_key": "BSE_50",
            },
        ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_derived_scope_discovers_systems_and_skips_bse(tmp_path: Path):
    workplan = tmp_path / "gap_workplan.json"
    _write_workplan(workplan)

    scope = derived_backfill.load_derived_scope(workplan)

    assert scope["industry_systems"] == ["csrc"]
    assert scope["concept_systems"] == ["em"]
    assert scope["index_ids"] == ["STAR_50"]
    assert scope["out_of_scope_index"] == ["BSE_50"]


def test_load_derived_scope_supports_legacy_buckets_only_workplan(tmp_path: Path):
    workplan = tmp_path / "legacy_gap_workplan.json"
    _write_workplan(workplan, include_gap_rows=False)

    scope = derived_backfill.load_derived_scope(workplan)

    assert scope["industry_systems"] == ["csrc"]
    assert scope["concept_systems"] == ["em"]
    assert scope["index_ids"] == ["STAR_50"]
    assert scope["out_of_scope_index"] == ["BSE_50"]


def test_run_derived_backfill_executes_builders_in_order_for_requested_window(
    monkeypatch, tmp_path: Path
):
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        derived_backfill,
        "build_asset_status_daily_for_service",
        lambda **kwargs: calls.append(("status", kwargs)),
    )
    monkeypatch.setattr(
        derived_backfill,
        "build_industry_daily_bars_for_service",
        lambda **kwargs: calls.append(("industry", kwargs)),
    )
    monkeypatch.setattr(
        derived_backfill,
        "build_concept_daily_bars_for_service",
        lambda **kwargs: calls.append(("concept", kwargs)),
    )
    monkeypatch.setattr(
        derived_backfill,
        "sync_index_daily_bars",
        lambda **kwargs: calls.append(("index", kwargs)) or 252,
    )
    monkeypatch.setattr(
        derived_backfill,
        "verify_index_coverage",
        lambda **kwargs: {"STAR_50": 252},
    )

    result = derived_backfill.run_derived_backfill(
        start_date=date(2025, 5, 28),
        end_date=date(2026, 7, 31),
        industry_systems=("csrc",),
        concept_systems=("em",),
        service="stock_research",
        dry_run=False,
        output_dir=tmp_path,
    )

    assert [name for name, _kwargs in calls] == [
        "status",
        "industry",
        "concept",
        "index",
    ]
    assert calls[0][1] == {
        "start_date": "2025-05-28",
        "end_date": "2026-07-31",
        "adjust_type": "hfq",
        "service": "stock_research",
    }
    assert calls[1][1]["industry_system"] == "csrc"
    assert calls[1][1]["adjust_type"] == "qfq"
    assert calls[2][1]["concept_system"] == "em"
    assert calls[2][1]["adjust_type"] == "qfq"
    assert calls[3][1]["index_ids"] == ("STAR_50",)
    assert result["asset_status_daily"]["start_date"] == "2025-05-28"
    assert result["industry_daily_bar"]["systems"] == ["csrc"]
    assert result["concept_daily_bar"]["systems"] == ["em"]
    assert result["index_daily_bar"]["indices"] == ["STAR_50"]


def test_run_derived_backfill_discovers_active_systems_without_workplan(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(
        derived_backfill,
        "discover_derived_scope",
        lambda **kwargs: {
            "industry_systems": ["sw"],
            "concept_systems": ["ths"],
            "index_ids": ["STAR_50"],
            "out_of_scope_index": ["BSE_50"],
        },
    )

    result = derived_backfill.run_derived_backfill(
        start_date="2026-07-29",
        end_date="2026-07-31",
        service="stock_research",
        dry_run=True,
        output_dir=tmp_path,
    )

    assert result["industry_daily_bar"]["systems"] == ["sw"]
    assert result["concept_daily_bar"]["systems"] == ["ths"]
    assert result["index_daily_bar"]["indices"] == ["STAR_50"]
    assert result["out_of_scope_index"] == ["BSE_50"]


def test_run_derived_backfill_dry_run_does_not_call_builders_or_index_adapter(
    monkeypatch, tmp_path: Path
):
    calls: list[str] = []
    for name in (
        "build_asset_status_daily_for_service",
        "build_industry_daily_bars_for_service",
        "build_concept_daily_bars_for_service",
        "sync_index_daily_bars",
    ):
        monkeypatch.setattr(
            derived_backfill,
            name,
            lambda *args, _name=name, **kwargs: calls.append(_name),
        )

    result = derived_backfill.run_derived_backfill(
        start_date="2026-07-29",
        end_date="2026-07-31",
        industry_systems=("csrc",),
        concept_systems=("em",),
        service="stock_research",
        dry_run=True,
        output_dir=tmp_path,
    )

    assert calls == []
    assert result["dry_run"] is True
    assert result["asset_status_daily"]["status"] == "planned"
    assert result["index_daily_bar"]["status"] == "planned"


def test_run_derived_backfill_keeps_bse_index_out_of_scope(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(
        derived_backfill,
        "sync_index_daily_bars",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("BSE_50 must not reach the index adapter")
        ),
    )

    result = derived_backfill.run_derived_backfill(
        start_date="2026-07-29",
        end_date="2026-07-31",
        index_ids=("BSE_50",),
        service="stock_research",
        dry_run=True,
        output_dir=tmp_path,
    )

    assert result["index_daily_bar"]["indices"] == []
    assert result["out_of_scope_index"] == ["BSE_50"]


def test_sync_index_daily_bars_selects_star_without_requesting_bse(monkeypatch):
    captured: dict[str, object] = {}
    upserted: list[dict[str, object]] = []

    monkeypatch.setattr(
        baostock_ingestion,
        "query_akshare_index_daily_rows",
        lambda *, start_date, end_date, targets=None: captured.update(
            {"start_date": start_date, "end_date": end_date, "targets": targets}
        )
        or [
            {
                "index_id": "STAR_50",
                "trade_date": "2026-07-31",
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.05,
                "preclose": 1.0,
                "volume": 1.0,
                "amount": 1.0,
                "source": "akshare",
            }
        ],
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "connect",
        lambda service: type(
            "Context",
            (),
            {
                "__enter__": lambda self: self,
                "__exit__": lambda self, exc_type, exc, tb: False,
            },
        )(),
    )
    monkeypatch.setattr(
        baostock_ingestion,
        "upsert_index_daily_bars",
        lambda conn, rows: upserted.extend(rows) or len(rows),
    )
    monkeypatch.setattr(
        baostock_ingestion.bs,
        "login",
        lambda: (_ for _ in ()).throw(AssertionError("STAR_50 must not use BSE/baostock targets")),
    )

    count = baostock_ingestion.sync_index_daily_bars(
        "2026-07-31",
        "2026-07-31",
        service="stock_research",
        index_ids=("STAR_50",),
    )

    assert count == 1
    assert captured["targets"] == {"STAR_50": "sh000688"}
    assert {row["index_id"] for row in upserted} == {"STAR_50"}


def test_cli_dispatches_derived_backfill_without_market_source_arguments(
    monkeypatch, tmp_path: Path
):
    workplan = tmp_path / "gap_workplan.json"
    _write_workplan(workplan)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli,
        "run_derived_backfill",
        lambda **kwargs: captured.update(kwargs)
        or {
            "paths": {
                "json": str(tmp_path / "report.json"),
                "csv": str(tmp_path / "report.csv"),
            },
            "asset_status_daily": {"status": "planned"},
            "industry_daily_bar": {"systems": ["csrc"]},
            "concept_daily_bar": {"systems": ["em"]},
            "index_daily_bar": {"indices": ["STAR_50"]},
            "out_of_scope_index": ["BSE_50"],
        },
    )

    argv = [
        "rolling-sector-oversold-backfill",
        "--dataset",
        "derived",
        "--gap-workplan",
        str(workplan),
        "--start-date",
        "2026-07-29",
        "--end-date",
        "2026-07-31",
        "--service",
        "stock_research",
        "--dry-run",
        "--output-dir",
        str(tmp_path / "reports"),
    ]

    args = cli.build_parser().parse_args(argv)
    assert args.dataset == "derived"
    cli.main_for_args(argv)

    assert captured["gap_workplan"] == str(workplan)
    assert captured["start_date"] == "2026-07-29"
    assert captured["end_date"] == "2026-07-31"
    assert captured["dry_run"] is True
