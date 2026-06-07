from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import requests

from stock_research.otp_relay import OtpRelay, request_broker_otp_via_feishu


class CiticsResearchError(Exception):
    pass


class CiticsResearchClient:
    def __init__(
        self,
        *,
        base_url: str = "https://research.citics.com/default",
        session: requests.Session | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.update(
            {
                "Origin": "https://research.citics.com",
                "Referer": "https://research.citics.com/rpt",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
                ),
            }
        )

    def request_email_code(self, email: str, *, validate: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": "email", "loginName": email}
        if validate:
            payload["validate"] = validate
        return self._post_json("/api/vcode", payload)

    def login_with_email_code(
        self,
        email: str,
        code: str,
        *,
        risk_flag: int = 0,
        token_path: str | Path | None = None,
    ) -> dict[str, Any]:
        payload = {
            "type": 2,
            "loginName": email,
            "vcode": code,
            "riskFlag": risk_flag,
        }
        result = self._post_json("/api/login", payload)
        token = self._last_authorization
        if not token:
            raise CiticsResearchError("citics login succeeded without authorization header")
        self.apply_token(token)
        if token_path is not None:
            self.save_token(token_path, token=token)
        return result

    def list_reports(
        self,
        *,
        keyword: str,
        start_date: str,
        end_date: str,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        payload = {
            "title": keyword,
            "rptLang": 1,
            "startRptDate": start_date,
            "endRptDate": end_date,
            "pno": page,
            "psize": page_size,
        }
        return self._post_json("/api/rpt/plist", payload)

    def apply_token(self, token: str) -> None:
        self.session.headers["authorization"] = token

    def save_token(self, token_path: str | Path, *, token: str | None = None) -> None:
        path = Path(token_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "broker": "citics",
            "authorization": token or self.session.headers.get("authorization", ""),
            "saved_at": int(time.time()),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def load_token(self, token_path: str | Path) -> bool:
        path = Path(token_path)
        if not path.exists():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        token = str(payload.get("authorization") or "")
        if not token:
            return False
        self.apply_token(token)
        return True

    @property
    def _last_authorization(self) -> str:
        return str(getattr(self, "_authorization", "") or "")

    def _post_json(self, api_path: str, data: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}{api_path}",
            data=data,
            timeout=self.timeout,
        )
        response.raise_for_status()
        self._authorization = str(response.headers.get("authorization") or "")
        payload = response.json()
        if not isinstance(payload, dict):
            raise CiticsResearchError("citics response is not a json object")
        code = payload.get("code")
        if code not in (0, "0", None):
            message = payload.get("msg") or payload.get("message") or "citics request failed"
            raise CiticsResearchError(f"citics api error {code}: {message}")
        return payload


def login_citics_with_feishu_otp(
    *,
    client: CiticsResearchClient,
    relay: OtpRelay,
    email: str,
    feishu_target: str,
    public_submit_url: str,
    wait_timeout_seconds: int = 300,
    token_path: str | Path | None = None,
    validate: str | None = None,
    feishu_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    dry_run: bool = False,
) -> dict[str, Any]:
    client.request_email_code(email, validate=validate)
    challenge = request_broker_otp_via_feishu(
        relay=relay,
        broker="中信证券",
        account=email,
        target=feishu_target,
        public_submit_url=public_submit_url,
        ttl_seconds=wait_timeout_seconds,
        feishu_account=feishu_account,
        openclaw_bin=openclaw_bin,
        dry_run=dry_run,
    )
    code = relay.wait_for_code(challenge.challenge_id, timeout_seconds=wait_timeout_seconds)
    return client.login_with_email_code(email, code, token_path=token_path)
