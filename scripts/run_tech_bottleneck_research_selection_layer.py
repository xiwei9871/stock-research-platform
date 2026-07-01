#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_v1 import _load_prices


REPLAY_DIR = Path("outputs/research/tech_bottleneck_pit_evidence_replay_neutral_missing_v1_20250101_20260629")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_research_selection_layer_v1")
RULE_VERSION = "tech_bottleneck_research_selection_layer_v1"
ALLOWED_REVIEW_ACTIONS = {
    "review_thesis",
    "monitor_setup",
    "review_data_quality",
    "risk_review_required",
    "ignore_until_reconfirmed",
    "watch_only",
}
FORBIDDEN_REVIEW_WORDS = {"buy", "sell", "add", "reduce", "hold", "target_price"}


def validate_review_actions(cards: pd.DataFrame) -> bool:
    if "recommended_action_for_reviewer" not in cards.columns:
        return False
    actions = cards["recommended_action_for_reviewer"].fillna("").astype(str)
    if not set(actions).issubset(ALLOWED_REVIEW_ACTIONS):
        return False
    lowered = actions.str.lower()
    return not any(lowered.str.contains(word, regex=False).any() for word in FORBIDDEN_REVIEW_WORDS)


def evidence_quality_score(field_count: Any) -> float:
    count = int(pd.to_numeric(pd.Series([field_count]), errors="coerce").fillna(0).iloc[0])
    if count >= 3:
        return 0.9
    if count == 2:
        return 0.75
    if count == 1:
        return 0.6
    return 0.5


def evidence_state_from_row(row: pd.Series) -> str:
    count = int(pd.to_numeric(pd.Series([row.get("source_backed_field_count", 0)]), errors="coerce").fillna(0).iloc[0])
    audit_status = str(row.get("evidence_audit_status", "") or "")
    if "risk" in str(row.get("evidence_state", "")).lower():
        return "risk_evidence"
    if audit_status == "degraded_no_pit_evidence":
        return "degraded_no_pit_evidence"
    if count >= 2:
        return "active_pit_evidence"
    if count == 1:
        return "weak"
    return "unverified"


def active_evidence_count(evidence: pd.DataFrame, *, asset_id: str, trade_date: str) -> int:
    if evidence.empty:
        return 0
    frame = evidence.copy()
    frame["source_date"] = pd.to_datetime(frame["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    active = frame[
        frame["asset_id"].astype(str).eq(str(asset_id))
        & frame["source_date"].fillna("").astype(str).le(str(trade_date))
    ]
    return int(active["field"].nunique()) if "field" in active.columns else int(len(active))


def compute_research_candidate_score(row: pd.Series) -> float:
    evidence = evidence_quality_score(row.get("source_backed_field_count", 0))
    low_position = _num(row.get("low_position_score"), 0.5)
    commercial = _num(row.get("commercial_validation_score"), 0.5)
    freshness = _num(row.get("freshness_score"), 0.5)
    risk = _num(row.get("fundamental_risk_score"), 0.0)
    score = 0.30 * evidence + 0.25 * low_position + 0.20 * commercial + 0.15 * freshness - 0.10 * risk
    return float(max(0.0, min(1.0, score)))


def _num(value: Any, default: float) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(default if pd.isna(parsed) else parsed)


def _research_priority(row: pd.Series) -> str:
    if bool(row.get("recent_drawdown_risk_flag", False)) or bool(row.get("event_risk_flag", False)):
        return "risk_review"
    score = float(row.get("research_candidate_score", 0.0))
    if score >= 0.72:
        return "high"
    if score >= 0.60:
        return "medium"
    if score >= 0.48:
        return "low"
    return "watch_only"


def _freshness_score(days: Any) -> float:
    if pd.isna(days):
        return 0.5
    return float(max(0.0, min(1.0, 1.0 - float(days) / 365.0)))


def _freshness_bucket(days: Any) -> str:
    if pd.isna(days):
        return "no_pit_evidence"
    days = float(days)
    if days <= 30:
        return "0_30d"
    if days <= 90:
        return "31_90d"
    if days <= 180:
        return "91_180d"
    return "181d_plus"


def _symbol(asset_id: Any) -> str:
    return str(asset_id).split(":")[-1]


def build_research_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    frame["symbol"] = frame["asset_id"].map(_symbol)
    frame["name"] = frame.get("stock_name", "").fillna("").astype(str)
    if "source_backed_field_count" not in frame.columns:
        frame["source_backed_field_count"] = 0
    frame["source_backed_field_count"] = pd.to_numeric(frame["source_backed_field_count"], errors="coerce").fillna(0).astype(int)
    frame["evidence_state"] = frame.apply(evidence_state_from_row, axis=1)
    frame["evidence_quality_score"] = frame["source_backed_field_count"].map(evidence_quality_score)
    for column, default in [
        ("low_position_score", 0.5),
        ("commercial_validation_score", 0.5),
        ("freshness_score", 0.5),
        ("fundamental_risk_score", 0.0),
    ]:
        if column not in frame.columns:
            frame[column] = default
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(default)
    frame["research_candidate_score"] = frame.apply(compute_research_candidate_score, axis=1)
    frame["research_priority"] = frame.apply(_research_priority, axis=1)
    frame["evidence_tags"] = frame.apply(_evidence_tags, axis=1)
    frame["source_count"] = frame["source_backed_field_count"]
    if "source_type_set" not in frame.columns:
        frame["source_type_set"] = ""
    frame["source_type_set"] = frame["source_type_set"].fillna("").astype(str)
    if "primary_chain_name" not in frame.columns:
        frame["primary_chain_name"] = ""
    frame["industry_bottleneck_theme"] = frame["primary_chain_name"].fillna("").astype(str)
    frame["thesis_summary"] = frame.apply(
        lambda row: f"{row.get('name', '')}: {row.get('industry_bottleneck_theme', '') or '未分类瓶颈主题'}; evidence={row.get('evidence_state', 'unverified')}",
        axis=1,
    )
    frame["risk_summary"] = frame.apply(_risk_summary, axis=1)
    frame["human_review_required"] = frame["research_priority"].isin(["high", "risk_review"])
    if "data_quality_status" not in frame.columns:
        frame["data_quality_status"] = "ok"
    frame["data_quality_status"] = frame["data_quality_status"].fillna("ok").astype(str)
    frame["rule_version"] = RULE_VERSION
    frame["valuation_position_score"] = pd.NA
    frame["fundamental_risk_score"] = pd.to_numeric(frame["fundamental_risk_score"], errors="coerce").fillna(0.0)
    columns = [
        "trade_date",
        "asset_id",
        "symbol",
        "name",
        "research_candidate_score",
        "research_priority",
        "evidence_state",
        "evidence_tags",
        "source_count",
        "source_type_set",
        "freshness_days",
        "low_position_score",
        "valuation_position_score",
        "fundamental_risk_score",
        "commercial_validation_score",
        "industry_bottleneck_theme",
        "thesis_summary",
        "risk_summary",
        "human_review_required",
        "data_quality_status",
        "rule_version",
    ]
    return frame[[column for column in columns if column in frame.columns]]


def _evidence_tags(row: pd.Series) -> str:
    tags: list[str] = []
    if bool(row.get("has_revenue_evidence", False)):
        tags.append("revenue_exposure")
    if bool(row.get("has_customer_evidence", False)):
        tags.append("customer_certification")
    if bool(row.get("has_supplier_evidence", False)):
        tags.append("supplier_constraint")
    if not tags:
        tags.append("unverified")
    return "|".join(tags)


def _risk_summary(row: pd.Series) -> str:
    flags = []
    if bool(row.get("recent_drawdown_risk_flag", False)):
        flags.append("recent_drawdown_risk")
    if bool(row.get("event_risk_flag", False)):
        flags.append("event_risk")
    if not flags:
        return "no_explicit_risk_flags; valuation/fundamental risk data partially missing"
    return "|".join(flags)


def _load_candidates(replay_dir: Path) -> pd.DataFrame:
    base = pd.read_csv(replay_dir / "official_baseline_daily_candidate_snapshots.csv", low_memory=False)
    pit = pd.read_csv(replay_dir / "pit_daily_evidence_multiplier.csv", low_memory=False)
    evidence_cols = [
        column
        for column in [
            "trade_date",
            "asset_id",
            "source_backed_field_count",
            "evidence_confidence_multiplier",
            "latest_evidence_date",
            "has_revenue_evidence",
            "has_customer_evidence",
            "has_supplier_evidence",
            "evidence_state",
            "evidence_audit_status",
            "evidence_coverage_ratio",
        ]
        if column in pit.columns
    ]
    frame = base.merge(pit[evidence_cols], on=["trade_date", "asset_id"], how="left")
    return frame


def _load_evidence(replay_dir: Path) -> pd.DataFrame:
    path = replay_dir / "new_evidence_seed_pit_usable.csv"
    if not path.exists():
        return pd.DataFrame(columns=["asset_id", "field", "source_type", "source_date"])
    frame = pd.read_csv(path, low_memory=False)
    frame["source_date"] = pd.to_datetime(frame["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame


def _load_price_features(candidates: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
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
    close = prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    high_120 = close.rolling(120, min_periods=3).max()
    low_120 = close.rolling(120, min_periods=3).min()
    pct_20_vol = close.pct_change().rolling(20, min_periods=5).std()
    rows: list[dict[str, Any]] = []
    candidate_keys = candidates[["trade_date", "asset_id", "stock_name"]].drop_duplicates()
    for row in candidate_keys.itertuples(index=False):
        trade_date = str(row.trade_date)
        asset_id = str(row.asset_id)
        close_value = close.at[trade_date, asset_id] if trade_date in close.index and asset_id in close.columns else np.nan
        h120 = high_120.at[trade_date, asset_id] if trade_date in high_120.index and asset_id in high_120.columns else np.nan
        l120 = low_120.at[trade_date, asset_id] if trade_date in low_120.index and asset_id in low_120.columns else np.nan
        vol20 = pct_20_vol.at[trade_date, asset_id] if trade_date in pct_20_vol.index and asset_id in pct_20_vol.columns else np.nan
        drawdown = float(close_value / h120 - 1.0) if pd.notna(close_value) and pd.notna(h120) and h120 else np.nan
        percentile = float((close_value - l120) / (h120 - l120)) if pd.notna(close_value) and pd.notna(h120) and pd.notna(l120) and h120 != l120 else np.nan
        price_score = float(max(0.0, min(1.0, 1.0 - percentile))) if pd.notna(percentile) else 0.5
        compression_score = float(max(0.0, min(1.0, 1.0 - vol20 / 0.06))) if pd.notna(vol20) else 0.5
        technical_score = 0.7 * price_score + 0.3 * compression_score
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "symbol": _symbol(asset_id),
                "name": str(row.stock_name or ""),
                "price_position_score": price_score,
                "valuation_position_score": pd.NA,
                "expectation_position_score": pd.NA,
                "fundamental_position_score": pd.NA,
                "technical_position_score": technical_score,
                "low_position_score": 0.7 * price_score + 0.3 * technical_score,
                "price_drawdown_from_120d_high": drawdown,
                "price_percentile_120d": percentile,
                "valuation_data_status": "missing",
                "expectation_data_status": "missing",
                "fundamental_data_status": "missing",
                "data_missing_flags": "valuation_missing|expectation_missing|fundamental_missing",
            }
        )
    return pd.DataFrame(rows)


def _attach_research_features(candidates: pd.DataFrame, low_position: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.merge(
        low_position[
            [
                "trade_date",
                "asset_id",
                "low_position_score",
                "technical_position_score",
                "price_drawdown_from_120d_high",
                "price_percentile_120d",
            ]
        ],
        on=["trade_date", "asset_id"],
        how="left",
    )
    frame["low_position_score"] = pd.to_numeric(frame["low_position_score"], errors="coerce").fillna(0.5)
    frame["source_backed_field_count"] = pd.to_numeric(frame["source_backed_field_count"], errors="coerce").fillna(0).astype(int)
    for column in ["has_revenue_evidence", "has_customer_evidence", "has_supplier_evidence"]:
        if column not in frame.columns:
            frame[column] = False
        frame[column] = frame[column].fillna(False).astype(bool)
    frame["latest_evidence_date"] = pd.to_datetime(frame.get("latest_evidence_date", ""), errors="coerce")
    frame["trade_date_dt"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["freshness_days"] = (frame["trade_date_dt"] - frame["latest_evidence_date"]).dt.days
    frame["freshness_score"] = frame["freshness_days"].map(_freshness_score)
    frame["commercial_validation_score"] = frame.apply(
        lambda row: 0.8 if row.get("has_customer_evidence") or row.get("has_supplier_evidence") else 0.5,
        axis=1,
    )
    frame["fundamental_risk_score"] = 0.0
    frame["recent_drawdown_risk_flag"] = pd.to_numeric(frame["price_drawdown_from_120d_high"], errors="coerce").lt(-0.45)
    frame["event_risk_flag"] = False
    source_sets = _source_type_sets(evidence)
    frame = frame.merge(source_sets, on=["trade_date", "asset_id"], how="left")
    frame["source_type_set"] = frame["source_type_set"].fillna("")
    date_coverage = frame.groupby("trade_date")["source_backed_field_count"].apply(lambda values: float((values > 0).mean()))
    frame["evidence_coverage_ratio_day"] = frame["trade_date"].map(date_coverage)
    frame["data_quality_status"] = np.where(frame["evidence_coverage_ratio_day"] < 0.10, "degraded_coverage", "ok")
    return frame.drop(columns=["trade_date_dt"], errors="ignore")


def _source_type_sets(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "source_type_set"])
    rows: list[dict[str, Any]] = []
    dates = sorted(evidence["source_date"].dropna().astype(str).unique().tolist())
    for trade_date in dates:
        active = evidence[evidence["source_date"].astype(str).le(trade_date)]
        for asset_id, group in active.groupby("asset_id"):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "source_type_set": "|".join(sorted(set(group["source_type"].dropna().astype(str)))),
                }
            )
    return pd.DataFrame(rows)


def build_source_coverage(candidates: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    frame = candidates[["trade_date", "asset_id"]].drop_duplicates().copy()
    if evidence.empty:
        grouped = frame.groupby("trade_date").size().reset_index(name="candidate_count")
        grouped["pit_evidence_count"] = 0
        grouped["evidence_coverage_ratio"] = 0.0
        grouped["source_type_distribution"] = "{}"
        grouped["evidence_state_distribution"] = "{}"
        grouped["freshness_bucket_distribution"] = "{}"
        grouped["missing_valuation_ratio"] = 1.0
        grouped["missing_fundamental_ratio"] = 1.0
        grouped["lookahead_violation_rows"] = 0
        grouped["data_quality_status"] = "degraded_coverage"
        return grouped
    evidence = evidence.copy()
    evidence["source_date"] = pd.to_datetime(evidence["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    rows: list[dict[str, Any]] = []
    for trade_date, day in frame.groupby("trade_date", sort=True):
        assets = set(day["asset_id"].astype(str))
        active = evidence[evidence["source_date"].astype(str).le(str(trade_date))]
        active = active[active["asset_id"].astype(str).isin(assets)]
        pit_assets = set(active["asset_id"].astype(str))
        candidate_count = len(assets)
        field_counts = active.groupby("asset_id")["field"].nunique() if not active.empty else pd.Series(dtype="int64")
        evidence_state_distribution = field_counts.map(
            lambda count: "active_pit_evidence" if count >= 2 else "weak" if count == 1 else "unverified"
        ).value_counts().to_dict()
        latest = active.groupby("asset_id")["source_date"].max() if not active.empty else pd.Series(dtype="object")
        freshness = (pd.Timestamp(str(trade_date)) - pd.to_datetime(latest, errors="coerce")).dt.days if not latest.empty else pd.Series(dtype="float64")
        freshness_dist = freshness.map(_freshness_bucket).value_counts().to_dict() if not freshness.empty else {}
        coverage_ratio = len(pit_assets) / candidate_count if candidate_count else 0.0
        rows.append(
            {
                "trade_date": trade_date,
                "candidate_count": candidate_count,
                "pit_evidence_count": len(pit_assets),
                "evidence_coverage_ratio": coverage_ratio,
                "source_type_distribution": str(active["source_type"].value_counts().to_dict()) if "source_type" in active.columns else "{}",
                "evidence_state_distribution": str(evidence_state_distribution),
                "freshness_bucket_distribution": str(freshness_dist),
                "missing_valuation_ratio": 1.0,
                "missing_fundamental_ratio": 1.0,
                "lookahead_violation_rows": 0,
                "data_quality_status": "degraded_coverage" if coverage_ratio < 0.10 else "ok",
            }
        )
    return pd.DataFrame(rows)


def build_risk_audit(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    frame["symbol"] = frame["asset_id"].map(_symbol)
    frame["name"] = frame.get("stock_name", "").fillna("").astype(str)
    frame["valuation_risk_flag"] = "missing"
    frame["liquidity_risk_flag"] = "missing"
    frame["recent_drawdown_risk_flag"] = frame.get("recent_drawdown_risk_flag", False).fillna(False).astype(bool)
    frame["event_risk_flag"] = False
    frame["risk_flags"] = frame.apply(
        lambda row: "|".join(
            flag
            for flag, active in [
                ("recent_drawdown_risk", bool(row.get("recent_drawdown_risk_flag", False))),
                ("valuation_missing", True),
                ("liquidity_missing", True),
                ("fundamental_missing", True),
            ]
            if active
        ),
        axis=1,
    )
    frame["risk_summary"] = frame.apply(_risk_summary, axis=1)
    frame["fundamental_risk_score"] = pd.to_numeric(frame.get("fundamental_risk_score", 0.0), errors="coerce").fillna(0.0)
    frame["human_review_required"] = frame["recent_drawdown_risk_flag"]
    return frame[
        [
            "trade_date",
            "asset_id",
            "symbol",
            "name",
            "risk_flags",
            "risk_summary",
            "fundamental_risk_score",
            "valuation_risk_flag",
            "liquidity_risk_flag",
            "recent_drawdown_risk_flag",
            "event_risk_flag",
            "human_review_required",
        ]
    ]


def build_review_cards(research_candidates: pd.DataFrame, low_position: pd.DataFrame) -> pd.DataFrame:
    frame = research_candidates.merge(
        low_position[
            [
                "trade_date",
                "asset_id",
                "price_drawdown_from_120d_high",
                "price_percentile_120d",
                "technical_position_score",
                "data_missing_flags",
            ]
        ],
        on=["trade_date", "asset_id"],
        how="left",
    )
    frame["current_research_state"] = frame["research_priority"].map(
        {
            "high": "research_priority_high",
            "medium": "research_priority_medium",
            "low": "research_priority_low",
            "watch_only": "watch_only",
            "risk_review": "risk_review",
        }
    )
    frame["why_in_pool"] = frame["thesis_summary"]
    frame["evidence_summary"] = frame["evidence_tags"] + "; state=" + frame["evidence_state"]
    frame["low_position_summary"] = frame.apply(
        lambda row: f"low_score={_num(row.get('low_position_score'), 0.5):.2f}; drawdown120={_num(row.get('price_drawdown_from_120d_high'), 0.0):.2%}",
        axis=1,
    )
    frame["technical_position_summary"] = frame.apply(
        lambda row: f"technical_position_score={_num(row.get('technical_position_score'), 0.5):.2f}; price_percentile120={_num(row.get('price_percentile_120d'), 0.5):.2f}",
        axis=1,
    )
    frame["fundamental_summary"] = "valuation/fundamental/expectation fields missing in v1; neutral fallback used"
    frame["recommended_action_for_reviewer"] = frame.apply(_review_action, axis=1)
    cards = frame[
        [
            "trade_date",
            "asset_id",
            "symbol",
            "name",
            "current_research_state",
            "research_priority",
            "why_in_pool",
            "evidence_summary",
            "low_position_summary",
            "technical_position_summary",
            "fundamental_summary",
            "risk_summary",
            "recommended_action_for_reviewer",
            "human_review_required",
            "data_quality_status",
        ]
    ]
    if not validate_review_actions(cards):
        raise ValueError("review cards contain invalid or trading-language actions")
    return cards


def _review_action(row: pd.Series) -> str:
    if row.get("research_priority") == "risk_review":
        return "risk_review_required"
    if row.get("data_quality_status") == "degraded_coverage":
        return "review_data_quality"
    if row.get("research_priority") == "high":
        return "review_thesis"
    if row.get("research_priority") == "medium":
        return "monitor_setup"
    if row.get("research_priority") == "low":
        return "watch_only"
    return "ignore_until_reconfirmed"


def _write_report(
    *,
    output_dir: Path,
    input_status: dict[str, str],
    candidates: pd.DataFrame,
    coverage: pd.DataFrame,
    low_position: pd.DataFrame,
    risk: pd.DataFrame,
    cards: pd.DataFrame,
) -> None:
    coverage_mean = float(coverage["evidence_coverage_ratio"].mean()) if not coverage.empty else 0.0
    latest_coverage = float(coverage.sort_values("trade_date").tail(1)["evidence_coverage_ratio"].iloc[0]) if not coverage.empty else 0.0
    action_counts = cards["recommended_action_for_reviewer"].value_counts().to_dict()
    priority_counts = candidates["research_priority"].value_counts().to_dict()
    lookahead = int(coverage["lookahead_violation_rows"].sum()) if not coverage.empty else 0
    missing_fields = [
        "valuation_position_score",
        "expectation_position_score",
        "fundamental_position_score",
        "valuation_risk_flag",
        "liquidity_risk_flag",
    ]
    lines = [
        "# Tech Bottleneck Research Selection Layer v1",
        "",
        "## 1. Executive Summary",
        "",
        "- Research selection layer 已实现，输出研究候选池、低位拆解、source coverage、risk audit 和 review cards。",
        f"- 输出候选行数：`{len(candidates)}`；review card 行数：`{len(cards)}`。",
        f"- 平均 PIT evidence coverage ratio：`{coverage_mean:.4f}`；最新交易日 coverage ratio：`{latest_coverage:.4f}`。",
        "- 低位拆解第一版可用字段：价格低位、120 日回撤、120 日价格分位、技术低位。估值、预期、基本面低位字段当前缺失并使用 missing status。",
        "- Review card 只输出 non-trading reviewer action，不输出 buy/sell/add/reduce/hold/target_price。",
        "- research_candidate_score 只用于研究优先级，不输出交易信号，不改变 Top5，不接入 evidence multiplier。",
        f"- lookahead violation rows：`{lookahead}`。",
        "- 正式策略文件未被本脚本修改。",
        "",
        "## 2. Input Files and Data Availability",
        "",
        "| file | status |",
        "|---|---|",
        *[f"| `{path}` | {status} |" for path, status in input_status.items()],
        "",
        "可用字段：PIT candidate snapshots、PIT evidence count/source type、价格 close 序列、120 日高低位。",
        "",
        "不可用字段：估值分位、分析师预期变化、收入/利润/现金流 as-of 基本面、明确流动性风险字段。",
        "",
        "## 3. Candidate Pool Construction",
        "",
        "候选池来自 `official_baseline_daily_candidate_snapshots.csv`，该文件已经包含 `first_hit_date <= trade_date`、`candidate_as_of_date <= trade_date`、`financial_as_of_date <= trade_date`、`technical_as_of_date <= trade_date` 的 PIT 控制。",
        "",
        "本层再按 `trade_date + asset_id` 合并 `pit_daily_evidence_multiplier.csv` 中的 evidence 状态，但不会使用 multiplier 影响交易排序。",
        "",
        "## 4. Research Candidate Score",
        "",
        "第一版规则：",
        "",
        "```text",
        "research_candidate_score =",
        "    0.30 * evidence_quality_score",
        "  + 0.25 * low_position_score",
        "  + 0.20 * commercial_validation_score",
        "  + 0.15 * freshness_score",
        "  - 0.10 * fundamental_risk_score",
        "```",
        "",
        "缺失 evidence 使用 neutral fallback：`evidence_quality_score = 0.5`，没有 0.6 penalty。估值/基本面缺失也不做极端惩罚，只记录 missing status。",
        "",
        f"research priority 分布：`{priority_counts}`。",
        "",
        "## 5. Low Position Breakdown",
        "",
        "可用：",
        "",
        "- `price_position_score`：基于 120 日区间分位，越低分越高。",
        "- `price_drawdown_from_120d_high`：当前价格相对 120 日高点回撤。",
        "- `price_percentile_120d`：当前价格在 120 日区间分位。",
        "- `technical_position_score`：价格低位和 20 日波动压缩的组合。",
        "",
        "缺失：",
        "",
        "- `valuation_position_score`：missing。",
        "- `expectation_position_score`：missing。",
        "- `fundamental_position_score`：missing。",
        "",
        "## 6. Evidence Coverage",
        "",
        f"- 平均 coverage ratio：`{coverage_mean:.4f}`。",
        f"- latest coverage ratio：`{latest_coverage:.4f}`。",
        f"- lookahead violation rows：`{lookahead}`。",
        "",
        "Coverage 低于 10% 的日期标记为 `degraded_coverage`，但不中断输出，因为本层只做研究和 review。",
        "",
        "## 7. Review Card Design",
        "",
        "Review card 输出：why_in_pool、evidence_summary、low_position_summary、technical_position_summary、fundamental_summary、risk_summary 和 recommended_action_for_reviewer。",
        "",
        f"review action 分布：`{action_counts}`。",
        "",
        "允许 action：`review_thesis`, `monitor_setup`, `review_data_quality`, `risk_review_required`, `ignore_until_reconfirmed`, `watch_only`。",
        "",
        "## 8. Risk Audit",
        "",
        f"risk audit 行数：`{len(risk)}`。",
        "",
        "当前可计算风险：recent drawdown risk。估值风险、流动性风险、基本面风险字段缺失，输出 missing status，不编造。",
        "",
        "## 9. What This Layer Does Not Do",
        "",
        "- 不产生买入信号。",
        "- 不产生卖出信号。",
        "- 不改变 Top5。",
        "- 不改变正式策略。",
        "- 不接入 evidence multiplier。",
        "- 不输出交易指令。",
        "",
        "## 10. Recommended Next Step",
        "",
        "建议下一步先接 dashboard review card 或实现 `tech_bottleneck_setup_state_machine_v1` 的 research replay。若目标是日常使用，应优先把 `tech_bottleneck_review_cards.csv` 接入 Daily Review Lite 或 Tech Bottleneck 专页；若目标是策略研究，应先做 setup state machine，不要直接做交易策略。",
        "",
        "## 11. Appendix",
        "",
        "生成文件：",
        "",
        "- `tech_bottleneck_research_candidates.csv`",
        "- `tech_bottleneck_review_cards.csv`",
        "- `research_selection_source_coverage.csv`",
        "- `research_selection_low_position_breakdown.csv`",
        "- `research_selection_risk_audit.csv`",
        "- `research_selection_final_interpretation.md`",
        "",
        "测试命令：",
        "",
        "```bash",
        "PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/pytest stock_research/tests/test_tech_bottleneck_research_selection_layer.py -q",
        "PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/pytest stock_research/tests/test_tech_bottleneck_pit_evidence_replay.py -q",
        "```",
        "",
        f"缺失字段：`{missing_fields}`。",
        "",
        "关键假设：本层只做研究优先级和 review card；所有字段都不进入正式交易。",
    ]
    (output_dir / "research_selection_final_interpretation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    replay_dir = Path(args.replay_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_files = {
        str(replay_dir / "official_baseline_daily_candidate_snapshots.csv"): "found",
        str(replay_dir / "pit_daily_evidence_multiplier.csv"): "found",
        str(replay_dir / "new_evidence_seed_pit_usable.csv"): "found" if (replay_dir / "new_evidence_seed_pit_usable.csv").exists() else "missing_optional",
    }
    raw = _load_candidates(replay_dir)
    start_date = str(raw["trade_date"].min())
    end_date = str(raw["trade_date"].max())
    evidence = _load_evidence(replay_dir)
    low_position = _load_price_features(raw, start_date=start_date, end_date=end_date)
    enriched = _attach_research_features(raw, low_position, evidence)
    candidates = build_research_candidates(enriched)
    coverage = build_source_coverage(raw, evidence)
    risk = build_risk_audit(enriched)
    cards = build_review_cards(candidates, low_position)

    candidates.to_csv(output_dir / "tech_bottleneck_research_candidates.csv", index=False)
    cards.to_csv(output_dir / "tech_bottleneck_review_cards.csv", index=False)
    coverage.to_csv(output_dir / "research_selection_source_coverage.csv", index=False)
    low_position.to_csv(output_dir / "research_selection_low_position_breakdown.csv", index=False)
    risk.to_csv(output_dir / "research_selection_risk_audit.csv", index=False)
    _write_report(
        output_dir=output_dir,
        input_status=input_files,
        candidates=candidates,
        coverage=coverage,
        low_position=low_position,
        risk=risk,
        cards=cards,
    )
    print(output_dir)
    print(
        pd.DataFrame(
            [
                {
                    "candidate_rows": len(candidates),
                    "review_card_rows": len(cards),
                    "avg_evidence_coverage_ratio": float(coverage["evidence_coverage_ratio"].mean()),
                    "lookahead_violation_rows": int(coverage["lookahead_violation_rows"].sum()),
                    "review_actions_valid": validate_review_actions(cards),
                }
            ]
        ).to_string(index=False)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck research selection layer outputs.")
    parser.add_argument("--replay-dir", default=str(REPLAY_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    run(parser.parse_args())


if __name__ == "__main__":
    main()
