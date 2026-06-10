from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


@dataclass(frozen=True)
class StrategyBacktestParams:
    start_date: str
    end_date: str
    score_version: str = "manual_v1"
    adjust_type: str = "hfq"


class StrategyBacktestAdapter(Protocol):
    strategy_id: str

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        ...


def normalize_strategy_scores(frame: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError(f"no {strategy_id} strategy scores found for selected range")
    required = {"trade_date", "asset_id", "score_total"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{strategy_id} scores missing columns: {', '.join(sorted(missing))}")

    normalized = frame.copy()
    normalized["score_total"] = pd.to_numeric(normalized["score_total"], errors="coerce")
    normalized = normalized.dropna(subset=["trade_date", "asset_id", "score_total"])
    if normalized.empty:
        raise ValueError(f"no {strategy_id} strategy scores found for selected range")

    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"]).dt.strftime("%Y-%m-%d")
    normalized["asset_id"] = normalized["asset_id"].astype(str)

    normalized = normalized.sort_values(
        ["trade_date", "score_total", "asset_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    normalized["rank"] = normalized.groupby("trade_date").cumcount() + 1
    normalized["strategy_id"] = strategy_id
    if "score_components" not in normalized.columns:
        normalized["score_components"] = [{} for _ in range(len(normalized))]
    if "eligibility" not in normalized.columns:
        normalized["eligibility"] = True
    normalized["eligibility"] = normalized["eligibility"].map(lambda value: bool(value)).astype(object)
    if "eligibility_reason" not in normalized.columns:
        normalized["eligibility_reason"] = "eligible"
    if "exposure_scale" not in normalized.columns:
        normalized["exposure_scale"] = 1.0
    return normalized[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score_total",
            "score_components",
            "strategy_id",
            "eligibility",
            "eligibility_reason",
            "exposure_scale",
        ]
    ]


def _fetch_frame(sql: str, params: list[object], service: str = SETTINGS.research_service) -> pd.DataFrame:
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return pd.DataFrame(rows)


def _num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def build_manual_v1_scores_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    strategy_id = "manual_v1_topn_rotation"
    if frame is None or frame.empty:
        return normalize_strategy_scores(frame, strategy_id=strategy_id)

    manual = _deduplicate_manual_scores(frame, strategy_id=strategy_id)
    normalized = normalize_strategy_scores(
        manual.copy(),
        strategy_id=strategy_id,
    )
    if "rank" not in manual.columns:
        return normalized

    manual_ranks = manual[["trade_date", "asset_id", "rank", "score_total"]].copy()
    manual_ranks["score_total"] = pd.to_numeric(manual_ranks["score_total"], errors="coerce")
    manual_ranks["rank"] = pd.to_numeric(manual_ranks["rank"], errors="coerce")
    manual_ranks = manual_ranks.dropna(subset=["trade_date", "asset_id", "rank", "score_total"])
    manual_ranks["trade_date"] = pd.to_datetime(manual_ranks["trade_date"]).dt.strftime("%Y-%m-%d")
    manual_ranks["asset_id"] = manual_ranks["asset_id"].astype(str)

    normalized = normalized.drop(columns=["rank"]).merge(
        manual_ranks[["trade_date", "asset_id", "rank"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    normalized = normalized.sort_values(
        ["trade_date", "rank", "asset_id"],
        ascending=[True, True, True],
    ).reset_index(drop=True)
    return normalized[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score_total",
            "score_components",
            "strategy_id",
            "eligibility",
            "eligibility_reason",
            "exposure_scale",
        ]
    ]


def _deduplicate_lhb_frame(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.copy()
    group_keys = ["trade_date", "asset_id"]
    numeric_columns = [
        "lhb_net_buy_ratio",
        "lhb_net_buy_amount",
        "institution_net_buy",
        "repeat_on_list_count_3d",
        "lhb_one_day_pump_risk",
    ]
    bool_columns = ["on_lhb", "lhb_after_reversal"]
    aggregations: dict[str, str] = {}

    for column in numeric_columns:
        if column in grouped.columns:
            grouped[column] = pd.to_numeric(grouped[column], errors="coerce")
            aggregations[column] = "max"
    for column in bool_columns:
        if column in grouped.columns:
            grouped[column] = grouped[column].fillna(False).astype(bool)
            aggregations[column] = "max"

    if not aggregations:
        return grouped[group_keys].drop_duplicates().reset_index(drop=True)
    return grouped.groupby(group_keys, as_index=False, sort=False).agg(aggregations)


def _deduplicate_technical_frame(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.copy()
    group_keys = ["trade_date", "asset_id"]
    aggregations: dict[str, str] = {}
    for column in ["amount_vs_20d", "high_to_close_drawdown"]:
        if column in grouped.columns:
            grouped[column] = pd.to_numeric(grouped[column], errors="coerce")
            aggregations[column] = "max"

    if not aggregations:
        return grouped[group_keys].drop_duplicates().reset_index(drop=True)
    return grouped.groupby(group_keys, as_index=False, sort=False).agg(aggregations)


def build_lhb_shortline_scores_from_frames(lhb: pd.DataFrame, technical: pd.DataFrame | None = None) -> pd.DataFrame:
    if lhb is None or lhb.empty:
        return normalize_strategy_scores(pd.DataFrame(), strategy_id="lhb_shortline")
    frame = _deduplicate_lhb_frame(lhb)
    if technical is not None and not technical.empty:
        technical = _deduplicate_technical_frame(
            technical[["trade_date", "asset_id", "amount_vs_20d", "high_to_close_drawdown"]]
        )
        frame = frame.merge(
            technical,
            on=["trade_date", "asset_id"],
            how="left",
        )
    net_ratio = _num(frame.get("lhb_net_buy_ratio", pd.Series(index=frame.index)))
    net_amount = _num(frame.get("lhb_net_buy_amount", pd.Series(index=frame.index))) / 100_000_000.0
    inst_buy = _num(frame.get("institution_net_buy", pd.Series(index=frame.index))) / 100_000_000.0
    repeat = _num(frame.get("repeat_on_list_count_3d", pd.Series(index=frame.index)))
    reversal = _bool(frame.get("lhb_after_reversal", pd.Series(index=frame.index))).astype(float)
    amount_confirmation = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 3)
    pump_risk = _num(frame.get("lhb_one_day_pump_risk", pd.Series(index=frame.index)))
    high_drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index)))

    frame["score_total"] = (
        50.0
        + net_ratio.clip(-1, 1) * 35.0
        + net_amount.clip(-1, 3) * 8.0
        + inst_buy.clip(-1, 2) * 6.0
        + repeat.clip(0, 5) * 2.5
        + reversal * 6.0
        + amount_confirmation * 2.0
        - pump_risk.clip(0, 1) * 25.0
        - high_drawdown.clip(0, 1) * 40.0
    )
    eligible = _bool(frame.get("on_lhb", pd.Series(index=frame.index))) & (pump_risk < 0.75)
    frame["eligibility"] = eligible.map(lambda value: bool(value)).astype(object)
    frame["eligibility_reason"] = eligible.map({True: "lhb_support", False: "pump_risk_or_missing_lhb"})
    frame["score_components"] = [
        {
            "lhb_net_buy_ratio": float(net_ratio.iloc[index]),
            "lhb_net_buy_amount": float(net_amount.iloc[index]),
            "institution_net_buy": float(inst_buy.iloc[index]),
            "lhb_one_day_pump_risk": float(pump_risk.iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="lhb_shortline")


def _factor_pivot(factors: pd.DataFrame | None) -> pd.DataFrame:
    if factors is None or factors.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id"])
    pivot = factors.pivot_table(
        index=["trade_date", "asset_id"],
        columns="factor_name",
        values="factor_value",
        aggfunc="max",
    ).reset_index()
    pivot.columns = [str(column) for column in pivot.columns]
    return pivot


def _deduplicate_manual_scores(frame: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return normalize_strategy_scores(pd.DataFrame(), strategy_id=strategy_id)
    required = {"trade_date", "asset_id", "score_total"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{strategy_id} scores missing columns: {', '.join(sorted(missing))}")

    grouped = frame.copy()
    grouped["score_total"] = pd.to_numeric(grouped["score_total"], errors="coerce")
    aggregations = {"score_total": "max"}
    if "rank" in grouped.columns:
        grouped["rank"] = pd.to_numeric(grouped["rank"], errors="coerce")
        aggregations["rank"] = "min"
    grouped = grouped.dropna(subset=["trade_date", "asset_id", "score_total"])
    if grouped.empty:
        return normalize_strategy_scores(pd.DataFrame(), strategy_id=strategy_id)
    return grouped.groupby(["trade_date", "asset_id"], as_index=False, sort=False).agg(aggregations)


def _deduplicate_feature_frame(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return frame
    group_keys = ["trade_date", "asset_id"]
    grouped = frame.copy()
    aggregations: dict[str, str] = {}
    for column in grouped.columns:
        if column in group_keys:
            continue
        grouped[column] = pd.to_numeric(grouped[column], errors="coerce")
        aggregations[column] = "max"

    if not aggregations:
        return grouped[group_keys].drop_duplicates().reset_index(drop=True)
    return grouped.groupby(group_keys, as_index=False, sort=False).agg(aggregations)


def _merge_manual_technical_factors(
    manual: pd.DataFrame,
    technical: pd.DataFrame | None,
    strategy_id: str,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    manual = _deduplicate_manual_scores(manual, strategy_id)
    base = manual[["trade_date", "asset_id", "score_total"]].copy()
    base = base.rename(columns={"score_total": "manual_score"})
    technical = _deduplicate_feature_frame(technical)
    if technical is not None and not technical.empty:
        base = base.merge(technical, on=["trade_date", "asset_id"], how="left")
    factor_wide = _factor_pivot(factors)
    if not factor_wide.empty:
        base = base.merge(factor_wide, on=["trade_date", "asset_id"], how="left")
    return base


def build_mid_trend_scores_from_frames(
    manual: pd.DataFrame,
    technical: pd.DataFrame | None,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical, strategy_id="mid_trend", factors=factors)
    trend = _num(frame.get("trend_r2_20", pd.Series(index=frame.index))).clip(0, 1)
    ret_20d = _num(frame.get("ret_20d", pd.Series(index=frame.index))).clip(-0.3, 0.5)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 3)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    frame["score_total"] = (
        manual_score * 0.35
        + trend * 35.0
        + ret_20d * 80.0
        + amount * 3.0
        - drawdown * 45.0
    )
    frame["eligibility"] = (trend >= 0.30) | (ret_20d > 0)
    frame["eligibility_reason"] = frame["eligibility"].map({True: "trend_candidate", False: "weak_trend"})
    frame["score_components"] = [
        {
            "manual_score": float(manual_score.iloc[index]),
            "trend_r2_20": float(trend.iloc[index]),
            "ret_20d": float(ret_20d.iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="mid_trend")


def build_tech_bottleneck_scores_from_frames(manual: pd.DataFrame, technical: pd.DataFrame | None) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical, strategy_id="tech_bottleneck")
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    ret_20d = _num(frame.get("ret_20d", pd.Series(index=frame.index))).clip(-0.3, 0.5)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 4)
    close_position = _num(frame.get("close_position_in_day", pd.Series(index=frame.index)), 0.5).clip(0, 1)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    frame["score_total"] = (
        manual_score * 0.20
        + ret_20d * 95.0
        + amount * 8.0
        + close_position * 18.0
        - drawdown * 35.0
    )
    frame["eligibility"] = amount >= 0.5
    frame["eligibility_reason"] = frame["eligibility"].map({True: "technical_confirmation", False: "weak_volume_price"})
    frame["score_components"] = [
        {
            "manual_score": float(manual_score.iloc[index]),
            "ret_20d": float(ret_20d.iloc[index]),
            "amount_vs_20d": float(amount.iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="tech_bottleneck")


def build_position_control_scores_from_frames(manual: pd.DataFrame, technical: pd.DataFrame | None) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical, strategy_id="position_control")
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 5)
    risk_penalty = drawdown * 120.0 + (amount - 2.5).clip(lower=0) * 8.0
    frame["score_total"] = manual_score - risk_penalty
    # Current TopN execution is equal-weighted, so score_total carries the risk-control effect.
    # exposure_scale is retained as metadata for later engine-level position scaling.
    exposure_scale = (1.0 - drawdown * 2.0).clip(lower=0.25, upper=1.0)
    frame["exposure_scale"] = exposure_scale.mask(drawdown <= 0.02, 1.0)
    frame["eligibility"] = frame["exposure_scale"] >= 0.25
    frame["eligibility_reason"] = frame["eligibility"].map({True: "risk_scaled", False: "risk_excluded"})
    frame["score_components"] = [
        {
            "manual_score": float(manual_score.iloc[index]),
            "risk_penalty": float(risk_penalty.iloc[index]),
            "exposure_scale": float(frame["exposure_scale"].iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="position_control")


def _load_manual_scores(params: StrategyBacktestParams) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT trade_date, asset_id, rank, score_total
        FROM factor.stock_score_daily
        WHERE score_version = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, rank, asset_id
        """,
        [params.score_version, params.start_date, params.end_date],
    )


def _load_technical_features(params: StrategyBacktestParams) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT
            trade_date,
            asset_id,
            ret_20d,
            amount_vs_20d,
            close_position_in_day,
            high_to_close_drawdown
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        """,
        [params.adjust_type, params.start_date, params.end_date],
    )


def _load_factor_values(params: StrategyBacktestParams, factor_names: list[str]) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT trade_date, asset_id, factor_name, factor_value
        FROM factor.factor_daily
        WHERE trade_date BETWEEN %s AND %s
          AND factor_name = ANY(%s)
        """,
        [params.start_date, params.end_date, factor_names],
    )


def _filter_eligible_scores(scores: pd.DataFrame) -> pd.DataFrame:
    filtered = scores[scores["eligibility"].map(bool)].reset_index(drop=True).copy()
    filtered["eligibility"] = filtered["eligibility"].map(lambda value: bool(value)).astype(object)
    return filtered


class ManualV1TopNAdapter:
    strategy_id = "manual_v1_topn_rotation"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        return build_manual_v1_scores_from_frame(_load_manual_scores(params))


class LHBShortlineAdapter:
    strategy_id = "lhb_shortline"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        lhb_sql = """
        SELECT
            l.trade_date,
            COALESCE(a.asset_id, l.ts_code) AS asset_id,
            l.on_lhb,
            l.lhb_net_buy_ratio,
            l.lhb_net_buy_amount,
            l.institution_net_buy,
            l.repeat_on_list_count_3d,
            l.lhb_after_reversal,
            l.lhb_one_day_pump_risk
        FROM factor.lhb_event_features_daily l
        LEFT JOIN core.asset_master a ON a.ts_code = l.ts_code
        WHERE l.trade_date BETWEEN %s AND %s
        """
        technical_sql = """
        SELECT trade_date, asset_id, amount_vs_20d, high_to_close_drawdown
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        """
        lhb = _fetch_frame(lhb_sql, [params.start_date, params.end_date])
        technical = _fetch_frame(technical_sql, [params.adjust_type, params.start_date, params.end_date])
        scores = build_lhb_shortline_scores_from_frames(lhb, technical)
        return _filter_eligible_scores(scores)


class MidTrendAdapter:
    strategy_id = "mid_trend"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        scores = build_mid_trend_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
            _load_factor_values(params, ["trend_r2_20", "ma20_slope", "ma60_slope"]),
        )
        return _filter_eligible_scores(scores)


class TechBottleneckAdapter:
    strategy_id = "tech_bottleneck"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        scores = build_tech_bottleneck_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
        )
        return _filter_eligible_scores(scores)


class PositionControlAdapter:
    strategy_id = "position_control"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        scores = build_position_control_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
        )
        return _filter_eligible_scores(scores)


STRATEGY_BACKTEST_REGISTRY: dict[str, StrategyBacktestAdapter] = {
    "manual_v1_topn_rotation": ManualV1TopNAdapter(),
    "lhb_shortline": LHBShortlineAdapter(),
    "mid_trend": MidTrendAdapter(),
    "tech_bottleneck": TechBottleneckAdapter(),
    "position_control": PositionControlAdapter(),
}
