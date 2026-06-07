from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import string
import threading
import time
from typing import Any, Callable

from stock_research.feishu_notify import send_openclaw_feishu_message


class OtpRelayError(Exception):
    pass


@dataclass(frozen=True)
class OtpChallenge:
    challenge_id: str
    broker: str
    account: str
    created_at: float
    expires_at: float


@dataclass
class _ChallengeState:
    challenge: OtpChallenge
    status: str = "pending"
    code: str | None = None


class OtpRelay:
    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._lock = threading.Condition()
        self._states: dict[str, _ChallengeState] = {}

    def create_challenge(
        self,
        *,
        broker: str,
        account: str,
        ttl_seconds: int = 300,
        challenge_id: str | None = None,
    ) -> OtpChallenge:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = self._clock()
        challenge = OtpChallenge(
            challenge_id=challenge_id or _new_challenge_id(),
            broker=broker,
            account=account,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            if challenge.challenge_id in self._states:
                raise OtpRelayError(f"challenge already exists: {challenge.challenge_id}")
            self._states[challenge.challenge_id] = _ChallengeState(challenge=challenge)
            self._lock.notify_all()
        return challenge

    def submit_code(self, challenge_id: str, code: str) -> dict[str, Any]:
        normalized_id = str(challenge_id or "").strip()
        normalized_code = _normalize_code(code)
        if not normalized_id:
            raise OtpRelayError("challenge_id is required")
        if not normalized_code:
            raise OtpRelayError("code is required")
        with self._lock:
            state = self._states.get(normalized_id)
            if state is None:
                raise OtpRelayError(f"unknown challenge: {normalized_id}")
            self._refresh_state(state)
            if state.status == "expired":
                raise OtpRelayError(f"challenge expired: {normalized_id}")
            if state.status == "completed":
                return {"status": "duplicate", "challenge_id": normalized_id}
            state.code = normalized_code
            state.status = "completed"
            self._lock.notify_all()
        return {"status": "accepted", "challenge_id": normalized_id}

    def wait_for_code(self, challenge_id: str, *, timeout_seconds: float) -> str:
        deadline = self._clock() + timeout_seconds
        normalized_id = str(challenge_id or "").strip()
        with self._lock:
            while True:
                state = self._states.get(normalized_id)
                if state is None:
                    raise OtpRelayError(f"unknown challenge: {normalized_id}")
                self._refresh_state(state)
                if state.status == "completed" and state.code is not None:
                    return state.code
                if state.status == "expired":
                    raise OtpRelayError(f"challenge expired: {normalized_id}")
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError(f"timed out waiting for challenge: {normalized_id}")
                self._lock.wait(timeout=min(remaining, 1.0))

    def status(self, challenge_id: str) -> dict[str, Any]:
        normalized_id = str(challenge_id or "").strip()
        with self._lock:
            state = self._states.get(normalized_id)
            if state is None:
                raise OtpRelayError(f"unknown challenge: {normalized_id}")
            self._refresh_state(state)
            challenge = state.challenge
            return {
                "challenge_id": challenge.challenge_id,
                "broker": challenge.broker,
                "account": challenge.account,
                "status": state.status,
                "created_at": challenge.created_at,
                "expires_at": challenge.expires_at,
                "has_code": state.code is not None,
            }

    def cleanup_expired(self) -> int:
        now = self._clock()
        with self._lock:
            expired_ids = [
                challenge_id
                for challenge_id, state in self._states.items()
                if state.status == "expired" or state.challenge.expires_at <= now
            ]
            for challenge_id in expired_ids:
                del self._states[challenge_id]
        return len(expired_ids)

    def _refresh_state(self, state: _ChallengeState) -> None:
        if state.status == "pending" and self._clock() > state.challenge.expires_at:
            state.status = "expired"


def request_broker_otp_via_feishu(
    *,
    relay: OtpRelay,
    broker: str,
    account: str,
    target: str,
    public_submit_url: str,
    ttl_seconds: int = 300,
    feishu_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    dry_run: bool = False,
) -> OtpChallenge:
    challenge = relay.create_challenge(
        broker=broker,
        account=account,
        ttl_seconds=ttl_seconds,
    )
    send_openclaw_feishu_message(
        message=build_broker_otp_message(challenge, public_submit_url=public_submit_url),
        target=target,
        account=feishu_account,
        openclaw_bin=openclaw_bin,
        dry_run=dry_run,
    )
    return challenge


def build_broker_otp_message(challenge: OtpChallenge, *, public_submit_url: str) -> str:
    expires_in = max(0, int(challenge.expires_at - challenge.created_at))
    return "\n".join(
        [
            "[stock-report] 券商研报登录需要验证码",
            f"券商: {challenge.broker}",
            f"账号: {challenge.account}",
            f"challenge_id: {challenge.challenge_id}",
            f"有效期: {expires_in} 秒",
            f"回调地址: {public_submit_url}",
            f"请在飞书回复: OTP {challenge.challenge_id} <收到的验证码>",
            "系统只在内存中短暂持有验证码，不写入日志或文件。",
        ]
    )


def parse_otp_submission(payload: dict[str, Any]) -> tuple[str, str]:
    challenge_id = str(payload.get("challenge_id") or "").strip()
    code = str(payload.get("code") or "").strip()
    if challenge_id and code:
        return challenge_id, _normalize_code(code)

    text = str(payload.get("text") or extract_feishu_text(payload) or "").strip()
    match = re.search(
        r"(?:^|\s)(?:OTP\s+)?(?P<challenge>[A-Za-z0-9_-]{6,64})\s+(?P<code>[A-Za-z0-9]{4,10})(?:\s|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise OtpRelayError("could not parse otp submission")
    return match.group("challenge"), _normalize_code(match.group("code"))


def extract_feishu_text(payload: dict[str, Any]) -> str:
    event = payload.get("event")
    if not isinstance(event, dict):
        return ""
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        try:
            content_payload = json.loads(content)
        except json.JSONDecodeError:
            return content
    elif isinstance(content, dict):
        content_payload = content
    else:
        return ""
    text = content_payload.get("text")
    return str(text or "")


def redact_code(code: str) -> str:
    return "*" * len(str(code or ""))


def serve_otp_relay(
    relay: OtpRelay,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    server = _build_server(relay, host=host, port=port)
    server.serve_forever()
    return server


def start_otp_relay_server(
    relay: OtpRelay,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    server = _build_server(relay, host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _build_server(relay: OtpRelay, *, host: str, port: int) -> ThreadingHTTPServer:
    handler = _make_handler(relay)
    return ThreadingHTTPServer((host, port), handler)


def _make_handler(relay: OtpRelay) -> type[BaseHTTPRequestHandler]:
    class OtpRelayHandler(BaseHTTPRequestHandler):
        server_version = "StockResearchOtpRelay/1.0"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._write_json({"status": "ok"})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._read_json()
                if "challenge" in payload and "event" not in payload:
                    self._write_json({"challenge": payload["challenge"]})
                    return
                if self.path not in {"/otp/submit", "/feishu/otp-callback"}:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                challenge_id, code = parse_otp_submission(payload)
                result = relay.submit_code(challenge_id, code)
                self._write_json(
                    {
                        "status": result["status"],
                        "challenge_id": result["challenge_id"],
                        "code": redact_code(code),
                    }
                )
            except Exception as exc:
                self._write_json(
                    {
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                    status=HTTPStatus.BAD_REQUEST,
                )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            if self.path.startswith("/otp/") or self.path.startswith("/feishu/"):
                return
            super().log_message(format, *args)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            if not raw:
                return {}
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise OtpRelayError("json object payload is required")
            return payload

        def _write_json(self, payload: dict[str, Any], *, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return OtpRelayHandler


def _new_challenge_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "otp_" + "".join(secrets.choice(alphabet) for _ in range(12))


def _normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", str(code or "")).strip()
