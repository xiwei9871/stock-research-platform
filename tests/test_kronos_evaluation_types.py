import pytest

from stock_research.kronos_evaluation_types import (
    KronosEvaluationConfig,
    RollingSnapshot,
    canonical_json_fingerprint,
    normalize_asset_ids,
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


def test_fingerprint_is_independent_of_mapping_order():
    first = canonical_json_fingerprint({"b": 2, "a": [1, "x"]})
    second = canonical_json_fingerprint({"a": [1, "x"], "b": 2})
    changed = canonical_json_fingerprint({"a": [1, "y"], "b": 2})

    assert first == second
    assert first != changed
