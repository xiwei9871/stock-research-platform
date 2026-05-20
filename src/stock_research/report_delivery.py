from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path
import re
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

        return list(artifacts_by_key.values()), warnings

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
            metadata=metadata,
        )

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
