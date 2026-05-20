from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
    "unknown": 0,
}


@dataclass(frozen=True)
class OpenClawExportItem:
    item_id: str
    artifact_id: str
    report_type: str
    title: str
    summary: str
    severity: str
    requires_attention: bool
    delivery_priority: int
    tags: list[str] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)
    run_card_path: str | None = None
    recommended_action: str = ""
    openclaw_route: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    recommended_channels: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        return self.recommended_action

    @property
    def route(self) -> str:
        return self.openclaw_route


@dataclass(frozen=True)
class OpenClawExportResult:
    manifest_path: str
    item_count: int
    items: list[OpenClawExportItem]
    channel: str = "openclaw"
    status: str = "dry_run"
    trade_date: str = ""
    generated_at: str = ""
    warnings: list[str] = field(default_factory=list)
    log_path: str | None = None


class OpenClawExportAdapter:
    def load_local_manifest(self, manifest_path: str | Path) -> dict[str, Any]:
        path = self._resolved_manifest_path(manifest_path)
        return json.loads(path.read_text(encoding="utf-8"))

    def select_openclaw_artifacts(
        self,
        manifest: dict[str, Any],
        *,
        include_all: bool = False,
        min_severity: str = "info",
        manifest_root: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        selected, _ = self._select_openclaw_artifacts_with_warnings(
            manifest,
            include_all=include_all,
            min_severity=min_severity,
            manifest_root=manifest_root,
        )
        return selected

    def _select_openclaw_artifacts_with_warnings(
        self,
        manifest: dict[str, Any],
        *,
        include_all: bool = False,
        min_severity: str = "info",
        manifest_root: str | Path | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        artifacts = manifest.get("artifacts", [])
        if not isinstance(artifacts, list):
            return [], []

        selected: list[dict[str, Any]] = []
        warnings: list[str] = []
        severity_threshold = self._severity_rank(min_severity)
        resolved_manifest_root = self._resolved_manifest_root(manifest_root)

        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue

            if not include_all:
                recommended_channels = artifact.get("recommended_channels", [])
                if not (isinstance(recommended_channels, list) and "openclaw" in recommended_channels):
                    continue

            severity = str(artifact.get("severity", "info"))
            if self._severity_rank(severity) < severity_threshold:
                continue

            sanitized_artifact, artifact_warnings = self._sanitize_artifact(
                artifact,
                manifest_root=resolved_manifest_root,
            )
            if artifact_warnings:
                warnings.extend(artifact_warnings)
            if sanitized_artifact is None:
                continue
            selected.append(sanitized_artifact)

        return selected, list(dict.fromkeys(warnings))

    def build_openclaw_item(
        self,
        artifact: dict[str, Any],
        *,
        manifest_root: str | Path | None = None,
    ) -> OpenClawExportItem:
        report_type = str(artifact.get("report_type", "generic_report"))
        requires_attention = bool(artifact.get("requires_attention", False))
        recommended_action = self._recommended_action_for(report_type)
        openclaw_route = self._openclaw_route_for(report_type, requires_attention=requires_attention)
        resolved_manifest_root = self._resolved_manifest_root(manifest_root)
        source_paths = self._existing_paths(
            [
                artifact.get("markdown_path"),
                artifact.get("json_path"),
                *self._coerce_path_list(artifact.get("csv_paths")),
                *self._metadata_paths(artifact.get("metadata"), "source_paths"),
                self._metadata_path(artifact.get("metadata"), "source_path"),
            ],
            resolved_manifest_root,
        )
        evidence_paths = self._existing_paths(
            [
                artifact.get("evidence_dir"),
                *self._metadata_paths(artifact.get("metadata"), "evidence_paths"),
            ],
            resolved_manifest_root,
        )
        run_card_path = self._existing_path(artifact.get("run_card_path"), resolved_manifest_root)
        payload = {
            "artifact_id": artifact.get("artifact_id", ""),
            "report_type": report_type,
            "title": artifact.get("title", ""),
            "summary": artifact.get("summary", ""),
            "severity": artifact.get("severity", "info"),
            "requires_attention": requires_attention,
            "delivery_priority": artifact.get("delivery_priority", 10),
            "tags": list(artifact.get("tags", [])),
            "source_paths": list(source_paths),
            "evidence_paths": list(evidence_paths),
            "run_card_path": run_card_path,
            "metadata": artifact.get("metadata", {}),
            "warnings": list(artifact.get("warnings", [])),
            "recommended_action": recommended_action,
            "openclaw_route": openclaw_route,
            "route": openclaw_route,
            "action": recommended_action,
        }
        return OpenClawExportItem(
            item_id=f"openclaw:{artifact.get('artifact_id', '')}",
            artifact_id=str(artifact.get("artifact_id", "")),
            report_type=report_type,
            title=str(artifact.get("title", "")),
            summary=str(artifact.get("summary", "")),
            severity=str(artifact.get("severity", "info")),
            requires_attention=requires_attention,
            delivery_priority=int(artifact.get("delivery_priority", 10)),
            tags=list(artifact.get("tags", [])),
            source_paths=list(source_paths),
            evidence_paths=list(evidence_paths),
            run_card_path=run_card_path,
            recommended_action=recommended_action,
            openclaw_route=openclaw_route,
            payload=payload,
            recommended_channels=list(artifact.get("recommended_channels", [])),
        )

    def export(
        self,
        manifest_path: str | Path,
        *,
        include_all: bool = False,
        min_severity: str = "info",
        dry_run: bool = True,
        log_path: str | Path | None = None,
    ) -> OpenClawExportResult:
        resolved_manifest_path = self._resolved_manifest_path(manifest_path)
        manifest = self.load_local_manifest(resolved_manifest_path)
        artifacts, warnings = self._select_openclaw_artifacts_with_warnings(
            manifest,
            include_all=include_all,
            min_severity=min_severity,
            manifest_root=resolved_manifest_path.parent,
        )
        items = [
            self.build_openclaw_item(artifact, manifest_root=resolved_manifest_path.parent)
            for artifact in artifacts
        ]
        result = OpenClawExportResult(
            manifest_path=str(resolved_manifest_path),
            item_count=len(items),
            items=items,
            status="dry_run" if dry_run else "completed",
            trade_date=str(manifest.get("trade_date", "")),
            generated_at=str(manifest.get("generated_at", "")),
            warnings=list(dict.fromkeys(warnings)),
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

    def _sanitize_artifact(
        self,
        artifact: dict[str, Any],
        *,
        manifest_root: Path,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        warnings: list[str] = []
        sanitized = dict(artifact)

        source_paths = self._sanitize_paths(
            [
                artifact.get("markdown_path"),
                artifact.get("json_path"),
                *self._coerce_path_list(artifact.get("csv_paths")),
                *self._metadata_paths(artifact.get("metadata"), "source_paths"),
                self._metadata_path(artifact.get("metadata"), "source_path"),
            ],
            warnings,
            manifest_root,
        )
        evidence_paths = self._sanitize_paths(
            [
                artifact.get("evidence_dir"),
                *self._metadata_paths(artifact.get("metadata"), "evidence_paths"),
            ],
            warnings,
            manifest_root,
        )
        run_card_path = self._sanitize_path(artifact.get("run_card_path"), warnings, manifest_root)

        sanitized["source_paths"] = source_paths
        sanitized["evidence_paths"] = evidence_paths
        if run_card_path is None:
            sanitized.pop("run_card_path", None)
        else:
            sanitized["run_card_path"] = run_card_path

        if not source_paths and not evidence_paths and run_card_path is None:
            return None, warnings

        return sanitized, warnings

    def _sanitize_paths(
        self,
        values: list[Any],
        warnings: list[str],
        manifest_root: Path,
    ) -> list[str]:
        sanitized: list[str] = []
        for value in values:
            path = self._sanitize_path(value, warnings, manifest_root)
            if path is not None and path not in sanitized:
                sanitized.append(path)
        return sanitized

    def _sanitize_path(self, value: Any, warnings: list[str], manifest_root: Path) -> str | None:
        if value in (None, ""):
            return None
        path = self._resolve_manifest_path(value, manifest_root)
        if path.exists():
            return str(path)
        warnings.append(f"missing_source_path:{path}")
        return None

    def _existing_paths(self, values: list[Any], manifest_root: Path) -> list[str]:
        paths: list[str] = []
        for value in values:
            if value in (None, ""):
                continue
            path = self._resolve_manifest_path(value, manifest_root)
            if path.exists():
                rendered = str(path)
                if rendered not in paths:
                    paths.append(rendered)
        return paths

    def _existing_path(self, value: Any, manifest_root: Path) -> str | None:
        if value in (None, ""):
            return None
        path = self._resolve_manifest_path(value, manifest_root)
        if path.exists():
            return str(path)
        return None

    def _coerce_path_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item not in (None, "")]
        return []

    def _metadata_paths(self, metadata: Any, key: str) -> list[str]:
        if not isinstance(metadata, dict):
            return []
        value = metadata.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if item not in (None, "")]
        return []

    def _metadata_path(self, metadata: Any, key: str) -> Any:
        if not isinstance(metadata, dict):
            return None
        value = metadata.get(key)
        return value if value not in (None, "") else None

    def _recommended_action_for(self, report_type: str) -> str:
        if report_type == "run_card_bundle":
            return "review_evidence"
        if report_type == "daily_topn_report":
            return "review_topn_candidates"
        if report_type == "watchlist_report":
            return "review_watchlist"
        if report_type == "must_watch_report":
            return "review_must_watch"
        if report_type == "risk_alert_report":
            return "review_risk_alert"
        if report_type == "factor_eval_report":
            return "review_factor_eval"
        if report_type == "backtest_report":
            return "review_backtest"
        return "review_report"

    def _openclaw_route_for(self, report_type: str, *, requires_attention: bool) -> str:
        if requires_attention:
            return "research_alert"
        if report_type == "run_card_bundle":
            return "evidence_review"
        if report_type in {"daily_topn_report", "watchlist_report", "must_watch_report"}:
            return "daily_research"
        if report_type in {"factor_eval_report", "backtest_report"}:
            return "research_validation"
        if report_type == "risk_alert_report":
            return "research_alert"
        return "research_inbox"

    def _severity_rank(self, severity: str) -> int:
        return SEVERITY_ORDER.get(str(severity).lower(), 0)

    def _resolved_manifest_root(self, manifest_root: str | Path | None) -> Path:
        if manifest_root is None:
            return Path.cwd()
        return Path(manifest_root).resolve()

    def _resolve_manifest_path(self, value: Any, manifest_root: Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (manifest_root / path).resolve()

    def _resolved_manifest_path(self, manifest_path: str | Path) -> Path:
        path = Path(manifest_path)
        if path.is_dir():
            return path / "manifest.json"
        return path
