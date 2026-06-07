from __future__ import annotations

import json
import threading
import time
import http.client

import pytest

from stock_research.otp_relay import (
    OtpRelay,
    OtpRelayError,
    build_broker_otp_message,
    extract_feishu_text,
    parse_otp_submission,
    redact_code,
    start_otp_relay_server,
)


def test_otp_relay_matches_submitted_code_to_waiting_challenge() -> None:
    relay = OtpRelay(clock=time.monotonic)
    challenge = relay.create_challenge(
        broker="中信证券",
        account="chenduanxiwei@163.com",
        ttl_seconds=60,
    )
    result: dict[str, str] = {}

    waiter = threading.Thread(
        target=lambda: result.update(code=relay.wait_for_code(challenge.challenge_id, timeout_seconds=1)),
    )
    waiter.start()
    assert relay.submit_code(challenge.challenge_id, "123456")["status"] == "accepted"
    waiter.join(timeout=2)

    assert result == {"code": "123456"}
    assert relay.status(challenge.challenge_id)["status"] == "completed"


def test_otp_relay_rejects_expired_challenge_without_storing_code() -> None:
    now = [100.0]
    relay = OtpRelay(clock=lambda: now[0])
    challenge = relay.create_challenge(
        broker="中信证券",
        account="account@example.com",
        ttl_seconds=5,
    )

    now[0] = 106.0

    with pytest.raises(OtpRelayError, match="expired"):
        relay.submit_code(challenge.challenge_id, "654321")
    assert relay.status(challenge.challenge_id)["status"] == "expired"
    assert "654321" not in json.dumps(relay.status(challenge.challenge_id), ensure_ascii=False)


def test_parse_otp_submission_supports_direct_json_and_feishu_reply_text() -> None:
    assert parse_otp_submission({"challenge_id": "abc123", "code": "987654"}) == ("abc123", "987654")
    assert parse_otp_submission({"text": "OTP abc123 987654"}) == ("abc123", "987654")
    assert parse_otp_submission({"text": "abc123 987654"}) == ("abc123", "987654")


def test_extract_feishu_text_handles_event_callback_payload() -> None:
    payload = {
        "event": {
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "OTP abc123 123456"}),
            }
        }
    }

    assert extract_feishu_text(payload) == "OTP abc123 123456"


def test_build_broker_otp_message_is_actionable_without_leaking_code() -> None:
    relay = OtpRelay(clock=time.monotonic)
    challenge = relay.create_challenge(
        broker="中信证券",
        account="chenduanxiwei@163.com",
        ttl_seconds=120,
    )

    message = build_broker_otp_message(challenge, public_submit_url="https://otp.example.com/feishu/otp-callback")

    assert "中信证券" in message
    assert "chenduanxiwei@163.com" in message
    assert challenge.challenge_id in message
    assert "OTP " in message
    assert "验证码明文" not in message


def test_redact_code_masks_short_and_long_codes() -> None:
    assert redact_code("1234") == "****"
    assert redact_code("123456") == "******"
    assert redact_code("AB12CD") == "******"


def test_start_otp_relay_server_accepts_direct_submission() -> None:
    relay = OtpRelay(clock=time.monotonic)
    challenge = relay.create_challenge(
        broker="中信证券",
        account="account@example.com",
        ttl_seconds=60,
    )
    server = start_otp_relay_server(relay, host="127.0.0.1", port=0)
    port = server.server_address[1]
    try:
        body = json.dumps(
            {"challenge_id": challenge.challenge_id, "code": "112233"},
            ensure_ascii=False,
        ).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request(
            "POST",
            "/otp/submit",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
    finally:
        server.shutdown()
        server.server_close()

    assert payload == {
        "status": "accepted",
        "challenge_id": challenge.challenge_id,
        "code": "******",
    }
    assert relay.wait_for_code(challenge.challenge_id, timeout_seconds=1) == "112233"
