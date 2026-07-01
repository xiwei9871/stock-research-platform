from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_watchlist_stock_report.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_stock_report", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    admissions = pd.DataFrame(
        [
            {
                "admission_variant": "standard_research_watchlist",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "first_admission_date": "2026-01-10",
                "first_source_date": "2026-01-09",
                "stock_event_id": "event-a",
                "source_type": "broker_report",
                "industry_bottleneck_theme": "国产替代",
                "bottleneck_theme": "国产替代",
                "admission_reason": "standard_research_coverage",
                "research_priority": "medium",
                "low_position_score": 0.7,
                "commercial_validation_score": 0.8,
                "fundamental_risk_score": 0.0,
                "source_confidence": 0.8,
                "extraction_confidence": 0.8,
                "data_quality_status": "degraded_coverage",
                "human_review_required": True,
            },
            {
                "admission_variant": "loose_research_watchlist",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "first_admission_date": "2026-01-10",
            },
        ]
    )
    structured = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-10",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "stock_event_id": "event-a",
                "source_type": "broker_report",
                "source_id": "report.pdf",
                "source_date": "2026-01-09",
                "as_of_date": "2026-01-09",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "industry_bottleneck_theme": "国产替代",
                "bottleneck_theme": "国产替代",
                "key_thesis": "具备国产替代研究线索",
                "evidence_tags": "customer_certification_stage|revenue_exposure_bucket",
                "commercial_validation_score": 0.8,
                "customer_validation_score": 0.8,
                "announcement_validation_score": 0.0,
                "revenue_exposure_score": 0.75,
                "supplier_dependency_risk": 0.2,
                "policy_catalyst_score": 0.0,
                "fundamental_recovery_score": pd.NA,
                "fundamental_risk_score": 0.0,
                "price_position_score": 0.7,
                "valuation_position_score": pd.NA,
                "expectation_position_score": pd.NA,
                "fundamental_position_score": pd.NA,
                "technical_position_score": 0.6,
                "low_position_score": 0.7,
                "source_confidence": 0.8,
                "extraction_confidence": 0.8,
                "data_quality_status": "degraded_coverage",
                "missing_fields": "valuation_position_score|fundamental_position_score",
                "conflict_flags": "",
                "research_priority": "medium",
                "risk_flags": "valuation_missing|fundamental_missing",
            }
        ]
    )
    forward = pd.DataFrame(
        [
            {
                "admission_variant": "standard_research_watchlist",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "first_admission_date": "2026-01-10",
                "horizon": horizon,
                "forward_return": 0.1,
                "forward_return_vs_market": 0.02,
                "future_data_available": True,
                "used_for_signal": False,
            }
            for horizon in ["30d", "60d", "90d", "120d"]
        ]
    )
    review_cards = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-10",
                "asset_id": "CN:SZ:000001",
                "risk_summary": "valuation/fundamental fields missing",
                "why_in_pool": "具备国产替代研究线索",
                "data_quality_status": "degraded_coverage",
            }
        ]
    )
    return admissions, structured, forward, review_cards


def test_reports_are_generated_only_for_standard_watchlist(tmp_path: Path) -> None:
    module = _load_module()
    admissions, structured, forward, review_cards = _sample_inputs()

    result = module.generate_reports(tmp_path, admissions, structured, forward, review_cards, optional_review_artifact_exists=False)

    assert len(result["index"]) == 1
    assert result["index"]["admission_variant"].eq("standard_research_watchlist").all()
    assert Path(result["index"].iloc[0]["report_path"]).exists()


def test_report_contains_disclaimer_and_boundary_language(tmp_path: Path) -> None:
    module = _load_module()
    admissions, structured, forward, review_cards = _sample_inputs()

    result = module.generate_reports(tmp_path, admissions, structured, forward, review_cards, optional_review_artifact_exists=False)
    content = Path(result["index"].iloc[0]["report_path"]).read_text(encoding="utf-8")

    assert "Non-trading Disclaimer" in content
    assert "仅用于事后复盘" in content
    assert "不构成交易信号" in content
    assert not module.contains_actionable_trading_language(content)


def test_missing_fields_are_rendered_as_missing(tmp_path: Path) -> None:
    module = _load_module()
    admissions, structured, forward, review_cards = _sample_inputs()

    result = module.generate_reports(tmp_path, admissions, structured, forward, review_cards, optional_review_artifact_exists=False)
    content = Path(result["index"].iloc[0]["report_path"]).read_text(encoding="utf-8")

    assert "missing" in content
    assert "不得编造" not in content


def test_quality_audit_reports_no_actionable_trading_language_and_no_lookahead(tmp_path: Path) -> None:
    module = _load_module()
    admissions, structured, forward, review_cards = _sample_inputs()

    result = module.generate_reports(tmp_path, admissions, structured, forward, review_cards, optional_review_artifact_exists=False)
    audit = result["audit"]
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["reports_with_trading_language"])) == 0
    assert int(float(lookup["lookahead_violation_rows"])) == 0


def test_future_lookahead_is_rejected_in_report_inputs(tmp_path: Path) -> None:
    module = _load_module()
    admissions, structured, forward, review_cards = _sample_inputs()
    structured.loc[0, "lookahead_violation"] = True

    with pytest.raises(ValueError, match="lookahead"):
        module.generate_reports(tmp_path, admissions, structured, forward, review_cards, optional_review_artifact_exists=False)
