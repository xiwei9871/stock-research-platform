from __future__ import annotations

from pathlib import Path

from stock_research.citics_research import (
    CiticsResearchClient,
    login_citics_with_feishu_otp,
)
from stock_research.otp_relay import OtpRelay


class _Response:
    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.headers = {}
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append({"url": url, "data": dict(data or {}), "timeout": timeout})
        if url.endswith("/api/login"):
            return _Response({"code": 0, "data": {"loginName": "account@example.com"}}, {"authorization": "Bearer token"})
        return _Response({"code": 0, "data": {}})


def test_citics_client_requests_email_vcode_with_expected_form() -> None:
    session = _Session()
    client = CiticsResearchClient(session=session)

    client.request_email_code("account@example.com", validate="captcha-token")

    assert session.posts[0]["url"] == "https://research.citics.com/default/api/vcode"
    assert session.posts[0]["data"] == {
        "type": "email",
        "loginName": "account@example.com",
        "validate": "captcha-token",
    }


def test_citics_client_login_stores_authorization_header_and_session_file(tmp_path: Path) -> None:
    session = _Session()
    client = CiticsResearchClient(session=session)

    result = client.login_with_email_code(
        "account@example.com",
        "123456",
        token_path=tmp_path / "citics_token.json",
    )

    assert session.posts[0]["url"] == "https://research.citics.com/default/api/login"
    assert session.posts[0]["data"] == {
        "type": 2,
        "loginName": "account@example.com",
        "vcode": "123456",
        "riskFlag": 0,
    }
    assert session.headers["authorization"] == "Bearer token"
    token_text = (tmp_path / "citics_token.json").read_text(encoding="utf-8")
    assert "Bearer token" in token_text
    assert "123456" not in token_text
    assert result["data"]["loginName"] == "account@example.com"


def test_citics_client_lists_reports_with_authenticated_header_fields() -> None:
    session = _Session()
    client = CiticsResearchClient(session=session)
    client.apply_token("Bearer token")

    client.list_reports(
        keyword="浦发银行",
        start_date="2025-01-01",
        end_date="2026-06-04",
        page=2,
        page_size=25,
    )

    assert session.headers["authorization"] == "Bearer token"
    assert session.posts[0]["url"] == "https://research.citics.com/default/api/rpt/plist"
    assert session.posts[0]["data"] == {
        "title": "浦发银行",
        "rptLang": 1,
        "startRptDate": "2025-01-01",
        "endRptDate": "2026-06-04",
        "pno": 2,
        "psize": 25,
    }


def test_login_citics_with_feishu_otp_waits_for_relay_code_before_login(monkeypatch) -> None:
    session = _Session()
    client = CiticsResearchClient(session=session)
    relay = OtpRelay()
    sent_messages = []

    def fake_send(**kwargs):
        sent_messages.append(kwargs)
        challenge_id = kwargs["message"].split("challenge_id: ", 1)[1].split("\n", 1)[0]
        relay.submit_code(challenge_id, "998877")

    monkeypatch.setattr("stock_research.otp_relay.send_openclaw_feishu_message", fake_send)

    login_citics_with_feishu_otp(
        client=client,
        relay=relay,
        email="account@example.com",
        feishu_target="oc_group",
        public_submit_url="https://otp.example.com/feishu/otp-callback",
        wait_timeout_seconds=1,
    )

    assert session.posts[0]["url"].endswith("/api/vcode")
    assert session.posts[1]["url"].endswith("/api/login")
    assert session.posts[1]["data"]["vcode"] == "998877"
    assert sent_messages
