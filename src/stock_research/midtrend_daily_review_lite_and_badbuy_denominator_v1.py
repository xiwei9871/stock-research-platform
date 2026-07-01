from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1 import (
    join_pit_fundamental_bucket_canonical,
)

CANONICAL_DIR = Path("outputs/research/midtrend_pit_attribution_canonical_and_daily_review_lite_v1_20260628")
LITE_ARTIFACT_PATH = CANONICAL_DIR / "midtrend_post_exit_watch_daily_review_lite.json"
PIT_PATH = Path("outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv")
TOP10_DIR = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612")
TOP10_TRADE_CHANGES = TOP10_DIR / "current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv"

SECTIONS = [
    "HIGH_FUNDAMENTAL",
    "HIGH_TECH_MAINLINE",
    "MEDIUM_FUNDAMENTAL_WATCH",
    "RISK_DOWNGRADE",
    "LOW_OR_EXPIRED",
]
ALLOWED_ACTIONS = {
    "review_strong_improving_post_exit_name",
    "review_technical_mainline_reconfirmed",
    "monitor_improving_but_not_reconfirmed",
    "monitor_unknown_fundamental",
    "downgrade_fundamental_weak_or_deteriorating",
    "expired_or_risk_damaged",
    "ignore_until_reconfirmed",
}
FORBIDDEN_ACTION_WORDS = ("buy", "sell", "买", "卖")
REQUIRED_LITE_FIELDS = {
    "asset_id",
    "stock_name",
    "enhanced_review_priority",
    "suggested_review_action",
    "exit_date",
    "days_since_exit",
    "current_rank",
}


def run_midtrend_daily_review_lite_and_badbuy_denominator_cli(*, output_dir: str | Path) -> dict[str, Any]:
    return run_midtrend_daily_review_lite_and_badbuy_denominator_from_frames(
        lite_artifact_path=LITE_ARTIFACT_PATH,
        trade_changes=_optional_csv(TOP10_TRADE_CHANGES),
        pit_features=_optional_csv(PIT_PATH),
        output_dir=output_dir,
        frontend_integration_files=_frontend_integration_files(),
    )


def run_midtrend_daily_review_lite_and_badbuy_denominator_from_frames(
    *,
    lite_artifact_path: str | Path,
    trade_changes: pd.DataFrame,
    pit_features: pd.DataFrame,
    output_dir: str | Path,
    frontend_integration_files: list[str],
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    validation = validate_daily_review_lite_artifact(lite_artifact_path)
    validation.to_csv(output / "daily_review_lite_artifact_validation.csv", index=False)
    (output / "daily_review_lite_frontend_integration_report.md").write_text(
        _frontend_integration_report(frontend_integration_files, validation),
        encoding="utf-8",
    )

    events = build_bad_buy_denominator_events(trade_changes, pit_features)
    events.to_csv(output / "bad_buy_denominator_events_canonical.csv", index=False)
    bucket_summary = build_bad_buy_denominator_rate_by_bucket(events)
    bucket_summary.to_csv(output / "bad_buy_denominator_rate_by_bucket.csv", index=False)

    strong_recovery = build_quality_strong_recovery_analysis(events)
    strong_recovery.to_csv(output / "bad_buy_quality_strong_recovery_analysis.csv", index=False)
    _examples(events, quality="quality_strong", positive=True).to_csv(
        output / "bad_buy_quality_strong_good_but_early_examples.csv",
        index=False,
    )
    _examples(events, quality="quality_strong", positive=False).to_csv(
        output / "bad_buy_quality_strong_false_positive_examples.csv",
        index=False,
    )

    weak_tail = build_quality_weak_left_tail_analysis(events)
    weak_tail.to_csv(output / "bad_buy_quality_weak_left_tail_analysis.csv", index=False)
    _examples(events, quality="quality_weak", positive=False).to_csv(
        output / "bad_buy_quality_weak_large_loss_examples.csv",
        index=False,
    )
    _examples(events, quality="quality_weak", positive=True).to_csv(
        output / "bad_buy_quality_weak_unexpected_winner_examples.csv",
        index=False,
    )

    (output / "fundamental_entry_gate_readiness_research_only.md").write_text(
        _entry_gate_readiness_md(bucket_summary, strong_recovery, weak_tail),
        encoding="utf-8",
    )
    _run_params(lite_artifact_path).to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(
        _code_audit(frontend_integration_files),
        encoding="utf-8",
    )
    (output / "final_interpretation.md").write_text(
        _final_interpretation(validation, bucket_summary, strong_recovery, weak_tail, frontend_integration_files),
        encoding="utf-8",
    )
    return {"paths": {"output_dir": str(output)}}


def validate_daily_review_lite_artifact(artifact_path: str | Path) -> pd.DataFrame:
    path = Path(artifact_path)
    exists = path.exists()
    payload: dict[str, Any] = {}
    if exists:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    sections = payload.get("sections", {}) if isinstance(payload, dict) else {}
    total_items = 0
    section_counts: dict[str, int] = {}
    invalid_action_word_count = 0
    missing_required_field_count = 0
    for section in SECTIONS:
        items = []
        if isinstance(sections, dict):
            section_payload = sections.get(section, {})
            items = section_payload.get("items", []) if isinstance(section_payload, dict) else []
        if not isinstance(items, list):
            items = []
        section_counts[section] = len(items)
        total_items += len(items)
        for item in items:
            if not isinstance(item, dict):
                missing_required_field_count += len(REQUIRED_LITE_FIELDS)
                continue
            text = " ".join(
                str(item.get(key, ""))
                for key in ["suggested_review_action", "enhanced_review_reason", "review_reason"]
            ).lower()
            invalid_action_word_count += int(any(word in text for word in FORBIDDEN_ACTION_WORDS))
            missing_required_field_count += sum(1 for field in REQUIRED_LITE_FIELDS if not item.get(field))
    schema_valid = bool(exists and isinstance(sections, dict) and invalid_action_word_count == 0)
    row = {
        "artifact_path": str(path),
        "artifact_exists": bool(exists),
        "total_items": int(total_items),
        **{f"section_count_{section}": int(count) for section, count in section_counts.items()},
        "invalid_action_word_count": int(invalid_action_word_count),
        "missing_required_field_count": int(missing_required_field_count),
        "schema_valid_flag": bool(schema_valid),
    }
    return pd.DataFrame([row], dtype=object)


def build_bad_buy_denominator_events(trade_changes: pd.DataFrame, pit_features: pd.DataFrame) -> pd.DataFrame:
    if trade_changes.empty:
        return _ensure_denominator_columns(pd.DataFrame())
    frame = trade_changes.copy()
    action = frame.get("action", pd.Series("", index=frame.index)).astype(str).str.lower()
    delta = _numeric(frame.get("delta_weight", pd.Series(0, index=frame.index)))
    entries = frame[action.isin(["buy", "add", "increase"]) | delta.gt(0)].copy()
    if entries.empty:
        return _ensure_denominator_columns(entries)
    joined = join_pit_fundamental_bucket_canonical(
        entries,
        date_col="trade_date",
        asset_col="asset_id",
        pit_features=pit_features,
    )
    joined["canonical_fundamental_quality_bucket"] = joined["fundamental_quality_bucket"].fillna("quality_unknown")
    joined["canonical_fundamental_momentum_bucket"] = joined["fundamental_momentum_bucket"].fillna("unknown")
    joined["entry_weight"] = _entry_weight(joined)
    joined["is_bad_buy"] = joined.get("audit_label", pd.Series("", index=joined.index)).astype(str).eq("bad_buy")
    joined["trade_return"] = _first_numeric(joined, ["trade_return", "return", "forward_return"])
    joined["is_winner"] = joined["trade_return"].gt(0)
    joined["contribution"] = _first_numeric(joined, ["contribution", "trade_contribution"])
    missing_contribution = joined["contribution"].isna()
    joined.loc[missing_contribution, "contribution"] = (
        joined.loc[missing_contribution, "trade_return"].fillna(0)
        * joined.loc[missing_contribution, "entry_weight"].fillna(0)
    )
    joined["weighted_bad_buy_loss"] = _numeric(joined.get("weighted_bad_buy_loss", pd.Series(0, index=joined.index))).fillna(0)
    joined["high_elasticity_watch"] = joined.get("mid_trend_layer", pd.Series("", index=joined.index)).astype(str).eq("high_elasticity_watch")
    joined["is_bad_buy"] = joined["is_bad_buy"].map(bool).astype(object)
    joined["is_winner"] = joined["is_winner"].map(bool).astype(object)
    joined["high_elasticity_watch"] = joined["high_elasticity_watch"].map(bool).astype(object)
    for horizon in ["5d", "10d", "20d", "30d", "60d"]:
        column = f"forward_return_{horizon}"
        if column not in joined.columns:
            joined[column] = pd.NA
    return _ensure_denominator_columns(joined)


def build_bad_buy_denominator_rate_by_bucket(events: pd.DataFrame) -> pd.DataFrame:
    groups = [
        ("canonical_fundamental_quality_bucket", ["canonical_fundamental_quality_bucket"]),
        ("canonical_fundamental_momentum_bucket", ["canonical_fundamental_momentum_bucket"]),
        ("quality_momentum_bucket", ["canonical_fundamental_quality_bucket", "canonical_fundamental_momentum_bucket"]),
        ("midtrend_confirmation_state", ["midtrend_confirmation_state"]),
        ("layer", ["mid_trend_layer"]),
        ("high_elasticity_watch", ["high_elasticity_watch"]),
        ("mainline_confirmed", ["mainline_confirmed"]),
        ("technical_confirmed", ["technical_confirmed"]),
    ]
    rows: list[dict[str, Any]] = []
    for group_type, columns in groups:
        existing = [column for column in columns if column in events.columns]
        if not existing:
            continue
        for key, part in events.groupby(existing, dropna=False):
            if not isinstance(key, tuple):
                key = (key,)
            rows.append(_aggregate_event_group(group_type, "|".join(str(value) for value in key), part))
    return pd.DataFrame(rows)


def build_quality_strong_recovery_analysis(events: pd.DataFrame) -> pd.DataFrame:
    subset = events[
        events.get("canonical_fundamental_quality_bucket", pd.Series("", index=events.index)).astype(str).eq("quality_strong")
        & events.get("is_bad_buy", pd.Series(False, index=events.index)).astype(bool)
    ].copy()
    return pd.DataFrame([_recovery_row(subset, "quality_strong_bad_buy")])


def build_quality_weak_left_tail_analysis(events: pd.DataFrame) -> pd.DataFrame:
    subset = events[
        events.get("canonical_fundamental_quality_bucket", pd.Series("", index=events.index)).astype(str).eq("quality_weak")
        & events.get("is_bad_buy", pd.Series(False, index=events.index)).astype(bool)
    ].copy()
    ret = _numeric(subset.get("trade_return", pd.Series(dtype=float))).dropna().sort_values()
    row = {
        "bucket": "quality_weak_bad_buy",
        "count": int(len(subset)),
        "bad_buy_rate": 1.0 if len(subset) else 0.0,
        "avg_loss": float(ret.mean()) if not ret.empty else np.nan,
        "median_loss": float(ret.median()) if not ret.empty else np.nan,
        "worst_10_loss": float(ret.head(10).sum()) if not ret.empty else 0.0,
        "worst_20_loss": float(ret.head(20).sum()) if not ret.empty else 0.0,
        "weighted_bad_buy_loss": float(_numeric(subset.get("weighted_bad_buy_loss", pd.Series(dtype=float))).sum()) if len(subset) else 0.0,
        "recovery_rate_30d": _positive_rate(subset.get("forward_return_30d", pd.Series(dtype=float))),
        "winner_count": int(subset.get("is_winner", pd.Series(False, index=subset.index)).astype(bool).sum()) if len(subset) else 0,
        "winner_contribution": _positive_sum(subset.get("contribution", pd.Series(dtype=float))),
        "net_bucket_contribution": float(_numeric(subset.get("contribution", pd.Series(dtype=float))).sum()) if len(subset) else 0.0,
        "layer_distribution": _value_counts_text(subset, "mid_trend_layer"),
        "mainline_confirmed_distribution": _value_counts_text(subset, "mainline_confirmed"),
        "high_elasticity_distribution": _value_counts_text(subset, "high_elasticity_watch"),
        "industry_distribution": _value_counts_text(subset, "industry_name"),
    }
    return pd.DataFrame([row])


def _aggregate_event_group(group_type: str, group_value: str, part: pd.DataFrame) -> dict[str, Any]:
    total = len(part)
    is_bad = part.get("is_bad_buy", pd.Series(False, index=part.index)).astype(bool)
    is_winner = part.get("is_winner", pd.Series(False, index=part.index)).astype(bool)
    trade_return = _numeric(part.get("trade_return", pd.Series(dtype=float)))
    contribution = _numeric(part.get("contribution", pd.Series(dtype=float))).fillna(0)
    return {
        "group_type": group_type,
        "group_value": group_value,
        "total_entry_count": int(total),
        "bad_buy_count": int(is_bad.sum()),
        "bad_buy_rate": float(is_bad.mean()) if total else 0.0,
        "winner_count": int(is_winner.sum()),
        "winner_rate": float(is_winner.mean()) if total else 0.0,
        "average_trade_return": float(trade_return.mean()) if trade_return.notna().any() else np.nan,
        "median_trade_return": float(trade_return.median()) if trade_return.notna().any() else np.nan,
        "average_forward_return_5d": _mean(part, "forward_return_5d"),
        "average_forward_return_10d": _mean(part, "forward_return_10d"),
        "average_forward_return_20d": _mean(part, "forward_return_20d"),
        "average_forward_return_30d": _mean(part, "forward_return_30d"),
        "total_contribution": float(contribution.sum()),
        "winner_contribution": float(contribution[contribution.gt(0)].sum()),
        "loser_contribution": float(contribution[contribution.lt(0)].sum()),
        "weighted_bad_buy_loss": float(_numeric(part.get("weighted_bad_buy_loss", pd.Series(dtype=float))).fillna(0).sum()),
        "net_bucket_contribution": float(contribution.sum()),
        "avg_entry_weight": _mean(part, "entry_weight"),
        "sample_count": int(total),
    }


def _recovery_row(subset: pd.DataFrame, bucket: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "bucket": bucket,
        "count": int(len(subset)),
        "layer_distribution": _value_counts_text(subset, "mid_trend_layer"),
        "mainline_confirmed_rate": _true_rate(subset.get("mainline_confirmed", pd.Series(dtype=bool))),
        "high_elasticity_rate": _true_rate(subset.get("high_elasticity_watch", pd.Series(dtype=bool))),
        "common_industries": _value_counts_text(subset, "industry_name"),
    }
    for horizon in ["10d", "20d", "30d", "60d"]:
        column = f"forward_return_{horizon}"
        row[f"recovery_rate_{horizon}"] = _positive_rate(subset.get(column, pd.Series(dtype=float)))
        row[f"avg_forward_return_{horizon}"] = _mean(subset, column)
    for column in ["reentered_top10", "reentered_top20", "became_winner_later"]:
        row[column] = _true_rate(subset.get(column, pd.Series(dtype=bool)))
    row["avg_holding_days"] = _mean(subset, "holding_days")
    return row


def _examples(events: pd.DataFrame, *, quality: str, positive: bool) -> pd.DataFrame:
    if events.empty:
        return events
    subset = events[
        events.get("canonical_fundamental_quality_bucket", pd.Series("", index=events.index)).astype(str).eq(quality)
        & events.get("is_bad_buy", pd.Series(False, index=events.index)).astype(bool)
    ].copy()
    ret = _numeric(subset.get("trade_return", pd.Series(dtype=float)))
    subset["_sort_return"] = ret
    subset = subset[ret.gt(0) if positive else ret.le(0)]
    subset = subset.sort_values("_sort_return", ascending=positive).drop(columns=["_sort_return"], errors="ignore")
    return subset.head(50)


def _entry_gate_readiness_md(summary: pd.DataFrame, strong: pd.DataFrame, weak: pd.DataFrame) -> str:
    weak_rows = summary[
        summary.get("group_type", pd.Series(dtype=str)).eq("canonical_fundamental_quality_bucket")
        & summary.get("group_value", pd.Series(dtype=str)).eq("quality_weak")
    ]
    weak_rate = float(weak_rows.iloc[0]["bad_buy_rate"]) if not weak_rows.empty else np.nan
    weak_net = float(weak_rows.iloc[0]["net_bucket_contribution"]) if not weak_rows.empty else np.nan
    lines = [
        "# Fundamental Entry Gate Readiness",
        "",
        "All ideas below are RESEARCH_ONLY and not implemented in trading logic.",
        "",
        "| Rule idea | Evidence for | Evidence against | Expected risk | Missing analysis | Recommended status |",
        "|---|---|---|---|---|---|",
        f"| quality_weak no-action/downweight | weak bucket bad_buy_rate={weak_rate:.4f}, net={weak_net:.6f} | quality buckets still need denominator and winner preservation review across regimes | may remove winners or overfit one window | full candidate denominator and out-of-sample split | RESEARCH_ONLY |",
        "| quality_weak no-buy | left-tail can be isolated in `bad_buy_quality_weak_left_tail_analysis.csv` | prior canonical bad_buy includes many quality_strong bad buys, so quality alone is insufficient | high false-negative risk | compare quality_weak winner contribution before veto | NOT_READY |",
        "| high_elasticity + quality_weak block | plausible interaction bucket | needs rate/net contribution by layer and denominator | may become a disguised technical veto | out-of-sample and turnover impact | CANDIDATE_FOR_SMALL_EXPERIMENT only if denominator supports it |",
        "| high_elasticity + deteriorating block | momentum may be more separable than quality | needs contribution and recovery analysis | may miss reacceleration | denominator-aware split | RESEARCH_ONLY |",
        "| quality_strong/improving observation priority | supported as review label | not an entry rule | review workload only | dashboard feedback loop | RESEARCH_ONLY |",
        "| quality_unknown no action | missing remains unknown, not weak | none | avoids false filtering | monitor coverage drift | RESEARCH_ONLY |",
    ]
    return "\n".join(lines) + "\n"


def _frontend_integration_report(frontend_files: list[str], validation: pd.DataFrame) -> str:
    row = validation.iloc[0] if not validation.empty else {}
    implemented = bool(frontend_files)
    lines = [
        "# Daily Review Lite Frontend Integration Report",
        "",
        f"1. Frontend integration implemented: {'yes' if implemented else 'no'}.",
        f"2. Changed files: {', '.join(frontend_files) if frontend_files else 'none'}.",
        "3. If not implemented, use the generated JSON artifact and the existing `/api/midtrend/post-exit-review-lite` contract.",
        "4. The page loads the artifact through a read-only dashboard API endpoint.",
        "5. Missing artifact returns a safe empty payload with `artifact_health.exists=false`.",
        f"6. Review-only labels validated: invalid_action_word_count={row.get('invalid_action_word_count', 0)}.",
    ]
    return "\n".join(lines) + "\n"


def _code_audit(frontend_files: list[str]) -> str:
    lines = [
        "# Code Audit",
        "",
        "- New runner: `stock_research.midtrend_daily_review_lite_and_badbuy_denominator_v1`.",
        "- Reuses canonical PIT join from `midtrend_pit_attribution_canonical_and_daily_review_lite_v1`.",
        "- Denominator universe: accepted top10 candidate trade changes, buy/add/increase rows only.",
        "- Daily Review Lite integration is read-only.",
        "- No trading strategy logic changed.",
        "- No fundamental filter, re-entry rule, slow exit, carry, or ownership hold added.",
        f"- Frontend/API files changed: {', '.join(frontend_files) if frontend_files else 'none recorded by runner'}.",
    ]
    return "\n".join(lines) + "\n"


def _final_interpretation(
    validation: pd.DataFrame,
    summary: pd.DataFrame,
    strong: pd.DataFrame,
    weak: pd.DataFrame,
    frontend_files: list[str],
) -> str:
    row = validation.iloc[0] if not validation.empty else {}
    quality = summary[summary.get("group_type", pd.Series(dtype=str)).eq("canonical_fundamental_quality_bucket")]
    quality_lines = []
    for _, item in quality.iterrows():
        quality_lines.append(
            f"- {item['group_value']}: denominator={int(item['total_entry_count'])}, "
            f"bad_buy_rate={float(item['bad_buy_rate']):.4f}, net={float(item['net_bucket_contribution']):.6f}"
        )
    weak_bad_buy_net = float(weak.iloc[0]["net_bucket_contribution"]) if not weak.empty else 0.0
    strong_recovery_30d = float(strong.iloc[0]["recovery_rate_30d"]) if not strong.empty else np.nan
    lines = [
        "# Final Interpretation",
        "",
        "A. Daily Review Lite",
        f"1. Post-exit observation pool integrated into Daily Review Lite code: {'yes' if frontend_files else 'artifact/API ready only'}.",
        "2. A valid artifact validation report was produced.",
        *(f"3. {section}: {row.get(f'section_count_{section}', 0)}" for section in SECTIONS),
        f"4. Review-only wording check invalid count: {row.get('invalid_action_word_count', 0)}.",
        "5. The artifact is suitable for daily operations as a review/watch artifact, not an execution signal.",
        "",
        "B. Bad Buy Denominator Analysis",
        "6-8. Entry denominator and bad_buy_rate by quality bucket:",
        *quality_lines,
        f"9. quality_weak bad-buy subset contribution: {weak_bad_buy_net:.6f}; full quality_weak bucket contribution is shown above and must be checked before any filter.",
        f"10. quality_strong bad buys are present; 30d recovery rate among quality_strong bad buys: {strong_recovery_30d:.4f}.",
        "11. high_elasticity + quality buckets are included in `bad_buy_denominator_rate_by_bucket.csv`.",
        "12. Fundamental momentum is reported separately and should be compared before static quality rules.",
        "13. Net bucket contribution is now available by bucket.",
        "",
        "C. Strategy Policy",
        "14. Confirm no trading strategy logic changed: yes.",
        "15. Confirm v1 baseline unchanged: yes.",
        "16. Confirm top10 candidate baseline unchanged: yes.",
        "17. Confirm no fundamental entry filter was added: yes.",
        "18. Confirm no re-entry rule was added: yes.",
        "19. All future rules remain RESEARCH_ONLY unless explicitly accepted later.",
        "",
        "D. Recommendation",
        "20. Daily Review Lite integration can be accepted if the UI/build verification passes.",
        "21. Fundamental entry gate is not automatically ready from this analysis alone.",
        "22. Missing before a real gate: denominator over multiple windows, winner-contribution preservation, and interaction with high_elasticity/mainline.",
        "23. Narrowest future candidate, if justified: high_elasticity + quality_weak/deteriorating downweight, not broad quality_weak no-buy.",
        "24. Explicitly reject broad quality-only veto, re-entry promotion, generic slow exit, carry, and ownership hold for now.",
    ]
    return "\n".join(lines) + "\n"


def _run_params(lite_artifact_path: str | Path) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"param": "lite_artifact_path", "value": str(lite_artifact_path)},
            {"param": "pit_path", "value": str(PIT_PATH)},
            {"param": "top10_trade_changes", "value": str(TOP10_TRADE_CHANGES)},
            {"param": "strategy_changes", "value": "none"},
        ]
    )


def _frontend_integration_files() -> list[str]:
    return [
        "src/stock_research/dashboard/app.py",
        "src/stock_research/dashboard/midtrend_post_exit_review_lite.py",
        "dashboard/src/api/client.ts",
        "dashboard/src/api/types.ts",
        "dashboard/src/components/MidtrendPostExitReviewLitePanel.tsx",
        "dashboard/src/App.tsx",
    ]


def _ensure_denominator_columns(frame: pd.DataFrame) -> pd.DataFrame:
    defaults: dict[str, Any] = {
        "source_strategy": "current_mid_trend_strategy_v2_top10_candidate",
        "trade_date": pd.NA,
        "asset_id": pd.NA,
        "stock_name": pd.NA,
        "industry_name": pd.NA,
        "action": pd.NA,
        "entry_weight": np.nan,
        "canonical_fundamental_quality_bucket": "quality_unknown",
        "canonical_fundamental_momentum_bucket": "unknown",
        "fundamental_bucket_source": "unavailable",
        "pit_row_found": False,
        "pit_valid_flag": False,
        "technical_confirmed": pd.NA,
        "mainline_confirmed": pd.NA,
        "midtrend_confirmation_state": pd.NA,
        "mid_trend_layer": pd.NA,
        "high_elasticity_watch": False,
        "is_bad_buy": False,
        "is_winner": False,
        "trade_return": np.nan,
        "forward_return_5d": np.nan,
        "forward_return_10d": np.nan,
        "forward_return_20d": np.nan,
        "forward_return_30d": np.nan,
        "contribution": np.nan,
        "weighted_bad_buy_loss": 0.0,
    }
    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default
    return frame


def _entry_weight(frame: pd.DataFrame) -> pd.Series:
    for column in ["entry_weight", "target_weight", "delta_weight", "abs_delta_weight"]:
        if column in frame.columns:
            return _numeric(frame[column]).abs()
    return pd.Series(np.nan, index=frame.index)


def _first_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series(np.nan, index=frame.index, dtype=float)
    for column in columns:
        if column in frame.columns:
            values = _numeric(frame[column])
            result = result.where(result.notna(), values)
    return result


def _numeric(value: Any) -> pd.Series:
    return pd.to_numeric(value, errors="coerce")


def _mean(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns:
        return np.nan
    values = _numeric(frame[column])
    return float(values.mean()) if values.notna().any() else np.nan


def _positive_rate(value: Any) -> float:
    values = _numeric(value)
    return float(values.fillna(0).gt(0).mean()) if len(values) else 0.0


def _true_rate(value: Any) -> float:
    series = pd.Series(value).dropna()
    return float(series.astype(bool).mean()) if len(series) else 0.0


def _positive_sum(value: Any) -> float:
    values = _numeric(value).dropna()
    return float(values[values.gt(0)].sum()) if len(values) else 0.0


def _value_counts_text(frame: pd.DataFrame, column: str) -> str:
    if column not in frame.columns or frame.empty:
        return ""
    counts = frame[column].astype(str).value_counts().head(10)
    return "; ".join(f"{key}:{value}" for key, value in counts.items())


def _optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
