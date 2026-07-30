from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

from .contracts import (
    LEGACY_OUTPUT_FILENAMES,
    REPAIR_BUCKETS,
    UNIFIED_OUTPUT_FILENAMES,
    validate_trade_date,
)


EVALUATION_FILENAMES = {
    "detail": "consumer_oversold_forward_evaluation_detail.csv",
    "summary": "consumer_oversold_forward_evaluation_summary.csv",
    "report": "consumer_oversold_forward_evaluation_report.md",
}
EVALUATION_MANIFEST_FILENAME = ".manifest.sha256"

_SNAPSHOT_COLUMNS = (
    "trade_date",
    "asset_id",
    "stock_code",
    "stock_name",
    "consumer_subindustry",
    "repair_bucket",
)
_BAR_COLUMNS = (
    "snapshot_trade_date",
    "asset_id",
    "consumer_subindustry",
    "trade_date",
    "close",
)
_RELEASE_SCHEMAS = {
    "legacy": LEGACY_OUTPUT_FILENAMES,
    "unified": UNIFIED_OUTPUT_FILENAMES,
}


def _required_columns(frame: pd.DataFrame, columns: Iterable[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _normalized_horizons(horizons: Iterable[int]) -> tuple[int, ...]:
    normalized = tuple(horizons)
    if not normalized or any(type(value) is not int or value <= 0 for value in normalized):
        raise ValueError("horizons must contain positive integers")
    if len(set(normalized)) != len(normalized):
        raise ValueError("horizons must be unique")
    return tuple(sorted(normalized))


def _asset_horizon(
    history: pd.DataFrame, trade_date: str, horizon_date: pd.Timestamp | None
) -> dict[str, float] | None:
    if horizon_date is None:
        return None
    ordered = history.sort_values("trade_date", kind="stable").drop_duplicates(
        "trade_date", keep="last"
    ).reset_index(drop=True)
    entry_rows = ordered.loc[ordered["trade_date"].eq(pd.Timestamp(trade_date))]
    target_rows = ordered.loc[ordered["trade_date"].eq(horizon_date)]
    if entry_rows.empty or target_rows.empty:
        return None
    entry_index = int(entry_rows.index[-1])
    target_index = int(target_rows.index[-1])
    path = pd.to_numeric(
        ordered.iloc[entry_index : target_index + 1]["close"], errors="coerce"
    )
    if path.isna().any() or not np.isfinite(path).all() or (path <= 0).any():
        return None
    entry = float(path.iloc[0])
    target = float(path.iloc[-1])
    drawdown = path / path.cummax() - 1.0
    return {
        "forward_return": target / entry - 1.0,
        "path_max_drawdown": float(drawdown.min()),
        "horizon_trade_date": ordered.iloc[target_index]["trade_date"].date().isoformat(),
    }


def evaluate_consumer_oversold_snapshots(
    snapshots: pd.DataFrame,
    bars: pd.DataFrame,
    horizons: Iterable[int] = (5, 20),
) -> dict[str, pd.DataFrame]:
    """Evaluate immutable weekly selections against subsequent hfq closes."""
    if not isinstance(snapshots, pd.DataFrame) or not isinstance(bars, pd.DataFrame):
        raise TypeError("snapshots and bars must be pandas DataFrames")
    _required_columns(snapshots, _SNAPSHOT_COLUMNS, "snapshots")
    _required_columns(bars, _BAR_COLUMNS, "bars")
    horizon_values = _normalized_horizons(horizons)

    selected_columns = [*_SNAPSHOT_COLUMNS]
    if "snapshot_rank" in snapshots.columns:
        selected_columns.append("snapshot_rank")
    selected = snapshots.loc[:, selected_columns].copy(deep=True)
    selected["trade_date"] = selected["trade_date"].map(validate_trade_date)
    selected["asset_id"] = selected["asset_id"].astype(str).str.strip()
    if selected["asset_id"].eq("").any():
        raise ValueError("snapshots asset_id must be non-empty")
    if selected.duplicated(["trade_date", "asset_id"]).any():
        raise ValueError("snapshots must contain unique trade_date and asset_id pairs")
    invalid_buckets = sorted(set(selected["repair_bucket"].astype(str)) - set(REPAIR_BUCKETS))
    if invalid_buckets:
        raise ValueError(f"snapshots contain invalid repair_bucket: {', '.join(invalid_buckets)}")

    market = bars.loc[:, _BAR_COLUMNS].copy(deep=True)
    market["snapshot_trade_date"] = market["snapshot_trade_date"].map(validate_trade_date)
    market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce")
    market["close"] = pd.to_numeric(market["close"], errors="coerce")
    market["asset_id"] = market["asset_id"].astype(str).str.strip()
    market = market.loc[market["trade_date"].notna()].copy()

    rows: list[dict[str, Any]] = []
    snapshot_calendars = {
        snapshot_date: sorted(group["trade_date"].dropna().unique())
        for snapshot_date, group in market.groupby("snapshot_trade_date", sort=True)
    }
    for snapshot in selected.sort_values(["trade_date", "repair_bucket", "asset_id"]).to_dict(
        orient="records"
    ):
        trade_date = str(snapshot["trade_date"])
        subindustry = str(snapshot["consumer_subindustry"])
        snapshot_bars = market.loc[
            market["snapshot_trade_date"].eq(trade_date)
            & market["consumer_subindustry"].astype(str).eq(subindustry)
        ]
        target_history = snapshot_bars.loc[
            snapshot_bars["asset_id"].eq(str(snapshot["asset_id"]))
        ]
        market_dates = snapshot_calendars.get(trade_date, [])
        try:
            entry_position = market_dates.index(pd.Timestamp(trade_date))
        except ValueError:
            entry_position = -1
        for horizon in horizon_values:
            horizon_position = entry_position + horizon
            horizon_date = (
                pd.Timestamp(market_dates[horizon_position])
                if entry_position >= 0 and horizon_position < len(market_dates)
                else None
            )
            target = _asset_horizon(target_history, trade_date, horizon_date)
            peer_returns = []
            for _, peer_history in snapshot_bars.groupby("asset_id", sort=True):
                outcome = _asset_horizon(peer_history, trade_date, horizon_date)
                if outcome is not None:
                    peer_returns.append(outcome["forward_return"])
            industry_return = float(np.mean(peer_returns)) if peer_returns else math.nan
            completed = target is not None and math.isfinite(industry_return)
            forward_return = target["forward_return"] if completed else math.nan
            excess_return = forward_return - industry_return if completed else math.nan
            rows.append(
                {
                    **snapshot,
                    "horizon": horizon,
                    "evaluation_status": "completed" if completed else "pending",
                    "horizon_trade_date": target["horizon_trade_date"] if completed else "",
                    "forward_return": forward_return,
                    "industry_forward_return": industry_return if completed else math.nan,
                    "excess_return": excess_return,
                    "path_max_drawdown": target["path_max_drawdown"] if completed else math.nan,
                    "excess_win": bool(excess_return > 0.0) if completed else pd.NA,
                    "industry_completed_assets": len(peer_returns),
                }
            )

    detail = pd.DataFrame(rows)
    summary_rows: list[dict[str, Any]] = []
    if not detail.empty:
        for (bucket, horizon), group in detail.groupby(
            ["repair_bucket", "horizon"], sort=True, dropna=False
        ):
            completed = group.loc[group["evaluation_status"].eq("completed")]
            summary_rows.append(
                {
                    "repair_bucket": bucket,
                    "horizon": int(horizon),
                    "completed_count": int(len(completed)),
                    "pending_count": int(group["evaluation_status"].eq("pending").sum()),
                    "win_rate": float(completed["excess_win"].astype(float).mean())
                    if not completed.empty
                    else math.nan,
                    "median_return": float(completed["forward_return"].median())
                    if not completed.empty
                    else math.nan,
                    "median_excess_return": float(completed["excess_return"].median())
                    if not completed.empty
                    else math.nan,
                    "median_path_max_drawdown": float(completed["path_max_drawdown"].median())
                    if not completed.empty
                    else math.nan,
                }
            )
    summary = pd.DataFrame(summary_rows)
    return {"detail": detail.reset_index(drop=True), "summary": summary.reset_index(drop=True)}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified_release(release: Path) -> str | None:
    manifest = release / ".manifest.sha256"
    try:
        release_mode = release.lstat().st_mode
        if not stat.S_ISDIR(release_mode) or release_mode & 0o222:
            return None
        manifest_mode = manifest.lstat().st_mode
        if not stat.S_ISREG(manifest_mode) or manifest_mode & 0o222:
            return None
        entries: dict[str, str] = {}
        for line in manifest.read_text(encoding="utf-8").splitlines():
            digest, filename = line.split("  ", 1)
            if filename in entries:
                return None
            entries[filename] = digest
        schema = next(
            (
                identifier
                for identifier, filenames in _RELEASE_SCHEMAS.items()
                if set(entries) == set(filenames.values())
            ),
            None,
        )
        if schema is None:
            return None
        required = set(_RELEASE_SCHEMAS[schema].values())
        if {path.name for path in release.iterdir()} != {EVALUATION_MANIFEST_FILENAME, *required}:
            return None
        valid = all(
            stat.S_ISREG((release / filename).lstat().st_mode)
            and not ((release / filename).lstat().st_mode & 0o222)
            and entries[filename] == _digest(release / filename)
            for filename in required
        )
        return schema if valid else None
    except (OSError, ValueError):
        return None


def _release_frames(release: Path, end_date: str) -> tuple[str, pd.DataFrame, pd.DataFrame] | None:
    schema = _verified_release(release)
    if schema is None:
        return None
    filenames = _RELEASE_SCHEMAS[schema]
    try:
        coverage = json.loads(
            (release / filenames["coverage"]).read_text(encoding="utf-8")
        )
        trade_date = validate_trade_date(coverage["trade_date"])
        if trade_date > end_date:
            return None
        scores = pd.read_csv(release / filenames["scores"], dtype=str)
        evidence = pd.read_csv(release / filenames["evidence"], dtype=str)
        if schema == "legacy":
            expected = pd.read_csv(release / filenames["expected"], dtype=str)
            early = pd.read_csv(release / filenames["early"], dtype=str)
            selected_parts = []
            for frame, bucket in zip((expected, early), REPAIR_BUCKETS, strict=True):
                _required_columns(
                    frame,
                    (
                        "asset_id",
                        "stock_code",
                        "stock_name",
                        "consumer_subindustry",
                        "repair_bucket",
                        "bucket_rank",
                    ),
                    bucket,
                )
                if not frame.empty and not frame["repair_bucket"].eq(bucket).all():
                    return None
                selected_parts.append(frame)
            selected = pd.concat(selected_parts, ignore_index=True)
            selected["snapshot_rank"] = pd.to_numeric(
                selected["bucket_rank"], errors="coerce"
            )
        else:
            if coverage.get("publication_status") != "ready":
                return None
            final_top_n = coverage.get("final_top_n")
            if type(final_top_n) is not int or final_top_n <= 0:
                return None
            selected = pd.read_csv(release / filenames["top20"], dtype=str)
            _required_columns(
                selected,
                (
                    "asset_id",
                    "stock_code",
                    "stock_name",
                    "consumer_subindustry",
                    "repair_bucket",
                    "final_rank",
                ),
                "top20",
            )
            if len(selected) != final_top_n:
                return None
            selected["snapshot_rank"] = pd.to_numeric(
                selected["final_rank"], errors="coerce"
            )
        if selected["snapshot_rank"].isna().any():
            return None
        _required_columns(evidence, ("asset_id", "repair_bucket"), "evidence")
        if not selected.empty:
            matched = selected.loc[:, ["asset_id", "repair_bucket"]].merge(
                evidence.loc[:, ["asset_id", "repair_bucket"]],
                on=["asset_id", "repair_bucket"],
                how="left",
                indicator=True,
            )
            if not matched["_merge"].eq("both").all():
                return None
        selected = selected.assign(trade_date=trade_date, snapshot_release=str(release))
        selected = selected.loc[:, [*_SNAPSHOT_COLUMNS, "snapshot_rank", "snapshot_release"]]
        _required_columns(scores, ("asset_id", "consumer_subindustry"), "scores")
        membership = scores.loc[:, ["asset_id", "consumer_subindustry"]].dropna().copy()
        membership["asset_id"] = membership["asset_id"].astype(str).str.strip()
        membership["consumer_subindustry"] = membership["consumer_subindustry"].astype(str).str.strip()
        membership = membership.loc[
            membership["asset_id"].ne("") & membership["consumer_subindustry"].ne("")
        ].drop_duplicates("asset_id", keep="first")
        selected_ids = set(selected["asset_id"].astype(str))
        if not selected_ids.issubset(set(membership["asset_id"])):
            return None
        membership["snapshot_trade_date"] = trade_date
        return trade_date, selected, membership
    except (OSError, ValueError, KeyError, json.JSONDecodeError, pd.errors.ParserError):
        return None


def _discover_snapshots(root: Path, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    releases: dict[Path, int] = {}
    if _verified_release(root):
        releases[root.resolve()] = 2
    for current in root.rglob("current"):
        if current.is_symlink():
            try:
                releases[current.resolve(strict=True)] = 2
            except OSError:
                continue
    for releases_dir in root.rglob(".releases"):
        if not releases_dir.is_dir():
            continue
        for release in releases_dir.glob("consumer-oversold-*"):
            resolved = release.resolve()
            releases[resolved] = max(releases.get(resolved, 0), 1)

    by_date: dict[str, tuple[int, str, pd.DataFrame, pd.DataFrame]] = {}
    for release, priority in sorted(releases.items(), key=lambda item: str(item[0])):
        loaded = _release_frames(release, end_date)
        if loaded is None:
            continue
        trade_date, selected, membership = loaded
        candidate = (priority, str(release), selected, membership)
        if trade_date not in by_date or candidate[:2] > by_date[trade_date][:2]:
            by_date[trade_date] = candidate
    if not by_date:
        raise ValueError("no valid sealed consumer oversold snapshots")
    selected = pd.concat([by_date[key][2] for key in sorted(by_date)], ignore_index=True)
    membership = pd.concat([by_date[key][3] for key in sorted(by_date)], ignore_index=True)
    return selected, membership


def _load_evaluation_bars(
    *, asset_ids: list[str], start_date: str, end_date: str, service: str
) -> pd.DataFrame:
    start = validate_trade_date(start_date)
    end = validate_trade_date(end_date)
    assets = sorted({str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()})
    if not assets:
        return pd.DataFrame(columns=["asset_id", "trade_date", "close"])
    sql = """
    SELECT asset_id, trade_date, close
    FROM market_daily_bar
    WHERE trade_date BETWEEN %s AND %s
      AND asset_id = ANY(%s)
      AND adjust_type = 'hfq'
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [start, end, assets])
    frame = pd.DataFrame(rows, columns=["asset_id", "trade_date", "close"])
    if frame.empty:
        return frame
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.loc[
        frame["trade_date"].between(pd.Timestamp(start), pd.Timestamp(end), inclusive="both")
    ]
    frame["trade_date"] = frame["trade_date"].dt.date.astype(str)
    return frame.sort_values(["asset_id", "trade_date"], kind="stable").reset_index(drop=True)


def _expand_bars(raw: pd.DataFrame, membership: pd.DataFrame, end_date: str) -> pd.DataFrame:
    parts = []
    for snapshot_date, members in membership.groupby("snapshot_trade_date", sort=True):
        part = raw.merge(members.loc[:, ["asset_id", "consumer_subindustry"]], on="asset_id")
        part = part.loc[
            part["trade_date"].astype(str).between(str(snapshot_date), end_date, inclusive="both")
        ].copy()
        part["snapshot_trade_date"] = str(snapshot_date)
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=_BAR_COLUMNS)
    return pd.concat(parts, ignore_index=True).loc[:, _BAR_COLUMNS]


def _escape_csv_formula(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    safe = frame.copy(deep=True)
    for column in safe.columns:
        safe[column] = safe[column].map(_escape_csv_formula)
    safe.to_csv(path, index=False, encoding="utf-8")
    _fsync_file(path)


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _write_and_verify_evaluation_manifest(release: Path) -> Path:
    manifest = release / EVALUATION_MANIFEST_FILENAME
    lines = [
        f"{_digest(release / filename)}  {filename}"
        for filename in sorted(EVALUATION_FILENAMES.values())
    ]
    _write_text(manifest, "\n".join(lines) + "\n")
    parsed: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split("  ", 1)
        parsed[filename] = digest
    expected_names = sorted(EVALUATION_FILENAMES.values())
    if list(parsed) != expected_names or any(
        parsed[filename] != _digest(release / filename) for filename in expected_names
    ):
        raise ValueError("evaluation release manifest verification failed")
    return manifest


def _render_report(end_date: str, detail: pd.DataFrame, summary: pd.DataFrame) -> str:
    lines = [
        "# 消费超跌修复候选前瞻评估",
        "",
        f"- 评估截止日：{end_date}",
        "- 收益口径：后复权（hfq）收盘价；仅评估历史 sealed snapshot 的固定成员。",
        "",
        "## 汇总",
        "",
    ]
    if summary.empty:
        lines.append("暂无可评估快照。")
    else:
        lines.extend(
            [
                "| 修复桶 | 交易日 | 完成 | 待评估 | 超额胜率 | 收益中位数 | 超额收益中位数 | 路径最大回撤中位数 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in summary.to_dict(orient="records"):
            def pct(value: Any) -> str:
                return "待评估" if pd.isna(value) else f"{float(value):.2%}"

            lines.append(
                f"| {row['repair_bucket']} | {row['horizon']} | {row['completed_count']} | "
                f"{row['pending_count']} | {pct(row['win_rate'])} | {pct(row['median_return'])} | "
                f"{pct(row['median_excess_return'])} | {pct(row['median_path_max_drawdown'])} |"
            )
    lines.extend(["", f"- 明细行数：{len(detail)}", ""])
    return "\n".join(lines)


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        path.chmod(0o755)
        shutil.rmtree(path)


def _restore_current(output_dir: Path, old_target: str | None) -> None:
    current = output_dir / "current"
    if old_target is None:
        current.unlink(missing_ok=True)
        return
    recovery = output_dir / f".consumer-oversold-evaluation-current-recovery-{uuid.uuid4().hex}"
    try:
        os.symlink(old_target, recovery)
        os.replace(recovery, current)
    finally:
        recovery.unlink(missing_ok=True)


def _publish_release(
    output_dir: Path, detail: pd.DataFrame, summary: pd.DataFrame, report: str
) -> dict[str, str]:
    releases = output_dir / ".releases"
    releases.mkdir(exist_ok=True)
    identifier = uuid.uuid4().hex
    staging = releases / f".consumer-oversold-evaluation-staging-{identifier}"
    release = releases / f"consumer-oversold-evaluation-{identifier}"
    temp_link = output_dir / f".consumer-oversold-evaluation-current-{identifier}"
    current = output_dir / "current"
    old_target: str | None = None
    if current.is_symlink():
        old_target = os.readlink(current)
    elif current.exists():
        raise ValueError("output_dir/current must be a symlink managed by this publisher")
    staging.mkdir()
    switched = False
    preserve_release = False
    try:
        _write_csv(detail, staging / EVALUATION_FILENAMES["detail"])
        _write_csv(summary, staging / EVALUATION_FILENAMES["summary"])
        _write_text(staging / EVALUATION_FILENAMES["report"], report)
        manifest = _write_and_verify_evaluation_manifest(staging)
        for filename in (*EVALUATION_FILENAMES.values(), manifest.name):
            artifact = staging / filename
            artifact.chmod(0o444)
            _fsync_file(artifact)
        staging.chmod(0o555)
        _fsync_dir(staging)
        os.replace(staging, release)
        _fsync_dir(releases)
        os.symlink(str(Path(".releases") / release.name), temp_link)
        os.replace(temp_link, current)
        switched = True
        try:
            _fsync_dir(output_dir)
        except OSError as publication_error:
            try:
                _restore_current(output_dir, old_target)
                _fsync_dir(output_dir)
            except BaseException as rollback_error:
                preserve_release = True
                failure = RuntimeError(
                    f"evaluation publication failed and rollback incomplete: {rollback_error}"
                )
                raise failure from publication_error
            switched = False
            raise
    finally:
        _remove(staging)
        temp_link.unlink(missing_ok=True)
        if not switched and not preserve_release:
            _remove(release)
    return {
        key: str(output_dir / "current" / filename)
        for key, filename in EVALUATION_FILENAMES.items()
    }


def _publish(
    output_dir: Path, detail: pd.DataFrame, summary: pd.DataFrame, report: str
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_handle = (output_dir / ".publish.lock").open("a+b")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        return _publish_release(output_dir, detail, summary, report)
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()


def _safe_path(value: str | Path, name: str) -> Path:
    text = str(value)
    if not text or any(character in text for character in ("|", "\r", "\n")):
        raise ValueError(f"{name} contains unsafe path characters")
    return Path(text).expanduser().resolve()


def _overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def run_consumer_oversold_evaluation(
    *,
    snapshots_root: str | Path,
    end_date: str,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    """Load sealed weekly snapshots, evaluate them through end_date, and publish artifacts."""
    cutoff = validate_trade_date(end_date)
    root = _safe_path(snapshots_root, "snapshots_root")
    destination = _safe_path(output_dir, "output_dir")
    if _overlap(root, destination):
        raise ValueError("snapshots_root and output_dir must not overlap")
    if not root.is_dir():
        raise ValueError("snapshots_root must be an existing directory")
    snapshots, membership = _discover_snapshots(root, cutoff)
    raw = _load_evaluation_bars(
        asset_ids=membership["asset_id"].astype(str).tolist(),
        start_date=str(snapshots["trade_date"].min()),
        end_date=cutoff,
        service=service,
    )
    bars = _expand_bars(raw, membership, cutoff)
    evaluated = evaluate_consumer_oversold_snapshots(snapshots, bars)
    report = _render_report(cutoff, evaluated["detail"], evaluated["summary"])
    paths = _publish(destination, evaluated["detail"], evaluated["summary"], report)
    return {"paths": paths, **evaluated, "report": report}
