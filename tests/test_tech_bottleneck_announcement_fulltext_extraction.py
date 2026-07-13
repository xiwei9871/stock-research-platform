from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_announcement_fulltext_extraction.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_announcement_fulltext_extraction", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_structured() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "announcement_id": "ann-1",
                "announcement_title": "样本A重大合同公告",
                "announcement_date": "2026-01-02",
                "as_of_date": "2026-01-02",
                "source_url": "https://example.com/ann-1.pdf",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "announcement_type": "order_contract",
                "order_contract": True,
                "customer_contract": False,
                "capacity_project": False,
                "fundraising_project": False,
                "equity_incentive": False,
                "risk_disclosure": False,
                "financial_guidance": False,
                "performance_forecast": False,
                "litigation_or_penalty": False,
                "major_customer_or_supplier": False,
                "announcement_validation_score": 0.45,
                "risk_event_score": 0.0,
                "extraction_confidence": 0.35,
                "extraction_method": "keyword_title_only",
                "matched_keywords": "重大合同",
                "missing_fields": "content",
                "data_quality_status": "title_only",
            },
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "announcement_id": "ann-2",
                "announcement_title": "样本B风险提示公告",
                "announcement_date": "2026-01-03",
                "as_of_date": "2026-01-03",
                "source_url": "",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "announcement_type": "risk_disclosure",
                "order_contract": False,
                "customer_contract": False,
                "capacity_project": False,
                "fundraising_project": False,
                "equity_incentive": False,
                "risk_disclosure": True,
                "financial_guidance": False,
                "performance_forecast": False,
                "litigation_or_penalty": False,
                "major_customer_or_supplier": False,
                "announcement_validation_score": 0.0,
                "risk_event_score": 0.7,
                "extraction_confidence": 0.35,
                "extraction_method": "keyword_title_only",
                "matched_keywords": "风险提示",
                "missing_fields": "content",
                "data_quality_status": "title_only",
            },
        ]
    )


def test_fetch_plan_covers_all_structured_rows(tmp_path: Path) -> None:
    module = _load_module()
    text_path = tmp_path / "ann-1.txt"
    text_path.write_text("公司签订重大合同，客户验证明确，合同金额较大。", encoding="utf-8")
    local_index = {"ann-1": text_path}

    plan = module.build_fulltext_fetch_plan(_sample_structured(), local_index, {})

    assert len(plan) == 2
    assert plan.loc[plan["announcement_id"].eq("ann-1"), "recommended_fetch_method"].iloc[0] == "use_local_text"
    assert plan.loc[plan["announcement_id"].eq("ann-2"), "recommended_fetch_method"].iloc[0] == "manual_download_required"


def test_fulltext_outputs_and_structured_evidence_preserve_pit_and_upgrade_confidence(tmp_path: Path) -> None:
    module = _load_module()
    structured = _sample_structured()
    text_path = tmp_path / "ann-1.txt"
    text_path.write_text("公司签订重大合同，客户验证明确。风险提示：履约存在不确定性。", encoding="utf-8")
    plan = module.build_fulltext_fetch_plan(structured, {"ann-1": text_path}, {})

    extracted = module.extract_fulltexts(plan)
    evidence = module.build_fulltext_structured_evidence(structured, extracted)

    assert {"announcement_id", "fulltext_status", "text_excerpt", "extraction_method"}.issubset(extracted.columns)
    assert not evidence["lookahead_violation"].astype(bool).any()
    assert pd.to_datetime(evidence["announcement_date"]).le(pd.to_datetime(evidence["trade_date"])).all()
    assert pd.to_datetime(evidence["as_of_date"]).le(pd.to_datetime(evidence["trade_date"])).all()
    fulltext_row = evidence[evidence["announcement_id"].eq("ann-1")].iloc[0]
    assert fulltext_row["fulltext_status"] == "fulltext_extracted"
    assert fulltext_row["extraction_confidence"] > 0.35
    assert str(fulltext_row["supporting_excerpt"])


def test_no_fulltext_does_not_fabricate_excerpt_and_stays_degraded() -> None:
    module = _load_module()
    structured = _sample_structured()
    plan = module.build_fulltext_fetch_plan(structured, {}, {})

    extracted = module.extract_fulltexts(plan)
    evidence = module.build_fulltext_structured_evidence(structured, extracted)
    missing_row = evidence[evidence["announcement_id"].eq("ann-2")].iloc[0]

    assert missing_row["fulltext_status"] != "fulltext_extracted"
    assert missing_row["supporting_excerpt"] == ""
    assert missing_row["risk_excerpt"] == ""
    assert "degraded" in missing_row["data_quality_status"]


def test_quality_audit_reports_zero_lookahead_and_patch_candidates_are_review_only(tmp_path: Path) -> None:
    module = _load_module()
    structured = _sample_structured()
    plan = module.build_fulltext_fetch_plan(structured, {}, {})
    extracted = module.extract_fulltexts(plan)
    evidence = module.build_fulltext_structured_evidence(structured, extracted)
    patch = module.build_watchlist_fulltext_patch_candidates(evidence)
    audit = module.build_quality_audit(structured, plan, extracted, evidence)

    lookup = dict(zip(audit["metric"], audit["value"]))
    assert int(float(lookup["lookahead_violation_rows"])) == 0
    assert set(patch["recommended_report_update"]).issubset(module.ALLOWED_REVIEW_ACTIONS)
    assert not module.contains_actionable_trading_language(" ".join(patch.astype(str).agg(" ".join, axis=1).tolist()))


def test_lookahead_rows_are_rejected(tmp_path: Path) -> None:
    module = _load_module()
    structured = _sample_structured()
    structured.loc[0, "announcement_date"] = "2027-01-01"

    try:
        module.build_fulltext_fetch_plan(structured, {}, {})
    except ValueError as exc:
        assert "lookahead" in str(exc)
    else:
        raise AssertionError("expected lookahead validation failure")
