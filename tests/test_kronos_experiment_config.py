import json

import pytest

from stock_research.kronos_experiment_config import (
    KronosExperimentSpec,
    canonical_spec_payload,
    load_experiment_spec,
)


VALID_PAYLOAD = {
    "schema_version": 1,
    "experiment_id": "test-small",
    "model": {"name": "small", "fallback": False, "seed": 7, "sample_count": 20},
    "data": {
        "frequency": "1d",
        "adjust_type": "qfq",
        "input_window": 3,
        "start_date": "2025-01-02",
        "end_date": "2025-01-31",
    },
    "universe": {
        "mode": "explicit",
        "count": 2,
        "seed": None,
        "market": "CN_A",
        "asset_ids": ["sh.600418", "000001.SZ"],
    },
    "prediction": {
        "forecast_horizon": 2,
        "report_horizons": [1, 2],
        "include_latest_forecast": False,
    },
    "evaluation": {"primary_horizon": 1, "baseline": "persistence"},
}


def write_spec(tmp_path, payload):
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_valid_spec_normalizes_and_builds_low_level_config(tmp_path):
    spec = load_experiment_spec(write_spec(tmp_path, VALID_PAYLOAD))

    assert spec.asset_ids == ("CN:SH:600418", "CN:SZ:000001")
    assert spec.end_date == "2025-01-31"
    assert spec.end_date_latest is False
    assert len(spec.config_fingerprint) == 64
    assert spec.config_fingerprint == load_experiment_spec(
        write_spec(tmp_path, VALID_PAYLOAD)
    ).config_fingerprint

    config = spec.to_evaluation_config(("600418.SH",), "2025-02-01")
    assert config.asset_ids == ("CN:SH:600418",)
    assert config.end_date == "2025-02-01"
    assert config.models == ("small",)
    assert config.evaluation_horizons == (1, 2)
    assert config.primary_horizon == 1
    assert config.frequency == "1d"
    assert config.experiment_id == "test-small"
    assert config.config_fingerprint == spec.config_fingerprint


def test_latest_end_date_is_represented_in_canonical_payload(tmp_path):
    payload = json.loads(json.dumps(VALID_PAYLOAD))
    payload["data"]["end_date"] = "latest_available"
    spec = load_experiment_spec(write_spec(tmp_path, payload))

    assert spec.end_date is None
    assert spec.end_date_latest is True
    assert canonical_spec_payload(spec)["data"]["end_date"] == "latest_available"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda p: p.update(schema_version=2), "schema_version"),
        (lambda p: p["model"].update(name="large"), "model"),
        (lambda p: p["model"].update(fallback=True), "fallback"),
        (lambda p: p.update(experiment_id="  "), "experiment_id"),
        (lambda p: p["data"].update(frequency="5m"), "frequency"),
        (lambda p: p["data"].update(start_date="2025-02-01"), "date"),
        (lambda p: p.update(extra=True), "unknown"),
        (lambda p: p["universe"].update(mode="random", count=0, seed=7), "count"),
        (lambda p: p["universe"].update(mode="random", count=2, seed=None), "seed"),
        (lambda p: p["universe"].update(asset_ids=["sh.600418", "600418.SH"]), "unique"),
        (lambda p: p["prediction"].update(report_horizons=[2], forecast_horizon=1), "horizon"),
        (lambda p: p["evaluation"].update(baseline="mean"), "baseline"),
    ],
)
def test_load_rejects_invalid_specs(tmp_path, mutate, message):
    payload = json.loads(json.dumps(VALID_PAYLOAD))
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        load_experiment_spec(write_spec(tmp_path, payload))
