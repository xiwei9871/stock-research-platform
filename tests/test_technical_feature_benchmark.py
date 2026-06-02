import json

from stock_research.technical_feature_benchmark import (
    generate_synthetic_technical_feature_bars,
    main,
    run_technical_feature_compare_benchmark,
    run_technical_feature_compute_benchmark,
    run_technical_feature_store_compare_benchmark,
)


def test_generate_synthetic_technical_feature_bars_creates_expected_shape():
    frame = generate_synthetic_technical_feature_bars(asset_count=3, bar_count=20)

    assert list(frame.columns) == [
        "trade_date",
        "asset_id",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "turnover_rate",
    ]
    assert len(frame) == 60
    assert frame["asset_id"].nunique() == 3


def test_run_technical_feature_compute_benchmark_returns_json_ready_metrics():
    result = run_technical_feature_compute_benchmark(asset_count=4, bar_count=30)

    assert result["asset_count"] == 4
    assert result["bar_count"] == 30
    assert result["indicator_columns"] > 0
    assert result["rows_written"] == 4
    assert result["total_seconds"] >= 0.0
    assert result["per_asset_seconds"] >= 0.0
    assert result["rows_per_second"] >= 0.0
    assert result["output_mode"] == "latest_per_asset"
    assert result["engine"] == "legacy"


def test_run_technical_feature_compare_benchmark_reports_both_engines():
    result = run_technical_feature_compare_benchmark(asset_count=3, bar_count=30)

    assert result["asset_count"] == 3
    assert result["bar_count"] == 30
    assert result["legacy_total_seconds"] >= 0.0
    assert result["fast_total_seconds"] >= 0.0
    assert "speedup_ratio" in result


def test_run_technical_feature_store_compare_benchmark_reports_both_strategies():
    result = run_technical_feature_store_compare_benchmark(asset_count=3, bar_count=30)

    assert result["asset_count"] == 3
    assert result["bar_count"] == 30
    assert result["legacy_total_seconds"] >= 0.0
    assert result["batch_frame_total_seconds"] >= 0.0
    assert result["latest_only_total_seconds"] >= 0.0
    assert result["legacy_rows_written"] == 3
    assert result["batch_frame_rows_written"] == 3
    assert result["latest_only_rows_written"] == 3
    assert "speedup_ratio" in result


def test_technical_feature_benchmark_main_prints_json(capsys):
    main(["--asset-count", "2", "--bar-count", "20", "--repeat", "1"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["asset_count"] == 2
    assert payload["bar_count"] == 20
    assert "total_seconds" in payload
    assert "rows_per_second" in payload
