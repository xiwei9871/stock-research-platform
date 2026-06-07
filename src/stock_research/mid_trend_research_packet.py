from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


OUTPUT_CANDIDATES = "mid_trend_research_packet_candidates.csv"
OUTPUT_MANUAL_FIELDS = "mid_trend_research_packet_manual_fields.csv"
OUTPUT_REPORT = "mid_trend_research_packet_report.md"

FUNDAMENTAL_COLUMNS = [
    "roe",
    "roa",
    "gross_margin",
    "net_margin",
    "debt_ratio",
    "revenue_yoy",
    "np_yoy",
    "deduct_np_yoy",
    "ocf_to_np",
    "np_parent_ttm",
    "revenue_ttm",
    "equity_parent",
    "total_share",
    "float_share",
]

MANUAL_FIELD_COLUMNS = [
    "broker_report_count_90d",
    "latest_rating",
    "target_price",
    "target_upside",
    "institution_names",
    "industry_position_note",
    "product_position_note",
    "moat_or_scarcity_note",
    "negative_research_note",
    "research_confidence",
    "human_review_status",
]


def run_mid_trend_research_packet(
    *,
    funnel_detail_path: str | Path,
    fundamental_path: str | Path | None = None,
    stock_report_feature_path: str | Path | None = None,
    trade_date: str | None = None,
    top_n: int = 5,
    score_floor: float = 80.0,
    output_dir: str | Path = "outputs/research",
    research_service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    detail = pd.read_csv(funnel_detail_path, low_memory=False)
    fundamentals = _read_optional_csv(fundamental_path)
    stock_report_features = _read_optional_csv(stock_report_feature_path)
    if stock_report_features.empty:
        stock_report_features = _load_stock_report_features_for_detail(
            detail,
            trade_date=trade_date,
            service=research_service,
        )
    return build_mid_trend_research_packet_from_frames(
        detail,
        fundamentals,
        stock_report_features=stock_report_features,
        trade_date=trade_date,
        top_n=top_n,
        score_floor=score_floor,
        output_dir=output_dir,
        input_paths={
            "funnel_detail_path": str(funnel_detail_path),
            "fundamental_path": str(fundamental_path) if fundamental_path else "",
        },
    )


def build_mid_trend_research_packet_from_frames(
    funnel_detail: pd.DataFrame,
    fundamentals: pd.DataFrame | None = None,
    stock_report_features: pd.DataFrame | None = None,
    *,
    trade_date: str | None = None,
    top_n: int = 5,
    score_floor: float = 80.0,
    output_dir: str | Path | None = None,
    input_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    detail = _normalize_funnel_detail(funnel_detail)
    if trade_date:
        detail = detail[detail["trade_date"].eq(pd.to_datetime(trade_date))].copy()

    candidates = _select_candidates(detail, top_n=top_n, score_floor=score_floor)
    candidates = _enrich_with_fundamentals(candidates, fundamentals if fundamentals is not None else pd.DataFrame())
    candidates = _enrich_with_stock_report_features(
        candidates,
        stock_report_features if stock_report_features is not None else pd.DataFrame(),
    )
    candidates = _add_research_fields(candidates)
    manual_fields = _manual_fields_view(candidates)
    report = _render_report(
        candidates,
        top_n=top_n,
        score_floor=score_floor,
        trade_date=trade_date,
        input_paths=input_paths or {},
    )

    result: dict[str, Any] = {
        "candidates": candidates,
        "manual_fields": manual_fields,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "candidates": output / OUTPUT_CANDIDATES,
            "manual_fields": output / OUTPUT_MANUAL_FIELDS,
            "report": output / OUTPUT_REPORT,
        }
        candidates.to_csv(paths["candidates"], index=False)
        manual_fields.to_csv(paths["manual_fields"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _read_optional_csv(path: str | Path | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path, low_memory=False)


def _normalize_funnel_detail(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "trade_date" not in result.columns:
        result["trade_date"] = pd.NaT
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    for column in [
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "market_regime",
        "mainline_context",
        "mainline_status",
        "mid_trend_layer",
    ]:
        if column not in result.columns:
            result[column] = ""
    for column in [
        "rank",
        "score_rank",
        "mid_trend_funnel_score",
        "industry_mainline_score_v1",
        "ret_20_score",
        "ret_60_score",
        "trend_r2_20_score",
        "max_drawdown_20_score",
        "volatility_20_score",
    ]:
        if column not in result.columns:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["ts_code"] = result.apply(
        lambda row: row.get("ts_code") if _has_text(row.get("ts_code")) else _ts_code_from_asset_id(row.get("asset_id")),
        axis=1,
    )
    result["stock_name"] = result.apply(
        lambda row: row.get("stock_name") if _has_text(row.get("stock_name")) else row.get("ts_code"),
        axis=1,
    )
    return result


def _select_candidates(detail: pd.DataFrame, *, top_n: int, score_floor: float) -> pd.DataFrame:
    columns = _candidate_columns()
    if detail.empty or top_n <= 0:
        return pd.DataFrame(columns=columns)
    source = detail.dropna(subset=["trade_date"]).copy()
    source["_sort_rank"] = source["rank"]
    source.loc[source["_sort_rank"].isna(), "_sort_rank"] = source.loc[source["_sort_rank"].isna(), "score_rank"]
    source["_sort_score"] = source["mid_trend_funnel_score"].fillna(-np.inf)
    selected = (
        source.sort_values(["trade_date", "_sort_score", "_sort_rank"], ascending=[True, False, True])
        .groupby("trade_date", sort=True)
        .head(top_n)
        .copy()
    )
    selected = selected[selected["mid_trend_funnel_score"] >= score_floor].copy()
    if selected.empty:
        return pd.DataFrame(columns=columns)
    selected = selected.sort_values(["trade_date", "_sort_score", "_sort_rank"], ascending=[True, False, True])
    selected["research_packet_rank"] = selected.groupby("trade_date").cumcount() + 1
    selected["research_packet_id"] = (
        selected["trade_date"].dt.strftime("%Y-%m-%d")
        + "_"
        + selected["asset_id"].astype(str)
        + "_mid_trend_research_packet"
    )
    selected["score_floor"] = score_floor
    selected["top_n_source"] = top_n
    return _ensure_columns(selected.drop(columns=["_sort_rank", "_sort_score"], errors="ignore"), columns)


def _enrich_with_fundamentals(candidates: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    for column in FUNDAMENTAL_COLUMNS:
        if column not in result.columns:
            result[column] = np.nan
    result["fundamental_trade_date"] = pd.NaT
    if result.empty or fundamentals.empty or "asset_id" not in fundamentals.columns:
        result["fundamental_hard_risk"] = "fundamental_data_missing"
        result["fundamental_quality_note"] = "No PIT fundamental row was available for this candidate."
        return result

    fundamentals = fundamentals.copy()
    if "trade_date" not in fundamentals.columns:
        fundamentals["trade_date"] = pd.NaT
    fundamentals["trade_date"] = pd.to_datetime(fundamentals["trade_date"], errors="coerce")
    for column in FUNDAMENTAL_COLUMNS:
        if column not in fundamentals.columns:
            fundamentals[column] = np.nan
        fundamentals[column] = pd.to_numeric(fundamentals[column], errors="coerce")
    by_asset = {
        asset_id: group.sort_values("trade_date")
        for asset_id, group in fundamentals.dropna(subset=["trade_date"]).groupby("asset_id", sort=False)
    }

    matched_rows: list[dict[str, Any]] = []
    for _, row in result.iterrows():
        group = by_asset.get(row["asset_id"])
        matched: dict[str, Any] = {"fundamental_trade_date": pd.NaT}
        if group is not None:
            eligible = group[group["trade_date"] <= row["trade_date"]]
            if not eligible.empty:
                latest = eligible.iloc[-1]
                matched = {column: latest.get(column, np.nan) for column in FUNDAMENTAL_COLUMNS}
                matched["fundamental_trade_date"] = latest.get("trade_date", pd.NaT)
        matched_rows.append(matched)

    matched_frame = pd.DataFrame(matched_rows)
    for column in FUNDAMENTAL_COLUMNS + ["fundamental_trade_date"]:
        result[column] = matched_frame.get(column, np.nan)
    result["fundamental_hard_risk"] = result.apply(_fundamental_hard_risk, axis=1)
    result["fundamental_quality_note"] = result.apply(_fundamental_quality_note, axis=1)
    return result


def _add_research_fields(candidates: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    if result.empty:
        for column in _research_columns():
            result[column] = []
        return result
    result["domestic_report_query"] = result.apply(
        lambda row: f"{_safe_text(row.get('stock_name'))} {_safe_text(row.get('ts_code'))} 研报 目标价 评级",
        axis=1,
    )
    result["foreign_report_query"] = result.apply(
        lambda row: (
            f"{_safe_text(row.get('stock_name'))} {_safe_text(row.get('industry_name'))} "
            "global peer analyst report target price"
        ),
        axis=1,
    )
    result["industry_position_query"] = result.apply(
        lambda row: f"{_safe_text(row.get('stock_name'))} {_safe_text(row.get('industry_name'))} 行业地位 市占率 龙头",
        axis=1,
    )
    result["product_position_query"] = result.apply(
        lambda row: f"{_safe_text(row.get('stock_name'))} 产品 竞争格局 垄断 稀缺",
        axis=1,
    )
    result["target_price_query"] = result.apply(
        lambda row: f"{_safe_text(row.get('stock_name'))} {_safe_text(row.get('ts_code'))} 目标价 评级 研报",
        axis=1,
    )
    result["industry_news_query"] = result.apply(
        lambda row: f"{_safe_text(row.get('industry_name'))} 行业 景气度 政策 订单 价格",
        axis=1,
    )
    for column in MANUAL_FIELD_COLUMNS:
        result[column] = ""
    result["broker_report_count_90d"] = result["broker_report_count_90d_pit"].map(_blank_if_nan)
    result["target_price"] = result["target_price_median_pit"].map(_blank_if_nan)
    result["target_upside"] = result["target_upside_median_pit"].map(_blank_if_nan)
    result["human_review_status"] = "pending"
    result["research_view"] = result.apply(_research_view, axis=1)
    result["operator_review_note"] = result.apply(_operator_review_note, axis=1)
    return _ensure_columns(result, _candidate_columns() + FUNDAMENTAL_COLUMNS + _research_columns())


def _enrich_with_stock_report_features(candidates: pd.DataFrame, stock_report_features: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    if result.empty or stock_report_features.empty:
        for column in _stock_report_feature_columns():
            result[column] = 0 if column != "latest_pdf_risk_summary" else ""
        result["broker_report_count_90d_pit"] = 0
        result["positive_rating_count_pit"] = 0
        result["rating_upgrade_count_pit"] = 0
        result["broker_coverage_count_pit"] = 0
        result["research_support_score_pit"] = 0.0
        result["pdf_target_price_count_90d"] = 0
        result["pdf_target_price_high_confidence_count_90d"] = 0
        result["pdf_profit_forecast_count_90d"] = 0
        result["pdf_risk_section_count_90d"] = 0
        return result

    features = stock_report_features.copy()
    if "trade_date" not in features.columns:
        features["trade_date"] = pd.NaT
    features["trade_date"] = pd.to_datetime(features["trade_date"], errors="coerce")
    for column in _stock_report_feature_numeric_columns():
        if column not in features.columns:
            features[column] = np.nan
        features[column] = pd.to_numeric(features[column], errors="coerce")
    if "metadata" not in features.columns:
        features["metadata"] = [{} for _ in range(len(features))]
    features["metadata"] = features["metadata"].map(_metadata_dict)
    features["latest_pdf_risk_summary"] = features["metadata"].map(lambda value: _safe_text(value.get("latest_pdf_risk_summary")))
    for column in [
        "pdf_target_price_count_90d",
        "pdf_target_price_high_confidence_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
    ]:
        features[column] = features["metadata"].map(lambda value, key=column: pd.to_numeric(value.get(key, 0), errors="coerce")).fillna(0)

    features = features.sort_values(["trade_date", "asset_id"]).drop_duplicates(["trade_date", "asset_id"], keep="last")
    merged = result.merge(
        features[
            [
                "trade_date",
                "asset_id",
                "report_count_90d",
                "latest_report_days",
                "positive_rating_count",
                "rating_upgrade_count",
                "target_price_median",
                "target_upside_median",
                "broker_coverage_count",
                "research_support_score",
                "pdf_target_price_count_90d",
                "pdf_target_price_high_confidence_count_90d",
                "pdf_profit_forecast_count_90d",
                "pdf_risk_section_count_90d",
                "latest_pdf_risk_summary",
            ]
        ],
        on=["trade_date", "asset_id"],
        how="left",
        suffixes=("", "_pit"),
    )
    rename_map = {
        "report_count_90d": "broker_report_count_90d_pit",
        "latest_report_days": "latest_report_days_pit",
        "positive_rating_count": "positive_rating_count_pit",
        "rating_upgrade_count": "rating_upgrade_count_pit",
        "target_price_median": "target_price_median_pit",
        "target_upside_median": "target_upside_median_pit",
        "broker_coverage_count": "broker_coverage_count_pit",
        "research_support_score": "research_support_score_pit",
    }
    merged = merged.rename(columns=rename_map)
    for column in _stock_report_feature_columns():
        if column not in merged.columns:
            merged[column] = 0 if column != "latest_pdf_risk_summary" else ""
    for column in [
        "broker_report_count_90d_pit",
        "positive_rating_count_pit",
        "rating_upgrade_count_pit",
        "broker_coverage_count_pit",
        "pdf_target_price_count_90d",
        "pdf_target_price_high_confidence_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
    ]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0)
    merged["research_support_score_pit"] = pd.to_numeric(merged["research_support_score_pit"], errors="coerce").fillna(0.0)
    return merged


def _manual_fields_view(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "research_packet_id",
        "trade_date",
        "research_packet_rank",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "mid_trend_funnel_score",
        "domestic_report_query",
        "foreign_report_query",
        "industry_position_query",
        "product_position_query",
        "target_price_query",
        "industry_news_query",
    ] + MANUAL_FIELD_COLUMNS + ["research_view", "operator_review_note"]
    return _ensure_columns(candidates, columns)


def _render_report(
    candidates: pd.DataFrame,
    *,
    top_n: int,
    score_floor: float,
    trade_date: str | None,
    input_paths: dict[str, str],
) -> str:
    industry_summary = _industry_summary(candidates)
    hard_risk_summary = (
        candidates["fundamental_hard_risk"].value_counts(dropna=False).rename_axis("fundamental_hard_risk").reset_index(name="count")
        if not candidates.empty and "fundamental_hard_risk" in candidates.columns
        else pd.DataFrame(columns=["fundamental_hard_risk", "count"])
    )
    lines = [
        "# Mid Trend Research Packet v1",
        "",
        "## 1. Scope",
        "This packet supports human research review for mid-trend candidates. It is not an automated trading signal and does not produce execution instructions.",
        "",
        "## 2. Selection",
        f"- source top_n: {top_n}",
        f"- score_floor: {score_floor:g}",
        f"- trade_date: {trade_date or 'all available dates'}",
        f"- funnel_detail_path: {input_paths.get('funnel_detail_path', '')}",
        f"- fundamental_path: {input_paths.get('fundamental_path', '')}",
        "",
        "## 3. Candidate Summary",
        f"- candidate_rows: {len(candidates)}",
        f"- trade_date_count: {int(candidates['trade_date'].nunique()) if not candidates.empty else 0}",
        f"- asset_count: {int(candidates['asset_id'].nunique()) if not candidates.empty else 0}",
        "",
        "## 4. Industry Summary",
        industry_summary.head(30).to_markdown(index=False) if not industry_summary.empty else "No candidate rows.",
        "",
        "## 5. Fundamental Hard Risk",
        hard_risk_summary.to_markdown(index=False) if not hard_risk_summary.empty else "No fundamental coverage.",
        "",
        "## 6. Manual Research Fields",
        "Fill broker report count, latest rating, target price context, industry position, product position, scarcity/moat notes, and negative research notes manually.",
        "",
        "## 7. Guardrail",
        "The packet is for selection support and research prioritization only. Final portfolio decisions remain manual.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _industry_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = ["industry_name", "sample_count", "avg_mid_trend_funnel_score", "hard_risk_count"]
    if candidates.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for industry, group in candidates.groupby("industry_name", sort=True):
        rows.append(
            {
                "industry_name": industry,
                "sample_count": int(len(group)),
                "avg_mid_trend_funnel_score": float(pd.to_numeric(group["mid_trend_funnel_score"], errors="coerce").mean()),
                "hard_risk_count": int(group["fundamental_hard_risk"].eq("loss_or_deterioration_risk").sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(["sample_count", "industry_name"], ascending=[False, True])


def _fundamental_hard_risk(row: pd.Series) -> str:
    key_values = [row.get("np_parent_ttm"), row.get("np_yoy"), row.get("deduct_np_yoy"), row.get("roe"), row.get("net_margin")]
    if all(pd.isna(value) for value in key_values):
        return "fundamental_data_missing"
    loss = _num(row.get("np_parent_ttm")) < 0 or _num(row.get("net_margin")) < 0
    deterioration = _num(row.get("np_yoy")) <= -0.3 or _num(row.get("deduct_np_yoy")) <= -0.3
    weak_profitability = _num(row.get("roe")) < 0 and _num(row.get("net_margin")) < 0
    if loss or deterioration or weak_profitability:
        return "loss_or_deterioration_risk"
    return "no_clear_hard_risk"


def _fundamental_quality_note(row: pd.Series) -> str:
    risk = row.get("fundamental_hard_risk")
    if risk == "fundamental_data_missing":
        return "Fundamental PIT data is missing; manual hard-risk review is required."
    if risk == "loss_or_deterioration_risk":
        return "Loss or profit deterioration signal exists; classify as high-risk research before considering longer holding."
    return "No obvious hard fundamental risk from available PIT fields; still verify reports and recent announcements manually."


def _research_view(row: pd.Series) -> str:
    if row.get("fundamental_hard_risk") == "loss_or_deterioration_risk":
        return "negative_or_uncertain"
    score = _num(row.get("mid_trend_funnel_score"))
    mainline_text = " ".join(
        [_safe_text(row.get("market_regime")), _safe_text(row.get("mainline_context")), _safe_text(row.get("mainline_status"))]
    ).lower()
    has_mainline = any(token in mainline_text for token in ["mainline", "sustained", "strong"])
    if score >= 90 and has_mainline:
        return "moderate_research_support_pending_manual"
    if score >= 80:
        return "weak_research_support_pending_manual"
    return "no_clear_research_support"


def _operator_review_note(row: pd.Series) -> str:
    return (
        "Human research required: verify broker coverage, industry position, product competitiveness, "
        "scarcity/moat evidence, target-price context, valuation pressure, and negative reports before any decision."
    )


def _candidate_columns() -> list[str]:
    return [
        "research_packet_id",
        "trade_date",
        "research_packet_rank",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "market_regime",
        "mainline_context",
        "mainline_status",
        "industry_mainline_score_v1",
        "mid_trend_layer",
        "mid_trend_funnel_score",
        "score_floor",
        "top_n_source",
        "rank",
        "score_rank",
        "ret_20_score",
        "ret_60_score",
        "trend_r2_20_score",
        "max_drawdown_20_score",
        "volatility_20_score",
    ]


def _research_columns() -> list[str]:
    return [
        "broker_report_count_90d_pit",
        "latest_report_days_pit",
        "positive_rating_count_pit",
        "rating_upgrade_count_pit",
        "target_price_median_pit",
        "target_upside_median_pit",
        "broker_coverage_count_pit",
        "research_support_score_pit",
        "pdf_target_price_count_90d",
        "pdf_target_price_high_confidence_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
        "latest_pdf_risk_summary",
        "fundamental_trade_date",
        "fundamental_hard_risk",
        "fundamental_quality_note",
        "domestic_report_query",
        "foreign_report_query",
        "industry_position_query",
        "product_position_query",
        "target_price_query",
        "industry_news_query",
    ] + MANUAL_FIELD_COLUMNS + ["research_view", "operator_review_note"]


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = np.nan
    return result[columns].reset_index(drop=True)


def _ts_code_from_asset_id(asset_id: Any) -> str:
    parts = str(asset_id or "").split(":")
    if len(parts) == 3 and parts[0] == "CN" and parts[1] in {"SH", "SZ", "BJ"}:
        return f"{parts[2]}.{parts[1]}"
    return ""


def _has_text(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"nan", "none", "nat"}


def _safe_text(value: Any) -> str:
    return str(value).strip() if _has_text(value) else ""


def _num(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return float("nan")
    return float(numeric)


def _blank_if_nan(value: Any) -> Any:
    return "" if pd.isna(pd.to_numeric(value, errors="coerce")) else value


def _stock_report_feature_columns() -> list[str]:
    return _stock_report_feature_numeric_columns() + ["latest_pdf_risk_summary"]


def _stock_report_feature_numeric_columns() -> list[str]:
    return [
        "broker_report_count_90d_pit",
        "latest_report_days_pit",
        "positive_rating_count_pit",
        "rating_upgrade_count_pit",
        "target_price_median_pit",
        "target_upside_median_pit",
        "broker_coverage_count_pit",
        "research_support_score_pit",
        "pdf_target_price_count_90d",
        "pdf_target_price_high_confidence_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
    ]


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _load_stock_report_features_for_detail(detail: pd.DataFrame, *, trade_date: str | None, service: str) -> pd.DataFrame:
    if detail.empty or "asset_id" not in detail.columns:
        return pd.DataFrame()
    asset_ids = detail["asset_id"].dropna().astype(str).unique().tolist()
    if not asset_ids:
        return pd.DataFrame()
    if "trade_date" in detail.columns:
        trade_dates = pd.to_datetime(detail["trade_date"], errors="coerce").dropna()
    else:
        trade_dates = pd.Series(dtype="datetime64[ns]")
    if trade_date:
        start_date = end_date = trade_date
    elif trade_dates.empty:
        return pd.DataFrame()
    else:
        start_date = trade_dates.min().strftime("%Y-%m-%d")
        end_date = trade_dates.max().strftime("%Y-%m-%d")
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT
                trade_date::text AS trade_date,
                asset_id,
                ts_code,
                stock_name,
                report_count_90d,
                latest_report_days,
                positive_rating_count,
                rating_upgrade_count,
                target_price_median,
                target_upside_median,
                broker_coverage_count,
                research_support_score,
                metadata
            FROM research.stock_report_feature_daily
            WHERE trade_date BETWEEN %s AND %s
              AND asset_id = ANY(%s)
            """,
            [start_date, end_date, asset_ids],
        )
    return pd.DataFrame(rows)
