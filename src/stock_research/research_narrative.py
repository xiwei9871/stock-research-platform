from __future__ import annotations

from typing import Any

import pandas as pd


_FACT_SHEET_COLUMNS = [
    "asset_id",
    "ts_code",
    "stock_name",
    "trade_date",
    "report_count_90d",
    "broker_coverage_count",
    "latest_rating",
    "target_price_median",
    "target_upside_median",
    "profit_forecast_count",
    "pdf_risk_section_count",
    "research_support_score",
    "research_confidence",
    "bull_case_summary",
    "key_growth_driver",
    "institution_consensus_note",
    "positive_rating_summary",
    "target_price_basis_note",
    "bear_case_summary",
    "key_risk_driver",
    "negative_research_note",
    "institution_disagreement_note",
    "risk_summary_compact",
    "industry_position_note",
    "product_position_note",
    "moat_or_scarcity_note",
    "industry_mainline_context",
    "theme_alignment_note",
    "analyst_core_assumption",
    "valuation_anchor_note",
    "expectation_dependency_note",
    "has_target_price",
    "has_profit_forecast",
    "has_industry_position",
    "has_product_position",
    "has_moat_note",
    "has_bull_case",
    "has_bear_case",
]

_NARRATIVE_COLUMNS = [
    "asset_id",
    "ts_code",
    "stock_name",
    "trade_date",
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
    "valuation_summary",
    "risk_summary",
    "decision_confidence",
    "narrative_quality_flag",
]

_RESEARCH_NUMERIC_COLUMNS = {
    "broker_report_count_90d": "report_count_90d",
    "broker_coverage_count_pit": "broker_coverage_count",
    "target_price_median_pit": "target_price_median",
    "target_upside_median_pit": "target_upside_median",
    "pdf_profit_forecast_count_90d": "profit_forecast_count",
    "pdf_risk_section_count_90d": "pdf_risk_section_count",
    "research_support_score_pit": "research_support_score",
}

_RESEARCH_TEXT_COLUMNS = [
    "asset_id",
    "ts_code",
    "stock_name",
    "latest_rating",
    "research_confidence",
    "institution_names",
    "industry_position_note",
    "product_position_note",
    "moat_or_scarcity_note",
    "negative_research_note",
    "valuation_note",
    "mainline_context",
    "mainline_status",
    "market_regime",
    "why_hold_or_change",
    "main_positive_evidence",
    "main_risk_evidence",
    "latest_pdf_risk_summary",
    "fundamental_hard_risk",
]

_REVIEW_TEXT_COLUMNS = [
    "asset_id",
    "ts_code",
    "stock_name",
    "section",
    "final_label",
    "why_hold_or_change",
    "main_positive_evidence",
    "main_risk_evidence",
    "latest_pdf_risk_summary",
]


def build_research_fact_sheet_from_frames(
    *,
    trade_date: str,
    mode: str,
    portfolio_review: pd.DataFrame,
    research_packet_candidates: pd.DataFrame,
) -> pd.DataFrame:
    normalized_review, normalized_research = _normalize_research_inputs(
        trade_date=trade_date,
        mode=mode,
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet_candidates,
    )
    return _build_fact_sheet_rows(
        trade_date=trade_date,
        normalized_review=normalized_review,
        normalized_research=normalized_research,
    )


def build_research_decision_narrative_from_fact_sheet(fact_sheet: pd.DataFrame) -> pd.DataFrame:
    if fact_sheet.empty:
        return pd.DataFrame(columns=_NARRATIVE_COLUMNS)

    rows: list[dict[str, Any]] = []
    for _, row in fact_sheet.iterrows():
        support_facts = _build_support_facts(row)
        oppose_facts = _build_oppose_facts(row)
        key_support = _first_non_empty(row.get("key_growth_driver"), row.get("bull_case_summary"))
        key_risk = _first_non_empty(row.get("key_risk_driver"), row.get("bear_case_summary"))
        industry_summary = _industry_position_summary(row)
        institution_summary = _institution_view_summary(row)
        valuation_summary = _valuation_summary(row)
        risk_summary = _risk_summary(row)
        watch_point = _watch_point(row)
        rows.append(
            {
                "asset_id": _safe_text(row.get("asset_id")),
                "ts_code": _safe_text(row.get("ts_code")),
                "stock_name": _safe_text(row.get("stock_name")),
                "trade_date": _safe_text(row.get("trade_date")),
                "one_line_judgment": _one_line_judgment(row, key_risk=key_risk),
                "support_fact_1": _fact_at(support_facts, 0),
                "support_fact_2": _fact_at(support_facts, 1),
                "support_fact_3": _fact_at(support_facts, 2),
                "oppose_fact_1": _fact_at(oppose_facts, 0),
                "oppose_fact_2": _fact_at(oppose_facts, 1),
                "watch_point": watch_point,
                "falsification_condition": _degrade_text(key_risk, row.get("risk_summary_compact")),
                "what_is_working_summary": _degrade_text(key_support),
                "industry_position_summary": industry_summary,
                "institution_view_summary": institution_summary,
                "valuation_summary": valuation_summary,
                "risk_summary": risk_summary,
                "decision_confidence": _safe_text(row.get("research_confidence")) or "thin",
                "narrative_quality_flag": _narrative_quality_flag(row),
            }
        )
    return pd.DataFrame(rows, columns=_NARRATIVE_COLUMNS)


def _normalize_research_inputs(
    *,
    trade_date: str,
    mode: str,
    portfolio_review: pd.DataFrame,
    research_packet_candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    requested_trade_date = pd.to_datetime(trade_date)
    normalized_review = portfolio_review.copy()
    if normalized_review.empty:
        normalized_review = pd.DataFrame(columns=_REVIEW_TEXT_COLUMNS + ["trade_date"])
    if "trade_date" not in normalized_review.columns:
        normalized_review["trade_date"] = requested_trade_date
    normalized_review["trade_date"] = pd.to_datetime(normalized_review["trade_date"], errors="coerce")
    normalized_review = normalized_review[normalized_review["trade_date"].eq(requested_trade_date)].copy()
    for column in _REVIEW_TEXT_COLUMNS:
        if column not in normalized_review.columns:
            normalized_review[column] = ""
    normalized_review["final_label"] = normalized_review["final_label"].map(_safe_text)
    normalized_review["ts_code"] = normalized_review.apply(
        lambda row: _first_non_empty(row.get("ts_code"), _ts_code_from_asset_id(row.get("asset_id"))),
        axis=1,
    )
    normalized_review["stock_name"] = normalized_review.apply(
        lambda row: _first_non_empty(row.get("stock_name"), row.get("ts_code")),
        axis=1,
    )
    if "shadow_top10_rank" not in normalized_review.columns:
        normalized_review["shadow_top10_rank"] = pd.NA
    normalized_review["shadow_top10_rank"] = pd.to_numeric(normalized_review["shadow_top10_rank"], errors="coerce")
    normalized_review = normalized_review.reset_index(drop=True)
    normalized_review["_source_order"] = range(len(normalized_review))
    normalized_review = normalized_review.sort_values(
        ["shadow_top10_rank", "section", "_source_order"],
        ascending=[True, True, True],
        kind="mergesort",
        na_position="last",
    )
    normalized_review["trade_date"] = normalized_review["trade_date"].dt.strftime("%Y-%m-%d")
    normalized_review = normalized_review.drop_duplicates(subset=["asset_id"], keep="first").drop(
        columns=["_source_order"],
        errors="ignore",
    )

    normalized_research = research_packet_candidates.copy()
    if normalized_research.empty or "asset_id" not in normalized_research.columns:
        return normalized_review, pd.DataFrame(columns=["trade_date", "_source_order", *_RESEARCH_TEXT_COLUMNS, *_RESEARCH_NUMERIC_COLUMNS.keys()])
    normalized_research = normalized_research.reset_index(drop=True)
    normalized_research["_source_order"] = range(len(normalized_research))
    if "trade_date" not in normalized_research.columns:
        normalized_research["trade_date"] = pd.NaT
    normalized_research["trade_date"] = pd.to_datetime(normalized_research["trade_date"], errors="coerce")
    normalized_research = normalized_research[normalized_research["trade_date"].notna()].copy()
    if mode == "replay":
        normalized_research = normalized_research[normalized_research["trade_date"].le(requested_trade_date)].copy()
    else:
        normalized_research = normalized_research[normalized_research["trade_date"].le(requested_trade_date)].copy()
    for column in _RESEARCH_TEXT_COLUMNS:
        if column not in normalized_research.columns:
            normalized_research[column] = ""
    for source_column in _RESEARCH_NUMERIC_COLUMNS:
        if source_column not in normalized_research.columns:
            normalized_research[source_column] = pd.NA
        normalized_research[source_column] = pd.to_numeric(normalized_research[source_column], errors="coerce")
    normalized_research["ts_code"] = normalized_research.apply(
        lambda row: _first_non_empty(row.get("ts_code"), _ts_code_from_asset_id(row.get("asset_id"))),
        axis=1,
    )
    normalized_research["stock_name"] = normalized_research.apply(
        lambda row: _first_non_empty(row.get("stock_name"), row.get("ts_code")),
        axis=1,
    )
    normalized_research = normalized_research.sort_values(
        ["trade_date", "_source_order"],
        ascending=[True, True],
        kind="mergesort",
    )
    normalized_research = normalized_research.drop_duplicates(subset=["asset_id"], keep="last")
    return normalized_review, normalized_research


def _build_fact_sheet_rows(
    *,
    trade_date: str,
    normalized_review: pd.DataFrame,
    normalized_research: pd.DataFrame,
) -> pd.DataFrame:
    if normalized_review.empty:
        return pd.DataFrame(columns=_FACT_SHEET_COLUMNS)

    research_by_asset = (
        normalized_research.set_index("asset_id", drop=False) if not normalized_research.empty else pd.DataFrame()
    )
    rows: list[dict[str, Any]] = []
    for _, review_row in normalized_review.iterrows():
        asset_id = _safe_text(review_row.get("asset_id"))
        research_row = _row_for_asset(research_by_asset, asset_id)
        ts_code = _first_non_empty(review_row.get("ts_code"), _value_from_row(research_row, "ts_code"), _ts_code_from_asset_id(asset_id))
        stock_name = _first_non_empty(review_row.get("stock_name"), _value_from_row(research_row, "stock_name"), ts_code)
        numeric_metrics = _mapped_numeric_values(research_row)
        report_count = numeric_metrics["report_count_90d"]
        coverage_count = numeric_metrics["broker_coverage_count"]
        latest_rating = _safe_text(_value_from_row(research_row, "latest_rating"))
        target_price = numeric_metrics["target_price_median"]
        target_upside = numeric_metrics["target_upside_median"]
        profit_forecast_count = numeric_metrics["profit_forecast_count"]
        pdf_risk_section_count = numeric_metrics["pdf_risk_section_count"]
        research_support_score = numeric_metrics["research_support_score"]
        main_positive_evidence = _first_non_empty(
            _value_from_row(research_row, "main_positive_evidence"),
            review_row.get("main_positive_evidence"),
        )
        main_risk_evidence = _first_non_empty(
            _value_from_row(research_row, "main_risk_evidence"),
            review_row.get("main_risk_evidence"),
        )
        why_hold_or_change = _first_non_empty(
            review_row.get("why_hold_or_change"),
            _value_from_row(research_row, "why_hold_or_change"),
        )
        risk_summary = _first_non_empty(
            _value_from_row(research_row, "latest_pdf_risk_summary"),
            review_row.get("latest_pdf_risk_summary"),
            main_risk_evidence,
        )
        industry_position_note = _safe_text(_value_from_row(research_row, "industry_position_note"))
        product_position_note = _safe_text(_value_from_row(research_row, "product_position_note"))
        moat_note = _safe_text(_value_from_row(research_row, "moat_or_scarcity_note"))
        negative_research_note = _first_non_empty(
            _value_from_row(research_row, "negative_research_note"),
            main_risk_evidence,
        )
        institution_names = _safe_text(_value_from_row(research_row, "institution_names"))
        mainline_context = _first_non_empty(
            _value_from_row(research_row, "mainline_context"),
            _value_from_row(research_row, "mainline_status"),
            _value_from_row(research_row, "market_regime"),
        )
        confidence = _first_non_empty(
            _safe_text(_value_from_row(research_row, "research_confidence")),
            _derive_research_confidence(
                report_count_90d=report_count,
                research_support_score=research_support_score,
                has_bull_case=_has_text(main_positive_evidence) or _has_text(why_hold_or_change),
                has_bear_case=_has_text(main_risk_evidence) or _has_text(risk_summary),
            ),
        )
        has_target_price = pd.notna(target_price)
        has_profit_forecast = pd.notna(profit_forecast_count) and float(profit_forecast_count) > 0
        has_industry_position = _has_text(industry_position_note)
        has_product_position = _has_text(product_position_note)
        has_moat_note = _has_text(moat_note)
        has_bull_case = _has_text(why_hold_or_change) or _has_text(main_positive_evidence)
        has_bear_case = _has_text(main_risk_evidence) or _has_text(risk_summary) or _has_text(negative_research_note)

        rows.append(
            {
                "asset_id": asset_id,
                "ts_code": ts_code,
                "stock_name": stock_name,
                "trade_date": trade_date,
                "report_count_90d": report_count,
                "broker_coverage_count": coverage_count,
                "latest_rating": latest_rating,
                "target_price_median": target_price,
                "target_upside_median": target_upside,
                "profit_forecast_count": profit_forecast_count,
                "pdf_risk_section_count": pdf_risk_section_count,
                "research_support_score": research_support_score,
                "research_confidence": confidence,
                "bull_case_summary": _first_non_empty(why_hold_or_change, main_positive_evidence),
                "key_growth_driver": main_positive_evidence,
                "institution_consensus_note": _institution_consensus_note(
                    institution_names=institution_names,
                    report_count_90d=report_count,
                    coverage_count=coverage_count,
                    latest_rating=latest_rating,
                ),
                "positive_rating_summary": _positive_rating_summary(latest_rating=latest_rating, report_count_90d=report_count),
                "target_price_basis_note": _target_price_basis_note(
                    target_price=target_price,
                    target_upside=target_upside,
                    latest_rating=latest_rating,
                ),
                "bear_case_summary": _first_non_empty(main_risk_evidence, risk_summary),
                "key_risk_driver": main_risk_evidence,
                "negative_research_note": negative_research_note,
                "institution_disagreement_note": _institution_disagreement_note(
                    institution_names=institution_names,
                    negative_research_note=negative_research_note,
                    risk_summary=risk_summary,
                ),
                "risk_summary_compact": risk_summary,
                "industry_position_note": industry_position_note,
                "product_position_note": product_position_note,
                "moat_or_scarcity_note": moat_note,
                "industry_mainline_context": mainline_context,
                "theme_alignment_note": _theme_alignment_note(
                    final_label=review_row.get("final_label"),
                    mainline_context=mainline_context,
                ),
                "analyst_core_assumption": _first_non_empty(why_hold_or_change, main_positive_evidence),
                "valuation_anchor_note": _first_non_empty(
                    _safe_text(_value_from_row(research_row, "valuation_note")),
                    _target_price_basis_note(
                        target_price=target_price,
                        target_upside=target_upside,
                        latest_rating=latest_rating,
                    ),
                ),
                "expectation_dependency_note": _expectation_dependency_note(
                    target_upside=target_upside,
                    risk_summary=risk_summary,
                    fundamental_hard_risk=_safe_text(_value_from_row(research_row, "fundamental_hard_risk")),
                ),
                "has_target_price": has_target_price,
                "has_profit_forecast": has_profit_forecast,
                "has_industry_position": has_industry_position,
                "has_product_position": has_product_position,
                "has_moat_note": has_moat_note,
                "has_bull_case": has_bull_case,
                "has_bear_case": has_bear_case,
            }
        )
    return pd.DataFrame(rows, columns=_FACT_SHEET_COLUMNS)


def _row_for_asset(frame: pd.DataFrame, asset_id: str) -> pd.Series | None:
    if frame.empty or asset_id not in frame.index:
        return None
    row = frame.loc[asset_id]
    if isinstance(row, pd.DataFrame):
        return row.iloc[-1]
    return row


def _mapped_numeric_values(row: pd.Series | None) -> dict[str, Any]:
    return {
        target_column: _numeric_or_na(_value_from_row(row, source_column))
        for source_column, target_column in _RESEARCH_NUMERIC_COLUMNS.items()
    }


def _value_from_row(row: pd.Series | None, column: str) -> Any:
    if row is None:
        return ""
    return row.get(column, "")


def _numeric_or_na(value: Any) -> Any:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return pd.NA
    return numeric.item() if hasattr(numeric, "item") else numeric


def _has_text(value: Any) -> bool:
    return _safe_text(value) != ""


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return ""


def _ordered_unique_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _fact_at(facts: list[str], index: int) -> str:
    if index < len(facts):
        return facts[index]
    return "信息不足，需补充"


def _build_support_facts(row: pd.Series) -> list[str]:
    return _ordered_unique_texts(
        [
            row.get("key_growth_driver"),
            row.get("institution_consensus_note"),
            row.get("target_price_basis_note"),
            row.get("positive_rating_summary"),
            row.get("bull_case_summary"),
            row.get("industry_position_note"),
            row.get("product_position_note"),
            row.get("moat_or_scarcity_note"),
            row.get("industry_mainline_context"),
        ]
    )


def _build_oppose_facts(row: pd.Series) -> list[str]:
    return _ordered_unique_texts(
        [
            row.get("key_risk_driver"),
            row.get("risk_summary_compact"),
            row.get("negative_research_note"),
            row.get("institution_disagreement_note"),
        ]
    )


def _one_line_judgment(row: pd.Series, *, key_risk: str) -> str:
    bull_summary = _first_non_empty(row.get("bull_case_summary"), row.get("analyst_core_assumption"))
    if bull_summary and key_risk:
        return f"{bull_summary}但反证仍需盯住{key_risk}"
    return _degrade_text(bull_summary, row.get("analyst_core_assumption"))


def _watch_point(row: pd.Series) -> str:
    expectation_note = _meaningful_expectation_note(row.get("expectation_dependency_note"))
    return _degrade_text(
        expectation_note,
        row.get("risk_summary_compact"),
        row.get("institution_disagreement_note"),
    )


def _industry_position_summary(row: pd.Series) -> str:
    return _join_sentences(
        [
            row.get("industry_position_note"),
            row.get("product_position_note"),
            row.get("moat_or_scarcity_note"),
            row.get("industry_mainline_context"),
        ]
    )


def _institution_view_summary(row: pd.Series) -> str:
    disagreement_note = _safe_text(row.get("institution_disagreement_note"))
    if disagreement_note in {
        _safe_text(row.get("key_risk_driver")),
        _safe_text(row.get("risk_summary_compact")),
    }:
        disagreement_note = ""
    return _join_segments(
        [
            row.get("institution_consensus_note"),
            row.get("positive_rating_summary"),
            disagreement_note,
        ]
    )


def _valuation_summary(row: pd.Series) -> str:
    return _join_sentences(
        [
            row.get("valuation_anchor_note"),
            _meaningful_expectation_note(row.get("expectation_dependency_note")),
        ]
    )


def _risk_summary(row: pd.Series) -> str:
    return _join_sentences([row.get("key_risk_driver"), row.get("risk_summary_compact")])


def _meaningful_expectation_note(value: Any) -> str:
    text = _safe_text(value)
    if text in {"", "no_clear_hard_risk"}:
        return ""
    return text


def _degrade_text(*values: Any) -> str:
    text = _first_non_empty(*values)
    return text or "信息不足，需补充"


def _join_segments(values: list[Any]) -> str:
    segments = _ordered_unique_texts(list(values))
    if not segments:
        return "信息不足，需补充"
    return "；".join(segments)


def _join_sentences(values: list[Any]) -> str:
    sentences = _ordered_unique_texts(list(values))
    if not sentences:
        return "信息不足，需补充"
    combined = sentences[0]
    for sentence in sentences[1:]:
        if combined.endswith(("。", "！", "？")):
            combined += sentence
        else:
            combined += f"。{sentence}"
    return combined


def _derive_research_confidence(
    *,
    report_count_90d: Any,
    research_support_score: Any,
    has_bull_case: bool,
    has_bear_case: bool,
) -> str:
    report_count = pd.to_numeric(report_count_90d, errors="coerce")
    support_score = pd.to_numeric(research_support_score, errors="coerce")
    if pd.notna(report_count) and float(report_count) >= 3 and pd.notna(support_score) and float(support_score) >= 30:
        return "rich"
    if has_bull_case and has_bear_case:
        return "medium"
    return "thin"


def _institution_consensus_note(
    *,
    institution_names: str,
    report_count_90d: Any,
    coverage_count: Any,
    latest_rating: str,
) -> str:
    if institution_names:
        return institution_names
    details = []
    if latest_rating:
        details.append(f"最新评级：{latest_rating}")
    if pd.notna(report_count_90d):
        details.append(f"近90天研报{int(float(report_count_90d))}篇")
    if pd.notna(coverage_count):
        details.append(f"覆盖机构{int(float(coverage_count))}家")
    return "；".join(details)


def _positive_rating_summary(*, latest_rating: str, report_count_90d: Any) -> str:
    details = []
    if latest_rating:
        details.append(f"评级：{latest_rating}")
    if pd.notna(report_count_90d):
        details.append(f"90天覆盖{int(float(report_count_90d))}篇")
    return "；".join(details)


def _target_price_basis_note(*, target_price: Any, target_upside: Any, latest_rating: str) -> str:
    if pd.isna(pd.to_numeric(target_price, errors="coerce")):
        return ""
    details = [f"目标价中位数{float(target_price):g}"]
    if pd.notna(pd.to_numeric(target_upside, errors="coerce")):
        details.append(f"目标涨幅中位数{float(target_upside):.0%}")
    if latest_rating:
        details.append(f"参考评级{latest_rating}")
    return "；".join(details)


def _institution_disagreement_note(*, institution_names: str, negative_research_note: str, risk_summary: str) -> str:
    if institution_names and negative_research_note:
        return f"{institution_names}存在偏谨慎观点"
    if negative_research_note and risk_summary and negative_research_note != risk_summary:
        return negative_research_note
    return ""


def _theme_alignment_note(*, final_label: Any, mainline_context: str) -> str:
    label = _safe_text(final_label)
    if not label and not mainline_context:
        return ""
    if mainline_context:
        return f"{label}；主线环境：{mainline_context}" if label else f"主线环境：{mainline_context}"
    return label


def _expectation_dependency_note(*, target_upside: Any, risk_summary: str, fundamental_hard_risk: str) -> str:
    upside = pd.to_numeric(target_upside, errors="coerce")
    if pd.notna(upside):
        return f"后续兑现依赖目标涨幅假设继续成立（{float(upside):.0%}）。"
    if fundamental_hard_risk:
        return fundamental_hard_risk
    return risk_summary


def _narrative_quality_flag(row: pd.Series) -> str:
    support_count = len(_build_support_facts(row))
    oppose_count = len(_build_oppose_facts(row))
    has_industry_view = _industry_position_summary(row) != "信息不足，需补充"
    has_institution_view = _institution_view_summary(row) != "信息不足，需补充"
    has_valuation_view = _valuation_summary(row) != "信息不足，需补充"
    if support_count >= 3 and oppose_count >= 2 and has_industry_view and has_institution_view and has_valuation_view:
        return "rich"
    if support_count >= 2 and oppose_count >= 1 and (has_institution_view or has_valuation_view):
        return "medium"
    return "thin"


def _ts_code_from_asset_id(asset_id: Any) -> str:
    parts = str(asset_id or "").split(":")
    if len(parts) == 3 and parts[0] == "CN" and parts[1] in {"SH", "SZ", "BJ"}:
        return f"{parts[2]}.{parts[1]}"
    return ""
