from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_watchlist_report_fulltext_announcement_patch.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_report_fulltext_announcement_patch", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_inputs(tmp_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    old_a = tmp_path / "title_a.md"
    old_b = tmp_path / "title_b.md"
    old_a.write_text("# 样本A\n\n已打 title-only 公告补丁。\n", encoding="utf-8")
    old_b.write_text("# 样本B\n\n已打 title-only 公告补丁。\n", encoding="utf-8")
    title_index = pd.DataFrame(
        [
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "old_report_path": str(old_a),
                "patched_report_path": str(old_a),
                "patch_status": "patched_with_announcement",
            },
            {
                "report_date": "2026-06-29",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "old_report_path": str(old_b),
                "patched_report_path": str(old_b),
                "patch_status": "no_announcement_support",
            },
        ]
    )
    original_index = pd.DataFrame(
        [
            {"report_date": "2026-06-29", "asset_id": "CN:SZ:000001", "symbol": "000001", "name": "样本A", "report_path": str(old_a)},
            {"report_date": "2026-06-29", "asset_id": "CN:SZ:000002", "symbol": "000002", "name": "样本B", "report_path": str(old_b)},
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "announcement_id": "ann-strong",
                "announcement_title": "样本A重大合同公告",
                "announcement_date": "2026-01-01",
                "as_of_date": "2026-01-01",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "fulltext_status": "fulltext_extracted",
                "extraction_method": "eastmoney_text_cache_fulltext",
                "announcement_type": "order_contract",
                "order_contract": True,
                "customer_contract": True,
                "capacity_project": False,
                "fundraising_project": False,
                "equity_incentive": False,
                "financial_guidance": False,
                "performance_forecast": False,
                "risk_disclosure": False,
                "litigation_or_penalty": False,
                "announcement_validation_score": 0.8,
                "risk_event_score": 0.0,
                "extraction_confidence": 0.82,
                "evidence_strength": "fulltext_evidence",
                "supporting_excerpt": "公司与主要客户签订重大合同，合同金额为一亿元，供货安排明确。",
                "risk_excerpt": "",
                "data_quality_status": "fulltext_available",
            },
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "announcement_id": "ann-generic-risk",
                "announcement_title": "样本A年度报告",
                "announcement_date": "2026-02-01",
                "as_of_date": "2026-02-01",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "fulltext_status": "fulltext_extracted",
                "extraction_method": "eastmoney_text_cache_fulltext",
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
                "risk_event_score": 0.8,
                "extraction_confidence": 0.82,
                "evidence_strength": "fulltext_evidence",
                "supporting_excerpt": "",
                "risk_excerpt": "本报告涉及的未来计划存在不确定性，请投资者注意风险。",
                "data_quality_status": "fulltext_available",
            },
        ]
    )
    quality = pd.DataFrame(
        [
            {"metric": "lookahead_violation_rows", "value": 0, "note": "must be zero"},
            {"metric": "PIT_valid_ratio", "value": 1.0, "note": "pit"},
        ]
    )
    return original_index, title_index, evidence, quality


def test_generates_fulltext_patched_reports_for_all_assets(tmp_path: Path) -> None:
    module = _load_module()
    original_index, title_index, evidence, quality = _sample_inputs(tmp_path)

    result = module.generate_fulltext_patched_reports(tmp_path / "out", original_index, title_index, evidence, quality)
    index = result["index"]

    assert len(index) == 2
    assert index["fulltext_patched_report_path"].map(lambda p: Path(p).exists()).all()


def test_patch_status_tracks_fulltext_and_missing_support(tmp_path: Path) -> None:
    module = _load_module()
    original_index, title_index, evidence, quality = _sample_inputs(tmp_path)

    index = module.generate_fulltext_patched_reports(tmp_path / "out", original_index, title_index, evidence, quality)["index"]
    by_asset = dict(zip(index["asset_id"], index["patch_status"]))

    assert by_asset["CN:SZ:000001"] == "patched_with_fulltext_announcement"
    assert by_asset["CN:SZ:000002"] == "no_announcement_support"


def test_generic_disclosure_is_not_strong_risk_evidence(tmp_path: Path) -> None:
    module = _load_module()
    _, _, evidence, _ = _sample_inputs(tmp_path)

    classified = evidence.apply(module.classify_evidence_strength, axis=1, result_type="expand")
    generic_row = classified.loc[evidence["announcement_id"].eq("ann-generic-risk")].iloc[0]

    assert generic_row["risk_specificity"] == "generic_disclosure_text"
    assert generic_row["evidence_strength_layer"] != "strong_fulltext_evidence"


def test_fulltext_report_contains_excerpts_and_no_actionable_language(tmp_path: Path) -> None:
    module = _load_module()
    original_index, title_index, evidence, quality = _sample_inputs(tmp_path)

    index = module.generate_fulltext_patched_reports(tmp_path / "out", original_index, title_index, evidence, quality)["index"]
    content = Path(index.loc[index["asset_id"].eq("CN:SZ:000001"), "fulltext_patched_report_path"].iloc[0]).read_text(encoding="utf-8")

    assert "Fulltext Announcement Evidence Patch" in content
    assert "supporting excerpts" in content
    assert "risk excerpts" in content
    assert "generic_disclosure_text" in content
    assert "title-only remaining count" in content
    assert not module.contains_actionable_trading_language(content)


def test_audit_reports_zero_language_and_zero_lookahead(tmp_path: Path) -> None:
    module = _load_module()
    original_index, title_index, evidence, quality = _sample_inputs(tmp_path)

    audit = module.generate_fulltext_patched_reports(tmp_path / "out", original_index, title_index, evidence, quality)["audit"]
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["reports_with_trading_language"])) == 0
    assert int(float(lookup["lookahead_violation_rows"])) == 0
    assert int(float(lookup["patch_failures"])) == 0


def test_lookahead_rows_are_rejected(tmp_path: Path) -> None:
    module = _load_module()
    original_index, title_index, evidence, quality = _sample_inputs(tmp_path)
    evidence.loc[0, "lookahead_violation"] = True

    try:
        module.generate_fulltext_patched_reports(tmp_path / "out", original_index, title_index, evidence, quality)
    except ValueError as exc:
        assert "lookahead" in str(exc)
    else:
        raise AssertionError("expected lookahead validation failure")
