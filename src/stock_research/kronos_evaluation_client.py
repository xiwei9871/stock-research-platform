from __future__ import annotations

import math
import re
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
_MAX_RAW_BODY_EXCERPT = 512
_REDACTED = "[REDACTED]"
_MAX_RAW_BODY_SCAN = _MAX_RAW_BODY_EXCERPT * 4
_MAX_ASSIGNMENT_FIELD_LENGTH = 128
_SAFE_UNQUOTED_VALUE_DELIMITERS = frozenset(",;\r\n]}")
_SENSITIVE_FIELD_TERMS = frozenset(
    {
        "authorization",
        "token",
        "secret",
        "password",
        "apikey",
        "accesskey",
        "refreshtoken",
        "clientsecret",
        "credential",
        "cookie",
        "privatekey",
        "passphrase",
    }
)
_PREDICTION_SUCCESS_STATUSES = frozenset({"partial", "complete", "succeeded"})
_PREDICTION_FAILURE_STATUSES = frozenset({"failed", "error"})
_DAILY_FAILURE_STATUSES = frozenset({"error", "unavailable", "failed"})
_HEALTH_NON_READY_STATUSES = frozenset({"degraded", "error", "unavailable"})


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
        raw_body_excerpt: str | None = None,
        redaction_token: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.status_code = status_code
        self.raw_response = (
            _redact_sensitive_json_value(raw_response, token=redaction_token)
            if isinstance(raw_response, Mapping)
            else raw_response
        )
        self.raw_body_excerpt = raw_body_excerpt


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
        self._owns_session = session is None
        self._closed = False
        self.session = session if session is not None else requests.Session()

    def close(self) -> None:
        """Close the internally-created HTTP session, if any."""

        if self._closed or not self._owns_session:
            return
        self._closed = True
        close = getattr(self.session, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "KronosClient":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        self.close()
        return False

    def health(self) -> dict[str, Any]:
        """Return ready health data with the active model normalized."""

        response = self._request_json("GET", "/health")
        status = response.get("status")
        if not isinstance(status, str):
            raise KronosClientError(
                "Kronos health response has an invalid status",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=self._headers.get("X-Kronos-Token"),
            )
        if status != "ok":
            if status not in _HEALTH_NON_READY_STATUSES:
                raise KronosClientError(
                    "Kronos health response has an unknown status",
                    category=KronosErrorCategory.PROTOCOL,
                    code=KronosErrorCode.INVALID_RESPONSE,
                    raw_response=response,
                    redaction_token=self._headers.get("X-Kronos-Token"),
                )
            raise KronosClientError(
                "Kronos service is not ready: expected health status 'ok'",
                category=KronosErrorCategory.TRANSPORT,
                code=KronosErrorCode.SERVICE_UNAVAILABLE,
                raw_response=response,
                redaction_token=self._headers.get("X-Kronos-Token"),
            )

        raw_model = response.get("model")
        if raw_model is None:
            raise KronosClientError(
                "Kronos health response is missing model",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=self._headers.get("X-Kronos-Token"),
            )
        try:
            normalized_model = _normalize_model_name(raw_model)
        except KronosClientError as exc:
            raise KronosClientError(
                "Kronos health response has unsupported model",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=self._headers.get("X-Kronos-Token"),
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
                raw_response=_complete_raw_response(health),
                redaction_token=self._headers.get("X-Kronos-Token"),
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
        _validate_prediction_response(
            result,
            expected_horizon=len(snapshot.future_timestamps),
            requested_sample_count=sample_count,
            redaction_token=self._headers.get("X-Kronos-Token"),
        )
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
                f"Kronos {path} request timed out",
                category=KronosErrorCategory.TIMEOUT,
                code=KronosErrorCode.TIMEOUT,
            ) from exc
        except TimeoutError as exc:
            raise KronosClientError(
                f"Kronos {path} request timed out",
                category=KronosErrorCategory.TIMEOUT,
                code=KronosErrorCode.TIMEOUT,
            ) from exc
        except requests.RequestException as exc:
            raise KronosClientError(
                f"Kronos {path} request failed",
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
            structured_response = _try_clone_structured_response(
                response,
            )
            if (
                path == "/v1/predict"
                and status_code == 502
                and isinstance(structured_response, Mapping)
                and structured_response.get("status") == "failed"
            ):
                raise KronosClientError(
                    "Kronos /v1/predict remote model failure (HTTP 502)",
                    category=KronosErrorCategory.MODEL,
                    code=KronosErrorCode.MODEL_ERROR,
                    status_code=status_code,
                    raw_response=structured_response,
                    redaction_token=self._headers.get("X-Kronos-Token"),
                )
            raise KronosClientError(
                f"Kronos {path} returned HTTP {status_code}",
                category=KronosErrorCategory.HTTP,
                code=KronosErrorCode.HTTP_ERROR,
                status_code=status_code,
                raw_response=structured_response,
                raw_body_excerpt=(
                    None
                    if structured_response is not None
                    else _bounded_raw_body_excerpt(
                        getattr(response, "text", None),
                        token=self._headers.get("X-Kronos-Token"),
                    )
                ),
                redaction_token=self._headers.get("X-Kronos-Token"),
            )

        try:
            raw_response = response.json()
        except (AttributeError, TypeError, ValueError) as exc:
            raise KronosClientError(
                f"Kronos {path} returned malformed JSON",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.MALFORMED_JSON,
                raw_body_excerpt=_bounded_raw_body_excerpt(
                    getattr(response, "text", None),
                    token=self._headers.get("X-Kronos-Token"),
                ),
                redaction_token=self._headers.get("X-Kronos-Token"),
            ) from exc

        try:
            normalized_response = _clone_json_value(raw_response)
        except (TypeError, ValueError) as exc:
            raise KronosClientError(
                f"Kronos {path} returned invalid JSON: {exc}",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_body_excerpt=_bounded_raw_body_excerpt(
                    getattr(response, "text", None),
                    token=self._headers.get("X-Kronos-Token"),
                ),
                redaction_token=self._headers.get("X-Kronos-Token"),
            ) from exc
        if not isinstance(normalized_response, dict):
            raise KronosClientError(
                f"Kronos {path} response must be a JSON object",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_body_excerpt=_bounded_raw_body_excerpt(
                    getattr(response, "text", None),
                    token=self._headers.get("X-Kronos-Token"),
                ),
                redaction_token=self._headers.get("X-Kronos-Token"),
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


def _validate_prediction_response(
    response: dict[str, Any],
    *,
    expected_horizon: int,
    requested_sample_count: int,
    redaction_token: str | None,
) -> None:
    status = response.get("status")
    if not isinstance(status, str):
        raise KronosClientError(
            "Kronos prediction response has an invalid status",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
            redaction_token=redaction_token,
        )
    if status in _PREDICTION_FAILURE_STATUSES:
        raise KronosClientError(
            "Kronos prediction response did not succeed",
            category=KronosErrorCategory.MODEL,
            code=KronosErrorCode.MODEL_ERROR,
            raw_response=response,
            redaction_token=redaction_token,
        )
    if status not in _PREDICTION_SUCCESS_STATUSES:
        raise KronosClientError(
            "Kronos prediction response has an unknown status",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
            redaction_token=redaction_token,
        )

    daily, result = _extract_daily_forecast(response)
    if not isinstance(daily, Mapping) or not daily:
        raise KronosClientError(
            "Kronos prediction response has no daily forecast data",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
            redaction_token=redaction_token,
        )
    daily_status = daily.get("status")
    if "status" in daily and not isinstance(daily_status, str):
        raise KronosClientError(
            "Kronos prediction response daily status is invalid",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
            redaction_token=redaction_token,
        )
    if isinstance(daily_status, str) and daily_status in _DAILY_FAILURE_STATUSES:
        raise KronosClientError(
            "Kronos prediction response daily forecast is unavailable",
            category=KronosErrorCategory.MODEL,
            code=KronosErrorCode.MODEL_ERROR,
            raw_response=response,
            redaction_token=redaction_token,
        )
    if isinstance(daily_status, str) and daily_status not in {
        "ok",
        "partial",
        "complete",
        "succeeded",
    }:
        raise KronosClientError(
            "Kronos prediction response daily status is unknown",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
            redaction_token=redaction_token,
        )
    if daily.get("unavailable") is True or daily.get("error") is not None:
        raise KronosClientError(
            "Kronos prediction response daily forecast is unavailable",
            category=KronosErrorCategory.MODEL,
            code=KronosErrorCode.MODEL_ERROR,
            raw_response=response,
            redaction_token=redaction_token,
        )

    quantiles = _find_daily_quantiles(daily)
    if quantiles is None:
        raise KronosClientError(
            "Kronos prediction response has no supported daily quantiles",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
            redaction_token=redaction_token,
        )

    quantile_values: dict[str, list[Any]] = {}
    for quantile_name in ("p10", "p50", "p90"):
        values = quantiles.get(quantile_name)
        if not isinstance(values, (list, tuple)):
            raise KronosClientError(
                f"Kronos prediction response {quantile_name} must be a sequence",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=redaction_token,
            )
        if not values or len(values) != expected_horizon:
            raise KronosClientError(
                f"Kronos prediction response {quantile_name} has invalid horizon",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=redaction_token,
            )
        if any(not _is_finite_number(value) for value in values):
            raise KronosClientError(
                f"Kronos prediction response {quantile_name} has invalid values",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=redaction_token,
            )
        quantile_values[quantile_name] = list(values)

    for p10, p50, p90 in zip(
        quantile_values["p10"],
        quantile_values["p50"],
        quantile_values["p90"],
    ):
        if p10 > p50 or p50 > p90:
            raise KronosClientError(
                "Kronos prediction response quantiles are not ordered",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=redaction_token,
            )

    sample_count_fields = _response_fields(
        response,
        result,
        daily,
        field_name="sample_count",
    )
    if not sample_count_fields:
        raise KronosClientError(
            "Kronos prediction response is missing sample_count",
            category=KronosErrorCategory.PROTOCOL,
            code=KronosErrorCode.INVALID_RESPONSE,
            raw_response=response,
            redaction_token=redaction_token,
        )
    for location, value in sample_count_fields:
        if isinstance(value, bool) or not isinstance(value, int):
            raise KronosClientError(
                f"Kronos prediction response sample_count at {location} is invalid",
                category=KronosErrorCategory.PROTOCOL,
                code=KronosErrorCode.INVALID_RESPONSE,
                raw_response=response,
                redaction_token=redaction_token,
            )
        if value != requested_sample_count:
            raise KronosClientError(
                f"Kronos prediction response sample_count at {location} mismatches request",
                category=KronosErrorCategory.MODEL,
                code=KronosErrorCode.MODEL_ERROR,
                raw_response=response,
                redaction_token=redaction_token,
            )

    for field_name in ("horizon", "forecast_horizon"):
        for location, value in _response_fields(
            response,
            result,
            daily,
            field_name=field_name,
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise KronosClientError(
                    f"Kronos prediction response {field_name} at {location} is invalid",
                    category=KronosErrorCategory.PROTOCOL,
                    code=KronosErrorCode.INVALID_RESPONSE,
                    raw_response=response,
                    redaction_token=redaction_token,
                )
            if value != expected_horizon:
                raise KronosClientError(
                    f"Kronos prediction response {field_name} at {location} mismatches forecast",
                    category=KronosErrorCategory.MODEL,
                    code=KronosErrorCode.MODEL_ERROR,
                    raw_response=response,
                    redaction_token=redaction_token,
                )


def _extract_daily_forecast(
    response: Mapping[str, Any],
) -> tuple[Any, Mapping[str, Any]]:
    if "daily" in response:
        top_level_daily = response["daily"]
        result = response.get("result")
        return top_level_daily, result if isinstance(result, Mapping) else {}

    result = response.get("result")
    if isinstance(result, Mapping):
        return result.get("daily"), result
    return None, {}


def _find_daily_quantiles(daily: Mapping[str, Any]) -> Mapping[str, Any] | None:
    required = ("p10", "p50", "p90")
    if all(field_name in daily for field_name in required):
        return daily

    summary = daily.get("summary")
    if not isinstance(summary, Mapping):
        return None
    close = summary.get("close")
    if isinstance(close, Mapping) and all(
        field_name in close for field_name in required
    ):
        return close
    return None


def _response_fields(
    response: Mapping[str, Any],
    result: Mapping[str, Any],
    daily: Mapping[str, Any],
    *,
    field_name: str,
) -> list[tuple[str, Any]]:
    fields: list[tuple[str, Any]] = []
    for location, mapping in (
        ("response", response),
        ("result", result),
        ("daily", daily),
    ):
        if field_name in mapping:
            fields.append((location, mapping[field_name]))
    return fields


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


class _KronosResponse(dict[str, Any]):
    """Internal dict carrying the client-created raw-response slot metadata."""

    _raw_response_slot: str | None = None


def _clone_json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    cloned = _clone_json_value(value)
    if not isinstance(cloned, dict):  # pragma: no cover - type guard for callers.
        raise TypeError("expected a JSON object")
    return cloned


def _bounded_raw_body_excerpt(body: Any, *, token: str | None) -> str | None:
    if not isinstance(body, str):
        return None
    excerpt = body[:_MAX_RAW_BODY_SCAN].strip()
    if not excerpt:
        return None
    excerpt = _redact_sensitive_text(excerpt, token=token)
    if len(excerpt) > _MAX_RAW_BODY_EXCERPT:
        return excerpt[: _MAX_RAW_BODY_EXCERPT - 1] + "…"
    return excerpt


def _try_clone_structured_response(
    response: Any,
) -> dict[str, Any] | None:
    try:
        raw_response = response.json()
    except (AttributeError, TypeError, ValueError):
        return None
    try:
        cloned_response = _clone_json_value(raw_response)
    except (TypeError, ValueError):
        return None
    if not isinstance(cloned_response, dict):
        return None
    return cloned_response


def _redact_sensitive_json_value(value: Any, *, token: str | None) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):  # pragma: no cover - clone validates keys.
                continue
            if _is_sensitive_field_name(key):
                redacted[key] = _REDACTED
            else:
                redacted[key] = _redact_sensitive_json_value(item, token=token)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_json_value(item, token=token) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value, token=token)
    return value


def _is_sensitive_field_name(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(term in normalized for term in _SENSITIVE_FIELD_TERMS)


def _redact_sensitive_text(value: str, *, token: str | None) -> str:
    was_truncated = len(value) > _MAX_RAW_BODY_SCAN
    bounded_value = value[:_MAX_RAW_BODY_SCAN]
    redacted = _redact_sensitive_assignments(bounded_value)
    redacted = _redact_bearer_credentials(redacted)
    if token:
        redacted = re.sub(
            re.escape(token),
            _REDACTED,
            redacted,
            flags=re.IGNORECASE,
        )
    if was_truncated or len(redacted) > _MAX_RAW_BODY_SCAN:
        redacted = redacted[: _MAX_RAW_BODY_SCAN - len(_REDACTED)]
        redacted += _REDACTED
    return redacted


def _redact_sensitive_assignments(value: str) -> str:
    output: list[str] = []
    copy_start = 0
    index = 0
    while index < len(value):
        if not _is_potential_field_start(value, index):
            index += 1
            continue

        candidate = _scan_assignment_field(value, index)
        if candidate is None:
            index += 1
            continue

        field_name, field_end, separator_index = candidate
        if separator_index is None or not _is_sensitive_field_name(field_name):
            index = (
                separator_index + 1
                if separator_index is not None
                else max(field_end, index + 1)
            )
            continue

        value_start = separator_index + 1
        while value_start < len(value) and value[value_start] in " \t":
            value_start += 1
        if (
            value_start >= len(value)
            or value[value_start] in _SAFE_UNQUOTED_VALUE_DELIMITERS
        ):
            index = max(value_start, index + 1)
            continue

        if value[value_start] in "\"'":
            value_end = len(value)
        else:
            value_end = _scan_unquoted_value_end(value, value_start)
        if value_end <= value_start:
            index = value_start + 1
            continue

        output.append(value[copy_start:value_start])
        output.append(_REDACTED)
        copy_start = value_end
        index = value_end

    if not output:
        return value
    output.append(value[copy_start:])
    return "".join(output)


def _redact_bearer_credentials(value: str) -> str:
    output: list[str] = []
    copy_start = 0
    index = 0
    while index < len(value):
        bearer_value = _scan_bearer_value(value, index)
        if bearer_value is None:
            index += 1
            continue

        value_start, value_end = bearer_value
        output.append(value[copy_start:value_start])
        output.append(_REDACTED)
        copy_start = value_end
        index = value_end

    if not output:
        return value
    output.append(value[copy_start:])
    return "".join(output)


def _is_potential_field_start(value: str, index: int) -> bool:
    character = value[index]
    if not (character.isalpha() or character == "_"):
        return False
    if index == 0:
        return True
    previous = value[index - 1]
    return not (previous.isalnum() or previous in "_.-")


def _scan_assignment_field(
    value: str,
    start: int,
) -> tuple[str, int, int | None] | None:
    if not _is_potential_field_start(value, start):
        return None

    field_end = start
    while (
        field_end < len(value)
        and field_end - start < _MAX_ASSIGNMENT_FIELD_LENGTH
        and (
            value[field_end].isalnum()
            or value[field_end] in "_.- \t"
        )
    ):
        field_end += 1

    if field_end == start:
        return None

    field_name = value[start:field_end].strip(" \t")
    if not field_name:
        return None

    separator_end = field_end
    while separator_end < len(value) and value[separator_end] in " \t\"'":
        separator_end += 1
    if separator_end >= len(value) or value[separator_end] not in ":=":
        return field_name, field_end, None
    return field_name, field_end, separator_end


def _scan_bearer_value(value: str, start: int) -> tuple[int, int] | None:
    bearer = "bearer"
    if value[start : start + len(bearer)].lower() != bearer:
        return None
    if start > 0 and (
        value[start - 1].isalnum() or value[start - 1] in "_.-"
    ):
        return None

    separator_end = start + len(bearer)
    if separator_end >= len(value) or not value[separator_end].isspace():
        return None
    value_start = separator_end
    while value_start < len(value) and value[value_start] in " \t":
        value_start += 1
    if value_start >= len(value):
        return None

    if value[value_start] in "\"'":
        return value_start, len(value)
    value_end = _scan_unquoted_value_end(value, value_start)
    if value_end <= value_start:
        return None
    return value_start, value_end


def _scan_unquoted_value_end(value: str, start: int) -> int:
    index = start
    while index < len(value) and value[index] not in _SAFE_UNQUOTED_VALUE_DELIMITERS:
        index += 1
    return index


def _complete_raw_response(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    client_slot = getattr(payload, "_raw_response_slot", None)
    if isinstance(client_slot, str):
        complete_response = payload.get(client_slot)
        if isinstance(complete_response, Mapping):
            return _clone_json_object(complete_response)

    collision_slots: list[tuple[int, Any]] = []
    for key, value in payload.items():
        if not isinstance(key, str) or key.lstrip("_") != "kronos_raw_response":
            continue
        leading_underscores = len(key) - len(key.lstrip("_"))
        if leading_underscores:
            collision_slots.append((leading_underscores, value))
    if collision_slots:
        _, complete_response = max(collision_slots, key=lambda item: item[0])
        if isinstance(complete_response, Mapping):
            return _clone_json_object(complete_response)

    raw_response = payload.get("raw_response")
    if isinstance(raw_response, Mapping):
        return _clone_json_object(raw_response)
    return None


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
    normalized = _KronosResponse(_clone_json_object(payload))
    complete_response = payload if raw_response is None else raw_response
    if "raw_response" not in normalized:
        normalized["raw_response"] = _clone_json_value(complete_response)
        normalized._raw_response_slot = "raw_response"
        return normalized

    fallback_key = "_kronos_raw_response"
    while fallback_key in normalized:
        fallback_key = f"_{fallback_key}"
    normalized[fallback_key] = _clone_json_value(complete_response)
    normalized._raw_response_slot = fallback_key
    return normalized


__all__ = [
    "KronosClient",
    "KronosClientError",
    "KronosErrorCategory",
    "KronosErrorCode",
]
