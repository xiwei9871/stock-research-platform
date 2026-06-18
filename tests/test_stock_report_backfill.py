from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.stock_report_backfill import (
    build_stock_report_backfill_plan,
    build_stock_report_feature_backfill,
    merge_existing_status_into_tasks,
    run_stock_report_backfill_run,
    run_stock_report_backfill_tasks,
)
from stock_research.stock_report_web_collection import build_stock_report_features_from_events
from stock_research.stock_report_backfill_watchdog import (
    StockReportBackfillWatchdogAdapter,
    run_stock_report_backfill_watchdog,
)


def _assets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "CN:SZ:002484", "ts_code": "002484.SZ", "stock_name": "江海股份", "symbol": "002484"},
            {"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "symbol": "600183"},
        ]
    )


def test_backfill_plan_builds_pending_tasks_without_fetching(tmp_path: Path):
    result = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
        output_dir=tmp_path,
    )

    tasks = result["tasks"]
    assert len(tasks) == 2
    assert set(tasks["status"]) == {"pending"}
    assert tasks["task_id"].is_unique
    assert tasks.iloc[0]["provider"] == "akshare_em"
    assert "stock_report_backfill_tasks_2025_to_2026.csv" in result["paths"]["tasks"]
    assert Path(result["paths"]["tasks"]).exists()
    assert "不抓取研报全文" in result["report"]


def test_backfill_run_filters_report_dates_and_builds_source_events(tmp_path: Path):
    tasks = build_stock_report_backfill_plan(
        assets=_assets().head(1),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]

    def fake_fetcher(symbol: str) -> pd.DataFrame:
        assert symbol == "002484"
        return pd.DataFrame(
            [
                {
                    "股票代码": "002484",
                    "股票简称": "江海股份",
                    "报告名称": "公司深度报告：乘AI之风",
                    "东财评级": "买入",
                    "机构": "爱建证券",
                    "行业": "元件",
                    "日期": "2026-04-23",
                    "报告PDF链接": "https://pdf.dfcfw.com/pdf/H3_AP202604231821501366_1.pdf",
                },
                {
                    "股票代码": "002484",
                    "股票简称": "江海股份",
                    "报告名称": "过早报告",
                    "东财评级": "买入",
                    "机构": "测试证券",
                    "行业": "元件",
                    "日期": "2024-12-31",
                    "报告PDF链接": "https://pdf.dfcfw.com/pdf/old.pdf",
                },
                {
                    "股票代码": "002484",
                    "股票简称": "江海股份",
                    "报告名称": "未来报告",
                    "东财评级": "买入",
                    "机构": "测试证券",
                    "行业": "元件",
                    "日期": "2026-06-10",
                    "报告PDF链接": "https://pdf.dfcfw.com/pdf/future.pdf",
                },
            ]
        )

    result = run_stock_report_backfill_tasks(
        tasks,
        start_date="2025-01-01",
        end_date="2026-06-02",
        fetcher=fake_fetcher,
        output_dir=tmp_path,
    )

    status = result["status"]
    assert status.iloc[0]["status"] == "done"
    assert status.iloc[0]["report_count"] == 1
    assert len(result["sources"]) == 1
    assert len(result["events"]) == 1
    assert result["events"].iloc[0]["report_date"] == "2026-04-23"
    assert not bool(result["events"].iloc[0]["auto_trade_enabled"])
    assert Path(result["paths"]["events"]).exists()


def test_backfill_run_resumes_done_tasks_and_records_fetch_errors():
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    tasks.loc[0, "status"] = "done"

    def fake_fetcher(symbol: str) -> pd.DataFrame:
        raise RuntimeError("boom")

    result = run_stock_report_backfill_tasks(
        tasks,
        start_date="2025-01-01",
        end_date="2026-06-02",
        fetcher=fake_fetcher,
    )

    status = result["status"].sort_values("ts_code").reset_index(drop=True)
    assert status.loc[0, "status"] == "done"
    assert status.loc[1, "status"] == "fetch_error"
    assert "boom" in status.loc[1, "error_message"]


def test_backfill_run_treats_akshare_infocode_keyerror_as_no_report():
    tasks = build_stock_report_backfill_plan(
        assets=_assets().head(1),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]

    def fake_fetcher(symbol: str) -> pd.DataFrame:
        raise KeyError("infoCode")

    result = run_stock_report_backfill_tasks(
        tasks,
        start_date="2025-01-01",
        end_date="2026-06-02",
        fetcher=fake_fetcher,
    )

    status = result["status"].iloc[0]
    assert status["status"] == "no_report"
    assert status["report_count"] == 0
    assert "infoCode" in status["error_message"]


def test_backfill_run_preserves_zero_padded_symbols_from_csv(tmp_path: Path):
    tasks = build_stock_report_backfill_plan(
        assets=_assets().head(1),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    path = tmp_path / "tasks.csv"
    tasks.to_csv(path, index=False)
    seen = []

    def fake_fetcher(symbol: str) -> pd.DataFrame:
        seen.append(symbol)
        return pd.DataFrame()

    loaded = pd.read_csv(path, dtype={"symbol": "string", "ts_code": "string"}, low_memory=False)
    run_stock_report_backfill_tasks(
        loaded,
        start_date="2025-01-01",
        end_date="2026-06-02",
        fetcher=fake_fetcher,
    )

    assert seen == ["002484"]


def test_backfill_run_batch_selects_next_pending_task_after_done_rows():
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    tasks.loc[0, "status"] = "done"
    seen = []

    def fake_fetcher(symbol: str) -> pd.DataFrame:
        seen.append(symbol)
        return pd.DataFrame()

    result = run_stock_report_backfill_tasks(
        tasks,
        start_date="2025-01-01",
        end_date="2026-06-02",
        batch_size=1,
        fetcher=fake_fetcher,
    )

    assert seen == ["600183"]
    assert len(result["status"]) == 2
    assert result["status"].set_index("symbol").loc["002484", "status"] == "done"
    assert result["status"].set_index("symbol").loc["600183", "status"] == "no_report"


def test_backfill_run_writes_status_after_each_task(tmp_path: Path):
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    snapshots = []

    def fake_fetcher(symbol: str) -> pd.DataFrame:
        status_path = tmp_path / "stock_report_backfill_status_2025_to_2026.csv"
        if status_path.exists():
            snapshots.append(pd.read_csv(status_path, dtype={"symbol": "string"}, low_memory=False))
        return pd.DataFrame()

    run_stock_report_backfill_tasks(
        tasks,
        start_date="2025-01-01",
        end_date="2026-06-02",
        fetcher=fake_fetcher,
        output_dir=tmp_path,
    )

    assert snapshots
    first_snapshot = snapshots[0].set_index("symbol")
    assert first_snapshot.loc["002484", "status"] == "no_report"
    assert first_snapshot.loc["600183", "status"] == "pending"


def test_backfill_run_wrapper_returns_tasks_path_for_cli_output(tmp_path: Path):
    tasks = build_stock_report_backfill_plan(
        assets=_assets().head(1),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    tasks_path = tmp_path / "tasks.csv"
    tasks.to_csv(tasks_path, index=False)

    result = run_stock_report_backfill_run(
        tasks_path=tasks_path,
        start_date="2025-01-01",
        end_date="2026-06-02",
        output_dir=tmp_path,
        sleep_seconds=0.0,
    )

    assert result["paths"]["tasks"] == str(tasks_path)


def test_stock_report_watchdog_adapter_reads_status_counts(tmp_path: Path):
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    tasks.to_csv(tmp_path / "stock_report_backfill_tasks_2025_to_2026.csv", index=False)
    status = tasks.copy()
    status.loc[0, "status"] = "done"
    status.loc[0, "report_count"] = 2
    status.loc[1, "status"] = "pending"
    status.to_csv(tmp_path / "stock_report_backfill_status_2025_to_2026.csv", index=False)

    adapter = StockReportBackfillWatchdogAdapter(output_dir=tmp_path)
    rows = adapter.load_status_rows()
    summary = adapter.summarize_status(rows)

    assert summary.total_tasks == 2
    assert summary.success_tasks == 1
    assert summary.pending_tasks == 1
    assert summary.total_rows_written == 2
    assert adapter.compute_frontier(rows) == {
        "completed_through": "002484.SZ",
        "currently_working_on": "600183.SH",
    }


def test_stock_report_watchdog_uses_full_tasks_as_denominator(tmp_path: Path):
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    tasks.to_csv(tmp_path / "stock_report_backfill_tasks_2025_to_2026.csv", index=False)
    status = tasks.head(1).copy()
    status.loc[0, "status"] = "done"
    status.loc[0, "report_count"] = 2
    status.to_csv(tmp_path / "stock_report_backfill_status_2025_to_2026.csv", index=False)

    adapter = StockReportBackfillWatchdogAdapter(output_dir=tmp_path)
    rows = adapter.load_status_rows()
    summary = adapter.summarize_status(rows)

    assert summary.total_tasks == 2
    assert summary.success_tasks == 1
    assert summary.pending_tasks == 1
    assert summary.total_rows_written == 2


def test_stock_report_watchdog_skips_feishu_when_complete(monkeypatch, tmp_path: Path):
    status = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    status.to_csv(tmp_path / "stock_report_backfill_tasks_2025_to_2026.csv", index=False)
    status["status"] = "no_report"
    status.to_csv(tmp_path / "stock_report_backfill_status_2025_to_2026.csv", index=False)
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr("stock_research.stock_report_backfill_watchdog.send_openclaw_feishu_message", fake_send)

    result = run_stock_report_backfill_watchdog(
        output_dir=tmp_path,
        report_target="feishu-group",
        report_dry_run=True,
    )

    assert result["status"].watchdog_action == "healthy"
    assert result["status"].work_remaining is False
    assert sent == []


def test_stock_report_watchdog_reports_pending_as_healthy_observe_only(monkeypatch, tmp_path: Path):
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    tasks.to_csv(tmp_path / "stock_report_backfill_tasks_2025_to_2026.csv", index=False)
    sent = []

    monkeypatch.setattr(
        "stock_research.stock_report_backfill_watchdog.send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_stock_report_backfill_watchdog(
        output_dir=tmp_path,
        report_target="invalid-target-for-dry-run",
        report_dry_run=True,
    )

    assert result["status"].watchdog_action == "healthy"
    assert result["status"].work_remaining is True
    assert result["post_summary"].pending_tasks == 2
    assert sent == []


def test_cli_accepts_stock_report_backfill_watchdog_command():
    args = cli.build_parser().parse_args(
        [
            "stock-report-backfill-watchdog",
            "--output-dir",
            "outputs/research/stock_report_backfill_2025_to_2026",
            "--report-target",
            "feishu-group",
            "--report-dry-run",
        ]
    )

    assert args.command == "stock-report-backfill-watchdog"
    assert args.report_target == "feishu-group"


def test_cli_dispatches_stock_report_backfill_watchdog(monkeypatch, tmp_path: Path, capsys):
    captured = {}

    class FakeStatus:
        watchdog_action = "healthy"
        work_remaining = False

    class FakeSummary:
        success_tasks = 1
        skipped_tasks = 2
        failed_tasks = 0
        pending_tasks = 0
        total_rows_written = 3

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": FakeStatus(),
            "post_summary": FakeSummary(),
        }

    monkeypatch.setattr(cli, "run_stock_report_backfill_watchdog", fake_run)

    cli.main_for_args(
        [
            "stock-report-backfill-watchdog",
            "--output-dir",
            str(tmp_path),
            "--report-target",
            "feishu-group",
            "--report-dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert captured["output_dir"] == str(tmp_path)
    assert captured["report_target"] == "feishu-group"
    assert "stock_report_backfill_watchdog|action|healthy" in out
    assert "stock_report_backfill_watchdog|pending|0" in out


def test_merge_existing_status_into_tasks_preserves_completed_rows():
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    status = tasks.head(1).copy()
    status.loc[0, "status"] = "done"
    status.loc[0, "report_count"] = 3
    status.loc[0, "latest_report_date"] = "2026-04-23"

    merged = merge_existing_status_into_tasks(tasks, status)

    first = merged.set_index("task_id").loc[status.loc[0, "task_id"]]
    assert first["status"] == "done"
    assert first["report_count"] == 3
    assert first["latest_report_date"] == "2026-04-23"
    assert merged["status"].value_counts().to_dict()["pending"] == 1


def test_merge_existing_status_handles_empty_date_columns_loaded_as_float():
    tasks = build_stock_report_backfill_plan(
        assets=_assets(),
        start_date="2025-01-01",
        end_date="2026-06-02",
    )["tasks"]
    tasks["latest_report_date"] = float("nan")
    status = pd.DataFrame(
        [
            {
                **tasks.iloc[0].to_dict(),
                "status": "done",
                "latest_report_date": "2026-04-26",
            }
        ],
        dtype=object,
    )

    merged = merge_existing_status_into_tasks(tasks, status)

    assert merged.loc[0, "latest_report_date"] == "2026-04-26"


def test_feature_backfill_builds_point_in_time_daily_rows():
    events = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-01-05",
                "rating": "买入",
                "broker": "爱建证券",
            },
            {
                "report_id": "r2",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-02-10",
                "rating": "增持",
                "broker": "开源证券",
            },
        ]
    )
    trade_dates = ["2026-01-06", "2026-02-11"]

    result = build_stock_report_feature_backfill(
        events=events,
        trade_dates=trade_dates,
    )

    features = result["features"].sort_values("trade_date").reset_index(drop=True)
    assert len(features) == 2
    assert features.loc[0, "report_count_90d"] == 1
    assert features.loc[1, "report_count_90d"] == 2
    assert features.loc[1, "positive_rating_count"] == 2


def test_feature_backfill_matches_single_day_pit_builder():
    events = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-01-05",
                "rating": "买入",
                "rating_change": "",
                "broker": "中信证券",
                "target_price": 10.0,
                "target_upside": 0.2,
                "negative_report_flag": False,
            },
            {
                "report_id": "r2",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-04-20",
                "rating": "增持",
                "rating_change": "上调",
                "broker": "开源证券",
                "target_price": 12.0,
                "target_upside": 0.3,
                "negative_report_flag": False,
            },
            {
                "report_id": "r3",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "report_date": "2026-04-21",
                "rating": "中性",
                "rating_change": "",
                "broker": "测试证券",
                "target_price": pd.NA,
                "target_upside": pd.NA,
                "negative_report_flag": True,
            },
        ]
    )
    trade_dates = ["2026-01-06", "2026-04-22"]

    fast = build_stock_report_feature_backfill(events=events, trade_dates=trade_dates)["features"]
    expected_frames = []
    normalized = events.copy()
    normalized["report_date"] = pd.to_datetime(normalized["report_date"])
    for trade_date in trade_dates:
        point_in_time = normalized[normalized["report_date"].le(pd.to_datetime(trade_date))].copy()
        expected_frames.append(build_stock_report_features_from_events(point_in_time, trade_date=trade_date)["features"])
    expected = pd.concat(expected_frames, ignore_index=True)

    columns = [
        "trade_date",
        "ts_code",
        "report_count_30d",
        "report_count_90d",
        "latest_report_days",
        "positive_rating_count",
        "rating_upgrade_count",
        "broker_coverage_count",
        "top_broker_coverage_count",
        "negative_report_flag",
        "source_count",
    ]
    fast_cmp = fast[columns].sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    expected_cmp = expected[columns].sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(fast_cmp, expected_cmp)


def test_feature_backfill_aggregates_pdf_extract_metadata_with_pit_window():
    events = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-01-05",
                "rating": "买入",
                "broker": "中信证券",
                "target_price": 10.0,
                "metadata": {
                    "pdf_extract": {
                        "target_price_confidence": 0.8,
                        "forecast_eps_values": [1.0],
                        "forecast_pe_values": [20.0],
                        "has_profit_forecast": True,
                        "has_risk_section": True,
                        "risk_summary": "需求不及预期",
                    }
                },
            },
            {
                "report_id": "r2",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "report_date": "2026-04-20",
                "rating": "增持",
                "broker": "开源证券",
                "target_price": 12.0,
                "metadata": {
                    "pdf_extract": {
                        "target_price_confidence": 0.6,
                        "forecast_eps_values": [],
                        "forecast_pe_values": [18.0],
                        "has_profit_forecast": False,
                        "has_risk_section": False,
                    }
                },
            },
        ]
    )

    features = build_stock_report_feature_backfill(
        events=events,
        trade_dates=["2026-01-06", "2026-04-22"],
    )["features"].sort_values("trade_date").reset_index(drop=True)

    first_metadata = features.loc[0, "metadata"]
    second_metadata = features.loc[1, "metadata"]
    assert first_metadata["pdf_target_price_count_90d"] == 1
    assert first_metadata["pdf_target_price_high_confidence_count_90d"] == 1
    assert second_metadata["pdf_target_price_count_90d"] == 1
    assert second_metadata["pdf_target_price_high_confidence_count_90d"] == 0
    assert second_metadata["pdf_pe_forecast_count_90d"] == 1


def test_cli_dispatches_stock_report_backfill_plan(monkeypatch, tmp_path: Path, capsys):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "tasks": pd.DataFrame([{"task_id": "T1"}]),
            "paths": {"tasks": str(tmp_path / "tasks.csv"), "report": str(tmp_path / "report.md")},
        }

    monkeypatch.setattr(cli, "run_stock_report_backfill_plan", fake_run)

    cli.main_for_args(
        [
            "stock-report-backfill-plan",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-02",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["start_date"] == "2025-01-01"
    assert "stock_report_backfill_plan|tasks|" in capsys.readouterr().out
