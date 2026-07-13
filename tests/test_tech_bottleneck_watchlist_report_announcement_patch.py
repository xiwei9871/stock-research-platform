from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_watchlist_report_announcement_patch.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_report_announcement_patch", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_inputs(tmp_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    old_a = tmp_path / "old_a.md"
    old_b = tmp_path / "old_b.md"
    old_a.write_text("# 样本A\n\n原始观察池报告。\n", encoding="utf-8")
    old_b.write_text("# 样本B\n\n原始观察池报告。\n", encoding="utf-8")
    report_index = pd.DataFrame(
        [
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "report_path": str(old_a),
            },
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "report_path": str(old_b),
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
                "announcement_id": "ann-positive",
                "announcement_title": "样本A重大合同公告",
                "announcement_date": "2026-01-01",
                "as_of_date": "2026-01-01",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "announcement_type": "order_contract",
                "order_contract": True,
                "customer_contract": False,
                "capacity_project": False,
                "fundraising_project": False,
                "equity_incentive": False,
                "financial_guidance": False,
                "performance_forecast": False,
                "risk_disclosure": False,
                "litigation_or_penalty": False,
                "announcement_validation_score": 0.45,
                "risk_event_score": 0.0,
                "extraction_confidence": 0.35,
                "extraction_method": "keyword_title_only",
                "data_quality_status": "title_only",
            },
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "announcement_id": "ann-risk",
                "announcement_title": "样本A风险提示公告",
                "announcement_date": "2026-02-01",
                "as_of_date": "2026-02-01",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "announcement_type": "risk_disclosure",
                "order_contract": False,
                "customer_contract": False,
                "capacity_project": False,
                "fundraising_project": False,
                "equity_incentive": False,
                "financial_guidance": False,
                "performance_forecast": False,
                "risk_disclosure": True,
                "litigation_or_penalty": False,
                "announcement_validation_score": 0.0,
                "risk_event_score": 0.7,
                "extraction_confidence": 0.35,
                "extraction_method": "keyword_title_only",
                "data_quality_status": "title_only",
            },
        ]
    )
    asset_coverage = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "announcement_count": 2,
                "pit_valid_announcement_count": 2,
                "latest_announcement_date": "2026-02-01",
            },
            {
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "announcement_count": 0,
                "pit_valid_announcement_count": 0,
                "latest_announcement_date": "missing",
            },
        ]
    )
    ingestion_audit = pd.DataFrame(
        [
            {"metric": "lookahead_violation_rows", "value": 0, "note": "must be zero"},
            {"metric": "PIT_valid_ratio", "value": 1.0, "note": "PIT valid rows"},
        ]
    )
    return report_index, structured, asset_coverage, ingestion_audit


def test_generates_patched_reports_for_all_standard_assets(tmp_path: Path) -> None:
    module = _load_module()
    report_index, structured, asset_coverage, ingestion_audit = _sample_inputs(tmp_path)

    result = module.generate_patched_reports(tmp_path / "out", report_index, structured, asset_coverage, ingestion_audit)

    index = result["index"]
    assert len(index) == 2
    assert index["patched_report_path"].map(lambda p: Path(p).exists()).all()


def test_patch_status_tracks_assets_with_and_without_announcement_support(tmp_path: Path) -> None:
    module = _load_module()
    report_index, structured, asset_coverage, ingestion_audit = _sample_inputs(tmp_path)

    index = module.generate_patched_reports(tmp_path / "out", report_index, structured, asset_coverage, ingestion_audit)["index"]

    by_asset = dict(zip(index["asset_id"], index["patch_status"]))
    assert by_asset["CN:SZ:000001"] == "patched_with_announcement"
    assert by_asset["CN:SZ:000002"] == "no_announcement_support"


def test_report_marks_title_only_positive_and_risk_review(tmp_path: Path) -> None:
    module = _load_module()
    report_index, structured, asset_coverage, ingestion_audit = _sample_inputs(tmp_path)

    index = module.generate_patched_reports(tmp_path / "out", report_index, structured, asset_coverage, ingestion_audit)["index"]
    content = Path(index.loc[index["asset_id"].eq("CN:SZ:000001"), "patched_report_path"].iloc[0]).read_text(encoding="utf-8")

    assert "title-only" in content
    assert "弱公告线索" in content
    assert "人工复核公告原文" in content
    assert "正向验证线索" in content
    assert "风险线索存在" in content
    assert not module.contains_actionable_trading_language(content)


def test_audit_reports_no_trading_language_and_no_lookahead(tmp_path: Path) -> None:
    module = _load_module()
    report_index, structured, asset_coverage, ingestion_audit = _sample_inputs(tmp_path)

    audit = module.generate_patched_reports(tmp_path / "out", report_index, structured, asset_coverage, ingestion_audit)["audit"]
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["reports_with_trading_language"])) == 0
    assert int(float(lookup["lookahead_violation_rows"])) == 0


def test_lookahead_rows_are_rejected(tmp_path: Path) -> None:
    module = _load_module()
    report_index, structured, asset_coverage, ingestion_audit = _sample_inputs(tmp_path)
    structured.loc[0, "lookahead_violation"] = True

    try:
        module.generate_patched_reports(tmp_path / "out", report_index, structured, asset_coverage, ingestion_audit)
    except ValueError as exc:
        assert "lookahead" in str(exc)
    else:
        raise AssertionError("expected lookahead validation failure")
