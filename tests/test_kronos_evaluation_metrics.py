import copy
import json
import math

import pytest


from stock_research.kronos_evaluation_metrics import (
    aggregate_metrics,
    build_baselines,
    compare_models,
    score_forecast,
    validate_comparison_seed,
)


def test_score_forecast_matches_the_plan_formulas_for_requested_horizons():
    scored = score_forecast(
        last_close=100.0,
        actual_closes=[102.0, 98.0, 105.0],
        p10=[98.0, 96.0, 100.0],
        p50=[101.0, 99.0, 104.0],
        p90=[104.0, 103.0, 110.0],
        horizons=(1, 3),
    )

    assert list(scored) == ["h1", "h3"]
    assert scored["h1"]["horizon"] == 1
    assert scored["h1"]["actual_return"] == pytest.approx(0.02)
    assert scored["h1"]["predicted_return"] == pytest.approx(0.01)
    assert scored["h1"]["absolute_return_error"] == pytest.approx(0.01)
    assert scored["h1"]["normalized_price_error"] == pytest.approx(0.01)
    assert scored["h1"]["direction_hit"] is True
    assert scored["h1"]["interval_coverage"] is True
    assert scored["h3"]["actual_return"] == pytest.approx(0.05)
    assert scored["h3"]["predicted_return"] == pytest.approx(0.04)


def test_score_forecast_supports_all_default_horizons_and_json_output():
    scored = score_forecast(
        last_close=100.0,
        actual_closes=[101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
        p10=[99.0] * 10,
        p50=[100.0 + index for index in range(10)],
        p90=[111.0] * 10,
    )

    assert tuple(scored) == ("h1", "h3", "h5", "h10")
    assert all(isinstance(value, bool) for value in scored["h5"].values() if isinstance(value, bool))
    serialized = json.dumps(scored, sort_keys=True)
    assert "NaN" not in serialized
    assert "Infinity" not in serialized


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"actual_closes": [1.0, 2.0], "p10": [0.0], "p50": [1.0, 2.0], "p90": [3.0, 4.0]},
            "equal length",
        ),
        (
            {"actual_closes": [1.0, 2.0], "p10": [0.0, 1.0], "p50": [1.0, 2.0], "p90": [3.0]},
            "equal length",
        ),
        (
            {"actual_closes": [1.0, 2.0], "p10": [0.0, 1.0], "p50": [1.0, 2.0], "p90": [3.0, 4.0], "horizons": (0,)},
            "horizon",
        ),
        (
            {"actual_closes": [1.0, 2.0], "p10": [0.0, 1.0], "p50": [1.0, 2.0], "p90": [3.0, 4.0], "horizons": (1, 3)},
            "horizon",
        ),
        (
            {"actual_closes": [1.0, 2.0], "p10": [0.0, 1.0], "p50": [1.0, 2.0], "p90": [3.0, 4.0], "horizons": (2, 1)},
            "increasing",
        ),
        (
            {"actual_closes": [1.0, 2.0], "p10": [0.0, 1.0], "p50": [1.0, 2.0], "p90": [3.0, 4.0], "horizons": (1, 1)},
            "increasing",
        ),
    ],
)
def test_score_forecast_rejects_length_and_horizon_contract_violations(kwargs, message):
    with pytest.raises(ValueError, match=message):
        score_forecast(last_close=100.0, **kwargs)


@pytest.mark.parametrize(
    ("last_close", "actual_closes", "p10", "p50", "p90"),
    [
        (0.0, [1.0], [0.0], [1.0], [2.0]),
        (float("nan"), [1.0], [0.0], [1.0], [2.0]),
        (float("inf"), [1.0], [0.0], [1.0], [2.0]),
        (100.0, [float("nan")], [0.0], [1.0], [2.0]),
        (100.0, [1.0], [float("inf")], [1.0], [2.0]),
        (100.0, [1.0], [0.0], [float("nan")], [2.0]),
        (100.0, [1.0], [0.0], [1.0], [float("inf")]),
    ],
)
def test_score_forecast_rejects_non_finite_or_invalid_last_close(
    last_close, actual_closes, p10, p50, p90
):
    with pytest.raises(ValueError, match="finite|positive"):
        score_forecast(last_close, actual_closes, p10, p50, p90, horizons=(1,))


def test_score_forecast_rejects_quantile_order_and_handles_pinball_direction_and_interval():
    with pytest.raises(ValueError, match="p10.*p50.*p90"):
        score_forecast(
            100.0,
            [102.0],
            [103.0],
            [101.0],
            [104.0],
            horizons=(1,),
        )

    scored = score_forecast(
        100.0,
        [100.0, 102.0, 98.0],
        [99.0, 100.0, 99.0],
        [100.0, 101.0, 99.0],
        [101.0, 103.0, 100.0],
        horizons=(1, 2, 3),
    )

    assert scored["h1"]["direction_hit"] is True
    assert scored["h1"]["interval_coverage"] is True
    assert scored["h1"]["pinball_loss_p10"] == pytest.approx(0.1)
    assert scored["h1"]["pinball_loss_p50"] == pytest.approx(0.0)
    assert scored["h1"]["pinball_loss_p90"] == pytest.approx(0.1)
    assert scored["h1"]["interval_width"] == pytest.approx(2.0)
    assert scored["h2"]["direction_hit"] is True
    assert scored["h2"]["interval_coverage"] is True
    assert scored["h3"]["direction_hit"] is True
    assert scored["h3"]["interval_coverage"] is False
    assert scored["h3"]["pinball_loss_p10"] == pytest.approx(0.9)
    assert scored["h3"]["pinball_loss_p50"] == pytest.approx(0.5)
    assert scored["h3"]["pinball_loss_p90"] == pytest.approx(0.2)


def test_score_forecast_groups_zero_with_non_negative_direction():
    scored = score_forecast(
        100.0,
        [100.0, 101.0, 100.0],
        [99.0, 99.0, 99.0],
        [101.0, 100.0, 99.0],
        [102.0, 102.0, 101.0],
        horizons=(1, 2, 3),
    )

    assert scored["h1"]["direction_hit"] is True
    assert scored["h2"]["direction_hit"] is True
    assert scored["h3"]["direction_hit"] is False


def test_build_baselines_is_deterministic_and_uses_compounded_mean_recent_return():
    closes = [100.0, 102.0, 101.0]
    result = build_baselines(closes, horizon=3, drift_window=2)

    recent_returns = (102.0 / 100.0 - 1.0, 101.0 / 102.0 - 1.0)
    drift = sum(recent_returns) / len(recent_returns)
    expected_drift = [101.0 * (1.0 + drift) ** step for step in (1, 2, 3)]
    assert result["persistence"] == [101.0, 101.0, 101.0]
    assert result["drift"] == pytest.approx(expected_drift)
    assert result == build_baselines(tuple(closes), horizon=3, drift_window=2)


def test_build_baselines_accepts_close_rows_and_rejects_invalid_inputs():
    result = build_baselines(
        [{"close": 100.0}, {"close": 102.0}, {"close": 101.0}],
        horizon=2,
        drift_window=20,
    )
    assert len(result["persistence"]) == len(result["drift"]) == 2

    invalid_cases = [
        ([], 1, 20),
        ([100.0], 1, 20),
        ([100.0, 0.0], 1, 20),
        ([100.0, float("nan")], 1, 20),
        ([100.0, 101.0], 0, 20),
        ([100.0, 101.0], 1, 0),
    ]
    for close_sequence, horizon, drift_window in invalid_cases:
        with pytest.raises(ValueError):
            build_baselines(close_sequence, horizon=horizon, drift_window=drift_window)


def _metric_row(
    asset_id,
    origin_date,
    horizon,
    *,
    status="success",
    absolute_return_error=0.1,
    normalized_price_error=0.2,
    direction_hit=True,
    interval_coverage=True,
    interval_width=0.5,
    pinball_loss_p10=0.01,
    pinball_loss_p50=0.02,
    pinball_loss_p90=0.03,
):
    return {
        "asset_id": asset_id,
        "origin_date": origin_date,
        "horizon": horizon,
        "status": status,
        "absolute_return_error": absolute_return_error,
        "normalized_price_error": normalized_price_error,
        "direction_hit": direction_hit,
        "interval_coverage": interval_coverage,
        "interval_width": interval_width,
        "pinball_loss_p10": pinball_loss_p10,
        "pinball_loss_p50": pinball_loss_p50,
        "pinball_loss_p90": pinball_loss_p90,
    }


def test_aggregate_metrics_keeps_status_counts_but_excludes_missing_and_failed_rows():
    success = _metric_row("A", "2025-01-02", 1)
    nested = {
        "asset_id": "A",
        "origin_date": "2025-01-03",
        "status": "succeeded",
        "metrics": _metric_row(
            "A",
            "2025-01-03",
            1,
            absolute_return_error=0.3,
            normalized_price_error=0.4,
            direction_hit=False,
            interval_coverage=False,
        ),
    }
    missing = _metric_row("A", "2025-01-04", 1, status="insufficient_truth")
    missing = {key: value for key, value in missing.items() if key in {"asset_id", "origin_date", "horizon", "status"}}
    failed = _metric_row("A", "2025-01-05", 1, status="model_error")
    failed = {key: value for key, value in failed.items() if key in {"asset_id", "origin_date", "horizon", "status"}}
    other_asset = _metric_row("B", "2025-01-02", 1, absolute_return_error=0.5)
    rows = [success, nested, missing, failed, other_asset]
    original_rows = copy.deepcopy(rows)

    grouped = aggregate_metrics(rows, group_by=("asset_id", "horizon"))
    group_a = next(row for row in grouped if row["asset_id"] == "A")
    group_b = next(row for row in grouped if row["asset_id"] == "B")

    assert group_a["row_count"] == 4
    assert group_a["metric_count"] == 2
    assert group_a["status_counts"] == {
        "insufficient_truth": 1,
        "model_error": 1,
        "success": 1,
        "succeeded": 1,
    }
    assert group_a["mean_absolute_return_error"] == pytest.approx(0.2)
    assert group_a["mean_normalized_price_error"] == pytest.approx(0.3)
    assert group_a["direction_hit_count"] == 1
    assert group_a["direction_hit_rate"] == pytest.approx(0.5)
    assert group_a["coverage_count"] == 1
    assert group_a["coverage_rate"] == pytest.approx(0.5)
    assert group_a["metric_denominators"]["absolute_return_error"] == 2
    assert group_a["metric_denominators"]["interval_coverage"] == 2
    assert group_b["row_count"] == 1
    assert group_b["metric_count"] == 1

    overall = aggregate_metrics(rows, group_by=())
    assert len(overall) == 1
    assert overall[0]["row_count"] == 5
    assert overall[0]["metric_count"] == 3
    assert overall[0]["coverage_count"] == 2
    assert rows == original_rows
    json.dumps(grouped, sort_keys=True)
    json.dumps(overall, sort_keys=True)


def test_aggregate_metrics_rejects_invalid_group_by_or_rows():
    with pytest.raises(ValueError, match="group_by"):
        aggregate_metrics([], group_by="")
    with pytest.raises(ValueError, match="mapping"):
        aggregate_metrics(["not a row"])


def test_aggregate_metrics_returns_an_explicit_empty_overall_summary():
    overall = aggregate_metrics([], group_by=())

    assert len(overall) == 1
    assert overall[0]["group_by"] == []
    assert overall[0]["row_count"] == 0
    assert overall[0]["total_count"] == 0
    assert overall[0]["success_count"] == 0
    assert overall[0]["failed_count"] == 0
    assert overall[0]["missing_count"] == 0
    assert overall[0]["excluded_count"] == 0
    assert overall[0]["metric_count"] == 0
    assert overall[0]["status_counts"] == {}
    assert all(
        denominator == 0
        for denominator in overall[0]["metric_denominators"].values()
    )
    assert all(mean is None for mean in overall[0]["means"].values())
    assert overall[0]["direction_hit_count"] == 0
    assert overall[0]["direction_hit_rate"] is None
    assert overall[0]["coverage_count"] == 0
    assert overall[0]["coverage_denominator"] == 0
    assert overall[0]["coverage_rate"] is None
    json.dumps(overall, sort_keys=True)


@pytest.mark.parametrize("bad_key", [["A"], ("A",)])
def test_aggregate_metrics_rejects_non_scalar_group_keys(bad_key):
    row = _metric_row(bad_key, "2025-01-02", 1)

    with pytest.raises(ValueError, match="scalar"):
        aggregate_metrics([row], group_by=("asset_id",))


def test_aggregate_metrics_keeps_mixed_scalar_group_keys_distinct():
    rows = [
        _metric_row(True, "2025-01-02", 1),
        _metric_row(1, "2025-01-02", 1),
        _metric_row(1.0, "2025-01-02", 1),
        _metric_row("1", "2025-01-02", 1),
    ]

    summaries = aggregate_metrics(rows, group_by=("asset_id",))

    assert len(summaries) == 4
    assert any(summary["asset_id"] is True for summary in summaries)
    assert any(
        summary["asset_id"] == 1 and type(summary["asset_id"]) is int
        for summary in summaries
    )
    assert any(
        summary["asset_id"] == 1.0 and type(summary["asset_id"]) is float
        for summary in summaries
    )
    assert any(
        summary["asset_id"] == "1" and type(summary["asset_id"]) is str
        for summary in summaries
    )
    json.dumps(summaries, sort_keys=True)


@pytest.mark.parametrize(
    "field",
    [
        "absolute_return_error",
        "normalized_price_error",
        "interval_width",
        "pinball_loss_p10",
        "pinball_loss_p50",
        "pinball_loss_p90",
    ],
)
def test_aggregate_metrics_rejects_negative_non_negative_metrics(field):
    row = _metric_row("A", "2025-01-02", 1)
    row[field] = -0.001

    with pytest.raises(ValueError, match=f"{field}.*non-negative"):
        aggregate_metrics([row])


def test_compare_models_bootstraps_complete_asset_origin_blocks_not_individual_rows():
    rows = [
        {"asset_id": "A", "origin_date": "2025-01-02", "horizon": 1, "small": 0.10, "base": 0.08},
        {"asset_id": "A", "origin_date": "2025-01-02", "horizon": 3, "small": 0.20, "base": 0.15},
        {"asset_id": "A", "origin_date": "2025-01-03", "horizon": 1, "small": 0.07, "base": 0.08},
        {"asset_id": "B", "origin_date": "2025-01-02", "horizon": 1, "small": 0.05, "base": 0.03},
        {"asset_id": "B", "origin_date": "2025-01-02", "horizon": 3, "small": 0.06, "base": 0.04},
        {"asset_id": "B", "origin_date": "2025-01-03", "horizon": 1, "small": 0.11, "base": 0.10},
        {"asset_id": "B", "origin_date": "2025-01-04", "horizon": 1, "small": 0.10, "base": 0.10, "status": "model_error"},
    ]

    first = compare_models(rows, left="small", right="base", seed=7)
    second = compare_models(rows, left="small", right="base", seed=7)

    assert first == second
    assert first["paired_count"] == 4
    assert first["paired_row_count"] == 6
    assert first["excluded_count"] == 1
    assert first["base_minus_small"] == pytest.approx(
        (-0.02 - 0.05 + 0.01 - 0.02 - 0.02 - 0.01) / 6
    )
    assert first["delta_mean"] == first["base_minus_small"]
    assert first["ci_low"] <= first["ci_high"]
    assert first["status"] == "ok"
    json.dumps(first, sort_keys=True)


def test_compare_models_empty_and_single_block_are_explicit():
    empty = compare_models([], seed=7)
    assert empty["status"] == "empty"
    assert empty["paired_count"] == 0
    assert empty["delta_mean"] is None
    assert empty["ci_low"] is None
    assert empty["ci_high"] is None

    single = compare_models(
        [
            {"asset_id": "A", "origin_date": "2025-01-02", "small": 0.10, "base": 0.08},
            {"asset_id": "A", "origin_date": "2025-01-02", "small": 0.20, "base": 0.15},
        ],
        seed=7,
    )
    assert single["status"] == "single_block"
    assert single["paired_count"] == 1
    assert single["delta_mean"] == pytest.approx((-0.02 - 0.05) / 2)
    assert single["ci_low"] == single["ci_high"] == single["delta_mean"]


def test_compare_models_weights_all_valid_rows_within_a_block():
    rows = [
        {
            "asset_id": "A",
            "origin_date": "2025-01-02",
            "horizon": 1,
            "small": 0.0,
            "base": 0.0,
        }
        for _ in range(100)
    ]
    rows.append(
        {
            "asset_id": "A",
            "origin_date": "2025-01-02",
            "horizon": 3,
            "small": 0.0,
            "base": 100.0,
        }
    )

    comparison = compare_models(rows, seed=7)

    assert comparison["paired_count"] == 1
    assert comparison["paired_row_count"] == 101
    assert comparison["paired_count_unit"] == "complete_asset_id|origin_date_blocks"
    assert comparison["delta_orientation"] == "base_minus_small"
    assert comparison["base_minus_small"] == pytest.approx(100.0 / 101.0)
    assert comparison["ci_low"] == comparison["ci_high"] == comparison["delta_mean"]


def test_compare_models_keeps_mixed_scalar_block_keys_distinct():
    rows = [
        {"asset_id": True, "origin_date": "2025-01-02", "small": 0.0, "base": 0.0},
        {"asset_id": 1, "origin_date": "2025-01-02", "small": 0.0, "base": 100.0},
        {"asset_id": 1.0, "origin_date": "2025-01-02", "small": 0.0, "base": 200.0},
    ]

    comparison = compare_models(rows, seed=7)

    assert comparison["paired_count"] == 3
    assert comparison["paired_row_count"] == 3
    assert comparison["base_minus_small"] == pytest.approx(100.0)
    json.dumps(comparison, sort_keys=True)


@pytest.mark.parametrize("bad_seed", [None, True, 1.5])
def test_compare_models_requires_an_integer_seed(bad_seed):
    with pytest.raises(ValueError, match="seed"):
        compare_models([], seed=bad_seed)


@pytest.mark.parametrize("bad_key", [["A"], ("A",)])
def test_compare_models_rejects_non_scalar_block_keys(bad_key):
    rows = [
        {
            "asset_id": bad_key,
            "origin_date": "2025-01-02",
            "small": 0.1,
            "base": 0.08,
        }
    ]

    with pytest.raises(ValueError, match="scalar"):
        compare_models(rows, seed=7)


def test_compare_models_long_rows_pair_by_horizon_independent_of_input_order():
    rows = [
        {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "horizon": 1, "value": 0.10},
        {"asset_id": "A", "origin_date": "2025-01-02", "model": "base", "horizon": 1, "value": 0.08},
        {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "horizon": 3, "value": 0.20},
        {"asset_id": "A", "origin_date": "2025-01-02", "model": "base", "horizon": 3, "value": 0.15},
    ]
    reordered = [rows[3], rows[0], rows[2], rows[1]]

    first = compare_models(rows, seed=7)
    second = compare_models(reordered, seed=7)

    assert first == second
    assert first["base_minus_small"] == pytest.approx((-0.02 - 0.05) / 2)


def test_compare_models_excludes_incomplete_long_blocks_with_failed_or_missing_counterparts():
    rows = [
        {"asset_id": "failed", "origin_date": "2025-01-02", "model": "small", "horizon": 1, "value": 0.10},
        {"asset_id": "failed", "origin_date": "2025-01-02", "model": "base", "horizon": 1, "status": "model_error"},
        {"asset_id": "missing", "origin_date": "2025-01-02", "model": "small", "horizon": 1, "value": 0.20},
        {"asset_id": "complete", "origin_date": "2025-01-02", "model": "small", "horizon": 1, "value": 0.20},
        {"asset_id": "complete", "origin_date": "2025-01-02", "model": "base", "horizon": 1, "value": 0.15},
    ]

    comparison = compare_models(rows, seed=7)

    assert comparison["status"] == "single_block"
    assert comparison["paired_count"] == 1
    assert comparison["paired_row_count"] == 1
    assert comparison["excluded_count"] == 3
    assert comparison["base_minus_small"] == pytest.approx(-0.05)


def test_compare_models_reports_no_complete_pairs_for_only_incomplete_long_blocks():
    comparison = compare_models(
        [
            {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "value": 0.10},
            {"asset_id": "A", "origin_date": "2025-01-02", "model": "base", "status": "insufficient_truth"},
        ],
        seed=7,
    )

    assert comparison["status"] == "no_complete_pairs"
    assert comparison["paired_count"] == 0
    assert comparison["paired_row_count"] == 0
    assert comparison["delta_mean"] is None
    assert comparison["ci_low"] is None
    assert comparison["ci_high"] is None


def test_compare_models_rejects_ambiguous_or_unequal_long_pair_sequences():
    with pytest.raises(ValueError, match="ambiguous.*horizon"):
        compare_models(
            [
                {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "value": 0.10},
                {"asset_id": "A", "origin_date": "2025-01-02", "model": "base", "value": 0.08},
                {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "value": 0.20},
                {"asset_id": "A", "origin_date": "2025-01-02", "model": "base", "value": 0.15},
            ],
            seed=7,
        )

    with pytest.raises(ValueError, match="equal cardinality"):
        compare_models(
            [
                {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "horizon": 1, "value": 0.10},
                {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "horizon": 3, "value": 0.20},
                {"asset_id": "A", "origin_date": "2025-01-02", "model": "base", "horizon": 1, "value": 0.08},
            ],
            seed=7,
        )


def test_compare_models_rejects_sequence_valued_wide_model_fields():
    with pytest.raises(ValueError, match="sequence-valued"):
        compare_models(
            [
                {
                    "asset_id": "A",
                    "origin_date": "2025-01-02",
                    "small": [0.10, 0.20],
                    "base": [0.08, 0.15],
                }
            ],
            seed=7,
        )


def test_compare_models_seeded_multi_block_bootstrap_is_exact_and_row_weighted():
    rows = [
        {"asset_id": "A", "origin_date": "2025-01-02", "horizon": 1, "small": 0.0, "base": 0.0},
        {"asset_id": "B", "origin_date": "2025-01-02", "horizon": 1, "small": 0.0, "base": 10.0},
        {"asset_id": "B", "origin_date": "2025-01-02", "horizon": 3, "small": 0.0, "base": 10.0},
        {"asset_id": "B", "origin_date": "2025-01-02", "horizon": 5, "small": 0.0, "base": 10.0},
    ]

    comparison = compare_models(rows, seed=7, bootstrap_samples=1000)

    assert comparison["paired_count"] == 2
    assert comparison["paired_row_count"] == 4
    assert comparison["base_minus_small"] == pytest.approx(7.5)
    assert comparison["ci_low"] == pytest.approx(0.0)
    assert comparison["ci_high"] == pytest.approx(10.0)
    assert comparison == compare_models(rows, seed=7, bootstrap_samples=1000)


def test_validate_comparison_seed_is_exported_and_fail_closed():
    assert validate_comparison_seed(7) == 7
    for bad_seed in (None, True, 1.5):
        with pytest.raises(ValueError, match="seed"):
            validate_comparison_seed(bad_seed)


def test_compare_models_accepts_long_model_rows():
    comparison = compare_models(
        [
            {"asset_id": "A", "origin_date": "2025-01-02", "model": "small", "value": 0.10},
            {"asset_id": "A", "origin_date": "2025-01-02", "model": "base", "value": 0.08},
        ],
        bootstrap_samples=10,
    )

    assert comparison["status"] == "single_block"
    assert comparison["paired_count"] == 1
    assert comparison["paired_row_count"] == 1
    assert comparison["base_minus_small"] == pytest.approx(-0.02)


def test_score_forecast_rejects_finite_inputs_that_produce_non_finite_metrics():
    with pytest.raises(ValueError, match="non-finite"):
        score_forecast(
            1e-308,
            [1e308],
            [1e308],
            [1e308],
            [1e308],
            horizons=(1,),
        )


def test_outputs_are_finite_json_compatible_and_input_rows_are_not_mutated():
    rows = [
        _metric_row("A", "2025-01-02", 1),
        {"asset_id": "A", "origin_date": "2025-01-02", "small": 1.0, "base": 1.1},
    ]
    original = copy.deepcopy(rows)
    outputs = [
        score_forecast(100.0, [101.0], [99.0], [100.0], [102.0], horizons=(1,)),
        build_baselines([100.0, 101.0], horizon=2),
        aggregate_metrics(rows[:1]),
        compare_models(rows[1:], seed=3),
    ]
    for output in outputs:
        encoded = json.dumps(output, allow_nan=False, sort_keys=True)
        assert "NaN" not in encoded
        assert "Infinity" not in encoded
        assert all(not isinstance(value, (set, tuple)) for value in _walk(output))
    assert rows == original


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
