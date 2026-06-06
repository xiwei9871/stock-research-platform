import json
from pathlib import Path

import pandas as pd

from stock_research.official_product_data_alignment_audit import (
    ALIGNMENT_AUDIT_COLUMNS,
    normalize_alignment_candidates,
    build_alignment_audit,
)


def test_normalize_alignment_candidates_accepts_real_pilot_shape():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "stock_name": "平安银行",
                "trade_date": "2025-01-03",
                "candidate_source": "pilot_top50",
                "rank": "1",
            }
        ]
    )

    normalized = normalize_alignment_candidates(candidates)

    assert normalized.to_dict("records") == [
        {
            "asset_id": "CN:SZ:000001",
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "candidate_trade_date": pd.Timestamp("2025-01-03").date(),
            "as_of_date": pd.Timestamp("2025-01-03").date(),
        }
    ]


def test_safe_product_evidence_produces_pit_safe_status():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            }
        ]
    )
    product_evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
                "evidence_date": "2025-04-25",
                "source_title": "2024年年度报告",
                "source_id": "121999",
                "source_url": "http://example.com/report.pdf",
                "as_of_safe": True,
                "metadata_json": json.dumps(
                    {
                        "report_period": "2024-12-31",
                        "publish_date": "2025-04-25",
                        "source_document_id": "121999",
                        "source_document_url": "http://example.com/report.pdf",
                        "item_name": "先进封装设备",
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=product_evidence,
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=pd.DataFrame(),
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert audit.columns.tolist() == ALIGNMENT_AUDIT_COLUMNS
    assert row["alignment_status"] == "pit_safe_product_evidence_available"
    assert row["alignment_reason"] == "candidate row has strict PIT-safe official product evidence"
    assert row["has_pit_safe_product_evidence"] is True
    assert row["safe_product_evidence_count"] == 1
    assert row["unsafe_product_evidence_count"] == 0
    assert row["best_report_period"] == pd.Timestamp("2024-12-31").date()
    assert row["best_publish_date"] == pd.Timestamp("2025-04-25").date()
    assert row["best_source_document_id"] == "121999"
    assert row["best_source_document_url"] == "http://example.com/report.pdf"
    assert row["recommended_action"] == "use_for_readiness"


def test_future_disclosure_evidence_remains_blocked():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
            }
        ]
    )
    product_evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
                "evidence_date": "2025-04-25",
                "source_title": "2024年年度报告",
                "source_id": "121999",
                "source_url": "http://example.com/report.pdf",
                "as_of_safe": False,
                "metadata_json": json.dumps(
                    {
                        "report_period": "2024-12-31",
                        "publish_date": "2025-04-25",
                        "source_document_id": "121999",
                        "source_document_url": "http://example.com/report.pdf",
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=product_evidence,
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=pd.DataFrame(),
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "joinable_but_future_disclosure"
    assert row["alignment_reason"] == "official product evidence exists but publish_date is after candidate as_of_date"
    assert row["has_pit_safe_product_evidence"] is False
    assert row["safe_product_evidence_count"] == 0
    assert row["unsafe_product_evidence_count"] == 1
    assert row["best_report_period"] == pd.Timestamp("2024-12-31").date()
    assert row["best_publish_date"] == pd.Timestamp("2025-04-25").date()
    assert row["min_future_publish_date"] == pd.Timestamp("2025-04-25").date()
    assert row["days_until_first_future_disclosure"] == 7
    assert row["recommended_action"] == "shift_test_window_later"
