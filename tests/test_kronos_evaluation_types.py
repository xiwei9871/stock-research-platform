import json
import math

import pytest

from stock_research.kronos_evaluation_types import (
    KronosEvaluationConfig,
    RollingSnapshot,
    canonical_json_fingerprint,
    normalize_asset_ids,
    thaw_json_value,
)


def test_config_accepts_confirmed_defaults():
    config = KronosEvaluationConfig(
        asset_ids=("CN:SH:600418", "CN:SZ:000001"),
        start_date="2025-01-02",
        end_date="2025-01-31",
    )

    assert config.asset_ids == ("CN:SH:600418", "CN:SZ:000001")
    assert config.input_window == 250
    assert config.roll_step == 1
    assert config.forecast_horizon == 10
    assert config.evaluation_horizons == (1, 3, 5, 10)
    assert config.sample_count == 20
    assert config.models == ("small", "base")
    assert config.adjust_type == "qfq"
    assert config.db_service == "stock_research"
    assert config.predict_url == "http://192.168.3.187:8123"
    assert config.token_env == "KRONOS_INTERNAL_TOKEN"
    assert config.timeout_seconds == 60.0
    assert config.seed == 20260806


def test_normalize_asset_ids_accepts_local_forms_and_explicit_bare_resolver():
    resolver_calls = []

    def resolve_exchange(symbol):
        resolver_calls.append(symbol)
        return {"600418": "sh", "000001": ("SZ",)}[symbol]

    assert normalize_asset_ids(("CN:SH:600418",)) == ("CN:SH:600418",)
    assert normalize_asset_ids(("sh.600418",)) == ("CN:SH:600418",)
    assert normalize_asset_ids(("600418.SH",)) == ("CN:SH:600418",)
    assert normalize_asset_ids(("600418",), exchange_resolver=resolve_exchange) == (
        "CN:SH:600418",
    )
    assert normalize_asset_ids(("000001",), exchange_resolver=resolve_exchange) == (
        "CN:SZ:000001",
    )
    assert resolver_calls == ["600418", "000001"]


def test_normalize_asset_ids_requires_a_unique_exchange_for_bare_codes():
    with pytest.raises(ValueError, match="exchange_resolver"):
        normalize_asset_ids(("600418",))

    with pytest.raises(ValueError, match="unique exchange"):
        normalize_asset_ids(
            ("600418",),
            exchange_resolver=lambda _symbol: ("SH", "SZ"),
        )

    with pytest.raises(ValueError, match="unique exchange"):
        normalize_asset_ids(
            ("600418",),
            exchange_resolver=lambda _symbol: None,
        )


def test_config_rejects_duplicate_assets_after_normalization():
    with pytest.raises(ValueError, match="unique"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418", "600418.SH"),
            start_date="2025-01-02",
            end_date="2025-01-31",
        )


def test_config_rejects_horizons_outside_forecast_window():
    with pytest.raises(ValueError, match="horizon"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            evaluation_horizons=(1, 11),
            forecast_horizon=10,
        )

    with pytest.raises(ValueError, match="horizon"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            evaluation_horizons=(3, 1),
        )

    with pytest.raises(ValueError, match="forecast_horizon"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            forecast_horizon=11,
        )


def test_config_rejects_invalid_numeric_settings_and_models():
    with pytest.raises(ValueError, match="input_window"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            input_window=0,
        )

    with pytest.raises(ValueError, match="roll_step"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            roll_step=0,
        )

    with pytest.raises(ValueError, match="sample_count"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            sample_count=101,
        )

    with pytest.raises(ValueError, match="models"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            models=("large",),
        )


def test_config_normalizes_model_case_and_whitespace():
    config = KronosEvaluationConfig(
        asset_ids=("CN:SH:600418",),
        start_date="2025-01-02",
        end_date="2025-01-31",
        models=(" SMALL ", "BASE"),
    )

    assert config.models == ("small", "base")


def test_config_accepts_numeric_boundary_values():
    config = KronosEvaluationConfig(
        asset_ids=("CN:SH:600418",),
        start_date="2025-01-02",
        end_date="2025-01-31",
        input_window=1,
        roll_step=1,
        forecast_horizon=1,
        evaluation_horizons=(1,),
        sample_count=1,
    )
    maximum_sample_config = KronosEvaluationConfig(
        asset_ids=("CN:SH:600418",),
        start_date="2025-01-02",
        end_date="2025-01-31",
        sample_count=100,
    )

    assert config.forecast_horizon == 1
    assert config.evaluation_horizons == (1,)
    assert maximum_sample_config.sample_count == 100


def test_config_rejects_timeout_integer_that_overflows_float_conversion():
    with pytest.raises(ValueError, match="timeout_seconds"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-01-02",
            end_date="2025-01-31",
            timeout_seconds=10**1000,
        )


def test_config_rejects_invalid_dates():
    with pytest.raises(ValueError, match="start_date"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-02-30",
            end_date="2025-03-01",
        )

    with pytest.raises(ValueError, match="start_date"):
        KronosEvaluationConfig(
            asset_ids=("CN:SH:600418",),
            start_date="2025-02-01",
            end_date="2025-01-31",
        )


def make_ready_snapshot():
    history = (
        {
            "timestamp": "2025-01-02",
            "open": 100.0,
            "high": 103.0,
            "low": 99.0,
            "close": 102.0,
            "volume": 1200.0,
            "amount": 121000.0,
        },
        {
            "timestamp": "2025-01-03",
            "open": 102.0,
            "high": 105.0,
            "low": 101.0,
            "close": 104.0,
            "volume": 1300.0,
            "amount": 135000.0,
        },
    )
    fingerprint_payload = {
        "asset_id": "CN:SH:600418",
        "origin_date": "2025-01-03",
        "history": history,
    }
    return RollingSnapshot(
        asset_id="CN:SH:600418",
        origin_date="2025-01-03",
        history=history,
        future_timestamps=("2025-01-06", "2025-01-07"),
        realized=(
            {"timestamp": "2025-01-06", "close": 105.0},
            {"timestamp": "2025-01-07", "close": 106.0},
        ),
        input_fingerprint=canonical_json_fingerprint(fingerprint_payload),
        status="ready",
    )


def test_snapshot_key_and_fingerprint_are_stable():
    first = make_ready_snapshot()
    second = make_ready_snapshot()

    assert first.key == "CN:SH:600418|2025-01-03"
    assert first.input_fingerprint == second.input_fingerprint
    assert first.input_fingerprint == canonical_json_fingerprint(
        {
            "history": first.history,
            "origin_date": first.origin_date,
            "asset_id": first.asset_id,
        }
    )


def test_snapshot_defensively_copies_and_freezes_nested_bar_data():
    source_history = [
        {
            "timestamp": "2025-01-02",
            "open": 100.0,
            "high": 103.0,
            "low": 99.0,
            "close": 102.0,
            "volume": 1200.0,
            "amount": 121000.0,
            "metadata": {"tags": ["input"]},
        }
    ]
    source_realized = [{"timestamp": "2025-01-06", "close": 105.0}]
    fingerprint = canonical_json_fingerprint(
        {
            "asset_id": "CN:SH:600418",
            "origin_date": "2025-01-02",
            "history": source_history,
        }
    )
    snapshot = RollingSnapshot(
        asset_id="CN:SH:600418",
        origin_date="2025-01-02",
        history=source_history,
        future_timestamps=("2025-01-06",),
        realized=source_realized,
        input_fingerprint=fingerprint,
        status="ready",
    )

    source_history[0]["close"] = 999.0
    source_history[0]["metadata"]["tags"].append("caller-mutated")
    source_realized[0]["close"] = 999.0

    assert snapshot.history[0]["close"] == 102.0
    assert snapshot.history[0]["metadata"]["tags"] == ("input",)
    assert snapshot.realized[0]["close"] == 105.0
    assert snapshot.input_fingerprint == fingerprint

    with pytest.raises(TypeError):
        snapshot.history[0]["close"] = 999.0
    with pytest.raises(TypeError):
        snapshot.history[0]["metadata"]["tags"] += ("caller-mutated",)
    with pytest.raises(TypeError):
        snapshot.realized[0]["close"] = 999.0


def test_snapshot_freezes_extra_json_values_and_supports_thawing():
    source_history = [
        {
            "timestamp": "2025-01-02",
            "open": 100.0,
            "high": 103.0,
            "low": 99.0,
            "close": 102.0,
            "volume": 1200.0,
            "amount": 121000.0,
            "extra": {"nested": [{"labels": ["stable"]}]},
        }
    ]
    snapshot = RollingSnapshot(
        asset_id="CN:SH:600418",
        origin_date="2025-01-02",
        history=source_history,
        future_timestamps=(),
        realized=(),
        input_fingerprint="0" * 64,
        status="ready",
    )

    source_history[0]["extra"]["nested"][0]["labels"].append("caller-mutated")

    assert snapshot.history[0]["extra"]["nested"][0]["labels"] == ("stable",)
    thawed = thaw_json_value(snapshot.history[0])
    assert thawed["extra"] == {"nested": [{"labels": ["stable"]}]}
    assert json.loads(json.dumps(thawed, sort_keys=True)) == thawed

    with pytest.raises(TypeError):
        snapshot.history[0]["extra"] = {"changed": True}
    with pytest.raises(TypeError):
        snapshot.history[0]["extra"]["nested"][0]["labels"] = ("changed",)
    with pytest.raises(TypeError):
        snapshot.history[0]["extra"]["nested"][0]["labels"] += ("changed",)


def test_snapshot_rejects_unsupported_nested_object_values():
    unsupported_history = {
        "timestamp": "2025-01-02",
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 1200.0,
        "amount": 121000.0,
        "extra": {"unsupported": object()},
    }

    with pytest.raises(ValueError, match="unsupported"):
        RollingSnapshot(
            asset_id="CN:SH:600418",
            origin_date="2025-01-02",
            history=(unsupported_history,),
            future_timestamps=(),
            realized=(),
            input_fingerprint="0" * 64,
            status="invalid_input",
        )


def test_snapshot_rejects_missing_or_non_finite_history_values():
    missing_close = {
        "timestamp": "2025-01-02",
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "volume": 1200.0,
        "amount": 121000.0,
    }
    non_finite_close = {
        "timestamp": "2025-01-02",
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": math.inf,
        "volume": 1200.0,
        "amount": 121000.0,
    }

    with pytest.raises(ValueError, match="close"):
        RollingSnapshot(
            asset_id="CN:SH:600418",
            origin_date="2025-01-02",
            history=(missing_close,),
            future_timestamps=(),
            realized=(),
            input_fingerprint="0" * 64,
            status="invalid_input",
        )
    with pytest.raises(ValueError, match="finite"):
        RollingSnapshot(
            asset_id="CN:SH:600418",
            origin_date="2025-01-02",
            history=(non_finite_close,),
            future_timestamps=(),
            realized=(),
            input_fingerprint="0" * 64,
            status="invalid_input",
        )


def test_fingerprint_is_independent_of_mapping_order():
    first = canonical_json_fingerprint({"b": 2, "a": [1, "x"]})
    second = canonical_json_fingerprint({"a": [1, "x"], "b": 2})
    changed = canonical_json_fingerprint({"a": [1, "y"], "b": 2})

    assert first == second
    assert first != changed


def test_fingerprint_canonicalizes_nested_key_order_and_json_edges():
    first = canonical_json_fingerprint(
        {"z": {"β": None, "a": []}, "a": {"empty": {}}, "flags": [True, False]}
    )
    second = canonical_json_fingerprint(
        {"flags": [True, False], "a": {"empty": {}}, "z": {"a": [], "β": None}}
    )

    assert first == second


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_fingerprint_rejects_non_finite_json_numbers(value):
    with pytest.raises(ValueError):
        canonical_json_fingerprint({"value": value})
