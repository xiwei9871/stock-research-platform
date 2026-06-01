from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


SHADOW_OUTCOME_HORIZONS = [1, 3, 5, 10, 20, 60]

UNSAFE_EXECUTION_FIELDS = {
    "account_id",
    "broker",
    "broker_id",
    "cash",
    "execution_id",
    "fill_id",
    "limit_price",
    "notional",
    "order_id",
    "order_side",
    "position_id",
    "price",
    "quantity",
    "shares",
    "side",
    "stop_price",
    "trade_id",
}

REQUIRED_TEXT_COLUMNS = [
    "shadow_candidate_id",
    "run_id",
    "replay_result_id",
    "source_p11_replay_run_id",
    "source_p10_proposal_run_id",
    "source_p9_analytics_run_id",
    "candidate_date",
    "asset_id",
    "shadow_layer",
    "status",
]


def build_shadow_outcomes_from_frames(
    *,
    shadow_candidates: pd.DataFrame,
    bars: pd.DataFrame,
    horizons: list[int] | None = None,
    run_id: str | None = None,
) -> pd.DataFrame:
    selected_horizons = _normalize_horizons(horizons)
    candidates = _normalize_candidates(shadow_candidates)
    if candidates.empty:
        return pd.DataFrame(columns=_outcome_columns(selected_horizons))

    market_bars = _normalize_bars(bars)
    grouped_bars = {
        str(asset_id): group.sort_values("trade_date").reset_index(drop=True)
        for asset_id, group in market_bars.groupby("asset_id", dropna=False)
    }
    rows = [
        _outcome_row(
            candidate,
            grouped_bars.get(str(candidate["asset_id"]), pd.DataFrame()),
            selected_horizons,
            run_id=run_id,
        )
        for candidate in candidates.to_dict("records")
    ]
    frame = pd.DataFrame(rows)
    for column in _outcome_columns(selected_horizons):
        if column not in frame.columns:
            frame[column] = pd.NA
    for column in [
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ]:
        frame[column] = frame[column].astype(object)
    return frame.loc[:, _outcome_columns(selected_horizons)]


def build_shadow_outcome_review(
    *,
    review_date: str,
    shadow_candidates: pd.DataFrame,
    bars: pd.DataFrame,
    horizons: list[int] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    selected_horizons = _normalize_horizons(horizons)
    date_text = str(review_date)
    resolved_run_id = run_id or f"p13-shadow-outcomes-{date_text}"
    outcomes = build_shadow_outcomes_from_frames(
        shadow_candidates=shadow_candidates,
        bars=bars,
        horizons=selected_horizons,
        run_id=resolved_run_id,
    )
    return {
        "run_id": resolved_run_id,
        "review_date": date_text,
        "status": "shadow_outcome_review_ready" if not outcomes.empty else "no_shadow_outcomes_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "horizons": selected_horizons,
        "outcome_count": int(len(outcomes)),
        "outcomes": _records(outcomes),
    }


def write_shadow_outcome_review(review: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    review_date = _safe_path_part(review.get("review_date") or "unknown-date")
    stem = f"operator_shadow_outcomes_{review_date}"

    json_path = output_path / f"{stem}.json"
    details_csv_path = output_path / f"{stem}_details.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(review)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(
        payload.get("outcomes", []),
        columns=_outcome_columns(_normalize_horizons(payload.get("horizons"))),
    ).to_csv(details_csv_path, index=False)
    markdown_path.write_text(_render_shadow_outcome_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "details_csv_path": str(details_csv_path),
        "markdown_path": str(markdown_path),
    }


def _normalize_horizons(horizons: list[int] | None) -> list[int]:
    return sorted({int(value) for value in (horizons or SHADOW_OUTCOME_HORIZONS) if int(value) > 0})


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    _reject_unsafe_execution_fields(candidates)
    normalized = candidates.copy()
    for column in _candidate_columns():
        if column not in normalized.columns:
            normalized[column] = _default_candidate_value(column)
    if normalized.empty:
        return normalized

    for column in REQUIRED_TEXT_COLUMNS:
        normalized[column] = normalized[column].map(_required_text(column))
    for column in ["stock_code", "stock_name", "candidate_reason", "shadow_artifact_path"]:
        normalized[column] = normalized[column].fillna("").astype(str)
    _normalize_safety_fields(normalized)
    normalized["candidate_date"] = pd.to_datetime(normalized["candidate_date"], errors="coerce")
    if normalized["candidate_date"].isna().any():
        raise ValueError("required_field_missing: candidate_date")
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
    candidate: dict[str, Any],
    asset_bars: pd.DataFrame,
    horizons: list[int],
    *,
    run_id: str | None,
) -> dict[str, Any]:
    candidate_date = candidate["candidate_date"]
    row = _base_outcome_row(candidate, run_id=run_id)
    eligible = asset_bars[asset_bars["trade_date"] >= candidate_date].reset_index(drop=True)
    if eligible.empty:
        raise ValueError(f"base_bar_required: {candidate['shadow_candidate_id']}")

    base = eligible.iloc[0]
    if pd.to_datetime(base["trade_date"]).date() != pd.to_datetime(candidate_date).date():
        raise ValueError(f"base_bar_required: {candidate['shadow_candidate_id']}")
    base_close = _float_or_none(base.get("close"))
    if base_close is None or base_close == 0:
        raise ValueError(f"base_bar_required: {candidate['shadow_candidate_id']}")

    future = eligible.iloc[1:].reset_index(drop=True)
    available = int(len(future))
    row["outcome_status"] = "complete" if available >= max(horizons) else "insufficient_data"
    row["available_future_bars"] = available
    row["base_trade_date"] = str(pd.to_datetime(base["trade_date"]).date())
    row["base_close"] = base_close
    for horizon in horizons:
        _add_horizon_metrics(row, future, base_close=base_close, horizon=horizon)
    return row


def _base_outcome_row(candidate: dict[str, Any], *, run_id: str | None) -> dict[str, Any]:
    candidate_date = candidate.get("candidate_date")
    shadow_candidate_id = str(candidate.get("shadow_candidate_id") or "")
    return {
        "shadow_outcome_id": f"p13-shadow-outcome:{shadow_candidate_id}",
        "run_id": str(run_id or ""),
        "shadow_candidate_id": shadow_candidate_id,
        "source_p12_shadow_run_id": str(candidate.get("run_id") or ""),
        "replay_result_id": str(candidate.get("replay_result_id") or ""),
        "source_p11_replay_run_id": str(candidate.get("source_p11_replay_run_id") or ""),
        "source_p10_proposal_run_id": str(candidate.get("source_p10_proposal_run_id") or ""),
        "source_p9_analytics_run_id": str(candidate.get("source_p9_analytics_run_id") or ""),
        "candidate_date": "" if pd.isna(candidate_date) else str(pd.to_datetime(candidate_date).date()),
        "asset_id": str(candidate.get("asset_id") or ""),
        "stock_code": str(candidate.get("stock_code") or ""),
        "stock_name": str(candidate.get("stock_name") or ""),
        "shadow_layer": str(candidate.get("shadow_layer") or ""),
        "shadow_status": str(candidate.get("status") or ""),
        "candidate_reason": str(candidate.get("candidate_reason") or ""),
        "source_shadow_artifact_path": str(candidate.get("shadow_artifact_path") or ""),
        "outcome_artifact_path": "",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
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


def _normalize_safety_fields(frame: pd.DataFrame) -> None:
    frame["manual_review_required"] = frame["manual_review_required"].map(
        lambda value: _parse_safety_value(value, column="manual_review_required", default=True)
    )
    if frame["manual_review_required"].ne(True).any():
        raise ValueError("manual_review_required")
    frame["manual_review_required"] = True

    frame["auto_trade_enabled"] = frame["auto_trade_enabled"].map(
        lambda value: _parse_safety_value(value, column="auto_trade_enabled", default=False)
    )
    if frame["auto_trade_enabled"].eq(True).any():
        raise ValueError("auto_trade_not_allowed")
    frame["auto_trade_enabled"] = False

    frame["production_watchlist_enabled"] = frame["production_watchlist_enabled"].map(
        lambda value: _parse_safety_value(value, column="production_watchlist_enabled", default=False)
    )
    if frame["production_watchlist_enabled"].eq(True).any():
        raise ValueError("production_watchlist_not_allowed")
    frame["production_watchlist_enabled"] = False

    frame["production_write_enabled"] = frame["production_write_enabled"].map(
        lambda value: _parse_safety_value(value, column="production_write_enabled", default=False)
    )
    if frame["production_write_enabled"].eq(True).any():
        raise ValueError("production_write_not_allowed")
    frame["production_write_enabled"] = False


def _parse_safety_value(value: Any, *, column: str, default: bool) -> bool:
    if _is_missing(value):
        return default
    parsed = _bool_value(value)
    if parsed is None:
        raise ValueError(f"invalid_safety_field: {column}")
    return parsed


def _reject_unsafe_execution_fields(frame: pd.DataFrame) -> None:
    for column in frame.columns:
        normalized_column = str(column).strip().lower()
        if normalized_column not in UNSAFE_EXECUTION_FIELDS:
            continue
        if frame[column].map(lambda value: not _is_missing(value) and str(value).strip() != "").any():
            raise ValueError(f"unsafe_execution_field: {column}")


def _required_text(column: str):
    def normalize(value: Any) -> str:
        if _is_missing(value) or str(value).strip() == "":
            raise ValueError(f"required_field_missing: {column}")
        return str(value).strip()

    return normalize


def _outcome_columns(horizons: list[int]) -> list[str]:
    columns = [
        "shadow_outcome_id",
        "run_id",
        "shadow_candidate_id",
        "source_p12_shadow_run_id",
        "replay_result_id",
        "source_p11_replay_run_id",
        "source_p10_proposal_run_id",
        "source_p9_analytics_run_id",
        "candidate_date",
        "asset_id",
        "stock_code",
        "stock_name",
        "shadow_layer",
        "shadow_status",
        "candidate_reason",
        "source_shadow_artifact_path",
        "outcome_artifact_path",
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
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


def _candidate_columns() -> list[str]:
    return [
        "shadow_candidate_id",
        "run_id",
        "replay_result_id",
        "source_p11_replay_run_id",
        "source_p10_proposal_run_id",
        "source_p9_analytics_run_id",
        "candidate_date",
        "asset_id",
        "stock_code",
        "stock_name",
        "shadow_layer",
        "candidate_reason",
        "status",
        "shadow_artifact_path",
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ]


def _default_candidate_value(column: str) -> Any:
    if column == "manual_review_required":
        return True
    if column in {"auto_trade_enabled", "production_watchlist_enabled", "production_write_enabled"}:
        return False
    return ""


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_json_safe(record) for record in frame.to_dict("records")]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _render_shadow_outcome_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# P13 Shadow Watchlist Outcome Tracking",
        "",
        f"run_id: {review.get('run_id', '')}",
        f"review_date: {review.get('review_date', '')}",
        f"status: {review.get('status', '')}",
        f"outcome_count: {review.get('outcome_count', 0)}",
        f"manual_review_required: {str(review.get('manual_review_required', True)).lower()}",
        f"auto_trade_enabled: {str(review.get('auto_trade_enabled', False)).lower()}",
        f"production_watchlist_enabled: {str(review.get('production_watchlist_enabled', False)).lower()}",
        f"production_write_enabled: {str(review.get('production_write_enabled', False)).lower()}",
        "",
        "Review-only shadow outcome diagnostics. No production watchlist, broker, order, or execution state is modified.",
        "",
        "## Outcomes",
    ]
    for outcome in review.get("outcomes", []):
        lines.extend(
            [
                "",
                f"- {outcome.get('shadow_candidate_id', '')} | {outcome.get('asset_id', '')} | {outcome.get('outcome_status', '')}",
                f"  - source_p12_shadow_run_id: {outcome.get('source_p12_shadow_run_id', '')}",
                f"  - source_p11_replay_run_id: {outcome.get('source_p11_replay_run_id', '')}",
                f"  - source_p10_proposal_run_id: {outcome.get('source_p10_proposal_run_id', '')}",
                f"  - source_p9_analytics_run_id: {outcome.get('source_p9_analytics_run_id', '')}",
                f"  - available_future_bars: {outcome.get('available_future_bars', 0)}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _safe_path_part(value: Any) -> str:
    return str(value).replace("/", "-").replace(":", "-")


def _float_or_none(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(number) if pd.notna(number) else None


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
