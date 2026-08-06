import os
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest


try:
    import requests
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    requests_stub.RequestException = RequestException
    requests_stub.Timeout = Timeout
    requests_stub.Session = object
    sys.modules["requests"] = requests_stub
    import requests


try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    psycopg_stub = types.ModuleType("psycopg")
    psycopg_stub.Connection = object
    psycopg_stub.connect = lambda *args, **kwargs: None
    psycopg_rows_stub = types.ModuleType("psycopg.rows")
    psycopg_rows_stub.dict_row = object()
    psycopg_stub.rows = psycopg_rows_stub
    sys.modules["psycopg"] = psycopg_stub
    sys.modules["psycopg.rows"] = psycopg_rows_stub


from stock_research.kronos_evaluation_client import (  # noqa: E402
    KronosClient,
    KronosClientError,
    KronosErrorCategory,
    KronosErrorCode,
)
from stock_research import kronos_evaluation_client as client_module  # noqa: E402
from stock_research.kronos_evaluation_types import (  # noqa: E402
    DEFAULT_KRONOS_SEED,
    RollingSnapshot,
    canonical_json_fingerprint,
)


class FakeResponse:
    def __init__(
        self,
        payload=None,
        *,
        status_code=200,
        text=None,
        json_error=None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else repr(payload)
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class TextAccessForbiddenResponse(FakeResponse):
    def __init__(self, payload, *, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.text_accesses = 0

    @property
    def text(self):
        self.text_accesses += 1
        raise AssertionError("successful responses must not read response.text")

    def json(self):
        return self._payload


class SliceTrackingText(str):
    def __new__(cls, value):
        instance = super().__new__(cls, value)
        instance.slice_stops = []
        return instance

    def __getitem__(self, item):
        if isinstance(item, slice):
            self.slice_stops.append(item.stop)
        return super().__getitem__(item)


class FakeSession:
    def __init__(
        self,
        *,
        health=None,
        prediction=None,
        health_response=None,
        prediction_response=None,
        get_exception=None,
        post_exception=None,
    ):
        self.health_response = health_response or FakeResponse(health)
        self.prediction_response = prediction_response or FakeResponse(prediction)
        self.get_exception = get_exception
        self.post_exception = post_exception
        self.requests = []
        self.closed = False

    def close(self):
        self.closed = True

    def get(self, url, *, headers, timeout):
        self.requests.append(
            {
                "method": "GET",
                "url": url,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if self.get_exception is not None:
            raise self.get_exception
        return self.health_response

    def post(self, url, *, headers, json, timeout):
        self.requests.append(
            {
                "method": "POST",
                "url": url,
                "headers": dict(headers),
                "json": json,
                "timeout": timeout,
            }
        )
        if self.post_exception is not None:
            raise self.post_exception
        return self.prediction_response


def make_snapshot():
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
    return RollingSnapshot(
        asset_id="CN:SH:600418",
        origin_date="2025-01-03",
        history=history,
        future_timestamps=("2025-01-06", "2025-01-07"),
        realized=(),
        input_fingerprint=canonical_json_fingerprint(
            {
                "asset_id": "CN:SH:600418",
                "origin_date": "2025-01-03",
                "history": history,
            }
        ),
        status="ready",
    )


def make_prediction_response(
    *,
    sample_count=20,
    sample_count_location="service",
    include_sample_count=True,
    horizon=2,
    include_horizon=True,
    layout="direct",
    envelope="service",
    status=None,
    quantiles=None,
):
    quantiles = quantiles or {
        "p10": [1.0, 1.1],
        "p50": [1.5, 1.6],
        "p90": [2.0, 2.1],
    }
    quantiles = {key: list(values) for key, values in quantiles.items()}
    if layout == "direct":
        daily = quantiles
    elif layout == "summary_close":
        daily = {"summary": {"close": quantiles}}
    else:
        raise ValueError(f"unsupported test layout: {layout}")

    if include_horizon:
        daily["horizon"] = horizon

    response_sample_count = None
    if envelope == "service":
        response = {
            "status": status or "partial",
            "daily": daily,
            "intraday": None,
            "aggregated": {},
            "diagnostics": [],
        }
        if include_sample_count:
            if sample_count_location in {"service", "response"}:
                response_sample_count = sample_count
            if sample_count_location in {"service", "daily"}:
                daily["sample_count"] = sample_count
            if sample_count_location == "result":
                raise ValueError("result sample_count requires result envelope")
    elif envelope == "result":
        result = {"daily": daily}
        response = {"status": status or "succeeded", "result": result}
        if include_sample_count:
            if sample_count_location in {"service", "response"}:
                response_sample_count = sample_count
            if sample_count_location in {"service", "daily"}:
                daily["sample_count"] = sample_count
            if sample_count_location == "result":
                result["sample_count"] = sample_count
    else:
        raise ValueError(f"unsupported test envelope: {envelope}")

    if response_sample_count is not None:
        response["sample_count"] = response_sample_count
    return response


def test_predict_daily_posts_exact_frozen_snapshot_payload_and_token_header():
    snapshot = make_snapshot()
    prediction = make_prediction_response()
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient(
        "http://kronos.test/",
        token="secret",
        timeout=12.5,
        session=session,
    )

    result = client.predict_daily(snapshot, model="small", sample_count=20, seed=7)

    assert result["status"] == "partial"
    assert result["raw_response"] == prediction
    assert session.requests[0] == {
        "method": "GET",
        "url": "http://kronos.test/health",
        "headers": {"X-Kronos-Token": "secret"},
        "timeout": 12.5,
    }
    request = session.requests[-1]
    assert request["method"] == "POST"
    assert request["url"] == "http://kronos.test/v1/predict"
    assert request["headers"] == {"X-Kronos-Token": "secret"}
    assert request["timeout"] == 12.5
    assert request["json"] == {
        "model": "small",
        "sample_count": 20,
        "seed": 7,
        "daily": {
            "history": [dict(row) for row in snapshot.history],
            "future_timestamps": list(snapshot.future_timestamps),
        },
    }
    assert json.loads(json.dumps(request["json"], sort_keys=True)) == request["json"]
    assert request["json"]["daily"]["history"] is not snapshot.history
    assert request["json"]["daily"]["history"][0] is not snapshot.history[0]

    request["json"]["daily"]["history"][0]["close"] = -1.0
    assert snapshot.history[0]["close"] == 102.0


@pytest.mark.parametrize(
    ("active_model", "expected_model"),
    [
        ("Kronos-small", "small"),
        ("small", "small"),
        ("Kronos-base", "base"),
        ("base", "base"),
    ],
)
def test_health_and_assert_model_normalize_active_model_names(
    active_model, expected_model
):
    session = FakeSession(health={"status": "ok", "model": active_model})
    client = KronosClient("http://kronos.test", token="secret", session=session)

    health = client.assert_model(expected_model)

    assert health["model"] == expected_model
    assert health["raw_response"]["model"] == active_model
    assert len(session.requests) == 1


@pytest.mark.parametrize(
    ("active_model", "requested_model"),
    [("Kronos-small", "base"), ("Kronos-base", "small")],
)
def test_model_mismatch_fails_closed_without_prediction_or_fallback(
    active_model, requested_model
):
    session = FakeSession(
        health={"status": "ok", "model": active_model},
        prediction={"status": "must not be sent"},
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError, match="model mismatch") as exc_info:
        client.predict_daily(make_snapshot(), model=requested_model)

    assert exc_info.value.category == KronosErrorCategory.MODEL
    assert exc_info.value.code == KronosErrorCode.MODEL_MISMATCH
    assert [request["method"] for request in session.requests] == ["GET"]


@pytest.mark.parametrize(
    ("health_response", "expected_message", "expected_category", "expected_code"),
    [
        (
            FakeResponse(
                {"error": "unavailable"},
                status_code=503,
                text="service unavailable",
            ),
            "HTTP 503",
            KronosErrorCategory.HTTP,
            KronosErrorCode.HTTP_ERROR,
        ),
        (
            FakeResponse(
                {"status": "ok", "model": "Kronos-small"},
                status_code=200,
                json_error=ValueError("bad json"),
                text="not json",
            ),
            "malformed JSON",
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.MALFORMED_JSON,
        ),
    ],
)
def test_health_reports_non_200_and_malformed_json(
    health_response, expected_message, expected_category, expected_code
):
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(health_response=health_response),
    )

    with pytest.raises(KronosClientError, match=expected_message) as exc_info:
        client.health()

    assert exc_info.value.category == expected_category
    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("health", "expected_category", "expected_code"),
    [
        (
            {"status": "degraded", "model": "Kronos-small"},
            KronosErrorCategory.TRANSPORT,
            KronosErrorCode.SERVICE_UNAVAILABLE,
        ),
        (
            {"status": "error", "model": "Kronos-small"},
            KronosErrorCategory.TRANSPORT,
            KronosErrorCode.SERVICE_UNAVAILABLE,
        ),
        (
            {"status": "unavailable", "model": "Kronos-small"},
            KronosErrorCategory.TRANSPORT,
            KronosErrorCode.SERVICE_UNAVAILABLE,
        ),
        (
            {"model": "Kronos-small"},
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.INVALID_RESPONSE,
        ),
        (
            {"status": 200, "model": "Kronos-small"},
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.INVALID_RESPONSE,
        ),
        (
            {"status": "mystery", "model": "Kronos-small"},
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.INVALID_RESPONSE,
        ),
    ],
)
def test_health_status_taxonomy_is_precise(
    health, expected_category, expected_code
):
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(health=health),
    )

    with pytest.raises(KronosClientError) as exc_info:
        client.health()

    assert exc_info.value.category == expected_category
    assert exc_info.value.code == expected_code


def test_health_semantic_error_redacts_configured_token_echo():
    token = "secret-token"
    health = {
        "status": "degraded",
        "model": "Kronos-small",
        "echo": token,
    }
    client = KronosClient(
        "http://kronos.test",
        token=token,
        session=FakeSession(health=health),
    )

    with pytest.raises(KronosClientError) as exc_info:
        client.health()

    assert exc_info.value.raw_response["echo"] == "[REDACTED]"
    assert token not in json.dumps(exc_info.value.raw_response)


@pytest.mark.parametrize(
    ("prediction_response", "expected_message", "expected_category", "expected_code"),
    [
        (
            FakeResponse(
                {"error": "bad request"},
                status_code=422,
                text="bad request",
            ),
            "HTTP 422",
            KronosErrorCategory.HTTP,
            KronosErrorCode.HTTP_ERROR,
        ),
        (
            FakeResponse(
                {"status": "succeeded"},
                status_code=200,
                json_error=ValueError("bad json"),
                text="not json",
            ),
            "malformed JSON",
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.MALFORMED_JSON,
        ),
    ],
)
def test_prediction_reports_non_200_and_malformed_json(
    prediction_response, expected_message, expected_category, expected_code
):
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=prediction_response,
        ),
    )

    with pytest.raises(KronosClientError, match=expected_message) as exc_info:
        client.predict_daily(make_snapshot(), model="small")

    assert exc_info.value.category == expected_category
    assert exc_info.value.code == expected_code


def test_non_200_preserves_structured_json_without_leaking_upstream_text():
    structured_error = {
        "error": "invalid request",
        "request_id": "req-422",
        "token": "server-token-value",
        "details": {
            "authorization": "Bearer upstream-auth-value",
            "api_key": "upstream-api-key-value",
            "nested": {
                "password": "upstream-password-value",
                "secret": "upstream-secret-value",
                "diagnostic": "keep this diagnostic",
            },
        },
    }
    response = FakeResponse(
        structured_error,
        status_code=422,
        text="Authorization: Bearer secret-token " + ("upstream detail " * 50),
    )
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=response,
        ),
    )

    with pytest.raises(KronosClientError, match="HTTP 422") as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.status_code == 422
    assert exc_info.value.raw_response["error"] == "invalid request"
    assert exc_info.value.raw_response["request_id"] == "req-422"
    assert exc_info.value.raw_response["token"] == "[REDACTED]"
    assert exc_info.value.raw_response["details"]["authorization"] == "[REDACTED]"
    assert exc_info.value.raw_response["details"]["api_key"] == "[REDACTED]"
    assert exc_info.value.raw_response["details"]["nested"]["password"] == "[REDACTED]"
    assert exc_info.value.raw_response["details"]["nested"]["secret"] == "[REDACTED]"
    assert (
        exc_info.value.raw_response["details"]["nested"]["diagnostic"]
        == "keep this diagnostic"
    )
    assert "server-token-value" not in json.dumps(exc_info.value.raw_response)
    assert "upstream-auth-value" not in json.dumps(exc_info.value.raw_response)
    assert exc_info.value.raw_body_excerpt is None
    assert "secret-token" not in str(exc_info.value)
    assert "upstream detail" not in str(exc_info.value)


def test_non_200_preserves_bounded_redacted_excerpt_for_non_json_body():
    body = "<html>gateway failure token=secret-token " + ("upstream detail " * 100)
    response = FakeResponse(
        None,
        status_code=502,
        text=body,
    )
    client = KronosClient(
        "http://kronos.test",
        token="secret-token",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=response,
        ),
    )

    with pytest.raises(KronosClientError, match="HTTP 502") as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.raw_response is None
    assert exc_info.value.raw_body_excerpt
    assert len(exc_info.value.raw_body_excerpt) <= 512
    assert "secret-token" not in exc_info.value.raw_body_excerpt
    assert "secret-token" not in str(exc_info.value)
    assert "upstream detail" not in str(exc_info.value)


def test_plaintext_excerpt_redacts_all_sensitive_key_value_forms():
    sensitive_values = {
        "private_key": "private-key-value",
        "secret_key": "secret-key-value",
        "passphrase": "passphrase-value",
        "privatekey": "privatekey-value",
        "accesskey": "accesskey-value",
        "client_secret": "client-secret-value",
        "refresh_token": "refresh-token-value",
    }
    body = "diagnostic=keep " + " ".join(
        f"{key}={value}" for key, value in sensitive_values.items()
    )
    response = FakeResponse(None, status_code=502, text=body)
    client = KronosClient(
        "http://kronos.test",
        token="configured-token",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=response,
        ),
    )

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small")

    assert "diagnostic=keep" in exc_info.value.raw_body_excerpt
    for value in sensitive_values.values():
        assert value not in exc_info.value.raw_body_excerpt


def test_nested_plaintext_values_are_redacted_in_structured_errors():
    nested_text = (
        'private_key="private-key-value" '
        "secret_key: 'secret-key-value' "
        "passphrase=passphrase-value "
        "privatekey=privatekey-value "
        "accesskey=accesskey-value"
    )
    structured_error = {
        "error": "invalid request",
        "details": {
            "message": nested_text,
            "items": [{"diagnostic": nested_text}],
            "ordinary": "keep this diagnostic",
        },
    }
    response = FakeResponse(structured_error, status_code=422)
    client = KronosClient(
        "http://kronos.test",
        token="configured-token",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=response,
        ),
    )

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small")

    raw_response = exc_info.value.raw_response
    assert raw_response["details"]["ordinary"] == "keep this diagnostic"
    serialized_response = json.dumps(raw_response)
    for value in (
        "private-key-value",
        "secret-key-value",
        "passphrase-value",
        "privatekey-value",
        "accesskey-value",
    ):
        assert value not in serialized_response


def test_successful_200_response_does_not_read_response_text():
    response = TextAccessForbiddenResponse(make_prediction_response())
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction_response=response,
    )
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=session,
    )

    client.predict_daily(make_snapshot(), model="small")

    assert response.text_accesses == 0


def test_non_json_excerpt_bounds_input_before_redaction_scan():
    body = SliceTrackingText("gateway failure " + ("upstream detail " * 10000))
    response = FakeResponse(None, status_code=502, text=body)
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=response,
        ),
    )

    with pytest.raises(KronosClientError):
        client.predict_daily(make_snapshot(), model="small")

    assert body.slice_stops
    assert body.slice_stops[0] < len(body)
    assert body.slice_stops[0] <= 4096


def test_http_200_malformed_json_preserves_bounded_redacted_excerpt():
    body = "gateway body echo=secret-token " + ("upstream detail " * 100)
    response = FakeResponse(
        {"status": "ok", "model": "Kronos-small"},
        status_code=200,
        json_error=ValueError("malformed JSON"),
        text=body,
    )
    client = KronosClient(
        "http://kronos.test",
        token="secret-token",
        session=FakeSession(health_response=response),
    )

    with pytest.raises(KronosClientError, match="malformed JSON") as exc_info:
        client.health()

    assert exc_info.value.raw_body_excerpt
    assert len(exc_info.value.raw_body_excerpt) <= 512
    assert "secret-token" not in exc_info.value.raw_body_excerpt
    assert "secret-token" not in str(exc_info.value)
    assert "upstream detail" not in str(exc_info.value)


def test_structured_502_failed_prediction_is_classified_as_model_error():
    structured_failure = {
        "status": "failed",
        "message": "CUDA inference failed",
        "diagnostics": {"token": "remote-token", "device": "cuda:0"},
    }
    response = FakeResponse(structured_failure, status_code=502)
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=response,
        ),
    )

    with pytest.raises(KronosClientError, match="model failure") as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == KronosErrorCategory.MODEL
    assert exc_info.value.code == KronosErrorCode.MODEL_ERROR
    assert exc_info.value.status_code == 502
    assert exc_info.value.raw_response["status"] == "failed"
    assert exc_info.value.raw_response["diagnostics"]["token"] == "[REDACTED]"
    assert exc_info.value.raw_body_excerpt is None


def test_generic_structured_502_remains_an_http_error():
    response = FakeResponse(
        {"status": "bad_gateway", "message": "gateway unavailable"},
        status_code=502,
    )
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=response,
        ),
    )

    with pytest.raises(KronosClientError, match="HTTP 502") as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == KronosErrorCategory.HTTP
    assert exc_info.value.code == KronosErrorCode.HTTP_ERROR
    assert exc_info.value.status_code == 502


@pytest.mark.parametrize(
    ("method", "exception", "expected_message", "expected_category", "expected_code"),
    [
        (
            "get",
            requests.Timeout("timed out"),
            "timed out",
            KronosErrorCategory.TIMEOUT,
            KronosErrorCode.TIMEOUT,
        ),
        (
            "post",
            requests.RequestException("connection reset"),
            "request failed",
            KronosErrorCategory.TRANSPORT,
            KronosErrorCode.TRANSPORT_ERROR,
        ),
    ],
)
def test_request_errors_are_reported_without_fallback(
    method, exception, expected_message, expected_category, expected_code
):
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        get_exception=exception if method == "get" else None,
        post_exception=exception if method == "post" else None,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError, match=expected_message) as exc_info:
        if method == "get":
            client.health()
        else:
            client.predict_daily(make_snapshot(), model="small")

    assert exc_info.value.category == expected_category
    assert exc_info.value.code == expected_code


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_token_is_rejected_before_any_request(token):
    with pytest.raises(KronosClientError, match="token") as exc_info:
        KronosClient("http://kronos.test", token=token, session=FakeSession())

    assert exc_info.value.category == KronosErrorCategory.VALIDATION
    assert exc_info.value.code == KronosErrorCode.TOKEN_REQUIRED


@pytest.mark.parametrize("invalid_payload", [None, [], "not an object"])
def test_invalid_json_object_response_is_rejected(invalid_payload):
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(
            health_response=FakeResponse(
                {"status": "ok", "model": "Kronos-small"}
            ),
            prediction_response=FakeResponse(invalid_payload),
        ),
    )

    with pytest.raises(KronosClientError, match="JSON object") as exc_info:
        client.predict_daily(make_snapshot(), model="small")

    assert exc_info.value.category == KronosErrorCategory.PROTOCOL
    assert exc_info.value.code == KronosErrorCode.INVALID_RESPONSE


def test_unknown_or_missing_health_model_fails_closed():
    for health in ({"status": "ok"}, {"status": "ok", "model": "Kronos-large"}):
        client = KronosClient(
            "http://kronos.test",
            token="secret",
            session=FakeSession(health=health),
        )

        with pytest.raises(KronosClientError, match="model") as exc_info:
            client.health()

        assert exc_info.value.category == KronosErrorCategory.PROTOCOL
        assert exc_info.value.code == KronosErrorCode.INVALID_RESPONSE


def test_predict_daily_uses_the_canonical_seed_when_omitted():
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=make_prediction_response(),
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    client.predict_daily(make_snapshot(), model="small")

    assert session.requests[-1]["json"]["seed"] == DEFAULT_KRONOS_SEED


def test_predict_daily_posts_explicit_base_model():
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-base"},
        prediction=make_prediction_response(),
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    result = client.predict_daily(make_snapshot(), model="base", seed=7)

    assert result["status"] == "partial"
    assert session.requests[-1]["method"] == "POST"
    assert session.requests[-1]["json"]["model"] == "base"
    assert session.requests[-1]["json"]["seed"] == 7


@pytest.mark.parametrize("sample_count", [0, 101, True, 1.5, "20", None])
def test_predict_daily_rejects_sample_count_outside_integer_range(sample_count):
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=make_prediction_response(),
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError, match="sample_count") as exc_info:
        client.predict_daily(
            make_snapshot(),
            model="small",
            sample_count=sample_count,
            seed=7,
        )

    assert exc_info.value.category == KronosErrorCategory.VALIDATION
    assert exc_info.value.code == KronosErrorCode.INVALID_ARGUMENT
    assert session.requests == []


@pytest.mark.parametrize("sample_count", [1, 100])
def test_predict_daily_accepts_sample_count_boundaries(sample_count):
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=make_prediction_response(sample_count=sample_count),
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    client.predict_daily(
        make_snapshot(),
        model="small",
        sample_count=sample_count,
        seed=7,
    )

    assert session.requests[-1]["json"]["sample_count"] == sample_count


def test_health_requires_exact_ok_status_and_blocks_prediction_when_unavailable():
    session = FakeSession(
        health={"status": "error", "model": "Kronos-small"},
        prediction=make_prediction_response(),
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError, match="not ready") as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == KronosErrorCategory.TRANSPORT
    assert exc_info.value.code == KronosErrorCode.SERVICE_UNAVAILABLE
    assert [request["method"] for request in session.requests] == ["GET"]


@pytest.mark.parametrize(
    ("prediction", "expected_category", "expected_code"),
    [
        (
            {"status": "error", "message": "model failed"},
            KronosErrorCategory.MODEL,
            KronosErrorCode.MODEL_ERROR,
        ),
        (
            {},
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.INVALID_RESPONSE,
        ),
        (
            {"status": "succeeded", "result": {}},
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.INVALID_RESPONSE,
        ),
        (
            {"status": "succeeded", "result": {"daily": []}},
            KronosErrorCategory.PROTOCOL,
            KronosErrorCode.INVALID_RESPONSE,
        ),
    ],
)
def test_prediction_requires_semantically_successful_daily_result(
    prediction, expected_category, expected_code
):
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError, match="prediction response") as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == expected_category
    assert exc_info.value.code == expected_code
    assert exc_info.value.raw_response == prediction


@pytest.mark.parametrize(
    ("status", "expected_category", "expected_code"),
    [
        ("failed", KronosErrorCategory.MODEL, KronosErrorCode.MODEL_ERROR),
        ("error", KronosErrorCategory.MODEL, KronosErrorCode.MODEL_ERROR),
        ("unknown", KronosErrorCategory.PROTOCOL, KronosErrorCode.INVALID_RESPONSE),
        (123, KronosErrorCategory.PROTOCOL, KronosErrorCode.INVALID_RESPONSE),
        (None, KronosErrorCategory.PROTOCOL, KronosErrorCode.INVALID_RESPONSE),
    ],
)
def test_prediction_status_classification_fails_closed(
    status, expected_category, expected_code
):
    prediction = make_prediction_response()
    prediction["status"] = status
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == expected_category
    assert exc_info.value.code == expected_code
    assert exc_info.value.raw_response == prediction


def test_prediction_semantic_error_redacts_configured_token_echo():
    token = "secret-token"
    prediction = {
        "status": "error",
        "message": "model failed",
        "echo": token,
    }
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token=token, session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == KronosErrorCategory.MODEL
    assert exc_info.value.code == KronosErrorCode.MODEL_ERROR
    assert exc_info.value.raw_response["echo"] == "[REDACTED]"
    assert token not in json.dumps(exc_info.value.raw_response)


def test_prediction_rejects_unknown_daily_status_as_protocol_error():
    prediction = make_prediction_response()
    prediction["daily"]["status"] = "mystery"
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == KronosErrorCategory.PROTOCOL
    assert exc_info.value.code == KronosErrorCode.INVALID_RESPONSE
    assert exc_info.value.raw_response == prediction


@pytest.mark.parametrize("status", ["partial", "complete"])
def test_prediction_accepts_service_daily_envelope_statuses(status):
    prediction = make_prediction_response(status=status)
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    result = client.predict_daily(make_snapshot(), model="small", seed=7)

    assert result["status"] == status
    assert result["raw_response"] == prediction


@pytest.mark.parametrize("status", ["failed", "error"])
def test_prediction_rejects_failed_service_envelope_statuses(status):
    prediction = make_prediction_response(status=status)
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == KronosErrorCategory.MODEL
    assert exc_info.value.code == KronosErrorCode.MODEL_ERROR
    assert exc_info.value.raw_response == prediction


def test_prediction_rejects_explicit_null_daily_before_legacy_fallback():
    compatibility_response = make_prediction_response(
        envelope="result",
        sample_count_location="result",
    )
    prediction = {
        "status": "partial",
        "sample_count": 20,
        "daily": None,
        "result": compatibility_response["result"],
        "intraday": None,
    }
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category == KronosErrorCategory.PROTOCOL
    assert exc_info.value.code == KronosErrorCode.INVALID_RESPONSE
    assert exc_info.value.raw_response == prediction


@pytest.mark.parametrize("daily_status", ["error", "unavailable"])
def test_prediction_rejects_error_or_unavailable_daily_envelope(daily_status):
    prediction = {
        "status": "partial",
        "sample_count": 20,
        "daily": {"status": daily_status, "message": "daily failed"},
        "intraday": None,
    }
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category in {
        KronosErrorCategory.MODEL,
        KronosErrorCategory.PROTOCOL,
    }
    assert exc_info.value.code in {
        KronosErrorCode.MODEL_ERROR,
        KronosErrorCode.INVALID_RESPONSE,
    }
    assert exc_info.value.raw_response == prediction


def test_prediction_accepts_summary_close_quantile_layout():
    prediction = make_prediction_response(layout="summary_close")
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    result = client.predict_daily(make_snapshot(), model="small", seed=7)

    assert result["status"] == "partial"
    assert result["raw_response"] == prediction


@pytest.mark.parametrize("sample_count_location", ["response", "result", "daily"])
def test_prediction_accepts_sample_count_at_supported_locations(sample_count_location):
    prediction = make_prediction_response(
        sample_count_location=sample_count_location,
        envelope="result" if sample_count_location == "result" else "service",
    )
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    client.predict_daily(make_snapshot(), model="small", sample_count=20, seed=7)


def test_prediction_accepts_legacy_result_daily_compatibility_envelope():
    prediction = make_prediction_response(
        envelope="result",
        sample_count_location="result",
    )
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    result = client.predict_daily(make_snapshot(), model="small", seed=7)

    assert result["status"] == "succeeded"
    assert result["raw_response"] == prediction


@pytest.mark.parametrize(
    "prediction",
    [
        {
            "status": "succeeded",
            "result": {
                "daily": {"message": "not a forecast"}
            },
        },
        make_prediction_response(
            quantiles={
                "p10": [1.0, 1.1],
                "p50": [],
                "p90": [2.0, 2.1],
            }
        ),
        make_prediction_response(
            quantiles={
                "p10": [1.0, 1.1],
                "p50": [1.5, 1.6],
            }
        ),
        make_prediction_response(
            quantiles={
                "p10": [1.0],
                "p50": [1.5, 1.6],
                "p90": [2.0, 2.1],
            }
        ),
        make_prediction_response(
            quantiles={
                "p10": [1.0, 1.1],
                "p50": [1.5, float("nan")],
                "p90": [2.0, 2.1],
            }
        ),
        make_prediction_response(sample_count=19),
        make_prediction_response(horizon=3),
        make_prediction_response(include_sample_count=False),
    ],
)
def test_prediction_rejects_semantically_invalid_success_response(prediction):
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category in {
        KronosErrorCategory.MODEL,
        KronosErrorCategory.PROTOCOL,
    }
    assert exc_info.value.code in {
        KronosErrorCode.MODEL_ERROR,
        KronosErrorCode.INVALID_RESPONSE,
    }


def test_prediction_rejects_elementwise_quantile_ordering_violations():
    prediction = make_prediction_response(
        quantiles={
            "p10": [1.6, 1.1],
            "p50": [1.5, 1.6],
            "p90": [2.0, 2.1],
        }
    )
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="small", seed=7)

    assert exc_info.value.category in {
        KronosErrorCategory.MODEL,
        KronosErrorCategory.PROTOCOL,
    }
    assert exc_info.value.code in {
        KronosErrorCode.MODEL_ERROR,
        KronosErrorCode.INVALID_RESPONSE,
    }
    assert exc_info.value.raw_response == prediction


def test_prediction_accepts_missing_optional_horizon_field():
    prediction = make_prediction_response(include_horizon=False)
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    client.predict_daily(make_snapshot(), model="small", seed=7)


def test_model_mismatch_preserves_complete_health_response_on_raw_key_collision():
    health = {
        "status": "ok",
        "model": "Kronos-small",
        "raw_response": {"upstream": "nested value"},
    }
    session = FakeSession(
        health=health,
        prediction=make_prediction_response(),
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="base", seed=7)

    assert exc_info.value.code == KronosErrorCode.MODEL_MISMATCH
    assert exc_info.value.raw_response == health


def test_model_mismatch_prefers_client_raw_response_when_upstream_uses_reserved_key():
    health = {
        "status": "ok",
        "model": "Kronos-small",
        "_kronos_raw_response": {"upstream": "reserved-looking field"},
    }
    session = FakeSession(
        health=health,
        prediction=make_prediction_response(),
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError) as exc_info:
        client.predict_daily(make_snapshot(), model="base", seed=7)

    assert exc_info.value.code == KronosErrorCode.MODEL_MISMATCH
    assert exc_info.value.raw_response == health


def test_client_context_closes_only_an_internally_created_session(monkeypatch):
    created_session = FakeSession()
    monkeypatch.setattr(client_module.requests, "Session", lambda: created_session)

    with KronosClient("http://kronos.test", token="secret") as client:
        assert client.session is created_session

    assert created_session.closed is True


def test_client_does_not_close_an_injected_session():
    injected_session = FakeSession()

    with KronosClient(
        "http://kronos.test",
        token="secret",
        session=injected_session,
    ) as client:
        assert client.session is injected_session

    client.close()
    assert injected_session.closed is False


def test_client_import_chain_does_not_require_db_dependencies():
    source = """
import sys
import types

requests_stub = types.ModuleType('requests')
class RequestException(Exception):
    pass
class Timeout(RequestException):
    pass
requests_stub.RequestException = RequestException
requests_stub.Timeout = Timeout
requests_stub.Session = object
sys.modules['requests'] = requests_stub

import stock_research.kronos_evaluation_client

assert 'stock_research.db' not in sys.modules
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    completed = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr


def test_prediction_preserves_upstream_raw_response_collision_safely():
    prediction = make_prediction_response()
    prediction["raw_response"] = {"upstream": "must remain"}
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    result = client.predict_daily(make_snapshot(), model="small", seed=7)

    assert result["raw_response"] == prediction["raw_response"]
    assert result["_kronos_raw_response"] == prediction
