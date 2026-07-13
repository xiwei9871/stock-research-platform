from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_research_input_watchlist_forward_return.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_research_input_watchlist_forward_return", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_structured_output_contains_pit_fields_and_no_lookahead() -> None:
    module = _load_module()
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-10",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本",
                "research_priority": "medium",
                "industry_bottleneck_theme": "test_theme",
                "low_position_score": 0.7,
                "commercial_validation_score": 0.5,
                "fundamental_risk_score": 0.0,
                "data_quality_status": "ok",
            }
        ]
    )
    low_position = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-10",
                "asset_id": "CN:SZ:000001",
                "price_position_score": 0.8,
                "valuation_position_score": pd.NA,
                "expectation_position_score": pd.NA,
                "fundamental_position_score": pd.NA,
                "technical_position_score": 0.6,
                "low_position_score": 0.7,
            }
        ]
    )
    risk = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-10",
                "asset_id": "CN:SZ:000001",
                "risk_flags": "valuation_missing",
                "fundamental_risk_score": 0.0,
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "field": "customer_certification_stage",
                "source_type": "broker_report",
                "source_path": "report.pdf",
                "source_date": "2026-01-09",
                "claim": "客户验证",
                "evidence_tier": "tier2",
            }
        ]
    )

    result = module.build_structured_outputs(candidates, low_position, risk, evidence)

    assert {"source_date", "as_of_date", "is_pit_valid", "lookahead_violation"}.issubset(result.columns)
    module.validate_structured_output_pit(result)
    assert int(result["lookahead_violation"].sum()) == 0


def test_structured_output_rejects_future_source_date() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-10"],
            "source_date": ["2026-01-11"],
            "as_of_date": ["2026-01-10"],
            "lookahead_violation": [True],
        }
    )

    with pytest.raises(ValueError, match="lookahead"):
        module.validate_structured_output_pit(frame)


def test_missing_fields_do_not_create_0p6_penalty() -> None:
    module = _load_module()
    row = pd.Series({"source_confidence": pd.NA, "extraction_confidence": pd.NA})

    confidence = module.neutral_confidence(row.get("source_confidence"))

    assert confidence == 0.5
    assert confidence != 0.6


def test_watchlist_admission_has_no_trading_language() -> None:
    module = _load_module()
    structured = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-10",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本",
                "stock_event_id": "e1",
                "source_type": "broker_report",
                "source_date": "2026-01-09",
                "industry_bottleneck_theme": "theme",
                "bottleneck_theme": "theme",
                "key_thesis": "clear thesis",
                "commercial_validation_score": 0.8,
                "customer_validation_score": 0.8,
                "announcement_validation_score": 0.0,
                "low_position_score": 0.8,
                "price_position_score": 0.8,
                "fundamental_risk_score": 0.0,
                "source_confidence": 0.8,
                "extraction_confidence": 0.8,
                "data_quality_status": "ok",
                "is_pit_valid": True,
                "conflict_flags": "",
            }
        ]
    )

    admissions = module.build_watchlist_admissions(structured)

    assert not admissions.empty
    module.validate_no_trading_language(admissions)
    assert "entry_signal" not in admissions.columns


def test_forward_return_uses_only_30_60_90_120_and_is_research_only() -> None:
    module = _load_module()
    admissions = pd.DataFrame(
        {
            "admission_variant": ["loose_research_watchlist"],
            "asset_id": ["A"],
            "symbol": ["A"],
            "name": ["A"],
            "first_admission_date": ["2026-01-01"],
        }
    )
    prices = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=130, freq="D").strftime("%Y-%m-%d"),
            "asset_id": ["A"] * 130,
            "close": range(100, 230),
        }
    )

    forward = module.build_watchlist_forward_returns(admissions, prices)

    assert set(forward["horizon"].unique()) == {"30d", "60d", "90d", "120d"}
    assert not forward["used_for_signal"].astype(bool).any()


def test_quality_audit_reports_zero_lookahead_for_valid_structured_outputs() -> None:
    module = _load_module()
    structured = pd.DataFrame(
        {
            "trade_date": ["2026-01-10"],
            "asset_id": ["A"],
            "stock_event_id": ["event"],
            "source_type": ["broker_report"],
            "is_pit_valid": [True],
            "lookahead_violation": [False],
            "key_thesis": ["x"],
            "commercial_validation_score": [0.8],
            "fundamental_recovery_score": [pd.NA],
            "valuation_position_score": [pd.NA],
            "low_position_score": [0.7],
            "extraction_confidence": [0.8],
            "source_confidence": [0.8],
            "conflict_flags": [""],
            "data_quality_status": ["ok"],
        }
    )

    audit = module.build_quality_audit(structured)
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["lookahead_violation_rows"])) == 0
