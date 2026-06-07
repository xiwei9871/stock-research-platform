from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from stock_research.research_narrative import (
    build_research_decision_narrative_from_fact_sheet,
    build_research_fact_sheet_from_frames,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "research"

_RESEARCH_NUMERIC_COLUMNS = [
    "research_support_score_pit",
    "broker_report_count_90d",
    "target_price_median_pit",
    "target_upside_median_pit",
    "broker_coverage_count_pit",
    "pdf_target_price_count_90d",
    "pdf_target_price_high_confidence_count_90d",
    "pdf_profit_forecast_count_90d",
    "pdf_risk_section_count_90d",
]

_CANDIDATE_ADD_LABEL_BONUS = 3.0
_CANDIDATE_ADD_DISCUSSION_BONUS = 2.0
_CANDIDATE_ADD_BROKER_REPORT_WEIGHT = 0.1
_CANDIDATE_ADD_RANK_PENALTY = 0.01

_CANDIDATE_REDUCE_NON_LOW_PRIORITY_PENALTY = 2.0
_CANDIDATE_REDUCE_NON_OBSERVATION_PENALTY = 1.0
_CANDIDATE_REDUCE_BROKER_REPORT_WEIGHT = 0.1
_DOSSIER_CANDIDATE_SHORTLIST_SIZE = 3
_NARRATIVE_JOIN_COLUMNS = [
    "asset_id",
    "one_line_judgment",
    "support_fact_1",
    "support_fact_2",
    "support_fact_3",
    "oppose_fact_1",
    "oppose_fact_2",
    "watch_point",
    "falsification_condition",
    "what_is_working_summary",
    "industry_position_summary",
    "institution_view_summary",
    "risk_summary",
]
_NEWS_ENRICHMENT_COLUMNS = [
    "trade_date",
    "asset_id",
    "news_compact_summary",
    "news_consensus_summary",
    "news_risk_summary",
    "theme_catalyst_summary",
    "overnight_catalyst_note",
    "news_attention_level",
    "news_risk_attention_flag",
    "news_enrichment_quality_flag",
]


def run_mid_trend_position_dossier(
    *,
    trade_date: str,
    mode: str,
    portfolio_review_path: str | Path,
    research_packet_path: str | Path,
    news_enrichment_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    portfolio_review = pd.read_csv(portfolio_review_path, low_memory=False)
    research_packet_candidates = pd.read_csv(research_packet_path, low_memory=False)
    news_enrichment = (
        pd.read_csv(news_enrichment_path, low_memory=False)
        if news_enrichment_path is not None
        else None
    )
    return build_mid_trend_position_dossier_from_frames(
        trade_date=trade_date,
        mode=mode,
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet_candidates,
        news_enrichment=news_enrichment,
        output_dir=_normalize_output_dir(output_dir),
    )


def build_mid_trend_position_dossier_from_frames(
    *,
    trade_date: str,
    mode: str,
    portfolio_review: pd.DataFrame,
    research_packet_candidates: pd.DataFrame,
    news_enrichment: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized_review = _normalize_dossier_portfolio_review(portfolio_review, trade_date=trade_date)
    normalized_research = _normalize_dossier_research(research_packet_candidates, trade_date=trade_date, mode=mode)
    normalized_news = _normalize_dossier_news_enrichment(news_enrichment, trade_date=trade_date)
    news_enrichment_status = _build_news_enrichment_status(
        normalized_review=normalized_review,
        normalized_news=normalized_news,
        news_enrichment_provided=news_enrichment is not None,
    )
    narrative = _build_dossier_narrative(
        trade_date=trade_date,
        mode=mode,
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet_candidates,
    )
    holdings, candidate_adds, candidate_reduces = _partition_dossier_rows(
        normalized_review=normalized_review,
        normalized_research=normalized_research,
        normalized_news=normalized_news,
    )
    holdings = _merge_narrative_columns(holdings, narrative)
    candidate_adds = _merge_narrative_columns(candidate_adds, narrative)
    candidate_reduces = _merge_narrative_columns(candidate_reduces, narrative)
    appendix = _build_appendix_rows(
        normalized_review=normalized_review,
        normalized_research=normalized_research,
        normalized_news=normalized_news,
        holdings=holdings,
        candidate_adds=candidate_adds,
        candidate_reduces=candidate_reduces,
    )
    summary_rows = _build_dossier_summary_rows(
        normalized_review=normalized_review,
        normalized_research=normalized_research,
        normalized_news=normalized_news,
        narrative=narrative,
        holdings=holdings,
        candidate_adds=candidate_adds,
        candidate_reduces=candidate_reduces,
    )
    summary = {
        "trade_date": trade_date,
        "mode": mode,
        "holding_count": int(len(holdings)),
        "candidate_add_count": int(len(candidate_adds)),
        "candidate_reduce_count": int(len(candidate_reduces)),
        "enhanced_sources_used": "yes" if _has_enhanced_research(normalized_research) else "no",
        **news_enrichment_status,
    }
    markdown = _render_dossier_markdown(
        summary=summary,
        holdings=holdings,
        candidate_adds=candidate_adds,
        candidate_reduces=candidate_reduces,
    )
    markdown += "\n## 附录：结构化证据摘要表\n"
    markdown += "\n".join(_render_appendix_table(appendix)).strip("\n")
    markdown = markdown.rstrip() + "\n"
    result = {
        "summary": summary,
        "holdings": holdings,
        "candidate_adds": candidate_adds,
        "candidate_reduces": candidate_reduces,
        "summary_rows": summary_rows,
        "appendix": appendix,
        "markdown": markdown,
        "paths": {},
        "output_dir": str(_normalize_output_dir(output_dir)),
        "news_enrichment_status": news_enrichment_status,
    }
    if output_dir is not None:
        output_path = _normalize_output_dir(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        csv_path = output_path / f"mid_trend_position_dossier_summary_{trade_date}.csv"
        md_path = output_path / f"mid_trend_position_dossier_{trade_date}.md"
        summary_rows.to_csv(csv_path, index=False)
        md_path.write_text(markdown, encoding="utf-8")
        result["paths"] = {"csv": str(csv_path), "md": str(md_path), "report": str(md_path)}
    return result


def _normalize_dossier_portfolio_review(frame: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return _empty_portfolio_review()
    requested_trade_date = pd.to_datetime(trade_date)
    if "shadow_top10_rank" not in result.columns and "candidate_rank" in result.columns:
        result["shadow_top10_rank"] = result["candidate_rank"]
    if "weight" not in result.columns and "target_weight" in result.columns:
        result["weight"] = result["target_weight"]
    if "trade_date" not in result.columns:
        result["trade_date"] = requested_trade_date
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result[result["trade_date"].eq(requested_trade_date)].copy()
    if result.empty:
        return _empty_portfolio_review()

    defaults: dict[str, Any] = {
        "asset_id": "",
        "ts_code": "",
        "stock_name": "",
        "section": "",
        "shadow_top10_rank": pd.NA,
        "weight": pd.NA,
        "final_label": "",
        "why_hold_or_change": "",
        "main_positive_evidence": "",
        "main_risk_evidence": "",
        "latest_pdf_risk_summary": "",
        "is_current_holding": pd.NA,
    }
    for column, value in defaults.items():
        if column not in result.columns:
            result[column] = value

    result["shadow_top10_rank"] = pd.to_numeric(result["shadow_top10_rank"], errors="coerce")
    result["weight"] = pd.to_numeric(result["weight"], errors="coerce")
    result["is_current_holding"] = result["is_current_holding"].fillna(False).astype(bool)
    result["stock_name"] = result["stock_name"].where(result["stock_name"].astype(str).str.strip().ne(""), result["ts_code"])
    return result.sort_values(["is_current_holding", "shadow_top10_rank"], ascending=[False, True], kind="mergesort")


def _normalize_dossier_research(frame: pd.DataFrame, *, trade_date: str, mode: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return _empty_research()
    if "trade_date" not in result.columns or "asset_id" not in result.columns:
        return _empty_research()

    result = result.reset_index(drop=True)
    result["_source_order"] = range(len(result))
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result[result["trade_date"].notna()].copy()
    if result.empty:
        return _empty_research()

    requested_trade_date = pd.to_datetime(trade_date)
    if mode == "replay":
        result = result[result["trade_date"].le(requested_trade_date)].copy()
    else:
        # Live mode still rejects future/missing rows, but it keeps a clear same-day
        # path so enhanced intraday/same-day inputs are treated as the freshest source.
        same_day_rows = result[result["trade_date"].eq(requested_trade_date)].copy()
        historical_rows = result[result["trade_date"].lt(requested_trade_date)].copy()
        result = pd.concat([historical_rows, same_day_rows], ignore_index=True)
    if result.empty:
        return _empty_research()

    defaults: dict[str, Any] = {
        "ts_code": "",
        "stock_name": "",
        "latest_pdf_risk_summary": "",
        "fundamental_hard_risk": "",
        "main_positive_evidence": "",
        "main_risk_evidence": "",
        "why_hold_or_change": "",
    }
    for column, value in defaults.items():
        if column not in result.columns:
            result[column] = value
    for column in _RESEARCH_NUMERIC_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result = result.sort_values(["trade_date", "_source_order"], ascending=[True, True], kind="mergesort")
    result = result.drop_duplicates(subset=["asset_id"], keep="last").drop(columns=["_source_order"], errors="ignore")
    result["stock_name"] = result["stock_name"].where(result["stock_name"].astype(str).str.strip().ne(""), result["ts_code"])
    return result


def _partition_dossier_rows(
    *,
    normalized_review: pd.DataFrame,
    normalized_research: pd.DataFrame,
    normalized_news: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    merged = normalized_review.copy()
    if normalized_news is None:
        normalized_news = pd.DataFrame(columns=_NEWS_ENRICHMENT_COLUMNS)
    if not normalized_research.empty:
        research = normalized_research.add_prefix("research_")
        merged = merged.merge(
            research,
            how="left",
            left_on="asset_id",
            right_on="research_asset_id",
        )
        for column in ["stock_name", "ts_code", "latest_pdf_risk_summary", "main_positive_evidence", "main_risk_evidence", "why_hold_or_change"]:
            research_column = f"research_{column}"
            if research_column in merged.columns:
                merged[column] = merged[column].where(merged[column].astype(str).str.strip().ne(""), merged[research_column])
        for column in _RESEARCH_NUMERIC_COLUMNS + ["fundamental_hard_risk"]:
            research_column = f"research_{column}"
            if research_column in merged.columns and column not in merged.columns:
                merged[column] = merged[research_column]
            elif research_column in merged.columns:
                merged[column] = merged[column].where(merged[column].notna(), merged[research_column])
    if not normalized_news.empty:
        merged = merged.merge(
            normalized_news[_NEWS_ENRICHMENT_COLUMNS],
            how="left",
            on=["trade_date", "asset_id"],
            suffixes=("", "_news"),
        )
    holdings = merged[merged["is_current_holding"].fillna(False)].copy()
    non_holdings = merged[~merged["is_current_holding"].fillna(False)].copy()

    holdings["_reduce_score"] = holdings.apply(_candidate_reduce_score, axis=1)
    non_holdings["_add_score"] = non_holdings.apply(_candidate_add_score, axis=1)

    candidate_adds = non_holdings.sort_values(
        ["_add_score", "shadow_top10_rank"],
        ascending=[False, True],
        kind="mergesort",
    ).head(_DOSSIER_CANDIDATE_SHORTLIST_SIZE).copy()
    candidate_reduces = holdings.sort_values(
        ["_reduce_score", "shadow_top10_rank"],
        ascending=[True, True],
        kind="mergesort",
    ).head(_DOSSIER_CANDIDATE_SHORTLIST_SIZE).copy()
    return (
        holdings.drop(columns=["_reduce_score"], errors="ignore"),
        candidate_adds.drop(columns=["_add_score"], errors="ignore"),
        candidate_reduces.drop(columns=["_reduce_score"], errors="ignore"),
    )


def _build_appendix_rows(
    *,
    normalized_review: pd.DataFrame,
    normalized_research: pd.DataFrame,
    normalized_news: pd.DataFrame,
    holdings: pd.DataFrame,
    candidate_adds: pd.DataFrame,
    candidate_reduces: pd.DataFrame,
) -> pd.DataFrame:
    if normalized_review.empty:
        return normalized_review.copy()
    membership = {
        **{asset_id: "candidate_add" for asset_id in candidate_adds.get("asset_id", pd.Series(dtype=object)).astype(str)},
        **{asset_id: "candidate_reduce" for asset_id in candidate_reduces.get("asset_id", pd.Series(dtype=object)).astype(str)},
        **{asset_id: "holding" for asset_id in holdings.get("asset_id", pd.Series(dtype=object)).astype(str)},
    }
    appendix = normalized_review.copy()
    if not normalized_research.empty:
        appendix = appendix.merge(
            normalized_research[
                ["asset_id", *_RESEARCH_NUMERIC_COLUMNS, "latest_pdf_risk_summary"]
            ],
            how="left",
            on="asset_id",
            suffixes=("", "_research"),
        )
        for column in _RESEARCH_NUMERIC_COLUMNS + ["latest_pdf_risk_summary"]:
            research_column = f"{column}_research"
            if research_column in appendix.columns:
                appendix[column] = appendix[column].where(appendix[column].notna(), appendix[research_column])
                appendix = appendix.drop(columns=[research_column], errors="ignore")
    if not normalized_news.empty:
        appendix = appendix.merge(
            normalized_news[
                [
                    "trade_date",
                    "asset_id",
                    "news_attention_level",
                    "news_risk_attention_flag",
                    "news_enrichment_quality_flag",
                ]
            ],
            how="left",
            on=["trade_date", "asset_id"],
        )
    appendix["dossier_bucket"] = appendix["asset_id"].astype(str).map(membership).fillna("unassigned")
    return appendix


def _build_dossier_summary_rows(
    *,
    normalized_review: pd.DataFrame,
    normalized_research: pd.DataFrame,
    normalized_news: pd.DataFrame,
    narrative: pd.DataFrame,
    holdings: pd.DataFrame,
    candidate_adds: pd.DataFrame,
    candidate_reduces: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "asset_id",
        "ts_code",
        "stock_name",
        "current_decision",
        "one_line_judgment",
        "core_support_points",
        "core_opposition_points",
        "is_candidate_add",
        "is_candidate_reduce",
        "trend_tag",
        "research_tag",
        "risk_tag",
        "rebalance_tag",
    ]
    if normalized_review.empty:
        return pd.DataFrame(columns=columns)

    merged = normalized_review.copy()
    if not normalized_research.empty:
        research = normalized_research.add_prefix("research_")
        merged = merged.merge(
            research,
            how="left",
            left_on="asset_id",
            right_on="research_asset_id",
        )
        for column in [
            "stock_name",
            "ts_code",
            "latest_pdf_risk_summary",
            "main_positive_evidence",
            "main_risk_evidence",
            "why_hold_or_change",
                "fundamental_hard_risk",
                *_RESEARCH_NUMERIC_COLUMNS,
        ]:
            research_column = f"research_{column}"
            if research_column in merged.columns and column not in merged.columns:
                merged[column] = merged[research_column]
            elif research_column in merged.columns:
                merged[column] = merged[column].where(merged[column].notna(), merged[research_column])
                if merged[column].dtype == object:
                    merged[column] = merged[column].where(
                        merged[column].astype(str).str.strip().ne(""),
                        merged[research_column],
                    )
    if not normalized_news.empty:
        merged = merged.merge(
            normalized_news[_NEWS_ENRICHMENT_COLUMNS],
            how="left",
            on=["trade_date", "asset_id"],
        )
    merged = _merge_narrative_columns(merged, narrative)

    holding_assets = set(holdings.get("asset_id", pd.Series(dtype=object)).astype(str))
    candidate_add_assets = set(candidate_adds.get("asset_id", pd.Series(dtype=object)).astype(str))
    candidate_reduce_assets = set(candidate_reduces.get("asset_id", pd.Series(dtype=object)).astype(str))

    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        narrative = _build_holding_narrative(row)
        asset_id = _safe_text(row.get("asset_id"))
        rows.append(
            {
                "asset_id": asset_id,
                "ts_code": _placeholder_text(row.get("ts_code")),
                "stock_name": _placeholder_text(row.get("stock_name")),
                "current_decision": narrative["current_conclusion"],
                "one_line_judgment": narrative["one_line_judgment"],
                "core_support_points": " | ".join(narrative["support_evidence"]),
                "core_opposition_points": " | ".join(narrative["oppose_evidence"]),
                "is_candidate_add": asset_id in candidate_add_assets,
                "is_candidate_reduce": asset_id in candidate_reduce_assets,
                "trend_tag": _format_section_label(row.get("section")) or "information_gap",
                "research_tag": _build_research_tag(row),
                "risk_tag": _build_risk_tag(row),
                "rebalance_tag": _build_rebalance_tag(
                    asset_id=asset_id,
                    final_label=_safe_text(row.get("final_label")),
                    why_hold_or_change=_safe_text(row.get("why_hold_or_change")),
                    holding_assets=holding_assets,
                    candidate_add_assets=candidate_add_assets,
                    candidate_reduce_assets=candidate_reduce_assets,
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _render_dossier_markdown(
    *,
    summary: dict[str, Any],
    holdings: pd.DataFrame,
    candidate_adds: pd.DataFrame,
    candidate_reduces: pd.DataFrame,
) -> str:
    lines = [f"# Mid Trend Position Dossier {summary['trade_date']}", ""]
    lines.extend(_render_executive_summary(summary))
    lines.extend(_render_holding_section(holdings))
    lines.extend(_render_candidate_add_section(candidate_adds))
    lines.extend(_render_candidate_reduce_section(candidate_reduces))
    return "\n".join(lines).strip() + "\n"


def _render_executive_summary(summary: dict[str, Any]) -> list[str]:
    return [
        "## 组合级执行摘要",
        f"- trade_date: {summary.get('trade_date', '')}",
        f"- mode: {summary.get('mode', '')}",
        f"- holding_count: {summary.get('holding_count', 0)}",
        f"- candidate_add_count: {summary.get('candidate_add_count', 0)}",
        f"- candidate_reduce_count: {summary.get('candidate_reduce_count', 0)}",
        f"- enhanced_sources_used: {summary.get('enhanced_sources_used', 'no')}",
        f"- news_enrichment_provided: {summary.get('news_enrichment_provided', 'no')}",
        f"- news_enrichment_used: {summary.get('news_enrichment_used', 'no')}",
        f"- matched_news_rows: {summary.get('matched_news_rows', 0)}",
        "",
    ]


def _render_holding_section(frame: pd.DataFrame) -> list[str]:
    lines = ["", "## 当前持仓 Top5"]
    if frame.empty:
        return [*lines, "- 无", ""]
    for index, (_, row) in enumerate(frame.iterrows(), start=1):
        identity = _render_security_heading(index, row)
        narrative = _build_holding_narrative(row)
        lines.extend(
            [
                f"### {identity}",
                f"- 当前结论：{narrative['current_conclusion']}",
                f"- 一句话判断：{narrative['one_line_judgment']}",
                "- 支持持有的 3 条核心证据",
                f"  1. {narrative['support_evidence'][0]}",
                f"  2. {narrative['support_evidence'][1]}",
                f"  3. {narrative['support_evidence'][2]}",
                "- 反对持有的 2 条核心证据",
                f"  1. {narrative['oppose_evidence'][0]}",
                f"  2. {narrative['oppose_evidence'][1]}",
                f"- 今天最关键观察点：{narrative['key_watch_point']}",
                f"- 它在涨什么：{narrative['what_is_working']}",
                f"- 行业/主线位置：{narrative['industry_theme_position']}",
                f"- 行业地位与产品地位：{narrative['industry_product_position']}",
                f"- 机构支持逻辑与分歧点：{narrative['institutional_logic']}",
                f"- 技术与趋势状态：{narrative['trend_status']}",
                *_render_news_section(row),
                f"- 主要风险与反例：{narrative['key_risks']}",
                f"- 证伪条件 / 继续跟踪点：{narrative['falsification_or_follow_up']}",
                "",
            ]
        )
    return lines


def _render_candidate_add_section(frame: pd.DataFrame) -> list[str]:
    lines = ["", "## 候选调入名单"]
    if frame.empty:
        return [*lines, "- 无", ""]
    for index, (_, row) in enumerate(frame.iterrows(), start=1):
        lines.extend(_render_candidate_section_entry(index=index, row=row, conclusion_label="调入结论", evidence_label="支持证据", risk_label="风险提示"))
    return lines


def _render_candidate_reduce_section(frame: pd.DataFrame) -> list[str]:
    lines = ["", "## 候选调出名单"]
    if frame.empty:
        return [*lines, "- 无", ""]
    for index, (_, row) in enumerate(frame.iterrows(), start=1):
        lines.extend(_render_candidate_section_entry(index=index, row=row, conclusion_label="调出结论", evidence_label="支持继续观察/调出证据", risk_label="风险或反例"))
    return lines


def _render_appendix_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["", "_No rows_", ""]
    columns = [
        "asset_id",
        "stock_name",
        "is_current_holding",
        "final_label",
        "why_hold_or_change",
        "research_support_score_pit",
        "target_price_median_pit",
        "pdf_profit_forecast_count_90d",
        "latest_pdf_risk_summary",
        "dossier_bucket",
    ]
    available = [column for column in columns if column in frame.columns]
    return _frame_to_markdown(frame[available])


def _render_security_heading(index: int, row: pd.Series) -> str:
    stock_name = _placeholder_text(row.get("stock_name"))
    symbol = _safe_text(row.get("ts_code")) or _safe_text(row.get("asset_id")) or "信息不足，需补充"
    return f"{index}. {stock_name}（{symbol}）"


def _build_holding_narrative(row: pd.Series) -> dict[str, str | list[str]]:
    industry_position_summary = _placeholder_text(row.get("industry_position_summary"))
    institution_view_summary = _placeholder_text(row.get("institution_view_summary"))
    return {
        "current_conclusion": _placeholder_text(row.get("final_label")),
        "one_line_judgment": _placeholder_text(row.get("one_line_judgment")),
        "support_evidence": [
            _placeholder_text(row.get("support_fact_1")),
            _placeholder_text(row.get("support_fact_2")),
            _placeholder_text(row.get("support_fact_3")),
        ],
        "oppose_evidence": [
            _placeholder_text(row.get("oppose_fact_1")),
            _placeholder_text(row.get("oppose_fact_2")),
        ],
        "key_watch_point": _placeholder_text(row.get("watch_point")),
        "what_is_working": _placeholder_text(row.get("what_is_working_summary")),
        "industry_theme_position": industry_position_summary,
        "industry_product_position": industry_position_summary,
        "institutional_logic": institution_view_summary,
        "trend_status": _render_trend_status(row),
        "key_risks": _placeholder_text(row.get("risk_summary")),
        "falsification_or_follow_up": _placeholder_text(row.get("falsification_condition")),
    }


def _render_candidate_section_entry(
    *,
    index: int,
    row: pd.Series,
    conclusion_label: str,
    evidence_label: str,
    risk_label: str,
) -> list[str]:
    narrative = _build_holding_narrative(row)
    return [
        f"### {_render_security_heading(index, row)}",
        f"- {conclusion_label}：{narrative['current_conclusion']}",
        f"- 核心理由：{narrative['one_line_judgment']}",
        f"- {evidence_label}：{narrative['support_evidence'][0]}",
        f"- {risk_label}：{narrative['oppose_evidence'][0]}",
        f"- 研究信号：{_render_research_signal(row)}",
        *_render_news_section(row),
        f"- 跟踪重点：{narrative['key_watch_point']}",
        "",
    ]


def _build_dossier_narrative(
    *,
    trade_date: str,
    mode: str,
    portfolio_review: pd.DataFrame,
    research_packet_candidates: pd.DataFrame,
) -> pd.DataFrame:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date=trade_date,
        mode=mode,
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet_candidates,
    )
    narrative = build_research_decision_narrative_from_fact_sheet(fact_sheet)
    if narrative.empty:
        return pd.DataFrame(columns=_NARRATIVE_JOIN_COLUMNS)
    available = [column for column in _NARRATIVE_JOIN_COLUMNS if column in narrative.columns]
    return narrative[available].copy()


def _normalize_dossier_news_enrichment(frame: pd.DataFrame | None, *, trade_date: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=_NEWS_ENRICHMENT_COLUMNS)
    result = frame.copy()
    if "trade_date" not in result.columns or "asset_id" not in result.columns:
        return pd.DataFrame(columns=_NEWS_ENRICHMENT_COLUMNS)
    requested_trade_date = pd.to_datetime(trade_date)
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result[result["trade_date"].eq(requested_trade_date)].copy()
    if result.empty:
        return pd.DataFrame(columns=_NEWS_ENRICHMENT_COLUMNS)
    for column in _NEWS_ENRICHMENT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    for column in [
        "news_compact_summary",
        "news_consensus_summary",
        "news_risk_summary",
        "theme_catalyst_summary",
        "overnight_catalyst_note",
        "news_attention_level",
        "news_enrichment_quality_flag",
    ]:
        result[column] = result[column].where(result[column].notna(), "")
    return (
        # Task 6 contract: if the same trade_date + asset_id appears multiple times
        # in the input file, dossier-side normalization resolves it by file-order
        # last-row-wins. This is intentionally not freshness-aware aggregation.
        result.sort_values(["trade_date"], kind="mergesort")
        .drop_duplicates(subset=["trade_date", "asset_id"], keep="last")
        .reindex(columns=_NEWS_ENRICHMENT_COLUMNS)
    )


def _build_news_enrichment_status(
    *,
    normalized_review: pd.DataFrame,
    normalized_news: pd.DataFrame,
    news_enrichment_provided: bool,
) -> dict[str, Any]:
    if not news_enrichment_provided:
        return {
            "news_enrichment_provided": "no",
            "news_enrichment_used": "no",
            "matched_news_rows": 0,
        }
    if normalized_review.empty or normalized_news.empty:
        return {
            "news_enrichment_provided": "yes",
            "news_enrichment_used": "no",
            "matched_news_rows": 0,
        }
    requested_keys = normalized_review[["trade_date", "asset_id"]].drop_duplicates()
    matched_rows = int(
        len(
            requested_keys.merge(
                normalized_news[["trade_date", "asset_id"]].drop_duplicates(),
                how="inner",
                on=["trade_date", "asset_id"],
            )
        )
    )
    return {
        "news_enrichment_provided": "yes",
        "news_enrichment_used": "yes" if matched_rows > 0 else "no",
        "matched_news_rows": matched_rows,
    }


def _merge_narrative_columns(frame: pd.DataFrame, narrative: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or narrative.empty or "asset_id" not in frame.columns:
        return frame.copy()
    merged = frame.merge(narrative, how="left", on="asset_id", suffixes=("", "_narrative"))
    for column in _NARRATIVE_JOIN_COLUMNS:
        if column == "asset_id" or column not in merged.columns:
            continue
        if merged[column].dtype == object:
            merged[column] = merged[column].where(merged[column].astype(str).str.strip().ne(""), pd.NA)
    return merged


def _render_institutional_logic(row: pd.Series) -> str:
    support_score = _placeholder_count_metric(row.get("research_support_score_pit"))
    coverage = _placeholder_count_metric(row.get("broker_coverage_count_pit"))
    hard_risk = _placeholder_text(row.get("fundamental_hard_risk"))
    return f"支持分 {support_score}；券商覆盖 {coverage}；硬风险标记 {hard_risk}。"


def _render_trend_status(row: pd.Series) -> str:
    section = _format_section_label(row.get("section"))
    if not section:
        return "信息不足，需补充"
    rank = _placeholder_count_metric(row.get("shadow_top10_rank"))
    weight = _placeholder_decimal_metric(row.get("weight"))
    return f"{section}持仓，影子排名 {rank}，当前权重 {weight}。"


def _render_research_signal(row: pd.Series) -> str:
    support_score = _placeholder_count_metric(row.get("research_support_score_pit"))
    broker_reports = _placeholder_count_metric(row.get("broker_report_count_90d"))
    target_price = _placeholder_decimal_metric(row.get("target_price_median_pit"))
    return f"支持分 {support_score}；90天券商报告数 {broker_reports}；目标价中位数 {target_price}。"


def _render_news_section(row: pd.Series) -> list[str]:
    if not _has_news_enrichment(row):
        return []
    return [
        "- 新闻/催化跟踪",
        f"  - 新闻短摘要：{_render_news_text(row.get('news_compact_summary'))}",
        f"  - 新闻关注度：{_render_news_attention_level(row.get('news_attention_level'))}",
        f"  - 新闻共识：{_render_news_text(row.get('news_consensus_summary'))}",
        f"  - 新闻风险：{_render_news_text(row.get('news_risk_summary'))}",
        f"  - 主题催化：{_render_news_text(row.get('theme_catalyst_summary'))}",
        f"  - 隔夜催化：{_render_news_text(row.get('overnight_catalyst_note'))}",
        f"  - 风险新闻关注：{_render_news_risk_flag(row.get('news_risk_attention_flag'))}",
    ]


def _has_news_enrichment(row: pd.Series) -> bool:
    return any(
        _safe_text(row.get(column))
        for column in [
            "news_consensus_summary",
            "news_risk_summary",
            "theme_catalyst_summary",
            "overnight_catalyst_note",
            "news_attention_level",
            "news_enrichment_quality_flag",
        ]
    ) or pd.notna(row.get("news_risk_attention_flag"))


def _render_news_text(value: object) -> str:
    text = _safe_text(value)
    return text or "信息不足，需补充"


def _render_news_attention_level(value: object) -> str:
    text = _safe_text(value)
    return text or "unknown"


def _render_news_risk_flag(value: object) -> str:
    if pd.isna(value):
        return "unknown"
    if bool(value):
        return "true"
    return "false"


def _build_research_tag(row: pd.Series) -> str:
    for column in [
        "research_support_score_pit",
        "broker_report_count_90d",
        "target_price_median_pit",
        "pdf_profit_forecast_count_90d",
        "latest_pdf_risk_summary",
    ]:
        value = row.get(column)
        if value is None or pd.isna(value):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return "enhanced_research"
    return "research_gap"


def _build_risk_tag(row: pd.Series) -> str:
    hard_risk = _safe_text(row.get("fundamental_hard_risk"))
    if hard_risk:
        return hard_risk
    if _safe_text(row.get("main_risk_evidence")) or _safe_text(row.get("latest_pdf_risk_summary")):
        return "risk_flagged"
    return "information_gap"


def _build_rebalance_tag(
    *,
    asset_id: str,
    final_label: str,
    why_hold_or_change: str,
    holding_assets: set[str],
    candidate_add_assets: set[str],
    candidate_reduce_assets: set[str],
) -> str:
    if asset_id in candidate_add_assets:
        return "candidate_add"
    if asset_id in candidate_reduce_assets and ("低优先级" in final_label or "观察" in why_hold_or_change):
        return "candidate_reduce"
    if asset_id in holding_assets:
        return "holding"
    if asset_id in candidate_reduce_assets:
        return "candidate_reduce"
    return "unassigned"


def _placeholder_text(value: Any) -> str:
    text = _safe_text(value)
    return text or "信息不足，需补充"


def _placeholder_metric(value: Any) -> str:
    if value is None or pd.isna(value):
        return "信息不足，需补充"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return str(value)
    text = _format_value(value)
    return text or "信息不足，需补充"


def _placeholder_count_metric(value: Any) -> str:
    if value is None or pd.isna(value):
        return "信息不足，需补充"
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "信息不足，需补充"
    if float(numeric).is_integer():
        return str(int(numeric))
    return str(numeric)


def _placeholder_decimal_metric(value: Any) -> str:
    if value is None or pd.isna(value):
        return "信息不足，需补充"
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "信息不足，需补充"
    return str(float(numeric))


def _placeholder_section_text(row: pd.Series) -> str:
    section = _format_section_label(row.get("section"))
    if not section:
        return "信息不足，需补充"
    return f"{section}，影子排名 {_placeholder_metric(row.get('shadow_top10_rank'))}。"


def _format_section_label(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    mapping = {
        "top5": "Top5",
        "top6_10": "Top6-10",
    }
    return mapping.get(text.lower(), text)


def _frame_to_markdown(frame: pd.DataFrame) -> list[str]:
    header = "| " + " | ".join(frame.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(frame.columns)) + " |"
    rows = [header, separator]
    for _, row in frame.iterrows():
        rows.append("| " + " | ".join(_format_markdown_cell(row[column]) for column in frame.columns) + " |")
    return ["", *rows, ""]


def _candidate_add_score(row: pd.Series) -> float:
    label = _safe_text(row.get("final_label"))
    return (
        (_CANDIDATE_ADD_LABEL_BONUS if "调入" in label else 0.0)
        + (_CANDIDATE_ADD_DISCUSSION_BONUS if "讨论" in label else 0.0)
        + _safe_float(row.get("research_support_score_pit"))
        + _CANDIDATE_ADD_BROKER_REPORT_WEIGHT * _safe_float(row.get("broker_report_count_90d"))
        - _CANDIDATE_ADD_RANK_PENALTY * _safe_float(row.get("shadow_top10_rank"), default=999.0)
    )


def _candidate_reduce_score(row: pd.Series) -> float:
    label = _safe_text(row.get("final_label"))
    return (
        (0.0 if "低优先级" in label else _CANDIDATE_REDUCE_NON_LOW_PRIORITY_PENALTY)
        + (0.0 if "观察" in _safe_text(row.get("why_hold_or_change")) else _CANDIDATE_REDUCE_NON_OBSERVATION_PENALTY)
        + _safe_float(row.get("research_support_score_pit"))
        + _CANDIDATE_REDUCE_BROKER_REPORT_WEIGHT * _safe_float(row.get("broker_report_count_90d"))
    )


def _has_enhanced_research(frame: pd.DataFrame) -> bool:
    if frame.empty:
        return False
    for column in ["target_price_median_pit", "pdf_profit_forecast_count_90d", "latest_pdf_risk_summary"]:
        if column not in frame.columns:
            continue
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series):
            if series.notna().any():
                return True
            continue
        if series.fillna("").astype(str).str.strip().ne("").any():
            return True
    return False


def _normalize_output_dir(output_dir: str | Path | None) -> Path:
    path = DEFAULT_OUTPUT_DIR if output_dir is None else Path(output_dir)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _empty_portfolio_review() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "trade_date",
            "asset_id",
            "ts_code",
            "stock_name",
            "section",
            "shadow_top10_rank",
            "weight",
            "final_label",
            "why_hold_or_change",
            "main_positive_evidence",
            "main_risk_evidence",
            "latest_pdf_risk_summary",
            "is_current_holding",
        ]
    )


def _empty_research() -> pd.DataFrame:
    return pd.DataFrame(columns=["trade_date", "asset_id", "ts_code", "stock_name", *_RESEARCH_NUMERIC_COLUMNS])


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return default
    return float(numeric)


def _format_markdown_cell(value: Any) -> str:
    text = _format_value(value)
    return text.replace("|", "\\|")


def _format_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
