"""Human-readable reporting for immutable rolling oversold snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable, Sequence

import pandas as pd


REPORT_NAME = "rolling_sector_oversold_report.md"


def load_rolling_oversold_snapshot(snapshot_dir: str | Path) -> dict[str, object]:
    """Load a successful snapshot or a blocked preflight artifact directory."""

    directory = Path(snapshot_dir).expanduser().resolve()
    manifest_path = directory / "manifest.json"
    preflight_path = directory / "preflight.json"
    preflight = (
        json.loads(preflight_path.read_text(encoding="utf-8"))
        if preflight_path.is_file()
        else {}
    )
    if not manifest_path.is_file():
        if not bool(preflight.get("blocked")):
            raise ValueError(f"rolling snapshot manifest does not exist: {manifest_path}")
        anchor_date = str(preflight.get("anchor_date") or _path_part(directory.parent, "anchor="))
        score_version = str(preflight.get("score_version") or _path_part(directory, "version="))
        return {
            "snapshot_id": f"{score_version}|{anchor_date}" if anchor_date and score_version else "",
            "anchor_date": anchor_date,
            "data_cutoff_date": preflight.get("data_cutoff_date", ""),
            "score_version": score_version,
            "previous_snapshot_id": None,
            "manifest": {},
            "market_regime": {},
            "sector_states": pd.DataFrame(),
            "stock_candidates": pd.DataFrame(),
            "preflight": preflight,
            "backfill_requests": _read_csv(directory / "backfill_requests.csv"),
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    market = _read_csv(directory / "market_regime.csv")
    return {
        "snapshot_id": manifest.get("snapshot_id", ""),
        "anchor_date": manifest.get("anchor_date", ""),
        "data_cutoff_date": manifest.get("data_cutoff_date", ""),
        "score_version": manifest.get("score_version", ""),
        "previous_snapshot_id": manifest.get("previous_snapshot_id"),
        "manifest": manifest,
        "market_regime": market.iloc[0].dropna().to_dict() if not market.empty else {},
        "sector_states": _read_csv(directory / "sector_states.csv"),
        "stock_candidates": _read_csv(directory / "stock_candidates.csv"),
        "preflight": preflight,
        "backfill_requests": _read_csv(directory / "backfill_requests.csv"),
    }


def write_rolling_sector_oversold_report(
    *,
    output_dir: str | Path,
    snapshot: dict[str, object] | None = None,
    snapshot_dir: str | Path | None = None,
    focus_patterns: Sequence[str] | str | None = None,
    evaluation_detail: pd.DataFrame | None = None,
    evaluation_summary: pd.DataFrame | None = None,
) -> Path:
    """Write an audit-oriented report without changing immutable artifacts."""

    if snapshot is None:
        if snapshot_dir is None:
            raise ValueError("snapshot or snapshot_dir is required")
        snapshot = load_rolling_oversold_snapshot(snapshot_dir)
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dictionary")
    directory = Path(snapshot_dir).expanduser().resolve() if snapshot_dir is not None else None
    evaluation_directory = (
        latest_rolling_evaluation_directory(directory) if directory is not None else None
    )
    if evaluation_detail is None and directory is not None:
        evaluation_detail = _read_csv(
            (evaluation_directory or directory) / "evaluation_detail.csv"
        )
    if evaluation_summary is None and directory is not None:
        evaluation_summary = _read_csv(
            (evaluation_directory or directory) / "evaluation_summary.csv"
        )
    detail = _frame(evaluation_detail)
    summary = _frame(evaluation_summary)
    sectors = _frame(snapshot.get("sector_states"))
    stocks = _frame(snapshot.get("stock_candidates"))
    regime = snapshot.get("market_regime", {})
    if not isinstance(regime, dict):
        regime = {}
    preflight = snapshot.get("preflight", {})
    if not isinstance(preflight, dict):
        preflight = {}
    gaps = _gap_frame(preflight, snapshot.get("backfill_requests"))
    patterns = _focus_patterns(focus_patterns)

    lines = [
        "# Rolling Sector Oversold Report",
        "",
        f"- Snapshot: `{snapshot.get('snapshot_id', '')}`",
        f"- Anchor date: `{snapshot.get('anchor_date', '')}`",
        f"- Data cutoff: `{snapshot.get('data_cutoff_date', '')}`",
        "",
        "## Market regime",
        "",
    ]
    if regime:
        lines.extend(_mapping_lines(regime))
    else:
        lines.append("No market-regime artifact is available.")
    lines.extend(["", "## Sector states", ""])
    lines.extend(
        _table_or_empty(
            sectors,
            (
                "sector_rank",
                "sector_system",
                "sector_code",
                "sector_name",
                "sector_gate_status",
                "sector_research_eligibility",
                "sector_recovery_state",
                "sector_low_date_20d",
                "sector_low_close_20d",
                "sector_recovery_from_low_20d",
                "sector_days_since_low_20d",
                "sector_volume_ratio_5_20",
                "sector_ma5_slope_5d",
                "sector_ma10_slope_10d",
                "sector_oversold_score",
                "sector_repairability_score",
                "sector_direction_score",
            ),
            "No sector rows are present.",
        )
    )
    lines.extend(["", "## Sector lifecycle revisions", ""])
    lines.extend(
        _table_or_empty(
            _sector_revision_rows(sectors),
            (
                "sector_system",
                "sector_code",
                "sector_name",
                "sector_revision_status",
                "sector_rank_delta",
                "sector_recovery_state_delta",
            ),
            "No sector lifecycle revisions are present.",
        )
    )
    lines.extend(["", "## Selected stocks", ""])
    selected = _selected_stocks(stocks)
    lines.extend(
        _table_or_empty(
            selected,
            (
                "stock_rank",
                "asset_id",
                "sector_system",
                "sector_code",
                "sector_name",
                "stock_score",
                "stock_lifecycle",
                "market_regime",
            ),
            "No active stock candidates are present.",
        )
    )
    lines.extend(["", "## Lifecycle revisions", ""])
    lifecycle = _revision_rows(stocks)
    lines.extend(
        _table_or_empty(
            lifecycle,
            (
                "asset_id",
                "stock_rank",
                "stock_lifecycle",
                "previous_snapshot_id",
                "rank_delta",
                "lifecycle_delta",
                "score_reason",
            ),
            "No stock lifecycle revisions are present.",
        )
    )
    lines.extend(["", "## Evaluation (1/3/5 sessions)", ""])
    lines.extend(_evaluation_lines(detail, summary))
    lines.extend(["", "## Focus patterns", ""])
    lines.extend(_focus_lines(patterns, sectors, selected))
    lines.extend(["", "## Data gaps", ""])
    lines.extend(
        _table_or_empty(
            gaps,
            ("dataset", "asset_id", "start_date", "end_date", "expected_rows", "actual_rows", "reason"),
            "No data gaps were recorded.",
        )
    )
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / REPORT_NAME
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _path_part(path: Path, prefix: str) -> str:
    return path.name.removeprefix(prefix) if path.name.startswith(prefix) else ""


def latest_rolling_evaluation_directory(snapshot_dir: str | Path) -> Path | None:
    """Return the newest complete evaluation sidecar directory for a snapshot."""

    directory = Path(snapshot_dir).expanduser().resolve()
    direct = directory / "evaluation_detail.csv"
    direct_summary = directory / "evaluation_summary.csv"
    candidates: list[tuple[int, Path]] = []
    if direct.is_file() and direct_summary.is_file():
        candidates.append((0, directory))
    for revision in directory.glob("evaluation_revision=*"):
        match = re.fullmatch(r"evaluation_revision=(\d+)", revision.name)
        if match is None:
            continue
        if (revision / "evaluation_detail.csv").is_file() and (
            revision / "evaluation_summary.csv"
        ).is_file():
            candidates.append((int(match.group(1)), revision))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _frame(value: object) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if not isinstance(value, pd.DataFrame):
        raise TypeError("report frames must be pandas DataFrames")
    return value.copy(deep=True)


def _mapping_lines(mapping: dict[str, object]) -> list[str]:
    return [f"- {key}: `{_text(value)}`" for key, value in sorted(mapping.items())]


def _selected_stocks(stocks: pd.DataFrame) -> pd.DataFrame:
    if stocks.empty or "stock_rank" not in stocks:
        return stocks.copy(deep=True)
    ranks = pd.to_numeric(stocks["stock_rank"], errors="coerce")
    return stocks.loc[ranks.notna()].copy()


def _revision_rows(stocks: pd.DataFrame) -> pd.DataFrame:
    if stocks.empty:
        return stocks.copy(deep=True)
    columns = [column for column in ("rank_delta", "lifecycle_delta", "score_reason") if column in stocks]
    if not columns:
        return stocks.iloc[0:0].copy()
    values = stocks.loc[:, columns].fillna("").astype(str)
    return stocks.loc[values.ne("").any(axis=1)].copy()


def _sector_revision_rows(sectors: pd.DataFrame) -> pd.DataFrame:
    if sectors.empty:
        return sectors.copy(deep=True)
    columns = [
        column
        for column in (
            "sector_revision_status",
            "sector_rank_delta",
            "sector_recovery_state_delta",
        )
        if column in sectors
    ]
    if not columns:
        return sectors.iloc[0:0].copy()
    values = sectors.loc[:, columns].fillna("").astype(str)
    return sectors.loc[values.ne("").any(axis=1)].copy()


def _evaluation_lines(detail: pd.DataFrame, summary: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    if not detail.empty and "forward_horizon_days" in detail:
        horizons = pd.to_numeric(detail["forward_horizon_days"], errors="coerce")
        statuses = detail.get("evaluation_status", pd.Series("pending", index=detail.index)).astype("string").fillna("pending")
        for horizon in (1, 3, 5):
            mask = horizons.eq(horizon)
            if not mask.any():
                lines.append(f"- {horizon}d: no rows")
                continue
            selected = statuses.loc[mask]
            complete = int(selected.eq("complete").sum())
            pending = int(selected.eq("pending").sum())
            excluded = int(selected.str.startswith("excluded_").sum())
            data_error = int(selected.eq("data_error").sum())
            lines.append(
                f"- {horizon}d: completed={complete}; pending={pending}; excluded={excluded}; data_error={data_error}"
            )
    else:
        lines.append("No evaluation detail is available.")
    overall = summary
    if not overall.empty and {"group_by", "forward_horizon_days"}.issubset(overall.columns):
        overall = overall.loc[overall["group_by"].astype(str).eq("overall")]
        if not overall.empty:
            lines.extend(["", "Evaluation summary:", ""])
            lines.extend(
                _table_or_empty(
                    overall,
                    (
                        "forward_horizon_days",
                        "total_count",
                        "complete_count",
                        "pending_count",
                        "excluded_count",
                        "data_error_count",
                        "mean_return",
                        "hit_3pct_rate",
                        "hit_5pct_rate",
                        "hit_7pct_rate",
                    ),
                    "",
                )
            )
    return lines


def _focus_patterns(value: Sequence[str] | str | None) -> tuple[str, ...]:
    values = value.split(",") if isinstance(value, str) else (value or ())
    return tuple(sorted({str(item).strip() for item in values if str(item).strip()}))


def _focus_lines(patterns: tuple[str, ...], sectors: pd.DataFrame, stocks: pd.DataFrame) -> list[str]:
    if not patterns:
        return ["No focus patterns were supplied."]
    lines = [f"Patterns: {', '.join(f'`{pattern}`' for pattern in patterns)}", ""]
    for pattern in patterns:
        matched_sectors = _matches(sectors, pattern)
        matched_stocks = _matches(stocks, pattern)
        lines.extend([f"### {pattern}", "", "Matching sectors:", ""])
        lines.extend(
            _table_or_empty(
                matched_sectors,
                ("sector_system", "sector_code", "sector_name", "sector_gate_status", "sector_recovery_state"),
                "No matching sector rows.",
            )
        )
        lines.extend(["", "Matching selected stocks:", ""])
        lines.extend(
            _table_or_empty(
                matched_stocks,
                ("stock_rank", "asset_id", "sector_name", "stock_lifecycle", "stock_score"),
                "No matching selected-stock rows.",
            )
        )
        lines.append("")
    return lines


def _matches(frame: pd.DataFrame, pattern: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy(deep=True)
    needle = pattern.casefold()
    matched = frame.fillna("").astype(str).apply(
        lambda row: any(needle in value.casefold() for value in row), axis=1
    )
    return frame.loc[matched].copy()


def _gap_frame(preflight: dict[str, object], backfill: object) -> pd.DataFrame:
    gaps = preflight.get("gaps", [])
    preflight_frame = pd.DataFrame(gaps) if isinstance(gaps, list) else pd.DataFrame()
    backfill_frame = _frame(backfill) if backfill is not None else pd.DataFrame()
    if preflight_frame.empty:
        return backfill_frame
    if backfill_frame.empty:
        return preflight_frame
    combined = pd.concat([preflight_frame, backfill_frame], ignore_index=True, sort=False)
    columns = [column for column in ("dataset", "asset_id", "reason") if column in combined]
    return combined.drop_duplicates(columns, keep="first") if columns else combined


def _table_or_empty(frame: pd.DataFrame, preferred: Iterable[str], empty_message: str) -> list[str]:
    if frame.empty:
        return [empty_message] if empty_message else []
    columns = [column for column in preferred if column in frame.columns]
    if not columns:
        columns = list(frame.columns)
    rows = frame.loc[:, columns]
    header = "| " + " | ".join(_escape(column) for column in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_escape(_text(value)) for value in row) + " |"
        for row in rows.itertuples(index=False, name=None)
    ]
    return [header, separator, *body]


def _escape(value: object) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")


def _text(value: object) -> str:
    if value is None or value is pd.NA:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)
