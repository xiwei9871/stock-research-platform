from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_watchlist_report_fundamental_patch.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_report_fundamental_patch", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_inputs(tmp_path: Path):
    report_a = tmp_path / "a.md"
    report_b = tmp_path / "b.md"
    report_a.write_text("# 样本A\n\n已有公告全文补丁。\n", encoding="utf-8")
    report_b.write_text("# 样本B\n\n已有公告全文补丁。\n", encoding="utf-8")
    announcement_index = pd.DataFrame(
        [
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "old_report_path": str(report_a),
                "fulltext_patched_report_path": str(report_a),
            },
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "old_report_path": str(report_b),
                "fulltext_patched_report_path": str(report_b),
            },
        ]
    )
    structured = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "report_period": "2026-03-31",
                "financial_as_of_date": "2026-03-31",
                "announcement_date": "2026-04-28",
                "as_of_date": "2026-04-28",
                "source_type": "fundamentals",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "revenue_growth_yoy": 0.25,
                "net_profit_growth_yoy": 0.30,
                "deducted_net_profit_growth_yoy": 0.28,
                "gross_margin": 0.38,
                "gross_margin_trend": 0.02,
                "operating_cashflow_to_profit": 1.1,
                "cashflow_quality_score": 0.8,
                "debt_to_asset": 0.32,
                "debt_risk_score": 0.1,
                "inventory_risk_score": 0.5,
                "receivable_risk_score": 0.5,
                "rd_intensity_score": 0.5,
                "capex_intensity_score": 0.5,
                "fundamental_recovery_score": 0.72,
                "fundamental_risk_score": 0.25,
                "fundamental_quality_score": 0.70,
                "missing_fields": "revenue|net_profit|operating_cashflow|inventory_growth_yoy|receivable_growth_yoy|rd_expense_ratio|capex",
                "data_quality_status": "degraded_missing_optional_fields",
            }
        ]
    )
    coverage = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "fundamental_record_count": 1,
                "pit_valid_record_count": 1,
                "latest_report_period": "2026-03-31",
                "latest_financial_as_of_date": "2026-03-31",
                "has_revenue_growth": True,
                "has_profit_growth": True,
                "has_gross_margin": True,
                "has_cashflow_quality": True,
                "has_debt_risk": True,
                "has_inventory_risk": False,
                "has_receivable_risk": False,
                "has_rd_intensity": False,
                "fundamental_recovery_score_latest": 0.72,
                "fundamental_risk_score_latest": 0.25,
                "fundamental_quality_score_latest": 0.70,
                "coverage_status": "covered_degraded_optional_fields",
            },
            {
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "fundamental_record_count": 0,
                "pit_valid_record_count": 0,
                "latest_report_period": "missing",
                "latest_financial_as_of_date": "missing",
                "has_revenue_growth": False,
                "has_profit_growth": False,
                "has_gross_margin": False,
                "has_cashflow_quality": False,
                "has_debt_risk": False,
                "has_inventory_risk": False,
                "has_receivable_risk": False,
                "has_rd_intensity": False,
                "fundamental_recovery_score_latest": "",
                "fundamental_risk_score_latest": "",
                "fundamental_quality_score_latest": "",
                "coverage_status": "fundamentals_missing",
            },
        ]
    )
    field_audit = pd.DataFrame(
        [
            {"field_name": "net_profit_growth_yoy", "coverage_ratio": 1.0},
            {"field_name": "gross_margin", "coverage_ratio": 1.0},
            {"field_name": "revenue", "coverage_ratio": 0.0},
            {"field_name": "operating_cashflow", "coverage_ratio": 0.0},
        ]
    )
    quality = pd.DataFrame(
        [
            {"metric": "lookahead_violation_rows", "value": 0, "note": "must be zero"},
            {"metric": "PIT_valid_ratio", "value": 1.0, "note": "pit"},
        ]
    )
    return announcement_index, structured, coverage, field_audit, quality


def test_generates_fundamental_patched_report_for_all_assets(tmp_path: Path) -> None:
    module = _load_module()
    announcement_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    result = module.generate_fundamental_patched_reports(tmp_path / "out", announcement_index, structured, coverage, field_audit, quality)
    index = result["index"]

    assert len(index) == 2
    assert index["fundamental_patched_report_path"].map(lambda value: Path(value).exists()).all()


def test_patch_status_tracks_fundamental_support(tmp_path: Path) -> None:
    module = _load_module()
    announcement_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    index = module.generate_fundamental_patched_reports(tmp_path / "out", announcement_index, structured, coverage, field_audit, quality)["index"]
    by_asset = dict(zip(index["asset_id"], index["patch_status"]))

    assert by_asset["CN:SZ:000001"] == "patched_with_fundamentals"
    assert by_asset["CN:SZ:000002"] == "no_fundamental_support"


def test_fundamental_layers_are_conservative_for_degraded_data(tmp_path: Path) -> None:
    module = _load_module()
    _, structured, _, _, _ = _sample_inputs(tmp_path)

    layers = module.classify_fundamental_layers(structured.iloc[0])

    assert layers["fundamental_recovery_signal"] == "recovery_positive"
    assert layers["fundamental_risk_level"] == "risk_medium"
    assert layers["fundamental_quality_level"] == "quality_medium"


def test_report_marks_derived_and_missing_detail_coverage(tmp_path: Path) -> None:
    module = _load_module()
    announcement_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    index = module.generate_fundamental_patched_reports(tmp_path / "out", announcement_index, structured, coverage, field_audit, quality)["index"]
    content = Path(index.loc[index["asset_id"].eq("CN:SZ:000001"), "fundamental_patched_report_path"].iloc[0]).read_text(encoding="utf-8")

    assert "Fundamental Evidence Patch" in content
    assert "PIT derived features" in content
    assert "degraded detail coverage" in content
    assert "missing financial fields" in content
    assert "cannot be interpreted as no risk" in content
    assert not module.contains_actionable_trading_language(content)


def test_missing_support_report_does_not_imply_no_risk(tmp_path: Path) -> None:
    module = _load_module()
    announcement_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    index = module.generate_fundamental_patched_reports(tmp_path / "out", announcement_index, structured, coverage, field_audit, quality)["index"]
    content = Path(index.loc[index["asset_id"].eq("CN:SZ:000002"), "fundamental_patched_report_path"].iloc[0]).read_text(encoding="utf-8")

    assert "fundamental support: missing" in content
    assert "missing cannot be interpreted as no risk" in content
    assert not module.contains_actionable_trading_language(content)


def test_audit_zero_language_zero_lookahead_and_no_execution_fields(tmp_path: Path) -> None:
    module = _load_module()
    announcement_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    result = module.generate_fundamental_patched_reports(tmp_path / "out", announcement_index, structured, coverage, field_audit, quality)
    audit = result["audit"]
    index = result["index"]
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["reports_with_trading_language"])) == 0
    assert int(float(lookup["lookahead_violation_rows"])) == 0
    assert int(float(lookup["patch_failures"])) == 0
    assert "target_price" not in index.columns
    assert "position_size" not in index.columns


def test_report_mentions_untracked_strategy_status(tmp_path: Path) -> None:
    module = _load_module()
    _, _, coverage, field_audit, quality = _sample_inputs(tmp_path)
    index = pd.DataFrame(
        {
            "patch_status": ["patched_with_fundamentals"],
            "fundamental_support": [True],
            "fundamental_recovery_signal": ["recovery_positive"],
            "fundamental_risk_level": ["risk_medium"],
            "fundamental_quality_level": ["quality_medium"],
        }
    )
    audit = pd.DataFrame({"metric": ["reports_with_trading_language", "lookahead_violation_rows", "patch_failures"], "value": [0, 0, 0], "note": ["", "", ""]})

    text = module.render_main_report(
        index=index,
        summary=coverage,
        audit=audit,
        field_audit=field_audit,
        quality_audit=quality,
        git_info={
            "repo_root": "/repo",
            "formal_strategy_status": "?? src/stock_research/tech_bottleneck_v1.py",
            "formal_strategy_ls_files": "",
            "formal_strategy_stat": "untracked",
        },
    )

    assert "untracked" in text
    assert not module.contains_actionable_trading_language(text)
