from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import requests

from stock_research.kronos_evaluation_types import (
    DEFAULT_KRONOS_SEED,
    RollingSnapshot,
    snapshot_to_json_payload,
    thaw_json_value,
)


_MODEL_ALIASES = {
    "small": "small",
    "kronos-small": "small",
    "base": "base",
    "kronos-base": "base",
}


class KronosErrorCategory:
    """Stable high-level categories for runner error handling."""

    VALIDATION = "validation"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    HTTP = "http"
    MODEL = "model"
    PROTOCOL = "protocol"


class KronosErrorCode:
    """Stable error codes carried by :class:`KronosClientError`."""

    INVALID_ARGUMENT = "invalid_argument"
    TOKEN_REQUIRED = "token_required"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    HTTP_ERROR = "http_error"
    MODEL_MISMATCH = "model_mismatch"
    MODEL_ERROR = "model_error"
    MALFORMED_JSON = "malformed_json"
    INVALID_RESPONSE = "invalid_response"


class KronosClientError(RuntimeError):
    """A categorized, catchable failure from the Kronos client."""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        code: str,
        status_code: int | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.status_code = status_code
        self.raw_response = raw_response


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
            raise KronosClientError(
                "Kronos base_url must be a non-empty string",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise KronosClientError(
                "Kronos base_url must be a non-empty string",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )

        if not isinstance(token, str) or not token.strip():
            raise KronosClientError(
                "Kronos token is required",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.TOKEN_REQUIRED,
            )

        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise KronosClientError(
                "Kronos timeout must be a positive finite number",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )
        try:
            normalized_timeout = float(timeout)
        except (OverflowError, TypeError, ValueError) as exc:
            raise KronosClientError(
                "Kronos timeout must be a positive finite number",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            ) from exc
        if not math.isfinite(normalized_timeout) or normalized_timeout <= 0:
            raise KronosClientError(
                "Kronos timeout must be a positive finite number",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )

        self.base_url = normalized_base_url
        self.timeout = normalized_timeout
        self._headers = {"X-Kronos-Token": token.strip()}
        self.session = session if session is not None else requests.Session()

    def health(self) -> dict[str, Any]:
        """Return ready health data with the active model normalized."""

        response = self._request_json("GET", "/health")
        if response.get("status") != "ok":
            raise KronosClientError(
                "Kronos service is not ready: expected health status 'ok', "
                f"got {response.get('status')!r}",
                category=KronosErrorCategory.TRANSPORT,
                code=KronosErrorCode.SERVICE_UNAVAILABLE,
                raw_response=response,
            )

        raw_model = response.get("model")
        if raw_model is None:
            raise KronosClientError(
                "Kronos health response is missing model",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
            )
        try:
            normalized_model = _normalize_model_name(raw_model)
        except KronosClientError as exc:
            raise KronosClientError(
                f"Kronos health response has unsupported model {raw_model!r}",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
            ) from exc

        normalized = _clone_json_object(response)
        normalized["model"] = normalized_model
        return _attach_raw_response(normalized, raw_response=response)

    def assert_model(self, model: str) -> dict[str, Any]:
        """Ensure the ready service is running the requested model."""

        requested_model = _normalize_model_name(model, label="requested model")
        health = self.health()
        active_model = health.get("model")
        if active_model != requested_model:
            raise KronosClientError(
                "Kronos model mismatch: "
                f"requested {requested_model}, active {active_model}",
                category=KronosErrorCategory.MODEL,
                code=KronosErrorCode.MODEL_MISMATCH,
                raw_response=health.get("raw_response"),
            )
        return health

    def predict_daily(
        self,
        snapshot: RollingSnapshot,
        *,
        model: str,
        sample_count: int = 20,
        seed: int | None = DEFAULT_KRONOS_SEED,
    ) -> dict[str, Any]:
        """Predict one ready snapshot with deterministic evaluation defaults.

        The default seed is shared with ``KronosEvaluationConfig``. Callers may
        pass an explicit seed such as ``7`` from the approved smoke example,
        or pass ``None`` when the service should receive no seed.
        """

        if not isinstance(snapshot, RollingSnapshot):
            raise KronosClientError(
                "snapshot must be a RollingSnapshot",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )
        if snapshot.status != "ready":
            raise KronosClientError(
                "cannot predict a snapshot whose status is "
                f"{snapshot.status!r}",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )
        if (
            isinstance(sample_count, bool)
            or not isinstance(sample_count, int)
            or not 1 <= sample_count <= 100
        ):
            raise KronosClientError(
                "sample_count must be an integer between 1 and 100",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )
        if seed is not None and (
            isinstance(seed, bool) or not isinstance(seed, int)
        ):
            raise KronosClientError(
                "seed must be an integer or None",
                category=KronosErrorCategory.VALIDATION,
                code=KronosErrorCode.INVALID_ARGUMENT,
            )

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
                "frozen snapshot serialization produced inconsistent JSON",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
            )

        result = self._request_json("POST", "/v1/predict", payload=payload)
        _validate_prediction_response(result)
        return _attach_raw_response(result)

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
                raise KronosClientError(
                    f"unsupported Kronos HTTP method: {method}",
                    category=KronosErrorCategory.VALIDATION,
                    code=KronosErrorCode.INVALID_ARGUMENT,
                )
        except requests.Timeout as exc:
            raise KronosClientError(
                f"Kronos {path} request timed out: {exc}",
                category=KronosErrorCategory.TIMEOUT,
                code=KronosErrorCode.TIMEOUT,
            ) from exc
        except TimeoutError as exc:
            raise KronosClientError(
                f"Kronos {path} request timed out: {exc}",
                category=KronosErrorCategory.TIMEOUT,
                code=KronosErrorCode.TIMEOUT,
            ) from exc
        except requests.RequestException as exc:
            raise KronosClientError(
                f"Kronos {path} request failed: {exc}",
                category=KronosErrorCategory.TRANSPORT,
                code=KronosErrorCode.TRANSPORT_ERROR,
            ) from exc

        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int):
            raise KronosClientError(
                f"Kronos {path} returned an invalid HTTP response",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
            )
        if status_code != 200:
            body = str(getattr(response, "text", "") or "").strip()
            detail = f": {body}" if body else ""
            raise KronosClientError(
                f"Kronos {path} returned HTTP {status_code}{detail}",
                category=KronosErrorCategory.HTTP,
                code=KronosErrorCode.HTTP_ERROR,
                status_code=status_code,
            )

        try:
            raw_response = response.json()
        except (AttributeError, TypeError, ValueError) as exc:
            raise KronosClientError(
                f"Kronos {path} returned malformed JSON",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.MALFORMED_JSON,
            ) from exc

        try:
            normalized_response = _clone_json_value(raw_response)
        except (TypeError, ValueError) as exc:
            raise KronosClientError(
                f"Kronos {path} returned invalid JSON: {exc}",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
            ) from exc
        if not isinstance(normalized_response, dict):
            raise KronosClientError(
                f"Kronos {path} response must be a JSON object",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
            )
        return normalized_response


def _normalize_model_name(value: Any, *, label: str = "model") -> str:
    if not isinstance(value, str):
        raise KronosClientError(
            f"{label} must be small or base",
            category=KronosErrorCategory.VALIDATION,
            code=KronosErrorCode.INVALID_ARGUMENT,
        )
    normalized = _MODEL_ALIASES.get(value.strip().lower())
    if normalized is None:
        raise KronosClientError(
            f"{label} must be small or base",
            category=KronosErrorCategory.VALIDATION,
            code=KronosErrorCode.INVALID_ARGUMENT,
        )
    return normalized


def _validate_prediction_response(response: dict[str, Any]) -> None:
    status = response.get("status")
    if status != "succeeded":
        if status is not None:
            raise KronosClientError(
                "Kronos prediction response did not succeed: "
                f"status={status!r}",
                category=KronosErrorCategory.MODEL,
                code=KronosErrorCode.MODEL_ERROR,
                raw_response=response,
            )
        raise KronosClientError(
            "Kronos prediction response is missing success status",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
        )

    result = response.get("result")
    if not isinstance(result, Mapping):
        raise KronosClientError(
            "Kronos prediction response has no result mapping",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
        )
    daily = result.get("daily")
    if not isinstance(daily, Mapping) or not daily:
        raise KronosClientError(
            "Kronos prediction response has no daily forecast data",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
        )


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


def _attach_raw_response(
    payload: dict[str, Any],
    *,
    raw_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _clone_json_object(payload)
    complete_response = payload if raw_response is None else raw_response
    if "raw_response" not in normalized:
        normalized["raw_response"] = _clone_json_value(complete_response)
        return normalized

    fallback_key = "_kronos_raw_response"
    while fallback_key in normalized:
        fallback_key = f"_{fallback_key}"
    normalized[fallback_key] = _clone_json_value(complete_response)
    return normalized


__all__ = [
    "KronosClient",
    "KronosClientError",
    "KronosErrorCategory",
    "KronosErrorCode",
]
