from __future__ import annotations

from typing import Any

import pandas as pd


OUTCOME_HORIZONS = [1, 3, 5, 10, 20, 60]
METRIC_PREFIXES = ["forward", "max_high", "max_low_drawdown"]


def build_decision_outcomes_from_frames(
    *,
    decision_events: pd.DataFrame,
    bars: pd.DataFrame,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    selected_horizons = sorted({int(value) for value in (horizons or OUTCOME_HORIZONS) if int(value) > 0})
    events = _normalize_events(decision_events)
    if events.empty:
        return pd.DataFrame(columns=_outcome_columns(selected_horizons))
    market_bars = _normalize_bars(bars)
    grouped_bars = {
        str(asset_id): group.sort_values("trade_date").reset_index(drop=True)
        for asset_id, group in market_bars.groupby("asset_id", dropna=False)
    }

    rows = [
        _outcome_row(event, grouped_bars.get(str(event["asset_id"]), pd.DataFrame()), selected_horizons)
        for event in events.to_dict("records")
    ]
    frame = pd.DataFrame(rows)
    for column in _outcome_columns(selected_horizons):
        if column not in frame.columns:
            frame[column] = pd.NA
    for column in ["requires_follow_up", "manual_review_required", "auto_trade_enabled"]:
        frame[column] = frame[column].astype(object)
    return frame.loc[:, _outcome_columns(selected_horizons)]


def summarize_decision_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    if outcomes.empty:
        return pd.DataFrame(
            columns=[
                "summary_level",
                "decision_label",
                "source_context",
                "sample_count",
                "complete_count",
                "insufficient_data_count",
                "follow_up_required_rate",
            ]
        )
    normalized = outcomes.copy()
    horizons = _horizons_from_columns(normalized.columns)
    for column in _metric_columns(horizons):
        normalized[column] = pd.to_numeric(normalized.get(column), errors="coerce")
    frames = [
        _summary_frame(
            normalized,
            group_columns=["decision_label"],
            summary_level="decision_label",
            horizons=horizons,
        ),
        _summary_frame(
            normalized,
            group_columns=["source_context"],
            summary_level="source_context",
            horizons=horizons,
        ),
    ]
    return pd.concat(frames, ignore_index=True)


def _normalize_events(events: pd.DataFrame) -> pd.DataFrame:
    normalized = events.copy()
    for column in [
        "event_id",
        "review_session_id",
        "review_date",
        "asset_id",
        "stock_code",
        "stock_name",
        "decision_label",
        "evidence_artifact_id",
        "evidence_path",
        "source_context",
        "requires_follow_up",
        "follow_up_note",
        "notes",
        "manual_review_required",
        "auto_trade_enabled",
        "source_artifact_path",
    ]:
        if column not in normalized.columns:
            normalized[column] = ""
    if normalized.empty:
        return normalized
    if normalized["auto_trade_enabled"].map(_bool_value).eq(True).any():
        raise ValueError("auto_trade_not_allowed")
    if normalized["manual_review_required"].map(_bool_value).ne(True).any():
        raise ValueError("manual_review_required")
    normalized["review_date"] = pd.to_datetime(normalized["review_date"], errors="coerce")
    normalized["requires_follow_up"] = normalized["requires_follow_up"].map(_bool_value).fillna(False)
    normalized["manual_review_required"] = True
    normalized["auto_trade_enabled"] = False
    return normalized


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    normalized = bars.copy()
    for column in ["asset_id", "trade_date", "close", "high", "low"]:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    normalized["high"] = pd.to_numeric(normalized["high"], errors="coerce")
    normalized["low"] = pd.to_numeric(normalized["low"], errors="coerce")
    return normalized.dropna(subset=["trade_date", "close"]).sort_values(["asset_id", "trade_date"])


def _outcome_row(
    event: dict[str, Any],
    asset_bars: pd.DataFrame,
    horizons: list[int],
) -> dict[str, Any]:
    review_date = event["review_date"]
    row = _base_outcome_row(event)
    if pd.isna(review_date) or asset_bars.empty:
        row.update(_empty_metrics(horizons, status="missing_base_bar", available_future_bars=0))
        return row

    eligible = asset_bars[asset_bars["trade_date"] >= review_date].reset_index(drop=True)
    if eligible.empty:
        row.update(_empty_metrics(horizons, status="missing_base_bar", available_future_bars=0))
        return row
    base = eligible.iloc[0]
    base_close = _float_or_none(base.get("close"))
    if base_close is None or base_close == 0:
        row.update(_empty_metrics(horizons, status="missing_base_bar", available_future_bars=0))
        return row

    future = eligible.iloc[1:].reset_index(drop=True)
    available = int(len(future))
    status = "complete" if available >= max(horizons) else "insufficient_data"
    row["outcome_status"] = status
    row["available_future_bars"] = available
    row["base_trade_date"] = str(pd.to_datetime(base["trade_date"]).date())
    row["base_close"] = base_close
    for horizon in horizons:
        _add_horizon_metrics(row, future, base_close=base_close, horizon=horizon)
    return row


def _base_outcome_row(event: dict[str, Any]) -> dict[str, Any]:
    review_date = event.get("review_date")
    return {
        "event_id": str(event.get("event_id") or ""),
        "review_session_id": str(event.get("review_session_id") or ""),
        "review_date": "" if pd.isna(review_date) else str(pd.to_datetime(review_date).date()),
        "asset_id": str(event.get("asset_id") or ""),
        "stock_code": str(event.get("stock_code") or ""),
        "stock_name": str(event.get("stock_name") or ""),
        "decision_label": str(event.get("decision_label") or ""),
        "evidence_artifact_id": str(event.get("evidence_artifact_id") or ""),
        "evidence_path": str(event.get("evidence_path") or ""),
        "source_context": str(event.get("source_context") or ""),
        "requires_follow_up": bool(event.get("requires_follow_up")),
        "follow_up_note": str(event.get("follow_up_note") or ""),
        "notes": str(event.get("notes") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "source_artifact_path": str(event.get("source_artifact_path") or ""),
    }


def _add_horizon_metrics(row: dict[str, Any], future: pd.DataFrame, *, base_close: float, horizon: int) -> None:
    if len(future) < horizon:
        row[f"forward_{horizon}d_return"] = pd.NA
        row[f"max_high_return_{horizon}d"] = pd.NA
        row[f"max_low_drawdown_{horizon}d"] = pd.NA
        return
    window = future.iloc[:horizon]
    close = _float_or_none(window.iloc[horizon - 1].get("close"))
    max_high = _float_or_none(window["high"].max())
    min_low = _float_or_none(window["low"].min())
    row[f"forward_{horizon}d_return"] = close / base_close - 1.0 if close is not None else pd.NA
    row[f"max_high_return_{horizon}d"] = max_high / base_close - 1.0 if max_high is not None else pd.NA
    if min_low is None:
        row[f"max_low_drawdown_{horizon}d"] = pd.NA
    else:
        row[f"max_low_drawdown_{horizon}d"] = min(min_low / base_close - 1.0, 0.0)


def _empty_metrics(horizons: list[int], *, status: str, available_future_bars: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "outcome_status": status,
        "available_future_bars": available_future_bars,
        "base_trade_date": "",
        "base_close": pd.NA,
    }
    for horizon in horizons:
        row[f"forward_{horizon}d_return"] = pd.NA
        row[f"max_high_return_{horizon}d"] = pd.NA
        row[f"max_low_drawdown_{horizon}d"] = pd.NA
    return row


def _summary_frame(
    outcomes: pd.DataFrame,
    *,
    group_columns: list[str],
    summary_level: str,
    horizons: list[int],
) -> pd.DataFrame:
    grouped = outcomes.groupby(group_columns, dropna=False)
    metric_columns = _metric_columns(horizons)
    summary = grouped[metric_columns].mean(numeric_only=True).reset_index()
    counts = grouped.size().reset_index(name="sample_count")
    complete = (
        outcomes[outcomes["outcome_status"].eq("complete")]
        .groupby(group_columns, dropna=False)
        .size()
        .reset_index(name="complete_count")
    )
    insufficient = (
        outcomes[outcomes["outcome_status"].eq("insufficient_data")]
        .groupby(group_columns, dropna=False)
        .size()
        .reset_index(name="insufficient_data_count")
    )
    follow_up = grouped["requires_follow_up"].mean().reset_index(name="follow_up_required_rate")
    result = counts.merge(complete, on=group_columns, how="left")
    result = result.merge(insufficient, on=group_columns, how="left")
    result = result.merge(follow_up, on=group_columns, how="left")
    result = result.merge(summary, on=group_columns, how="left")
    result.insert(0, "summary_level", summary_level)
    result["complete_count"] = result["complete_count"].fillna(0).astype(int)
    result["insufficient_data_count"] = result["insufficient_data_count"].fillna(0).astype(int)
    for column in ["decision_label", "source_context"]:
        if column not in result.columns:
            result[column] = ""
    ordered = [
        "summary_level",
        "decision_label",
        "source_context",
        "sample_count",
        "complete_count",
        "insufficient_data_count",
        "follow_up_required_rate",
        *_summary_metric_columns(horizons),
    ]
    return result.rename(columns={column: f"{column}_mean" for column in metric_columns}).loc[:, ordered]


def _outcome_columns(horizons: list[int]) -> list[str]:
    columns = [
        "event_id",
        "review_session_id",
        "review_date",
        "asset_id",
        "stock_code",
        "stock_name",
        "decision_label",
        "evidence_artifact_id",
        "evidence_path",
        "source_context",
        "requires_follow_up",
        "follow_up_note",
        "notes",
        "manual_review_required",
        "auto_trade_enabled",
        "source_artifact_path",
        "outcome_status",
        "available_future_bars",
        "base_trade_date",
        "base_close",
    ]
    columns.extend(_metric_columns(horizons))
    return columns


def _metric_columns(horizons: list[int]) -> list[str]:
    columns: list[str] = []
    for horizon in horizons:
        columns.extend(
            [
                f"forward_{horizon}d_return",
                f"max_high_return_{horizon}d",
                f"max_low_drawdown_{horizon}d",
            ]
        )
    return columns


def _summary_metric_columns(horizons: list[int]) -> list[str]:
    return [f"{column}_mean" for column in _metric_columns(horizons)]


def _horizons_from_columns(columns: Any) -> list[int]:
    horizons: set[int] = set()
    for column in columns:
        text = str(column)
        if text.startswith("forward_") and text.endswith("d_return"):
            horizons.add(int(text.removeprefix("forward_").removesuffix("d_return")))
    return sorted(horizons)


def _float_or_none(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(number) if pd.notna(number) else None


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None
