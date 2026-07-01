#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_v1 import (
    TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH,
    _extend_market_exposure,
    _load_prices,
    build_tech_bottleneck_v1_from_rank_snapshots,
)


DEFAULT_REPLAY_DIR = Path(
    "outputs/research/tech_bottleneck_pit_evidence_replay_neutral_missing_v1_20250101_20260629"
)
VARIANTS = [
    "baseline_technical_only",
    "tag_only",
    "tie_breaker_1pct",
    "tie_breaker_3pct",
    "tie_breaker_5pct",
    "rank_jump_cap_1",
    "rank_jump_cap_2",
    "weak_multiplier_1p01_1p03",
    "weak_multiplier_1p02_1p05",
]


def evidence_priority_from_count(count: Any) -> int:
    parsed = pd.to_numeric(pd.Series([count]), errors="coerce").fillna(0).iloc[0]
    if parsed >= 3:
        return 3
    if parsed == 2:
        return 2
    if parsed == 1:
        return 1
    return 0


def evidence_state_from_count(count: Any) -> str:
    priority = evidence_priority_from_count(count)
    if priority == 3:
        return "E3_strong"
    if priority == 2:
        return "E2_valid"
    if priority == 1:
        return "E1_weak"
    return "unverified"


def _prepare_candidates(base: pd.DataFrame) -> pd.DataFrame:
    frame = base.copy()
    if "raw_bottleneck_score" in frame.columns:
        frame["raw_technical_score"] = pd.to_numeric(frame["raw_bottleneck_score"], errors="coerce")
    else:
        frame["raw_technical_score"] = pd.to_numeric(frame["bottleneck_score"], errors="coerce")
    frame["rank_before_evidence"] = pd.to_numeric(frame["bottleneck_rank"], errors="coerce").astype(int)
    frame["source_backed_field_count"] = pd.to_numeric(
        frame.get("source_backed_field_count", 0), errors="coerce"
    ).fillna(0).astype(int)
    frame["evidence_priority"] = frame["source_backed_field_count"].map(evidence_priority_from_count)
    frame["evidence_state"] = frame["source_backed_field_count"].map(evidence_state_from_count)
    frame["evidence_tag"] = frame["evidence_state"]
    return frame


def _assign_ranks(frame: pd.DataFrame, *, score_col: str, sort_cols: list[str] | None = None) -> pd.DataFrame:
    result = frame.copy()
    columns = ["trade_date", score_col]
    ascending = [True, False]
    if sort_cols:
        columns.extend(sort_cols)
        ascending.extend([False if col == "evidence_priority" else True for col in sort_cols])
    columns.append("asset_id")
    ascending.append(True)
    result = result.sort_values(columns, ascending=ascending).reset_index(drop=True)
    result["bottleneck_rank"] = result.groupby("trade_date").cumcount() + 1
    result["is_top5"] = result["bottleneck_rank"] <= 5
    result["bottleneck_score"] = result[score_col]
    return result


def _tie_breaker_day(day: pd.DataFrame, threshold: float) -> pd.DataFrame:
    ordered = day.sort_values(["raw_technical_score", "asset_id"], ascending=[False, True]).reset_index(drop=True)
    clusters: list[pd.DataFrame] = []
    current: list[int] = []
    cluster_top = None
    for idx, row in ordered.iterrows():
        score = float(row["raw_technical_score"])
        if cluster_top is None:
            cluster_top = score
            current = [idx]
            continue
        gap = abs(cluster_top - score) / max(abs(cluster_top), 1e-12)
        if gap <= threshold:
            current.append(idx)
        else:
            cluster = ordered.loc[current].sort_values(
                ["evidence_priority", "raw_technical_score", "asset_id"],
                ascending=[False, False, True],
            )
            clusters.append(cluster)
            cluster_top = score
            current = [idx]
    if current:
        clusters.append(
            ordered.loc[current].sort_values(
                ["evidence_priority", "raw_technical_score", "asset_id"],
                ascending=[False, False, True],
            )
        )
    return pd.concat(clusters, ignore_index=True)


def _apply_tie_breaker(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    rows = [_tie_breaker_day(day, threshold) for _, day in frame.groupby("trade_date", sort=True)]
    result = pd.concat(rows, ignore_index=True)
    result["bottleneck_rank"] = result.groupby("trade_date").cumcount() + 1
    result["is_top5"] = result["bottleneck_rank"] <= 5
    result["bottleneck_score"] = result["raw_technical_score"]
    result["evidence_confidence_multiplier"] = 1.0
    return result


def _apply_rank_jump_cap(frame: pd.DataFrame, cap: int) -> pd.DataFrame:
    boosted = frame.copy()
    boosted["boosted_score"] = boosted["raw_technical_score"] * boosted["source_backed_field_count"].map(
        lambda count: 1.15 if count >= 3 else 1.05 if count == 2 else 1.0
    )
    days: list[pd.DataFrame] = []
    for _, day in boosted.groupby("trade_date", sort=True):
        remaining = day.sort_values(["boosted_score", "raw_technical_score", "asset_id"], ascending=[False, False, True]).copy()
        chosen: list[pd.Series] = []
        slot = 1
        while not remaining.empty:
            eligible = remaining[remaining["rank_before_evidence"].astype(int) - int(cap) <= slot]
            if eligible.empty:
                selected_index = remaining["rank_before_evidence"].astype(int).idxmin()
            else:
                selected_index = eligible.index[0]
            selected = remaining.loc[selected_index]
            chosen.append(selected)
            remaining = remaining.drop(index=selected_index)
            slot += 1
        days.append(pd.DataFrame(chosen))
    result = pd.concat(days, ignore_index=True)
    result["bottleneck_rank"] = result.groupby("trade_date").cumcount() + 1
    result["is_top5"] = result["bottleneck_rank"] <= 5
    result["bottleneck_score"] = result["raw_technical_score"]
    result["evidence_confidence_multiplier"] = 1.0
    return result


def _apply_weak_multiplier(frame: pd.DataFrame, *, e2: float, e3: float) -> pd.DataFrame:
    result = frame.copy()
    result["evidence_confidence_multiplier"] = result["source_backed_field_count"].map(
        lambda count: e3 if count >= 3 else e2 if count == 2 else 1.0
    )
    result["weak_adjusted_score"] = result["raw_technical_score"] * result["evidence_confidence_multiplier"]
    return _assign_ranks(result, score_col="weak_adjusted_score")


def apply_evidence_usage_variant(candidates: pd.DataFrame, variant: str) -> pd.DataFrame:
    frame = _prepare_candidates(candidates)
    frame["evidence_usage_variant"] = variant
    frame["evidence_confidence_multiplier"] = 1.0
    if variant in {"baseline_technical_only", "tag_only"}:
        result = _assign_ranks(frame, score_col="raw_technical_score")
    elif variant == "tie_breaker_1pct":
        result = _apply_tie_breaker(frame, 0.01)
    elif variant == "tie_breaker_3pct":
        result = _apply_tie_breaker(frame, 0.03)
    elif variant == "tie_breaker_5pct":
        result = _apply_tie_breaker(frame, 0.05)
    elif variant == "rank_jump_cap_1":
        result = _apply_rank_jump_cap(frame, 1)
    elif variant == "rank_jump_cap_2":
        result = _apply_rank_jump_cap(frame, 2)
    elif variant == "weak_multiplier_1p01_1p03":
        result = _apply_weak_multiplier(frame, e2=1.01, e3=1.03)
    elif variant == "weak_multiplier_1p02_1p05":
        result = _apply_weak_multiplier(frame, e2=1.02, e3=1.05)
    else:
        raise ValueError(f"unknown variant: {variant}")
    result["evidence_usage_variant"] = variant
    result["rank_jump"] = result["rank_before_evidence"] - result["bottleneck_rank"]
    result["is_top5"] = result["bottleneck_rank"] <= 5
    result["ablation_selection_score"] = result.groupby("trade_date")["bottleneck_rank"].transform(
        lambda ranks: len(ranks) + 1 - ranks.astype(float)
    )
    result["bottleneck_score"] = result["ablation_selection_score"]
    return result[_snapshot_columns(result)]


def _snapshot_columns(frame: pd.DataFrame) -> list[str]:
    required = [
        "trade_date",
        "asset_id",
        "stock_name",
        "first_hit_date",
        "candidate_as_of_date",
        "hit_count_as_of_date",
        "primary_chain_id",
        "primary_chain_name",
        "matched_bottleneck_dimensions",
        "financial_as_of_date",
        "technical_as_of_date",
        "data_as_of_date",
        "filter_decision",
        "filter_reason",
        "bottleneck_score",
        "bottleneck_rank",
        "is_top5",
        "engine_version",
        "run_id",
    ]
    extras = [
        "raw_technical_score",
        "rank_before_evidence",
        "rank_jump",
        "source_backed_field_count",
        "evidence_priority",
        "evidence_state",
        "evidence_tag",
        "evidence_confidence_multiplier",
        "evidence_usage_variant",
        "ablation_selection_score",
    ]
    return [col for col in required + extras if col in frame.columns]


def _load_replay_context(replay_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    base = pd.read_csv(replay_dir / "official_baseline_daily_candidate_snapshots.csv", low_memory=False)
    pit = pd.read_csv(replay_dir / "pit_daily_evidence_multiplier.csv", low_memory=False)
    evidence_cols = [
        col
        for col in [
            "trade_date",
            "asset_id",
            "source_backed_field_count",
            "evidence_confidence_multiplier",
            "evidence_state",
            "evidence_audit_status",
            "evidence_coverage_ratio",
            "latest_evidence_date",
            "bucket_rule_version",
        ]
        if col in pit.columns
    ]
    base = base.merge(pit[evidence_cols], on=["trade_date", "asset_id"], how="left")
    comparison = pd.read_csv(replay_dir / "baseline_vs_pit_evidence_replay.csv", low_memory=False)
    start_date = str(comparison["actual_replay_start_date"].dropna().iloc[0])
    end_date = str(comparison["end_date"].dropna().iloc[0])
    return base, comparison, start_date, end_date


def _load_prices_for_candidates(candidates: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    asset_ids = sorted(candidates["asset_id"].dropna().astype(str).unique().tolist())
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type="hfq",
        asset_ids=asset_ids,
        service=SETTINGS.research_service,
    )
    for column in ["open", "high", "low", "close"]:
        if column in prices.columns:
            prices[column] = pd.to_numeric(prices[column], errors="coerce")
    return prices


def _run_strategy_variant(
    *,
    variant: str,
    snapshots: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    replay_dir: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    strategy = build_tech_bottleneck_v1_from_rank_snapshots(
        candidate_snapshots=snapshots[
            [
                "trade_date",
                "asset_id",
                "stock_name",
                "first_hit_date",
                "candidate_as_of_date",
                "hit_count_as_of_date",
                "primary_chain_id",
                "primary_chain_name",
                "matched_bottleneck_dimensions",
                "financial_as_of_date",
                "technical_as_of_date",
                "data_as_of_date",
                "filter_decision",
                "filter_reason",
                "bottleneck_score",
                "bottleneck_rank",
                "is_top5",
                "engine_version",
                "run_id",
            ]
        ],
        prices=prices,
        market_exposure=market_exposure,
        start_date=start_date,
        end_date=end_date,
        top_n=5,
        rebalance_frequency="biweekly",
        transaction_cost_bps=20.0,
        max_position_weight=0.2,
        adjust_type="hfq",
    )
    directory = replay_dir / f"ablation_{variant}"
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(strategy["equity_curve"]).to_csv(directory / "strategy_tech_bottleneck_equity.csv", index=False)
    pd.DataFrame(strategy["positions"]).to_csv(directory / "strategy_tech_bottleneck_positions.csv", index=False)
    pd.DataFrame(strategy["trades"]).to_csv(directory / "strategy_tech_bottleneck_trades.csv", index=False)
    pd.DataFrame([strategy["summary"]]).to_csv(directory / "summary.csv", index=False)
    row = dict(strategy["summary"])
    row["variant"] = variant
    row["trade_rows"] = len(strategy["trades"])
    row["position_rows"] = len(strategy["positions"])
    return row


def _top5_sets(frame: pd.DataFrame) -> pd.Series:
    return (
        frame[frame["bottleneck_rank"].le(5)]
        .groupby("trade_date")["asset_id"]
        .apply(lambda values: "|".join(sorted(values.astype(str))))
    )


def _daily_top5_changes(baseline: pd.DataFrame, variant_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base_sets = _top5_sets(baseline).rename("baseline_top5")
    rows: list[dict[str, Any]] = []
    for variant, frame in variant_frames.items():
        sets = _top5_sets(frame).rename("variant_top5")
        merged = pd.concat([base_sets, sets], axis=1).reset_index()
        merged["variant"] = variant
        merged["top5_changed_vs_baseline"] = merged["baseline_top5"] != merged["variant_top5"]
        for row in merged.itertuples(index=False):
            base = set(str(row.baseline_top5).split("|")) if pd.notna(row.baseline_top5) else set()
            var = set(str(row.variant_top5).split("|")) if pd.notna(row.variant_top5) else set()
            rows.append(
                {
                    "trade_date": row.trade_date,
                    "variant": variant,
                    "baseline_top5": row.baseline_top5,
                    "variant_top5": row.variant_top5,
                    "top5_changed_vs_baseline": bool(row.top5_changed_vs_baseline),
                    "entered_assets": "|".join(sorted(var - base)),
                    "dropped_assets": "|".join(sorted(base - var)),
                    "entered_count": len(var - base),
                    "dropped_count": len(base - var),
                }
            )
    return pd.DataFrame(rows)


def _position_contribution_delta(replay_dir: Path, variant: str, prices: pd.DataFrame) -> pd.DataFrame:
    close = prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    next_return = close.shift(-1) / close - 1.0

    def contribution(path: Path, prefix: str) -> pd.DataFrame:
        positions = pd.read_csv(path)
        rows: list[dict[str, Any]] = []
        for row in positions.itertuples(index=False):
            trade_date = str(row.trade_date)
            asset_id = str(row.asset_id)
            ret = next_return.at[trade_date, asset_id] if trade_date in next_return.index and asset_id in next_return.columns else pd.NA
            weight = float(row.weight)
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    f"{prefix}_weight": weight,
                    f"{prefix}_contribution": weight * float(ret) if pd.notna(ret) else 0.0,
                }
            )
        return pd.DataFrame(rows)

    baseline = contribution(replay_dir / "ablation_baseline_technical_only" / "strategy_tech_bottleneck_positions.csv", "baseline")
    other = contribution(replay_dir / f"ablation_{variant}" / "strategy_tech_bottleneck_positions.csv", "variant")
    frame = baseline.merge(other, on=["trade_date", "asset_id"], how="outer").fillna(0.0)
    frame["variant"] = variant
    frame["weight_delta_vs_baseline"] = frame["variant_weight"] - frame["baseline_weight"]
    frame["contribution_delta_vs_baseline"] = frame["variant_contribution"] - frame["baseline_contribution"]
    return frame


def _forward_return(close: pd.DataFrame, asset_id: str, trade_date: str, horizon: int) -> float | pd.NA:
    if not asset_id or asset_id not in close.columns or trade_date not in close.index:
        return pd.NA
    dates = close.index.tolist()
    idx = dates.index(trade_date)
    if idx + horizon >= len(dates):
        return pd.NA
    start = close.at[trade_date, asset_id]
    end = close.iloc[idx + horizon][asset_id]
    if pd.isna(start) or pd.isna(end) or float(start) == 0.0:
        return pd.NA
    return float(end) / float(start) - 1.0


def _stock_events(replay_dir: Path) -> pd.DataFrame:
    events = pd.read_csv(replay_dir / "new_evidence_seed_pit_usable.csv", low_memory=False).copy()
    events["source_date"] = pd.to_datetime(events["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    source_key = events["source_path"].fillna(events["source_type"]).astype(str)
    events["stock_event_id"] = events["asset_id"].astype(str) + "|" + events["source_date"].astype(str) + "|" + source_key
    grouped = (
        events.groupby(["stock_event_id", "asset_id", "source_date", "source_type"], dropna=False)
        .agg(
            field_count=("field", "nunique"),
            field_keys=("field", lambda values: "|".join(sorted(set(values.astype(str))))),
            source_paths=("source_path", lambda values: "|".join(sorted(set(values.dropna().astype(str))))),
        )
        .reset_index()
    )
    grouped["evidence_state"] = grouped["field_count"].map(evidence_state_from_count)
    grouped["evidence_priority"] = grouped["field_count"].map(evidence_priority_from_count)
    return grouped


def _stock_event_attribution(
    *,
    stock_events: pd.DataFrame,
    variant_frames: dict[str, pd.DataFrame],
    daily_changes: pd.DataFrame,
    trade_delta: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    close = prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    rows: list[dict[str, Any]] = []
    for event in stock_events.itertuples(index=False):
        base: dict[str, Any] = {
            "stock_event_id": event.stock_event_id,
            "asset_id": event.asset_id,
            "symbol": str(event.asset_id).split(":")[-1],
            "name": _stock_name_for_asset(variant_frames["baseline_technical_only"], str(event.asset_id)),
            "evidence_date": event.source_date,
            "source_type": event.source_type,
            "field_count": event.field_count,
            "field_keys": event.field_keys,
            "first_effective_trade_date": event.source_date,
            "evidence_state": event.evidence_state,
            "evidence_priority": event.evidence_priority,
        }
        for variant, frame in variant_frames.items():
            day_rows = frame[
                frame["asset_id"].astype(str).eq(str(event.asset_id))
                & frame["trade_date"].astype(str).ge(str(event.source_date))
            ]
            entered_days = int(
                (
                    day_rows["bottleneck_rank"].le(5)
                    & day_rows["rank_before_evidence"].gt(5)
                ).sum()
            ) if not day_rows.empty else 0
            top5_days = int(day_rows["bottleneck_rank"].le(5).sum()) if not day_rows.empty else 0
            base[f"top5_impact_days_{variant}"] = top5_days
            base[f"entered_top5_days_{variant}"] = entered_days
            base[f"avg_rank_after_{variant}"] = float(day_rows["bottleneck_rank"].mean()) if not day_rows.empty else pd.NA
            deltas = trade_delta[
                trade_delta["variant"].eq(variant)
                & trade_delta["asset_id"].astype(str).eq(str(event.asset_id))
                & trade_delta["trade_date"].astype(str).ge(str(event.source_date))
            ]
            realized = float(deltas["contribution_delta_vs_baseline"].sum()) if not deltas.empty else 0.0
            base[f"realized_trade_return_delta_{variant}"] = realized
            first_entry = day_rows[
                day_rows["bottleneck_rank"].le(5) & day_rows["rank_before_evidence"].gt(5)
            ].sort_values("trade_date").head(1)
            first_date = str(first_entry.iloc[0]["trade_date"]) if not first_entry.empty else str(event.source_date)
            for horizon in [5, 10, 20]:
                base[f"forward_{horizon}d_delta_{variant}"] = _forward_return(
                    close, str(event.asset_id), first_date, horizon
                )
            base[f"attribution_label_{variant}"] = (
                "beneficial" if realized > 0.002 else "harmful" if realized < -0.002 else "neutral"
            )
        base["avg_rank_before"] = float(
            variant_frames["baseline_technical_only"][
                variant_frames["baseline_technical_only"]["asset_id"].astype(str).eq(str(event.asset_id))
                & variant_frames["baseline_technical_only"]["trade_date"].astype(str).ge(str(event.source_date))
            ]["rank_before_evidence"].mean()
        )
        rows.append(base)
    return pd.DataFrame(rows)


def _stock_name_for_asset(frame: pd.DataFrame, asset_id: str) -> str:
    rows = frame[frame["asset_id"].astype(str).eq(str(asset_id))]
    if rows.empty:
        return ""
    return str(rows.iloc[0].get("stock_name", ""))


def _summary_metrics(
    *,
    rows: list[dict[str, Any]],
    variant_frames: dict[str, pd.DataFrame],
    daily_changes: pd.DataFrame,
    trade_delta: pd.DataFrame,
) -> pd.DataFrame:
    summary = pd.DataFrame(rows)
    baseline_return = float(summary.loc[summary["variant"].eq("baseline_technical_only"), "total_return"].iloc[0])
    extra_rows: list[dict[str, Any]] = []
    for row in summary.to_dict("records"):
        variant = row["variant"]
        frame = variant_frames[variant]
        changes = daily_changes[daily_changes["variant"].eq(variant)]
        deltas = trade_delta[trade_delta["variant"].eq(variant)] if not trade_delta.empty else pd.DataFrame()
        changed = changes[changes["top5_changed_vs_baseline"]]
        extra = dict(row)
        extra["realized_return_delta_vs_baseline"] = float(row.get("total_return", 0.0)) - baseline_return
        extra["top5_changed_days_vs_baseline"] = int(changed["trade_date"].nunique())
        extra["entered_top5_stock_count"] = len(set("|".join(changed["entered_assets"].fillna("").astype(str)).split("|")) - {""})
        extra["dropped_top5_stock_count"] = len(set("|".join(changed["dropped_assets"].fillna("").astype(str)).split("|")) - {""})
        affected = frame[frame["rank_jump"].fillna(0).ne(0)]
        extra["avg_rank_jump"] = float(affected["rank_jump"].mean()) if not affected.empty else 0.0
        extra["max_rank_jump"] = float(affected["rank_jump"].max()) if not affected.empty else 0.0
        extra["evidence_affected_trade_count"] = int(
            deltas[deltas["weight_delta_vs_baseline"].abs().gt(1e-12)][["trade_date", "asset_id"]].drop_duplicates().shape[0]
        ) if not deltas.empty else 0
        extra["forward_5d_delta_mean"] = pd.NA
        extra["forward_10d_delta_mean"] = pd.NA
        extra["forward_20d_delta_mean"] = pd.NA
        extra_rows.append(extra)
    return pd.DataFrame(extra_rows)


def _format_number(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.4f}"


def _write_report(
    *,
    replay_dir: Path,
    summary: pd.DataFrame,
    stock_attr: pd.DataFrame,
    daily_changes: pd.DataFrame,
) -> None:
    report_summary = summary.copy()
    for col in ["total_return", "max_drawdown", "sharpe", "sharpe_ratio", "realized_return_delta_vs_baseline", "avg_rank_jump", "max_rank_jump"]:
        if col in report_summary.columns:
            report_summary[col] = report_summary[col].map(_format_number)
    perf_cols = [
        "variant",
        "total_return",
        "max_drawdown",
        "sharpe_ratio",
        "trade_rows",
        "turnover_avg",
        "top5_changed_days_vs_baseline",
        "entered_top5_stock_count",
        "dropped_top5_stock_count",
        "avg_rank_jump",
        "max_rank_jump",
        "evidence_affected_trade_count",
        "realized_return_delta_vs_baseline",
    ]
    perf_cols = [col for col in perf_cols if col in report_summary.columns]
    top = summary.sort_values(["total_return", "top5_changed_days_vs_baseline"], ascending=[False, True]).head(3)
    best_variant = str(top.iloc[0]["variant"])
    stock_focus_cols = [
        "stock_event_id",
        "name",
        "evidence_date",
        "field_count",
        "field_keys",
    ]
    for variant in ["tie_breaker_1pct", "rank_jump_cap_1", "weak_multiplier_1p01_1p03", "weak_multiplier_1p02_1p05"]:
        for col in [f"entered_top5_days_{variant}", f"realized_trade_return_delta_{variant}", f"attribution_label_{variant}"]:
            if col in stock_attr.columns:
                stock_focus_cols.append(col)
    stock_report = stock_attr.copy()
    for col in stock_report.columns:
        if col.startswith("realized_trade_return_delta_"):
            stock_report[col] = stock_report[col].map(_format_number)
    changed_counts = daily_changes.groupby("variant")["top5_changed_vs_baseline"].sum().reset_index()
    lines = [
        "# Tech Bottleneck Evidence Usage Ablation v1",
        "",
        "## 1. Executive Summary",
        "",
        f"- 测试 variants：`{', '.join(VARIANTS)}`。",
        f"- 按 total_return 排序的最高 variant 是 `{best_variant}`；但本报告不建议据此接入正式交易。",
        "- `tag_only` 等价 baseline，适合作为 dashboard/review priority 的安全用法。",
        "- tie-breaker 和 rank jump cap 能明显降低 Top5 扰动，但样本仍过少，不能证明稳定 alpha。",
        "- weak multiplier 比旧强 multiplier 安全，但仍可能让少量 stock-event 放大排名影响。",
        "- 当前继续建议禁用 evidence multiplier；如要使用，优先考虑 tag/review/tie-breaker，而不是乘主分。",
        "",
        "## 2. Context",
        "",
        f"- Replay directory: `{replay_dir}`",
        "- PIT evidence rule base: `neutral_missing_v1`",
        "- 上一轮结论：12 条 field-level evidence 中，只有 2 个股票级事件真正推入 Top5，且强 multiplier 造成 109 天 Top5 扰动。",
        "",
        "## 3. Variant Definitions",
        "",
        "- `baseline_technical_only`: 完全按原始 bottleneck technical score 排序。",
        "- `tag_only`: 只输出 evidence tag/priority，不改变排序。",
        "- `tie_breaker_1pct/3pct/5pct`: 只有技术分差在阈值内时，evidence_priority 高者优先。",
        "- `rank_jump_cap_1/2`: 先按强 evidence boost 形成倾向，再限制单只股票最多提升 1/2 名。",
        "- `weak_multiplier_1p01_1p03`: E2=1.01，E3=1.03，E0/E1=1.00。",
        "- `weak_multiplier_1p02_1p05`: E2=1.02，E3=1.05，E0/E1=1.00。",
        "",
        "## 4. Performance Comparison",
        "",
        report_summary[perf_cols].to_markdown(index=False),
        "",
        "## 5. Top5 Stability Comparison",
        "",
        changed_counts.to_markdown(index=False),
        "",
        "## 6. Stock-Event Attribution",
        "",
        stock_report[stock_focus_cols].to_markdown(index=False),
        "",
        "## 7. Harmful Case Suppression",
        "",
        "普利特 stock-event 是上一轮 harmful case。轻量规则的关键是减少它长时间被 evidence 推入 Top5。若 `entered_top5_days_*` 下降到 0 或显著低于强 multiplier 版本，说明规则有效抑制了 harmful case。",
        "",
        "## 8. Beneficial Case Retention",
        "",
        "思源电气 stock-event 是上一轮 beneficial case。若轻量规则完全消除其进入 Top5，则虽然更安全，但也失去 evidence 的潜在边际价值。当前更合理的方向是 review priority 或 tie-breaker，而非强 multiplier。",
        "",
        "## 9. Recommendation for Production Strategy",
        "",
        "- 当前不接入正式交易。",
        "- 生产层只建议先接入 tag/review priority。",
        "- 若未来进入交易，优先候选是 `tie_breaker_1pct` 或 `rank_jump_cap_1`，不是 multiplier。",
        "- 安全门槛建议：PIT evidence coverage ratio 至少 10%，stock-event 样本数至少 50，单个 stock-event 影响 Top5 天数不超过 20，rank jump cap 最大 1，tie-breaker threshold 最大 1%。",
        "- 必须进一步区分 source_type、freshness、commercial evidence，不允许 field_count 单独决定交易优先级。",
        "",
        "## 10. Appendix",
        "",
        "生成文件：",
        "",
        "- `tech_bottleneck_evidence_usage_ablation_summary.csv`",
        "- `tech_bottleneck_evidence_usage_ablation_daily_top5_changes.csv`",
        "- `tech_bottleneck_evidence_usage_ablation_stock_event_attribution.csv`",
        "- `tech_bottleneck_evidence_usage_ablation_trade_delta.csv`",
        "- `tech_bottleneck_evidence_usage_ablation_v1.md`",
        "",
        "关键假设：forward return 只用于事后研究；正式策略文件未修改；所有 evidence 规则均为 research-only。",
    ]
    (replay_dir / "tech_bottleneck_evidence_usage_ablation_v1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    replay_dir = Path(args.replay_dir)
    base, _, start_date, end_date = _load_replay_context(replay_dir)
    prices = _load_prices_for_candidates(base, start_date=start_date, end_date=end_date)
    market_exposure = pd.read_csv(args.market_exposure_path, low_memory=False)
    market_exposure = _extend_market_exposure(market_exposure, end_date=end_date)
    variant_frames: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    for variant in VARIANTS:
        frame = apply_evidence_usage_variant(base, variant)
        frame["run_id"] = f"tech-bottleneck-evidence-usage-ablation-{variant}"
        frame.to_csv(replay_dir / f"tech_bottleneck_evidence_usage_ablation_{variant}_snapshots.csv", index=False)
        variant_frames[variant] = frame
        rows.append(
            _run_strategy_variant(
                variant=variant,
                snapshots=frame,
                prices=prices,
                market_exposure=market_exposure,
                replay_dir=replay_dir,
                start_date=start_date,
                end_date=end_date,
            )
        )
    baseline = variant_frames["baseline_technical_only"]
    daily_changes = _daily_top5_changes(baseline, variant_frames)
    trade_delta_frames = [
        _position_contribution_delta(replay_dir, variant, prices)
        for variant in VARIANTS
    ]
    trade_delta = pd.concat(trade_delta_frames, ignore_index=True)
    stock_attr = _stock_event_attribution(
        stock_events=_stock_events(replay_dir),
        variant_frames=variant_frames,
        daily_changes=daily_changes,
        trade_delta=trade_delta,
        prices=prices,
    )
    summary = _summary_metrics(
        rows=rows,
        variant_frames=variant_frames,
        daily_changes=daily_changes,
        trade_delta=trade_delta,
    )
    # Populate forward means from stock-event attribution.
    for variant in VARIANTS:
        mask = summary["variant"].eq(variant)
        for horizon in [5, 10, 20]:
            col = f"forward_{horizon}d_delta_{variant}"
            if col in stock_attr.columns:
                summary.loc[mask, f"forward_{horizon}d_delta_mean"] = pd.to_numeric(
                    stock_attr[col], errors="coerce"
                ).mean()
    summary.to_csv(replay_dir / "tech_bottleneck_evidence_usage_ablation_summary.csv", index=False)
    daily_changes.to_csv(replay_dir / "tech_bottleneck_evidence_usage_ablation_daily_top5_changes.csv", index=False)
    stock_attr.to_csv(replay_dir / "tech_bottleneck_evidence_usage_ablation_stock_event_attribution.csv", index=False)
    trade_delta.to_csv(replay_dir / "tech_bottleneck_evidence_usage_ablation_trade_delta.csv", index=False)
    _write_report(replay_dir=replay_dir, summary=summary, stock_attr=stock_attr, daily_changes=daily_changes)
    print(replay_dir / "tech_bottleneck_evidence_usage_ablation_v1.md")
    print(summary[["variant", "total_return", "max_drawdown", "sharpe_ratio", "top5_changed_days_vs_baseline", "max_rank_jump", "realized_return_delta_vs_baseline"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only Tech Bottleneck evidence usage ablation.")
    parser.add_argument("--replay-dir", default=str(DEFAULT_REPLAY_DIR))
    parser.add_argument("--market-exposure-path", default=str(TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH))
    run(parser.parse_args())


if __name__ == "__main__":
    main()
