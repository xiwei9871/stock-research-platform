#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_v1 import _load_prices


DEFAULT_REPLAY_DIR = Path(
    "outputs/research/tech_bottleneck_pit_evidence_replay_neutral_missing_v1_20250101_20260629"
)


def _bool_series(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False)
    return values.fillna(False).astype(str).str.lower().isin({"true", "1", "yes"})


def _event_frame(evidence_seed: pd.DataFrame) -> pd.DataFrame:
    events = evidence_seed.copy()
    if events.empty:
        events["evidence_event_id"] = []
        return events
    events["source_date"] = pd.to_datetime(events["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    events = events.sort_values(["source_date", "asset_id", "field", "source_type"]).reset_index(drop=True)
    events["evidence_event_id"] = [f"EV{i:03d}" for i in range(1, len(events) + 1)]
    return events


def active_evidence_event_ids(events: pd.DataFrame, *, asset_id: str, trade_date: str) -> list[str]:
    if events.empty:
        return []
    frame = _event_frame(events) if "evidence_event_id" not in events.columns else events.copy()
    active = frame[
        frame["asset_id"].astype(str).eq(str(asset_id))
        & frame["source_date"].fillna("").astype(str).le(str(trade_date))
    ]
    return active["evidence_event_id"].astype(str).tolist()


def build_decision_ledger(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    before_cols = [
        "trade_date",
        "asset_id",
        "stock_name",
        "bottleneck_rank",
        "bottleneck_score",
        "is_top5",
    ]
    after_cols = [
        column
        for column in [
            "trade_date",
            "asset_id",
            "stock_name",
            "bottleneck_rank",
            "bottleneck_score",
            "is_top5",
            "raw_bottleneck_score",
            "evidence_confidence_multiplier",
            "evidence_state",
            "evidence_audit_status",
            "latest_evidence_date",
            "source_backed_field_count",
            "primary_chain_name",
            "matched_bottleneck_dimensions",
        ]
        if column in after.columns
    ]
    frame = before[before_cols].merge(
        after[after_cols],
        on=["trade_date", "asset_id"],
        how="outer",
        suffixes=("_before", "_after"),
    )
    frame["stock_name"] = frame.get("stock_name_after", "").fillna(frame.get("stock_name_before", ""))
    frame["rank_before_evidence"] = pd.to_numeric(frame["bottleneck_rank_before"], errors="coerce")
    frame["rank_after_evidence"] = pd.to_numeric(frame["bottleneck_rank_after"], errors="coerce")
    raw = frame["bottleneck_score_before"]
    if "raw_bottleneck_score" in frame.columns:
        raw = frame["raw_bottleneck_score"].fillna(raw)
    frame["raw_technical_score"] = pd.to_numeric(raw, errors="coerce")
    frame["final_score"] = pd.to_numeric(frame["bottleneck_score_after"], errors="coerce")
    frame["evidence_multiplier"] = pd.to_numeric(
        frame.get("evidence_confidence_multiplier", pd.Series([1.0] * len(frame), index=frame.index)),
        errors="coerce",
    ).fillna(1.0)
    frame["selected_top5_before_evidence"] = _bool_series(frame["is_top5_before"])
    frame["selected_top5_after_evidence"] = _bool_series(frame["is_top5_after"])
    frame["entered_top5_due_to_evidence"] = (
        ~frame["selected_top5_before_evidence"] & frame["selected_top5_after_evidence"]
    )
    frame["dropped_from_top5_due_to_evidence"] = (
        frame["selected_top5_before_evidence"] & ~frame["selected_top5_after_evidence"]
    )
    frame["score_delta"] = frame["final_score"] - frame["raw_technical_score"]
    frame["rank_delta"] = frame["rank_before_evidence"] - frame["rank_after_evidence"]
    frame["reason_code"] = "unchanged"
    frame.loc[
        frame["entered_top5_due_to_evidence"] & frame["evidence_multiplier"].gt(1.0),
        "reason_code",
    ] = "evidence_boost_entered_top5"
    frame.loc[
        frame["entered_top5_due_to_evidence"] & frame["evidence_multiplier"].le(1.0),
        "reason_code",
    ] = "entered_top5_tie_or_secondary_sort"
    frame.loc[frame["dropped_from_top5_due_to_evidence"], "reason_code"] = "displaced_by_evidence_boost"
    for column, default in [
        ("evidence_state", "unverified"),
        ("evidence_audit_status", "unavailable"),
        ("latest_evidence_date", ""),
        ("source_backed_field_count", 0),
        ("primary_chain_name", ""),
        ("matched_bottleneck_dimensions", ""),
    ]:
        if column not in frame.columns:
            frame[column] = default
        frame[column] = frame[column].fillna(default)
    result_cols = [
        "trade_date",
        "asset_id",
        "stock_name",
        "rank_before_evidence",
        "rank_after_evidence",
        "raw_technical_score",
        "evidence_multiplier",
        "final_score",
        "score_delta",
        "rank_delta",
        "evidence_state",
        "evidence_audit_status",
        "latest_evidence_date",
        "source_backed_field_count",
        "primary_chain_name",
        "matched_bottleneck_dimensions",
        "selected_top5_before_evidence",
        "selected_top5_after_evidence",
        "entered_top5_due_to_evidence",
        "dropped_from_top5_due_to_evidence",
        "reason_code",
    ]
    return frame[result_cols].sort_values(["trade_date", "rank_after_evidence", "rank_before_evidence", "asset_id"])


def _top5_replacement_events(ledger: pd.DataFrame, events: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    close = prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    rows: list[dict[str, Any]] = []
    for trade_date, day in ledger.groupby("trade_date", sort=True):
        entered = day[day["entered_top5_due_to_evidence"]].sort_values("rank_after_evidence")
        dropped = day[day["dropped_from_top5_due_to_evidence"]].sort_values("rank_before_evidence")
        if entered.empty and dropped.empty:
            continue
        pairs = max(len(entered), len(dropped))
        entered_rows = entered.to_dict("records")
        dropped_rows = dropped.to_dict("records")
        for i in range(pairs):
            in_row = entered_rows[i] if i < len(entered_rows) else {}
            out_row = dropped_rows[i] if i < len(dropped_rows) else {}
            in_asset = str(in_row.get("asset_id", ""))
            out_asset = str(out_row.get("asset_id", ""))
            row = {
                "trade_date": trade_date,
                "entered_asset_id": in_asset,
                "entered_stock_name": in_row.get("stock_name", ""),
                "entered_rank_before": in_row.get("rank_before_evidence"),
                "entered_rank_after": in_row.get("rank_after_evidence"),
                "entered_raw_score": in_row.get("raw_technical_score"),
                "entered_multiplier": in_row.get("evidence_multiplier"),
                "entered_final_score": in_row.get("final_score"),
                "entered_evidence_state": in_row.get("evidence_state"),
                "entered_latest_evidence_date": in_row.get("latest_evidence_date", ""),
                "entered_evidence_event_ids": "|".join(
                    active_evidence_event_ids(events, asset_id=in_asset, trade_date=str(trade_date))
                ),
                "dropped_asset_id": out_asset,
                "dropped_stock_name": out_row.get("stock_name", ""),
                "dropped_rank_before": out_row.get("rank_before_evidence"),
                "dropped_rank_after": out_row.get("rank_after_evidence"),
                "dropped_raw_score": out_row.get("raw_technical_score"),
                "dropped_multiplier": out_row.get("evidence_multiplier"),
                "dropped_final_score": out_row.get("final_score"),
                "reason_code": "evidence_boost_replaced_top5_member",
            }
            for horizon in [5, 10, 20, 60]:
                row[f"forward_{horizon}d_return_of_in_asset"] = _forward_return(close, in_asset, str(trade_date), horizon)
                row[f"forward_{horizon}d_return_of_out_asset"] = _forward_return(close, out_asset, str(trade_date), horizon)
                row[f"forward_{horizon}d_return_delta_in_minus_out"] = (
                    row[f"forward_{horizon}d_return_of_in_asset"] - row[f"forward_{horizon}d_return_of_out_asset"]
                    if pd.notna(row[f"forward_{horizon}d_return_of_in_asset"])
                    and pd.notna(row[f"forward_{horizon}d_return_of_out_asset"])
                    else pd.NA
                )
            rows.append(row)
    return pd.DataFrame(rows)


def _forward_return(close: pd.DataFrame, asset_id: str, trade_date: str, horizon: int) -> float | pd.NA:
    if not asset_id or asset_id not in close.columns or trade_date not in close.index:
        return pd.NA
    dates = close.index.tolist()
    idx = dates.index(trade_date)
    target_idx = idx + horizon
    if target_idx >= len(dates):
        return pd.NA
    start = close.at[trade_date, asset_id]
    end = close.iloc[target_idx][asset_id]
    if pd.isna(start) or pd.isna(end) or float(start) == 0.0:
        return pd.NA
    return float(end) / float(start) - 1.0


def _position_contribution_delta(replay_dir: Path, prices: pd.DataFrame) -> pd.DataFrame:
    normalized_prices = prices.copy()
    normalized_prices["close"] = pd.to_numeric(normalized_prices["close"], errors="coerce")
    close = normalized_prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    next_return = close.shift(-1) / close - 1.0

    def contributions(variant: str) -> pd.DataFrame:
        positions = pd.read_csv(replay_dir / variant / "strategy_tech_bottleneck_positions.csv")
        rows: list[dict[str, Any]] = []
        for row in positions.itertuples(index=False):
            trade_date = str(row.trade_date)
            asset_id = str(row.asset_id)
            ret = next_return.at[trade_date, asset_id] if trade_date in next_return.index and asset_id in next_return.columns else pd.NA
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    f"{variant}_weight": float(row.weight),
                    f"{variant}_contribution": float(row.weight) * float(ret) if pd.notna(ret) else 0.0,
                }
            )
        return pd.DataFrame(rows)

    old = contributions("pit_replay_old_evidence")
    new = contributions("pit_replay_after_new_reports")
    frame = old.merge(new, on=["trade_date", "asset_id"], how="outer").fillna(0.0)
    frame["weight_delta_new_minus_old"] = (
        frame["pit_replay_after_new_reports_weight"] - frame["pit_replay_old_evidence_weight"]
    )
    frame["contribution_delta_new_minus_old"] = (
        frame["pit_replay_after_new_reports_contribution"] - frame["pit_replay_old_evidence_contribution"]
    )
    return frame.sort_values(["trade_date", "contribution_delta_new_minus_old", "asset_id"])


def _event_attribution(
    events: pd.DataFrame,
    ledger: pd.DataFrame,
    replacements: pd.DataFrame,
    contribution_delta: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for event in events.itertuples(index=False):
        event_id = str(event.evidence_event_id)
        asset_id = str(event.asset_id)
        source_date = str(event.source_date)
        active_ledger = ledger[
            ledger["asset_id"].astype(str).eq(asset_id)
            & ledger["trade_date"].astype(str).ge(source_date)
        ]
        impacted = active_ledger[active_ledger["entered_top5_due_to_evidence"]]
        first = impacted.sort_values("trade_date").head(1)
        replacement_rows = replacements[
            replacements["entered_evidence_event_ids"].fillna("").astype(str).str.split("|").apply(lambda ids: event_id in ids)
        ]
        contrib = contribution_delta[
            contribution_delta["asset_id"].astype(str).eq(asset_id)
            & contribution_delta["trade_date"].astype(str).ge(source_date)
        ]
        realized_delta = float(contrib["contribution_delta_new_minus_old"].sum()) if not contrib.empty else 0.0
        top5_impact_type = "not_selected"
        first_effective = source_date
        if not first.empty:
            top5_impact_type = "entered_top5"
            first_effective = str(first.iloc[0]["trade_date"])
        elif bool((active_ledger["rank_delta"].fillna(0) > 0).any()):
            top5_impact_type = "rank_improved_no_top5"
        label = _attribution_label(top5_impact_type, realized_delta, replacement_rows)
        row: dict[str, Any] = {
            "evidence_event_id": event_id,
            "asset_id": asset_id,
            "stock_name": getattr(event, "stock_name", ""),
            "evidence_date": source_date,
            "trade_date_first_effective": first_effective,
            "source_type": getattr(event, "source_type", ""),
            "field_key": getattr(event, "field", ""),
            "old_multiplier": 1.0,
            "new_multiplier": float(first.iloc[0]["evidence_multiplier"]) if not first.empty else 1.0,
            "score_delta": float(first.iloc[0]["score_delta"]) if not first.empty else 0.0,
            "rank_delta": float(first.iloc[0]["rank_delta"]) if not first.empty else 0.0,
            "top5_impact_type": top5_impact_type,
            "top5_impact_days": int(active_ledger["entered_top5_due_to_evidence"].sum()),
            "realized_trade_return_delta": realized_delta,
            "attribution_label": label,
        }
        if not replacement_rows.empty:
            first_repl = replacement_rows.sort_values("trade_date").iloc[0]
            row.update(
                {
                    "replaced_in_asset_id": first_repl.get("entered_asset_id", ""),
                    "replaced_in_symbol": first_repl.get("entered_stock_name", ""),
                    "replaced_out_asset_id": first_repl.get("dropped_asset_id", ""),
                    "replaced_out_symbol": first_repl.get("dropped_stock_name", ""),
                }
            )
            for horizon in [5, 10, 20, 60]:
                row[f"forward_{horizon}d_return_of_in_asset"] = first_repl.get(
                    f"forward_{horizon}d_return_of_in_asset", pd.NA
                )
                row[f"forward_{horizon}d_return_of_out_asset"] = first_repl.get(
                    f"forward_{horizon}d_return_of_out_asset", pd.NA
                )
        else:
            row.update(
                {
                    "replaced_in_asset_id": "",
                    "replaced_in_symbol": "",
                    "replaced_out_asset_id": "",
                    "replaced_out_symbol": "",
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _attribution_label(top5_impact_type: str, realized_delta: float, replacement_rows: pd.DataFrame) -> str:
    if top5_impact_type == "not_selected":
        return "not_selected"
    if replacement_rows.empty:
        return "neutral"
    if realized_delta > 0.002:
        return "beneficial"
    if realized_delta < -0.002:
        return "harmful"
    return "neutral"


def _load_replay_inputs(replay_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    before = pd.read_csv(replay_dir / "old_pit_evidence_adjusted_daily_candidate_snapshots_diagnostic.csv", low_memory=False)
    after = pd.read_csv(replay_dir / "pit_evidence_adjusted_daily_candidate_snapshots_diagnostic.csv", low_memory=False)
    events = _event_frame(pd.read_csv(replay_dir / "new_evidence_seed_pit_usable.csv", low_memory=False))
    audit = pd.read_csv(replay_dir / "pit_evidence_no_lookahead_audit.csv", low_memory=False)
    return before, after, events, audit


def _load_replay_prices(before: pd.DataFrame, end_date: str, start_date: str) -> pd.DataFrame:
    asset_ids = sorted(before["asset_id"].dropna().astype(str).unique().tolist())
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


def _fmt_pct(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _fmt_num(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.4f}"


def _small_markdown(frame: pd.DataFrame, columns: list[str], *, max_rows: int = 12) -> str:
    if frame.empty:
        return "_No rows._"
    return frame[columns].head(max_rows).to_markdown(index=False)


def _write_markdown(
    *,
    replay_dir: Path,
    comparison: pd.DataFrame,
    audit: pd.DataFrame,
    ledger: pd.DataFrame,
    replacements: pd.DataFrame,
    events: pd.DataFrame,
    event_attr: pd.DataFrame,
    contribution_delta: pd.DataFrame,
) -> None:
    summary_counts = event_attr["attribution_label"].value_counts().to_dict() if not event_attr.empty else {}
    changed_days = int(ledger.groupby("trade_date")["entered_top5_due_to_evidence"].sum().gt(0).sum())
    entered_assets = int(ledger[ledger["entered_top5_due_to_evidence"]]["asset_id"].nunique())
    dropped_assets = int(ledger[ledger["dropped_from_top5_due_to_evidence"]]["asset_id"].nunique())
    total_delta = (
        float(comparison.loc[comparison["variant"].eq("pit_replay_after_new_reports"), "total_return"].iloc[0])
        - float(comparison.loc[comparison["variant"].eq("official_v1_baseline_static_seed"), "total_return"].iloc[0])
    )
    harmful = event_attr[event_attr["attribution_label"].eq("harmful")].sort_values("realized_trade_return_delta")
    beneficial = event_attr[event_attr["attribution_label"].eq("beneficial")].sort_values(
        "realized_trade_return_delta", ascending=False
    )
    worst_replacements = replacements.sort_values("forward_20d_return_delta_in_minus_out").copy()
    best_replacements = replacements.sort_values("forward_20d_return_delta_in_minus_out", ascending=False).copy()
    for frame in [worst_replacements, best_replacements]:
        for horizon in [5, 10, 20, 60]:
            for col in [f"forward_{horizon}d_return_of_in_asset", f"forward_{horizon}d_return_of_out_asset", f"forward_{horizon}d_return_delta_in_minus_out"]:
                if col in frame.columns:
                    frame[col] = frame[col].map(_fmt_pct)
    event_report = event_attr.copy()
    for col in [
        "realized_trade_return_delta",
        "score_delta",
        "rank_delta",
        "forward_5d_return_of_in_asset",
        "forward_5d_return_of_out_asset",
        "forward_10d_return_of_in_asset",
        "forward_10d_return_of_out_asset",
        "forward_20d_return_of_in_asset",
        "forward_20d_return_of_out_asset",
    ]:
        if col in event_report.columns:
            event_report[col] = event_report[col].map(_fmt_num)

    audit_metrics = dict(zip(audit["metric"], audit["value"]))
    comp_cols = ["variant", "total_return", "max_drawdown", "sharpe_ratio", "trade_rows"]
    comp = comparison[comp_cols].copy()
    for col in ["total_return", "max_drawdown", "sharpe_ratio"]:
        comp[col] = comp[col].map(_fmt_num)
    replacement_summary = replacements.copy()
    for col in ["entered_raw_score", "entered_multiplier", "entered_final_score", "dropped_raw_score", "dropped_final_score"]:
        if col in replacement_summary.columns:
            replacement_summary[col] = replacement_summary[col].map(_fmt_num)
    lines = [
        "# Tech Bottleneck PIT Evidence Impact Attribution v1",
        "",
        "## 1. Executive Summary",
        "",
        f"- 本报告基于 `neutral_missing_v1` replay，正式交易策略未变更。",
        f"- 新 PIT evidence 共 `{len(events)}` 条；其中 `{int(event_attr['top5_impact_type'].eq('entered_top5').sum())}` 条至少一次把对应股票推入 Top5。",
        f"- event 标签分布：beneficial `{summary_counts.get('beneficial', 0)}`，harmful `{summary_counts.get('harmful', 0)}`，neutral `{summary_counts.get('neutral', 0)}`，not_selected `{summary_counts.get('not_selected', 0)}`。",
        f"- Top5 发生 evidence-driven 推入的交易日 `{changed_days}` 天，涉及推入股票 `{entered_assets}` 只、被挤出股票 `{dropped_assets}` 只。",
        f"- `pit_replay_after_new_reports` 相对 official baseline 的 total_return 差值为 `{total_delta:.4f}`，方向仍为负。",
        "- 主要问题不是 missing multiplier 了，而是少量 E2/E3 evidence 对 Top5 排名有放大效应，推入后的组合贡献不足以覆盖被挤出标的的机会成本。",
        "- 结论：继续禁用 evidence multiplier 接入正式交易；下一步应做字段/来源/freshness 分层，不应按 field count 直接乘分。",
        "",
        "## 2. Replay Context",
        "",
        f"- Replay directory: `{replay_dir}`",
        "- Rule version: `neutral_missing_v1`",
        "- Variant comparison:",
        "",
        comp.to_markdown(index=False),
        "",
        "## 3. Evidence Coverage and Audit Status",
        "",
        f"- `old_evidence_audit_status`: `{audit_metrics.get('old_evidence_audit_status')}`",
        f"- `new_evidence_audit_status`: `{audit_metrics.get('new_evidence_audit_status')}`",
        f"- `old_pit_evidence_coverage_ratio`: `{audit_metrics.get('old_pit_evidence_coverage_ratio')}`",
        f"- `new_pit_evidence_coverage_ratio`: `{audit_metrics.get('new_pit_evidence_coverage_ratio')}`",
        f"- `lookahead_violation_rows`: `{audit_metrics.get('lookahead_violation_rows')}`",
        f"- `top5_changed_days_old_vs_new`: `{audit_metrics.get('top5_changed_days_old_vs_new')}`",
        "",
        "## 4. Top5 Replacement Summary",
        "",
        "以下列出 20 日 forward return 差值最差的替换事件。",
        "",
        _small_markdown(
            worst_replacements,
            [
                "trade_date",
                "entered_stock_name",
                "entered_rank_before",
                "entered_rank_after",
                "entered_multiplier",
                "dropped_stock_name",
                "dropped_rank_before",
                "dropped_rank_after",
                "forward_20d_return_of_in_asset",
                "forward_20d_return_of_out_asset",
                "forward_20d_return_delta_in_minus_out",
            ],
            max_rows=10,
        ),
        "",
        "以下列出 20 日 forward return 差值最好的替换事件。",
        "",
        _small_markdown(
            best_replacements,
            [
                "trade_date",
                "entered_stock_name",
                "entered_rank_before",
                "entered_rank_after",
                "entered_multiplier",
                "dropped_stock_name",
                "dropped_rank_before",
                "dropped_rank_after",
                "forward_20d_return_of_in_asset",
                "forward_20d_return_of_out_asset",
                "forward_20d_return_delta_in_minus_out",
            ],
            max_rows=10,
        ),
        "",
        "## 5. Evidence Event Attribution Table",
        "",
        _small_markdown(
            event_report,
            [
                "evidence_event_id",
                "asset_id",
                "evidence_date",
                "source_type",
                "field_key",
                "top5_impact_type",
                "top5_impact_days",
                "replaced_in_symbol",
                "replaced_out_symbol",
                "realized_trade_return_delta",
                "attribution_label",
            ],
            max_rows=20,
        ),
        "",
        "## 6. Harmful Cases",
        "",
        "Harmful 的定义是：该 evidence 对应股票在 source_date 之后进入 Top5，且新旧持仓差异贡献为负。这个贡献是研究近似，未精确拆分组合复利和交易成本。",
        "",
        _small_markdown(
            harmful,
            [
                "evidence_event_id",
                "asset_id",
                "evidence_date",
                "field_key",
                "top5_impact_days",
                "replaced_in_symbol",
                "replaced_out_symbol",
                "realized_trade_return_delta",
            ],
            max_rows=12,
        ),
        "",
        "## 7. Beneficial Cases",
        "",
        _small_markdown(
            beneficial,
            [
                "evidence_event_id",
                "asset_id",
                "evidence_date",
                "field_key",
                "top5_impact_days",
                "replaced_in_symbol",
                "replaced_out_symbol",
                "realized_trade_return_delta",
            ],
            max_rows=12,
        ),
        "",
        "## 8. Why After-New-Reports Still Underperforms Baseline",
        "",
        "当前证据支持以下判断：",
        "",
        "1. **evidence 覆盖太少。** 新 PIT usable evidence 只有 12 条，覆盖率约 1.95%。样本不足以支撑稳定的横截面重排。",
        "2. **multiplier 仍然偏强。** E2/E3 只影响少数股票，但能改变 109 个交易日的 Top5 集合，说明排序杠杆过大。",
        "3. **推入股票的机会成本偏高。** 多个替换事件中，进入股票 20 日 forward return 低于被挤出股票，说明 evidence boost 经常替换掉更强的原始技术/低位排序候选。",
        "4. **不是风控改进。** after-new-reports 的 max_drawdown 与 baseline 基本相同，但 total_return 明显下降，说明 evidence 没有有效降低左尾风险。",
        "5. **更像小样本噪声叠加过强 multiplier。** 目前不能证明 evidence 规则整体无效，但可以证明 field-count multiplier 不适合直接进交易。",
        "",
        "## 9. Recommendations",
        "",
        "- 继续禁用 evidence multiplier 接入正式交易。",
        "- 将 evidence 从 `multiplier` 降级为 `tag / review priority / tie-breaker`，不要直接乘主分。",
        "- 如果继续测试 multiplier，应把 E2/E3 强度降到更小，例如 1.01/1.03，并设置最大 rank jump cap。",
        "- 扩大 PIT evidence coverage 前，不做策略接入实验。",
        "- 后续 evidence 必须按 source_type、freshness、field、是否商业化订单/客户认证分别归因。",
        "- 下一轮优先做 `evidence field/source/freshness attribution`，而不是继续调 TopN 或保护参数。",
        "",
        "## 10. Appendix",
        "",
        "生成文件：",
        "",
        "- `tech_bottleneck_pit_evidence_decision_ledger.csv`",
        "- `tech_bottleneck_pit_top5_replacement_events.csv`",
        "- `tech_bottleneck_pit_evidence_event_attribution.csv`",
        "- `tech_bottleneck_pit_position_contribution_delta.csv`",
        "- `tech_bottleneck_pit_evidence_impact_attribution_v1.md`",
        "",
        "关键假设：",
        "",
        "- old PIT 等价 official baseline，因此使用 old PIT 作为 before-evidence 口径。",
        "- realized trade return delta 使用每日持仓权重乘 next-day return 的差值做研究近似。",
        "- forward return 只用于事后归因，不参与任何策略信号。",
        "- 正式策略文件未修改。",
    ]
    (replay_dir / "tech_bottleneck_pit_evidence_impact_attribution_v1.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> None:
    replay_dir = Path(args.replay_dir)
    before, after, events, audit = _load_replay_inputs(replay_dir)
    comparison = pd.read_csv(replay_dir / "baseline_vs_pit_evidence_replay.csv", low_memory=False)
    start_date = str(comparison["actual_replay_start_date"].dropna().iloc[0])
    end_date = str(comparison["end_date"].dropna().iloc[0])
    prices = _load_replay_prices(before, end_date=end_date, start_date=start_date)
    ledger = build_decision_ledger(before, after)
    replacements = _top5_replacement_events(ledger, events, prices)
    contribution_delta = _position_contribution_delta(replay_dir, prices)
    event_attr = _event_attribution(events, ledger, replacements, contribution_delta)

    ledger.to_csv(replay_dir / "tech_bottleneck_pit_evidence_decision_ledger.csv", index=False)
    replacements.to_csv(replay_dir / "tech_bottleneck_pit_top5_replacement_events.csv", index=False)
    contribution_delta.to_csv(replay_dir / "tech_bottleneck_pit_position_contribution_delta.csv", index=False)
    event_attr.to_csv(replay_dir / "tech_bottleneck_pit_evidence_event_attribution.csv", index=False)
    _write_markdown(
        replay_dir=replay_dir,
        comparison=comparison,
        audit=audit,
        ledger=ledger,
        replacements=replacements,
        events=events,
        event_attr=event_attr,
        contribution_delta=contribution_delta,
    )
    print(replay_dir / "tech_bottleneck_pit_evidence_impact_attribution_v1.md")
    print(event_attr[["evidence_event_id", "asset_id", "field_key", "top5_impact_type", "top5_impact_days", "realized_trade_return_delta", "attribution_label"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only Tech Bottleneck PIT evidence impact attribution.")
    parser.add_argument("--replay-dir", default=str(DEFAULT_REPLAY_DIR))
    run(parser.parse_args())


if __name__ == "__main__":
    main()
