from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Sequence
from typing import Any

import pandas as pd


PROFILE_RETURN_FIRST = "return_first"
PROFILE_BALANCED = "balanced"
PROFILE_DRAWDOWN_FIRST = "drawdown_first"


def run_official_strategy_contract_rescan(
    *,
    output_dir: str | Path,
    lhb_paths: Sequence[Path],
    mid_trend_paths: Sequence[Path],
    tech_bottleneck_paths: Sequence[Path],
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    candidates = pd.concat(
        [
            load_lhb_scan_candidates(lhb_paths),
            load_mid_trend_scan_candidates(mid_trend_paths),
            load_tech_bottleneck_scan_candidates(tech_bottleneck_paths),
        ],
        ignore_index=True,
    )
    profile_records: list[dict[str, Any]] = []
    for strategy_id in ["lhb_shortline", "mid_trend", "tech_bottleneck"]:
        profiles = select_strategy_profiles(candidates, strategy_id=strategy_id)
        profile_records.extend(profiles.values())

    selected = pd.DataFrame(profile_records)
    if not candidates.empty:
        candidates = candidates.copy()
        candidates["selected_profile"] = ""
        for record in profile_records:
            path = str(record.get("benchmark_artifact_path") or "")
            variant = str(record.get("variant") or "")
            strategy_id = str(record.get("strategy_id") or "")
            profile = str(record.get("selected_profile") or "")
            mask = (
                (candidates["strategy_id"].astype(str) == strategy_id)
                & (candidates["variant"].astype(str) == variant)
                & (candidates["benchmark_artifact_path"].astype(str) == path)
            )
            candidates.loc[mask, "selected_profile"] = profile

    candidates_path = output / "official_strategy_profile_candidates.csv"
    contracts_path = output / "official_strategy_contracts.json"
    report_path = output / "official_strategy_contract_rescan_report.md"
    candidates.to_csv(candidates_path, index=False)
    contracts_path.write_text(
        json.dumps(
            {
                "contract_version": "official_strategy_contract_rescan_v1",
                "profiles": profile_records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_render_rescan_report(profile_records), encoding="utf-8")
    return {
        "candidate_count": int(len(candidates)),
        "selected_count": int(len(profile_records)),
        "paths": {
            "candidates": str(candidates_path),
            "contracts": str(contracts_path),
            "report": str(report_path),
        },
        "profiles": profile_records,
    }


def load_lhb_scan_candidates(paths: Sequence[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        source = Path(path)
        if not source.exists():
            continue
        frame = pd.read_csv(source)
        if frame.empty:
            continue
        strategy = _column_or_default(frame, "strategy", "auction_enhanced_rerank").astype(str)
        risk_profile = _column_or_default(frame, "risk_profile", "").fillna("").astype(str)
        variant = strategy.where(risk_profile.eq(""), strategy + ":" + risk_profile)
        normalized = pd.DataFrame(
            {
                "strategy_id": "lhb_shortline",
                "engine": "lhb_shortline_v1",
                "variant": variant,
                "selected_profile_hint": risk_profile.map(_lhb_profile_hint),
                "profile_candidate_source": "lhb_phase18c",
                "top_n": _column_or_default(frame, "top_n", 5),
                "frequency": "daily",
                "protection_name": "",
                "transaction_cost_bps": _column_or_default(frame, "transaction_cost_bps", 10.0),
                "adjust_type": _column_or_default(frame, "adjust_type", "hfq"),
                "final_equity": _column_or_default(frame, "final_equity", pd.NA),
                "total_return": _column_or_default(frame, "total_return", pd.NA),
                "max_drawdown": _column_or_default(frame, "max_drawdown", pd.NA),
                "sharpe": _first_existing_column(frame, "sharpe", "sharpe_ratio"),
                "trade_rows": _first_existing_column(frame, "trade_rows", "filled_trade_count", default=1),
                "position_rows": _first_existing_column(frame, "position_rows", "filled_trade_count", default=1),
                "benchmark_artifact_path": str(source),
            }
        )
        frames.append(normalized)
    return _concat_frames(frames)


def load_mid_trend_scan_candidates(paths: Sequence[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        source = Path(path)
        if not source.exists():
            continue
        frame = pd.read_csv(source)
        if frame.empty:
            continue
        normalized = pd.DataFrame(
            {
                "strategy_id": "mid_trend",
                "engine": "mid_trend_v1",
                "variant": _first_existing_column(frame, "variant_name", "variant"),
                "profile_candidate_source": "mid_trend_weekly_control",
                "top_n": _column_or_default(frame, "top_n", 5),
                "frequency": _column_or_default(frame, "frequency", "weekly"),
                "protection_name": "",
                "transaction_cost_bps": _column_or_default(frame, "transaction_cost_bps", 20.0),
                "adjust_type": _column_or_default(frame, "adjust_type", "hfq"),
                "final_equity": _column_or_default(frame, "final_equity", pd.NA),
                "total_return": _column_or_default(frame, "total_return", pd.NA),
                "max_drawdown": _column_or_default(frame, "max_drawdown", pd.NA),
                "sharpe": _first_existing_column(frame, "sharpe", "sharpe_ratio"),
                "trade_rows": _column_or_default(frame, "trade_rows", 1),
                "position_rows": _column_or_default(frame, "position_rows", 1),
                "benchmark_artifact_path": str(source),
            }
        )
        frames.append(normalized)
    return _concat_frames(frames)


def load_tech_bottleneck_scan_candidates(paths: Sequence[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        source = Path(path)
        if not source.exists():
            continue
        frame = pd.read_csv(source)
        if frame.empty:
            continue
        universe = _column_or_default(frame, "universe", "strict_153")
        frequency = _column_or_default(frame, "frequency", "weekly")
        protection = _column_or_default(frame, "protection_name", "rank_exit_top10_1d")
        normalized = pd.DataFrame(
            {
                "strategy_id": "tech_bottleneck",
                "engine": "tech_bottleneck_v1",
                "variant": universe.astype(str) + ":" + frequency.astype(str) + ":" + protection.astype(str),
                "profile_candidate_source": "serenity_tight3b_c2",
                "top_n": _column_or_default(frame, "top_n", 5),
                "frequency": frequency,
                "protection_name": protection,
                "transaction_cost_bps": _column_or_default(frame, "transaction_cost_bps", 20.0),
                "adjust_type": _column_or_default(frame, "adjust_type", "hfq"),
                "final_equity": _final_equity_from_return(frame),
                "total_return": _column_or_default(frame, "total_return", pd.NA),
                "max_drawdown": _column_or_default(frame, "max_drawdown", pd.NA),
                "sharpe": _first_existing_column(frame, "sharpe", "sharpe_ratio"),
                "trade_rows": _column_or_default(frame, "trade_rows", 1),
                "position_rows": _column_or_default(frame, "position_rows", 1),
                "benchmark_artifact_path": str(source),
            }
        )
        frames.append(normalized)
    return _concat_frames(frames)


def select_strategy_profiles(candidates: pd.DataFrame, *, strategy_id: str) -> dict[str, dict[str, Any]]:
    frame = _eligible_candidates(candidates, strategy_id=strategy_id)
    if frame.empty:
        return {
            PROFILE_RETURN_FIRST: _unconfirmed(strategy_id, "no eligible candidates"),
            PROFILE_BALANCED: _unconfirmed(strategy_id, "no eligible candidates"),
            PROFILE_DRAWDOWN_FIRST: _unconfirmed(strategy_id, "no eligible candidates"),
        }

    scored = frame.copy()
    scored["_return_metric"] = _return_metric(scored)
    scored["_drawdown_abs"] = pd.to_numeric(scored.get("max_drawdown"), errors="coerce").abs()
    scored["_drawdown_control"] = 1.0 - _normalize(scored["_drawdown_abs"])
    scored["_return_score"] = _normalize(scored["_return_metric"])
    scored["_sharpe_score"] = _normalize(_metric_or_default(scored, "sharpe", "sharpe_ratio"))
    scored["_balanced_score"] = (
        scored["_return_score"] * 0.45
        + scored["_drawdown_control"] * 0.40
        + scored["_sharpe_score"] * 0.15
    )

    return_first = _explicit_profile(scored, PROFILE_RETURN_FIRST) or _profile_record(
            scored.sort_values(["_return_metric", "_drawdown_control"], ascending=[False, False]).iloc[0],
            PROFILE_RETURN_FIRST,
        )
    balanced = _explicit_profile(scored, PROFILE_BALANCED) or _balanced_profile_record(scored, return_first)
    drawdown_first = _explicit_profile(scored, PROFILE_DRAWDOWN_FIRST) or _profile_record(
            scored.sort_values(["_drawdown_abs", "_return_metric"], ascending=[True, False]).iloc[0],
            PROFILE_DRAWDOWN_FIRST,
        )
    return {
        PROFILE_RETURN_FIRST: return_first,
        PROFILE_BALANCED: balanced,
        PROFILE_DRAWDOWN_FIRST: drawdown_first,
    }


def _eligible_candidates(candidates: pd.DataFrame, *, strategy_id: str) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    frame = candidates.copy()
    if "strategy_id" in frame.columns:
        frame = frame[frame["strategy_id"].astype(str) == strategy_id].copy()
    if frame.empty:
        return frame
    for column in ["trade_rows", "position_rows"]:
        if column not in frame.columns:
            frame[column] = 1
    frame["trade_rows"] = pd.to_numeric(frame["trade_rows"], errors="coerce").fillna(0)
    frame["position_rows"] = pd.to_numeric(frame["position_rows"], errors="coerce").fillna(0)
    return frame[(frame["trade_rows"] > 0) & (frame["position_rows"] > 0)].copy()


def _return_metric(frame: pd.DataFrame) -> pd.Series:
    if "final_equity" in frame.columns:
        final_equity = pd.to_numeric(frame["final_equity"], errors="coerce")
        if final_equity.notna().any():
            return final_equity - 1.0
    if "total_return" in frame.columns:
        return pd.to_numeric(frame["total_return"], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=frame.index, dtype="float64")


def _metric_or_default(frame: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            if values.notna().any():
                return values.fillna(values.median())
    return pd.Series(0.0, index=frame.index, dtype="float64")


def _normalize(values: pd.Series) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce").fillna(0.0)
    low = float(series.min())
    high = float(series.max())
    if high <= low:
        return pd.Series(1.0, index=series.index, dtype="float64")
    return (series - low) / (high - low)


def _profile_record(row: pd.Series, profile: str) -> dict[str, Any]:
    record = {
        str(key): _json_scalar(value)
        for key, value in row.drop(labels=[key for key in row.index if str(key).startswith("_")]).items()
    }
    record["selected_profile"] = profile
    return record


def _explicit_profile(frame: pd.DataFrame, profile: str) -> dict[str, Any] | None:
    if "selected_profile_hint" not in frame.columns:
        return None
    hinted = frame[frame["selected_profile_hint"].astype(str).eq(profile)].copy()
    if hinted.empty:
        return None
    hinted["_return_metric"] = _return_metric(hinted)
    return _profile_record(
        hinted.sort_values(["_return_metric", "_drawdown_control"], ascending=[False, False]).iloc[0],
        profile,
    )


def _balanced_profile_record(frame: pd.DataFrame, return_first: dict[str, Any]) -> dict[str, Any]:
    return_metric = float(return_first.get("final_equity") or 1.0) - 1.0
    if return_metric <= 0:
        return _profile_record(
            frame.sort_values(["_balanced_score", "_return_metric"], ascending=[False, False]).iloc[0],
            PROFILE_BALANCED,
        )
    return_drawdown_abs = abs(float(return_first.get("max_drawdown") or 0.0))
    eligible = frame[
        (frame["_return_metric"] >= return_metric * 0.75)
        & (frame["_drawdown_abs"] < return_drawdown_abs - 1e-6)
    ].copy()
    if eligible.empty:
        record = _profile_record(
            frame.sort_values(["_balanced_score", "_return_metric"], ascending=[False, False]).iloc[0],
            PROFILE_BALANCED,
        )
        record["profile_selection_note"] = "no independent balanced candidate met 75% return and lower drawdown rule"
        return record
    return _profile_record(
        eligible.sort_values(["_balanced_score", "_return_metric"], ascending=[False, False]).iloc[0],
        PROFILE_BALANCED,
    )


def _unconfirmed(strategy_id: str, reason: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "selected_profile": "unconfirmed",
        "unconfirmed_reason": reason,
    }


def _json_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _column_or_default(frame: pd.DataFrame, column: str, default: Any) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series(default, index=frame.index)


def _first_existing_column(frame: pd.DataFrame, *columns: str, default: Any = pd.NA) -> pd.Series:
    for column in columns:
        if column in frame.columns:
            return frame[column]
    return pd.Series(default, index=frame.index)


def _final_equity_from_return(frame: pd.DataFrame) -> pd.Series:
    if "final_equity" in frame.columns:
        return frame["final_equity"]
    if "total_return" in frame.columns:
        return pd.to_numeric(frame["total_return"], errors="coerce") + 1.0
    return pd.Series(pd.NA, index=frame.index)


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _lhb_profile_hint(risk_profile: str) -> str:
    return {
        "return_max": PROFILE_RETURN_FIRST,
        "balanced": PROFILE_BALANCED,
        "drawdown_control": PROFILE_DRAWDOWN_FIRST,
    }.get(str(risk_profile), "")


def _render_rescan_report(profile_records: list[dict[str, Any]]) -> str:
    lines = [
        "# Official Strategy Contract Rescan",
        "",
        "| Strategy | Profile | Variant | Return | Max Drawdown | Source |",
        "|---|---|---|---:|---:|---|",
    ]
    for record in profile_records:
        lines.append(
            "| {strategy} | {profile} | {variant} | {ret} | {dd} | {source} |".format(
                strategy=record.get("strategy_id", ""),
                profile=record.get("selected_profile", ""),
                variant=record.get("variant", record.get("unconfirmed_reason", "")),
                ret=record.get("total_return", record.get("final_equity", "")),
                dd=record.get("max_drawdown", ""),
                source=record.get("benchmark_artifact_path", ""),
            )
        )
    lines.append("")
    return "\n".join(lines)
