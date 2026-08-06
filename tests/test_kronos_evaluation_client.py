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
)
from stock_research.kronos_evaluation_types import (  # noqa: E402
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

    with pytest.raises(KronosClientError, match="model mismatch"):
        client.predict_daily(make_snapshot(), model=requested_model)

    assert [request["method"] for request in session.requests] == ["GET"]


@pytest.mark.parametrize(
    ("health_response", "expected_message"),
    [
        (
            FakeResponse(
                {"error": "unavailable"},
                status_code=503,
                text="service unavailable",
            ),
            "HTTP 503",
        ),
        (
            FakeResponse(
                {"status": "ok", "model": "Kronos-small"},
                status_code=200,
                json_error=ValueError("bad json"),
                text="not json",
            ),
            "malformed JSON",
        ),
    ],
)
def test_health_reports_non_200_and_malformed_json(
    health_response, expected_message
):
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(health_response=health_response),
    )

    with pytest.raises(KronosClientError, match=expected_message):
        client.health()


@pytest.mark.parametrize(
    ("prediction_response", "expected_message"),
    [
        (
            FakeResponse(
                {"error": "bad request"},
                status_code=422,
                text="bad request",
            ),
            "HTTP 422",
        ),
        (
            FakeResponse(
                {"status": "succeeded"},
                status_code=200,
                json_error=ValueError("bad json"),
                text="not json",
            ),
            "malformed JSON",
        ),
    ],
)
def test_prediction_reports_non_200_and_malformed_json(
    prediction_response, expected_message
):
    client = KronosClient(
        "http://kronos.test",
        token="secret",
        session=FakeSession(
            health={"status": "ok", "model": "Kronos-small"},
            prediction_response=prediction_response,
        ),
    )

    with pytest.raises(KronosClientError, match=expected_message):
        client.predict_daily(make_snapshot(), model="small")


@pytest.mark.parametrize(
    ("method", "exception", "expected_message"),
    [
        ("get", requests.Timeout("timed out"), "timed out"),
        ("post", requests.RequestException("connection reset"), "request failed"),
    ],
)
def test_request_errors_are_reported_without_fallback(
    method, exception, expected_message
):
    session = FakeSession(
        health={"status": "ok", "model": "Kronos-small"},
        get_exception=exception if method == "get" else None,
        post_exception=exception if method == "post" else None,
    )
    client = KronosClient("http://kronos.test", token="secret", session=session)

    with pytest.raises(KronosClientError, match=expected_message):
        if method == "get":
            client.health()
        else:
            client.predict_daily(make_snapshot(), model="small")


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_token_is_rejected_before_any_request(token):
    with pytest.raises(KronosClientError, match="token"):
        KronosClient("http://kronos.test", token=token, session=FakeSession())


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

    with pytest.raises(KronosClientError, match="JSON object"):
        client.predict_daily(make_snapshot(), model="small")


def test_unknown_or_missing_health_model_fails_closed():
    for health in ({"status": "ok"}, {"status": "ok", "model": "Kronos-large"}):
        client = KronosClient(
            "http://kronos.test",
            token="secret",
            session=FakeSession(health=health),
        )

        with pytest.raises(KronosClientError, match="model"):
            client.health()
