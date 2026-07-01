import re
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import ReportLink
from stock_research.report_delivery import LocalDeliveryAdapter, ReportArtifact, detect_report_type

DEFAULT_REPORTS_DIR = Path(SETTINGS.reports_root)


def load_report_links(
    trade_date: str,
    reports_dirs: list[str | Path] | None = None,
) -> list[dict[str, Any]]:
    dirs = [Path(path) for path in (reports_dirs or [DEFAULT_REPORTS_DIR])]
    artifacts, _warnings = LocalDeliveryAdapter().collect_artifacts(
        trade_date=trade_date,
        report_dirs=dirs,
        input_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    links = [
        _link_from_artifact(artifact, trade_date)
        for artifact in artifacts
        if _artifact_matches_trade_date(artifact, trade_date)
    ]
    links.extend(_load_html_report_links(trade_date, dirs))
    links.sort(key=lambda link: link.path)
    return [link.to_dict() for link in links]


def _report_type(filename: str) -> str:
    path = Path(filename)
    kwargs: dict[str, Any] = {
        "artifact_id": f"dashboard:{path.stem}",
        "report_type": "unknown",
        "title": path.stem.replace("_", " "),
        "trade_date": "",
        "generated_at": "",
        "metadata": {"path": filename},
    }
    if path.suffix.lower() == ".md":
        kwargs["markdown_path"] = filename
    elif path.suffix.lower() == ".json":
        kwargs["json_path"] = filename
    elif path.suffix.lower() == ".csv":
        kwargs["csv_paths"] = [filename]
    return detect_report_type(ReportArtifact(**kwargs))


def _link_from_artifact(artifact: ReportArtifact, trade_date: str) -> ReportLink:
    path = _primary_artifact_path(artifact)
    return ReportLink(
        report_type=artifact.report_type,
        title=Path(path).name,
        path=str(path),
        format=Path(path).suffix.lower().lstrip("."),
        trade_date=trade_date,
    )


def _load_html_report_links(trade_date: str, dirs: list[Path]) -> list[ReportLink]:
    links: list[ReportLink] = []
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() != ".html":
                continue
            if not _path_matches_trade_date(path, trade_date):
                continue
            links.append(
                ReportLink(
                    report_type=_report_type(path.name),
                    title=path.name,
                    path=str(path),
                    format="html",
                    trade_date=trade_date,
                )
            )
    return links


def _artifact_matches_trade_date(artifact: ReportArtifact, trade_date: str) -> bool:
    return any(_path_matches_trade_date(path, trade_date) for path in _artifact_paths(artifact))


def _path_matches_trade_date(path: Path, trade_date: str) -> bool:
    return re.search(rf"(?<!\d){re.escape(trade_date)}(?!\d)", path.name) is not None


def _primary_artifact_path(artifact: ReportArtifact) -> Path:
    source_path = artifact.metadata.get("source_path")
    if isinstance(source_path, str) and source_path:
        return Path(source_path)
    paths = _artifact_paths(artifact)
    if paths:
        return paths[0]
    path = artifact.metadata.get("path")
    return Path(str(path))


def _artifact_paths(artifact: ReportArtifact) -> list[Path]:
    paths: list[Path] = []
    for path_value in [
        artifact.markdown_path,
        artifact.json_path,
        artifact.run_card_path,
        *artifact.csv_paths,
    ]:
        if path_value is None:
            continue
        path = Path(path_value)
        if path not in paths:
            paths.append(path)
    return paths
