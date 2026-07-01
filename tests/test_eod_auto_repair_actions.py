import pytest

from stock_research.eod_auto_repair_actions import (
    repair_lhb_source_and_features,
    repair_market_monitor,
    repair_minute5_bars,
    repair_strategy_publish,
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
