from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_targeted_source_backfill_collects_sources_parses_evidence_and_rescores(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_omission_rescue_targeted_source_backfill import run

    queue_path = tmp_path / "remaining_gap.csv"
    output_dir = tmp_path / "out"
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    primary_pdf = pdf_dir / "primary.pdf"
    broker_pdf = pdf_dir / "broker.pdf"
    primary_pdf.write_bytes(b"%PDF-1.7\nfake")
    broker_pdf.write_bytes(b"%PDF-1.7\nfake")

    pd.DataFrame(
        [
            {
                "stock_code": "002384",
                "stock_name": "东山精密",
                "recall_decision": "add_to_review_universe_separate_review",
                "tech_bottleneck_domain": "光电与通信",
                "supply_chain_role": "bottleneck",
                "primary_source_supported": False,
                "page_level_citation_count": "",
                "evidence_count": 0,
                "page_citation_count": 0,
                "source_pdf_count": 0,
                "db_concept_tags_concepts": "AI服务器/高速PCB",
                "remaining_evidence_gap_flags": "missing_official_product_source",
                "downgrade_risk_flags": "",
            },
            {
                "stock_code": "000333",
                "stock_name": "美的集团",
                "recall_decision": "human_confirm_before_review",
                "tech_bottleneck_domain": "其他战略性关键环节",
                "supply_chain_role": "concept_only",
                "primary_source_supported": False,
                "page_level_citation_count": "",
                "evidence_count": 0,
                "page_citation_count": 0,
                "source_pdf_count": 0,
                "db_concept_tags_concepts": "机器人/家电",
                "remaining_evidence_gap_flags": "",
                "downgrade_risk_flags": "",
            },
        ]
    ).to_csv(queue_path, index=False)

    def fake_primary_collector(queue: pd.DataFrame, output: Path, **_: object) -> dict[str, pd.DataFrame]:
        manifest = pd.DataFrame(
            [
                {
                    "stock_code": "002384",
                    "stock_name": "东山精密",
                    "source_type": "annual_report",
                    "source_title": "东山精密2025年年度报告",
                    "source_url": "https://example.test/primary.pdf",
                    "local_pdf_path": str(primary_pdf),
                    "provider": "cninfo",
                    "download_status": "downloaded",
                    "source_id": "cninfo-002384-a",
                }
            ]
        )
        search = pd.DataFrame([{"stock_code": "002384", "stock_name": "东山精密", "status": "ok", "candidate_count": 1}])
        downloads = manifest.rename(columns={"local_pdf_path": "local_pdf_path"}).copy()
        return {"manifest": manifest, "search": search, "downloads": downloads}

    def fake_report_collector(universe_path: Path, output: Path, **_: object) -> dict[str, pd.DataFrame]:
        downloads = pd.DataFrame(
            [
                {
                    "stock_code": "002384",
                    "stock_name": "东山精密",
                    "report_title": "东山精密AI服务器高速PCB深度报告",
                    "status": "downloaded",
                    "pdf_path": str(broker_pdf),
                    "filename": broker_pdf.name,
                    "org_name": "中信证券",
                }
            ]
        )
        return {"downloads": downloads, "search": pd.DataFrame(), "coverage": pd.DataFrame()}

    def fake_pdf_parser(sources: pd.DataFrame, **_: object) -> dict[str, pd.DataFrame]:
        rows = []
        for source in sources.to_dict("records"):
            rows.append(
                {
                    "stock_code": source["stock_code"],
                    "stock_name": source["stock_name"],
                    "source_title": source["source_title"],
                    "source_type": source["source_type"],
                    "source_path": source["source_path"],
                    "page": 12,
                    "evidence_text": "公司电子电路产品用于AI服务器高速PCB、高速互连和高速信号完整性关键环节。",
                    "evidence_claim_type": "hard_tech_exposure",
                    "citation_quality": "page_level",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
        return {
            "evidence": pd.DataFrame(rows),
            "parse_manifest": sources.assign(parse_status="parsed", page_count=20),
            "parse_failures": pd.DataFrame(),
        }

    summary = run(
        remaining_gap_queue_path=queue_path,
        output_dir=output_dir,
        primary_collector=fake_primary_collector,
        broker_report_collector=fake_report_collector,
        pdf_parser=fake_pdf_parser,
        market_profile={
            "company": pd.DataFrame(),
            "concepts": pd.DataFrame(),
            "financial": pd.DataFrame(),
            "business": pd.DataFrame(),
        },
    )

    assert summary["source_remaining_gap_count"] == 2
    assert summary["processed_count"] == 2
    assert summary["cninfo_downloaded_pdf_count"] == 1
    assert summary["yanbaoke_downloaded_pdf_count"] == 1
    assert summary["page_level_evidence_stock_count_after"] == 1
    assert summary["remaining_evidence_gap_count_after"] == 1
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["frozen_quality_pool_generated"] is False
    assert (output_dir / "omission_rescue_targeted_evidence_index.csv").exists()
    assert (output_dir / "omission_rescue_targeted_quality_reassessment.csv").exists()


def test_targeted_source_backfill_real_outputs_guardrails() -> None:
    output_dir = Path(
        "/Users/xiwei/stock_research/outputs/research/"
        "tech_bottleneck_omission_rescue_targeted_source_backfill_v1"
    )
    summary_path = output_dir / "omission_rescue_targeted_source_backfill_summary.json"
    guardrails_path = output_dir / "omission_rescue_targeted_source_backfill_guardrails.json"
    if not summary_path.exists() or not guardrails_path.exists():
        return

    import json

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    guardrails = json.loads(guardrails_path.read_text(encoding="utf-8"))
    assert summary["source_remaining_gap_count"] == 74
    assert summary["processed_count"] == 74
    assert guardrails["research_only"] is True
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["frozen_quality_pool_generated"] is False
    assert guardrails["strategy_file_diff_clean"] is True
