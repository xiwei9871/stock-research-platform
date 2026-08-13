from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from stock_research.kronos_evaluation_types import (
    KronosEvaluationConfig,
    canonical_json_fingerprint,
    normalize_asset_ids,
)


_TOP_LEVEL_KEYS = {"schema_version", "experiment_id", "model", "data", "universe", "prediction", "evaluation"}
_MODEL_KEYS = {"name", "fallback", "seed", "sample_count"}
_DATA_KEYS = {"frequency", "adjust_type", "input_window", "start_date", "end_date"}
_UNIVERSE_KEYS = {"mode", "count", "seed", "market", "asset_ids"}
_PREDICTION_KEYS = {"forecast_horizon", "report_horizons", "include_latest_forecast"}
_EVALUATION_KEYS = {"primary_horizon", "baseline"}
_EXPERIMENT_ID_RE = re.compile(r"^[A-Za-z0-9_-](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9_-])?$")


@dataclass(frozen=True)
class KronosExperimentSpec:
    schema_version: int
    experiment_id: str
    model_name: str
    fallback: bool
    model_seed: int | None
    sample_count: int
    frequency: str
    adjust_type: str
    input_window: int
    start_date: str
    end_date: str | None
    end_date_latest: bool
    universe_mode: str
    universe_count: int
    universe_seed: int | None
    market: str
    asset_ids: tuple[str, ...]
    forecast_horizon: int
    report_horizons: tuple[int, ...]
    primary_horizon: int
    include_latest_forecast: bool
    baseline: str
    config_fingerprint: str

    def to_evaluation_config(
        self, *, asset_ids: tuple[str, ...], end_date: str
    ) -> KronosEvaluationConfig:
        return KronosEvaluationConfig(
            asset_ids=asset_ids,
            start_date=self.start_date,
            end_date=end_date,
            input_window=self.input_window,
            forecast_horizon=self.forecast_horizon,
            evaluation_horizons=self.report_horizons,
            sample_count=self.sample_count,
            models=(self.model_name,),
            adjust_type=self.adjust_type,
            seed=self.model_seed,
            frequency=self.frequency,
            primary_horizon=self.primary_horizon,
            include_latest_forecast=self.include_latest_forecast,
            fallback=self.fallback,
            experiment_id=self.experiment_id,
            config_fingerprint=self.config_fingerprint,
        )


def load_experiment_spec(path: Path) -> KronosExperimentSpec:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid experiment JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("experiment JSON must contain an object")
    _require_keys(payload, _TOP_LEVEL_KEYS, "experiment")
    if (
        isinstance(payload["schema_version"], bool)
        or not isinstance(payload["schema_version"], int)
        or payload["schema_version"] != 1
    ):
        raise ValueError("schema_version must be 1")

    model = _mapping(payload["model"], "model")
    data = _mapping(payload["data"], "data")
    universe = _mapping(payload["universe"], "universe")
    prediction = _mapping(payload["prediction"], "prediction")
    evaluation = _mapping(payload["evaluation"], "evaluation")
    _require_keys(model, _MODEL_KEYS, "model")
    _require_keys(data, _DATA_KEYS, "data")
    _require_keys(universe, _UNIVERSE_KEYS, "universe")
    _require_keys(prediction, _PREDICTION_KEYS, "prediction")
    _require_keys(evaluation, _EVALUATION_KEYS, "evaluation")

    experiment_id = _non_empty_string(payload["experiment_id"], "experiment_id")
    if len(experiment_id) > 128 or not _EXPERIMENT_ID_RE.fullmatch(experiment_id):
        raise ValueError("experiment_id must use safe path-compatible characters")
    model_name = _non_empty_string(model["name"], "model.name").lower()
    if model_name not in {"small", "base"}:
        raise ValueError("model must be small or base")
    if model["fallback"] is not False:
        raise ValueError("fallback must be false")
    model_seed = _optional_int(model["seed"], "model.seed")
    sample_count = _positive_int(model["sample_count"], "model.sample_count")
    frequency = _non_empty_string(data["frequency"], "frequency")
    if frequency != "1d":
        raise ValueError("frequency must be 1d")
    adjust_type = _non_empty_string(data["adjust_type"], "adjust_type")
    input_window = _positive_int(data["input_window"], "input_window")
    start_date = _iso_date(data["start_date"], "start_date")
    end_date, end_date_latest = _end_date(data["end_date"])
    if end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    universe_mode = _non_empty_string(universe["mode"], "universe.mode").lower()
    if universe_mode not in {"explicit", "random"}:
        raise ValueError("universe.mode must be explicit or random")
    universe_count = _positive_int(universe["count"], "universe.count")
    universe_seed = _optional_int(universe["seed"], "universe.seed")
    if universe_mode == "random" and universe_seed is None:
        raise ValueError("random universe requires seed")
    market = _non_empty_string(universe["market"], "universe.market")
    raw_asset_ids = universe["asset_ids"]
    if universe_mode == "random" and raw_asset_ids:
        raise ValueError("random universe must not specify asset_ids")
    if universe_mode == "explicit" and not raw_asset_ids:
        raise ValueError("explicit universe requires asset_ids")
    asset_ids = normalize_asset_ids(raw_asset_ids or ())
    if universe_mode == "explicit" and len(asset_ids) != universe_count:
        raise ValueError("universe.count must match asset_ids")

    forecast_horizon = _positive_int(prediction["forecast_horizon"], "forecast_horizon")
    report_horizons = _positive_int_tuple(prediction["report_horizons"], "report_horizons")
    if report_horizons != tuple(sorted(report_horizons)) or len(set(report_horizons)) != len(report_horizons):
        raise ValueError("report_horizons must be strictly increasing")
    if any(horizon > forecast_horizon for horizon in report_horizons):
        raise ValueError("report_horizons must not exceed forecast_horizon")
    include_latest_forecast = prediction["include_latest_forecast"]
    if not isinstance(include_latest_forecast, bool):
        raise ValueError("include_latest_forecast must be a boolean")
    primary_horizon = _positive_int(evaluation["primary_horizon"], "primary_horizon")
    if primary_horizon not in report_horizons or primary_horizon > forecast_horizon:
        raise ValueError("primary_horizon must be in report_horizons")
    baseline = _non_empty_string(evaluation["baseline"], "baseline").lower()
    if baseline != "persistence":
        raise ValueError("baseline must be persistence")

    spec = KronosExperimentSpec(
        schema_version=1,
        experiment_id=experiment_id,
        model_name=model_name,
        fallback=False,
        model_seed=model_seed,
        sample_count=sample_count,
        frequency=frequency,
        adjust_type=adjust_type,
        input_window=input_window,
        start_date=start_date,
        end_date=end_date,
        end_date_latest=end_date_latest,
        universe_mode=universe_mode,
        universe_count=universe_count,
        universe_seed=universe_seed,
        market=market,
        asset_ids=asset_ids,
        forecast_horizon=forecast_horizon,
        report_horizons=report_horizons,
        primary_horizon=primary_horizon,
        include_latest_forecast=include_latest_forecast,
        baseline=baseline,
        config_fingerprint="",
    )
    return KronosExperimentSpec(**{**spec.__dict__, "config_fingerprint": canonical_json_fingerprint(canonical_spec_payload(spec))})


def canonical_spec_payload(spec: KronosExperimentSpec) -> dict[str, Any]:
    return {
        "schema_version": spec.schema_version,
        "experiment_id": spec.experiment_id,
        "model": {"name": spec.model_name, "fallback": spec.fallback, "seed": spec.model_seed, "sample_count": spec.sample_count},
        "data": {"frequency": spec.frequency, "adjust_type": spec.adjust_type, "input_window": spec.input_window, "start_date": spec.start_date, "end_date": "latest_available" if spec.end_date_latest else spec.end_date},
        "universe": {"mode": spec.universe_mode, "count": spec.universe_count, "seed": spec.universe_seed, "market": spec.market, "asset_ids": list(spec.asset_ids)},
        "prediction": {"forecast_horizon": spec.forecast_horizon, "report_horizons": list(spec.report_horizons), "include_latest_forecast": spec.include_latest_forecast},
        "evaluation": {"primary_horizon": spec.primary_horizon, "baseline": spec.baseline},
    }


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _require_keys(value: dict[str, Any], allowed: set[str], field_name: str) -> None:
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown:
        raise ValueError(f"unknown {field_name} keys: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing {field_name} keys: {sorted(missing)}")


def _non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer or None")
    return value


def _positive_int_tuple(value: Any, field_name: str) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must contain positive integers")
    try:
        return tuple(_positive_int(item, f"{field_name}[]") for item in value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must contain positive integers") from exc


def _iso_date(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _end_date(value: Any) -> tuple[str | None, bool]:
    if value == "latest_available":
        return None, True
    end_date = _iso_date(value, "end_date")
    return end_date, False
