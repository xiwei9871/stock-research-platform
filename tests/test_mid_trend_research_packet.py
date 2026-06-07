from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_research_packet import build_mid_trend_research_packet_from_frames


def _funnel_detail() -> pd.DataFrame:
    rows = []
    specs = [
        ("CN:SH:688001", "芯片A", "半导体", 105, 1),
        ("CN:SZ:300001", "算力B", "软件服务", 96, 2),
        ("CN:SH:600001", "设备C", "专用设备", 88, 3),
        ("CN:SZ:002001", "材料D", "化工材料", 82, 4),
        ("CN:SH:603001", "低分E", "汽车零部件", 78, 5),
        ("CN:SZ:000001", "候补F", "银行", 120, 6),
    ]
    for asset_id, stock_name, industry, score, rank in specs:
        rows.append(
            {
                "trade_date": "2026-05-19",
                "asset_id": asset_id,
                "ts_code": "",
                "stock_name": stock_name,
                "industry_name": industry,
                "rank": rank,
                "score_rank": rank,
                "market_regime": "mainline",
                "mainline_context": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.75,
                "mid_trend_layer": "stable_trend_watch",
                "mid_trend_funnel_score": score,
                "ret_20_score": 80,
                "ret_60_score": 90,
                "trend_r2_20_score": 85,
                "max_drawdown_20_score": 70,
                "volatility_20_score": 60,
            }
        )
    return pd.DataFrame(rows)


def _fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-05-16",
                "asset_id": "CN:SH:688001",
                "roe": 0.12,
                "gross_margin": 0.45,
                "net_margin": 0.14,
                "debt_ratio": 0.35,
                "revenue_yoy": 0.22,
                "np_yoy": 0.18,
                "deduct_np_yoy": 0.16,
                "ocf_to_np": 0.9,
                "np_parent_ttm": 100000000,
                "revenue_ttm": 1200000000,
                "equity_parent": 800000000,
                "total_share": 100000000,
                "float_share": 80000000,
            },
            {
                "trade_date": "2026-05-19",
                "asset_id": "CN:SZ:300001",
                "roe": -0.05,
                "gross_margin": 0.18,
                "net_margin": -0.08,
                "debt_ratio": 0.62,
                "revenue_yoy": -0.12,
                "np_yoy": -0.5,
                "deduct_np_yoy": -0.55,
                "ocf_to_np": -0.8,
                "np_parent_ttm": -50000000,
                "revenue_ttm": 500000000,
                "equity_parent": 300000000,
                "total_share": 100000000,
                "float_share": 70000000,
            },
        ]
    )


def _stock_report_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-05-19",
                "asset_id": "CN:SH:688001",
                "ts_code": "688001.SH",
                "stock_name": "芯片A",
                "report_count_90d": 4,
                "latest_report_days": 3,
                "positive_rating_count": 3,
                "rating_upgrade_count": 1,
                "target_price_median": 88.0,
                "target_upside_median": 0.22,
                "broker_coverage_count": 3,
                "research_support_score": 48.0,
                "metadata": {
                    "pdf_target_price_count_90d": 3,
                    "pdf_target_price_high_confidence_count_90d": 2,
                    "pdf_profit_forecast_count_90d": 2,
                    "pdf_risk_section_count_90d": 2,
                    "latest_pdf_risk_summary": "需求不及预期",
                },
            },
            {
                "trade_date": "2026-05-19",
                "asset_id": "CN:SZ:300001",
                "ts_code": "300001.SZ",
                "stock_name": "算力B",
                "report_count_90d": 0,
                "latest_report_days": pd.NA,
                "positive_rating_count": 0,
                "rating_upgrade_count": 0,
                "target_price_median": pd.NA,
                "target_upside_median": pd.NA,
                "broker_coverage_count": 0,
                "research_support_score": 0.0,
                "metadata": {
                    "pdf_target_price_count_90d": 0,
                    "pdf_target_price_high_confidence_count_90d": 0,
                    "pdf_profit_forecast_count_90d": 0,
                    "pdf_risk_section_count_90d": 0,
                    "latest_pdf_risk_summary": "",
                },
            },
        ]
    )


def test_research_packet_selects_by_funnel_score_then_score_floor_and_adds_manual_fields():
    result = build_mid_trend_research_packet_from_frames(
        _funnel_detail(),
        _fundamentals(),
        _stock_report_features(),
        trade_date="2026-05-19",
        top_n=5,
        score_floor=80,
    )

    candidates = result["candidates"]
    assert candidates["asset_id"].tolist() == [
        "CN:SZ:000001",
        "CN:SH:688001",
        "CN:SZ:300001",
        "CN:SH:600001",
        "CN:SZ:002001",
    ]
    assert "CN:SH:603001" not in set(candidates["asset_id"])
    assert set(candidates["human_review_status"]) == {"pending"}
    assert {"domestic_report_query", "foreign_report_query", "target_price_query", "research_view"}.issubset(
        candidates.columns
    )
    assert "买入" not in " ".join(candidates["operator_review_note"].astype(str))


def test_research_packet_uses_latest_prior_fundamental_row_without_future_leakage():
    result = build_mid_trend_research_packet_from_frames(
        _funnel_detail(),
        _fundamentals(),
        _stock_report_features(),
        trade_date="2026-05-19",
        top_n=5,
        score_floor=80,
    )

    candidates = result["candidates"]
    chip = candidates[candidates["asset_id"].eq("CN:SH:688001")].iloc[0]
    software = candidates[candidates["asset_id"].eq("CN:SZ:300001")].iloc[0]
    assert chip["roe"] == 0.12
    assert chip["fundamental_hard_risk"] == "no_clear_hard_risk"
    assert software["fundamental_hard_risk"] == "loss_or_deterioration_risk"


def test_research_packet_falls_back_to_ts_code_when_stock_name_missing():
    detail = _funnel_detail()
    detail.loc[0, "stock_name"] = pd.NA
    detail.loc[0, "ts_code"] = pd.NA

    result = build_mid_trend_research_packet_from_frames(
        detail,
        _fundamentals(),
        _stock_report_features(),
        trade_date="2026-05-19",
        top_n=5,
        score_floor=80,
    )

    row = result["candidates"][result["candidates"]["asset_id"].eq("CN:SH:688001")].iloc[0]
    assert row["stock_name"] == "688001.SH"
    assert "688001.SH" in row["domestic_report_query"]


def test_research_packet_writes_outputs(tmp_path: Path):
    result = build_mid_trend_research_packet_from_frames(
        _funnel_detail(),
        _fundamentals(),
        _stock_report_features(),
        trade_date="2026-05-19",
        top_n=5,
        score_floor=80,
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["candidates"]).exists()
    assert Path(result["paths"]["manual_fields"]).exists()
    assert Path(result["paths"]["report"]).exists()
    assert "Mid Trend Research Packet" in Path(result["paths"]["report"]).read_text(encoding="utf-8")


def test_research_packet_enriches_candidates_with_stock_report_pit_fields():
    result = build_mid_trend_research_packet_from_frames(
        _funnel_detail(),
        _fundamentals(),
        _stock_report_features(),
        trade_date="2026-05-19",
        top_n=5,
        score_floor=80,
    )

    candidates = result["candidates"]
    chip = candidates[candidates["asset_id"].eq("CN:SH:688001")].iloc[0]
    software = candidates[candidates["asset_id"].eq("CN:SZ:300001")].iloc[0]
    assert chip["broker_report_count_90d"] == 4
    assert chip["research_support_score_pit"] == 48.0
    assert chip["pdf_target_price_count_90d"] == 3
    assert chip["pdf_target_price_high_confidence_count_90d"] == 2
    assert chip["pdf_profit_forecast_count_90d"] == 2
    assert chip["latest_pdf_risk_summary"] == "需求不及预期"
    assert software["broker_report_count_90d"] == 0
    assert software["pdf_target_price_count_90d"] == 0


def test_cli_dispatches_mid_trend_research_packet(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "candidates": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "candidates": str(tmp_path / "candidates.csv"),
                "manual_fields": str(tmp_path / "manual.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_research_packet", fake_run)

    cli.main_for_args(
        [
            "build-mid-trend-research-packet",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--fundamental-path",
            "outputs/research/watchlist_fundamental_pit_context.csv",
            "--trade-date",
            "2026-05-19",
            "--top-n",
            "5",
            "--score-floor",
            "80",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-05-19"
    assert captured["top_n"] == 5
    assert captured["score_floor"] == 80
    out = capsys.readouterr().out
    assert "mid_trend_research_packet|candidates|" in out
    assert "mid_trend_research_packet|rows|1" in out
