from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.stock_report_research import build_stock_report_workpack_from_candidates


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002484",
                "ts_code": "002484.SZ",
                "stock_name": "江海股份",
                "industry_name": "电子元件",
                "research_packet_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "fundamental_hard_risk": "no_clear_hard_risk",
                "research_view": "weak_research_support_pending_manual",
                "domestic_report_query": "江海股份 研报 目标价 评级",
                "industry_position_query": "江海股份 行业地位 市占率 龙头",
                "broker_report_count_90d": 4,
                "research_support_score_pit": 48.0,
                "target_price_median_pit": 88.0,
                "target_upside_median_pit": 0.22,
                "broker_coverage_count_pit": 3,
                "pdf_target_price_count_90d": 3,
                "pdf_target_price_high_confidence_count_90d": 2,
                "pdf_profit_forecast_count_90d": 2,
                "pdf_risk_section_count_90d": 2,
                "latest_pdf_risk_summary": "需求不及预期",
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:002552",
                "ts_code": "002552.SZ",
                "stock_name": "宝鼎科技",
                "industry_name": "电子设备",
                "research_packet_rank": 4,
                "mid_trend_funnel_score": 83.9,
                "fundamental_hard_risk": "loss_or_deterioration_risk",
                "research_view": "negative_or_uncertain",
                "domestic_report_query": "宝鼎科技 研报 目标价 评级",
                "industry_position_query": "宝鼎科技 行业地位 市占率 龙头",
                "broker_report_count_90d": 0,
                "research_support_score_pit": 0.0,
                "target_price_median_pit": pd.NA,
                "target_upside_median_pit": pd.NA,
                "broker_coverage_count_pit": 0,
                "pdf_target_price_count_90d": 0,
                "pdf_target_price_high_confidence_count_90d": 0,
                "pdf_profit_forecast_count_90d": 0,
                "pdf_risk_section_count_90d": 0,
                "latest_pdf_risk_summary": "",
            },
        ]
    )


def test_stock_report_workpack_builds_candidates_template_and_report():
    result = build_stock_report_workpack_from_candidates(_candidates(), trade_date="2026-06-02")

    workpack = result["workpack"]
    template = result["import_template"]
    assert workpack["ts_code"].tolist() == ["002484.SZ", "002552.SZ"]
    assert "domestic_broker_report_query" in workpack.columns
    assert "foreign_report_query" in workpack.columns
    assert "stock_report_manual_review" in result["report"]
    assert "report_id" in template.columns
    assert "target_price" in template.columns
    assert "moat_or_scarcity_note" in template.columns
    assert set(template["review_status"]) == {"pending"}
    assert "买入" not in result["report"]
    assert "broker_report_count_90d" in workpack.columns
    assert "pdf_target_price_count_90d" in workpack.columns
    assert workpack.iloc[0]["pdf_target_price_count_90d"] == 3
    assert workpack.iloc[0]["latest_pdf_risk_summary"] == "需求不及预期"


def test_stock_report_workpack_writes_outputs(tmp_path: Path):
    result = build_stock_report_workpack_from_candidates(
        _candidates(),
        trade_date="2026-06-02",
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["workpack"]).exists()
    assert Path(result["paths"]["import_template"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_stock_report_workpack(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "workpack": pd.DataFrame([{"ts_code": "002484.SZ"}]),
            "paths": {
                "workpack": str(tmp_path / "workpack.csv"),
                "import_template": str(tmp_path / "template.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_stock_report_workpack", fake_run)

    cli.main_for_args(
        [
            "build-stock-report-workpack",
            "--research-packet-path",
            "outputs/research/mid_trend_research_packet_20260602/mid_trend_research_packet_candidates.csv",
            "--trade-date",
            "2026-06-02",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-06-02"
    out = capsys.readouterr().out
    assert "stock_report_workpack|workpack|" in out
    assert "stock_report_workpack|rows|1" in out
