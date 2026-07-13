from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_announcement_fulltext_extraction_v2.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_announcement_fulltext_extraction_v2", path)
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
                "source_type": "announcement",
                "announcement_title": "样本A重大合同公告",
                "announcement_date": "2026-01-02",
                "as_of_date": "2026-01-02",
                "source_url": "https://data.eastmoney.com/notices/detail/000001/AN1.html",
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
                "evidence_direction": "positive_or_validation",
                "announcement_validation_score": 0.45,
                "risk_event_score": 0.0,
                "source_confidence": 0.8,
                "extraction_confidence": 0.35,
                "extraction_method": "keyword_title_only",
                "matched_keywords": "重大合同",
                "missing_fields": "content",
                "conflict_flags": "",
                "data_quality_status": "title_only",
            },
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "announcement_id": "ann-2",
                "source_type": "announcement",
                "announcement_title": "样本B法律意见书",
                "announcement_date": "2026-01-03",
                "as_of_date": "2026-01-03",
                "source_url": "https://data.eastmoney.com/notices/detail/000002/AN2.html",
                "is_pit_valid": True,
                "lookahead_violation": False,
                "announcement_type": "unclassified",
                "order_contract": False,
                "customer_contract": False,
                "capacity_project": False,
                "fundraising_project": False,
                "equity_incentive": False,
                "risk_disclosure": False,
                "financial_guidance": False,
                "performance_forecast": False,
                "litigation_or_penalty": False,
                "major_customer_or_supplier": False,
                "evidence_direction": "neutral_or_unclassified",
                "announcement_validation_score": 0.0,
                "risk_event_score": 0.0,
                "source_confidence": 0.8,
                "extraction_confidence": 0.35,
                "extraction_method": "keyword_title_only",
                "matched_keywords": "",
                "missing_fields": "content",
                "conflict_flags": "",
                "data_quality_status": "title_only",
            },
        ]
    )


def _sample_manifest(tmp_path: Path) -> pd.DataFrame:
    text_path = tmp_path / "ann-1.txt"
    text_path.write_text(
        "公司公告：公司签订重大合同，合同金额较大，客户验证明确。风险提示：合同履约存在不确定性。",
        encoding="utf-8",
    )
    return pd.DataFrame(
        [
            {
                "announcement_id": "ann-1",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "announcement_title": "样本A重大合同公告",
                "announcement_date": "2026-01-02",
                "source_url": "https://data.eastmoney.com/notices/detail/000001/AN1.html",
                "resolved_pdf_url": "https://pdf.dfcfw.com/pdf/H2_AN1.pdf",
                "pdf_available": False,
                "text_available": True,
                "pdf_cache_path": "",
                "text_cache_path": str(text_path),
                "text_source": "resolved_text",
                "raw_text_length": 47,
                "clean_text_length": 47,
                "data_quality_status": "text_cache_available",
            },
            {
                "announcement_id": "ann-2",
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "announcement_title": "样本B法律意见书",
                "announcement_date": "2026-01-03",
                "source_url": "https://data.eastmoney.com/notices/detail/000002/AN2.html",
                "resolved_pdf_url": "https://pdf.dfcfw.com/pdf/H2_AN2.pdf",
                "pdf_available": False,
                "text_available": False,
                "pdf_cache_path": "",
                "text_cache_path": "",
                "text_source": "",
                "raw_text_length": 0,
                "clean_text_length": 0,
                "data_quality_status": "degraded_metadata_only",
            },
        ]
    )


def test_v2_extracted_outputs_cover_manifest_rows_and_preserve_text_available(tmp_path: Path) -> None:
    module = _load_module()
    manifest = _sample_manifest(tmp_path)

    extracted = module.build_v2_extracted_outputs(manifest)

    assert len(extracted) == 2
    assert int(extracted["text_available"].astype(bool).sum()) == int(manifest["text_available"].astype(bool).sum())
    assert extracted.loc[extracted["announcement_id"].eq("ann-1"), "fulltext_status"].iloc[0] == "fulltext_extracted"
    assert extracted.loc[extracted["announcement_id"].eq("ann-2"), "data_quality_status"].iloc[0].startswith("degraded")


def test_structured_evidence_preserves_pit_and_uses_fulltext_excerpts(tmp_path: Path) -> None:
    module = _load_module()
    structured = _sample_structured()
    extracted = module.build_v2_extracted_outputs(_sample_manifest(tmp_path))

    evidence = module.build_v2_structured_evidence(structured, extracted)

    assert {"announcement_date", "as_of_date", "lookahead_violation", "resolved_pdf_url"}.issubset(evidence.columns)
    assert not evidence["lookahead_violation"].astype(bool).any()
    assert pd.to_datetime(evidence["announcement_date"]).le(pd.to_datetime(evidence["trade_date"])).all()
    assert pd.to_datetime(evidence["as_of_date"]).le(pd.to_datetime(evidence["trade_date"])).all()
    fulltext_row = evidence.loc[evidence["announcement_id"].eq("ann-1")].iloc[0]
    assert fulltext_row["extraction_method"] == "eastmoney_text_cache_fulltext"
    assert fulltext_row["extraction_confidence"] > 0.35
    assert "合同" in str(fulltext_row["supporting_excerpt"])
    assert "风险" in str(fulltext_row["risk_excerpt"])
    metadata_row = evidence.loc[evidence["announcement_id"].eq("ann-2")].iloc[0]
    assert metadata_row["supporting_excerpt"] == ""
    assert metadata_row["risk_excerpt"] == ""
    assert "degraded" in metadata_row["data_quality_status"]


def test_quality_audit_reports_before_after_and_zero_lookahead(tmp_path: Path) -> None:
    module = _load_module()
    structured = _sample_structured()
    extracted = module.build_v2_extracted_outputs(_sample_manifest(tmp_path))
    evidence = module.build_v2_structured_evidence(structured, extracted)

    audit = module.build_v2_quality_audit(structured, extracted, evidence)
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["candidate_announcement_rows"])) == 2
    assert int(float(lookup["text_available_rows"])) == 1
    assert int(float(lookup["lookahead_violation_rows"])) == 0
    assert float(lookup["average_extraction_confidence_after"]) > float(lookup["average_extraction_confidence_before"])


def test_patch_candidates_are_review_only(tmp_path: Path) -> None:
    module = _load_module()
    extracted = module.build_v2_extracted_outputs(_sample_manifest(tmp_path))
    evidence = module.build_v2_structured_evidence(_sample_structured(), extracted)

    patch = module.build_watchlist_fulltext_v2_patch_candidates(evidence)

    assert set(patch["recommended_report_update"]).issubset(module.ALLOWED_REVIEW_ACTIONS)
    assert not module.contains_actionable_trading_language(" ".join(patch.astype(str).agg(" ".join, axis=1).tolist()))


def test_lookahead_rows_are_rejected(tmp_path: Path) -> None:
    module = _load_module()
    structured = _sample_structured()
    structured.loc[0, "as_of_date"] = "2027-01-01"
    extracted = module.build_v2_extracted_outputs(_sample_manifest(tmp_path))

    try:
        module.build_v2_structured_evidence(structured, extracted)
    except ValueError as exc:
        assert "lookahead" in str(exc)
    else:
        raise AssertionError("expected lookahead validation failure")
