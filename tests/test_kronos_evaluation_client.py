import json
import sys
import types

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


def test_predict_daily_posts_exact_frozen_snapshot_payload_and_token_header():
    snapshot = make_snapshot()
    prediction = {
        "status": "succeeded",
        "result": {"daily": {"p50": [1.0]}},
    }
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

    assert result["status"] == "succeeded"
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
        prediction={"status": "succeeded", "result": {"daily": {"p50": [1.0]}}},
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    client.predict_daily(make_snapshot(), model="small")

    assert session.requests[-1]["json"]["seed"] == DEFAULT_KRONOS_SEED


def test_predict_daily_posts_explicit_base_model():
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-base"},
        prediction={"status": "succeeded", "result": {"daily": {"p50": [1.0]}}},
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    result = client.predict_daily(make_snapshot(), model="base", seed=7)

    assert result["status"] == "succeeded"
    assert session.requests[-1]["method"] == "POST"
    assert session.requests[-1]["json"]["model"] == "base"
    assert session.requests[-1]["json"]["seed"] == 7


@pytest.mark.parametrize("sample_count", [0, 101, True, 1.5, "20", None])
def test_predict_daily_rejects_sample_count_outside_integer_range(sample_count):
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction={"status": "succeeded", "result": {"daily": {"p50": [1.0]}}},
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
        prediction={"status": "succeeded", "result": {"daily": {"p50": [1.0]}}},
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
        prediction={"status": "succeeded", "result": {"daily": {"p50": [1.0]}}},
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


def test_prediction_preserves_upstream_raw_response_collision_safely():
    prediction = {
        "status": "succeeded",
        "result": {"daily": {"p50": [1.0]}},
        "raw_response": {"upstream": "must remain"},
    }
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        prediction=prediction,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    result = client.predict_daily(make_snapshot(), model="small", seed=7)

    assert result["raw_response"] == prediction["raw_response"]
    assert result["_kronos_raw_response"] == prediction
