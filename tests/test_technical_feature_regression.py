from stock_research.technical_feature_regression import (
    DEFAULT_FAST_REGRESSION_GATE,
    evaluate_fast_regression_gate,
    main,
    run_technical_feature_fast_regression,
)


def test_run_technical_feature_fast_regression_reports_zero_mismatches_for_synthetic_data():
    result = run_technical_feature_fast_regression(asset_count=3, bar_count=40)

    assert result["asset_count"] == 3
    assert result["bar_count"] == 40
    assert result["column_count"] > 0
    assert result["scenario_count"] >= 4
    assert result["max_abs_diff"] <= 1e-12
    assert result["nan_mismatch_count"] == 0
    assert result["gate"]["passed"] is True
    assert "adx14" in result["per_column"]
    assert "monotonic_rise" in result["scenarios"]
    assert "interior_missing_recovery" in result["scenarios"]


def test_evaluate_fast_regression_gate_enforces_explicit_thresholds():
    failed = evaluate_fast_regression_gate(
        max_abs_diff=1e-6,
        mean_abs_diff=0.0,
        nan_mismatch_count=0,
    )

    assert DEFAULT_FAST_REGRESSION_GATE["max_abs_diff"] == 1e-12
    assert failed["passed"] is False
    assert failed["thresholds"] == DEFAULT_FAST_REGRESSION_GATE


def test_technical_feature_regression_main_prints_json(capsys):
    main(["--asset-count", "2", "--bar-count", "30"])

    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["asset_count"] == 2
    assert "max_abs_diff" in payload
    assert "nan_mismatch_count" in payload
    assert "gate" in payload
