from datetime import date

import pytest

from stock_research.eod_auto_repair_actions import (
    repair_generated_reports,
    repair_lhb_source_and_features,
    repair_market_monitor,
    repair_minute5_bars,
    repair_minute5_raw_bars,
    repair_review_evidence_snapshots,
    repair_score_topn,
    repair_strategy_publish,
    repair_technical_features,
    repair_watchlist,
)
from stock_research.eod_auto_repair_models import RepairStatus


def test_repair_minute5_bars_rejects_multiple_workers():
    with pytest.raises(ValueError, match="Baostock minute backfill must use workers=1"):
        repair_minute5_bars("2026-06-29", workers=2, runner=lambda **kwargs: {})


def test_repair_minute5_bars_runs_single_worker_batches_until_no_pending_jobs():
    calls = []
    progress_events = []
    batches = iter([
        {"attempted": 100, "success": 99, "failed": 1, "rows": 4752},
        {"attempted": 25, "success": 25, "failed": 0, "rows": 1200},
        {"attempted": 0, "success": 0, "failed": 0, "rows": 0},
    ])

    def runner(**kwargs):
        calls.append(kwargs)
        kwargs["progress"]({"event": "minute_backfill_progress", "completed": 100})
        return next(batches)

    result = repair_minute5_bars(
        "2026-06-29",
        workers=1,
        runner=runner,
        progress=progress_events.append,
        batch_size=100,
    )

    assert result.status == RepairStatus.SUCCESS
    assert [call["workers"] for call in calls] == [1, 1, 1]
    assert [call["max_jobs"] for call in calls] == [100, 100, 100]
    assert [call["reset_stale_before_run"] for call in calls] == [True, False, False]
    assert all(call["retry_failed"] is True for call in calls)
    assert all(call["start_date"] == "2026-06-29" for call in calls)
    assert all(call["end_date"] == "2026-06-29" for call in calls)
    assert result.metrics == {"attempted": 125, "success": 124, "failed": 1, "rows": 5952, "batches": 3}
    assert progress_events == [
        {"event": "minute_backfill_progress", "completed": 100},
        {"event": "minute_backfill_progress", "completed": 100},
        {"event": "minute_backfill_progress", "completed": 100},
    ]


def test_repair_minute5_raw_bars_fetches_missing_raw_and_derives_qfq():
    calls = []
    upserted = []
    derived = []
    quality = []

    def missing_loader(trade_date):
        calls.append(("missing", trade_date))
        return ["600000.SH", "000001.SZ"]

    def raw_fetcher(ts_code, start_date, end_date, timeout_seconds):
        calls.append(("fetch", ts_code, start_date, end_date, timeout_seconds))
        return [
            {
                "ts_code": ts_code,
                "trade_date": start_date,
                "adjust_type": "raw",
            }
        ]

    def upserter(service, rows):
        upserted.extend(rows)
        return len(rows)

    def qfq_deriver(service, trade_date):
        derived.append((service, trade_date))
        return {"raw_rows": 2, "inserted_rows": 2}

    def quality_refresher(service, trade_date):
        quality.append((service, trade_date))
        return {"expected_count": 2, "actual_count": 2, "missing_symbols": [], "abnormal_symbols": []}

    result = repair_minute5_raw_bars(
        "2026-07-06",
        service="test",
        missing_symbols_loader=missing_loader,
        raw_fetcher=raw_fetcher,
        upserter=upserter,
        qfq_deriver=qfq_deriver,
        quality_refresher=quality_refresher,
        timeout_seconds=30,
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics == {
        "attempted": 2,
        "success": 2,
        "failed": 0,
        "rows": 2,
        "qfq_rows": 2,
        "remaining_missing": 0,
        "remaining_abnormal": 0,
    }
    assert [row["adjust_type"] for row in upserted] == ["raw", "raw"]
    assert derived == [("test", date(2026, 7, 6))]
    assert quality == [("test", date(2026, 7, 6))]


def test_repair_minute5_raw_bars_reports_failed_noop_when_no_missing_symbols():
    result = repair_minute5_raw_bars(
        "2026-07-06",
        service="test",
        missing_symbols_loader=lambda _trade_date: [],
        raw_fetcher=lambda **_kwargs: [],
        upserter=lambda _service, rows: len(rows),
        qfq_deriver=lambda _service, _trade_date: {"inserted_rows": 0},
        quality_refresher=lambda _service, _trade_date: {},
    )

    assert result.status == RepairStatus.FAILED
    assert result.message == "minute5 raw repair had no missing symbols to attempt"
    assert result.metrics["attempted"] == 0


def test_repair_minute5_raw_bars_sleeps_between_baostock_symbols(monkeypatch):
    import stock_research.eod_auto_repair_actions as eod_auto_repair_actions

    sleeps = []

    monkeypatch.setattr(eod_auto_repair_actions.time, "sleep", sleeps.append)

    result = repair_minute5_raw_bars(
        "2026-07-06",
        service="test",
        missing_symbols_loader=lambda _trade_date: ["600000.SH", "000001.SZ"],
        raw_fetcher=lambda ts_code, **_kwargs: [
            {"ts_code": ts_code, "trade_date": date(2026, 7, 6), "adjust_type": "raw"}
        ],
        upserter=lambda _service, rows: len(rows),
        qfq_deriver=lambda _service, _trade_date: {"inserted_rows": 2},
        quality_refresher=lambda _service, _trade_date: {"missing_symbols": [], "abnormal_symbols": []},
        symbol_sleep_seconds=0.75,
    )

    assert result.status == RepairStatus.SUCCESS
    assert sleeps == [0.75, 0.75]


def test_repair_lhb_source_and_features_runs_enrichment_then_feature_build():
    calls = []

    def enrichment_runner(**kwargs):
        calls.append(("enrichment", kwargs))
        return {"results": ["ok"]}

    def feature_runner(**kwargs):
        calls.append(("features", kwargs))
        return {
            "lhb_event_features": "frame",
            "paths": {"lhb_event_features": "/tmp/lhb_event_features_daily_sample.csv"},
        }

    result = repair_lhb_source_and_features(
        "2026-06-29",
        output_dir="/tmp/out",
        enrichment_runner=enrichment_runner,
        feature_runner=feature_runner,
    )

    assert result.status == RepairStatus.SUCCESS
    assert [call[0] for call in calls] == ["enrichment", "features"]
    assert result.artifact_paths == ["/tmp/lhb_event_features_daily_sample.csv"]


def test_repair_strategy_publish_wraps_publisher_result():
    result = repair_strategy_publish(
        "2026-06-29",
        output_root="outputs",
        publisher=lambda **kwargs: {
            "review_rows": 14,
            "output_dir": "outputs/research/strategy_daily_eod/2026-06-29",
        },
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["review_rows"] == 14
    assert result.artifact_paths == ["outputs/research/strategy_daily_eod/2026-06-29"]


def test_repair_market_monitor_wraps_runner_result():
    result = repair_market_monitor(
        "2026-06-29",
        runner=lambda **kwargs: {"emotion_rows": 1, "index_rows": 5},
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["index_rows"] == 5


def test_repair_technical_features_passes_trade_date_to_runner():
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"stored_rows": 5187}

    result = repair_technical_features("2026-07-01", runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert captured["trade_date"] == "2026-07-01"
    assert captured["adjust_type"] == "hfq"
    assert result.metrics["stored_rows"] == 5187


def test_repair_score_topn_passes_manual_v1_to_runner():
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"score_rows": 5187}

    result = repair_score_topn("2026-07-01", output_dir="/tmp/out", runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert captured["trade_date"] == "2026-07-01"
    assert captured["score_version"] == "manual_v1"
    assert result.metrics["score_rows"] == 5187


def test_repair_watchlist_builds_default_and_diagnostics():
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {"members": 50}

    result = repair_watchlist("2026-07-01", runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert [call["watchlist_id"] for call in calls] == ["default", "diagnostics"]
    assert result.metrics == {"default_rows": 50, "diagnostics_rows": 50}


def test_repair_generated_reports_wraps_runner_output():
    result = repair_generated_reports(
        "2026-07-01",
        runner=lambda **kwargs: {"generated_reports": 2, "output_dir": "/tmp/reports"},
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["generated_reports"] == 2
    assert result.artifact_paths == ["/tmp/reports"]


def test_repair_review_evidence_snapshots_wraps_runner_output():
    result = repair_review_evidence_snapshots(
        "2026-07-01",
        runner=lambda **kwargs: {"snapshot_rows": 28, "output_dir": "/tmp/snapshots"},
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["snapshot_rows"] == 28
    assert result.artifact_paths == ["/tmp/snapshots"]
