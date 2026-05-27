from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from stock_research.report_delivery_openclaw import SEVERITY_ORDER


class FeishuManifestError(ValueError):
    pass


@dataclass(frozen=True)
class FeishuDeliveryResult:
    preview_path: str
    delivery_log_path: str
    output_dir: str
    source_manifest_path: str
    channel: str = "feishu"
    status: str = "dry_run"
    trade_date: str = ""
    generated_at: str = ""
    item_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeishuSendConfig:
    webhook_url: str | None
    dry_run: bool
    outbox_dir: str
    limit: int | None
    allow_live_send: bool
    severity_max: str | None = None
    test_mode: bool = False


@dataclass(frozen=True)
class FeishuSendResult:
    send_id: str
    channel: str
    status: str
    dry_run: bool
    item_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    send_preview_path: str
    send_log_path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: str = ""


class FakeFeishuTransport:
    def send(self, payload: dict[str, Any], config: FeishuSendConfig) -> dict[str, Any]:
        item_results = [
            {"artifact_id": str(item.get("artifact_id", "")), "status": "sent"}
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]
        return {
            "status": "sent",
            "dry_run": False,
            "sent_count": len(item_results),
            "failed_count": 0,
            "skipped_count": 0,
            "warnings": [],
            "errors": [],
            "item_results": item_results,
        }


class HttpFeishuTransport:
    def send(self, payload: dict[str, Any], config: FeishuSendConfig) -> dict[str, Any]:
        if not config.webhook_url:
            raise ValueError("webhook_url is required for live Feishu send")
        items = payload.get("items")
        if not isinstance(items, list) or len(items) != 1:
            raise ValueError("Feishu transport requires exactly one deliverable item")
        item = items[0]
        if not isinstance(item, dict):
            raise ValueError("Feishu transport item must be a JSON object")
        feishu_payload = item.get("feishu_payload")
        if not isinstance(feishu_payload, dict):
            raise ValueError("Feishu transport item must include feishu_payload")

        body = json.dumps(feishu_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        request = Request(
            config.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = None
        try:
            response = urlopen(request, timeout=10)
        except URLError as exc:
            raise RuntimeError(f"Feishu HTTP send failed for {_webhook_host(config.webhook_url)}: {exc}") from exc
        except OSError as exc:
            raise RuntimeError(f"Feishu HTTP send failed for {_webhook_host(config.webhook_url)}: {exc}") from exc
        try:
            response_status = getattr(response, "status", getattr(response, "code", None))
        finally:
            if hasattr(response, "close"):
                response.close()
        if isinstance(response_status, int) and 200 <= response_status < 300:
            return {
                "status": "sent",
                "dry_run": False,
                "sent_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "warnings": [],
                "errors": [],
                "item_results": [
                    {
                        "artifact_id": str(item.get("artifact_id", "")),
                        "status": "sent",
                    }
                ],
            }
        raise RuntimeError(
            f"Feishu HTTP send failed for {_webhook_host(config.webhook_url)}: HTTP {response_status or 'unknown'}"
        )


class FeishuDryRunAdapter:
    def load_local_manifest(self, manifest_path: str | Path) -> dict[str, Any]:
        path = Path(manifest_path)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FeishuManifestError(f"Feishu manifest not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise FeishuManifestError(f"Feishu manifest is not valid JSON: {path}") from exc
        except OSError as exc:
            raise FeishuManifestError(f"Feishu manifest is not readable: {path}") from exc

    def select_artifacts(
        self,
        manifest: dict[str, Any],
        *,
        include_all: bool = False,
        min_severity: str = "info",
    ) -> list[dict[str, Any]]:
        artifacts = manifest.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise FeishuManifestError("Feishu manifest artifacts must be a list")

        selected: list[dict[str, Any]] = []
        severity_threshold = _severity_rank(min_severity)
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                raise FeishuManifestError(f"Feishu manifest artifact at index {index} must be an object")

            severity = str(artifact.get("severity", "info"))
            if _severity_rank(severity) < severity_threshold:
                continue

            recommended_channels = artifact.get("recommended_channels", [])
            recommended_for_feishu = isinstance(recommended_channels, list) and "feishu" in recommended_channels
            requires_attention = bool(artifact.get("requires_attention", False))
            if include_all or recommended_for_feishu or requires_attention or severity in {"high", "critical"}:
                selected.append(artifact)
        return selected

    def render_preview(
        self,
        manifest_path: str | Path,
        *,
        output_dir: str | Path,
        include_all: bool = False,
        min_severity: str = "info",
    ) -> FeishuDeliveryResult:
        resolved_manifest_path = Path(manifest_path)
        manifest = self.load_local_manifest(resolved_manifest_path)
        artifacts = self.select_artifacts(
            manifest,
            include_all=include_all,
            min_severity=min_severity,
        )
        generated_at = _generated_at()
        resolved_output_dir = Path(output_dir)
        resolved_output_dir.mkdir(parents=True, exist_ok=True)

        preview_path = resolved_output_dir / "feishu_preview.json"
        delivery_log_path = resolved_output_dir / "feishu_delivery_log.jsonl"
        preview = {
            "channel": "feishu",
            "status": "dry_run",
            "dry_run": True,
            "generated_at": generated_at,
            "trade_date": str(manifest.get("trade_date", "")),
            "source_manifest_path": str(resolved_manifest_path),
            "item_count": len(artifacts),
            "message_count": len(artifacts),
            "items": [self._build_preview_item(artifact) for artifact in artifacts],
        }
        preview_path.write_text(
            json.dumps(preview, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = FeishuDeliveryResult(
            preview_path=str(preview_path),
            delivery_log_path=str(delivery_log_path),
            output_dir=str(resolved_output_dir),
            source_manifest_path=str(resolved_manifest_path),
            trade_date=str(manifest.get("trade_date", "")),
            generated_at=generated_at,
            item_count=len(artifacts),
        )
        self._write_log(delivery_log_path, result)
        return result

    def _build_preview_item(self, artifact: dict[str, Any]) -> dict[str, Any]:
        message = self._message_for(artifact)
        return {
            "artifact_id": str(artifact.get("artifact_id", "")),
            "report_type": str(artifact.get("report_type", "generic_report")),
            "title": str(artifact.get("title", "")),
            "summary": str(artifact.get("summary", "")),
            "severity": str(artifact.get("severity", "info")),
            "requires_attention": bool(artifact.get("requires_attention", False)),
            "delivery_priority": int(artifact.get("delivery_priority", 10)),
            "message": message,
            "feishu_payload": {
                "msg_type": "text",
                "content": {"text": message},
            },
            "source_paths": _source_paths_for(artifact),
        }

    def _message_for(self, artifact: dict[str, Any]) -> str:
        title = str(artifact.get("title", "")).strip() or "Untitled report"
        report_type = str(artifact.get("report_type", "generic_report")).strip()
        severity = str(artifact.get("severity", "info")).strip()
        summary = str(artifact.get("summary", "")).strip()
        attention_marker = "attention required" if bool(artifact.get("requires_attention", False)) else "review"
        parts = [
            f"[{severity}] {title}",
            f"type: {report_type}",
            f"action: {attention_marker}",
        ]
        if summary:
            parts.append(f"summary: {summary}")
        artifact_id = str(artifact.get("artifact_id", "")).strip()
        if artifact_id:
            parts.append(f"artifact_id: {artifact_id}")
        source_paths = _source_paths_for(artifact)
        if source_paths:
            parts.append(f"paths: {', '.join(source_paths)}")
        return "\n".join(parts)

    def _write_log(self, path: Path, result: FeishuDeliveryResult) -> None:
        record = {
            "channel": result.channel,
            "status": result.status,
            "generated_at": result.generated_at,
            "trade_date": result.trade_date,
            "item_count": result.item_count,
            "preview_path": result.preview_path,
            "source_manifest_path": result.source_manifest_path,
            "errors": result.errors,
            "warnings": result.warnings,
        }
        path.write_text(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")


class FeishuSender:
    def __init__(self, transport: Any) -> None:
        self.transport = transport

    def load_preview(self, preview_path: str | Path) -> dict[str, Any]:
        path = Path(preview_path)
        try:
            preview = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FeishuManifestError(f"Feishu preview not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise FeishuManifestError(f"Feishu preview is not valid JSON: {path}") from exc
        except OSError as exc:
            raise FeishuManifestError(f"Feishu preview is not readable: {path}") from exc
        if not isinstance(preview, dict):
            raise FeishuManifestError(f"Feishu preview must contain a JSON object: {path}")
        items = preview.get("items")
        if not isinstance(items, list):
            raise FeishuManifestError(f"Feishu preview items must be a list: {path}")
        return preview

    def build_send_payload(self, preview: dict[str, Any], config: FeishuSendConfig) -> dict[str, Any]:
        items = self._filter_items(list(preview.get("items", [])), config)
        if not config.dry_run and config.allow_live_send and len(items) != 1:
            if not items:
                raise ValueError("live Feishu send requires at least one deliverable item after filtering")
            raise ValueError(
                "live Feishu send requires exactly one deliverable item after filtering; "
                f"got {len(items)}"
            )
        return {
            "channel": "feishu",
            "dry_run": config.dry_run,
            "webhook_host": _webhook_host(config.webhook_url),
            "generated_at": _generated_at(),
            "trade_date": str(preview.get("trade_date", "")),
            "source_preview_path": str(preview.get("source_preview_path", "")),
            "source_manifest_path": str(preview.get("source_manifest_path", "")),
            "item_count": len(items),
            "message_count": len(items),
            "items": items,
            "payload": {
                "messages": [
                    item.get("feishu_payload", {})
                    for item in items
                    if isinstance(item, dict)
                ],
            },
        }

    def send_preview(
        self,
        *,
        preview_path: str | Path,
        config: FeishuSendConfig,
    ) -> FeishuSendResult:
        preview = self.load_preview(preview_path)
        payload = self.build_send_payload(preview, config)
        outbox_dir = Path(config.outbox_dir)
        outbox_dir.mkdir(parents=True, exist_ok=True)
        send_preview_path = outbox_dir / "feishu_send_preview.json"
        send_log_path = outbox_dir / "feishu_send_log.jsonl"
        send_id = self._send_id(payload, preview_path)
        generated_at = payload["generated_at"]

        self.write_send_preview(send_preview_path, payload)
        if config.dry_run:
            self.write_send_log(
                send_log_path,
                [
                    self._summary_log_record(
                        send_id=send_id,
                        status="dry_run",
                        dry_run=True,
                        payload=payload,
                        send_preview_path=send_preview_path,
                        sent_count=0,
                        failed_count=0,
                        skipped_count=0,
                        generated_at=generated_at,
                    )
                ],
            )
            return FeishuSendResult(
                send_id=send_id,
                channel="feishu",
                status="dry_run",
                dry_run=True,
                item_count=payload["item_count"],
                sent_count=0,
                failed_count=0,
                skipped_count=0,
                send_preview_path=str(send_preview_path),
                send_log_path=str(send_log_path),
                generated_at=generated_at,
            )

        self._validate_live_send_config(config)
        self._validate_live_send_items(payload["items"])
        if payload["item_count"] == 0:
            raise ValueError("live Feishu send requires at least one deliverable item after filtering")

        transport_result = self.transport.send(payload, config)
        records = [
            self._summary_log_record(
                send_id=send_id,
                status=str(transport_result.get("status", "sent")),
                dry_run=False,
                payload=payload,
                send_preview_path=send_preview_path,
                sent_count=int(transport_result.get("sent_count", 0)),
                failed_count=int(transport_result.get("failed_count", 0)),
                skipped_count=int(transport_result.get("skipped_count", 0)),
                generated_at=generated_at,
            )
        ]
        item_results = {
            str(item_result.get("artifact_id", "")): item_result
            for item_result in transport_result.get("item_results", [])
            if isinstance(item_result, dict)
        }
        for item in payload["items"]:
            artifact_id = str(item.get("artifact_id", ""))
            item_result = item_results.get(artifact_id, {})
            records.append(
                {
                    "send_id": send_id,
                    "channel": "feishu",
                    "artifact_id": artifact_id,
                    "report_type": str(item.get("report_type", "")),
                    "status": str(item_result.get("status", transport_result.get("status", "sent"))),
                    "send_preview_path": str(send_preview_path),
                    "generated_at": generated_at,
                    "source_manifest_path": payload["source_manifest_path"],
                }
            )
        self.write_send_log(send_log_path, records)
        return FeishuSendResult(
            send_id=send_id,
            channel="feishu",
            status=str(transport_result.get("status", "sent")),
            dry_run=False,
            item_count=payload["item_count"],
            sent_count=int(transport_result.get("sent_count", 0)),
            failed_count=int(transport_result.get("failed_count", 0)),
            skipped_count=int(transport_result.get("skipped_count", 0)),
            send_preview_path=str(send_preview_path),
            send_log_path=str(send_log_path),
            errors=list(transport_result.get("errors", [])),
            warnings=list(transport_result.get("warnings", [])),
            generated_at=generated_at,
        )

    def write_send_preview(self, path: str | Path, payload: dict[str, Any]) -> None:
        Path(path).write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_send_log(self, path: str | Path, records: list[dict[str, Any]]) -> None:
        with Path(path).open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
                handle.write("\n")

    def _filter_items(self, items: list[dict[str, Any]], config: FeishuSendConfig) -> list[dict[str, Any]]:
        severity_threshold = _severity_rank(config.severity_max) if config.severity_max else None
        filtered: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if severity_threshold is not None and _severity_rank(item.get("severity", "unknown")) > severity_threshold:
                continue
            filtered.append(dict(item))
        if config.limit is not None:
            filtered = filtered[: config.limit]
        return filtered

    def _validate_live_send_config(self, config: FeishuSendConfig) -> None:
        problems: list[str] = []
        if not config.webhook_url:
            problems.append("webhook_url must be present")
        if not config.allow_live_send:
            problems.append("allow_live_send must be True")
        if config.limit != 1:
            problems.append("limit == 1")
        if config.severity_max in (None, ""):
            problems.append("severity_max must be present")
        elif str(config.severity_max).lower() not in {"info", "low"}:
            problems.append("severity_max must stay within the low-risk smoke-test envelope; use info or low")
        if not config.test_mode:
            problems.append("test_mode must be True")
        if problems:
            raise ValueError("live Feishu send requires " + ", ".join(problems))

    def _validate_live_send_items(self, items: list[dict[str, Any]]) -> None:
        invalid_severities = [
            str(item.get("severity", "")).lower() or "<missing>"
            for item in items
            if str(item.get("severity", "")).lower() not in SEVERITY_ORDER
        ]
        if invalid_severities:
            raise ValueError(
                "live Feishu send requires known item severity; invalid severity: "
                + ", ".join(sorted(set(invalid_severities)))
            )

    def _send_id(self, payload: dict[str, Any], preview_path: str | Path) -> str:
        return f"feishu-send:{payload['item_count']}:{payload['generated_at']}:{preview_path}"

    def _summary_log_record(
        self,
        *,
        send_id: str,
        status: str,
        dry_run: bool,
        payload: dict[str, Any],
        send_preview_path: Path,
        sent_count: int,
        failed_count: int,
        skipped_count: int,
        generated_at: str,
    ) -> dict[str, Any]:
        return {
            "send_id": send_id,
            "channel": "feishu",
            "status": status,
            "dry_run": dry_run,
            "item_count": payload["item_count"],
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "send_preview_path": str(send_preview_path),
            "source_manifest_path": payload["source_manifest_path"],
            "webhook_host": payload["webhook_host"],
            "generated_at": generated_at,
        }


def _source_paths_for(artifact: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ["markdown_path", "json_path", "run_card_path", "evidence_dir"]:
        value = artifact.get(key)
        if value:
            paths.append(str(value))
    csv_paths = artifact.get("csv_paths", [])
    if isinstance(csv_paths, list):
        paths.extend(str(value) for value in csv_paths if value)
    return paths


def _severity_rank(value: str) -> int:
    return SEVERITY_ORDER.get(str(value).lower(), 0)


def _webhook_host(webhook_url: str | None) -> str:
    if not webhook_url:
        return ""
    parsed = urlparse(webhook_url)
    return parsed.netloc


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
