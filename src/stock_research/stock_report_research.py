from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


WORKPACK_FILE = "stock_report_research_workpack.csv"
IMPORT_TEMPLATE_FILE = "stock_report_research_import_template.csv"
REPORT_FILE = "stock_report_research_workpack_report.md"


def run_stock_report_workpack(
    *,
    research_packet_path: str | Path,
    trade_date: str | None = None,
    output_dir: str | Path = "outputs/research",
) -> dict[str, Any]:
    candidates = pd.read_csv(research_packet_path, low_memory=False)
    return build_stock_report_workpack_from_candidates(
        candidates,
        trade_date=trade_date,
        output_dir=output_dir,
        input_path=str(research_packet_path),
    )


def build_stock_report_workpack_from_candidates(
    candidates: pd.DataFrame,
    *,
    trade_date: str | None = None,
    output_dir: str | Path | None = None,
    input_path: str = "",
) -> dict[str, Any]:
    normalized = _normalize_candidates(candidates)
    if trade_date:
        normalized = normalized[normalized["trade_date"].eq(pd.to_datetime(trade_date))].copy()
    workpack = _build_workpack(normalized)
    import_template = _build_import_template(workpack)
    report = _render_report(workpack, import_template, trade_date=trade_date, input_path=input_path)
    result: dict[str, Any] = {
        "workpack": workpack,
        "import_template": import_template,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "workpack": output / WORKPACK_FILE,
            "import_template": output / IMPORT_TEMPLATE_FILE,
            "report": output / REPORT_FILE,
        }
        workpack.to_csv(paths["workpack"], index=False)
        import_template.to_csv(paths["import_template"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "trade_date" not in result.columns:
        result["trade_date"] = pd.NaT
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    for column in [
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "fundamental_hard_risk",
        "research_view",
        "domestic_report_query",
        "foreign_report_query",
        "industry_position_query",
        "product_position_query",
        "target_price_query",
        "industry_news_query",
        "latest_pdf_risk_summary",
    ]:
        if column not in result.columns:
            result[column] = ""
    for column in [
        "research_packet_rank",
        "mid_trend_funnel_score",
        "broker_report_count_90d",
        "research_support_score_pit",
        "target_price_median_pit",
        "target_upside_median_pit",
        "broker_coverage_count_pit",
        "pdf_target_price_count_90d",
        "pdf_target_price_high_confidence_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
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
    return result.sort_values(["trade_date", "research_packet_rank", "mid_trend_funnel_score"], ascending=[True, True, False])


def _build_workpack(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "review_id",
        "trade_date",
        "candidate_rank",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "mid_trend_funnel_score",
        "fundamental_hard_risk",
        "research_view",
        "broker_report_count_90d",
        "research_support_score_pit",
        "target_price_median_pit",
        "target_upside_median_pit",
        "broker_coverage_count_pit",
        "pdf_target_price_count_90d",
        "pdf_target_price_high_confidence_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
        "latest_pdf_risk_summary",
        "domestic_broker_report_query",
        "foreign_report_query",
        "industry_position_query",
        "product_position_query",
        "target_price_query",
        "industry_news_query",
        "manual_fields_required",
        "review_priority",
        "review_status",
        "notes",
    ]
    if candidates.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in candidates.iterrows():
        trade_date = row["trade_date"].strftime("%Y-%m-%d") if pd.notna(row["trade_date"]) else ""
        ts_code = _safe_text(row.get("ts_code"))
        stock_name = _safe_text(row.get("stock_name")) or ts_code
        industry_name = _safe_text(row.get("industry_name"))
        rows.append(
            {
                "review_id": f"{trade_date}_{ts_code}_stock_report_manual_review",
                "trade_date": trade_date,
                "candidate_rank": int(row["research_packet_rank"]) if pd.notna(row.get("research_packet_rank")) else np.nan,
                "asset_id": row.get("asset_id", ""),
                "ts_code": ts_code,
                "stock_name": stock_name,
                "industry_name": industry_name,
                "mid_trend_funnel_score": row.get("mid_trend_funnel_score", np.nan),
                "fundamental_hard_risk": row.get("fundamental_hard_risk", ""),
                "research_view": row.get("research_view", ""),
                "broker_report_count_90d": row.get("broker_report_count_90d", np.nan),
                "research_support_score_pit": row.get("research_support_score_pit", np.nan),
                "target_price_median_pit": row.get("target_price_median_pit", np.nan),
                "target_upside_median_pit": row.get("target_upside_median_pit", np.nan),
                "broker_coverage_count_pit": row.get("broker_coverage_count_pit", np.nan),
                "pdf_target_price_count_90d": row.get("pdf_target_price_count_90d", np.nan),
                "pdf_target_price_high_confidence_count_90d": row.get("pdf_target_price_high_confidence_count_90d", np.nan),
                "pdf_profit_forecast_count_90d": row.get("pdf_profit_forecast_count_90d", np.nan),
                "pdf_risk_section_count_90d": row.get("pdf_risk_section_count_90d", np.nan),
                "latest_pdf_risk_summary": row.get("latest_pdf_risk_summary", ""),
                "domestic_broker_report_query": _query_or_default(
                    row.get("domestic_report_query"),
                    f"{stock_name} {ts_code} 研报 目标价 评级",
                ),
                "foreign_report_query": _query_or_default(
                    row.get("foreign_report_query"),
                    f"{stock_name} {industry_name} global peer analyst report target price",
                ),
                "industry_position_query": _query_or_default(
                    row.get("industry_position_query"),
                    f"{stock_name} {industry_name} 行业地位 市占率 龙头",
                ),
                "product_position_query": _query_or_default(
                    row.get("product_position_query"),
                    f"{stock_name} 产品 竞争格局 垄断 稀缺",
                ),
                "target_price_query": _query_or_default(
                    row.get("target_price_query"),
                    f"{stock_name} {ts_code} 目标价 评级 研报",
                ),
                "industry_news_query": _query_or_default(
                    row.get("industry_news_query"),
                    f"{industry_name} 行业 景气度 政策 订单 价格",
                ),
                "manual_fields_required": (
                    "broker_report_count_90d,latest_rating,target_price,target_upside,"
                    "institution_names,industry_position_note,product_position_note,"
                    "moat_or_scarcity_note,negative_research_note,valuation_note,evidence_summary,confidence"
                ),
                "review_priority": _review_priority(row),
                "review_status": "pending",
                "notes": "Open-source report metadata and manual summary only; do not paste paid report full text.",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _build_import_template(workpack: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "report_id",
        "review_id",
        "trade_date",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "source_type",
        "source_name",
        "broker",
        "analyst",
        "report_title",
        "publish_date",
        "source_url",
        "public_access",
        "copyright_note",
        "source_confidence",
        "rating",
        "rating_change",
        "target_price",
        "target_upside",
        "forecast_revenue",
        "forecast_profit",
        "industry_view",
        "company_view",
        "risk_summary",
        "broker_report_count_90d",
        "latest_rating",
        "institution_names",
        "industry_position_note",
        "product_position_note",
        "moat_or_scarcity_note",
        "negative_research_note",
        "valuation_note",
        "evidence_summary",
        "confidence",
        "review_status",
        "human_reviewer",
    ]
    if workpack.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in workpack.iterrows():
        report_id = f"{row['trade_date']}_{row['ts_code']}_manual_report_source_1"
        rows.append(
            {
                "report_id": report_id,
                "review_id": row["review_id"],
                "trade_date": row["trade_date"],
                "asset_id": row["asset_id"],
                "ts_code": row["ts_code"],
                "stock_name": row["stock_name"],
                "industry_name": row["industry_name"],
                "source_type": "",
                "source_name": "",
                "broker": "",
                "analyst": "",
                "report_title": "",
                "publish_date": "",
                "source_url": "",
                "public_access": True,
                "copyright_note": "metadata and manual summary only; no paid full-text storage",
                "source_confidence": "",
                "rating": "",
                "rating_change": "",
                "target_price": "",
                "target_upside": "",
                "forecast_revenue": "",
                "forecast_profit": "",
                "industry_view": "",
                "company_view": "",
                "risk_summary": "",
                "broker_report_count_90d": "",
                "latest_rating": "",
                "institution_names": "",
                "industry_position_note": "",
                "product_position_note": "",
                "moat_or_scarcity_note": "",
                "negative_research_note": "",
                "valuation_note": "",
                "evidence_summary": "",
                "confidence": "",
                "review_status": "pending",
                "human_reviewer": "",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _render_report(
    workpack: pd.DataFrame,
    import_template: pd.DataFrame,
    *,
    trade_date: str | None,
    input_path: str,
) -> str:
    risk_summary = (
        workpack["fundamental_hard_risk"].value_counts(dropna=False).rename_axis("fundamental_hard_risk").reset_index(name="count")
        if not workpack.empty
        else pd.DataFrame(columns=["fundamental_hard_risk", "count"])
    )
    lines = [
        "# Stock Report Research Workpack v1",
        "",
        "## 1. Scope",
        "This workpack supports manual research-note collection for mid-trend candidates. It stores public metadata and manual summaries only; it does not store paid full text and does not produce trading instructions.",
        "",
        "## 2. Inputs",
        f"- research_packet_path: {input_path}",
        f"- trade_date: {trade_date or 'all available dates'}",
        "",
        "## 3. Outputs",
        "- `research.stock_report_source`: report metadata and source URL",
        "- `research.stock_report_event`: structured rating, target price, forecast and risk fields",
        "- `research.stock_report_manual_review`: industry/product/moat/negative-note manual review",
        "",
        "## 4. Candidate Summary",
        f"- workpack_rows: {len(workpack)}",
        f"- import_template_rows: {len(import_template)}",
        "",
        "## 5. PIT Research Coverage",
        workpack[
            [
                "candidate_rank",
                "ts_code",
                "broker_report_count_90d",
                "research_support_score_pit",
                "pdf_target_price_count_90d",
                "pdf_profit_forecast_count_90d",
                "pdf_risk_section_count_90d",
            ]
        ].to_markdown(index=False)
        if not workpack.empty
        else "No rows.",
        "",
        "## 6. Fundamental Risk Summary",
        risk_summary.to_markdown(index=False) if not risk_summary.empty else "No rows.",
        "",
        "## 7. Guardrail",
        "Use this as a research support packet only. Do not treat report count, rating or target price as an automatic selection or execution signal.",
        "",
        "## 8. stock_report_manual_review",
        "Fill industry position, product position, moat/scarcity, valuation pressure, negative research and evidence summary manually.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _review_priority(row: pd.Series) -> str:
    if str(row.get("fundamental_hard_risk", "")) == "loss_or_deterioration_risk":
        return "hard_risk_review_first"
    score = pd.to_numeric(row.get("mid_trend_funnel_score"), errors="coerce")
    if pd.notna(score) and float(score) >= 85:
        return "high_score_research"
    return "standard_research"


def _query_or_default(value: Any, default: str) -> str:
    return _safe_text(value) or default


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
