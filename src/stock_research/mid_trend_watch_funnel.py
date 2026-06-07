from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


MID_TREND_LAYERS = [
    "stable_trend_watch",
    "mainline_momentum_watch",
    "pullback_reacceleration_watch",
    "high_elasticity_watch",
]
METRICS = [
    "future_20d_return",
    "future_30d_return",
    "future_40d_return",
    "future_60d_return",
    "future_60d_max_drawdown",
    "max_return_within_60d",
    "hit_double_within_60d",
]
DEFAULT_CONTEXT_DETAIL_PATH = Path("outputs/research/trend_discovery_template_detail.csv")
DEFAULT_MARKET_REGIME_PATH = Path("outputs/research/market_regime_diagnostics.csv")
DEFAULT_INDUSTRY_MAINLINE_PATH = Path("outputs/research/industry_mainline_regime_diagnostics.csv")
CONTEXT_COLUMNS = [
    "industry_name",
    "market_regime",
    "mainline_context",
    "mainline_status",
    "industry_mainline_score_v1",
]


def run_mid_trend_watch_funnel(
    *,
    discovery_pool_path: str | Path,
    output_dir: str | Path,
    top50_size: int = 50,
    top10_size: int = 10,
    trade_date: str | None = None,
    context_detail_path: str | Path | None = DEFAULT_CONTEXT_DETAIL_PATH,
    market_regime_path: str | Path | None = DEFAULT_MARKET_REGIME_PATH,
    industry_mainline_path: str | Path | None = DEFAULT_INDUSTRY_MAINLINE_PATH,
    research_service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    detail = pd.read_csv(discovery_pool_path, low_memory=False)
    return build_mid_trend_watch_funnel_from_frames(
        discovery_pool_detail=detail,
        output_dir=output_dir,
        top50_size=top50_size,
        top10_size=top10_size,
        trade_date=trade_date,
        context_detail=_read_optional_csv(context_detail_path),
        market_regime=_read_optional_csv(market_regime_path),
        industry_mainline=_read_optional_csv(industry_mainline_path),
        industry_membership=_load_industry_membership_context(detail, service=research_service),
    )


def build_mid_trend_watch_funnel_from_frames(
    *,
    discovery_pool_detail: pd.DataFrame,
    context_detail: pd.DataFrame | None = None,
    market_regime: pd.DataFrame | None = None,
    industry_mainline: pd.DataFrame | None = None,
    industry_membership: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
    top50_size: int = 50,
    top10_size: int = 10,
    trade_date: str | None = None,
) -> dict[str, Any]:
    detail = _build_detail(discovery_pool_detail, trade_date=trade_date)
    detail = _enrich_context(
        detail,
        context_detail=context_detail,
        market_regime=market_regime,
        industry_mainline=industry_mainline,
        industry_membership=industry_membership,
    )
    layer_effectiveness = _layer_effectiveness(detail)
    top50 = _select_by_trade_date(detail, size=top50_size, target="top50")
    top10 = _select_by_trade_date(top50, size=top10_size, target="top10")
    pool_effectiveness = _pool_effectiveness(detail, top50, top10)
    report = _render_report(layer_effectiveness, pool_effectiveness, top50, top10)
    result: dict[str, Any] = {
        "detail": detail,
        "layer_effectiveness": layer_effectiveness,
        "pool_effectiveness": pool_effectiveness,
        "top50": top50,
        "top10": top10,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "mid_trend_watch_funnel_detail.csv",
            "layer_effectiveness": output / "mid_trend_watch_funnel_layer_effectiveness.csv",
            "pool_effectiveness": output / "mid_trend_watch_pool_effectiveness.csv",
            "top50": output / "mid_trend_watch_top50.csv",
            "top10": output / "mid_trend_watch_top10.csv",
            "report": output / "mid_trend_watch_funnel_report.md",
        }
        detail.to_csv(paths["detail"], index=False)
        layer_effectiveness.to_csv(paths["layer_effectiveness"], index=False)
        pool_effectiveness.to_csv(paths["pool_effectiveness"], index=False)
        top50.to_csv(paths["top50"], index=False)
        top10.to_csv(paths["top10"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_detail(frame: pd.DataFrame, *, trade_date: str | None) -> pd.DataFrame:
    detail = frame.copy()
    if detail.empty:
        return _empty_detail()
    detail["trade_date"] = pd.to_datetime(detail["trade_date"], errors="coerce")
    if trade_date:
        detail = detail[detail["trade_date"].eq(pd.to_datetime(trade_date))].copy()
    for column in ["asset_id", "ts_code", "stock_name"]:
        if column not in detail.columns:
            detail[column] = ""
    if "score_rank" not in detail.columns:
        detail["score_rank"] = detail.get("rank", np.nan)
    detail["score_rank"] = pd.to_numeric(detail["score_rank"], errors="coerce")
    detail["score_components"] = detail.get("score_components", pd.Series([{}] * len(detail))).map(_parse_components)
    component_frame = pd.DataFrame([_component_values(value) for value in detail["score_components"]], index=detail.index)
    detail = pd.concat([detail, component_frame], axis=1)
    detail["mid_trend_layer"] = detail.apply(_classify_layer, axis=1)
    detail["mid_trend_funnel_score"] = detail.apply(_funnel_score, axis=1)
    detail["evaluation_horizon"] = "20/30/40/60d"
    detail["observation_note"] = detail["mid_trend_layer"].map(_observation_note)
    detail["invalid_condition"] = detail["mid_trend_layer"].map(_invalid_condition)
    for metric in METRICS:
        if metric not in detail.columns:
            detail[metric] = np.nan
        detail[metric] = pd.to_numeric(detail[metric], errors="coerce")
    detail["hit_double_within_60d"] = detail["hit_double_within_60d"].fillna(0).astype(bool)
    return detail.sort_values(["trade_date", "mid_trend_funnel_score", "score_rank"], ascending=[True, False, True])


def _enrich_context(
    detail: pd.DataFrame,
    *,
    context_detail: pd.DataFrame | None,
    market_regime: pd.DataFrame | None,
    industry_mainline: pd.DataFrame | None,
    industry_membership: pd.DataFrame | None,
) -> pd.DataFrame:
    if detail.empty:
        return _ensure_context_columns(detail.copy())

    enriched = detail.copy()
    enriched["trade_date"] = pd.to_datetime(enriched["trade_date"], errors="coerce")
    enriched["asset_id"] = enriched["asset_id"].astype(str)

    context = _normalize_context_detail(context_detail)
    if not context.empty:
        enriched = enriched.merge(context, on=["trade_date", "asset_id"], how="left", suffixes=("", "_context"))
        for column in ["industry_name", "market_regime", "mainline_context"]:
            context_column = f"{column}_context"
            if context_column in enriched.columns:
                if column in enriched.columns:
                    enriched[column] = enriched[column].where(_has_value(enriched[column]), enriched[context_column])
                else:
                    enriched[column] = enriched[context_column]
                enriched = enriched.drop(columns=[context_column])

    membership = _normalize_industry_membership(industry_membership)
    if not membership.empty:
        membership_match = enriched[["trade_date", "asset_id"]].merge(membership, on="asset_id", how="left")
        active = membership_match[
            membership_match["start_date"].le(membership_match["trade_date"])
            & (
                membership_match["end_date"].isna()
                | membership_match["end_date"].ge(membership_match["trade_date"])
            )
        ].copy()
        active = active.sort_values(["trade_date", "asset_id", "start_date"]).drop_duplicates(
            ["trade_date", "asset_id"],
            keep="last",
        )
        if not active.empty:
            enriched = enriched.merge(
                active[["trade_date", "asset_id", "industry_name"]],
                on=["trade_date", "asset_id"],
                how="left",
                suffixes=("", "_membership"),
            )
            if "industry_name_membership" in enriched.columns:
                enriched["industry_name"] = enriched.get("industry_name", pd.Series(index=enriched.index)).where(
                    _has_value(enriched.get("industry_name", pd.Series(index=enriched.index))),
                    enriched["industry_name_membership"],
                )
                enriched = enriched.drop(columns=["industry_name_membership"])

    regimes = _normalize_market_regime(market_regime)
    if not regimes.empty:
        enriched = enriched.merge(regimes, on="trade_date", how="left", suffixes=("", "_regime"))
        if "market_regime_regime" in enriched.columns:
            existing_regime = enriched.get("market_regime", pd.Series(index=enriched.index))
            enriched["market_regime"] = enriched["market_regime_regime"].where(
                _has_value(enriched["market_regime_regime"]),
                existing_regime,
            )
            enriched = enriched.drop(columns=["market_regime_regime"])

    mainline = _normalize_industry_mainline(industry_mainline)
    if not mainline.empty:
        if "industry_name" not in enriched.columns:
            enriched["industry_name"] = ""
        enriched = enriched.merge(mainline, on=["trade_date", "industry_name"], how="left", suffixes=("", "_mainline"))

    enriched = _ensure_context_columns(enriched)
    enriched["market_regime"] = enriched["market_regime"].fillna("unknown").replace("", "unknown")
    enriched["industry_name"] = enriched["industry_name"].fillna("unknown").replace("", "unknown")
    enriched["mainline_context"] = enriched["mainline_context"].fillna("unknown").replace("", "unknown")
    enriched["mainline_status"] = enriched["mainline_status"].fillna(enriched["mainline_context"]).replace("", "unknown")
    enriched["industry_mainline_score_v1"] = pd.to_numeric(enriched["industry_mainline_score_v1"], errors="coerce")
    return enriched


def _normalize_context_detail(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["trade_date", "asset_id", "industry_name", "market_regime", "mainline_context"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    context = frame.copy()
    if "trade_date" not in context.columns or "asset_id" not in context.columns:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in context.columns:
            context[column] = np.nan
    context["trade_date"] = pd.to_datetime(context["trade_date"], errors="coerce")
    context["asset_id"] = context["asset_id"].astype(str)
    return (
        context[columns]
        .dropna(subset=["trade_date", "asset_id"])
        .drop_duplicates(subset=["trade_date", "asset_id"], keep="first")
    )


def _normalize_market_regime(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty or "market_regime" not in frame.columns:
        return pd.DataFrame(columns=["trade_date", "market_regime"])
    regimes = frame.copy()
    date_column = "trade_date" if "trade_date" in regimes.columns else "rebalance_date" if "rebalance_date" in regimes.columns else None
    if date_column is None:
        return pd.DataFrame(columns=["trade_date", "market_regime"])
    regimes["trade_date"] = pd.to_datetime(regimes[date_column], errors="coerce")
    return regimes[["trade_date", "market_regime"]].dropna(subset=["trade_date"]).drop_duplicates("trade_date", keep="first")


def _normalize_industry_membership(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["asset_id", "industry_name", "start_date", "end_date"]
    if frame is None or frame.empty or "asset_id" not in frame.columns or "industry_name" not in frame.columns:
        return pd.DataFrame(columns=columns)
    membership = frame.copy()
    if "start_date" not in membership.columns:
        membership["start_date"] = pd.Timestamp("1900-01-01")
    if "end_date" not in membership.columns:
        membership["end_date"] = pd.NaT
    membership["asset_id"] = membership["asset_id"].astype(str)
    membership["start_date"] = pd.to_datetime(membership["start_date"], errors="coerce").fillna(pd.Timestamp("1900-01-01"))
    membership["end_date"] = pd.to_datetime(membership["end_date"], errors="coerce")
    return membership[columns].dropna(subset=["asset_id", "industry_name"])


def _normalize_industry_mainline(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["trade_date", "industry_name", "industry_mainline_score_v1", "mainline_status"]
    if frame is None or frame.empty or "industry_name" not in frame.columns:
        return pd.DataFrame(columns=columns)
    mainline = frame.copy()
    date_column = "trade_date" if "trade_date" in mainline.columns else "rebalance_date" if "rebalance_date" in mainline.columns else None
    if date_column is None:
        return pd.DataFrame(columns=columns)
    mainline["trade_date"] = pd.to_datetime(mainline[date_column], errors="coerce")
    if "industry_mainline_score_v1" not in mainline.columns:
        mainline["industry_mainline_score_v1"] = np.nan
    if "mainline_status" not in mainline.columns:
        mainline["mainline_status"] = mainline.get("mainline_tag", np.nan)
    return (
        mainline[columns]
        .dropna(subset=["trade_date", "industry_name"])
        .drop_duplicates(subset=["trade_date", "industry_name"], keep="first")
    )


def _ensure_context_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in CONTEXT_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame


def _has_value(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def _read_optional_csv(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    csv_path = Path(path)
    if not csv_path.exists():
        return None
    return pd.read_csv(csv_path, low_memory=False)


def _load_industry_membership_context(
    detail: pd.DataFrame,
    *,
    service: str,
    industry_system: str = "csrc",
    industry_level: int = 1,
) -> pd.DataFrame | None:
    required = {"trade_date", "asset_id"}
    if detail.empty or not required <= set(detail.columns):
        return None
    trade_dates = pd.to_datetime(detail["trade_date"], errors="coerce").dropna()
    asset_ids = sorted(set(detail["asset_id"].dropna().astype(str)))
    if trade_dates.empty or not asset_ids:
        return None
    sql = """
        SELECT asset_id, industry_name, start_date, end_date
        FROM core.industry_membership
        WHERE industry_system = %s
          AND level = %s
          AND asset_id = ANY(%s)
          AND start_date <= %s
          AND (end_date IS NULL OR end_date >= %s)
    """
    params = [
        industry_system,
        industry_level,
        asset_ids,
        trade_dates.max().date(),
        trade_dates.min().date(),
    ]
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, params)
    except Exception:
        return None
    return pd.DataFrame(rows)


def _component_values(components: dict[str, Any]) -> dict[str, float]:
    names = [
        "ret_20_score",
        "ret_60_score",
        "ma20_slope_score",
        "ma60_slope_score",
        "trend_r2_20_score",
        "momentum_20_5_score",
        "sector_ret_20_score",
        "stock_excess_ret_20_score",
        "max_drawdown_20_score",
        "volatility_20_score",
        "atr_pct_score",
        "amount_ratio_5_20_score",
    ]
    return {name: _number(components.get(name)) for name in names}


def _classify_layer(row: pd.Series) -> str:
    hard_risk = _score(row, "max_drawdown_20_score") < 25 or (
        _score(row, "volatility_20_score") < 10 and _score(row, "atr_pct_score") < 10
    )
    if hard_risk:
        return "risk_exclusion_watch"
    if (
        _score(row, "ret_60_score") >= 85
        and _score(row, "ma60_slope_score") >= 80
        and _score(row, "ma20_slope_score") >= 80
        and _score(row, "trend_r2_20_score") >= 80
        and _score(row, "max_drawdown_20_score") >= 70
    ):
        return "stable_trend_watch"
    if (
        _score(row, "sector_ret_20_score") >= 85
        and _score(row, "stock_excess_ret_20_score") >= 85
        and _score(row, "ret_20_score") >= 80
        and _score(row, "max_drawdown_20_score") >= 55
    ):
        return "mainline_momentum_watch"
    if (
        _score(row, "ret_60_score") >= 75
        and _score(row, "momentum_20_5_score") >= 85
        and _score(row, "ma20_slope_score") >= 75
        and _score(row, "max_drawdown_20_score") >= 45
    ):
        return "pullback_reacceleration_watch"
    if _score(row, "ret_20_score") >= 90 and (
        _score(row, "volatility_20_score") <= 25
        or _score(row, "atr_pct_score") <= 25
        or _score(row, "max_drawdown_20_score") <= 55
    ):
        return "high_elasticity_watch"
    return "unclassified_mid_trend_watch"


def _funnel_score(row: pd.Series) -> float:
    weights = {
        "ret_60_score": 0.18,
        "ret_20_score": 0.12,
        "ma60_slope_score": 0.14,
        "ma20_slope_score": 0.12,
        "trend_r2_20_score": 0.12,
        "stock_excess_ret_20_score": 0.12,
        "sector_ret_20_score": 0.10,
        "max_drawdown_20_score": 0.10,
    }
    base = sum(_score(row, name) * weight for name, weight in weights.items())
    layer_bonus = {
        "stable_trend_watch": 8.0,
        "mainline_momentum_watch": 6.0,
        "pullback_reacceleration_watch": 5.0,
        "high_elasticity_watch": 2.0,
        "unclassified_mid_trend_watch": 0.0,
        "risk_exclusion_watch": -30.0,
    }
    return float(base + layer_bonus.get(str(row.get("mid_trend_layer")), 0.0))


def _select_by_trade_date(detail: pd.DataFrame, *, size: int, target: str) -> pd.DataFrame:
    if detail.empty or size <= 0:
        return detail.head(0).copy()
    selected_frames = []
    quota = _layer_quota(size)
    for _, group in detail.groupby("trade_date", sort=True):
        eligible = group[~group["mid_trend_layer"].eq("risk_exclusion_watch")].copy()
        picked_indexes: list[Any] = []
        for layer, layer_quota in quota.items():
            layer_rows = eligible[eligible["mid_trend_layer"].eq(layer)].sort_values(
                ["mid_trend_funnel_score", "score_rank"], ascending=[False, True]
            )
            picked_indexes.extend(layer_rows.head(layer_quota).index.tolist())
        picked = eligible.loc[picked_indexes].drop_duplicates(subset=["trade_date", "asset_id"])
        if len(picked) < size:
            fill = eligible.drop(index=picked.index, errors="ignore").sort_values(
                ["mid_trend_funnel_score", "score_rank"], ascending=[False, True]
            )
            picked = pd.concat([picked, fill.head(size - len(picked))], ignore_index=False)
        picked = picked.sort_values(["mid_trend_funnel_score", "score_rank"], ascending=[False, True]).head(size).copy()
        picked[f"mid_trend_{target}_rank"] = range(1, len(picked) + 1)
        selected_frames.append(picked)
    return pd.concat(selected_frames, ignore_index=True) if selected_frames else detail.head(0).copy()


def _layer_quota(size: int) -> dict[str, int]:
    if size <= 10:
        return {
            "stable_trend_watch": max(1, round(size * 0.30)),
            "mainline_momentum_watch": max(1, round(size * 0.30)),
            "pullback_reacceleration_watch": max(1, round(size * 0.20)),
            "high_elasticity_watch": max(1, size - round(size * 0.80)),
        }
    return {
        "stable_trend_watch": round(size * 0.30),
        "mainline_momentum_watch": round(size * 0.30),
        "pullback_reacceleration_watch": round(size * 0.20),
        "high_elasticity_watch": size - round(size * 0.80),
    }


def _layer_effectiveness(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for layer, group in detail.groupby("mid_trend_layer", sort=True):
        rows.append(_metric_row(group, "mid_trend_layer", layer))
    return pd.DataFrame(rows)


def _pool_effectiveness(detail: pd.DataFrame, top50: pd.DataFrame, top10: pd.DataFrame) -> pd.DataFrame:
    non_risk = detail[~detail["mid_trend_layer"].eq("risk_exclusion_watch")] if not detail.empty else detail
    return pd.DataFrame(
        [
            _metric_row(detail, "pool_name", "mid_trend_top500_all"),
            _metric_row(non_risk, "pool_name", "mid_trend_top500_nonrisk"),
            _metric_row(top50, "pool_name", "mid_trend_top50"),
            _metric_row(top10, "pool_name", "mid_trend_top10"),
        ]
    )


def _metric_row(frame: pd.DataFrame, key_name: str, key_value: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        key_name: key_value,
        "sample_count": int(len(frame)),
        "unique_asset_count": int(frame["asset_id"].nunique()) if "asset_id" in frame.columns else 0,
    }
    for metric in METRICS:
        series = pd.to_numeric(frame.get(metric), errors="coerce")
        if metric == "hit_double_within_60d":
            row[f"{metric}_rate"] = float(series.mean()) if not series.dropna().empty else np.nan
        else:
            row[f"{metric}_mean"] = float(series.mean()) if not series.dropna().empty else np.nan
    return row


def _render_report(
    layer_effectiveness: pd.DataFrame,
    pool_effectiveness: pd.DataFrame,
    top50: pd.DataFrame,
    top10: pd.DataFrame,
) -> str:
    lines = [
        "# Mid Trend Watch Funnel v1",
        "",
        "## 1. Scope",
        "本报告只服务中线趋势观察，评价周期为 20/30/40/60d；不用于短线 1/3/5/10d，不生成交易建议。",
        "",
        "## 2. Layer Effectiveness",
        layer_effectiveness.to_markdown(index=False) if not layer_effectiveness.empty else "No layer rows.",
        "",
        "## 3. Pool Effectiveness",
        pool_effectiveness.to_markdown(index=False) if not pool_effectiveness.empty else "No pool rows.",
        "",
        "## 4. Top50 / Top10",
        f"- top50 rows: {len(top50)}",
        f"- top10 rows: {len(top10)}",
        "",
        "## 5. Usage",
        "- Top500 是 discovery pool；Top50 是复盘池；Top10 是重点观察池。",
        "- `high_elasticity_watch` 只表示高赔率高波动观察，不等同于低风险趋势核心。",
        "- `risk_exclusion_watch` 不进入 Top50/Top10。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _parse_components(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(value)
                return parsed if isinstance(parsed, dict) else {}
            except (ValueError, SyntaxError):
                return {}
    return {}


def _score(row: pd.Series, name: str) -> float:
    value = _number(row.get(name))
    return 0.0 if pd.isna(value) else value


def _number(value: Any) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if not pd.isna(numeric) else np.nan


def _observation_note(layer: str) -> str:
    return {
        "stable_trend_watch": "stable trend candidate; observe 20/30/40/60d trend persistence",
        "mainline_momentum_watch": "mainline relative-strength candidate; observe industry continuation",
        "pullback_reacceleration_watch": "prior strength with reacceleration; observe whether pullback resolves upward",
        "high_elasticity_watch": "high elasticity candidate; higher return potential with higher volatility",
        "risk_exclusion_watch": "excluded from top pools due to hard drawdown or volatility risk",
        "unclassified_mid_trend_watch": "mid trend fallback candidate; requires manual review",
    }.get(layer, "mid trend candidate")


def _invalid_condition(layer: str) -> str:
    return {
        "stable_trend_watch": "trend score falls or 20d drawdown expands materially",
        "mainline_momentum_watch": "industry relative strength fades or stock excess return reverses",
        "pullback_reacceleration_watch": "reacceleration fails and price breaks recent support",
        "high_elasticity_watch": "volatility expands with negative return or drawdown becomes dominant",
        "risk_exclusion_watch": "not eligible for top pools",
        "unclassified_mid_trend_watch": "fails to enter a named trend layer",
    }.get(layer, "trend thesis invalidates")


def _empty_detail() -> pd.DataFrame:
    return pd.DataFrame(columns=["trade_date", "asset_id", "mid_trend_layer", "mid_trend_funnel_score"])
