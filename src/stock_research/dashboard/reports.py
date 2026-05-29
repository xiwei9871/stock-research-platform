from pathlib import Path
from typing import Any

from stock_research.dashboard.schemas import ReportLink


DEFAULT_REPORTS_DIR = Path("/Users/xiwei/stock_research/reports")


def load_report_links(
    trade_date: str,
    reports_dirs: list[str | Path] | None = None,
) -> list[dict[str, Any]]:
    dirs = [Path(path) for path in (reports_dirs or [DEFAULT_REPORTS_DIR])]
    links: list[ReportLink] = []
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob(f"*{trade_date}*")):
            if path.suffix.lower() not in {".md", ".csv", ".json", ".html"}:
                continue
            links.append(
                ReportLink(
                    report_type=_report_type(path.name),
                    title=path.name,
                    path=str(path),
                    format=path.suffix.lower().lstrip("."),
                    trade_date=trade_date,
                )
            )
    return [link.to_dict() for link in links]


def _report_type(filename: str) -> str:
    lowered = filename.lower()
    if "watchlist" in lowered:
        return "watchlist_report"
    if "topn" in lowered or "top20" in lowered:
        return "daily_topn_report"
    if "risk" in lowered:
        return "risk_report"
    if "portfolio" in lowered or "retention" in lowered:
        return "simulation_report"
    return "generic_report"
