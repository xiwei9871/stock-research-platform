from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha1
import csv
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

RUN_CARD_FILENAMES = {
    "run_card.json",
    "run_card.md",
    "metrics.json",
    "config_snapshot.json",
    "warnings.md",
    "data_coverage.json",
}
WATCHLIST_FILE_RE = re.compile(
    r"^(watchlist_report|watchlist_signals|must_watch)_(\d{4}-\d{2}-\d{2})_(.+)\.(md|json|csv)$"
)
REPORT_TYPE_PRIORITY = [
    "run_card_bundle",
    "risk_alert_report",
    "must_watch_report",
    "watchlist_signal_report",
    "watchlist_report",
    "factor_eval_report",
    "daily_topn_report",
    "daily_market_report",
    "backtest_report",
    "generic_report",
]
SEVERITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
    "unknown": 0,
}


@dataclass(frozen=True)
class ReportArtifact:
    artifact_id: str
    report_type: str
    title: str
    trade_date: str
    generated_at: str
    markdown_path: str | None = None
    json_path: str | None = None
    csv_paths: list[str] = field(default_factory=list)
    run_card_path: str | None = None
    evidence_dir: str | None = None
    warnings: list[str] = field(default_factory=list)
    severity: str = "info"
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    recommended_channels: list[str] = field(default_factory=lambda: ["local"])
    requires_attention: bool = False
    delivery_priority: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryResult:
    delivery_id: str
    channel: str
    status: str
    artifact_count: int
    output_dir: str
    manifest_path: str | None
    delivery_log_path: str | None
    errors: list[str]
    generated_at: str


class LocalDeliveryAdapter:
    def collect_artifacts(
        self,
        *,
        trade_date: str,
        input_dirs: list[str | Path],
        report_dirs: list[str | Path],
        run_card_dirs: list[str | Path],
        artifact_paths: list[str | Path],
    ) -> tuple[list[ReportArtifact], list[str]]:
        artifacts_by_key: dict[tuple[str, str], ReportArtifact] = {}
        warnings: list[str] = []
        for root in input_dirs:
            path = Path(root)
            if not path.exists():
                warnings.append(f"missing_input_dir:{path}")
                continue
            self._collect_path(path, trade_date, artifacts_by_key, warnings)

        for root in report_dirs:
            path = Path(root)
            if not path.exists():
                warnings.append(f"missing_report_dir:{path}")
                continue
            self._collect_path(path, trade_date, artifacts_by_key, warnings)

        for root in run_card_dirs:
            path = Path(root)
            if not path.exists():
                warnings.append(f"missing_run_card_dir:{path}")
                continue
            self._collect_path(path, trade_date, artifacts_by_key, warnings)

        for item in artifact_paths:
            path = Path(item)
            if not path.exists():
                warnings.append(f"missing_artifact_path:{path}")
                continue
            self._collect_path(path, trade_date, artifacts_by_key, warnings)

        return self._classify_artifacts(list(artifacts_by_key.values())), warnings

    def deliver_local(
        self,
        *,
        trade_date: str,
        input_dirs: list[str | Path],
        report_dirs: list[str | Path],
        run_card_dirs: list[str | Path],
        artifact_paths: list[str | Path],
        output_dir: str | Path,
        dry_run: bool = True,
    ) -> DeliveryResult:
        generated_at = _generated_at()
        output_path = Path(output_dir)
        delivery_id = _delivery_id_for(trade_date=trade_date, output_dir=output_path, generated_at=generated_at)

        artifacts, warnings = self.collect_artifacts(
            trade_date=trade_date,
            input_dirs=input_dirs,
            report_dirs=report_dirs,
            run_card_dirs=run_card_dirs,
            artifact_paths=artifact_paths,
        )
        errors = [warning for warning in warnings if warning.startswith("missing_input_dir:")]

        output_path.mkdir(parents=True, exist_ok=True)
        manifest_path = output_path / "manifest.json"
        delivery_log_path: Path | None = None

        delivered_artifacts = artifacts
        if not dry_run:
            artifacts_dir = output_path / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            delivered_artifacts, copy_warnings = self._materialize_artifacts(artifacts, artifacts_dir)
            warnings = [*warnings, *copy_warnings]
            errors.extend(
                warning for warning in copy_warnings if warning.startswith("missing_source_path:")
            )

        status = "error" if errors else ("dry_run" if dry_run else "completed")
        manifest = build_manifest(
            trade_date=trade_date,
            artifacts=delivered_artifacts,
            warnings=warnings,
            errors=errors,
            generated_at=generated_at,
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if not dry_run:
            delivery_log_path = output_path / "delivery_log.jsonl"
            write_delivery_log(
                delivery_log_path,
                delivery_id=delivery_id,
                generated_at=generated_at,
                channel="local",
                status=status,
                trade_date=trade_date,
                artifact_count=len(delivered_artifacts),
                manifest_path=manifest_path,
                error_message="; ".join(dict.fromkeys(errors)) if errors else "",
            )

        return DeliveryResult(
            delivery_id=delivery_id,
            channel="local",
            status=status,
            artifact_count=len(delivered_artifacts),
            output_dir=str(output_path),
            manifest_path=str(manifest_path),
            delivery_log_path=str(delivery_log_path) if delivery_log_path is not None else None,
            errors=list(dict.fromkeys(errors)),
            generated_at=generated_at,
        )

    def _collect_path(
        self,
        path: Path,
        trade_date: str,
        artifacts_by_key: dict[tuple[str, str], ReportArtifact],
        warnings: list[str],
    ) -> None:
        if path.is_dir():
            found = self._scan_dir(path, trade_date, artifacts_by_key, warnings)
            if not found:
                warnings.append(f"no_artifacts_found:{path}")
            return

        artifact = self._artifact_from_path(path, trade_date, warnings)
        if artifact is not None:
            self._merge_artifact(artifacts_by_key, artifact)

    def _scan_dir(
        self,
        root: Path,
        trade_date: str,
        artifacts_by_key: dict[tuple[str, str], ReportArtifact],
        warnings: list[str],
    ) -> bool:
        found = False
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            artifact = self._artifact_from_path(path, trade_date, warnings)
            if artifact is None:
                continue
            self._merge_artifact(artifacts_by_key, artifact)
            found = True
        return found

    def _artifact_from_path(
        self,
        path: Path,
        trade_date: str,
        warnings: list[str],
    ) -> ReportArtifact | None:
        if not path.exists() or not path.is_file():
            return None
        if path.suffix.lower() not in {".md", ".json", ".csv"}:
            return None

        bundle_root = self._run_card_bundle_dir(path)
        report_type = self._infer_report_type(path)
        title = path.stem.replace("_", " ")
        metadata: dict[str, Any] = {"path": str(path)}
        artifact_warnings: list[str] = []

        if bundle_root is not None:
            report_type = "run_card"
            title = bundle_root.name.replace("_", " ")
            metadata["bundle_dir"] = str(bundle_root)
        else:
            watchlist_identity = self._watchlist_identity(path)
            if watchlist_identity is not None:
                report_type = "watchlist"
                title = f"watchlist {watchlist_identity[0]} {watchlist_identity[1]}"
                metadata["watchlist_trade_date"] = watchlist_identity[0]
                metadata["watchlist_id"] = watchlist_identity[1]
        if path.suffix.lower() == ".json":
            json_warnings: list[str] = []
            _load_json_preview(path, json_warnings)
            warnings.extend(json_warnings)
            artifact_warnings.extend(json_warnings)

        artifact_id = self._artifact_id_for(path, report_type, trade_date)
        kwargs: dict[str, Any] = {
            "artifact_id": artifact_id,
            "report_type": report_type,
            "title": title,
            "trade_date": trade_date,
            "generated_at": "",
            "metadata": metadata,
            "warnings": artifact_warnings,
        }
        if path.suffix.lower() == ".md":
            kwargs["markdown_path"] = str(path)
        elif path.suffix.lower() == ".json":
            if bundle_root is not None and path.name == "run_card.json":
                kwargs["run_card_path"] = str(path)
            elif bundle_root is not None and path.name == "manifest.json" and path.parent.name == "evidence":
                kwargs["evidence_dir"] = str(path.parent)
            else:
                kwargs["json_path"] = str(path)
        elif path.suffix.lower() == ".csv":
            kwargs["csv_paths"] = [str(path)]

        return ReportArtifact(**kwargs)

    def _infer_report_type(self, path: Path) -> str:
        if self._run_card_bundle_dir(path) is not None:
            return "run_card"
        if self._watchlist_identity(path) is not None:
            return "watchlist"
        if path.name == "run_card.json":
            return "run_card"
        if path.name == "manifest.json" and path.parent.name == "evidence":
            return "evidence_bundle"

        text = " ".join([path.stem.lower(), *(part.lower() for part in path.parts)])
        mapping = [
            ("topn", "topn"),
            ("watchlist", "watchlist"),
            ("daily_research", "daily_research"),
            ("risk_alert", "risk_alerts"),
            ("risk_alerts", "risk_alerts"),
            ("market_state", "market_state"),
            ("sector_strength", "sector_strength"),
            ("position_review", "position_review"),
        ]
        for needle, report_type in mapping:
            if needle in text:
                return report_type
        return "unknown"

    def _artifact_id_for(self, path: Path, report_type: str, trade_date: str) -> str:
        digest = sha1(f"{trade_date}:{report_type}:{path}".encode("utf-8")).hexdigest()[:12]
        return f"{report_type}:{trade_date}:{digest}"

    def _merge_artifact(
        self,
        artifacts_by_key: dict[tuple[str, str], ReportArtifact],
        artifact: ReportArtifact,
    ) -> None:
        key = self._artifact_key_for_path(Path(artifact.metadata["path"]), artifact.report_type)
        current = artifacts_by_key.get(key)
        if current is None:
            artifacts_by_key[key] = artifact
            return

        markdown_path = current.markdown_path or artifact.markdown_path
        json_path = current.json_path or artifact.json_path
        run_card_path = current.run_card_path or artifact.run_card_path
        evidence_dir = current.evidence_dir or artifact.evidence_dir
        csv_paths = self._sort_csv_paths([*current.csv_paths, *artifact.csv_paths])
        warnings = list(dict.fromkeys([*current.warnings, *artifact.warnings]))
        metadata = {**current.metadata, **artifact.metadata}

        artifacts_by_key[key] = ReportArtifact(
            artifact_id=current.artifact_id,
            report_type=current.report_type,
            title=current.title,
            trade_date=current.trade_date,
            generated_at=current.generated_at or artifact.generated_at,
            markdown_path=markdown_path,
            json_path=json_path,
            csv_paths=csv_paths,
            run_card_path=run_card_path,
            evidence_dir=evidence_dir,
            warnings=warnings,
            severity=current.severity,
            summary=current.summary or artifact.summary,
            tags=list(dict.fromkeys([*current.tags, *artifact.tags])),
            recommended_channels=list(
                dict.fromkeys([*current.recommended_channels, *artifact.recommended_channels])
            ),
            requires_attention=current.requires_attention or artifact.requires_attention,
            delivery_priority=min(current.delivery_priority, artifact.delivery_priority),
            metadata=metadata,
        )

    def _classify_artifacts(self, artifacts: list[ReportArtifact]) -> list[ReportArtifact]:
        return [classify_artifact(artifact) for artifact in artifacts]

    def _classify_artifact(self, artifact: ReportArtifact) -> ReportArtifact:
        return classify_artifact(artifact)

    def _artifact_key_for_path(self, path: Path, report_type: str) -> tuple[str, str]:
        if report_type == "run_card":
            bundle_dir = self._run_card_bundle_dir(path)
            if bundle_dir is not None:
                return (report_type, str(bundle_dir))
        if report_type == "watchlist":
            watchlist_identity = self._watchlist_identity(path)
            if watchlist_identity is not None:
                trade_date, watchlist_id = watchlist_identity
                return (report_type, f"{path.parent}:{trade_date}:{watchlist_id}")
        if report_type == "evidence_bundle":
            return ("run_card", str(path.parent.parent))
        return (report_type, str(path.with_suffix("")))

    def _run_card_bundle_dir(self, path: Path) -> Path | None:
        if path.name in RUN_CARD_FILENAMES and (path.parent / "run_card.json").exists():
            return path.parent
        if path.name == "manifest.json" and path.parent.name == "evidence":
            bundle_dir = path.parent.parent
            if (bundle_dir / "run_card.json").exists():
                return bundle_dir
        return None

    def _watchlist_identity(self, path: Path) -> tuple[str, str] | None:
        match = WATCHLIST_FILE_RE.match(path.name)
        if match is None:
            return None
        return (match.group(2), match.group(3))

    def _sort_csv_paths(self, csv_paths: list[str]) -> list[str]:
        unique_paths = list(dict.fromkeys(csv_paths))
        def sort_key(value: str) -> tuple[int, str]:
            name = Path(value).name
            if name.startswith("watchlist_signals_"):
                return (0, name)
            if name.startswith("must_watch_"):
                return (1, name)
            return (2, name)

        return sorted(unique_paths, key=sort_key)

    def _materialize_artifacts(
        self,
        artifacts: list[ReportArtifact],
        artifacts_dir: Path,
    ) -> tuple[list[ReportArtifact], list[str]]:
        delivered_artifacts: list[ReportArtifact] = []
        warnings: list[str] = []
        for artifact in artifacts:
            delivered_artifacts.append(
                self._copy_artifact_to_dir(artifact=artifact, artifacts_dir=artifacts_dir, warnings=warnings)
            )
        return delivered_artifacts, warnings

    def _copy_artifact_to_dir(
        self,
        *,
        artifact: ReportArtifact,
        artifacts_dir: Path,
        warnings: list[str],
    ) -> ReportArtifact:
        destination_root = artifacts_dir / artifact.artifact_id.replace(":", "_")
        destination_root.mkdir(parents=True, exist_ok=True)

        bundle_dir_value = artifact.metadata.get("bundle_dir")
        if isinstance(bundle_dir_value, str):
            bundle_dir = Path(bundle_dir_value)
            copied_bundle_root = destination_root / bundle_dir.name
            copied_bundle_root.mkdir(parents=True, exist_ok=True)
            if bundle_dir.exists():
                for source_path in sorted(bundle_dir.rglob("*")):
                    if not source_path.is_file():
                        continue
                    destination_path = copied_bundle_root / source_path.relative_to(bundle_dir)
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, destination_path)
            else:
                warnings.append(f"missing_source_path:{bundle_dir}")

            return ReportArtifact(
                artifact_id=artifact.artifact_id,
                report_type=artifact.report_type,
                title=artifact.title,
                trade_date=artifact.trade_date,
                generated_at=artifact.generated_at,
                markdown_path=_copied_value(artifact.markdown_path, bundle_dir, copied_bundle_root),
                json_path=_copied_value(artifact.json_path, bundle_dir, copied_bundle_root),
                csv_paths=[
                    _copied_value(path, bundle_dir, copied_bundle_root) or path
                    for path in artifact.csv_paths
                ],
                run_card_path=_copied_value(artifact.run_card_path, bundle_dir, copied_bundle_root),
                evidence_dir=_copied_dir_value(artifact.evidence_dir, bundle_dir, copied_bundle_root),
                warnings=list(artifact.warnings),
                severity=artifact.severity,
                summary=artifact.summary,
                tags=list(artifact.tags),
                recommended_channels=list(artifact.recommended_channels),
                requires_attention=artifact.requires_attention,
                delivery_priority=artifact.delivery_priority,
                metadata={**artifact.metadata, "delivered_path": str(copied_bundle_root)},
            )

        source_paths = self._artifact_source_paths(artifact)
        source_root = self._common_source_root(source_paths)
        copied_paths: dict[str, str] = {}
        for source_path in source_paths:
            if not source_path.exists():
                warnings.append(f"missing_source_path:{source_path}")
                continue
            relative_path = source_path.relative_to(source_root)
            destination_path = destination_root / relative_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            copied_paths[str(source_path)] = str(destination_path)

        return ReportArtifact(
            artifact_id=artifact.artifact_id,
            report_type=artifact.report_type,
            title=artifact.title,
            trade_date=artifact.trade_date,
            generated_at=artifact.generated_at,
            markdown_path=copied_paths.get(artifact.markdown_path, artifact.markdown_path),
            json_path=copied_paths.get(artifact.json_path, artifact.json_path),
            csv_paths=[copied_paths.get(path, path) for path in artifact.csv_paths],
            run_card_path=copied_paths.get(artifact.run_card_path, artifact.run_card_path),
            evidence_dir=artifact.evidence_dir,
            warnings=list(artifact.warnings),
            severity=artifact.severity,
            summary=artifact.summary,
            tags=list(artifact.tags),
            recommended_channels=list(artifact.recommended_channels),
            requires_attention=artifact.requires_attention,
            delivery_priority=artifact.delivery_priority,
            metadata={**artifact.metadata, "delivered_path": str(destination_root)},
        )

    def _artifact_source_paths(self, artifact: ReportArtifact) -> list[Path]:
        unique_paths: list[Path] = []
        for path_value in [
            artifact.markdown_path,
            artifact.json_path,
            artifact.run_card_path,
            *artifact.csv_paths,
        ]:
            if path_value is None:
                continue
            path = Path(path_value)
            if path not in unique_paths:
                unique_paths.append(path)
        return unique_paths

    def _common_source_root(self, paths: list[Path]) -> Path:
        if not paths:
            return Path(".")
        if len(paths) == 1:
            return paths[0].parent
        try:
            common_path = Path(
                os.path.commonpath([str(path.parent) for path in paths])
            )
        except ValueError:
            return paths[0].parent
        return common_path


def classify_artifact(artifact: ReportArtifact) -> ReportArtifact:
    report_type = detect_report_type(artifact)
    severity = detect_severity(artifact, report_type=report_type)
    summary = extract_summary(artifact, report_type=report_type)
    recommended_channels = _recommended_channels_for(report_type)
    requires_attention = artifact.requires_attention or severity in {"high", "critical"}
    metadata = build_artifact_metadata(
        artifact,
        detected_by=_detected_by_for_artifact(artifact, report_type=report_type),
        warning_count=len(artifact.warnings),
    )

    tags = list(artifact.tags)
    if report_type == "daily_topn_report":
        tags = list(dict.fromkeys([*tags, "daily", "topn"]))
    elif report_type == "daily_market_report":
        tags = list(dict.fromkeys([*tags, "daily", "market"]))
    elif report_type == "run_card_bundle":
        tags = list(dict.fromkeys([*tags, "run_card", "bundle"]))
    elif report_type == "risk_alert_report":
        tags = list(dict.fromkeys([*tags, "risk", "alert"]))

    return replace(
        artifact,
        report_type=report_type,
        severity=severity,
        summary=summary,
        tags=tags,
        recommended_channels=recommended_channels,
        requires_attention=requires_attention,
        metadata=metadata,
    )


def detect_report_type(artifact: ReportArtifact) -> str:
    marker_text = _artifact_marker_text(artifact)
    primary_marker_text = _artifact_marker_text(artifact, primary_only=True)
    for report_type in REPORT_TYPE_PRIORITY:
        if report_type == "run_card_bundle" and _has_run_card_bundle_marker(artifact, marker_text):
            return report_type
        if report_type == "risk_alert_report" and _has_any_marker(primary_marker_text, ("risk_alert", "risk alerts", "risk-alert")):
            return report_type
        if report_type == "must_watch_report" and (
            _has_any_marker(primary_marker_text, ("must_watch", "must watch"))
            or _has_populated_must_watch_csv(artifact)
        ):
            return report_type
        if report_type == "watchlist_signal_report" and _has_any_marker(
            primary_marker_text, ("watchlist_signals", "watchlist_signal", "signal_watchlist")
        ):
            return report_type
        if report_type == "watchlist_report" and _has_any_marker(
            primary_marker_text, ("watchlist_report", "watchlist report", "watchlist")
        ):
            return report_type
        if report_type == "factor_eval_report" and _has_any_marker(primary_marker_text, ("factor_eval", "factor eval")):
            return report_type
        if report_type == "daily_topn_report" and _has_any_marker(primary_marker_text, ("daily_topn", "topn")):
            return report_type
        if report_type == "daily_market_report" and _has_any_marker(
            primary_marker_text,
            ("daily_market", "market_state", "market_regime", "market_summary", "market_report"),
        ):
            return report_type
        if report_type == "backtest_report" and _has_any_marker(primary_marker_text, ("backtest",)):
            return report_type
    for report_type in REPORT_TYPE_PRIORITY:
        if report_type == "risk_alert_report" and _has_any_marker(marker_text, ("risk_alert", "risk alerts", "risk-alert")):
            return report_type
        if report_type == "watchlist_signal_report" and _has_any_marker(
            marker_text, ("watchlist_signals", "watchlist_signal", "signal_watchlist")
        ):
            return report_type
        if report_type == "watchlist_report" and _has_any_marker(
            marker_text, ("watchlist_report", "watchlist report", "watchlist")
        ):
            return report_type
        if report_type == "factor_eval_report" and _has_any_marker(marker_text, ("factor_eval", "factor eval")):
            return report_type
        if report_type == "daily_topn_report" and _has_any_marker(marker_text, ("daily_topn", "topn")):
            return report_type
        if report_type == "daily_market_report" and _has_any_marker(
            marker_text,
            ("daily_market", "market_state", "market_regime", "market_summary", "market_report"),
        ):
            return report_type
        if report_type == "backtest_report" and _has_any_marker(marker_text, ("backtest",)):
            return report_type
    return "generic_report"


def detect_severity(artifact: ReportArtifact, *, report_type: str | None = None) -> str:
    resolved_type = report_type or detect_report_type(artifact)
    if resolved_type != "risk_alert_report":
        return "info"

    severities: list[str] = []
    for path in _artifact_source_paths(artifact):
        if path.suffix.lower() == ".md":
            severities.extend(_severity_tokens_from_text(path.read_text(encoding="utf-8")))
        elif path.suffix.lower() == ".json":
            severities.extend(_severity_tokens_from_json(path))

    if not severities:
        return "info"
    return max(severities, key=lambda value: SEVERITY_ORDER.get(value, 0))


def extract_summary(artifact: ReportArtifact, *, report_type: str | None = None) -> str:
    resolved_type = report_type or detect_report_type(artifact)

    if resolved_type == "daily_topn_report":
        json_summary = _summary_from_json(artifact)
        if json_summary:
            return json_summary
        markdown_summary = _summary_from_markdown(artifact)
        if markdown_summary:
            return markdown_summary
        filename_summary = _summary_from_filename(artifact)
        if filename_summary:
            return filename_summary
        return ""

    if resolved_type == "run_card_bundle":
        run_card_summary = _summary_from_run_card_bundle(artifact)
        if run_card_summary:
            return run_card_summary

    json_summary = _summary_from_json(artifact)
    if json_summary:
        return json_summary

    markdown_summary = _summary_from_markdown(artifact)
    if markdown_summary:
        return markdown_summary

    cleaned_filename = _summary_from_filename(artifact)
    if cleaned_filename:
        return cleaned_filename

    return ""


def _artifact_source_paths(artifact: ReportArtifact) -> list[Path]:
    unique_paths: list[Path] = []
    for path_value in [
        artifact.markdown_path,
        artifact.json_path,
        artifact.run_card_path,
        *artifact.csv_paths,
    ]:
        if path_value is None:
            continue
        path = Path(path_value)
        if path not in unique_paths:
            unique_paths.append(path)
    return unique_paths


def _artifact_marker_text(artifact: ReportArtifact, *, primary_only: bool = False) -> str:
    parts: list[str] = [artifact.report_type.lower(), artifact.title.lower()]
    paths = _artifact_primary_paths(artifact) if primary_only else _artifact_source_paths(artifact)
    for path in paths:
        parts.extend(part.lower() for part in path.parts)
        parts.append(path.stem.lower())
        if path.suffix.lower() == ".md":
            h1 = _load_markdown_title(path)
            if h1:
                parts.append(h1.lower())
        elif path.suffix.lower() == ".json":
            payload = _safe_json_load(path)
            if isinstance(payload, dict):
                for key in ("title", "report_type", "type", "name"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value.lower())

    bundle_dir_value = artifact.metadata.get("bundle_dir")
    if isinstance(bundle_dir_value, str):
        bundle_dir = Path(bundle_dir_value)
        parts.extend(part.lower() for part in bundle_dir.parts)
        parts.append(bundle_dir.name.lower())

    return " ".join(parts)


def _artifact_primary_paths(artifact: ReportArtifact) -> list[Path]:
    paths: list[Path] = []
    for path_value in [artifact.markdown_path, artifact.json_path, artifact.run_card_path]:
        if path_value is None:
            continue
        path = Path(path_value)
        if path not in paths:
            paths.append(path)
    return paths


def _has_run_card_bundle_marker(artifact: ReportArtifact, marker_text: str) -> bool:
    if artifact.run_card_path is not None:
        return True
    if isinstance(artifact.metadata.get("bundle_dir"), str):
        return True
    return _has_any_marker(
        marker_text,
        ("run_card.json", "run_card.md", "metrics.json", "config_snapshot", "warnings.md", "data_coverage.json"),
    )


def _has_any_marker(marker_text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in marker_text for marker in markers)


def _has_populated_must_watch_csv(artifact: ReportArtifact) -> bool:
    for path in artifact.csv_paths:
        csv_path = Path(path)
        if not csv_path.name.startswith("must_watch_") or csv_path.suffix.lower() != ".csv":
            continue
        if _csv_has_data_rows(csv_path):
            return True
    return False


def _csv_has_data_rows(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                next(reader)
            except StopIteration:
                return False
            for row in reader:
                if any(cell.strip() for cell in row):
                    return True
    except Exception:
        return False
    return False


def _summary_from_markdown(artifact: ReportArtifact) -> str:
    for path in _artifact_source_paths(artifact):
        if path.suffix.lower() != ".md":
            continue
        h1 = _load_markdown_title(path)
        if h1:
            return h1
    return ""


def _summary_from_json(artifact: ReportArtifact) -> str:
    for path in _artifact_source_paths(artifact):
        if path.suffix.lower() != ".json":
            continue
        payload = _safe_json_load(path)
        if isinstance(payload, dict):
            for key in ("summary", "title"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _summary_from_run_card_bundle(artifact: ReportArtifact) -> str:
    if artifact.run_card_path is not None:
        payload = _safe_json_load(Path(artifact.run_card_path))
        if isinstance(payload, dict):
            title = payload.get("title")
            if isinstance(title, str) and not _summary_is_insufficient(title):
                return title.strip()
            metrics = payload.get("metrics")
            metrics_summary = _summary_from_metrics(metrics)
            if metrics_summary:
                return metrics_summary
            warnings = payload.get("warnings")
            if isinstance(warnings, list) and warnings:
                first_warning = warnings[0]
                if isinstance(first_warning, str) and not _summary_is_insufficient(first_warning):
                    return first_warning.strip()
    return ""


def build_artifact_metadata(
    artifact: ReportArtifact,
    *,
    detected_by: list[str],
    warning_count: int,
) -> dict[str, Any]:
    source_path = _primary_source_path(artifact)
    metadata = dict(artifact.metadata)
    metadata.update(
        {
            "source_path": source_path,
            "source_kind": _source_kind_for(artifact),
            "detected_by": list(dict.fromkeys(detected_by)),
            "file_count": len(_artifact_source_paths(artifact)),
            "has_markdown": artifact.markdown_path is not None,
            "has_json": artifact.json_path is not None,
            "has_csv": bool(artifact.csv_paths),
            "has_run_card": artifact.run_card_path is not None,
            "has_evidence_bundle": artifact.evidence_dir is not None,
            "warning_count": warning_count,
        }
    )
    return _json_safe_value(metadata)


def _summary_from_filename(artifact: ReportArtifact) -> str:
    for path in _artifact_source_paths(artifact):
        candidate = _clean_filename(path.stem)
        if candidate:
            return candidate
    return ""


def _summary_from_metrics(metrics: Any) -> str:
    if not isinstance(metrics, dict) or not metrics:
        return ""

    parts: list[str] = []
    for key in sorted(metrics):
        value = metrics.get(key)
        rendered = _render_metric_value(value)
        if rendered is None:
            continue
        parts.append(f"{key}={rendered}")
        if len(parts) >= 2:
            break
    return ", ".join(parts)


def _render_metric_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _summary_is_insufficient(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"", "run card", "run_card", "topn"}


def _recommended_channels_for(report_type: str) -> list[str]:
    if report_type == "run_card_bundle":
        return ["local", "openclaw"]
    if report_type == "daily_topn_report":
        return ["local", "openclaw"]
    return ["local"]


def _load_markdown_title(path: Path, *, max_lines: int = 8) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for _ in range(max_lines):
                line = handle.readline()
                if not line:
                    break
                match = re.match(r"^\s*#\s+(.+?)\s*$", line)
                if match is not None:
                    return match.group(1).strip()
    except Exception:
        return ""
    return ""


def _load_json_preview(path: Path, warnings: list[str] | None = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        if warnings is not None:
            warnings.append(f"invalid_json:{path}")
        return None
    except Exception:
        return None


def _safe_json_load(path: Path) -> Any:
    return _load_json_preview(path)


def _severity_tokens_from_text(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"\b(critical|high|medium|low|info)\b", text, flags=re.IGNORECASE):
        token = match.group(1).lower()
        if token not in tokens:
            tokens.append(token)
    return tokens


def _severity_tokens_from_json(path: Path) -> list[str]:
    payload = _safe_json_load(path)
    tokens: list[str] = []
    for value in _iter_json_values(payload):
        if isinstance(value, str):
            lower = value.lower()
            if lower in SEVERITY_ORDER and lower not in tokens:
                tokens.append(lower)
    return tokens


def _iter_json_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        items: list[Any] = []
        for item in value.values():
            items.extend(_iter_json_values(item))
        return items
    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            items.extend(_iter_json_values(item))
        return items
    return [value]


def _detected_by_for_artifact(artifact: ReportArtifact, *, report_type: str) -> list[str]:
    detected_by: list[str] = []
    if isinstance(artifact.metadata.get("bundle_dir"), str):
        detected_by.append("bundle_dir")
    if artifact.run_card_path is not None:
        detected_by.append("run_card")
    if artifact.markdown_path is not None:
        detected_by.append("markdown")
        if _load_markdown_title(Path(artifact.markdown_path)):
            detected_by.append("markdown_h1")
    if artifact.json_path is not None:
        detected_by.append("json")
        payload = _safe_json_load(Path(artifact.json_path))
        if isinstance(payload, dict) and any(
            isinstance(payload.get(key), str) and str(payload.get(key)).strip()
            for key in ("summary", "title", "report_type", "type", "name")
        ):
            detected_by.append("json_preview")
    if artifact.csv_paths:
        detected_by.append("csv")
    if report_type == "generic_report" and not detected_by:
        detected_by.append("path")
    return list(dict.fromkeys(detected_by))


def _primary_source_path(artifact: ReportArtifact) -> str:
    for path_value in [artifact.markdown_path, artifact.json_path, artifact.run_card_path, *artifact.csv_paths]:
        if path_value:
            return str(path_value)
    bundle_dir_value = artifact.metadata.get("bundle_dir")
    if isinstance(bundle_dir_value, str) and bundle_dir_value:
        return bundle_dir_value
    path_value = artifact.metadata.get("path")
    return str(path_value) if path_value is not None else ""


def _source_kind_for(artifact: ReportArtifact) -> str:
    if artifact.run_card_path is not None or isinstance(artifact.metadata.get("bundle_dir"), str):
        return "bundle"
    return "file"


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, set):
        return [_json_safe_value(item) for item in sorted(value, key=str)]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _clean_filename(value: str) -> str:
    cleaned = value.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\b\d{4}\b", "", cleaned)
    cleaned = re.sub(r"\b\d{2}\b", "", cleaned)
    tokens = [
        token
        for token in cleaned.split()
        if token.lower() not in {"manual", "final", "draft", "report", "v1", "v2", "v3"}
    ]
    normalized = " ".join(tokens).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ""
    words = []
    for token in normalized.split():
        if token.lower() == "topn":
            words.append("TopN")
        else:
            words.append(token.capitalize())
    return " ".join(words)


def build_manifest(
    *,
    trade_date: str,
    artifacts: list[ReportArtifact],
    warnings: list[str],
    errors: list[str],
    generated_at: str,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "trade_date": trade_date,
        "channel": "local",
        "artifact_count": len(artifacts),
        "artifacts": [asdict(artifact) for artifact in artifacts],
        "warnings": list(dict.fromkeys(warnings)),
        "errors": list(dict.fromkeys(errors)),
    }


def write_delivery_log(
    log_path: str | Path,
    *,
    delivery_id: str,
    generated_at: str,
    channel: str,
    status: str,
    trade_date: str,
    artifact_count: int,
    manifest_path: str | Path,
    error_message: str,
) -> None:
    payload = {
        "delivery_id": delivery_id,
        "generated_at": generated_at,
        "channel": channel,
        "status": status,
        "trade_date": trade_date,
        "artifact_count": artifact_count,
        "manifest_path": str(manifest_path),
        "error_message": error_message,
    }
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def deliver_local_reports(
    *,
    trade_date: str,
    input_dirs: list[str | Path],
    report_dirs: list[str | Path],
    run_card_dirs: list[str | Path],
    artifact_paths: list[str | Path],
    output_dir: str | Path,
    dry_run: bool = True,
) -> DeliveryResult:
    adapter = LocalDeliveryAdapter()
    return adapter.deliver_local(
        trade_date=trade_date,
        input_dirs=input_dirs,
        report_dirs=report_dirs,
        run_card_dirs=run_card_dirs,
        artifact_paths=artifact_paths,
        output_dir=output_dir,
        dry_run=dry_run,
    )


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _delivery_id_for(*, trade_date: str, output_dir: Path, generated_at: str) -> str:
    digest = sha1(f"{trade_date}:{output_dir}:{generated_at}".encode("utf-8")).hexdigest()[:12]
    return f"local:{trade_date}:{digest}"


def _copied_value(value: str | None, source_root: Path, destination_root: Path) -> str | None:
    if value is None:
        return None
    path = Path(value)
    return str(destination_root / path.relative_to(source_root))


def _copied_dir_value(value: str | None, source_root: Path, destination_root: Path) -> str | None:
    if value is None:
        return None
    path = Path(value)
    return str(destination_root / path.relative_to(source_root))
