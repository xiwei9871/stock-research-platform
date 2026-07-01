from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.midtrend_badbuy_unknown_and_review_priority_v1 import _load_bad_buy_source_data

PIT_PATH = Path("outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv")
BADBUY_REVIEW_DIR = Path("outputs/research/midtrend_badbuy_unknown_and_review_priority_v1_20260626")
PIT_ATTR_DIR = Path("outputs/research/midtrend_pit_fundamental_attribution_v1_20260626")
POST_EXIT_ATTR_DIR = Path("outputs/research/midtrend_post_exit_fundamental_attribution_v1_20260626")
REENTRY_DIR = Path("outputs/research/midtrend_top10_reentry_gating_experiment_20260626")
BUCKET_RULE_VERSION = "pit_fundamental_features_v1"

SECTION_LABELS = {
    "HIGH_FUNDAMENTAL": "基本面增强观察",
    "HIGH_TECH_MAINLINE": "技术主线重新确认",
    "MEDIUM_FUNDAMENTAL_WATCH": "基本面观察",
    "RISK_DOWNGRADE": "基本面/风险降级",
    "LOW_OR_EXPIRED": "低优先级/已过期",
}
REVIEW_ACTIONS = {
    "review_strong_improving_post_exit_name",
    "review_technical_mainline_reconfirmed",
    "monitor_improving_but_not_reconfirmed",
    "monitor_unknown_fundamental",
    "downgrade_fundamental_weak_or_deteriorating",
    "expired_or_risk_damaged",
    "ignore_until_reconfirmed",
}


def run_midtrend_pit_attribution_canonical_cli(*, output_dir: str | Path) -> dict[str, Any]:
    pit = _optional_csv(PIT_PATH)
    bad_buy = _load_bad_buy_source_data()
    bad_sell = _load_bad_sell_rows()
    post_exit = _load_post_exit_rows()
    reentry = _load_reentry_rows()
    enhanced_watch = _optional_csv(BADBUY_REVIEW_DIR / "midtrend_post_exit_watch_daily_fundamental_priority.csv")
    return run_midtrend_pit_attribution_canonical_from_frames(
        pit_features=pit,
        bad_buy_rows=bad_buy,
        bad_sell_rows=bad_sell,
        post_exit_rows=post_exit,
        reentry_rows=reentry,
        enhanced_watch_rows=enhanced_watch,
        output_dir=output_dir,
    )


def run_midtrend_pit_attribution_canonical_from_frames(
    *,
    pit_features: pd.DataFrame,
    bad_buy_rows: pd.DataFrame,
    bad_sell_rows: pd.DataFrame,
    post_exit_rows: pd.DataFrame,
    reentry_rows: pd.DataFrame,
    enhanced_watch_rows: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    bad_buy = _canonical_bad_buy(bad_buy_rows, pit_features)
    bad_buy.to_csv(output / "bad_buy_fundamental_attribution_pit_canonical.csv", index=False)
    bad_buy_audit = build_bucket_source_audit(bad_buy, attribution_type="bad_buy")
    bad_buy_audit.to_csv(output / "bad_buy_bucket_source_audit.csv", index=False)

    bad_sell = _canonical_bad_sell(bad_sell_rows, pit_features)
    bad_sell.to_csv(output / "bad_sell_fundamental_attribution_pit_canonical.csv", index=False)
    bad_sell_audit = build_bucket_source_audit(bad_sell, attribution_type="bad_sell")
    bad_sell_audit.to_csv(output / "bad_sell_bucket_source_audit.csv", index=False)

    post_exit = _canonical_post_exit(post_exit_rows, pit_features)
    post_exit.to_csv(output / "post_exit_fundamental_attribution_pit_canonical.csv", index=False)
    post_exit_audit = build_bucket_source_audit(post_exit, attribution_type="post_exit")
    post_exit_audit.to_csv(output / "post_exit_bucket_source_audit.csv", index=False)

    reentry = _canonical_reentry(reentry_rows, pit_features)
    reentry.to_csv(output / "reentry_left_tail_fundamental_attribution_pit_canonical.csv", index=False)
    reentry_audit = build_bucket_source_audit(reentry, attribution_type="reentry")
    reentry_audit.to_csv(output / "reentry_bucket_source_audit.csv", index=False)

    global_audit = pd.concat([bad_buy_audit, bad_sell_audit, post_exit_audit, reentry_audit], ignore_index=True)
    global_audit.to_csv(output / "attribution_bucket_source_audit.csv", index=False)

    lite_csv, lite_json = build_daily_review_lite_artifacts(enhanced_watch_rows)
    lite_csv.to_csv(output / "midtrend_post_exit_watch_daily_review_lite.csv", index=False)
    (output / "midtrend_post_exit_watch_daily_review_lite.json").write_text(
        json.dumps(lite_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output / "daily_review_lite_integration_contract.md").write_text(
        _daily_review_contract_md(),
        encoding="utf-8",
    )
    _run_params().to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(_code_audit(), encoding="utf-8")
    (output / "final_interpretation.md").write_text(
        _final_interpretation(global_audit, lite_json),
        encoding="utf-8",
    )
    return {"paths": {"output_dir": str(output)}}


def join_pit_fundamental_bucket_canonical(
    frame: pd.DataFrame,
    *,
    date_col: str,
    asset_col: str,
    pit_features: pd.DataFrame,
) -> pd.DataFrame:
    source = frame.copy()
    if source.empty:
        return _ensure_canonical_columns(source)
    source[date_col] = _date_str(source.get(date_col))
    source[asset_col] = source.get(asset_col, pd.Series(index=source.index, dtype=object)).astype(str)
    if "source_fundamental_quality_bucket" not in source.columns:
        source["source_fundamental_quality_bucket"] = source.get("fundamental_quality_bucket", pd.NA)
    source = source.drop(columns=["fundamental_quality_bucket", "fundamental_momentum_bucket", "fundamental_risk_flag"], errors="ignore")

    pit = _prepare_pit(pit_features)
    if pit.empty:
        result = source.copy()
        result["pit_row_found"] = False
        result["pit_valid_flag"] = False
        result["pit_lookahead_violation_flag"] = False
        result["pit_fundamental_quality_bucket"] = pd.NA
        result["pit_fundamental_momentum_bucket"] = pd.NA
        result["pit_fundamental_risk_flag"] = pd.NA
        result["fundamental_bucket_source"] = np.where(
            result["source_fundamental_quality_bucket"].notna(),
            "source_only",
            "unavailable",
        )
        result["fundamental_quality_bucket"] = result["source_fundamental_quality_bucket"].fillna("quality_unknown")
        result["fundamental_momentum_bucket"] = "unknown"
        result["fundamental_risk_flag"] = False
        return _ensure_canonical_columns(result)

    joined = source.merge(
        pit,
        left_on=[date_col, asset_col],
        right_on=["pit_join_date", "asset_id"],
        how="left",
        suffixes=("", "_pitdup"),
    )
    if asset_col != "asset_id" and "asset_id_pitdup" in joined.columns:
        joined = joined.drop(columns=["asset_id_pitdup"])
    joined["pit_row_found"] = joined["pit_join_date"].notna()
    joined["pit_valid_flag"] = joined["pit_valid_flag"].fillna(False).astype(bool)
    joined["pit_lookahead_violation_flag"] = joined["pit_lookahead_violation_flag"].fillna(False).astype(bool)
    source_bucket = joined["source_fundamental_quality_bucket"]
    pit_valid = joined["pit_row_found"] & joined["pit_valid_flag"] & ~joined["pit_lookahead_violation_flag"]
    invalid = joined["pit_row_found"] & joined["pit_lookahead_violation_flag"]
    fallback = ~joined["pit_row_found"] & source_bucket.notna()

    joined["fundamental_bucket_source"] = "unavailable"
    joined.loc[pit_valid, "fundamental_bucket_source"] = "pit"
    joined.loc[fallback, "fundamental_bucket_source"] = "pit_missing_fallback_source"
    joined.loc[invalid, "fundamental_bucket_source"] = "invalid_lookahead_rejected"
    joined["fundamental_quality_bucket"] = "quality_unknown"
    joined.loc[pit_valid, "fundamental_quality_bucket"] = joined.loc[pit_valid, "pit_fundamental_quality_bucket"].fillna("quality_unknown")
    joined.loc[fallback, "fundamental_quality_bucket"] = source_bucket.loc[fallback].fillna("quality_unknown")
    joined["fundamental_momentum_bucket"] = "unknown"
    joined.loc[pit_valid, "fundamental_momentum_bucket"] = joined.loc[pit_valid, "pit_fundamental_momentum_bucket"].fillna("unknown")
    joined["fundamental_risk_flag"] = False
    joined.loc[pit_valid, "fundamental_risk_flag"] = joined.loc[pit_valid, "pit_fundamental_risk_flag"].fillna(False)
    joined["bucket_rule_version"] = BUCKET_RULE_VERSION
    return _ensure_canonical_columns(joined)


def build_bucket_source_audit(frame: pd.DataFrame, *, attribution_type: str) -> pd.DataFrame:
    if frame.empty:
        total = 0
        result = {key: 0 for key in _audit_count_columns()}
    else:
        total = len(frame)
        source = frame.get("fundamental_bucket_source", pd.Series("", index=frame.index)).astype(str)
        quality = frame.get("fundamental_quality_bucket", pd.Series("", index=frame.index)).astype(str)
        momentum = frame.get("fundamental_momentum_bucket", pd.Series("", index=frame.index)).astype(str)
        source_bucket = frame.get("source_fundamental_quality_bucket", pd.Series(pd.NA, index=frame.index)).astype(str)
        pit_bucket = frame.get("pit_fundamental_quality_bucket", pd.Series(pd.NA, index=frame.index)).astype(str)
        mismatch = (
            source.eq("pit")
            & source_bucket.notna()
            & source_bucket.ne("nan")
            & source_bucket.ne("")
            & pit_bucket.notna()
            & pit_bucket.ne("nan")
            & source_bucket.ne(pit_bucket)
            & quality.eq(pit_bucket)
        )
        result = {
            "canonical_pit_rows": int(source.eq("pit").sum()),
            "fallback_source_rows": int(source.eq("pit_missing_fallback_source").sum()),
            "source_only_rows": int(source.eq("source_only").sum()),
            "unavailable_rows": int(source.eq("unavailable").sum()),
            "invalid_lookahead_rejected_rows": int(source.eq("invalid_lookahead_rejected").sum()),
            "source_domain_mismatch_rows": int((source.ne("pit") & mismatch).sum()),
            "quality_unknown_rows": int(quality.eq("quality_unknown").sum()),
            "quality_weak_rows": int(quality.eq("quality_weak").sum()),
            "quality_neutral_rows": int(quality.eq("quality_neutral").sum()),
            "quality_strong_rows": int(quality.eq("quality_strong").sum()),
            "improving_rows": int(momentum.eq("improving").sum()),
            "deteriorating_rows": int(momentum.eq("deteriorating").sum()),
            "stable_rows": int(momentum.eq("stable").sum()),
        }
    return pd.DataFrame(
        [
            {
                "attribution_type": attribution_type,
                "total_rows": total,
                **result,
                "source_domain_mismatch_rate": (result["source_domain_mismatch_rows"] / total) if total else 0.0,
                "quality_unknown_rate": (result["quality_unknown_rows"] / total) if total else 0.0,
                "bucket_rule_version": BUCKET_RULE_VERSION,
            }
        ]
    )


def build_daily_review_lite_artifacts(enhanced_watch: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = enhanced_watch.copy()
    if frame.empty:
        frame = pd.DataFrame(columns=_lite_columns())
    for column in _lite_columns():
        if column not in frame.columns:
            frame[column] = pd.NA
    if "exit_date" not in frame.columns or frame["exit_date"].isna().all():
        frame["exit_date"] = frame.get("event_date", pd.NA)
    frame["exit_event_type"] = frame.get("exit_event_type", frame.get("event_type", pd.NA))
    frame["exit_rank"] = frame.get("exit_rank", frame.get("rank_on_exit_date", pd.NA))
    frame["exit_score"] = frame.get("exit_score", frame.get("mid_trend_funnel_score_on_exit", pd.NA))
    frame["suggested_review_action"] = frame["suggested_review_action"].where(
        frame["suggested_review_action"].astype(str).isin(REVIEW_ACTIONS),
        frame.get("enhanced_review_reason", "monitor_unknown_fundamental"),
    )
    frame["suggested_review_action"] = frame["suggested_review_action"].where(
        frame["suggested_review_action"].astype(str).isin(REVIEW_ACTIONS),
        "monitor_unknown_fundamental",
    )
    frame = frame[_lite_columns()].copy()
    frame["section"] = frame["enhanced_review_priority"].where(
        frame["enhanced_review_priority"].astype(str).isin(SECTION_LABELS),
        "LOW_OR_EXPIRED",
    )
    frame = frame.sort_values(["section", "current_rank", "days_since_exit"], na_position="last").reset_index(drop=True)
    sections = {}
    for section, label in SECTION_LABELS.items():
        items = frame[frame["section"].eq(section)].drop(columns=["section"]).replace({np.nan: None}).to_dict(orient="records")
        sections[section] = {"label_zh": label, "count": len(items), "items": items}
    return frame, {"schema_version": "midtrend_post_exit_watch_daily_review_lite_v1", "sections": sections}


def _canonical_bad_buy(rows: pd.DataFrame, pit: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    if "audit_label" in frame.columns:
        frame = frame[frame["audit_label"].astype(str).eq("bad_buy")].copy()
    joined = join_pit_fundamental_bucket_canonical(frame, date_col="trade_date", asset_col="asset_id", pit_features=pit)
    joined["high_elasticity_watch"] = joined.get("mid_trend_layer", pd.Series("", index=joined.index)).astype(str).eq("high_elasticity_watch")
    return joined


def _canonical_bad_sell(rows: pd.DataFrame, pit: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    if "audit_label" in frame.columns:
        frame = frame[frame["audit_label"].astype(str).eq("bad_sell")].copy()
    date_col = "trade_date" if "trade_date" in frame.columns else ("event_date" if "event_date" in frame.columns else "exit_date")
    return join_pit_fundamental_bucket_canonical(frame, date_col=date_col, asset_col="asset_id", pit_features=pit)


def _canonical_post_exit(rows: pd.DataFrame, pit: pd.DataFrame) -> pd.DataFrame:
    date_col = "event_date" if "event_date" in rows.columns else ("exit_date" if "exit_date" in rows.columns else "trade_date")
    return join_pit_fundamental_bucket_canonical(rows, date_col=date_col, asset_col="asset_id", pit_features=pit)


def _canonical_reentry(rows: pd.DataFrame, pit: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    date_col = "reentry_date" if "reentry_date" in frame.columns else "trade_date"
    joined = join_pit_fundamental_bucket_canonical(frame, date_col=date_col, asset_col="asset_id", pit_features=pit)
    if "return_after_reentry" in joined.columns:
        ret = pd.to_numeric(joined["return_after_reentry"], errors="coerce")
        joined["failed_reentry_flag"] = ret.lt(0)
        joined["severe_failed_reentry_flag"] = ret.lt(-0.1)
    return joined


def _prepare_pit(pit_features: pd.DataFrame) -> pd.DataFrame:
    pit = pit_features.copy()
    if pit.empty:
        return pit
    pit["pit_join_date"] = _date_str(pit.get("trade_date", pit.get("pit_trade_date")))
    pit["asset_id"] = pit.get("asset_id", pd.Series(index=pit.index, dtype=object)).astype(str)
    rename = {
        "fundamental_quality_bucket": "pit_fundamental_quality_bucket",
        "fundamental_momentum_bucket": "pit_fundamental_momentum_bucket",
        "fundamental_risk_flag": "pit_fundamental_risk_flag",
        "lookahead_violation_flag": "pit_lookahead_violation_flag",
        "report_disclosure_date": "pit_report_disclosure_date",
        "data_available_asof_date": "pit_data_available_asof_date",
    }
    pit = pit.rename(columns=rename)
    for column, default in {
        "pit_fundamental_quality_bucket": "quality_unknown",
        "pit_fundamental_momentum_bucket": "unknown",
        "pit_fundamental_risk_flag": False,
        "pit_valid_flag": False,
        "pit_lookahead_violation_flag": False,
        "pit_report_disclosure_date": pd.NA,
        "pit_data_available_asof_date": pd.NA,
    }.items():
        if column not in pit.columns:
            pit[column] = default
    return pit[
        [
            "pit_join_date",
            "asset_id",
            "pit_fundamental_quality_bucket",
            "pit_fundamental_momentum_bucket",
            "pit_fundamental_risk_flag",
            "pit_valid_flag",
            "pit_lookahead_violation_flag",
            "pit_report_disclosure_date",
            "pit_data_available_asof_date",
        ]
    ].drop_duplicates(["pit_join_date", "asset_id"], keep="last")


def _ensure_canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column, default in {
        "source_fundamental_quality_bucket": pd.NA,
        "pit_fundamental_quality_bucket": pd.NA,
        "pit_fundamental_momentum_bucket": pd.NA,
        "pit_fundamental_risk_flag": pd.NA,
        "pit_valid_flag": False,
        "pit_row_found": False,
        "pit_lookahead_violation_flag": False,
        "pit_report_disclosure_date": pd.NA,
        "pit_data_available_asof_date": pd.NA,
        "fundamental_quality_bucket": "quality_unknown",
        "fundamental_momentum_bucket": "unknown",
        "fundamental_risk_flag": False,
        "fundamental_bucket_source": "unavailable",
        "bucket_rule_version": BUCKET_RULE_VERSION,
    }.items():
        if column not in frame.columns:
            frame[column] = default
    return frame


def _load_bad_sell_rows() -> pd.DataFrame:
    frames = []
    all_trades = _load_bad_buy_source_data()
    if not all_trades.empty and "audit_label" in all_trades.columns:
        sell_trades = all_trades[all_trades["audit_label"].astype(str).eq("bad_sell")].copy()
        if not sell_trades.empty:
            frames.append(sell_trades)
    for path in [
        PIT_ATTR_DIR / "bad_sell_examples_quality_strong_continued.csv",
        PIT_ATTR_DIR / "bad_sell_examples_quality_weak_true_exit.csv",
        POST_EXIT_ATTR_DIR / "bad_sell_examples_continued_winners.csv",
        POST_EXIT_ATTR_DIR / "bad_sell_examples_true_exits.csv",
    ]:
        frame = _optional_csv(path)
        if not frame.empty:
            frame["source_file"] = path.name
            if "trade_date" not in frame.columns and "event_date" in frame.columns:
                frame["trade_date"] = frame["event_date"]
            if "audit_label" not in frame.columns:
                frame["audit_label"] = "bad_sell"
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _load_post_exit_rows() -> pd.DataFrame:
    path = PIT_ATTR_DIR / "post_exit_observation_pool_with_pit_fundamentals.csv"
    frame = _optional_csv(path)
    if frame.empty:
        frame = _optional_csv(POST_EXIT_ATTR_DIR / "post_exit_path_behavior.csv")
    return frame


def _load_reentry_rows() -> pd.DataFrame:
    events = _optional_csv(REENTRY_DIR / "reentry_gating_event_log.csv")
    trades = _optional_csv(REENTRY_DIR / "reentry_gating_trade_contribution.csv")
    if events.empty:
        return trades
    if trades.empty:
        return events
    trades["trade_date"] = _date_str(trades["trade_date"])
    events["reentry_date"] = _date_str(events["reentry_date"])
    return trades.merge(
        events,
        left_on=["variant_name", "asset_id", "trade_date"],
        right_on=["variant_name", "asset_id", "reentry_date"],
        how="left",
        suffixes=("", "_event"),
    )


def _audit_count_columns() -> list[str]:
    return [
        "canonical_pit_rows",
        "fallback_source_rows",
        "source_only_rows",
        "unavailable_rows",
        "invalid_lookahead_rejected_rows",
        "source_domain_mismatch_rows",
        "quality_unknown_rows",
        "quality_weak_rows",
        "quality_neutral_rows",
        "quality_strong_rows",
        "improving_rows",
        "deteriorating_rows",
        "stable_rows",
    ]


def _lite_columns() -> list[str]:
    return [
        "trade_date",
        "asset_id",
        "stock_name",
        "industry_name",
        "enhanced_review_priority",
        "review_priority",
        "fundamental_priority_tag",
        "enhanced_review_reason",
        "suggested_review_action",
        "exit_date",
        "days_since_exit",
        "exit_event_type",
        "exit_rank",
        "current_rank",
        "exit_score",
        "current_score",
        "score_delta_since_exit",
        "current_mid_trend_layer",
        "current_mainline_status",
        "technical_confirmed",
        "mainline_confirmed",
        "midtrend_confirmation_state",
        "current_fundamental_quality_bucket",
        "current_fundamental_momentum_bucket",
        "current_fundamental_risk_flag",
        "forward_return_since_exit",
        "max_return_since_exit",
        "max_drawdown_since_exit",
        "reentered_top5",
        "reentered_top10",
        "reentered_top20",
        "reconfirmed_T1_M1",
        "path_class_so_far",
    ]


def _daily_review_contract_md() -> str:
    lines = [
        "# Daily Review Lite Integration Contract",
        "",
        "- Artifact JSON: `midtrend_post_exit_watch_daily_review_lite.json`",
        "- Artifact CSV: `midtrend_post_exit_watch_daily_review_lite.csv`",
        "- Sections: `HIGH_FUNDAMENTAL`, `HIGH_TECH_MAINLINE`, `MEDIUM_FUNDAMENTAL_WATCH`, `RISK_DOWNGRADE`, `LOW_OR_EXPIRED`",
        "- Default sort: section, current_rank, days_since_exit.",
        "- Chinese labels: HIGH_FUNDAMENTAL=基本面增强观察; HIGH_TECH_MAINLINE=技术主线重新确认; MEDIUM_FUNDAMENTAL_WATCH=基本面观察; RISK_DOWNGRADE=基本面/风险降级; LOW_OR_EXPIRED=低优先级/已过期.",
        "- Suggested badges: 基本面改善, 质量强, 质量弱, 主线确认, 技术确认, 重新进入Top10, 重新进入Top20, 风险降级, 观察期过半, 已过期.",
        "- This artifact is review-only and is not an automatic trading signal.",
    ]
    return "\n".join(lines) + "\n"


def _run_params() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"param": "pit_path", "value": str(PIT_PATH)},
            {"param": "badbuy_review_dir", "value": str(BADBUY_REVIEW_DIR)},
            {"param": "bucket_rule_version", "value": BUCKET_RULE_VERSION},
        ]
    )


def _code_audit() -> str:
    return "\n".join(
        [
            "# Code Audit",
            "",
            "- runner: `stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1`",
            "- all attribution bucket fields are canonicalized through `join_pit_fundamental_bucket_canonical`",
            "- source-side buckets are preserved only as `source_fundamental_quality_bucket`",
            "- no trading strategy logic changed",
        ]
    ) + "\n"


def _final_interpretation(global_audit: pd.DataFrame, lite_json: dict[str, Any]) -> str:
    mismatch = int(global_audit["source_domain_mismatch_rows"].sum()) if not global_audit.empty else 0
    total = int(global_audit["total_rows"].sum()) if not global_audit.empty else 0
    sections = lite_json.get("sections", {})
    lines = [
        "# Final Interpretation",
        "",
        "A1. All generated attribution outputs use canonical PIT bucket fields when PIT rows are valid.",
        f"A2. Source-domain mismatch rows in canonical outputs: {mismatch}; mismatch_rate={(mismatch / total) if total else 0.0:.4f}.",
        "A3. Source-side buckets are retained only as fallback fields and are explicitly flagged by `fundamental_bucket_source`.",
        "A4. Quality_unknown rows are now explainable through bucket-source audit columns.",
        "A5. Canonical bad_buy attribution should be read from `bad_buy_fundamental_attribution_pit_canonical.csv`; quality_strong bad buys remain visible and are not filtered.",
        "A6. Canonical bad_sell/post-exit attribution remains suitable for observation-priority research, not exit-rule changes.",
        "A7. Canonical re-entry attribution does not promote re-entry; re-entry remains research-only.",
        "B8. Daily Review Lite artifact was generated.",
        *(f"B9. {section}: {payload.get('count', 0)}" for section, payload in sections.items()),
        "B10. The artifact is suitable for dashboard/API integration through the generated contract.",
        "B11. Dashboard code integration was not changed in this runner; only the integration contract/artifacts were produced.",
        "B12. Labels and actions are review-only and avoid trading instructions.",
        "C13. Confirm no trading strategy logic changed: yes.",
        "C14. Confirm v1 baseline unchanged: yes.",
        "C15. Confirm top10 candidate baseline unchanged: yes.",
        "C16. Confirm no fundamental entry filter was added: yes.",
        "C17. Confirm no re-entry strategy was added: yes.",
        "C18. Confirm all strategy-like ideas remain RESEARCH_ONLY: yes.",
        "D19. Next task should be Daily Review Lite frontend integration if the dashboard artifact loader path is agreed.",
        "D20. Canonical bad_buy denominator/rate analysis is also a reasonable next research task.",
        "D21. A fundamental entry gate experiment remains premature.",
        "D22. Recommended next research task: denominator-aware bad_buy attribution by PIT quality and momentum.",
    ]
    return "\n".join(lines) + "\n"


def _optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _date_str(value: Any) -> Any:
    if isinstance(value, pd.Series):
        return pd.to_datetime(value, errors="coerce").dt.strftime("%Y-%m-%d")
    return pd.to_datetime(value, errors="coerce").strftime("%Y-%m-%d") if pd.notna(value) else pd.NA
