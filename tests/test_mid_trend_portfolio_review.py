from __future__ import annotations

from pathlib import Path

import pandas as pd

import stock_research.cli as cli
import stock_research.mid_trend_portfolio_review as portfolio_review
from stock_research.mid_trend_portfolio_review import (
    _normalize_research,
    build_mid_trend_portfolio_review_from_frames,
    run_mid_trend_portfolio_review,
)


def test_portfolio_review_builds_top5_full_and_top6_10_short_sections(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
                "shadow_top10_rank": 2,
                "mid_trend_funnel_score": 84.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "neutral",
                "industry_name": "机械",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:603931",
                "ts_code": "603931.SH",
                "stock_name": "格林达",
                "shadow_top10_rank": 3,
                "mid_trend_funnel_score": 84.0,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "化工",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688390",
                "ts_code": "688390.SH",
                "stock_name": "固德威",
                "shadow_top10_rank": 4,
                "mid_trend_funnel_score": 82.4,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电力设备",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SZ:300831",
                "ts_code": "300831.SZ",
                "stock_name": "派瑞股份",
                "shadow_top10_rank": 5,
                "mid_trend_funnel_score": 70.1,
                "mid_trend_layer": "high_elasticity_watch",
                "market_regime": "mainline",
                "mainline_status": "neutral",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
                "shadow_top10_rank": 6,
                "mid_trend_funnel_score": 82.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "医疗器械",
            },
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "weight": 0.2,
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SZ:300201",
                "weight": 0.2,
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SH:603931",
                "weight": 0.2,
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SH:688390",
                "weight": 0.2,
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SZ:300831",
                "weight": 0.2,
            },
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:603931",
                "side": "buy",
                "turnover_contribution": 0.2,
                "transaction_cost": 0.0004,
                "reason": "weekly_rebalance",
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2026-06-04",
                "asset_id": "CN:SZ:000811",
                "side": "sell",
                "turnover_contribution": 0.2,
                "transaction_cost": 0.0004,
                "reason": "weekly_rebalance",
            },
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 3,
                "research_support_score_pit": 33,
                "target_price_median_pit": 103.5,
                "target_upside_median_pit": pd.NA,
                "broker_coverage_count_pit": 3,
                "pdf_target_price_count_90d": 3,
                "pdf_target_price_high_confidence_count_90d": 1,
                "pdf_profit_forecast_count_90d": 3,
                "pdf_risk_section_count_90d": 3,
                "latest_pdf_risk_summary": "下游需求不及预期风险；行业竞争加剧风险。",
                "fundamental_hard_risk": "no_clear_hard_risk",
                "main_positive_evidence": "行业景气回升，研报覆盖较多。",
                "main_risk_evidence": "估值偏高，行业竞争加剧。",
                "why_hold_or_change": "高支持度且为核心持仓，继续持有。",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "broker_report_count_90d": 0,
                "research_support_score_pit": 0,
                "target_price_median_pit": pd.NA,
                "target_upside_median_pit": pd.NA,
                "broker_coverage_count_pit": 0,
                "pdf_target_price_count_90d": 0,
                "pdf_target_price_high_confidence_count_90d": 0,
                "pdf_profit_forecast_count_90d": 0,
                "pdf_risk_section_count_90d": 0,
                "latest_pdf_risk_summary": "",
                "fundamental_hard_risk": "no_clear_hard_risk",
                "main_positive_evidence": "",
                "main_risk_evidence": "",
                "why_hold_or_change": "",
            },
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=trades,
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    review = result["review_rows"]
    summary = result["portfolio_summary"]

    assert set(review["section"]) == {"top5", "top6_10"}
    assert review.loc[review["section"].eq("top6_10"), "final_label"].eq("仅讨论").all()
    assert review.loc[review["section"].eq("top5"), "final_label"].notna().all()
    assert review.loc[review["asset_id"].eq("CN:SH:600183"), "final_label"].item() == "高优先级持有"
    assert review.loc[review["asset_id"].eq("CN:SZ:300201"), "final_label"].item() == "低优先级持有"
    assert review.loc[review["asset_id"].eq("CN:SH:603931"), "final_label"].item() == "低优先级持有"
    assert "latest_pdf_risk_summary" in review.columns
    assert "main_positive_evidence" in review.columns
    assert "main_risk_evidence" in review.columns
    assert "why_hold_or_change" in review.columns
    assert summary["trade_date"] == "2026-06-04"
    assert Path(result["paths"]["csv"]).exists()
    assert Path(result["paths"]["md"]).exists()
    assert "## Portfolio Summary" in result["markdown"]
    assert "## Top5 Execution Pool" in result["markdown"]
    assert "## Top6-10 Discussion Pool" in result["markdown"]


def test_portfolio_review_writes_markdown_and_csv_with_section_names(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
                "shadow_top10_rank": 6,
                "mid_trend_funnel_score": 82.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "医疗器械",
            },
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=pd.DataFrame(),
        output_dir=tmp_path,
    )

    csv_path = Path(result["paths"]["csv"])
    md_path = Path(result["paths"]["md"])
    assert csv_path.exists()
    assert md_path.exists()

    csv_text = csv_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    assert "section" in csv_text.splitlines()[0]
    assert "## Portfolio Summary" in md_text
    assert "## Top5 Execution Pool" in md_text
    assert "## Top6-10 Discussion Pool" in md_text


def test_portfolio_review_ignores_malformed_holdings_trades_and_research(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-06",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    )
    malformed_holdings = pd.DataFrame(
        [
            {
                "rebalance_date": "2026-06-05",
                "asset_id": "CN:SH:600183",
                "weight": 1.0,
            }
        ]
    )
    malformed_trades = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "asset_id": "CN:SH:600183",
                "side": "buy",
                "reason": "weekly_rebalance",
            }
        ]
    )
    malformed_research = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "broker_report_count_90d": 9,
                "research_support_score_pit": 99,
                "latest_pdf_risk_summary": "should not leak",
                "main_positive_evidence": "should not leak",
                "main_risk_evidence": "should not leak",
                "why_hold_or_change": "should not leak",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-06",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=malformed_holdings,
        trades=malformed_trades,
        research_packet_candidates=malformed_research,
        output_dir=tmp_path,
    )

    row = result["review_rows"].iloc[0]
    assert not row["is_current_holding"]
    assert not row["is_new_buy"]
    assert not row["is_candidate_sell"]
    assert pd.isna(row["broker_report_count_90d"])
    assert row["latest_pdf_risk_summary"] == ""
    assert row["main_positive_evidence"] != "should not leak"
    assert "主线环境" in row["main_positive_evidence"]
    assert row["main_risk_evidence"] != "should not leak"
    assert row["why_hold_or_change"] == "discussion_only"


def test_portfolio_review_drops_non_integral_candidate_ranks(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-07",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 5.0,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-07",
                "asset_id": "CN:SZ:300201",
                "ts_code": "300201.SZ",
                "stock_name": "海伦哲",
                "shadow_top10_rank": 5.9,
                "mid_trend_funnel_score": 84.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "neutral",
                "industry_name": "机械",
            },
            {
                "trade_date": "2026-06-07",
                "asset_id": "CN:SH:603931",
                "ts_code": "603931.SH",
                "stock_name": "格林达",
                "shadow_top10_rank": 6.0,
                "mid_trend_funnel_score": 84.0,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "化工",
            },
            {
                "trade_date": "2026-06-07",
                "asset_id": "CN:SH:688390",
                "ts_code": "688390.SH",
                "stock_name": "固德威",
                "shadow_top10_rank": 10.7,
                "mid_trend_funnel_score": 82.4,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电力设备",
            },
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-07",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=pd.DataFrame(),
        output_dir=tmp_path,
    )

    review = result["review_rows"]
    assert set(review["asset_id"]) == {"CN:SH:600183", "CN:SH:603931"}
    assert review.loc[review["asset_id"].eq("CN:SH:600183"), "section"].item() == "top5"
    assert review.loc[review["asset_id"].eq("CN:SH:603931"), "section"].item() == "top6_10"
    assert "CN:SZ:300201" not in set(review["asset_id"])
    assert "CN:SH:688390" not in set(review["asset_id"])


def test_normalize_research_prefers_latest_trade_date_for_duplicate_assets() -> None:
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 1,
                "research_support_score_pit": 10,
                "latest_pdf_risk_summary": "older row",
            },
            {
                "trade_date": "2026-06-05",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 7,
                "research_support_score_pit": 30,
                "latest_pdf_risk_summary": "newer row",
            },
            {
                "trade_date": "2026-06-05",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 9,
                "research_support_score_pit": 40,
                "latest_pdf_risk_summary": "same-date later row",
            },
        ]
    )

    normalized = _normalize_research(research, trade_date="2026-06-05")

    assert len(normalized) == 1
    row = normalized.iloc[0]
    assert row["trade_date"].strftime("%Y-%m-%d") == "2026-06-05"
    assert row["broker_report_count_90d"] == 9
    assert row["research_support_score_pit"] == 40
    assert row["latest_pdf_risk_summary"] == "same-date later row"


def test_normalize_research_preserves_requested_earlier_date_rows() -> None:
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 2,
                "research_support_score_pit": 12,
                "latest_pdf_risk_summary": "requested day row",
            },
            {
                "trade_date": "2026-06-05",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 8,
                "research_support_score_pit": 32,
                "latest_pdf_risk_summary": "later day row",
            },
        ]
    )

    normalized = _normalize_research(research, trade_date="2026-06-04")

    assert len(normalized) == 1
    row = normalized.iloc[0]
    assert row["trade_date"].strftime("%Y-%m-%d") == "2026-06-04"
    assert row["broker_report_count_90d"] == 2
    assert row["research_support_score_pit"] == 12
    assert row["latest_pdf_risk_summary"] == "requested day row"


def test_portfolio_review_rebalance_summary_includes_trade_counts_and_reason(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SH:603931",
                "ts_code": "603931.SH",
                "stock_name": "格林达",
                "shadow_top10_rank": 2,
                "mid_trend_funnel_score": 84.0,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "化工",
            },
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SH:688390",
                "ts_code": "688390.SH",
                "stock_name": "固德威",
                "shadow_top10_rank": 6,
                "mid_trend_funnel_score": 82.4,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电力设备",
            },
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-01",
                "asset_id": "CN:SH:600183",
                "weight": 0.5,
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-01",
                "asset_id": "CN:SH:603931",
                "weight": 0.5,
            },
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2026-06-01",
                "asset_id": "CN:SH:603931",
                "side": "buy",
                "turnover_contribution": 0.4,
                "transaction_cost": 0.001,
                "reason": "weekly_rebalance",
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2026-06-01",
                "asset_id": "CN:SH:688390",
                "side": "sell",
                "turnover_contribution": 0.4,
                "transaction_cost": 0.001,
                "reason": "weekly_rebalance",
            },
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-01",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=trades,
        research_packet_candidates=pd.DataFrame(),
        output_dir=tmp_path,
    )

    summary = result["portfolio_summary"]
    review = result["review_rows"]

    assert summary["trade_date"] == "2026-06-01"
    assert summary["strategy_variant"] == "top5_weekly_max_2_replacements"
    assert summary["review_mode"] == "rebalance_review"
    assert summary["current_position_count"] == 2
    assert summary["top5_count"] == 2
    assert summary["top10_count"] == 3
    assert summary["rebalance_triggered"] is True
    assert summary["buy_count"] == 1
    assert summary["sell_count"] == 1
    assert summary["turnover"] == 0.8
    assert summary["transaction_cost"] == 0.002
    assert summary["rebalance_reason_summary"] == "weekly_rebalance"
    assert review.loc[review["asset_id"].eq("CN:SH:603931"), "why_hold_or_change"].item() == "rebalance_day_new_buy"
    assert review.loc[review["asset_id"].eq("CN:SH:688390"), "why_hold_or_change"].item() == "rebalance_day_candidate_sell"
    assert review.loc[review["asset_id"].eq("CN:SH:600183"), "why_hold_or_change"].item() == "discussion_only"


def test_portfolio_review_holding_only_day_marks_hold_reason(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-01",
                "asset_id": "CN:SH:600183",
                "weight": 1.0,
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-02",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=pd.DataFrame(),
        research_packet_candidates=pd.DataFrame(),
        output_dir=tmp_path,
    )

    summary = result["portfolio_summary"]
    review = result["review_rows"]

    assert summary["rebalance_triggered"] is False
    assert summary["review_mode"] == "holding_review"
    assert summary["current_position_count"] > 0
    assert review.iloc[0]["is_current_holding"]
    assert review.iloc[0]["why_hold_or_change"] == "holding_day_no_rebalance"


def test_cli_dispatches_mid_trend_portfolio_review(monkeypatch, capsys, tmp_path: Path) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "review_rows": pd.DataFrame([{"ts_code": "600183.SH"}]),
            "paths": {
                "csv": str(tmp_path / "review.csv"),
                "report": str(tmp_path / "review.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_portfolio_review", fake_run, raising=False)

    cli.main_for_args(
        [
            "build-mid-trend-portfolio-review",
            "--trade-date",
            "2026-06-04",
            "--strategy-variant",
            "top5_weekly_max_2_replacements",
            "--top10-path",
            "outputs/research/mid_trend_shadow_top10.csv",
            "--holdings-path",
            "outputs/research/mid_trend_shadow_weekly_control_positions.csv",
            "--trades-path",
            "outputs/research/mid_trend_shadow_weekly_control_trades.csv",
            "--research-packet-path",
            "outputs/research/mid_trend_research_packet_candidates.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured == {
        "trade_date": "2026-06-04",
        "strategy_variant": "top5_weekly_max_2_replacements",
        "top10_path": "outputs/research/mid_trend_shadow_top10.csv",
        "holdings_path": "outputs/research/mid_trend_shadow_weekly_control_positions.csv",
        "trades_path": "outputs/research/mid_trend_shadow_weekly_control_trades.csv",
        "research_packet_path": "outputs/research/mid_trend_research_packet_candidates.csv",
        "output_dir": str(tmp_path),
        "write_research_infra": False,
    }
    out = capsys.readouterr().out
    assert f"mid_trend_portfolio_review|csv|{tmp_path / 'review.csv'}" in out
    assert f"mid_trend_portfolio_review|report|{tmp_path / 'review.md'}" in out
    assert "mid_trend_portfolio_review|rows|1" in out


def test_cli_dispatches_mid_trend_portfolio_review_with_research_infra(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    captured = {}
    run_card_path = tmp_path / "research_infra" / "run_card" / "run_card.json"

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "review_rows": pd.DataFrame([{"ts_code": "600183.SH"}]),
            "paths": {
                "csv": str(tmp_path / "review.csv"),
                "report": str(tmp_path / "review.md"),
            },
            "research_infra": {
                "research_infra_dir": str(tmp_path / "research_infra"),
                "research_signals_json_path": str(
                    tmp_path / "research_infra" / "research_signals.json"
                ),
                "attribution_cards_json_path": str(
                    tmp_path / "research_infra" / "attribution_cards.json"
                ),
                "run_card": {
                    "run_card_json_path": str(run_card_path),
                },
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_portfolio_review", fake_run, raising=False)

    cli.main_for_args(
        [
            "build-mid-trend-portfolio-review",
            "--trade-date",
            "2026-06-04",
            "--strategy-variant",
            "top5_weekly_max_2_replacements",
            "--top10-path",
            "outputs/research/mid_trend_shadow_top10.csv",
            "--holdings-path",
            "outputs/research/mid_trend_shadow_weekly_control_positions.csv",
            "--trades-path",
            "outputs/research/mid_trend_shadow_weekly_control_trades.csv",
            "--research-packet-path",
            "outputs/research/mid_trend_research_packet_candidates.csv",
            "--output-dir",
            str(tmp_path),
            "--write-research-infra",
        ]
    )

    assert captured["write_research_infra"] is True
    out = capsys.readouterr().out
    assert f"mid_trend_portfolio_review|csv|{tmp_path / 'review.csv'}" in out
    assert f"mid_trend_portfolio_review|report|{tmp_path / 'review.md'}" in out
    assert "mid_trend_portfolio_review|rows|1" in out
    assert f"mid_trend_portfolio_review|research_infra|{tmp_path / 'research_infra'}" in out
    assert (
        "mid_trend_portfolio_review|research_signals|"
        f"{tmp_path / 'research_infra' / 'research_signals.json'}"
    ) in out
    assert (
        "mid_trend_portfolio_review|attribution_cards|"
        f"{tmp_path / 'research_infra' / 'attribution_cards.json'}"
    ) in out
    assert f"mid_trend_portfolio_review|run_card|{run_card_path}" in out


def test_run_mid_trend_portfolio_review_reads_csvs_and_delegates(monkeypatch, tmp_path: Path) -> None:
    csv_inputs = {
        tmp_path / "top10.csv": pd.DataFrame([{"asset_id": "A", "shadow_top10_rank": 1}]),
        tmp_path / "holdings.csv": pd.DataFrame([{"asset_id": "A"}]),
        tmp_path / "trades.csv": pd.DataFrame([{"asset_id": "A"}]),
        tmp_path / "research.csv": pd.DataFrame([{"asset_id": "A"}]),
    }
    read_paths: list[Path] = []
    captured = {}

    def fake_read_csv(path, *args, **kwargs):
        read_paths.append(Path(path))
        return csv_inputs[Path(path)]

    def fake_build_mid_trend_portfolio_review_from_frames(**kwargs):
        captured.update(kwargs)
        return {"review_rows": pd.DataFrame(), "paths": {}}

    monkeypatch.setattr(portfolio_review.pd, "read_csv", fake_read_csv)
    monkeypatch.setattr(
        portfolio_review,
        "build_mid_trend_portfolio_review_from_frames",
        fake_build_mid_trend_portfolio_review_from_frames,
    )

    result = run_mid_trend_portfolio_review(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10_path=tmp_path / "top10.csv",
        holdings_path=tmp_path / "holdings.csv",
        trades_path=tmp_path / "trades.csv",
        research_packet_path=tmp_path / "research.csv",
    )

    assert read_paths == [
        tmp_path / "top10.csv",
        tmp_path / "holdings.csv",
        tmp_path / "trades.csv",
        tmp_path / "research.csv",
    ]
    assert captured["trade_date"] == "2026-06-04"
    assert captured["strategy_variant"] == "top5_weekly_max_2_replacements"
    assert captured["top10"].equals(csv_inputs[tmp_path / "top10.csv"])
    assert captured["holdings"].equals(csv_inputs[tmp_path / "holdings.csv"])
    assert captured["trades"].equals(csv_inputs[tmp_path / "trades.csv"])
    assert captured["research_packet_candidates"].equals(csv_inputs[tmp_path / "research.csv"])
    assert captured["output_dir"] == portfolio_review.REPO_ROOT / "outputs" / "research"
    assert "research_infra" not in result


def test_run_mid_trend_portfolio_review_writes_research_infra_when_enabled(
    tmp_path: Path,
) -> None:
    top10_path = tmp_path / "top10.csv"
    holdings_path = tmp_path / "holdings.csv"
    trades_path = tmp_path / "trades.csv"
    research_path = tmp_path / "research.csv"

    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    ).to_csv(top10_path, index=False)
    pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "weight": 1.0,
            }
        ]
    ).to_csv(holdings_path, index=False)
    pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "side": "buy",
                "turnover_contribution": 0.2,
                "transaction_cost": 0.0004,
                "reason": "weekly_rebalance",
            }
        ]
    ).to_csv(trades_path, index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 3,
                "research_support_score_pit": 33,
                "pdf_target_price_count_90d": 3,
                "pdf_profit_forecast_count_90d": 3,
                "pdf_risk_section_count_90d": 3,
            }
        ]
    ).to_csv(research_path, index=False)

    result = run_mid_trend_portfolio_review(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10_path=top10_path,
        holdings_path=holdings_path,
        trades_path=trades_path,
        research_packet_path=research_path,
        output_dir=tmp_path / "review_output",
        write_research_infra=True,
    )

    assert "research_infra" in result
    research_infra = result["research_infra"]
    assert Path(research_infra["research_infra_dir"]).is_dir()
    assert Path(research_infra["research_signals_json_path"]).exists()
    assert Path(research_infra["attribution_cards_json_path"]).exists()
    assert Path(research_infra["attribution_cards_md_path"]).exists()
    assert Path(research_infra["experiment_registry_path"]).exists()
    assert Path(research_infra["run_card"]["run_card_json_path"]).exists()
    assert research_infra["research_signal_count"] == 3


def test_portfolio_review_backfills_placeholder_stock_name_from_research() -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "CN:SH:688301",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 82.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "医疗器械",
            }
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=research,
    )

    assert result["review_rows"].loc[0, "stock_name"] == "奕瑞科技"


def test_portfolio_review_backfills_placeholder_stock_name_from_lookup(monkeypatch) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "688301",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 82.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "医疗器械",
            }
        ]
    )
    monkeypatch.setattr(
        portfolio_review,
        "_load_review_stock_name_lookup",
        lambda ts_codes: {"688301.SH": "奕瑞科技"},
        raising=False,
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=pd.DataFrame(),
    )

    assert result["review_rows"].loc[0, "stock_name"] == "奕瑞科技"


def test_portfolio_review_derives_positive_evidence_from_structured_fields_when_blank() -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 3,
                "research_support_score_pit": 33,
                "pdf_target_price_count_90d": 3,
                "pdf_profit_forecast_count_90d": 2,
                "main_positive_evidence": "",
                "main_risk_evidence": "",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=research,
    )

    evidence = result["review_rows"].loc[0, "main_positive_evidence"]
    assert "主线环境" in evidence
    assert "研报/PDF覆盖" in evidence


def test_portfolio_review_derives_risk_evidence_from_structured_fields_when_blank() -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:603931",
                "ts_code": "603931.SH",
                "stock_name": "格林达",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.0,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "rotation",
                "mainline_status": "weak_mainline",
                "industry_name": "化工",
            }
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:603931",
                "ts_code": "603931.SH",
                "fundamental_hard_risk": "profit_quality_warning",
                "pdf_risk_section_count_90d": 2,
                "latest_pdf_risk_summary": "下游需求不及预期风险；产品价格波动风险。",
                "main_positive_evidence": "",
                "main_risk_evidence": "",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=research,
    )

    evidence = result["review_rows"].loc[0, "main_risk_evidence"]
    assert "硬风险" in evidence
    assert "风险段" in evidence


def test_portfolio_review_emits_structured_evidence_fields() -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "weight": 0.2,
            }
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 3,
                "research_support_score_pit": 33,
                "pdf_target_price_count_90d": 3,
                "pdf_profit_forecast_count_90d": 2,
                "pdf_risk_section_count_90d": 1,
                "fundamental_hard_risk": "no_clear_hard_risk",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=pd.DataFrame(),
        research_packet_candidates=research,
    )

    row = result["review_rows"].iloc[0]
    assert row["trend_market_regime_tag"] == "mainline"
    assert row["trend_mainline_status_tag"] == "sustained_mainline"
    assert row["trend_score_band_tag"] == "strong"
    assert row["research_support_band_tag"] == "high_support"
    assert row["research_report_coverage_tag"] == "dense_coverage"
    assert row["research_target_price_coverage_tag"] == "target_price_available"
    assert row["risk_fundamental_hard_risk_tag"] == "no_clear_hard_risk"
    assert row["risk_pdf_risk_coverage_tag"] == "risk_disclosed"
    assert row["risk_research_gap_tag"] == "supported"
    assert row["rebalance_action_tag"] == "hold_no_trade"
    assert row["rebalance_membership_tag"] == "current_holding"
    assert row["rebalance_rank_bucket_tag"] == "top3"


def test_portfolio_review_emits_rebalance_evidence_on_holding_day() -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-01",
                "asset_id": "CN:SH:600183",
                "weight": 0.2,
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-02",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=pd.DataFrame(),
        research_packet_candidates=pd.DataFrame(),
    )

    row = result["review_rows"].iloc[0]
    assert row["rebalance_action_tag"] == "hold_no_trade"
    assert row["rebalance_reason_evidence_summary"] != ""
    assert row["rebalance_trade_reason_tag"] == "carry_forward_hold"


def test_portfolio_review_aggregates_main_evidence_from_new_summaries() -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 3,
                "research_support_score_pit": 33,
                "pdf_target_price_count_90d": 3,
                "pdf_profit_forecast_count_90d": 2,
                "pdf_risk_section_count_90d": 1,
                "latest_pdf_risk_summary": "下游需求不及预期风险。",
                "fundamental_hard_risk": "no_clear_hard_risk",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=research,
    )

    row = result["review_rows"].iloc[0]
    assert "主线环境" in row["main_positive_evidence"]
    assert "研报/PDF覆盖" in row["main_positive_evidence"]
    assert "风险段:" in row["main_risk_evidence"]
    assert "动作:" in row["main_risk_evidence"]


def test_portfolio_review_markdown_renders_top5_as_per_stock_sections(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
                "shadow_top10_rank": 6,
                "mid_trend_funnel_score": 82.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "医疗器械",
            },
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 3,
                "research_support_score_pit": 33,
                "pdf_target_price_count_90d": 3,
                "pdf_profit_forecast_count_90d": 2,
                "pdf_risk_section_count_90d": 1,
                "latest_pdf_risk_summary": "下游需求不及预期风险。",
                "fundamental_hard_risk": "no_clear_hard_risk",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    markdown = result["markdown"]
    assert "## Top5 Overview" in markdown
    assert "## Evidence Snapshot" in markdown
    assert "### 1. 生益科技 / 600183.SH" in markdown
    assert "**Trend Evidence**" in markdown
    assert "**Research Evidence**" in markdown
    assert "**Risk Evidence**" in markdown
    assert "**Rebalance Reason Evidence**" in markdown


def test_portfolio_review_markdown_keeps_top6_10_as_compact_table(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
                "shadow_top10_rank": 6,
                "mid_trend_funnel_score": 82.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "医疗器械",
            },
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=pd.DataFrame(),
        output_dir=tmp_path,
    )

    markdown = result["markdown"]
    assert "## Top6-10 Discussion Pool" in markdown
    assert "| candidate_rank | stock_name | ts_code |" in markdown


def test_portfolio_review_includes_current_holding_even_when_not_in_top10(tmp_path: Path) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
                "shadow_top10_rank": 6,
                "mid_trend_funnel_score": 82.3,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "医疗器械",
            },
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "weight": 0.2,
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SZ:300831",
                "weight": 0.2,
            },
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SZ:300831",
                "ts_code": "300831.SZ",
                "stock_name": "派瑞股份",
                "research_support_score_pit": 5,
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=pd.DataFrame(),
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    review = result["review_rows"]
    markdown = result["markdown"]
    assert "CN:SZ:300831" in set(review.loc[review["section"].eq("top5"), "asset_id"])
    assert "### 2. 派瑞股份 / 300831.SZ" in markdown


def test_portfolio_review_derives_ts_code_and_name_for_holding_only_asset(monkeypatch) -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
            }
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SZ:300831",
                "weight": 0.2,
            }
        ]
    )
    monkeypatch.setattr(
        portfolio_review,
        "_load_review_stock_name_lookup",
        lambda ts_codes: {"300831.SZ": "派瑞股份"},
        raising=False,
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=pd.DataFrame(),
        research_packet_candidates=pd.DataFrame(),
    )

    row = result["review_rows"].iloc[0]
    assert row["ts_code"] == "300831.SZ"
    assert row["stock_name"] == "派瑞股份"
