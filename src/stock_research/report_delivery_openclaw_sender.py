from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from stock_research.report_delivery_openclaw import SEVERITY_ORDER


@dataclass(frozen=True)
class OpenClawSendConfig:
    endpoint: str | None
    token: str | None
    timeout_seconds: float
    dry_run: bool
    retry_count: int
    retry_backoff_seconds: float
    outbox_dir: str
    limit: int | None
    allow_live_send: bool
    route_allowlist: list[str] = field(default_factory=list)
    severity_max: str | None = None
    test_mode: bool = False


@dataclass(frozen=True)
class OpenClawSendResult:
    send_id: str
    channel: str
    status: str
    dry_run: bool
    item_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    preview_path: str
    send_log_path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: str = ""


class DryRunOpenClawTransport:
    def send(self, payload: dict[str, Any], config: OpenClawSendConfig) -> dict[str, Any]:
        return {
            "status": "dry_run",
            "dry_run": True,
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "warnings": [],
            "errors": [],
            "payload": payload,
        }


class FakeOpenClawTransport:
    def send(self, payload: dict[str, Any], config: OpenClawSendConfig) -> dict[str, Any]:
        item_count = len(payload.get("items", []))
        return {
            "status": "sent",
            "dry_run": False,
            "sent_count": item_count,
            "failed_count": 0,
            "skipped_count": 0,
            "warnings": [],
            "errors": [],
            "payload": payload,
        }


class HttpOpenClawTransport:
    def send(self, payload: dict[str, Any], config: OpenClawSendConfig) -> dict[str, Any]:
        raise NotImplementedError("HttpOpenClawTransport is not implemented yet")


class OpenClawSender:
    def __init__(self, transport: Any) -> None:
        self.transport = transport

    def load_export(self, manifest_path: str | Path, items_path: str | Path) -> dict[str, Any]:
        resolved_manifest_path = Path(manifest_path)
        resolved_items_path = Path(items_path)

        manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = []
        for line in resolved_items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            items.append(json.loads(line))

        return {
            "manifest_path": str(resolved_manifest_path),
            "items_path": str(resolved_items_path),
            "manifest": manifest,
            "items": items,
        }

    def build_send_payload(self, export_data: dict[str, Any], config: OpenClawSendConfig) -> dict[str, Any]:
        manifest = export_data["manifest"]
        items = self._filter_items(list(export_data["items"]), config)
        payload_metadata: dict[str, Any] = {}
        if config.test_mode:
            payload_metadata = {
                "source": "stock_research_openclaw_smoke_test",
                "test_mode": True,
            }

        return {
            "channel": "openclaw",
            "dry_run": config.dry_run,
            "endpoint": config.endpoint,
            "generated_at": self._generated_at(),
            "source_manifest_path": manifest.get("source_manifest_path", export_data["manifest_path"]),
            "item_count": len(items),
            "items": items,
            "manifest": manifest,
            "payload": {
                "items": items,
                "metadata": payload_metadata,
            },
        }

    def send_batch(
        self,
        *,
        manifest_path: str | Path,
        items_path: str | Path,
        config: OpenClawSendConfig,
    ) -> OpenClawSendResult:
        export_data = self.load_export(manifest_path, items_path)
        payload = self.build_send_payload(export_data, config)
        outbox_dir = Path(config.outbox_dir)
        outbox_dir.mkdir(parents=True, exist_ok=True)
        preview_path = outbox_dir / "send_preview.json"
        send_log_path = outbox_dir / "send_log.jsonl"
        send_id = self._send_id(payload)
        generated_at = payload["generated_at"]

        if config.dry_run:
            self.write_send_preview(preview_path, payload)
            self.write_send_log(
                send_log_path,
                {
                    "send_id": send_id,
                    "channel": "openclaw",
                    "status": "dry_run",
                    "dry_run": True,
                    "item_count": payload["item_count"],
                    "sent_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "preview_path": str(preview_path),
                    "source_manifest_path": payload["source_manifest_path"],
                    "generated_at": generated_at,
                },
            )
            return OpenClawSendResult(
                send_id=send_id,
                channel="openclaw",
                status="dry_run",
                dry_run=True,
                item_count=payload["item_count"],
                sent_count=0,
                failed_count=0,
                skipped_count=0,
                preview_path=str(preview_path),
                send_log_path=str(send_log_path),
                errors=[],
                warnings=[],
                generated_at=generated_at,
            )

        self._validate_live_send_config(config)
        self._validate_live_send_items(payload["items"])

        transport_result = self.transport.send(payload, config)
        self.write_send_preview(preview_path, payload)
        self.write_send_log(
            send_log_path,
            {
                "send_id": send_id,
                "channel": "openclaw",
                "status": str(transport_result.get("status", "sent")),
                "dry_run": False,
                "item_count": payload["item_count"],
                "sent_count": int(transport_result.get("sent_count", 0)),
                "failed_count": int(transport_result.get("failed_count", 0)),
                "skipped_count": int(transport_result.get("skipped_count", 0)),
                "preview_path": str(preview_path),
                "source_manifest_path": payload["source_manifest_path"],
                "generated_at": generated_at,
            },
        )
        return OpenClawSendResult(
            send_id=send_id,
            channel="openclaw",
            status=str(transport_result.get("status", "sent")),
            dry_run=False,
            item_count=payload["item_count"],
            sent_count=int(transport_result.get("sent_count", 0)),
            failed_count=int(transport_result.get("failed_count", 0)),
            skipped_count=int(transport_result.get("skipped_count", 0)),
            preview_path=str(preview_path),
            send_log_path=str(send_log_path),
            errors=list(transport_result.get("errors", [])),
            warnings=list(transport_result.get("warnings", [])),
            generated_at=generated_at,
        )

    def write_send_preview(self, preview_path: str | Path, payload: dict[str, Any]) -> None:
        Path(preview_path).write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_send_log(self, send_log_path: str | Path, record: dict[str, Any]) -> None:
        Path(send_log_path).write_text(
            json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _generated_at(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _send_id(self, payload: dict[str, Any]) -> str:
        source_manifest_path = str(payload.get("source_manifest_path", ""))
        item_count = int(payload.get("item_count", 0))
        generated_at = str(payload.get("generated_at", ""))
        return f"openclaw-send:{item_count}:{generated_at}:{source_manifest_path}"

    def _filter_items(self, items: list[dict[str, Any]], config: OpenClawSendConfig) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        allowed_routes = {str(route) for route in config.route_allowlist if str(route)}
        severity_threshold = self._severity_rank(config.severity_max) if config.severity_max else None

        for item in items:
            if allowed_routes and str(item.get("openclaw_route", "")) not in allowed_routes:
                continue
            if severity_threshold is not None:
                severity_rank = self._severity_rank(item.get("severity", "unknown"))
                if severity_rank is None or severity_rank > severity_threshold:
                    continue
            filtered.append(self._copy_item(item))

        if config.limit is not None:
            filtered = filtered[: config.limit]
        return filtered

    def _copy_item(self, item: dict[str, Any]) -> dict[str, Any]:
        copied = dict(item)
        payload = copied.get("payload")
        if isinstance(payload, dict):
            copied["payload"] = dict(payload)
        return copied

    def _severity_rank(self, severity: Any) -> int | None:
        normalized = str(severity).lower()
        if normalized not in SEVERITY_ORDER:
            return None
        return int(SEVERITY_ORDER[normalized])

    def _validate_live_send_config(self, config: OpenClawSendConfig) -> None:
        endpoint = config.endpoint
        if not endpoint:
            raise ValueError("endpoint is required when dry_run is False")

        problems: list[str] = []
        if not config.allow_live_send:
            problems.append("allow_live_send must be True")
        if config.limit != 1:
            problems.append("limit == 1")
        if not config.route_allowlist:
            problems.append("route_allowlist must be non-empty")
        if config.severity_max in (None, ""):
            problems.append("severity_max must be present")
        elif str(config.severity_max).lower() not in {"info", "low", "medium", "high"}:
            problems.append("severity_max must stay within the smoke-test envelope; critical is not allowed")
        if not config.test_mode:
            problems.append("test_mode must be True")

        if problems:
            raise ValueError("live send requires " + ", ".join(problems))

    def _validate_live_send_items(self, items: list[dict[str, Any]]) -> None:
        invalid_severities: list[str] = []
        for item in items:
            severity = str(item.get("severity", "")).lower()
            if severity not in {"critical", "high", "medium", "low", "info"}:
                invalid_severities.append(severity or "<missing>")
        if invalid_severities:
            unique_invalid = ", ".join(sorted(set(invalid_severities)))
            raise ValueError(f"live send requires known item severity; invalid severity: {unique_invalid}")
