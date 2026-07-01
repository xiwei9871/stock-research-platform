from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_watchlist_report_valuation_patch.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_report_valuation_patch", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_inputs(tmp_path: Path):
    report_a = tmp_path / "a.md"
    report_b = tmp_path / "b.md"
    report_a.write_text("# 样本A\n\n已有基本面补丁。\n", encoding="utf-8")
    report_b.write_text("# 样本B\n\n已有基本面补丁。\n", encoding="utf-8")
    fundamental_index = pd.DataFrame(
        [
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "old_report_path": str(report_a),
                "fundamental_patched_report_path": str(report_a),
            },
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "old_report_path": str(report_b),
                "fundamental_patched_report_path": str(report_b),
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
                "source_type": "valuation",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "market_cap": 120.0,
                "valuation_position_score": 0.2,
                "valuation_risk_score": 0.8,
                "valuation_quality_score": 0.25,
                "valuation_level": "valuation_high",
                "valuation_data_status": "market_cap_context_only",
                "missing_fields": "pe_ttm|pb|ps_ttm|ev_ebitda|float_market_cap|valuation_percentile_1y|valuation_percentile_3y|valuation_percentile_5y|industry_valuation_percentile",
                "data_quality_status": "degraded_market_cap_only",
                "as_of_date": "2026-06-12",
            }
        ]
    )
    coverage = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "valuation_record_count": 1,
                "pit_valid_record_count": 1,
                "latest_trade_date": "2026-06-29",
                "has_pe_ttm": False,
                "has_pb": False,
                "has_ps_ttm": False,
                "has_ev_ebitda": False,
                "has_market_cap": True,
                "has_float_market_cap": False,
                "has_valuation_percentile_1y": False,
                "has_valuation_percentile_3y": False,
                "has_valuation_percentile_5y": False,
                "has_industry_valuation_percentile": False,
                "valuation_position_score_latest": 0.2,
                "valuation_risk_score_latest": 0.8,
                "valuation_quality_score_latest": 0.25,
                "valuation_level_latest": "valuation_high",
                "coverage_status": "covered_market_cap_only",
            },
            {
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "valuation_record_count": 0,
                "pit_valid_record_count": 0,
                "latest_trade_date": "missing",
                "has_pe_ttm": False,
                "has_pb": False,
                "has_ps_ttm": False,
                "has_ev_ebitda": False,
                "has_market_cap": False,
                "has_float_market_cap": False,
                "has_valuation_percentile_1y": False,
                "has_valuation_percentile_3y": False,
                "has_valuation_percentile_5y": False,
                "has_industry_valuation_percentile": False,
                "valuation_position_score_latest": "",
                "valuation_risk_score_latest": "",
                "valuation_quality_score_latest": "",
                "valuation_level_latest": "valuation_missing",
                "coverage_status": "valuation_missing",
            },
        ]
    )
    field_audit = pd.DataFrame(
        [
            {"field_name": "market_cap", "coverage_ratio": 1.0},
            {"field_name": "pe_ttm", "coverage_ratio": 0.0},
            {"field_name": "pb", "coverage_ratio": 0.0},
            {"field_name": "ps_ttm", "coverage_ratio": 0.0},
        ]
    )
    quality = pd.DataFrame(
        [
            {"metric": "lookahead_violation_rows", "value": 0, "note": "must be zero"},
            {"metric": "PIT_valid_ratio", "value": 1.0, "note": "pit"},
        ]
    )
    return fundamental_index, structured, coverage, field_audit, quality


def test_generates_valuation_patched_report_for_all_assets(tmp_path: Path) -> None:
    module = _load_module()
    fundamental_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    result = module.generate_valuation_patched_reports(tmp_path / "out", fundamental_index, structured, coverage, field_audit, quality)
    index = result["index"]

    assert len(index) == 2
    assert index["valuation_patched_report_path"].map(lambda value: Path(value).exists()).all()


def test_patch_status_tracks_valuation_support(tmp_path: Path) -> None:
    module = _load_module()
    fundamental_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    index = module.generate_valuation_patched_reports(tmp_path / "out", fundamental_index, structured, coverage, field_audit, quality)["index"]
    by_asset = dict(zip(index["asset_id"], index["patch_status"]))

    assert by_asset["CN:SZ:000001"] == "patched_with_valuation"
    assert by_asset["CN:SZ:000002"] == "no_valuation_support"


def test_detail_quality_and_review_flag_are_conservative(tmp_path: Path) -> None:
    module = _load_module()
    _, structured, _, _, _ = _sample_inputs(tmp_path)

    detail = module.classify_valuation_detail_quality(structured.iloc[0])
    flag = module.classify_valuation_review_flag(structured.iloc[0])

    assert detail == "detail_degraded_market_cap_only"
    assert flag in {"review_market_cap_context", "request_pe_pb_ps_data"}


def test_report_marks_market_cap_only_and_no_directional_execution_terms(tmp_path: Path) -> None:
    module = _load_module()
    fundamental_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    index = module.generate_valuation_patched_reports(tmp_path / "out", fundamental_index, structured, coverage, field_audit, quality)["index"]
    content = Path(index.loc[index["asset_id"].eq("CN:SZ:000001"), "valuation_patched_report_path"].iloc[0]).read_text(encoding="utf-8")

    assert "Valuation Context Patch" in content
    assert "market-cap-only" in content
    assert "degraded detail coverage" in content
    assert "not a complete PE/PB/PS valuation conclusion" in content
    assert "does not imply automated action" in content
    assert not module.contains_actionable_trading_language(content)


def test_missing_support_report_is_explicit(tmp_path: Path) -> None:
    module = _load_module()
    fundamental_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    index = module.generate_valuation_patched_reports(tmp_path / "out", fundamental_index, structured, coverage, field_audit, quality)["index"]
    content = Path(index.loc[index["asset_id"].eq("CN:SZ:000002"), "valuation_patched_report_path"].iloc[0]).read_text(encoding="utf-8")

    assert "valuation support: missing" in content
    assert "missing valuation data cannot be interpreted as low or high valuation" in content
    assert not module.contains_actionable_trading_language(content)


def test_audit_zero_language_zero_lookahead_and_no_execution_fields(tmp_path: Path) -> None:
    module = _load_module()
    fundamental_index, structured, coverage, field_audit, quality = _sample_inputs(tmp_path)

    result = module.generate_valuation_patched_reports(tmp_path / "out", fundamental_index, structured, coverage, field_audit, quality)
    audit = result["audit"]
    index = result["index"]
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["reports_with_trading_language"])) == 0
    assert int(float(lookup["lookahead_violation_rows"])) == 0
    assert int(float(lookup["patch_failures"])) == 0
    assert "target_price" not in index.columns
    assert "entry_signal" not in index.columns


def test_main_report_mentions_untracked_strategy_status(tmp_path: Path) -> None:
    module = _load_module()
    _, _, coverage, field_audit, quality = _sample_inputs(tmp_path)
    index = pd.DataFrame(
        {
            "patch_status": ["patched_with_valuation"],
            "valuation_support": [True],
            "valuation_context_level": ["valuation_high"],
            "valuation_detail_quality": ["detail_degraded_market_cap_only"],
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
