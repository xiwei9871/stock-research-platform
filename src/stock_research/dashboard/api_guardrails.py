from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from typing import Any, Mapping


@dataclass(frozen=True)
class GuardrailConfig:
    enabled: bool
    shared_token: str


def guardrail_config_from_env() -> GuardrailConfig:
    token = os.environ.get("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "").strip()
    enabled = os.environ.get("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return GuardrailConfig(enabled=enabled, shared_token=token)


def require_guarded_operation(
    *,
    operation: str,
    headers: Mapping[str, str],
    config: GuardrailConfig | None = None,
) -> dict[str, object]:
    selected = config or guardrail_config_from_env()
    if not selected.enabled:
        return {"operation": operation, "authenticated": False}

    token = str(headers.get("x-dashboard-write-token") or headers.get("X-Dashboard-Write-Token") or "")
    if not token:
        raise PermissionError("missing_dashboard_write_token")
    if not selected.shared_token or token != selected.shared_token:
        raise PermissionError("invalid_dashboard_write_token")
    return {"operation": operation, "authenticated": True}


class PublicationGuardBlocked(ValueError):
    def __init__(self, detail: dict[str, Any]):
        super().__init__("platform_not_ready_for_publication")
        self.detail = detail


def assert_publication_ready(readiness_loader: Callable[[], dict[str, Any]]) -> None:
    try:
        readiness = readiness_loader()
    except Exception as exc:  # pragma: no cover - defensive fail-closed path
        raise PublicationGuardBlocked(
            {
                "error": "platform_readiness_unavailable",
                "blocking_reasons": [str(exc)],
                "warnings": [],
            }
        ) from exc

    policy = readiness.get("policy") if isinstance(readiness.get("policy"), dict) else None
    if policy is not None:
        if policy.get("ready_for_publication") is True:
            return
        raise PublicationGuardBlocked(
            {
                "error": "platform_not_ready_for_publication",
                "status": policy.get("status") or readiness.get("status") or "unknown",
                "blocking_reasons": list(policy.get("blocking_reasons") or []),
                "warnings": list(policy.get("warnings") or []),
            }
        )

    status = str(readiness.get("status") or "").upper()
    if status in {"OK", "READY"}:
        return
    raise PublicationGuardBlocked(
        {
            "error": "platform_not_ready_for_publication",
            "status": readiness.get("status") or "unknown",
            "blocking_reasons": list(readiness.get("missing_data") or readiness.get("partial_data") or []),
            "warnings": list(readiness.get("warnings") or []),
        }
    )
