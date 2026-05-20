from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha1
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
            found = self._scan_dir(path, trade_date, artifacts_by_key)
            if not found:
                warnings.append(f"no_artifacts_found:{path}")
            return

        artifact = self._artifact_from_path(path, trade_date)
        if artifact is not None:
            self._merge_artifact(artifacts_by_key, artifact)

    def _scan_dir(
        self,
        root: Path,
        trade_date: str,
        artifacts_by_key: dict[tuple[str, str], ReportArtifact],
    ) -> bool:
        found = False
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            artifact = self._artifact_from_path(path, trade_date)
            if artifact is None:
                continue
            self._merge_artifact(artifacts_by_key, artifact)
            found = True
        return found

    def _artifact_from_path(self, path: Path, trade_date: str) -> ReportArtifact | None:
        if not path.exists() or not path.is_file():
            return None
        if path.suffix.lower() not in {".md", ".json", ".csv"}:
            return None

        bundle_root = self._run_card_bundle_dir(path)
        report_type = self._infer_report_type(path)
        title = path.stem.replace("_", " ")
        metadata: dict[str, Any] = {"path": str(path)}

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

        artifact_id = self._artifact_id_for(path, report_type, trade_date)
        kwargs: dict[str, Any] = {
            "artifact_id": artifact_id,
            "report_type": report_type,
            "title": title,
            "trade_date": trade_date,
            "generated_at": "",
            "metadata": metadata,
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
        return [self._classify_artifact(artifact) for artifact in artifacts]

    def _classify_artifact(self, artifact: ReportArtifact) -> ReportArtifact:
        path_value = artifact.metadata.get("path")
        path = Path(path_value) if isinstance(path_value, str) else None
        if (
            artifact.report_type == "topn"
            and path is not None
            and path.suffix.lower() == ".md"
            and path.name.startswith("daily_topn_")
        ):
            return replace(
                artifact,
                report_type="daily_topn_report",
                severity="info",
                summary="Daily TopN",
                tags=["daily", "topn"],
                recommended_channels=["local", "openclaw"],
                requires_attention=False,
                delivery_priority=10,
            )
        return artifact

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
