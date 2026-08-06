from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import requests

from stock_research.kronos_evaluation_data import snapshot_to_json_payload
from stock_research.kronos_evaluation_types import RollingSnapshot, thaw_json_value


_MODEL_ALIASES = {
    "small": "small",
    "kronos-small": "small",
    "base": "base",
    "kronos-base": "base",
}


class KronosClientError(RuntimeError):
    """Raised when the Kronos service cannot safely serve an evaluation request."""


class KronosClient:
    """Authenticated client for the frozen-snapshot Kronos HTTP contract."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise KronosClientError("Kronos base_url must be a non-empty string")
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise KronosClientError("Kronos base_url must be a non-empty string")

        if not isinstance(token, str) or not token.strip():
            raise KronosClientError("Kronos token is required")

        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise KronosClientError("Kronos timeout must be a positive finite number")
        try:
            normalized_timeout = float(timeout)
        except (OverflowError, TypeError, ValueError) as exc:
            raise KronosClientError(
                "Kronos timeout must be a positive finite number"
            ) from exc
        if not math.isfinite(normalized_timeout) or normalized_timeout <= 0:
            raise KronosClientError("Kronos timeout must be a positive finite number")

        self.base_url = normalized_base_url
        self.timeout = normalized_timeout
        self._headers = {"X-Kronos-Token": token.strip()}
        self.session = session if session is not None else requests.Session()

    def health(self) -> dict[str, Any]:
        """Return health data with the active model normalized to ``small``/``base``."""

        response = self._request_json("GET", "/health")
        raw_model = response.get("model")
        if raw_model is None:
            raise KronosClientError("Kronos health response is missing model")
        try:
            normalized_model = _normalize_model_name(raw_model)
        except KronosClientError as exc:
            raise KronosClientError(
                f"Kronos health response has unsupported model {raw_model!r}"
            ) from exc

        normalized = _clone_json_object(response)
        normalized["model"] = normalized_model
        normalized["raw_response"] = _clone_json_value(response)
        return normalized

    def assert_model(self, model: str) -> dict[str, Any]:
        """Ensure the service is running the requested model before prediction."""

        requested_model = _normalize_model_name(model, label="requested model")
        health = self.health()
        active_model = health.get("model")
        if active_model != requested_model:
            raise KronosClientError(
                "Kronos model mismatch: "
                f"requested {requested_model}, active {active_model}"
            )
        return health

    def predict_daily(
        self,
        snapshot: RollingSnapshot,
        *,
        model: str,
        sample_count: int = 20,
        seed: int | None = 7,
    ) -> dict[str, Any]:
        """Predict from one ready, immutable daily snapshot."""

        if not isinstance(snapshot, RollingSnapshot):
            raise KronosClientError("snapshot must be a RollingSnapshot")
        if snapshot.status != "ready":
            raise KronosClientError(
                "cannot predict a snapshot whose status is "
                f"{snapshot.status!r}"
            )
        if (
            isinstance(sample_count, bool)
            or not isinstance(sample_count, int)
            or sample_count <= 0
        ):
            raise KronosClientError("sample_count must be a positive integer")
        if seed is not None and (
            isinstance(seed, bool) or not isinstance(seed, int)
        ):
            raise KronosClientError("seed must be an integer or None")

        requested_model = _normalize_model_name(model, label="requested model")
        self.assert_model(requested_model)

        serialized_snapshot = snapshot_to_json_payload(snapshot)
        payload = thaw_json_value(
            {
                "model": requested_model,
                "sample_count": sample_count,
                "seed": seed,
                "daily": {
                    "history": snapshot.history,
                    "future_timestamps": snapshot.future_timestamps,
                },
            }
        )
        if (
            payload["daily"]["history"] != serialized_snapshot["history"]
            or payload["daily"]["future_timestamps"]
            != serialized_snapshot["future_timestamps"]
        ):
            raise KronosClientError(
                "frozen snapshot serialization produced inconsistent JSON"
            )
        result = self._request_json("POST", "/v1/predict", payload=payload)
        normalized_result = _clone_json_object(result)
        normalized_result["raw_response"] = _clone_json_value(result)
        return normalized_result

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = dict(self._headers)
        try:
            if method == "GET":
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                )
            elif method == "POST":
                response = self.session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
            else:  # pragma: no cover - private method only has two call sites.
                raise KronosClientError(f"unsupported Kronos HTTP method: {method}")
        except requests.Timeout as exc:
            raise KronosClientError(
                f"Kronos {path} request timed out: {exc}"
            ) from exc
        except TimeoutError as exc:
            raise KronosClientError(
                f"Kronos {path} request timed out: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise KronosClientError(
                f"Kronos {path} request failed: {exc}"
            ) from exc

        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int):
            raise KronosClientError(
                f"Kronos {path} returned an invalid HTTP response"
            )
        if status_code != 200:
            body = str(getattr(response, "text", "") or "").strip()
            detail = f": {body}" if body else ""
            raise KronosClientError(
                f"Kronos {path} returned HTTP {status_code}{detail}"
            )

        try:
            raw_response = response.json()
        except (AttributeError, TypeError, ValueError) as exc:
            raise KronosClientError(
                f"Kronos {path} returned malformed JSON"
            ) from exc

        try:
            normalized_response = _clone_json_value(raw_response)
        except (TypeError, ValueError) as exc:
            raise KronosClientError(
                f"Kronos {path} returned invalid JSON: {exc}"
            ) from exc
        if not isinstance(normalized_response, dict):
            raise KronosClientError(
                f"Kronos {path} response must be a JSON object"
            )
        return normalized_response


def _normalize_model_name(value: Any, *, label: str = "model") -> str:
    if not isinstance(value, str):
        raise KronosClientError(f"{label} must be small or base")
    normalized = _MODEL_ALIASES.get(value.strip().lower())
    if normalized is None:
        raise KronosClientError(f"{label} must be small or base")
    return normalized


def _clone_json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    cloned = _clone_json_value(value)
    if not isinstance(cloned, dict):  # pragma: no cover - type guard for callers.
        raise TypeError("expected a JSON object")
    return cloned


def _clone_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        cloned: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            cloned[key] = _clone_json_value(item)
        return cloned
    if isinstance(value, (list, tuple)):
        return [_clone_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


__all__ = ["KronosClient", "KronosClientError"]
