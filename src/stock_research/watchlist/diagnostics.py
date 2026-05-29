from __future__ import annotations

from typing import Any

import pandas as pd


ALLOWED_OPPORTUNITY_STRUCTURES = {
    "second_wave_candidate",
    "break_then_reversal_candidate",
    "weak_to_strong_candidate",
    "trend_continuation_candidate",
}

TREND_CONTINUATION_MAX_SCORE_RANK = 20
DIAGNOSTICS_RULE_VERSION = "watchlist_diagnostics_v2_3"

EXCLUDED_FAILURE_STRUCTURES = {
    "a_kill_failure",
    "failed_second_wave",
    "high_open_low_close_failure",
    "one_day_pump",
    "failed_reversal",
}


def build_watchlist_diagnostics(
    *,
    trade_date: str,
    top_scores: pd.DataFrame,
    factor_frame: pd.DataFrame | None = None,
    dragon_frame: pd.DataFrame | None = None,
    lhb_frame: pd.DataFrame | None = None,
    event_frame: pd.DataFrame | None = None,
    market_frame: pd.DataFrame | None = None,
    risk_watch_n: int,
    opportunity_watch_n: int,
) -> dict[str, pd.DataFrame]:
    frame = _ensure_asset_frame(top_scores).copy()
    frame = frame.rename(columns={"rank": "score_rank"})
    frame["trade_date"] = trade_date

    frame = frame.merge(_merge_ready_frame(factor_frame), on="asset_id", how="left")
    frame = frame.merge(
        _merge_ready_frame(dragon_frame, defaults=_dragon_defaults()),
        on="asset_id",
        how="left",
    )
    frame = frame.merge(
        _merge_ready_frame(lhb_frame, defaults=_lhb_defaults()),
        on="asset_id",
        how="left",
    )
    frame = frame.merge(
        _merge_ready_frame(event_frame, defaults=_event_defaults()),
        on="asset_id",
        how="left",
    )
    frame = frame.merge(
        _merge_ready_frame(market_frame, defaults=_market_defaults()),
        on="asset_id",
        how="left",
    )
    frame = _ensure_columns(frame, _classification_defaults())

    frame["failure_flag"] = frame["failure_flag"].map(_coerce_bool)
    frame["event_structure"] = frame.apply(_resolved_event_structure, axis=1)
    frame["watch_group"] = frame.apply(_classify_watch_group, axis=1)
    frame["watch_priority"] = frame.apply(_priority_value, axis=1)
    frame["diagnostic_reason"] = frame.apply(_diagnostic_reason, axis=1)
    frame["risk_note"] = frame.apply(_risk_note, axis=1)
    frame["opportunity_note"] = frame.apply(_opportunity_note, axis=1)
    frame["opportunity_flag"] = frame["watch_group"].eq("opportunity_watch")
    frame["diagnostics_rule_version"] = DIAGNOSTICS_RULE_VERSION

    risk_rows = frame[frame["watch_group"] == "risk_watch"].sort_values(
        by=["watch_priority", "score_rank", "asset_id"]
    ).head(risk_watch_n)
    opportunity_rows = frame[frame["watch_group"] == "opportunity_watch"].sort_values(
        by=["watch_priority", "score_rank", "asset_id"]
    ).head(opportunity_watch_n)
    must_watch = pd.concat([risk_rows, opportunity_rows], ignore_index=True)

    return {
        "full": frame.sort_values(by=["score_rank", "asset_id"]).reset_index(drop=True),
        "must_watch": must_watch.reset_index(drop=True),
    }


def _ensure_asset_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame(columns=["asset_id"])
    result = frame.copy()
    if "asset_id" not in result.columns:
        result["asset_id"] = pd.Series(dtype="object")
    return result


def _ensure_columns(frame: pd.DataFrame, defaults: dict[str, Any]) -> pd.DataFrame:
    result = frame.copy()
    for column, value in defaults.items():
        if column not in result.columns:
            result[column] = value
    return result


def _merge_ready_frame(frame: pd.DataFrame | None, *, defaults: dict[str, Any] | None = None) -> pd.DataFrame:
    result = _ensure_asset_frame(frame)
    if defaults:
        result = _ensure_columns(result, defaults)
    if result.empty:
        return result
    return _latest_per_asset_id(result).reset_index(drop=True)


def _classify_watch_group(row: pd.Series) -> str:
    structure = _normalize_text(row.get("event_structure"))
    dragon_risk = _coerce_float(row.get("dragon_risk_score"))
    lhb_risk = _coerce_float(row.get("lhb_risk_score"))
    amount_vs_20d = _coerce_float(row.get("amount_vs_20d"))
    high_to_close_drawdown = _coerce_float(row.get("high_to_close_drawdown"))

    if structure in EXCLUDED_FAILURE_STRUCTURES or _coerce_bool(row.get("failure_flag")):
        return "risk_watch"
    if dragon_risk >= 0.7 or lhb_risk >= 0.7:
        return "risk_watch"
    if _coerce_bool(row.get("lhb_high_pump_risk")):
        return "risk_watch"
    if _coerce_bool(row.get("lhb_after_event_attention")) and (
        _coerce_bool(row.get("lhb_negative_net_buy"))
        or _coerce_bool(row.get("lhb_institution_selling"))
    ):
        return "risk_watch"
    if _risk_confirmation_count(row) >= 2:
        return "risk_watch"
    if amount_vs_20d >= 4.0 or high_to_close_drawdown >= 0.08:
        return "risk_watch"
    if structure in ALLOWED_OPPORTUNITY_STRUCTURES:
        return "opportunity_watch"
    return "candidate"


def _priority_value(row: pd.Series) -> int:
    watch_group = row.get("watch_group")
    if watch_group == "risk_watch":
        return _risk_priority_value(row)
    if watch_group == "opportunity_watch":
        return _opportunity_priority_value(row)
    return 999


def _diagnostic_reason(row: pd.Series) -> str:
    structure = _normalize_text(row.get("event_structure")) or "unknown"
    return f"{row.get('watch_group')}:{structure}"


def _risk_note(row: pd.Series) -> str:
    notes: list[str] = []
    if _coerce_float(row.get("dragon_risk_score")) >= 0.7:
        notes.append("dragon_risk_high")
    if _coerce_float(row.get("lhb_risk_score")) >= 0.7:
        notes.append("lhb_risk_high")
    if _coerce_bool(row.get("overheat_avoid")):
        notes.append("overheat_avoid")
    if _coerce_bool(row.get("crowded_late_entry")):
        notes.append("crowded_late_entry")
    if _coerce_bool(row.get("lhb_negative_net_buy")):
        notes.append("lhb_negative_net_buy")
    if _coerce_bool(row.get("lhb_institution_selling")):
        notes.append("lhb_institution_selling")
    if _coerce_bool(row.get("lhb_high_pump_risk")):
        notes.append("lhb_high_pump_risk")
    if _coerce_bool(row.get("lhb_after_event_attention")):
        notes.append("lhb_after_event_attention")
    if _coerce_float(row.get("amount_vs_20d")) >= 4.0:
        notes.append("extreme_amount")
    if _coerce_float(row.get("high_to_close_drawdown")) >= 0.08:
        notes.append("intraday_fade")
    return ",".join(notes)


def _opportunity_note(row: pd.Series) -> str:
    if row.get("watch_group") != "opportunity_watch":
        return ""
    return _normalize_text(row.get("event_structure"))


def _coerce_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except Exception:
        pass
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "f", "no", "n", "off", "none", "null"}:
            return False
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
    return bool(value)


def _normalize_text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if value is None:
        return ""
    return str(value).strip()


def _risk_confirmation_count(row: pd.Series) -> int:
    return sum(
        (
            _coerce_bool(row.get("overheat_avoid")),
            _coerce_bool(row.get("crowded_late_entry")),
            _coerce_bool(row.get("lhb_negative_net_buy")),
            _coerce_bool(row.get("lhb_institution_selling")),
            _coerce_bool(row.get("lhb_high_pump_risk")),
        )
    )


def _dragon_defaults() -> dict[str, Any]:
    return {
        "dragon_risk_score": 0.0,
        "overheat_avoid": False,
        "crowded_late_entry": False,
    }


def _lhb_defaults() -> dict[str, Any]:
    return {
        "lhb_risk_score": 0.0,
        "lhb_negative_net_buy": False,
        "lhb_institution_selling": False,
        "lhb_high_pump_risk": False,
        "lhb_after_event_attention": False,
    }


def _event_defaults() -> dict[str, Any]:
    return {
        "event_structure": "",
        "failure_flag": False,
    }


def _market_defaults() -> dict[str, Any]:
    return {}


def _classification_defaults() -> dict[str, Any]:
    return {
        **_dragon_defaults(),
        **_lhb_defaults(),
        **_event_defaults(),
        "amount_vs_20d": 0.0,
        "high_to_close_drawdown": 0.0,
        "volatility_5d": 0.0,
    }


def _risk_priority_value(row: pd.Series) -> int:
    structure = _normalize_text(row.get("event_structure"))
    failure_priority = {
        "a_kill_failure": 0,
        "failed_second_wave": 1,
        "high_open_low_close_failure": 2,
        "one_day_pump": 3,
        "failed_reversal": 4,
    }
    if structure in failure_priority:
        return failure_priority[structure]
    if _coerce_float(row.get("dragon_risk_score")) >= 0.7 or _coerce_float(row.get("lhb_risk_score")) >= 0.7:
        return 10
    if _risk_confirmation_count(row) >= 2:
        return 20
    if _coerce_bool(row.get("lhb_high_pump_risk")) or _coerce_bool(row.get("lhb_after_event_attention")):
        return 30
    if _coerce_float(row.get("amount_vs_20d")) >= 4.0 or _coerce_float(row.get("high_to_close_drawdown")) >= 0.08:
        return 40
    return 90


def _opportunity_priority_value(row: pd.Series) -> int:
    structure = _normalize_text(row.get("event_structure"))
    structure_priority = {
        "weak_to_strong_candidate": 100,
        "break_then_reversal_candidate": 110,
        "second_wave_candidate": 120,
        "trend_continuation_candidate": 130,
    }
    base = structure_priority.get(structure, 190)
    risk_penalty = int(round(min(_coerce_float(row.get("dragon_risk_score")), 0.99) * 10))
    return base + risk_penalty


def _resolved_event_structure(row: pd.Series) -> str:
    structure = _normalize_text(row.get("event_structure"))
    if structure:
        return structure
    inferred = _infer_opportunity_structure(row)
    return inferred


def _infer_opportunity_structure(row: pd.Series) -> str:
    entry_window_v2 = _normalize_text(row.get("entry_window_v2"))
    entry_window = _normalize_text(row.get("entry_window"))
    score_rank = _coerce_float(row.get("score_rank"))
    dragon_risk = _coerce_float(row.get("dragon_risk_score"))
    amount_vs_20d = _coerce_float(row.get("amount_vs_20d"))
    volatility_5d = _coerce_float(row.get("volatility_5d"))
    high_to_close_drawdown = _coerce_float(row.get("high_to_close_drawdown"))
    if entry_window_v2 == "low_congestion_opportunity":
        return "second_wave_candidate"
    if entry_window_v2 == "recovery_or_repair":
        return "break_then_reversal_candidate"
    if (
        entry_window == "early_setup"
        and entry_window_v2 == "breakout_entry"
        and dragon_risk < 0.12
        and 0.9 <= amount_vs_20d <= 1.8
        and volatility_5d <= 0.025
        and high_to_close_drawdown <= 0.015
    ):
        return "break_then_reversal_candidate"
    if entry_window_v2 == "early_setup":
        return "weak_to_strong_candidate"
    if entry_window_v2 == "breakout_entry" and 0 < score_rank <= TREND_CONTINUATION_MAX_SCORE_RANK:
        return "trend_continuation_candidate"
    return ""


def _latest_per_asset_id(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "asset_id" not in frame.columns:
        return frame
    for date_column in ("case_event_date", "lhb_event_date", "dragon_trade_date", "event_date", "trade_date"):
        if date_column not in frame.columns:
            continue
        ordered = frame.copy()
        ordered[date_column] = pd.to_datetime(ordered[date_column], errors="coerce")
        tie_break_columns = [
            column
            for column in sorted(ordered.columns)
            if column not in {"asset_id", date_column}
        ]
        ordered = ordered.sort_values(
            ["asset_id", date_column, *tie_break_columns],
            kind="stable",
        )
        return ordered.drop_duplicates(subset=["asset_id"], keep="last")
    return frame.drop_duplicates(subset=["asset_id"], keep="first")
