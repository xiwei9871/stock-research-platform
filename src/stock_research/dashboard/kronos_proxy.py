"""Server-side bridge to the authenticated Kronos service on the GPU host."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests


class KronosProxyError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def normalize_kronos_code(asset_id: str) -> str:
    value = str(asset_id or "").strip().upper()
    if value.startswith("CN:"):
        parts = value.split(":")
        if len(parts) == 3:
            value = parts[2]
    elif "." in value:
        value = value.split(".", 1)[0]
    if len(value) != 6 or not value.isdigit():
        raise KronosProxyError("Kronos预测目前仅支持6位A股代码", status_code=400)
    return value


def _base_url() -> str:
    return os.environ.get("KRONOS_PROXY_BASE_URL", "").strip().rstrip("/")


def _token() -> str:
    return os.environ.get("KRONOS_PROXY_TOKEN", "").strip()


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = _base_url()
    token = _token()
    if not base_url or not token:
        raise KronosProxyError("Kronos外网代理未配置", status_code=503)

    timeout = float(os.environ.get("KRONOS_PROXY_TIMEOUT_SECONDS", "30"))
    try:
        response = requests.request(
            method,
            f"{base_url}/{path.lstrip('/')}",
            headers={"X-Kronos-Proxy-Token": token},
            params=params,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise KronosProxyError(f"Kronos服务不可达: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise KronosProxyError(
            f"Kronos服务返回了无效响应 ({response.status_code})",
            status_code=502,
        ) from exc

    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        message = str(detail or body or f"Kronos服务HTTP {response.status_code}")
        mapped_status = response.status_code if response.status_code in {400, 404, 409} else 502
        raise KronosProxyError(message, status_code=mapped_status)

    if isinstance(body, dict) and body.get("success") is False:
        raise KronosProxyError(str(body.get("message") or "Kronos服务返回失败"), status_code=502)
    if isinstance(body, dict) and "data" in body:
        data = body.get("data")
        if data is None:
            raise KronosProxyError("Kronos服务响应数据为空", status_code=502)
        return data
    if not isinstance(body, dict):
        raise KronosProxyError("Kronos服务响应格式错误", status_code=502)
    return body


def create_prediction(
    asset_id: str,
    *,
    force: bool = False,
    model: str = "small",
    sample_count: int = 20,
    daily_horizon: int = 10,
    intraday_horizon: int = 48,
) -> dict[str, Any]:
    code = normalize_kronos_code(asset_id)
    return _request(
        "POST",
        f"/stocks/{quote(code, safe='')}/kronos/predictions",
        params={"force": "true"} if force else None,
        payload={
            "model": model,
            "sample_count": sample_count,
            "daily_horizon": daily_horizon,
            "intraday_horizon": intraday_horizon,
        },
    )


def get_run(run_id: str) -> dict[str, Any]:
    value = str(run_id or "").strip()
    if not value:
        raise KronosProxyError("Kronos任务ID不能为空", status_code=400)
    return _request("GET", f"/kronos/runs/{quote(value, safe='')}")


def get_latest(asset_id: str) -> dict[str, Any]:
    code = normalize_kronos_code(asset_id)
    return _request(
        "GET",
        f"/stocks/{quote(code, safe='')}/kronos/predictions/latest",
    )
