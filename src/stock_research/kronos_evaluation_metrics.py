"""Deterministic metrics for the Kronos rolling evaluation.

The functions in this module are deliberately independent of the Kronos HTTP
client.  They accept ordinary Python sequences and mappings, validate them
without padding or clipping, and return only JSON-compatible values.

``score_forecast`` returns one mapping per requested horizon.  The key is
``h1``, ``h3``, and so on; each value contains the realized/predicted prices,
returns, errors, interval statistics, and pinball losses.

``build_baselines`` uses two simple forecasts.  Persistence repeats the last
historical close.  The drift forecast computes the arithmetic mean of the
most recent ``drift_window`` one-period simple returns and compounds that mean
return from the last close for each future step.

``aggregate_metrics`` accepts flat per-horizon rows or rows containing a
``metrics`` mapping.  It returns a deterministically ordered list of group
summaries.  ``group_by=()`` produces one overall summary; callers can request
per-asset, per-horizon, or combined summaries by passing the corresponding
field names.  Even with no rows, ``group_by=()`` returns one explicit
zero-count overall summary.

``compare_models`` treats ``asset_id|origin_date`` as the independent unit.
Complete blocks are resampled, while each replicate averages all valid paired
rows from the sampled blocks, so overlapping daily windows are not treated as
independent observations and uneven row counts retain their weight.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from numbers import Integral
from typing import Any


__all__ = (
    "aggregate_metrics",
    "build_baselines",
    "compare_models",
    "score_forecast",
    "validate_comparison_seed",
)


_SUCCESS_STATUSES = frozenset(
    {
        "complete",
        "completed",
        "ok",
        "partial",
        "ready",
        "success",
        "succeeded",
    }
)
_FAILED_STATUSES = frozenset(
    {
        "error",
        "failed",
        "model_error",
        "timeout",
        "unavailable",
    }
)
_MISSING_STATUSES = frozenset(
    {
        "",
        "insufficient_input",
        "insufficient_truth",
        "invalid_input",
        "missing",
        "not_available",
    }
)
_NUMERIC_METRIC_FIELDS = (
    "actual_return",
    "predicted_return",
    "absolute_return_error",
    "normalized_price_error",
    "interval_width",
    "pinball_loss_p10",
    "pinball_loss_p50",
    "pinball_loss_p90",
)
_BOOLEAN_METRIC_FIELDS = ("direction_hit", "interval_coverage")
_NON_NEGATIVE_METRIC_FIELDS = frozenset(
    {
        "absolute_return_error",
        "normalized_price_error",
        "interval_width",
        "pinball_loss_p10",
        "pinball_loss_p50",
        "pinball_loss_p90",
    }
)
_HORIZON_KEY_RE = re.compile(r"^h([1-9][0-9]*)$")
_LONG_VALUE_FIELDS = ("value", "metric_value", "score", "metric")


def validate_comparison_seed(seed: Any) -> int:
    """Validate the deterministic seed required by research comparisons.

    The rolling-evaluation runner should call this before comparing model
    results and reject ``config.seed=None``.  This research-only contract is
    intentionally stricter than the HTTP client, which may pass ``seed=None``
    to the service-level prediction endpoint.
    """

    if isinstance(seed, bool) or not isinstance(seed, Integral):
        raise ValueError("seed must be an integer")
    return int(seed)


def score_forecast(
    last_close: Any,
    actual_closes: Iterable[Any],
    p10: Iterable[Any],
    p50: Iterable[Any],
    p90: Iterable[Any],
    horizons: Iterable[int] = (1, 3, 5, 10),
) -> dict[str, dict[str, Any]]:
    """Score point and interval forecasts at each requested horizon.

    Direction uses the approved non-negative grouping rule exactly:
    ``(predicted_return >= 0) == (actual_return >= 0)``.  A zero return is
    therefore grouped with positive/non-negative returns.
    """

    normalized_last_close = _finite_float(last_close, "last_close")
    if normalized_last_close <= 0:
        raise ValueError("last_close must be positive and finite")

    actual_values = _finite_float_sequence(actual_closes, "actual_closes")
    p10_values = _finite_float_sequence(p10, "p10")
    p50_values = _finite_float_sequence(p50, "p50")
    p90_values = _finite_float_sequence(p90, "p90")
    lengths = {
        len(actual_values),
        len(p10_values),
        len(p50_values),
        len(p90_values),
    }
    if len(lengths) != 1:
        raise ValueError("actual_closes, p10, p50, and p90 must have equal length")
    if not actual_values:
        raise ValueError("forecast sequences must not be empty")

    for index, (lower, median, upper) in enumerate(
        zip(p10_values, p50_values, p90_values)
    ):
        if not lower <= median <= upper:
            raise ValueError(
                "quantiles must satisfy p10 <= p50 <= p90 at every position "
                f"(index {index})"
            )

    normalized_horizons = _validate_horizons(horizons, len(actual_values))
    scored: dict[str, dict[str, Any]] = {}
    for horizon in normalized_horizons:
        index = horizon - 1
        actual_close = actual_values[index]
        predicted_p10 = p10_values[index]
        predicted_p50 = p50_values[index]
        predicted_p90 = p90_values[index]
        actual_return = _finite_result(
            actual_close / normalized_last_close - 1.0,
            "actual_return",
        )
        predicted_return = _finite_result(
            predicted_p50 / normalized_last_close - 1.0,
            "predicted_return",
        )
        absolute_return_error = _finite_result(
            abs(predicted_return - actual_return),
            "absolute_return_error",
        )
        normalized_price_error = _finite_result(
            abs(predicted_p50 - actual_close) / abs(normalized_last_close),
            "normalized_price_error",
        )
        interval_width = _finite_result(
            predicted_p90 - predicted_p10,
            "interval_width",
        )
        pinball_losses = {
            "p10": _finite_result(
                _pinball_loss(actual_close, predicted_p10, 0.10),
                "pinball_loss_p10",
            ),
            "p50": _finite_result(
                _pinball_loss(actual_close, predicted_p50, 0.50),
                "pinball_loss_p50",
            ),
            "p90": _finite_result(
                _pinball_loss(actual_close, predicted_p90, 0.90),
                "pinball_loss_p90",
            ),
        }
        scored[f"h{horizon}"] = {
            "horizon": horizon,
            "last_close": normalized_last_close,
            "actual_close": actual_close,
            "p10": predicted_p10,
            "p50": predicted_p50,
            "p90": predicted_p90,
            "predicted_p10": predicted_p10,
            "predicted_p50": predicted_p50,
            "predicted_p90": predicted_p90,
            "actual_return": actual_return,
            "predicted_return": predicted_return,
            "absolute_return_error": absolute_return_error,
            "normalized_price_error": normalized_price_error,
            "direction_hit": (predicted_return >= 0.0)
            == (actual_return >= 0.0),
            "interval_coverage": predicted_p10
            <= actual_close
            <= predicted_p90,
            "interval_width": interval_width,
            "pinball_loss_p10": pinball_losses["p10"],
            "pinball_loss_p50": pinball_losses["p50"],
            "pinball_loss_p90": pinball_losses["p90"],
            "pinball_loss": pinball_losses,
        }
    return scored


def build_baselines(
    close_sequence: Iterable[Any] | None = None,
    horizon: int | None = None,
    drift_window: int = 20,
    *,
    actual: Iterable[Any] | None = None,
    history: Iterable[Any] | None = None,
) -> dict[str, list[float]]:
    """Build persistence and deterministic recent-drift forecasts.

    ``close_sequence`` may be a sequence of close numbers or a sequence of
    mappings containing a finite, positive ``close`` field.  ``actual`` and
    ``history`` are keyword aliases for callers that use those names; exactly
    one input sequence is accepted.  At least two historical closes are
    required because the drift baseline needs one-period returns.
    """

    supplied = [
        value
        for value in (close_sequence, actual, history)
        if value is not None
    ]
    if len(supplied) != 1:
        raise ValueError("provide exactly one close sequence, actual, or history")
    if horizon is None:
        raise ValueError("horizon must be a positive integer")
    normalized_horizon = _positive_int(horizon, "horizon")
    normalized_drift_window = _positive_int(drift_window, "drift_window")

    sequence = supplied[0]
    if isinstance(sequence, (str, bytes, Mapping)):
        raise ValueError("close sequence must be an iterable of numbers or rows")
    try:
        raw_values = tuple(sequence)
    except TypeError as exc:
        raise ValueError("close sequence must be an iterable") from exc
    if len(raw_values) < 2:
        raise ValueError("close sequence must contain at least two closes")

    closes: list[float] = []
    for index, value in enumerate(raw_values):
        if isinstance(value, Mapping):
            if "close" not in value:
                raise ValueError(f"close sequence row {index} is missing close")
            value = value["close"]
        normalized_value = _finite_float(value, f"close_sequence[{index}]")
        if normalized_value <= 0:
            raise ValueError(f"close_sequence[{index}] must be positive and finite")
        closes.append(normalized_value)

    recent_return_start = max(1, len(closes) - normalized_drift_window)
    recent_returns = [
        _finite_result(
            closes[index] / closes[index - 1] - 1.0,
            f"recent_return[{index}]",
        )
        for index in range(recent_return_start, len(closes))
    ]
    mean_recent_return = _finite_result(
        sum(recent_returns) / len(recent_returns),
        "mean_recent_return",
    )
    last_close = closes[-1]
    persistence = [last_close for _ in range(normalized_horizon)]
    drift: list[float] = []
    forecast = last_close
    for _ in range(normalized_horizon):
        forecast *= 1.0 + mean_recent_return
        if not math.isfinite(forecast):
            raise ValueError("drift baseline produced a non-finite forecast")
        drift.append(forecast)
    return {"persistence": persistence, "drift": drift}


def aggregate_metrics(
    rows: Iterable[Mapping[str, Any]],
    group_by: str | Iterable[str] | None = ("asset_id", "horizon"),
) -> list[dict[str, Any]]:
    """Aggregate successful metric rows while retaining status coverage.

    Successful rows contribute independently to each metric denominator.  A
    missing or failed row contributes to ``row_count`` and ``status_counts``
    but not to metric means.  ``coverage_count`` and ``coverage_rate`` use
    only rows with a valid ``interval_coverage`` value; their denominator is
    exposed as ``metric_denominators['interval_coverage']``.
    """

    normalized_group_by = _normalize_group_by(group_by)
    normalized_rows = _flatten_metric_rows(rows)
    buckets: dict[tuple[tuple[str, Any], ...], list[dict[str, Any]]] = defaultdict(list)
    group_values_by_key: dict[tuple[tuple[str, Any], ...], tuple[Any, ...]] = {}
    for row in normalized_rows:
        group_values = tuple(
            _group_value(row.get(field)) for field in normalized_group_by
        )
        key = tuple(_typed_scalar_key(value) for value in group_values)
        buckets[key].append(row)
        group_values_by_key.setdefault(key, group_values)
    if not buckets and not normalized_group_by:
        buckets[()] = []
        group_values_by_key[()] = ()

    summaries: list[dict[str, Any]] = []
    for key in sorted(buckets, key=_stable_sort_key):
        group_rows = buckets[key]
        status_counts: Counter[str] = Counter()
        metric_values: dict[str, list[float]] = {
            field: []
            for field in _NUMERIC_METRIC_FIELDS + _BOOLEAN_METRIC_FIELDS
        }
        success_count = 0
        failed_count = 0
        missing_count = 0
        metric_count = 0

        for row in group_rows:
            status = _row_status(row)
            status_counts[status] += 1
            if status in _SUCCESS_STATUSES:
                success_count += 1
            elif status in _FAILED_STATUSES:
                failed_count += 1
            else:
                missing_count += 1

            if status not in _SUCCESS_STATUSES:
                continue
            row_has_metric = False
            for field in _NUMERIC_METRIC_FIELDS:
                value = _optional_metric_float(row, field)
                if value is not None:
                    metric_values[field].append(value)
                    row_has_metric = True
            for field in _BOOLEAN_METRIC_FIELDS:
                value = _optional_metric_bool(row, field)
                if value is not None:
                    metric_values[field].append(float(value))
                    row_has_metric = True
            if row_has_metric:
                metric_count += 1

        denominators = {
            field: len(values) for field, values in metric_values.items()
        }
        means = {
            field: _mean_or_none(values) for field, values in metric_values.items()
        }
        direction_hit_count = sum(
            int(value) for value in metric_values["direction_hit"]
        )
        coverage_count = sum(
            int(value) for value in metric_values["interval_coverage"]
        )
        direction_denominator = denominators["direction_hit"]
        coverage_denominator = denominators["interval_coverage"]
        summary: dict[str, Any] = {
            field: value
            for field, value in zip(
                normalized_group_by, group_values_by_key[key]
            )
        }
        summary.update(
            {
                "group_by": list(normalized_group_by),
                "row_count": len(group_rows),
                "total_count": len(group_rows),
                "success_count": success_count,
                "failed_count": failed_count,
                "missing_count": missing_count,
                "excluded_count": len(group_rows) - metric_count,
                "metric_count": metric_count,
                "status_counts": {
                    status: status_counts[status]
                    for status in sorted(status_counts)
                },
                "metric_denominators": denominators,
                "means": means,
                "direction_hit_count": direction_hit_count,
                "direction_hit_rate": _rate_or_none(
                    direction_hit_count, direction_denominator
                ),
                "coverage_count": coverage_count,
                "coverage_denominator": coverage_denominator,
                "coverage_rate": _rate_or_none(
                    coverage_count, coverage_denominator
                ),
            }
        )
        for field, mean in means.items():
            summary[f"mean_{field}"] = mean
        summaries.append(summary)
    return summaries


def compare_models(
    rows: Iterable[Mapping[str, Any]],
    left: str = "small",
    right: str = "base",
    seed: int = 7,
    *,
    bootstrap_samples: int = 10_000,
) -> dict[str, Any]:
    """Compare two models using complete asset/origin blocks.

    Wide rows should contain ``left`` and ``right`` numeric values.  Long rows
    may instead contain ``model`` and one of ``value``, ``metric_value``,
    ``score``, or ``metric``.  Within each ``asset_id|origin_date`` block,
    ``paired_count`` is the number of complete ``asset_id|origin_date``
    blocks, while ``paired_row_count`` is the number of valid paired rows in
    those blocks.  ``delta_mean`` and every bootstrap replicate are weighted
    over the valid paired rows, including all requested horizons; horizon
    subgroup means are never averaged with equal weight.  The confidence
    interval is a deterministic empirical 95% block bootstrap using
    ``random.Random(seed)`` and linearly interpolated 2.5%/97.5% quantiles.
    Long-form blocks with failed or missing counterpart rows are excluded
    entirely; cardinality and ambiguity errors apply only to complete valid
    long-form blocks.  A non-empty input with no complete pairs reports
    ``status='no_complete_pairs'``.
    """

    left_name = _model_name(left, "left")
    right_name = _model_name(right, "right")
    if left_name == right_name:
        raise ValueError("left and right models must be different")
    normalized_seed = validate_comparison_seed(seed)
    normalized_bootstrap_samples = _positive_int(
        bootstrap_samples, "bootstrap_samples"
    )

    output_base = {
        "left_model": left_name,
        "right_model": right_name,
        "seed": normalized_seed,
        "bootstrap_samples": normalized_bootstrap_samples,
        "confidence_level": 0.95,
        "paired_count_unit": "complete_asset_id|origin_date_blocks",
        "delta_orientation": f"{right_name}_minus_{left_name}",
        "status_counts": {},
        "paired_count": 0,
        "complete_block_count": 0,
        "paired_row_count": 0,
        "excluded_count": 0,
        "delta_mean": None,
        "ci_low": None,
        "ci_high": None,
        "ci_method": "none",
        "status": "empty",
    }
    delta_key = f"{right_name}_minus_{left_name}"
    output_base[delta_key] = None

    materialized_rows = _materialize_rows(rows, "rows")
    if not materialized_rows:
        return output_base

    status_counts: Counter[str] = Counter()
    block_deltas: dict[tuple[tuple[str, Any], tuple[str, Any]], list[float]] = defaultdict(list)
    long_subgroups: dict[
        tuple[tuple[tuple[str, Any], tuple[str, Any]], tuple[str, Any]],
        dict[str, list[float]],
    ] = defaultdict(lambda: defaultdict(list))
    long_block_models: dict[
        tuple[tuple[str, Any], tuple[str, Any]], set[str]
    ] = defaultdict(set)
    long_block_incomplete: set[tuple[tuple[str, Any], tuple[str, Any]]] = set()
    long_block_valid_row_counts: dict[
        tuple[tuple[str, Any], tuple[str, Any]], int
    ] = defaultdict(int)
    excluded_count = 0
    paired_row_count = 0

    for index, row in enumerate(materialized_rows):
        if "asset_id" not in row or "origin_date" not in row:
            raise ValueError(
                f"rows[{index}] must contain asset_id and origin_date"
            )
        block_values = (
            _group_value(row["asset_id"]),
            _group_value(row["origin_date"]),
        )
        block = tuple(_typed_scalar_key(value) for value in block_values)
        status = _comparison_row_status(row, left_name, right_name)
        status_counts[status] += 1
        subkey = _typed_scalar_key(_group_value(row.get("horizon")))

        if _is_long_comparison_row(row, left_name, right_name):
            model = _normalized_model_value(row.get("model"), row_index=index)
            value = _optional_numeric_value(row, _LONG_VALUE_FIELDS)
            if model not in {left_name, right_name}:
                excluded_count += 1
                continue
            long_block_models[block].add(model)
            if status not in _SUCCESS_STATUSES or value is None:
                long_block_incomplete.add(block)
                excluded_count += 1
                continue
            long_subgroups[(block, subkey)][model].append(value)
            long_block_valid_row_counts[block] += 1
            continue

        left_value = _optional_comparison_value(row, left_name)
        right_value = _optional_comparison_value(row, right_name)
        if (
            status not in _SUCCESS_STATUSES
            or left_value is None
            or right_value is None
        ):
            excluded_count += 1
            continue
        block_deltas[block].append(
            _finite_result(right_value - left_value, "model_delta")
        )
        paired_row_count += 1

    for block in sorted(long_block_models, key=_stable_sort_key):
        if block in long_block_incomplete:
            excluded_count += long_block_valid_row_counts[block]
            continue
        if long_block_models[block] != {left_name, right_name}:
            excluded_count += long_block_valid_row_counts[block]
            continue
        block_subgroups = [
            (subkey, values_by_model)
            for (sub_block, subkey), values_by_model in long_subgroups.items()
            if sub_block == block
        ]
        for _subkey, values_by_model in block_subgroups:
            left_values = values_by_model.get(left_name, [])
            right_values = values_by_model.get(right_name, [])
            if len(left_values) != len(right_values):
                raise ValueError(
                    "long-form model rows must have equal cardinality for each horizon"
                )
            if len(left_values) > 1:
                raise ValueError(
                    "ambiguous long-form pairing; provide one unique horizon per model row"
                )
            for pair_index in range(len(left_values)):
                block_deltas[block].append(
                    _finite_result(
                        right_values[pair_index] - left_values[pair_index],
                        "model_delta",
                    )
                )
            paired_row_count += len(left_values)

    complete_block_rows = [
        deltas
        for _block, deltas in sorted(block_deltas.items(), key=_stable_sort_key)
        if deltas
    ]
    output_base["status_counts"] = {
        status: status_counts[status] for status in sorted(status_counts)
    }
    output_base["excluded_count"] = excluded_count
    output_base["paired_row_count"] = paired_row_count
    output_base["paired_count"] = len(complete_block_rows)
    output_base["complete_block_count"] = len(complete_block_rows)
    if not complete_block_rows:
        output_base["status"] = "no_complete_pairs"
        return output_base

    all_paired_deltas = [
        delta for block_rows in complete_block_rows for delta in block_rows
    ]
    delta_mean = _mean(all_paired_deltas)
    output_base["delta_mean"] = delta_mean
    output_base[delta_key] = delta_mean
    if len(complete_block_rows) == 1:
        output_base["status"] = "single_block"
        output_base["ci_low"] = delta_mean
        output_base["ci_high"] = delta_mean
        output_base["ci_method"] = "degenerate_single_block"
        return output_base

    rng = random.Random(normalized_seed)
    bootstrap_means: list[float] = []
    block_count = len(complete_block_rows)
    for _ in range(normalized_bootstrap_samples):
        sample_sum = 0.0
        sample_row_count = 0
        for _ in range(block_count):
            sampled_rows = complete_block_rows[rng.randrange(block_count)]
            sample_sum += sum(sampled_rows)
            sample_row_count += len(sampled_rows)
        bootstrap_means.append(
            _finite_result(
                sample_sum / sample_row_count,
                "bootstrap_delta_mean",
            )
        )
    bootstrap_means.sort()
    output_base["status"] = "ok"
    output_base["ci_low"] = _empirical_quantile(bootstrap_means, 0.025)
    output_base["ci_high"] = _empirical_quantile(bootstrap_means, 0.975)
    output_base["ci_method"] = "block_bootstrap"
    return output_base


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, (bool, str, bytes)) or value is None:
        raise ValueError(f"{field_name} must be a finite numeric value")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite numeric value") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be a finite numeric value")
    return normalized


def _finite_result(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} produced a non-finite result")
    return value


def _finite_float_sequence(values: Iterable[Any], field_name: str) -> list[float]:
    if isinstance(values, (str, bytes, Mapping)):
        raise ValueError(f"{field_name} must be an iterable of finite numbers")
    try:
        materialized = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an iterable of finite numbers") from exc
    return [
        _finite_float(value, f"{field_name}[{index}]")
        for index, value in enumerate(materialized)
    ]


def _validate_horizons(horizons: Iterable[int], sequence_length: int) -> tuple[int, ...]:
    if isinstance(horizons, (str, bytes, Mapping)):
        raise ValueError("horizons must be a strictly increasing iterable of integers")
    try:
        raw_horizons = tuple(horizons)
    except TypeError as exc:
        raise ValueError(
            "horizons must be a strictly increasing iterable of integers"
        ) from exc
    if not raw_horizons:
        raise ValueError("horizons must not be empty")
    normalized: list[int] = []
    for horizon in raw_horizons:
        if isinstance(horizon, bool) or not isinstance(horizon, Integral):
            raise ValueError("horizons must contain integers")
        normalized_horizon = int(horizon)
        if normalized_horizon <= 0 or normalized_horizon > sequence_length:
            raise ValueError(
                f"horizon {normalized_horizon} is outside the available bounds"
            )
        normalized.append(normalized_horizon)
    if normalized != sorted(normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("horizons must be strictly increasing")
    return tuple(normalized)


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return int(value)


def _pinball_loss(actual: float, forecast: float, quantile: float) -> float:
    error = actual - forecast
    return quantile * error if error >= 0 else (quantile - 1.0) * error


def _normalize_group_by(
    group_by: str | Iterable[str] | None,
) -> tuple[str, ...]:
    if group_by is None:
        return ()
    if isinstance(group_by, str):
        raw_group_by = (group_by,)
    else:
        if isinstance(group_by, (bytes, Mapping)):
            raise ValueError("group_by must contain non-empty field names")
        try:
            raw_group_by = tuple(group_by)
        except TypeError as exc:
            raise ValueError("group_by must contain non-empty field names") from exc
    normalized: list[str] = []
    for field in raw_group_by:
        if not isinstance(field, str) or not field.strip():
            raise ValueError("group_by must contain non-empty field names")
        normalized.append(field.strip())
    if len(set(normalized)) != len(normalized):
        raise ValueError("group_by fields must be unique")
    return tuple(normalized)


def _materialize_rows(
    rows: Iterable[Mapping[str, Any]], field_name: str
) -> list[Mapping[str, Any]]:
    if isinstance(rows, (str, bytes, Mapping)):
        raise ValueError(f"{field_name} must be an iterable of mapping rows")
    try:
        materialized = tuple(rows)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an iterable of mapping rows") from exc
    for index, row in enumerate(materialized):
        if not isinstance(row, Mapping):
            raise ValueError(f"{field_name}[{index}] must be a mapping row")
    return list(materialized)


def _flatten_metric_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    materialized = _materialize_rows(rows, "rows")
    flattened: list[dict[str, Any]] = []
    for index, row in enumerate(materialized):
        base = dict(row)
        nested = base.pop("metrics", None)
        if nested is None:
            nested = base.pop("metric", None) if isinstance(base.get("metric"), Mapping) else None
        if isinstance(nested, Mapping):
            if _looks_like_horizon_mapping(nested):
                for horizon_key, metric_mapping in sorted(
                    nested.items(), key=lambda item: _stable_sort_key(item[0])
                ):
                    if not isinstance(metric_mapping, Mapping):
                        raise ValueError(
                            f"rows[{index}].metrics[{horizon_key!r}] must be a mapping"
                        )
                    merged = dict(metric_mapping)
                    merged.update(base)
                    _expand_metric_aliases(merged)
                    merged["horizon"] = _horizon_from_key(
                        horizon_key, metric_mapping.get("horizon")
                    )
                    flattened.append(merged)
                continue
            merged = dict(nested)
            merged.update(base)
            _expand_metric_aliases(merged)
            flattened.append(merged)
            continue

        horizon_mappings = [
            (key, value)
            for key, value in base.items()
            if _HORIZON_KEY_RE.fullmatch(str(key)) and isinstance(value, Mapping)
        ]
        if horizon_mappings and not _has_metric_fields(base):
            metadata = {
                key: value
                for key, value in base.items()
                if key not in {horizon_key for horizon_key, _ in horizon_mappings}
            }
            for horizon_key, metric_mapping in sorted(
                horizon_mappings, key=lambda item: _stable_sort_key(item[0])
            ):
                merged = dict(metric_mapping)
                merged.update(metadata)
                _expand_metric_aliases(merged)
                merged["horizon"] = _horizon_from_key(
                    horizon_key, metric_mapping.get("horizon")
                )
                flattened.append(merged)
            continue
        _expand_metric_aliases(base)
        flattened.append(base)
    return flattened


def _looks_like_horizon_mapping(value: Mapping[Any, Any]) -> bool:
    return bool(value) and all(
        _HORIZON_KEY_RE.fullmatch(str(key)) is not None for key in value
    )


def _horizon_from_key(key: Any, value: Any) -> int:
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
            raise ValueError("horizon must be a positive integer")
        return int(value)
    match = _HORIZON_KEY_RE.fullmatch(str(key))
    if match is None:
        raise ValueError(f"invalid horizon key: {key!r}")
    return int(match.group(1))


def _has_metric_fields(row: Mapping[str, Any]) -> bool:
    return any(
        field in row for field in _NUMERIC_METRIC_FIELDS + _BOOLEAN_METRIC_FIELDS
    )


def _expand_metric_aliases(row: dict[str, Any]) -> None:
    pinball_loss = row.get("pinball_loss")
    if not isinstance(pinball_loss, Mapping):
        return
    for quantile in ("p10", "p50", "p90"):
        field = f"pinball_loss_{quantile}"
        if field not in row and quantile in pinball_loss:
            row[field] = pinball_loss[quantile]


def _row_status(row: Mapping[str, Any]) -> str:
    status = row.get("status")
    if status is None:
        return "success" if _has_metric_fields(row) else "missing"
    if not isinstance(status, str):
        raise ValueError("row status must be a string")
    normalized = status.strip().lower()
    if not normalized:
        return "missing"
    return normalized


def _optional_metric_float(row: Mapping[str, Any], field: str) -> float | None:
    if field not in row or row[field] is None:
        return None
    value = _finite_float(row[field], field)
    if field in _NON_NEGATIVE_METRIC_FIELDS and value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _optional_metric_bool(row: Mapping[str, Any], field: str) -> bool | None:
    if field not in row or row[field] is None:
        return None
    value = row[field]
    if isinstance(value, bool):
        return value
    if isinstance(value, Integral) and value in (0, 1):
        return bool(value)
    raise ValueError(f"{field} must be a boolean")


def _mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    if not materialized:
        return None
    result = sum(materialized) / len(materialized)
    if not math.isfinite(result):
        raise ValueError("metric mean must be finite")
    return result


def _mean_or_none(values: list[float]) -> float | None:
    return _mean(values)


def _rate_or_none(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    rate = numerator / denominator
    if not math.isfinite(rate):
        raise ValueError("metric rate must be finite")
    return rate


def _group_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("group and block keys must be finite scalars")
        return value
    raise ValueError(
        "group and block keys must be JSON-compatible scalar values; "
        f"got {type(value).__name__}"
    )


def _typed_scalar_key(value: Any) -> tuple[str, Any]:
    """Return a collision-free internal key while preserving the scalar value."""

    normalized = _group_value(value)
    return (type(normalized).__name__, normalized)


def _stable_sort_key(value: Any) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(item for part in value for item in _stable_sort_key(part))
    if isinstance(value, list):
        return tuple(item for part in value for item in _stable_sort_key(part))
    return (type(value).__name__, repr(value))


def _model_name(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} model must be a non-empty string")
    return value.strip()


def _comparison_row_status(
    row: Mapping[str, Any], left: str, right: str
) -> str:
    model_statuses: list[str] = []
    for model in (left, right):
        for field in (f"{model}_status", f"status_{model}"):
            if field in row:
                model_statuses.append(_normalize_status_value(row[field]))
                break
    if model_statuses:
        for status in model_statuses:
            if status not in _SUCCESS_STATUSES:
                return status
        return "success"
    if "status" in row:
        return _normalize_status_value(row["status"])
    if left in row and right in row:
        return "success"
    if "model" in row and any(field in row for field in _LONG_VALUE_FIELDS):
        return "success"
    return "missing"


def _normalize_status_value(value: Any) -> str:
    if value is None:
        return "missing"
    if not isinstance(value, str):
        raise ValueError("comparison row status must be a string")
    normalized = value.strip().lower()
    return normalized or "missing"


def _is_long_comparison_row(
    row: Mapping[str, Any], left: str, right: str
) -> bool:
    return "model" in row and left not in row and right not in row


def _normalized_model_value(value: Any, *, row_index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"rows[{row_index}].model must be a non-empty string")
    return value.strip()


def _optional_numeric_value(
    row: Mapping[str, Any], field_names: Iterable[str]
) -> float | None:
    for field in field_names:
        if field in row:
            if row[field] is None:
                return None
            return _finite_float(row[field], field)
    return None


def _optional_comparison_value(row: Mapping[str, Any], model: str) -> float | None:
    if model not in row or row[model] is None:
        return None
    if isinstance(row[model], (list, tuple)):
        raise ValueError(
            "sequence-valued model fields require explicit horizon rows"
        )
    return _finite_float(row[model], model)


def _empirical_quantile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("cannot calculate a quantile from no values")
    position = (len(sorted_values) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    weight = position - lower_index
    return sorted_values[lower_index] * (1.0 - weight) + sorted_values[upper_index] * weight
