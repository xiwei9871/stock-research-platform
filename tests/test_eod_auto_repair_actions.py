import pytest

from stock_research.eod_auto_repair_actions import (
    repair_generated_reports,
    repair_lhb_source_and_features,
    repair_market_monitor,
    repair_minute5_bars,
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


def test_repair_minute5_bars_passes_single_worker_to_runner():
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"raw_success": 5209, "qfq_success": 5209}

    result = repair_minute5_bars("2026-06-29", workers=1, runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert captured["workers"] == 1
    assert captured["start_date"] == "2026-06-29"
    assert captured["end_date"] == "2026-06-29"


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
