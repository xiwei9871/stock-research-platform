from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from .contracts import validate_trade_date


GROUPS = {
    "top20": lambda rank: rank <= 20,
    "top30": lambda rank: rank <= 30,
    "01-10": lambda rank: rank <= 10,
    "11-20": lambda rank: 11 <= rank <= 20,
    "21-30": lambda rank: 21 <= rank <= 30,
}

_DAILY_REQUIRED_COLUMNS = (
    "asset_id",
    "trade_date",
    "hfq_close",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
)
_MINUTE_REQUIRED_COLUMNS = (
    "asset_id",
    "trade_date",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "limit_up_price",
)
_DETAIL_COLUMNS = (
    "trade_date",
    "asset_id",
    "final_rank",
    "horizon",
    "horizon_trade_date",
    "evaluation_status",
    "entry_hfq_close",
    "horizon_hfq_close",
    "forward_return",
    "path_max_drawdown",
    "max_high_return",
    "high_to_close_fade",
    "retention_ratio",
)
_SUMMARY_COLUMNS = (
    "group",
    "horizon",
    "horizon_trade_date",
    "member_count",
    "completed_count",
    "pending_count",
    "rising_count",
    "rising_ratio",
    "mean_return",
    "median_return",
    "positive_mean_return",
    "gte_3pct_count",
    "gte_3pct_ratio",
    "gte_5pct_count",
    "gte_5pct_ratio",
    "gte_7pct_count",
    "gte_7pct_ratio",
    "reached_3pct_not_retained_count",
    "reached_3pct_not_retained_ratio",
    "reached_5pct_not_retained_count",
    "reached_5pct_not_retained_ratio",
    "reached_7pct_not_retained_count",
    "reached_7pct_not_retained_ratio",
    "median_path_max_drawdown",
    "median_max_high_return",
    "median_high_to_close_fade",
    "median_retention_ratio",
    "extreme_loss_count",
    "extreme_loss_ratio",
    "spearman_rank_correlation",
    "qualified_pool_benchmark_status",
    "qualified_pool_member_count",
    "qualified_pool_completed_count",
    "qualified_pool_mean_return",
    "qualified_pool_excess_return",
    "breadth_quality",
    "repair_strength",
    "risk_and_retention",
    "balanced_evaluation",
    "group_evaluation_status",
    "overall_evaluation",
)
_MINUTE_DETAIL_COLUMNS = (
    "trade_date",
    "asset_id",
    "final_rank",
    "horizon",
    "outcome_trade_date",
    "bar_count",
    "first_high_time",
    "intraday_max_return",
    "above_entry_bar_ratio",
    "morning_close_return",
    "morning_retention",
    "afternoon_close_return",
    "afternoon_retention",
    "limit_up_reached",
    "first_limit_up_time",
    "limit_up_held_to_close",
)
_CANONICAL_MINUTE_TIMES = frozenset(
    pd.Timestamp(value).time()
    for value in (
        *pd.date_range("09:35", "11:30", freq="5min").tolist(),
        *pd.date_range("13:05", "15:00", freq="5min").tolist(),
    )
)


def _required_columns(frame: pd.DataFrame, columns: Iterable[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _normalized_horizons(horizons: Iterable[int]) -> tuple[int, ...]:
    values = tuple(horizons)
    if not values or any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("horizons must contain positive integers")
    if len(set(values)) != len(values):
        raise ValueError("horizons must be unique")
    return tuple(sorted(values))


def _normalized_outcome_dates(
    values: Iterable[str], snapshot_trade_date: str
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("outcome_dates must be an ordered iterable of dates")
    try:
        parsed = tuple(validate_trade_date(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError("outcome_dates must contain valid dates") from exc
    if parsed and parsed[0] == snapshot_trade_date:
        parsed = parsed[1:]
    if len(set(parsed)) != len(parsed):
        raise ValueError("outcome_dates must contain unique dates")
    if any(value <= snapshot_trade_date for value in parsed):
        raise ValueError("outcome_dates must be strictly after snapshot trade_date")
    if tuple(sorted(parsed)) != parsed:
        raise ValueError("outcome_dates must be strictly ordered")
    return parsed


def _resolve_outcome_dates(
    daily_bars: pd.DataFrame,
    snapshot_trade_date: str,
    outcome_dates: Iterable[str] | None,
) -> tuple[str, ...]:
    if outcome_dates is None:
        attrs = getattr(daily_bars, "attrs", {})
        outcome_dates = attrs.get("outcome_dates")
        if outcome_dates is None:
            outcome_dates = attrs.get("outcome_calendar")
        if isinstance(outcome_dates, pd.DataFrame):
            if "trade_date" not in outcome_dates.columns:
                raise ValueError("authoritative outcome calendar must contain trade_date")
            outcome_dates = outcome_dates["trade_date"].tolist()
        if outcome_dates is None:
            raise ValueError(
                "authoritative outcome calendar is required; pass outcome_dates or set daily_bars.attrs"
            )
    return _normalized_outcome_dates(outcome_dates, snapshot_trade_date)


def _normalize_asset_ids(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    result = frame.copy(deep=True)
    if not result["asset_id"].map(
        lambda value: isinstance(value, str) and bool(value.strip())
    ).all():
        raise ValueError(f"{name} asset_id must contain non-empty strings")
    result["asset_id"] = result["asset_id"].str.strip()
    if result.duplicated("asset_id").any():
        raise ValueError(f"{name} must contain unique asset_id rows")
    return result


def _single_trade_date(frame: pd.DataFrame, name: str) -> str:
    _required_columns(frame, ("trade_date",), name)
    dates = frame["trade_date"].map(validate_trade_date)
    unique = dates.unique().tolist()
    if len(unique) != 1:
        raise ValueError(f"{name} must contain exactly one trade_date")
    return str(unique[0])


def _validate_snapshot(snapshot: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if not isinstance(snapshot, pd.DataFrame):
        raise TypeError("snapshot must be a pandas DataFrame")
    _required_columns(snapshot, ("trade_date", "asset_id", "final_rank"), "snapshot")
    selected = _normalize_asset_ids(snapshot, "snapshot")
    trade_date = _single_trade_date(selected, "snapshot")
    ranks = pd.to_numeric(selected["final_rank"], errors="coerce")
    valid = (
        not selected["final_rank"].map(lambda value: isinstance(value, (bool, np.bool_))).any()
        and ranks.notna().all()
        and np.isfinite(ranks).all()
        and ranks.gt(0).all()
        and ranks.eq(np.floor(ranks)).all()
        and sorted(ranks.astype(int).tolist()) == list(range(1, len(selected) + 1))
    )
    if not valid:
        raise ValueError("snapshot must contain consecutive positive final_rank values")
    selected["trade_date"] = trade_date
    selected["final_rank"] = ranks.astype(int)
    return selected.sort_values("final_rank", kind="stable").reset_index(drop=True), trade_date


def _validate_qualified_pool(
    qualified_pool: pd.DataFrame,
    snapshot: pd.DataFrame,
    snapshot_trade_date: str,
) -> pd.DataFrame:
    if not isinstance(qualified_pool, pd.DataFrame):
        raise TypeError("qualified_pool must be a pandas DataFrame")
    _required_columns(qualified_pool, ("asset_id",), "qualified_pool")
    qualified = _normalize_asset_ids(qualified_pool, "qualified_pool")
    missing = sorted(set(snapshot["asset_id"]) - set(qualified["asset_id"]))
    if missing:
        raise ValueError("snapshot assets must be present in qualified_pool")
    if "trade_date" in qualified:
        qualified_date = _single_trade_date(qualified, "qualified_pool")
        if qualified_date != snapshot_trade_date:
            raise ValueError("qualified_pool trade_date must equal snapshot trade_date")
        qualified["trade_date"] = qualified_date
    else:
        qualified["trade_date"] = snapshot_trade_date
    if "final_rank" in qualified:
        ranks = pd.to_numeric(qualified["final_rank"], errors="coerce")
        if ranks.isna().any() or not np.isfinite(ranks).all():
            raise ValueError("qualified_pool final_rank must be finite when present")
        qualified["final_rank"] = ranks
    else:
        qualified["final_rank"] = pd.NA
    return qualified.sort_values(["final_rank", "asset_id"], kind="stable", na_position="last").reset_index(
        drop=True
    )


def _normalize_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(daily_bars, pd.DataFrame):
        raise TypeError("daily_bars must be a pandas DataFrame")
    source = daily_bars.copy(deep=True)
    aliases = {
        "hfq_close": ("close",),
        "raw_open": ("open",),
        "raw_high": ("high",),
        "raw_low": ("low",),
        "raw_close": ("close",),
    }
    for target, candidates in aliases.items():
        if target in source:
            continue
        replacement = next((column for column in candidates if column in source), None)
        if replacement is not None:
            source[target] = source[replacement]
    _required_columns(source, _DAILY_REQUIRED_COLUMNS, "daily_bars")
    frame = source.loc[:, _DAILY_REQUIRED_COLUMNS].copy(deep=True)
    if not frame["asset_id"].map(
        lambda value: isinstance(value, str) and bool(value.strip())
    ).all():
        raise ValueError("daily_bars asset_id must contain non-empty strings")
    frame["asset_id"] = frame["asset_id"].str.strip()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.normalize()
    if frame["trade_date"].isna().any():
        raise ValueError("daily_bars trade_date must contain valid dates")
    if frame.duplicated(["asset_id", "trade_date"]).any():
        raise ValueError("daily_bars must contain unique asset_id and trade_date pairs")
    for column in _DAILY_REQUIRED_COLUMNS[2:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["asset_id", "trade_date"], kind="stable").reset_index(drop=True)


def _outcome_calendar(
    snapshot_trade_date: str,
    horizons: tuple[int, ...],
    outcome_dates: tuple[str, ...],
) -> tuple[list[pd.Timestamp], dict[int, pd.Timestamp | None]]:
    cutoff = pd.Timestamp(snapshot_trade_date)
    future_dates = [pd.Timestamp(value) for value in outcome_dates]
    calendar = [cutoff, *future_dates]
    targets = {
        horizon: future_dates[horizon - 1] if horizon <= len(future_dates) else None
        for horizon in horizons
    }
    return calendar, targets


def _empty_outcome(
    row: dict[str, Any], horizon: int, target: pd.Timestamp | None, status: str
) -> dict[str, Any]:
    return {
        "trade_date": row["trade_date"],
        "asset_id": row["asset_id"],
        "final_rank": row.get("final_rank", pd.NA),
        "horizon": horizon,
        "horizon_trade_date": target.date().isoformat() if target is not None else "",
        "evaluation_status": status,
        "entry_hfq_close": math.nan,
        "horizon_hfq_close": math.nan,
        "forward_return": math.nan,
        "path_max_drawdown": math.nan,
        "max_high_return": math.nan,
        "high_to_close_fade": math.nan,
        "retention_ratio": math.nan,
    }


def _daily_forward_detail(
    members: pd.DataFrame,
    daily_bars: pd.DataFrame,
    snapshot_trade_date: str,
    horizons: tuple[int, ...],
    calendar: list[pd.Timestamp],
    targets: dict[int, pd.Timestamp | None],
) -> pd.DataFrame:
    cutoff = pd.Timestamp(snapshot_trade_date)
    rows: list[dict[str, Any]] = []
    for member in members.to_dict(orient="records"):
        history = daily_bars.loc[daily_bars["asset_id"].eq(member["asset_id"])].set_index(
            "trade_date"
        )
        for horizon in horizons:
            target = targets[horizon]
            if target is None:
                rows.append(_empty_outcome(member, horizon, target, "insufficient_outcome_calendar"))
                continue
            expected_dates = [value for value in calendar if cutoff <= value <= target]
            if cutoff not in history.index:
                rows.append(_empty_outcome(member, horizon, target, "missing_entry_bar"))
                continue
            if any(value not in history.index for value in expected_dates):
                rows.append(_empty_outcome(member, horizon, target, "missing_outcome_bar"))
                continue
            path = history.loc[expected_dates]
            numeric = path.loc[:, _DAILY_REQUIRED_COLUMNS[2:]]
            if (
                numeric.isna().any().any()
                or not np.isfinite(numeric.to_numpy(dtype=float)).all()
                or (numeric <= 0).any().any()
                or (path["raw_low"] > path["raw_high"]).any()
                or (path[["raw_open", "raw_close"]].max(axis=1) > path["raw_high"]).any()
                or (path[["raw_open", "raw_close"]].min(axis=1) < path["raw_low"]).any()
            ):
                rows.append(_empty_outcome(member, horizon, target, "invalid_daily_bar"))
                continue
            entry_hfq = float(path.iloc[0]["hfq_close"])
            target_hfq = float(path.iloc[-1]["hfq_close"])
            hfq_path = path["hfq_close"].astype(float)
            drawdown = hfq_path / hfq_path.cummax() - 1.0
            outcome_path = path.loc[path.index > cutoff]
            adjusted_high = outcome_path["raw_high"] * (
                outcome_path["hfq_close"] / outcome_path["raw_close"]
            )
            maximum_high = float(adjusted_high.max())
            max_high_return = maximum_high / entry_hfq - 1.0
            forward_return = target_hfq / entry_hfq - 1.0
            retention = (
                float(np.clip(forward_return / max_high_return, 0.0, 1.0))
                if max_high_return > 0.0
                else math.nan
            )
            rows.append(
                {
                    "trade_date": snapshot_trade_date,
                    "asset_id": member["asset_id"],
                    "final_rank": member.get("final_rank", pd.NA),
                    "horizon": horizon,
                    "horizon_trade_date": target.date().isoformat(),
                    "evaluation_status": "completed",
                    "entry_hfq_close": entry_hfq,
                    "horizon_hfq_close": target_hfq,
                    "forward_return": forward_return,
                    "path_max_drawdown": float(drawdown.min()),
                    "max_high_return": max_high_return,
                    "high_to_close_fade": (maximum_high - target_hfq) / maximum_high,
                    "retention_ratio": retention,
                }
            )
    return pd.DataFrame(rows, columns=_DETAIL_COLUMNS).sort_values(
        ["horizon", "final_rank", "asset_id"], kind="stable", na_position="last"
    ).reset_index(drop=True)


def _safe_mean(values: pd.Series) -> float:
    return float(values.mean()) if not values.empty else math.nan


def _safe_median(values: pd.Series) -> float:
    return float(values.median()) if not values.empty else math.nan


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else math.nan


def _spearman_rank_correlation(completed: pd.DataFrame) -> float:
    if len(completed) < 2:
        return math.nan
    expected_rank = pd.to_numeric(completed["final_rank"], errors="coerce")
    outcome_rank = completed["forward_return"].rank(method="average", ascending=False)
    if expected_rank.isna().any() or expected_rank.nunique() < 2 or outcome_rank.nunique() < 2:
        return math.nan
    return float(expected_rank.corr(outcome_rank, method="pearson"))


def _bounded_score(value: float, scale: float, *, inverse: bool = False) -> float:
    if not math.isfinite(value):
        return math.nan
    raw = -value if inverse else value
    return float(np.clip(raw / scale, 0.0, 1.0) * 100.0)


def _summary_row(
    group_name: str,
    horizon: int,
    group: pd.DataFrame,
    qualified_completed: pd.DataFrame,
    qualified_complete: bool,
    qualified_expected_count: int,
) -> dict[str, Any]:
    completed = group.loc[group["evaluation_status"].eq("completed")].copy()
    member_count = len(group)
    completed_count = len(completed)
    group_complete = bool(member_count > 0 and completed_count == member_count)
    returns = completed["forward_return"]
    positive = returns.loc[returns.gt(0.0)]
    rising_count = int(returns.gt(0.0).sum())
    thresholds = (3, 5, 7)
    counts = {threshold: int(returns.ge(threshold / 100.0).sum()) for threshold in thresholds}
    fades = {
        threshold: int(
            (
                completed["max_high_return"].ge(threshold / 100.0)
                & completed["forward_return"].lt(threshold / 100.0)
            ).sum()
        )
        for threshold in thresholds
    }
    mean_return = _safe_mean(returns)
    median_return = _safe_median(returns)
    positive_mean = _safe_mean(positive)
    median_drawdown = _safe_median(completed["path_max_drawdown"])
    median_fade = _safe_median(completed["high_to_close_fade"])
    median_retention = _safe_median(completed["retention_ratio"].dropna())
    breadth_ratios = [
        _ratio(rising_count, completed_count),
        *[_ratio(counts[threshold], completed_count) for threshold in thresholds],
    ]
    breadth_quality = (
        float(np.mean(breadth_ratios) * 100.0)
        if group_complete
        else math.nan
    )
    strength_parts = (
        _bounded_score(mean_return, 0.07),
        _bounded_score(median_return, 0.05),
        _bounded_score(positive_mean, 0.10) if not positive.empty else 0.0,
    )
    repair_strength = (
        float(np.mean(strength_parts))
        if group_complete and all(math.isfinite(value) for value in strength_parts)
        else math.nan
    )
    risk_parts = (
        100.0 - _bounded_score(median_drawdown, 0.10, inverse=True),
        100.0 - _bounded_score(median_fade, 0.10),
        _bounded_score(median_retention, 1.0)
        if math.isfinite(median_retention)
        else 0.0,
    )
    risk_and_retention = (
        float(np.mean(risk_parts))
        if group_complete and all(math.isfinite(value) for value in risk_parts)
        else math.nan
    )
    balanced = (
        0.40 * breadth_quality + 0.40 * repair_strength + 0.20 * risk_and_retention
        if all(
            math.isfinite(value)
            for value in (breadth_quality, repair_strength, risk_and_retention)
        )
        else math.nan
    )
    pool_mean = (
        _safe_mean(qualified_completed["forward_return"])
        if qualified_complete
        else math.nan
    )
    horizon_dates = completed["horizon_trade_date"].drop_duplicates().tolist()
    return {
        "group": group_name,
        "horizon": horizon,
        "horizon_trade_date": horizon_dates[0] if len(horizon_dates) == 1 else "",
        "member_count": member_count,
        "completed_count": completed_count,
        "pending_count": member_count - completed_count,
        "rising_count": rising_count,
        "rising_ratio": _ratio(rising_count, completed_count)
        if group_complete
        else math.nan,
        "mean_return": mean_return if group_complete else math.nan,
        "median_return": median_return if group_complete else math.nan,
        "positive_mean_return": positive_mean if group_complete else math.nan,
        **{
            f"gte_{threshold}pct_count": counts[threshold]
            for threshold in thresholds
        },
        **{
            f"gte_{threshold}pct_ratio": _ratio(counts[threshold], completed_count)
            if group_complete
            else math.nan
            for threshold in thresholds
        },
        **{
            f"reached_{threshold}pct_not_retained_count": fades[threshold]
            for threshold in thresholds
        },
        **{
            f"reached_{threshold}pct_not_retained_ratio": _ratio(
                fades[threshold], completed_count
            )
            if group_complete
            else math.nan
            for threshold in thresholds
        },
        "median_path_max_drawdown": median_drawdown if group_complete else math.nan,
        "median_max_high_return": _safe_median(completed["max_high_return"])
        if group_complete
        else math.nan,
        "median_high_to_close_fade": median_fade if group_complete else math.nan,
        "median_retention_ratio": median_retention if group_complete else math.nan,
        "extreme_loss_count": int(returns.le(-0.05).sum()),
        "extreme_loss_ratio": _ratio(int(returns.le(-0.05).sum()), completed_count)
        if group_complete
        else math.nan,
        "spearman_rank_correlation": _spearman_rank_correlation(completed)
        if group_complete
        else math.nan,
        "qualified_pool_benchmark_status": "completed"
        if qualified_complete
        else "incomplete",
        "qualified_pool_member_count": qualified_expected_count,
        "qualified_pool_completed_count": len(qualified_completed),
        "qualified_pool_mean_return": pool_mean,
        "qualified_pool_excess_return": mean_return - pool_mean
        if math.isfinite(mean_return) and math.isfinite(pool_mean)
        else math.nan,
        "breadth_quality": breadth_quality,
        "repair_strength": repair_strength,
        "risk_and_retention": risk_and_retention,
        "balanced_evaluation": balanced,
        "group_evaluation_status": "complete"
        if group_complete
        else "partial"
        if member_count
        else "empty",
        "overall_evaluation": math.nan,
    }


def _group_summary(
    detail: pd.DataFrame,
    qualified_detail: pd.DataFrame,
    horizons: tuple[int, ...],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon in horizons:
        horizon_detail = detail.loc[detail["horizon"].eq(horizon)]
        qualified_horizon = qualified_detail.loc[qualified_detail["horizon"].eq(horizon)]
        qualified_completed = qualified_horizon.loc[
            qualified_horizon["evaluation_status"].eq("completed")
        ]
        qualified_complete = bool(
            not qualified_horizon.empty
            and qualified_horizon["evaluation_status"].eq("completed").all()
        )
        for group_name, predicate in GROUPS.items():
            ranks = pd.to_numeric(horizon_detail["final_rank"], errors="coerce")
            mask = ranks.map(lambda rank: bool(predicate(int(rank))) if pd.notna(rank) else False)
            rows.append(
                _summary_row(
                    group_name,
                    horizon,
                    horizon_detail.loc[mask],
                    qualified_completed,
                    qualified_complete,
                    len(qualified_horizon),
                )
            )
    summary = pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)
    for group_name in GROUPS:
        group_rows = summary.loc[summary["group"].eq(group_name)]
        complete_rows = group_rows.loc[
            group_rows["group_evaluation_status"].eq("complete")
        ]
        completed_scores = complete_rows.set_index("horizon")["balanced_evaluation"]
        if len(completed_scores) < len(horizons):
            overall = math.nan
        elif 3 in completed_scores.index and 5 in completed_scores.index:
            overall = 0.30 * float(completed_scores.loc[3]) + 0.70 * float(
                completed_scores.loc[5]
            )
        elif len(horizons) == 1:
            overall = float(completed_scores.iloc[0])
        elif len(horizons) > 1:
            overall = float(completed_scores.mean())
        else:
            overall = math.nan
        summary.loc[summary["group"].eq(group_name), "overall_evaluation"] = overall
    order = {name: position for position, name in enumerate(GROUPS)}
    return (
        summary.assign(_group_order=summary["group"].map(order))
        .sort_values(["horizon", "_group_order"], kind="stable")
        .drop(columns="_group_order")
        .reset_index(drop=True)
    )


def _minute_diagnostics(
    snapshot: pd.DataFrame,
    minute_bars: pd.DataFrame,
    daily_bars: pd.DataFrame,
    targets: dict[int, pd.Timestamp | None],
) -> tuple[pd.DataFrame, bool]:
    if snapshot.empty or not isinstance(minute_bars, pd.DataFrame) or minute_bars.empty:
        return pd.DataFrame(columns=_MINUTE_DETAIL_COLUMNS), False
    if any(column not in minute_bars.columns for column in _MINUTE_REQUIRED_COLUMNS):
        return pd.DataFrame(columns=_MINUTE_DETAIL_COLUMNS), False
    requested = {horizon: target for horizon, target in targets.items() if target is not None}
    if len(requested) != len(targets):
        return pd.DataFrame(columns=_MINUTE_DETAIL_COLUMNS), False
    frame = minute_bars.copy(deep=True)
    frame["asset_id"] = frame["asset_id"].astype(str).str.strip()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.normalize()
    frame["trade_time"] = pd.to_datetime(frame["trade_time"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["limit_up_price"] = pd.to_numeric(
        frame["limit_up_price"], errors="coerce"
    )
    selected_assets = set(snapshot["asset_id"])
    target_dates = set(requested.values())
    frame = frame.loc[
        frame["asset_id"].isin(selected_assets) & frame["trade_date"].isin(target_dates)
    ].copy()
    if (
        frame.empty
        or frame[
            [
                "trade_date",
                "trade_time",
                "open",
                "high",
                "low",
                "close",
                "limit_up_price",
            ]
        ].isna().any().any()
        or frame.duplicated(["asset_id", "trade_time"]).any()
        or not frame["trade_time"].dt.normalize().eq(frame["trade_date"]).all()
        or not frame["trade_time"].dt.time.map(
            lambda value: value in _CANONICAL_MINUTE_TIMES
        ).all()
        or not np.isfinite(frame["limit_up_price"].to_numpy(dtype=float)).all()
        or frame["limit_up_price"].le(0).any()
    ):
        return pd.DataFrame(columns=_MINUTE_DETAIL_COLUMNS), False
    entry_raw = (
        daily_bars.loc[
            daily_bars["trade_date"].eq(pd.Timestamp(snapshot.iloc[0]["trade_date"]))
            & daily_bars["asset_id"].isin(selected_assets),
            ["asset_id", "raw_close"],
        ]
        .drop_duplicates("asset_id")
        .set_index("asset_id")["raw_close"]
    )
    rows: list[dict[str, Any]] = []
    complete = True
    for member in snapshot.to_dict(orient="records"):
        for horizon, outcome_date in requested.items():
            bars = frame.loc[
                frame["asset_id"].eq(member["asset_id"])
                & frame["trade_date"].eq(outcome_date)
            ].sort_values("trade_time", kind="stable")
            if len(bars) != 48 or member["asset_id"] not in entry_raw.index:
                complete = False
                continue
            if frozenset(bars["trade_time"].dt.time) != _CANONICAL_MINUTE_TIMES:
                complete = False
                continue
            prices = bars[["open", "high", "low", "close"]]
            if (
                not np.isfinite(prices.to_numpy(dtype=float)).all()
                or (prices <= 0).any().any()
                or not np.isfinite(bars["limit_up_price"].to_numpy(dtype=float)).all()
                or bars["limit_up_price"].le(0).any()
                or (bars["low"] > bars["high"]).any()
                or (bars[["open", "close"]].max(axis=1) > bars["high"]).any()
                or (bars[["open", "close"]].min(axis=1) < bars["low"]).any()
            ):
                complete = False
                continue
            entry = float(entry_raw.loc[member["asset_id"]])
            day_high = float(bars["high"].max())
            first_high = bars.loc[bars["high"].eq(day_high), "trade_time"].iloc[0]
            morning = bars.loc[bars["trade_time"].dt.time <= pd.Timestamp("11:30").time()]
            close = float(bars.iloc[-1]["close"])
            morning_close = float(morning.iloc[-1]["close"]) if not morning.empty else math.nan
            morning_high = float(morning["high"].max()) if not morning.empty else math.nan
            limit_price = (
                float(bars["limit_up_price"].dropna().iloc[-1])
                if "limit_up_price" in bars and not bars["limit_up_price"].dropna().empty
                else math.nan
            )
            tolerance = max(abs(limit_price) * 1e-6, 1e-8) if math.isfinite(limit_price) else math.nan
            rows.append(
                {
                    "trade_date": member["trade_date"],
                    "asset_id": member["asset_id"],
                    "final_rank": member["final_rank"],
                    "horizon": horizon,
                    "outcome_trade_date": outcome_date.date().isoformat(),
                    "bar_count": len(bars),
                    "first_high_time": first_high.isoformat(sep=" "),
                    "intraday_max_return": day_high / entry - 1.0,
                    "above_entry_bar_ratio": float(bars["close"].gt(entry).mean()),
                    "morning_close_return": morning_close / entry - 1.0,
                    "morning_retention": float(
                        np.clip(
                            (morning_close / entry - 1.0)
                            / (morning_high / entry - 1.0),
                            0.0,
                            1.0,
                        )
                    )
                    if morning_high > entry
                    else math.nan,
                    "afternoon_close_return": close / entry - 1.0,
                    "afternoon_retention": float(
                        np.clip((close / entry - 1.0) / (day_high / entry - 1.0), 0.0, 1.0)
                    )
                    if day_high > entry
                    else math.nan,
                    "limit_up_reached": day_high + tolerance >= limit_price
                    if math.isfinite(limit_price)
                    else pd.NA,
                    "first_limit_up_time": bars.loc[
                        bars["high"].ge(limit_price - tolerance), "trade_time"
                    ].iloc[0].isoformat(sep=" ")
                    if math.isfinite(limit_price)
                    and bool(bars["high"].ge(limit_price - tolerance).any())
                    else "",
                    "limit_up_held_to_close": close + tolerance >= limit_price
                    if math.isfinite(limit_price)
                    else pd.NA,
                }
            )
    detail = pd.DataFrame(rows, columns=_MINUTE_DETAIL_COLUMNS).sort_values(
        ["horizon", "final_rank", "asset_id"], kind="stable"
    ).reset_index(drop=True)
    expected_count = len(snapshot) * len(requested)
    return detail, bool(complete and len(detail) == expected_count)


def evaluate_v2_snapshot(
    *,
    snapshot: pd.DataFrame,
    qualified_pool: pd.DataFrame,
    daily_bars: pd.DataFrame,
    minute_bars: pd.DataFrame,
    outcome_dates: Iterable[str] | None = None,
    horizons: tuple[int, ...] = (3, 5),
) -> dict[str, pd.DataFrame | dict[str, object]]:
    """Evaluate immutable V2 members without recomputing membership or scores."""
    horizon_values = _normalized_horizons(horizons)
    selected, snapshot_trade_date = _validate_snapshot(snapshot)
    qualified = _validate_qualified_pool(
        qualified_pool, selected, snapshot_trade_date
    )
    authoritative_dates = _resolve_outcome_dates(
        daily_bars, snapshot_trade_date, outcome_dates
    )
    market = _normalize_daily_bars(daily_bars)
    calendar, targets = _outcome_calendar(
        snapshot_trade_date,
        horizon_values,
        authoritative_dates,
    )
    detail = _daily_forward_detail(
        selected,
        market,
        snapshot_trade_date,
        horizon_values,
        calendar,
        targets,
    )
    qualified_detail = _daily_forward_detail(
        qualified,
        market,
        snapshot_trade_date,
        horizon_values,
        calendar,
        targets,
    )
    summary = _group_summary(detail, qualified_detail, horizon_values)
    minute_detail, minute_complete = _minute_diagnostics(
        selected, minute_bars, market, targets
    )
    selected_daily_complete = bool(
        not detail.empty and detail["evaluation_status"].eq("completed").all()
    )
    qualified_pool_daily_complete = bool(
        not qualified_detail.empty
        and qualified_detail["evaluation_status"].eq("completed").all()
    )
    daily_complete = selected_daily_complete and qualified_pool_daily_complete
    warnings: list[str] = []
    if not selected_daily_complete:
        warnings.append("selected_daily_incomplete")
    if not qualified_pool_daily_complete:
        warnings.append("qualified_pool_daily_incomplete")
    coverage: dict[str, object] = {
        "snapshot_trade_date": snapshot_trade_date,
        "horizons": list(horizon_values),
        "authoritative_outcome_dates": list(authoritative_dates),
        "outcome_trade_dates": {
            str(horizon): target.date().isoformat() if target is not None else None
            for horizon, target in targets.items()
        },
        "selected_asset_count": len(selected),
        "qualified_pool_count": len(qualified),
        "daily_completed_rows": int(detail["evaluation_status"].eq("completed").sum()),
        "daily_expected_rows": len(detail),
        "selected_daily_complete": selected_daily_complete,
        "qualified_pool_daily_completed_rows": int(
            qualified_detail["evaluation_status"].eq("completed").sum()
        ),
        "qualified_pool_daily_expected_rows": len(qualified_detail),
        "qualified_pool_daily_complete": qualified_pool_daily_complete,
        "daily_complete": daily_complete,
        "minute_complete": minute_complete,
        "warnings": warnings,
        "evaluation_status": (
            "complete"
            if daily_complete and minute_complete
            else "daily_complete_minute_degraded"
            if daily_complete
            else "daily_incomplete"
        ),
    }
    return {
        "detail": detail,
        "summary": summary,
        "minute_detail": minute_detail,
        "coverage": coverage,
    }
