from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pytest

from stock_research import cli
from stock_research.rolling_oversold import fundamental_backfill


def _finance_rows(asset_id: str) -> list[dict[str, object]]:
    periods = (
        "2026-03-31",
        "2025-12-31",
        "2025-09-30",
        "2025-06-30",
        "2025-03-31",
    )
    return [
        {
            "asset_id": asset_id,
            "report_period": period,
            "announcement_date": "2026-04-30",
            "revenue": 100.0,
            "np_parent": 10.0,
            "source": "baostock",
            "calc_version": "baostock_v1",
        }
        for period in periods
    ]


def test_finance_backfill_never_publishes_future_announcements():
    rows = fundamental_backfill.build_finance_backfill_rows(
        asset_ids=["CN:SZ:000001"],
        cutoff=date(2026, 7, 21),
        source_rows=[
            *_finance_rows("CN:SZ:000001"),
            {
                **_finance_rows("CN:SZ:000001")[0],
                "announcement_date": "2026-07-22",
            },
        ],
    )
    assert all(row["announcement_date"] <= date(2026, 7, 21) for row in rows)
    assert len({row["report_period"] for row in rows}) >= 5


def test_valuation_backfill_keeps_factor_names_and_version():
    rows = fundamental_backfill.build_valuation_backfill_rows(
        asset_ids=["CN:SZ:000001"],
        start_date=date(2025, 5, 28),
        end_date=date(2026, 7, 31),
        source_rows=[
            {
                "asset_id": "CN:SZ:000001",
                "trade_date": "2026-07-31",
                "factor_name": name,
                "factor_value": 1.0,
                "calc_version": "value_v1",
            }
            for name in ("pe_ttm", "ps_ttm", "ev_ebitda")
        ],
    )
    assert {row["factor_name"] for row in rows} <= {"pe_ttm", "ps_ttm", "ev_ebitda"}
    assert all(row["calc_version"] for row in rows)


def test_valuation_backfill_replaces_empty_version_and_keeps_nan_unwritable():
    rows = fundamental_backfill.build_valuation_backfill_rows(
        asset_ids=["CN:SZ:000001"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
        source_rows=[
            {
                "asset_id": "CN:SZ:000001",
                "trade_date": "2026-07-31",
                "factor_name": "pe_ttm",
                "factor_value": math.nan,
                "calc_version": None,
                "computed_at": "2026-07-31T09:00:00+08:00",
            }
        ],
    )
    assert rows[0]["calc_version"]
    assert not fundamental_backfill._usable_factor_value(rows[0]["factor_value"])


def test_workplan_scope_only_returns_eligible_finance_and_valuation_assets(tmp_path: Path):
    path = tmp_path / "gap_workplan.json"
    path.write_text(
        json.dumps(
            {
                "buckets": {
                    "finance_backfill": ["CN:SZ:000001", "CN:BJ:920001"],
                    "valuation_backfill": ["CN:SZ:000001", "CN:SH:600000"],
                    "out_of_scope_bse": ["CN:BJ:920001"],
                    "invalid_membership": ["CN:SZ:999999"],
                },
                "gap_rows": [
                    {
                        "bucket": "finance_backfill",
                        "dataset": "finance_history",
                        "asset_or_key": "CN:SZ:000001",
                    },
                    {
                        "bucket": "valuation_backfill",
                        "dataset": "valuation_history",
                        "asset_or_key": "CN:SH:600000",
                    },
                    {
                        "bucket": "out_of_scope_bse",
                        "dataset": "finance_history",
                        "asset_or_key": "CN:BJ:920001",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    scope = fundamental_backfill.load_fundamental_scope(path)

    assert scope["finance_assets"] == ["CN:SZ:000001"]
    assert scope["valuation_assets"] == ["CN:SH:600000"]
    assert scope["out_of_scope_bse"] == ["CN:BJ:920001"]
    assert scope["invalid_membership"] == ["CN:SZ:999999"]


def test_run_fundamental_backfill_dry_run_never_calls_adapter_or_writer(monkeypatch, tmp_path: Path):
    calls: list[str] = []
    monkeypatch.setattr(
        fundamental_backfill,
        "sync_finance_for_assets",
        lambda *args, **kwargs: calls.append("adapter"),
    )
    monkeypatch.setattr(
        fundamental_backfill,
        "_upsert_valuation_rows",
        lambda *args, **kwargs: calls.append("writer"),
    )
    workplan = tmp_path / "gap_workplan.json"
    workplan.write_text(
        json.dumps(
            {
                "buckets": {
                    "finance_backfill": ["CN:SZ:000001"],
                    "valuation_backfill": ["CN:SZ:000001"],
                }
            }
        ),
        encoding="utf-8",
    )

    result = fundamental_backfill.run_fundamental_backfill(
        start_date=date(2025, 5, 28),
        end_date=date(2026, 7, 31),
        gap_workplan=workplan,
        service="stock_research",
        dry_run=True,
        output_dir=tmp_path / "out",
    )

    assert calls == []
    assert result["dry_run"] is True
    assert Path(result["paths"]["json"]).exists()


def test_execute_uses_only_scoped_assets_and_visible_rows(monkeypatch, tmp_path: Path):
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        fundamental_backfill,
        "_load_finance_rows",
        lambda *args, **kwargs: _finance_rows("CN:SZ:000001"),
    )
    monkeypatch.setattr(fundamental_backfill, "_load_valuation_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        fundamental_backfill,
        "_upsert_valuation_rows",
        lambda *args, **kwargs: 0,
    )

    def fake_adapter(*, asset_ids, year, quarter, service, cutoff):
        calls.append(
            {
                "asset_ids": asset_ids,
                "year": year,
                "quarter": quarter,
                "cutoff": cutoff,
            }
        )
        return {"indicator_quarter": 1, "income_statement": 1, "share_capital_event": 1}

    workplan = tmp_path / "gap_workplan.json"
    workplan.write_text(
        json.dumps(
            {
                "buckets": {
                    "finance_backfill": ["CN:SZ:000001", "CN:BJ:920001"],
                    "valuation_backfill": ["CN:SZ:000001"],
                }
            }
        ),
        encoding="utf-8",
    )
    result = fundamental_backfill.run_fundamental_backfill(
        start_date=date(2025, 5, 28),
        end_date=date(2026, 7, 31),
        gap_workplan=workplan,
        service="stock_research",
        dry_run=False,
        output_dir=tmp_path / "out",
        finance_adapter=fake_adapter,
    )

    assert len(calls) == 6
    assert all(call["asset_ids"] == ["CN:SZ:000001"] for call in calls)
    assert all(call["cutoff"] == date(2026, 7, 31) for call in calls)
    assert result["finance"]["requested_periods"][-1] == "2025-03-31"
    assert result["finance"]["visible_report_periods"]["CN:SZ:000001"] >= 5


def test_execute_reports_short_finance_history_without_fabricating_rows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        fundamental_backfill,
        "_load_finance_rows",
        lambda *args, **kwargs: _finance_rows("CN:SZ:000001")[:4],
    )
    monkeypatch.setattr(fundamental_backfill, "_load_valuation_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(fundamental_backfill, "_upsert_valuation_rows", lambda *args, **kwargs: 0)

    workplan = tmp_path / "gap_workplan.json"
    workplan.write_text(
        json.dumps({"buckets": {"finance_backfill": ["CN:SZ:000001"]}}),
        encoding="utf-8",
    )
    result = fundamental_backfill.run_fundamental_backfill(
        start_date=date(2025, 5, 28),
        end_date=date(2026, 7, 31),
        gap_workplan=workplan,
        dry_run=False,
        output_dir=tmp_path / "out",
        finance_adapter=lambda year, quarter, service: {},
    )

    assert result["finance"]["visible_report_periods"]["CN:SZ:000001"] == 4
    assert result["finance"]["incomplete_assets"] == ["CN:SZ:000001"]


def test_cli_accepts_fundamentals_dataset(monkeypatch, tmp_path: Path, capsys):
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        cli,
        "run_fundamental_backfill",
        lambda **kwargs: calls.append(kwargs)
        or {
            "paths": {"json": str(tmp_path / "report.json"), "csv": str(tmp_path / "report.csv")},
            "finance": {"requested": 1},
            "valuation": {"requested": 3},
            "exclusions": {},
        },
    )

    cli.main(
        [
            "rolling-sector-oversold-backfill",
            "--dataset",
            "fundamentals",
            "--gap-workplan",
            str(tmp_path / "workplan.json"),
            "--start-date",
            "2025-05-28",
            "--end-date",
            "2026-07-31",
            "--service",
            "stock_research",
        ]
    )

    assert calls[0]["dry_run"] is True
    assert "rolling_sector_oversold_fundamentals_backfill|report|" in capsys.readouterr().out
