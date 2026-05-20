from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenClawExportItem:
    artifact_id: str
    report_type: str
    route: str
    action: str
    title: str
    trade_date: str
    generated_at: str
    payload: dict[str, Any] = field(default_factory=dict)
    recommended_channels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OpenClawExportResult:
    manifest_path: str
    item_count: int
    items: list[OpenClawExportItem]
    warnings: list[str] = field(default_factory=list)
    log_path: str | None = None


class OpenClawExportAdapter:
    def load_local_manifest(self, manifest_path: str | Path) -> dict[str, Any]:
        path = self._resolved_manifest_path(manifest_path)
        return json.loads(path.read_text(encoding="utf-8"))

    def select_openclaw_artifacts(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        artifacts = manifest.get("artifacts", [])
        if not isinstance(artifacts, list):
            return []
        selected: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            recommended_channels = artifact.get("recommended_channels", [])
            if isinstance(recommended_channels, list) and "openclaw" in recommended_channels:
                selected.append(artifact)
        return selected

    def build_openclaw_item(self, artifact: dict[str, Any]) -> OpenClawExportItem:
        report_type = str(artifact.get("report_type", "generic_report"))
        route, action = self._route_and_action_for(report_type)
        source_paths = {
            "markdown_path": artifact.get("markdown_path"),
            "json_path": artifact.get("json_path"),
            "csv_paths": list(artifact.get("csv_paths", [])),
            "run_card_path": artifact.get("run_card_path"),
            "evidence_dir": artifact.get("evidence_dir"),
        }
        metadata = artifact.get("metadata", {})
        bundle_dir = metadata.get("bundle_dir") if isinstance(metadata, dict) else None
        payload = {
            "artifact_id": artifact.get("artifact_id", ""),
            "report_type": report_type,
            "title": artifact.get("title", ""),
            "trade_date": artifact.get("trade_date", ""),
            "generated_at": artifact.get("generated_at", ""),
            "summary": artifact.get("summary", ""),
            "severity": artifact.get("severity", "info"),
            "requires_attention": bool(artifact.get("requires_attention", False)),
            "recommended_channels": list(artifact.get("recommended_channels", [])),
            "source_paths": source_paths,
            "bundle_dir": bundle_dir,
            "route": route,
            "action": action,
        }
        return OpenClawExportItem(
            artifact_id=str(artifact.get("artifact_id", "")),
            report_type=report_type,
            route=route,
            action=action,
            title=str(artifact.get("title", "")),
            trade_date=str(artifact.get("trade_date", "")),
            generated_at=str(artifact.get("generated_at", "")),
            payload=payload,
            recommended_channels=list(artifact.get("recommended_channels", [])),
        )

    def export(
        self,
        manifest_path: str | Path,
        *,
        log_path: str | Path | None = None,
    ) -> OpenClawExportResult:
        resolved_manifest_path = self._resolved_manifest_path(manifest_path)
        manifest = self.load_local_manifest(resolved_manifest_path)
        artifacts = self.select_openclaw_artifacts(manifest)
        items = [self.build_openclaw_item(artifact) for artifact in artifacts]
        result = OpenClawExportResult(
            manifest_path=str(resolved_manifest_path),
            item_count=len(items),
            items=items,
            warnings=[],
            log_path=str(log_path) if log_path is not None else None,
        )
        if log_path is not None:
            self.write_openclaw_log(log_path, result)
        return result

    def write_openclaw_log(self, log_path: str | Path, result: OpenClawExportResult) -> None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "manifest_path": result.manifest_path,
            "item_count": result.item_count,
            "items": [asdict(item) for item in result.items],
            "warnings": list(result.warnings),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")

    def _route_and_action_for(self, report_type: str) -> tuple[str, str]:
        if report_type == "run_card_bundle":
            return ("openclaw.report.run_card_bundle", "publish")
        if report_type == "daily_topn_report":
            return ("openclaw.report.daily_topn_report", "publish")
        return (f"openclaw.report.{report_type}", "preview")

    def _resolved_manifest_path(self, manifest_path: str | Path) -> Path:
        path = Path(manifest_path)
        if path.is_dir():
            return path / "manifest.json"
        return path
