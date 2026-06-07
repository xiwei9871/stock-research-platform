from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_infra.mid_trend_integration import (
    build_mid_trend_review_with_research_infra,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "research"


def build_mid_trend_portfolio_review_from_frames(
    *,
    trade_date: str,
    strategy_variant: str,
    top10: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    research_packet_candidates: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized_top10 = _normalize_top10(top10, trade_date)
    normalized_holdings = _normalize_holdings(holdings, trade_date, strategy_variant)
    normalized_trades = _normalize_trades(trades, trade_date, strategy_variant)
    normalized_research = _normalize_research(research_packet_candidates, trade_date)

    review_rows = _build_review_rows(
        normalized_top10=normalized_top10,
        normalized_holdings=normalized_holdings,
        normalized_trades=normalized_trades,
        normalized_research=normalized_research,
    )
    portfolio_summary = _build_portfolio_summary(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        review_rows=review_rows,
        holdings=normalized_holdings,
        trades=normalized_trades,
    )
    markdown = _render_markdown(portfolio_summary, review_rows)

    result: dict[str, Any] = {
        "portfolio_summary": portfolio_summary,
        "review_rows": review_rows,
        "markdown": markdown,
        "paths": {},
    }
    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        csv_path = output_path / f"mid_trend_portfolio_review_{trade_date}.csv"
        md_path = output_path / f"mid_trend_portfolio_review_{trade_date}.md"
        review_rows.to_csv(csv_path, index=False)
        md_path.write_text(markdown, encoding="utf-8")
        result["paths"] = {"csv": str(csv_path), "md": str(md_path), "report": str(md_path)}
    return result


def run_mid_trend_portfolio_review(
    *,
    trade_date: str,
    strategy_variant: str,
    top10_path: str | Path,
    holdings_path: str | Path,
    trades_path: str | Path,
    research_packet_path: str | Path,
    output_dir: str | Path | None = None,
    write_research_infra: bool = False,
) -> dict[str, Any]:
    normalized_output_dir = _normalize_output_dir(output_dir)
    top10 = pd.read_csv(top10_path)
    holdings = pd.read_csv(holdings_path)
    trades = pd.read_csv(trades_path)
    research_packet_candidates = pd.read_csv(research_packet_path)

    def build_review() -> dict[str, Any]:
        return build_mid_trend_portfolio_review_from_frames(
            trade_date=trade_date,
            strategy_variant=strategy_variant,
            top10=top10,
            holdings=holdings,
            trades=trades,
            research_packet_candidates=research_packet_candidates,
            output_dir=normalized_output_dir,
        )

    return build_mid_trend_review_with_research_infra(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        review_builder=build_review,
        output_dir=normalized_output_dir,
        write_research_infra=write_research_infra,
    )


def _normalize_output_dir(output_dir: str | Path | None) -> Path:
    path = DEFAULT_OUTPUT_DIR if output_dir is None else Path(output_dir)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _normalize_top10(frame: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return _empty_review_rows()
    result["trade_date"] = pd.to_datetime(result.get("trade_date"), errors="coerce")
    result = result[result["trade_date"].eq(pd.to_datetime(trade_date))].copy()
    if result.empty:
        return _empty_review_rows()
    for column in [
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "market_regime",
        "mainline_status",
        "mid_trend_layer",
    ]:
        if column not in result.columns:
            result[column] = ""
    if "shadow_top10_rank" not in result.columns:
        result["shadow_top10_rank"] = np.nan
    result["shadow_top10_rank"] = pd.to_numeric(result["shadow_top10_rank"], errors="coerce")
    result["candidate_rank"] = result["shadow_top10_rank"]
    return result


def _normalize_holdings(frame: pd.DataFrame, trade_date: str, strategy_variant: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    if "variant_name" not in result.columns or "rebalance_date" not in result.columns:
        return result.iloc[0:0].copy()
    result["rebalance_date"] = pd.to_datetime(result["rebalance_date"], errors="coerce")
    requested_trade_date = pd.to_datetime(trade_date)
    result = result[
        result["variant_name"].eq(strategy_variant)
        & result["rebalance_date"].notna()
        & result["rebalance_date"].le(requested_trade_date)
    ].copy()
    if result.empty:
        return result
    latest_rebalance_date = result["rebalance_date"].max()
    result = result[result["rebalance_date"].eq(latest_rebalance_date)].copy()
    if "asset_id" not in result.columns:
        result["asset_id"] = ""
    if "weight" in result.columns:
        result["target_weight"] = pd.to_numeric(result["weight"], errors="coerce")
    elif "target_weight" not in result.columns:
        result["target_weight"] = np.nan
    return result.drop_duplicates(subset=["asset_id"], keep="last")


def _normalize_trades(frame: pd.DataFrame, trade_date: str, strategy_variant: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    if "variant_name" not in result.columns or "trade_date" not in result.columns:
        return result.iloc[0:0].copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result[result["variant_name"].eq(strategy_variant) & result["trade_date"].eq(pd.to_datetime(trade_date))].copy()
    if "asset_id" not in result.columns:
        result["asset_id"] = ""
    if "side" not in result.columns:
        result["side"] = ""
    if "reason" not in result.columns:
        result["reason"] = ""
    return result


def _normalize_research(frame: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    if "trade_date" not in result.columns or "asset_id" not in result.columns:
        return result.iloc[0:0].copy()
    result = result.reset_index(drop=True)
    result["_source_order"] = np.arange(len(result))
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    requested_trade_date = pd.to_datetime(trade_date)
    result = result[result["trade_date"].eq(requested_trade_date)].copy()
    defaults: dict[str, Any] = {
        "ts_code": "",
        "broker_report_count_90d": np.nan,
        "research_support_score_pit": np.nan,
        "pdf_target_price_count_90d": np.nan,
        "pdf_profit_forecast_count_90d": np.nan,
        "pdf_risk_section_count_90d": np.nan,
        "latest_pdf_risk_summary": "",
        "fundamental_hard_risk": "",
        "main_positive_evidence": "",
        "main_risk_evidence": "",
        "why_hold_or_change": "",
    }
    for column, default_value in defaults.items():
        if column not in result.columns:
            result[column] = default_value
    for column in [
        "broker_report_count_90d",
        "research_support_score_pit",
        "pdf_target_price_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
    ]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.sort_values(["trade_date", "_source_order"], ascending=[True, True], kind="mergesort")
    result = result.drop_duplicates(subset=["asset_id"], keep="last").drop(columns=["_source_order"], errors="ignore")
    return result


def _build_review_rows(
    *,
    normalized_top10: pd.DataFrame,
    normalized_holdings: pd.DataFrame,
    normalized_trades: pd.DataFrame,
    normalized_research: pd.DataFrame,
) -> pd.DataFrame:
    if normalized_top10.empty and normalized_holdings.empty:
        return _empty_review_rows()

    holding_assets = set(normalized_holdings.get("asset_id", pd.Series(dtype=str)).astype(str))
    rebalance_triggered = not normalized_trades.empty
    if not normalized_trades.empty and "side" in normalized_trades.columns:
        trade_sides = normalized_trades["side"].astype(str).str.lower()
        buy_assets = set(normalized_trades.loc[trade_sides.eq("buy"), "asset_id"].astype(str))
        sell_assets = set(normalized_trades.loc[trade_sides.eq("sell"), "asset_id"].astype(str))
    else:
        buy_assets = set()
        sell_assets = set()
    research_by_asset = normalized_research.set_index("asset_id", drop=False) if not normalized_research.empty else pd.DataFrame()
    holdings_by_asset = (
        normalized_holdings.set_index("asset_id", drop=False) if not normalized_holdings.empty else pd.DataFrame()
    )
    top10_by_asset = normalized_top10.set_index("asset_id", drop=False) if not normalized_top10.empty else pd.DataFrame()
    stock_name_lookup = _load_review_stock_name_lookup(
        sorted(
            {
                _safe_text(code).upper()
                for code in pd.concat(
                    [
                        normalized_top10.get("ts_code", pd.Series(dtype=object)),
                        normalized_research.get("ts_code", pd.Series(dtype=object)),
                        normalized_holdings.get("asset_id", pd.Series(dtype=object)).map(_ts_code_from_asset_id),
                    ],
                    ignore_index=True,
                ).tolist()
                if _safe_text(code)
            }
        )
    )

    rows: list[dict[str, Any]] = []
    rendered_assets: set[str] = set()
    has_current_holdings = not normalized_holdings.empty

    if has_current_holdings:
        for _, holding in normalized_holdings.iterrows():
            asset_id = str(holding.get("asset_id", ""))
            rendered_assets.add(asset_id)
            top10_row = _row_for_asset(top10_by_asset, asset_id)
            review_row = _build_single_review_row(
                asset_id=asset_id,
                section="top5",
                candidate_source_row=top10_row,
                holdings_by_asset=holdings_by_asset,
                research_by_asset=research_by_asset,
                normalized_trades=normalized_trades,
                holding_assets=holding_assets,
                buy_assets=buy_assets,
                sell_assets=sell_assets,
                rebalance_triggered=rebalance_triggered,
                stock_name_lookup=stock_name_lookup,
            )
            if review_row is not None:
                rows.append(review_row)

    for _, row in normalized_top10.sort_values("candidate_rank", ascending=True).iterrows():
        asset_id = str(row.get("asset_id", ""))
        if asset_id in rendered_assets:
            continue
        candidate_rank = row.get("candidate_rank")
        if not _is_integral_candidate_rank(candidate_rank):
            continue
        candidate_rank_int = int(_safe_numeric(candidate_rank))
        section = "top6_10" if has_current_holdings else ("top5" if candidate_rank_int <= 5 else "top6_10")
        review_row = _build_single_review_row(
            asset_id=asset_id,
            section=section,
            candidate_source_row=row,
            holdings_by_asset=holdings_by_asset,
            research_by_asset=research_by_asset,
            normalized_trades=normalized_trades,
            holding_assets=holding_assets,
            buy_assets=buy_assets,
            sell_assets=sell_assets,
            rebalance_triggered=rebalance_triggered,
            stock_name_lookup=stock_name_lookup,
        )
        if review_row is not None:
            rows.append(review_row)

    review_rows = pd.DataFrame(rows)
    if review_rows.empty:
        return _empty_review_rows()
    return review_rows.reset_index(drop=True)


def _build_single_review_row(
    *,
    asset_id: str,
    section: str,
    candidate_source_row: pd.Series,
    holdings_by_asset: pd.DataFrame,
    research_by_asset: pd.DataFrame,
    normalized_trades: pd.DataFrame,
    holding_assets: set[str],
    buy_assets: set[str],
    sell_assets: set[str],
    rebalance_triggered: bool,
    stock_name_lookup: dict[str, str],
) -> dict[str, Any] | None:
    candidate_rank = candidate_source_row.get("candidate_rank")
    candidate_rank_value = _safe_numeric(candidate_rank)
    candidate_rank_int = int(candidate_rank_value) if _is_integral_candidate_rank(candidate_rank_value) else np.nan
    if section == "top6_10" and np.isnan(candidate_rank_int):
        return None
    research_row = _row_for_asset(research_by_asset, asset_id)
    holding_row = _row_for_asset(holdings_by_asset, asset_id)
    is_current_holding = asset_id in holding_assets
    is_new_buy = asset_id in buy_assets
    is_candidate_sell = asset_id in sell_assets
    research_support_score = _safe_numeric(research_row.get("research_support_score_pit"))
    why_hold_or_change = _why_hold_or_change(
        is_new_buy=is_new_buy,
        is_candidate_sell=is_candidate_sell,
        is_current_holding=is_current_holding,
        rebalance_triggered=rebalance_triggered,
    )
    final_label = _final_label(
        section=section,
        is_current_holding=is_current_holding,
        is_new_buy=is_new_buy,
        is_candidate_sell=is_candidate_sell,
        research_support_score_pit=research_support_score,
    )
    ts_code = _safe_text(
        _coalesce(
            candidate_source_row.get("ts_code"),
            research_row.get("ts_code"),
            _ts_code_from_asset_id(asset_id),
        )
    )
    stock_name = _resolve_review_stock_name(
        top10_name=candidate_source_row.get("stock_name"),
        research_name=research_row.get("stock_name"),
        asset_id=asset_id,
        ts_code=ts_code,
        lookup=stock_name_lookup,
    )
    trend_evidence = _build_trend_evidence(
        market_regime=candidate_source_row.get("market_regime"),
        mainline_status=candidate_source_row.get("mainline_status"),
        mid_trend_layer=candidate_source_row.get("mid_trend_layer"),
        mid_trend_funnel_score=candidate_source_row.get("mid_trend_funnel_score"),
    )
    research_evidence = _build_research_evidence(
        research_support_score_pit=research_support_score,
        broker_report_count_90d=research_row.get("broker_report_count_90d"),
        pdf_target_price_count_90d=research_row.get("pdf_target_price_count_90d"),
        pdf_profit_forecast_count_90d=research_row.get("pdf_profit_forecast_count_90d"),
        existing_text=research_row.get("main_positive_evidence"),
    )
    risk_evidence = _build_risk_evidence(
        market_regime=candidate_source_row.get("market_regime"),
        mainline_status=candidate_source_row.get("mainline_status"),
        fundamental_hard_risk=research_row.get("fundamental_hard_risk"),
        research_support_score_pit=research_support_score,
        pdf_risk_section_count_90d=research_row.get("pdf_risk_section_count_90d"),
        latest_pdf_risk_summary=research_row.get("latest_pdf_risk_summary"),
        existing_text=research_row.get("main_risk_evidence"),
    )
    rebalance_evidence = _build_rebalance_evidence(
        is_current_holding=is_current_holding,
        is_new_buy=is_new_buy,
        is_candidate_sell=is_candidate_sell,
        candidate_rank=int(candidate_rank_int) if not np.isnan(candidate_rank_int) else 999,
        why_hold_or_change=why_hold_or_change,
        trade_reason=_trade_reason_for_asset(normalized_trades, asset_id),
    )
    main_positive_evidence = _join_nonempty(
        [
            trend_evidence["trend_evidence_summary"],
            research_evidence["research_evidence_summary"],
        ]
    )
    main_risk_evidence = _join_nonempty(
        [
            risk_evidence["risk_evidence_summary"],
            rebalance_evidence["rebalance_reason_evidence_summary"],
        ]
    )
    return {
        "section": section,
        "candidate_rank": candidate_rank_int,
        "asset_id": asset_id,
        "ts_code": ts_code,
        "stock_name": stock_name or asset_id,
        "industry_name": _safe_text(candidate_source_row.get("industry_name")) or _safe_text(research_row.get("industry_name")),
        "portfolio_role": _portfolio_role(section, is_current_holding, is_new_buy, is_candidate_sell),
        "is_current_holding": is_current_holding,
        "is_new_buy": is_new_buy,
        "is_candidate_sell": is_candidate_sell,
        "target_weight": _safe_numeric(holding_row.get("target_weight")),
        "mid_trend_funnel_score": _safe_numeric(candidate_source_row.get("mid_trend_funnel_score")),
        "mid_trend_layer": _safe_text(candidate_source_row.get("mid_trend_layer")),
        "market_regime": _safe_text(candidate_source_row.get("market_regime")),
        "mainline_status": _safe_text(candidate_source_row.get("mainline_status")),
        "broker_report_count_90d": _safe_numeric(research_row.get("broker_report_count_90d")),
        "research_support_score_pit": research_support_score,
        "pdf_target_price_count_90d": _safe_numeric(research_row.get("pdf_target_price_count_90d")),
        "pdf_profit_forecast_count_90d": _safe_numeric(research_row.get("pdf_profit_forecast_count_90d")),
        "pdf_risk_section_count_90d": _safe_numeric(research_row.get("pdf_risk_section_count_90d")),
        "latest_pdf_risk_summary": _safe_text(research_row.get("latest_pdf_risk_summary")),
        "fundamental_hard_risk": _safe_text(research_row.get("fundamental_hard_risk")),
        **trend_evidence,
        **research_evidence,
        **risk_evidence,
        **rebalance_evidence,
        "main_positive_evidence": main_positive_evidence,
        "main_risk_evidence": main_risk_evidence,
        "why_hold_or_change": why_hold_or_change,
        "final_label": final_label,
    }


def _build_portfolio_summary(
    *,
    trade_date: str,
    strategy_variant: str,
    review_rows: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
) -> dict[str, Any]:
    reason_values = []
    if not trades.empty and "reason" in trades.columns:
        reason_values = sorted({str(value) for value in trades["reason"].dropna().astype(str) if str(value).strip()})
    rebalance_triggered = bool(not trades.empty)
    buy_count = int(trades["side"].astype(str).str.lower().eq("buy").sum()) if rebalance_triggered and "side" in trades.columns else 0
    sell_count = int(trades["side"].astype(str).str.lower().eq("sell").sum()) if rebalance_triggered and "side" in trades.columns else 0
    turnover = float(pd.to_numeric(trades["turnover_contribution"], errors="coerce").fillna(0).sum()) if rebalance_triggered and "turnover_contribution" in trades.columns else 0.0
    transaction_cost = float(pd.to_numeric(trades["transaction_cost"], errors="coerce").fillna(0).sum()) if rebalance_triggered and "transaction_cost" in trades.columns else 0.0
    return {
        "trade_date": trade_date,
        "strategy_variant": strategy_variant,
        "review_mode": "rebalance_review" if rebalance_triggered else "holding_review",
        "current_position_count": int(len(holdings)) if holdings is not None else 0,
        "top5_count": int(review_rows["section"].eq("top5").sum()) if not review_rows.empty else 0,
        "top6_10_count": int(review_rows["section"].eq("top6_10").sum()) if not review_rows.empty else 0,
        "top10_count": int(len(review_rows)),
        "holding_count": int(len(holdings)) if holdings is not None else 0,
        "rebalance_triggered": rebalance_triggered,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "turnover": turnover,
        "transaction_cost": transaction_cost,
        "rebalance_reason_summary": "|".join(reason_values),
    }


def _render_markdown(portfolio_summary: dict[str, Any], review_rows: pd.DataFrame) -> str:
    lines = [f"# Mid Trend Portfolio Review {portfolio_summary['trade_date']}", "", "## Portfolio Summary"]
    for key in [
        "strategy_variant",
        "top5_count",
        "top6_10_count",
        "holding_count",
        "buy_count",
        "sell_count",
        "rebalance_triggered",
        "rebalance_reason_summary",
    ]:
        lines.append(f"- {key}: {portfolio_summary.get(key, '')}")

    top5 = review_rows[review_rows["section"].eq("top5")].copy()
    lines.extend(["", "## Top5 Overview"])
    lines.extend(_render_top5_overview(top5))

    lines.extend(["", "## Evidence Snapshot"])
    lines.extend(_render_evidence_snapshot(top5))

    lines.extend(["", "## Top5 Execution Pool"])
    lines.extend(_render_top5_stock_sections(top5))

    lines.extend(["", "## Top6-10 Discussion Pool"])
    top6_10 = review_rows[review_rows["section"].eq("top6_10")].copy()
    lines.extend(_render_top6_10_table(top6_10))
    return "\n".join(lines).strip() + "\n"


def _render_top5_overview(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["", "_No top5 rows_", ""]
    top5_names = [f"{idx}.{_safe_text(row.get('stock_name'))}" for idx, (_, row) in enumerate(frame.iterrows(), start=1)]
    new_buys = [_safe_text(row.get("stock_name")) for _, row in frame[frame["rebalance_action_tag"].eq("new_buy")].iterrows()]
    sells = [_safe_text(row.get("stock_name")) for _, row in frame[frame["rebalance_action_tag"].eq("candidate_sell")].iterrows()]
    lines = [
        "",
        f"- top5_names: {', '.join(top5_names)}",
        f"- new_buys: {', '.join(new_buys) if new_buys else '<none>'}",
        f"- candidate_sells: {', '.join(sells) if sells else '<none>'}",
        "",
    ]
    return lines


def _render_evidence_snapshot(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["", "_No evidence snapshot_", ""]
    lines = [
        "",
        f"- high_support_count: {int(frame['research_support_band_tag'].eq('high_support').sum())}",
        f"- research_gap_count: {int(frame['risk_research_gap_tag'].eq('research_gap').sum())}",
        f"- regime_warning_count: {int(frame['risk_regime_warning_tag'].eq('regime_warning').sum())}",
        f"- new_buy_count: {int(frame['rebalance_action_tag'].eq('new_buy').sum())}",
        f"- hold_no_trade_count: {int(frame['rebalance_action_tag'].eq('hold_no_trade').sum())}",
        "",
    ]
    return lines


def _render_top5_stock_sections(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["", "_No rows_", ""]
    lines: list[str] = [""]
    for display_rank, (_, row) in enumerate(frame.iterrows(), start=1):
        candidate_rank = _safe_numeric(row.get("candidate_rank"))
        candidate_rank_text = f"Top{int(candidate_rank)}" if _is_integral_candidate_rank(candidate_rank) else "<not_in_top10>"
        score_text = _format_evidence_number(row.get("mid_trend_funnel_score"))
        lines.extend(
            [
                f"### {display_rank}. {_safe_text(row.get('stock_name'))} / {_safe_text(row.get('ts_code'))}",
                f"- 最终标签：{_safe_text(row.get('final_label'))}",
                f"- 当前角色：{_safe_text(row.get('portfolio_role'))}",
                f"- 候选排名/分数：{candidate_rank_text} / {score_text}",
                f"- 主线状态：{_safe_text(row.get('market_regime'))} / {_safe_text(row.get('mainline_status'))}",
                f"- 调仓动作：{_safe_text(row.get('rebalance_action_tag'))}",
                "",
                "**Trend Evidence**",
                f"- tags: {_safe_text(row.get('trend_market_regime_tag'))} / {_safe_text(row.get('trend_mainline_status_tag'))} / {_safe_text(row.get('trend_layer_tag'))} / {_safe_text(row.get('trend_score_band_tag'))}",
                f"- summary: {_safe_text(row.get('trend_evidence_summary')) or '<empty>'}",
                "",
                "**Research Evidence**",
                f"- tags: {_safe_text(row.get('research_support_band_tag'))} / {_safe_text(row.get('research_report_coverage_tag'))} / {_safe_text(row.get('research_target_price_coverage_tag'))} / {_safe_text(row.get('research_profit_forecast_coverage_tag'))}",
                f"- summary: {_safe_text(row.get('research_evidence_summary')) or '<empty>'}",
                "",
                "**Risk Evidence**",
                f"- tags: {_safe_text(row.get('risk_fundamental_hard_risk_tag'))} / {_safe_text(row.get('risk_pdf_risk_coverage_tag'))} / {_safe_text(row.get('risk_regime_warning_tag'))} / {_safe_text(row.get('risk_research_gap_tag'))}",
                f"- summary: {_safe_text(row.get('risk_evidence_summary')) or '<empty>'}",
                "",
                "**Rebalance Reason Evidence**",
                f"- tags: {_safe_text(row.get('rebalance_action_tag'))} / {_safe_text(row.get('rebalance_membership_tag'))} / {_safe_text(row.get('rebalance_rank_bucket_tag'))} / {_safe_text(row.get('rebalance_trade_reason_tag'))}",
                f"- summary: {_safe_text(row.get('rebalance_reason_evidence_summary')) or '<empty>'}",
                "",
                "**结论**",
                f"- positive: {_safe_text(row.get('main_positive_evidence')) or '<empty>'}",
                f"- risk: {_safe_text(row.get('main_risk_evidence')) or '<empty>'}",
                "",
            ]
        )
    return lines


def _render_top6_10_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["", "_No rows_", ""]
    columns = [
        "candidate_rank",
        "stock_name",
        "ts_code",
        "mid_trend_funnel_score",
        "final_label",
        "trend_score_band_tag",
        "research_support_band_tag",
        "risk_research_gap_tag",
        "rebalance_action_tag",
        "why_hold_or_change",
    ]
    return _frame_to_markdown(frame[columns])


def _markdown_table(frame: pd.DataFrame, *, full: bool) -> list[str]:
    if frame.empty:
        return ["", "_No rows_", ""]
    if full:
        columns = [
            "candidate_rank",
            "asset_id",
            "ts_code",
            "stock_name",
            "industry_name",
            "portfolio_role",
            "is_current_holding",
            "is_new_buy",
            "is_candidate_sell",
            "target_weight",
            "mid_trend_funnel_score",
            "mid_trend_layer",
            "market_regime",
            "mainline_status",
            "broker_report_count_90d",
            "research_support_score_pit",
            "pdf_target_price_count_90d",
            "pdf_profit_forecast_count_90d",
            "pdf_risk_section_count_90d",
            "latest_pdf_risk_summary",
            "fundamental_hard_risk",
            "main_positive_evidence",
            "main_risk_evidence",
            "why_hold_or_change",
            "final_label",
        ]
    else:
        columns = [
            "candidate_rank",
            "asset_id",
            "stock_name",
            "industry_name",
            "mid_trend_funnel_score",
            "final_label",
            "why_hold_or_change",
        ]
    return _frame_to_markdown(frame[columns])


def _frame_to_markdown(frame: pd.DataFrame) -> list[str]:
    header = "| " + " | ".join(frame.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(frame.columns)) + " |"
    rows = [header, separator]
    for _, row in frame.iterrows():
        values = [_format_markdown_cell(row[column]) for column in frame.columns]
        rows.append("| " + " | ".join(values) + " |")
    return ["", *rows, ""]


def _final_label(
    *,
    section: str,
    is_current_holding: bool,
    is_new_buy: bool,
    is_candidate_sell: bool,
    research_support_score_pit: float | int | None,
) -> str:
    if section == "top6_10":
        return "仅讨论"
    if is_current_holding and _safe_numeric(research_support_score_pit) >= 20:
        return "高优先级持有"
    if is_current_holding:
        return "低优先级持有"
    if is_new_buy:
        return "候选调入"
    if is_candidate_sell:
        return "候选调出"
    return "仅讨论"


def _portfolio_role(section: str, is_current_holding: bool, is_new_buy: bool, is_candidate_sell: bool) -> str:
    if section == "top6_10":
        return "仅讨论"
    if is_current_holding:
        return "持有"
    if is_new_buy:
        return "调入候选"
    if is_candidate_sell:
        return "调出候选"
    return "观察"


def _empty_review_rows() -> pd.DataFrame:
    columns = [
        "section",
        "candidate_rank",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "portfolio_role",
        "is_current_holding",
        "is_new_buy",
        "is_candidate_sell",
        "target_weight",
        "mid_trend_funnel_score",
        "mid_trend_layer",
        "market_regime",
        "mainline_status",
        "broker_report_count_90d",
        "research_support_score_pit",
        "pdf_target_price_count_90d",
        "pdf_profit_forecast_count_90d",
        "pdf_risk_section_count_90d",
        "latest_pdf_risk_summary",
        "fundamental_hard_risk",
        "trend_market_regime_tag",
        "trend_mainline_status_tag",
        "trend_layer_tag",
        "trend_score_band_tag",
        "trend_market_regime_value",
        "trend_mainline_status_value",
        "trend_layer_value",
        "trend_funnel_score_value",
        "trend_evidence_summary",
        "research_support_band_tag",
        "research_report_coverage_tag",
        "research_target_price_coverage_tag",
        "research_profit_forecast_coverage_tag",
        "research_support_score_value",
        "research_report_count_90d_value",
        "research_target_price_count_value",
        "research_profit_forecast_count_value",
        "research_evidence_summary",
        "risk_fundamental_hard_risk_tag",
        "risk_pdf_risk_coverage_tag",
        "risk_regime_warning_tag",
        "risk_research_gap_tag",
        "risk_fundamental_hard_risk_value",
        "risk_pdf_risk_count_value",
        "risk_research_support_score_value",
        "risk_pdf_risk_excerpt_value",
        "risk_evidence_summary",
        "rebalance_action_tag",
        "rebalance_membership_tag",
        "rebalance_rank_bucket_tag",
        "rebalance_trade_reason_tag",
        "rebalance_is_current_holding_value",
        "rebalance_is_new_buy_value",
        "rebalance_is_candidate_sell_value",
        "rebalance_candidate_rank_value",
        "rebalance_trade_reason_value",
        "rebalance_reason_evidence_summary",
        "main_positive_evidence",
        "main_risk_evidence",
        "why_hold_or_change",
        "final_label",
    ]
    return pd.DataFrame(columns=columns)


def _why_hold_or_change(
    *,
    is_new_buy: bool,
    is_candidate_sell: bool,
    is_current_holding: bool,
    rebalance_triggered: bool,
) -> str:
    if is_new_buy:
        return "rebalance_day_new_buy"
    if is_candidate_sell:
        return "rebalance_day_candidate_sell"
    if is_current_holding and not rebalance_triggered:
        return "holding_day_no_rebalance"
    return "discussion_only"


def _build_trend_evidence(
    *,
    market_regime: Any,
    mainline_status: Any,
    mid_trend_layer: Any,
    mid_trend_funnel_score: Any,
) -> dict[str, Any]:
    market_regime_text = _safe_text(market_regime) or "unknown"
    mainline_status_text = _safe_text(mainline_status) or "unknown"
    layer_text = _safe_text(mid_trend_layer) or "unknown"
    score = _safe_numeric(mid_trend_funnel_score)
    if np.isnan(score):
        score_band = "unknown"
    elif score >= 85:
        score_band = "elite"
    elif score >= 80:
        score_band = "strong"
    else:
        score_band = "borderline"
    score_text = "" if np.isnan(score) else f"{score:.1f}"
    summary = _join_nonempty(
        [
            f"主线环境: {market_regime_text}",
            f"趋势结构: {layer_text}" + (f" / score={score_text}" if score_text else ""),
        ]
    )
    return {
        "trend_market_regime_tag": market_regime_text,
        "trend_mainline_status_tag": mainline_status_text,
        "trend_layer_tag": layer_text,
        "trend_score_band_tag": score_band,
        "trend_market_regime_value": market_regime_text,
        "trend_mainline_status_value": mainline_status_text,
        "trend_layer_value": layer_text,
        "trend_funnel_score_value": score,
        "trend_evidence_summary": summary,
    }


def _build_research_evidence(
    *,
    research_support_score_pit: Any,
    broker_report_count_90d: Any,
    pdf_target_price_count_90d: Any,
    pdf_profit_forecast_count_90d: Any,
    existing_text: Any,
) -> dict[str, Any]:
    support = _safe_numeric(research_support_score_pit)
    report_count = _safe_numeric(broker_report_count_90d)
    target_count = _safe_numeric(pdf_target_price_count_90d)
    forecast_count = _safe_numeric(pdf_profit_forecast_count_90d)
    support_tag = _support_band_tag(support)
    report_tag = _coverage_tag(report_count, dense_threshold=3, dense_label="dense_coverage", light_label="light_coverage")
    target_tag = _availability_tag(target_count, positive_label="target_price_available", zero_label="target_price_missing")
    forecast_tag = _availability_tag(forecast_count, positive_label="forecast_available", zero_label="forecast_missing")
    explicit = _normalize_existing_evidence_text(existing_text)
    summary = explicit or (
        "研报/PDF覆盖: "
        f"support={_format_evidence_number(support)}, "
        f"reports={_format_evidence_number(report_count)}, "
        f"target={_format_evidence_number(target_count)}, "
        f"forecast={_format_evidence_number(forecast_count)}"
        if any(not np.isnan(v) and v > 0 for v in [support, report_count, target_count, forecast_count])
        else ""
    )
    return {
        "research_support_band_tag": support_tag,
        "research_report_coverage_tag": report_tag,
        "research_target_price_coverage_tag": target_tag,
        "research_profit_forecast_coverage_tag": forecast_tag,
        "research_support_score_value": support,
        "research_report_count_90d_value": report_count,
        "research_target_price_count_value": target_count,
        "research_profit_forecast_count_value": forecast_count,
        "research_evidence_summary": summary,
    }


def _build_risk_evidence(
    *,
    market_regime: Any,
    mainline_status: Any,
    fundamental_hard_risk: Any,
    research_support_score_pit: Any,
    pdf_risk_section_count_90d: Any,
    latest_pdf_risk_summary: Any,
    existing_text: Any,
) -> dict[str, Any]:
    hard_risk = _safe_text(fundamental_hard_risk)
    risk_count = _safe_numeric(pdf_risk_section_count_90d)
    research_support = _safe_numeric(research_support_score_pit)
    risk_excerpt = _summarize_risk_text(latest_pdf_risk_summary)
    market_regime_text = _safe_text(market_regime) or "unknown"
    mainline_status_text = _safe_text(mainline_status) or "unknown"
    risk_tag = hard_risk if hard_risk and hard_risk != "no_clear_hard_risk" else "no_clear_hard_risk"
    pdf_risk_tag = _availability_tag(risk_count, positive_label="risk_disclosed", zero_label="risk_not_disclosed")
    regime_warning_tag = "regime_warning" if market_regime_text != "mainline" or "weak" in mainline_status_text else "no_regime_warning"
    research_gap_tag = (
        "unknown"
        if np.isnan(research_support)
        else "research_gap"
        if research_support <= 0
        else "limited_support"
        if research_support < 20
        else "supported"
    )
    explicit = _normalize_existing_evidence_text(existing_text)
    summary = explicit or _derive_risk_evidence(
        existing_text="",
        market_regime=market_regime_text,
        mainline_status=mainline_status_text,
        fundamental_hard_risk=hard_risk,
        research_support_score_pit=research_support,
        pdf_risk_section_count_90d=risk_count,
        latest_pdf_risk_summary=risk_excerpt,
    )
    return {
        "risk_fundamental_hard_risk_tag": risk_tag,
        "risk_pdf_risk_coverage_tag": pdf_risk_tag,
        "risk_regime_warning_tag": regime_warning_tag,
        "risk_research_gap_tag": research_gap_tag,
        "risk_fundamental_hard_risk_value": hard_risk,
        "risk_pdf_risk_count_value": risk_count,
        "risk_research_support_score_value": research_support,
        "risk_pdf_risk_excerpt_value": risk_excerpt,
        "risk_evidence_summary": summary,
    }


def _build_rebalance_evidence(
    *,
    is_current_holding: bool,
    is_new_buy: bool,
    is_candidate_sell: bool,
    candidate_rank: int,
    why_hold_or_change: str,
    trade_reason: Any,
) -> dict[str, Any]:
    if is_new_buy:
        action_tag = "new_buy"
    elif is_candidate_sell:
        action_tag = "candidate_sell"
    elif is_current_holding:
        action_tag = "hold_no_trade"
    else:
        action_tag = "discussion_only"
    if candidate_rank <= 3:
        rank_bucket = "top3"
    elif candidate_rank <= 5:
        rank_bucket = "top5"
    elif candidate_rank <= 10:
        rank_bucket = "top10"
    else:
        rank_bucket = "out_of_scope"
    trade_reason_text = _safe_text(trade_reason)
    if trade_reason_text:
        trade_reason_tag = trade_reason_text
    elif action_tag == "hold_no_trade":
        trade_reason_tag = "carry_forward_hold"
    else:
        trade_reason_tag = "no_trade_signal"
    summary = f"动作: {action_tag}; 排名: {rank_bucket}; reason={trade_reason_tag}"
    return {
        "rebalance_action_tag": action_tag,
        "rebalance_membership_tag": "current_holding" if is_current_holding else "not_holding",
        "rebalance_rank_bucket_tag": rank_bucket,
        "rebalance_trade_reason_tag": trade_reason_tag,
        "rebalance_is_current_holding_value": is_current_holding,
        "rebalance_is_new_buy_value": is_new_buy,
        "rebalance_is_candidate_sell_value": is_candidate_sell,
        "rebalance_candidate_rank_value": candidate_rank,
        "rebalance_trade_reason_value": trade_reason_text or why_hold_or_change,
        "rebalance_reason_evidence_summary": summary,
    }


def _trade_reason_for_asset(trades: pd.DataFrame, asset_id: str) -> str:
    if trades.empty or "asset_id" not in trades.columns:
        return ""
    matched = trades[trades["asset_id"].astype(str).eq(asset_id)]
    if matched.empty or "reason" not in matched.columns:
        return ""
    return _safe_text(matched["reason"].iloc[-1])


def _support_band_tag(value: float) -> str:
    if np.isnan(value):
        return "unknown"
    if value >= 20:
        return "high_support"
    if value > 0:
        return "mid_support"
    return "no_support"


def _coverage_tag(value: float, *, dense_threshold: int, dense_label: str, light_label: str) -> str:
    if np.isnan(value):
        return "unknown"
    if value >= dense_threshold:
        return dense_label
    if value > 0:
        return light_label
    return "no_coverage"


def _availability_tag(value: float, *, positive_label: str, zero_label: str) -> str:
    if np.isnan(value):
        return "unknown"
    if value > 0:
        return positive_label
    return zero_label


def _join_nonempty(parts: list[str]) -> str:
    values = [part.strip() for part in parts if _safe_text(part).strip()]
    return "; ".join(values)


def _resolve_review_stock_name(
    *,
    top10_name: Any,
    research_name: Any,
    asset_id: Any,
    ts_code: Any,
    lookup: dict[str, str],
) -> str:
    top10_text = _safe_text(top10_name)
    research_text = _safe_text(research_name)
    normalized_ts_code = _safe_text(ts_code).upper()
    if top10_text and not _is_placeholder_stock_name(top10_text, asset_id, normalized_ts_code):
        return top10_text
    if research_text and not _is_placeholder_stock_name(research_text, asset_id, normalized_ts_code):
        return research_text
    return lookup.get(normalized_ts_code, research_text or top10_text)


def _is_placeholder_stock_name(name: Any, asset_id: Any, ts_code: Any) -> bool:
    text = _safe_text(name)
    if not text:
        return True
    normalized_ts_code = _safe_text(ts_code).upper()
    code = normalized_ts_code.split(".")[0] if normalized_ts_code else ""
    asset_code = _safe_text(asset_id).split(":")[-1]
    return text in {code, asset_code, normalized_ts_code, _safe_text(asset_id)}


def _load_review_stock_name_lookup(ts_codes: list[str]) -> dict[str, str]:
    if not ts_codes:
        return {}
    sql = """
        SELECT ts_code, name AS stock_name
        FROM core.asset_master
        WHERE ts_code = ANY(%s)
          AND name IS NOT NULL
          AND name <> ''
    """
    try:
        with connect(SETTINGS.research_service) as conn:
            rows = fetch_all(conn, sql, (ts_codes,))
    except Exception:
        return {}
    lookup: dict[str, str] = {}
    for row in rows:
        ts_code = _safe_text(row.get("ts_code")).upper()
        stock_name = _safe_text(row.get("stock_name"))
        if ts_code and stock_name and not _is_placeholder_stock_name(stock_name, "", ts_code):
            lookup.setdefault(ts_code, stock_name)
    return lookup


def _ts_code_from_asset_id(asset_id: Any) -> str:
    parts = _safe_text(asset_id).split(":")
    if len(parts) != 3:
        return ""
    _, exchange, code = parts
    exchange = exchange.strip().upper()
    code = code.strip()
    if exchange not in {"SH", "SZ", "BJ"} or not code:
        return ""
    return f"{code}.{exchange}"


def _derive_positive_evidence(
    *,
    existing_text: Any,
    market_regime: Any,
    mainline_status: Any,
    mid_trend_layer: Any,
    mid_trend_funnel_score: Any,
    research_support_score_pit: Any,
    broker_report_count_90d: Any,
    pdf_target_price_count_90d: Any,
    pdf_profit_forecast_count_90d: Any,
) -> str:
    existing = _normalize_existing_evidence_text(existing_text)
    if existing:
        return existing
    parts: list[str] = []
    market_regime_text = _safe_text(market_regime)
    mainline_status_text = _safe_text(mainline_status)
    if market_regime_text == "mainline" or "mainline" in mainline_status_text:
        parts.append(f"主线环境: {market_regime_text or mainline_status_text}")
    layer_text = _safe_text(mid_trend_layer)
    score = _safe_numeric(mid_trend_funnel_score)
    if layer_text or not np.isnan(score):
        score_text = "" if np.isnan(score) else f"{score:.1f}"
        parts.append(f"趋势结构: {layer_text or 'unknown'} / score={score_text}".strip(" /"))
    research_score = _safe_numeric(research_support_score_pit)
    report_count = _safe_numeric(broker_report_count_90d)
    pdf_target_count = _safe_numeric(pdf_target_price_count_90d)
    pdf_forecast_count = _safe_numeric(pdf_profit_forecast_count_90d)
    if any(not np.isnan(value) and value > 0 for value in [research_score, report_count, pdf_target_count, pdf_forecast_count]):
        parts.append(
            "研报/PDF覆盖: "
            f"support={_format_evidence_number(research_score)}, "
            f"reports={_format_evidence_number(report_count)}, "
            f"target={_format_evidence_number(pdf_target_count)}, "
            f"forecast={_format_evidence_number(pdf_forecast_count)}"
        )
    return "; ".join(parts[:3])


def _derive_risk_evidence(
    *,
    existing_text: Any,
    market_regime: Any,
    mainline_status: Any,
    fundamental_hard_risk: Any,
    research_support_score_pit: Any,
    pdf_risk_section_count_90d: Any,
    latest_pdf_risk_summary: Any,
) -> str:
    existing = _normalize_existing_evidence_text(existing_text)
    if existing:
        return existing
    parts: list[str] = []
    hard_risk = _safe_text(fundamental_hard_risk)
    if hard_risk and hard_risk != "no_clear_hard_risk":
        parts.append(f"硬风险: {hard_risk}")
    risk_count = _safe_numeric(pdf_risk_section_count_90d)
    risk_summary = _summarize_risk_text(latest_pdf_risk_summary)
    if (not np.isnan(risk_count) and risk_count > 0) or risk_summary:
        parts.append(
            f"风险段: count={_format_evidence_number(risk_count)}"
            + (f", {risk_summary}" if risk_summary else "")
        )
    research_score = _safe_numeric(research_support_score_pit)
    market_regime_text = _safe_text(market_regime)
    mainline_status_text = _safe_text(mainline_status)
    if (not np.isnan(research_score) and research_score <= 0) or "weak" in mainline_status_text or market_regime_text == "rotation":
        parts.append(
            "环境/覆盖风险: "
            f"regime={market_regime_text or 'unknown'}, "
            f"mainline={mainline_status_text or 'unknown'}, "
            f"support={_format_evidence_number(research_score)}"
        )
    return "; ".join(parts[:3])


def _format_evidence_number(value: Any) -> str:
    numeric = _safe_numeric(value)
    if np.isnan(numeric):
        return "nan"
    if float(numeric).is_integer():
        return str(int(numeric))
    return f"{numeric:.1f}"


def _normalize_existing_evidence_text(value: Any, *, max_len: int = 80) -> str:
    text = " ".join(_safe_text(value).split()).lstrip("，,。；;：: ")
    if not text:
        return ""
    segments = [text]
    for delimiter in ("；", ";", "。", ".", "\n"):
        next_segments: list[str] = []
        for segment in segments:
            next_segments.extend(segment.split(delimiter))
        segments = next_segments
    cleaned = [segment.strip(" ，,。；;：:") for segment in segments if segment.strip(" ，,。；;：:")]
    merged = "; ".join(cleaned[:2])
    if len(merged) > max_len:
        merged = merged[:max_len].rstrip() + "..."
    return merged


def _summarize_risk_text(value: Any, *, max_len: int = 40) -> str:
    text = " ".join(_safe_text(value).split())
    if not text:
        return ""
    for delimiter in ("；", ";", "。", ".", "\n"):
        text = text.split(delimiter)[0]
    text = text.lstrip("，,。；;：: ")
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return text


def _row_for_asset(frame: pd.DataFrame, asset_id: str) -> pd.Series:
    if frame.empty or asset_id not in frame.index:
        return pd.Series(dtype=object)
    value = frame.loc[asset_id]
    if isinstance(value, pd.DataFrame):
        return value.iloc[-1]
    return value


def _safe_text(value: Any) -> str:
    if value is None or value is pd.NA:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    if pd.isna(value):
        return ""
    return str(value)


def _safe_numeric(value: Any) -> float:
    if value is None or value is pd.NA:
        return np.nan
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(numeric):
        return np.nan
    return numeric


def _is_integral_candidate_rank(value: Any) -> bool:
    numeric = _safe_numeric(value)
    return bool(not np.isnan(numeric) and float(numeric).is_integer())


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is None or value is pd.NA:
            continue
        if isinstance(value, float) and np.isnan(value):
            continue
        if pd.isna(value):
            continue
        if str(value).strip():
            return value
    return ""


def _format_markdown_cell(value: Any) -> str:
    if value is None or value is pd.NA or pd.isna(value):
        return ""
    text = str(value)
    return text.replace("\n", "<br>")
