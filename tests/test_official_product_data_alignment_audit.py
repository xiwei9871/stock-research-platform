import json
from pathlib import Path

import pandas as pd

from stock_research.official_product_data_alignment_audit import (
    ALIGNMENT_AUDIT_COLUMNS,
    ALIGNMENT_STATUS_SUMMARY_COLUMNS,
    OfficialProductDataAlignmentAuditResult,
    build_alignment_status_summary,
    normalize_alignment_candidates,
    build_alignment_audit,
    write_alignment_audit_artifacts,
)

DESIGN_ALIGNMENT_AUDIT_COLUMNS = [
    "run_id",
    "asset_id",
    "ts_code",
    "stock_name",
    "candidate_trade_date",
    "as_of_date",
    "alignment_status",
    "alignment_reason",
    "has_pit_safe_product_evidence",
    "safe_product_evidence_count",
    "unsafe_product_evidence_count",
    "best_report_period",
    "best_publish_date",
    "best_disclosure_type",
    "best_source_document_id",
    "best_source_document_url",
    "best_source_title",
    "best_product_main_business_rows",
    "best_manifest_rows",
    "manifest_rows_for_asset",
    "product_main_business_rows_for_asset",
    "joinable_report_periods_for_asset",
    "manifest_query_error_count_for_asset",
    "max_safe_report_period",
    "min_future_publish_date",
    "days_until_first_future_disclosure",
    "recommended_action",
]


def test_alignment_audit_columns_match_design_contract():
    assert ALIGNMENT_AUDIT_COLUMNS == DESIGN_ALIGNMENT_AUDIT_COLUMNS


def test_alignment_audit_result_fields_are_artifact_summary_only():
    assert list(OfficialProductDataAlignmentAuditResult.__dataclass_fields__) == [
        "output_dir",
        "candidate_rows",
        "candidate_assets",
        "pit_safe_rows",
        "future_disclosure_rows",
        "manifest_query_error_rows",
    ]


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


def test_safe_historical_joinable_diagnostic_is_not_readiness():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "trade_date": "2025-05-09",
            }
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "2025-04-25",
                "disclosure_type": "annual",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
                "announcement_title": "2024年年度报告",
                "product_main_business_rows": 4,
                "manifest_rows": 1,
                "join_status": "joinable",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] != "manifest_available_no_joinable_product_period"
    assert row["alignment_status"] != "pit_safe_product_evidence_available"
    assert row["alignment_status"] == "no_official_manifest_or_product_rows"
    assert row["has_pit_safe_product_evidence"] is False
    assert (
        row["alignment_reason"]
        == "join diagnostics contain a safe historical period but no candidate-scoped evidence row exists"
    )
    assert row["recommended_action"] != "use_for_readiness"
    assert row["recommended_action"] == "investigate_source_coverage"
    assert row["max_safe_report_period"] == pd.Timestamp("2024-12-31").date()
    assert row["joinable_report_periods_for_asset"] == 1
    assert row["best_source_title"] == "2024年年度报告"


def test_malformed_joinable_diagnostic_is_not_no_joinable_period():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "trade_date": "2025-05-09",
            }
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "",
                "publish_date": "",
                "disclosure_type": "annual",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
                "announcement_title": "2024年年度报告",
                "product_main_business_rows": 2,
                "manifest_rows": 1,
                "join_status": "joinable",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] != "manifest_available_no_joinable_product_period"
    assert row["alignment_status"] == "no_official_manifest_or_product_rows"
    assert row["alignment_reason"] == "joinable diagnostics exist but report_period or publish_date is unusable"
    assert row["recommended_action"] == "investigate_source_coverage"
    assert row["joinable_report_periods_for_asset"] == 0


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


def test_candidate_unsafe_evidence_with_future_report_period_ignores_future_period():
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
                "source_title": "2025年半年度报告",
                "source_id": "122500",
                "source_url": "http://example.com/2025h1.pdf",
                "as_of_safe": False,
                "metadata_json": json.dumps(
                    {
                        "report_period": "2025-06-30",
                        "publish_date": "2025-04-25",
                        "source_document_id": "122500",
                        "source_document_url": "http://example.com/2025h1.pdf",
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
    assert row["alignment_status"] == "joinable_but_report_period_future"
    assert row["alignment_reason"] == "joinable official product period is after candidate as_of_date"
    assert row["recommended_action"] == "ignore_future_period"
    assert row["best_report_period"] == pd.Timestamp("2025-06-30").date()


def test_real_shape_diagnostics_are_enriched_from_manifest_for_future_disclosure():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "trade_date": "2025-04-18",
            }
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "manifest_rows": 1,
                "product_main_business_rows": 3,
                "join_status": "joinable",
            }
        ]
    )
    manifest = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "2025-04-25",
                "disclosure_type": "annual",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
                "announcement_title": "2024年年度报告",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=manifest,
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "joinable_but_future_disclosure"
    assert row["alignment_reason"] == "official manifest and product rows join, but publish_date is after candidate as_of_date"
    assert row["recommended_action"] == "shift_test_window_later"
    assert row["best_publish_date"] == pd.Timestamp("2025-04-25").date()
    assert row["best_source_document_id"] == "121999"
    assert row["best_source_document_url"] == "http://example.com/report.pdf"
    assert row["best_source_title"] == "2024年年度报告"


def test_joinable_future_report_period_is_separated_from_future_disclosure():
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
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2025-06-30",
                "publish_date": "2025-08-28",
                "disclosure_type": "semiannual",
                "source_document_id": "122500",
                "source_document_url": "http://example.com/2025h1.pdf",
                "announcement_title": "2025年半年度报告",
                "product_main_business_rows": 5,
                "manifest_rows": 1,
                "join_status": "joinable",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "joinable_but_report_period_future"
    assert row["alignment_reason"] == "joinable official product period is after candidate as_of_date"
    assert row["best_report_period"] == pd.Timestamp("2025-06-30").date()
    assert row["best_publish_date"] == pd.Timestamp("2025-08-28").date()
    assert row["best_product_main_business_rows"] == 5
    assert row["best_manifest_rows"] == 1
    assert row["joinable_report_periods_for_asset"] == 1
    assert row["recommended_action"] == "ignore_future_period"


def test_manifest_and_product_rows_without_matching_period_recommends_historical_backfill():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "trade_date": "2025-05-09",
            }
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "2025-04-25",
                "disclosure_type": "annual",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
                "announcement_title": "2024年年度报告",
                "product_main_business_rows": 0,
                "manifest_rows": 1,
                "join_status": "missing_product_rows",
            },
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "",
                "publish_date": "",
                "disclosure_type": "",
                "source_document_id": "",
                "source_document_url": "",
                "announcement_title": "",
                "product_main_business_rows": 4,
                "manifest_rows": 0,
                "join_status": "product_rows_without_manifest",
            },
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "manifest_available_no_joinable_product_period"
    assert row["manifest_rows_for_asset"] == 1
    assert row["product_main_business_rows_for_asset"] == 4
    assert row["recommended_action"] == "backfill_historical_product_rows"


def test_manifest_without_product_rows_recommends_product_table_backfill():
    candidates = pd.DataFrame([{"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "trade_date": "2025-05-09"}])
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "2025-04-25",
                "disclosure_type": "annual",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
                "announcement_title": "2024年年度报告",
                "product_main_business_rows": 0,
                "manifest_rows": 1,
                "join_status": "missing_product_rows",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "manifest_available_no_product_rows"
    assert row["recommended_action"] == "backfill_product_table_source"


def test_product_rows_without_manifest_recommends_manifest_source_fix():
    candidates = pd.DataFrame([{"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "trade_date": "2025-05-09"}])
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "",
                "disclosure_type": "",
                "source_document_id": "",
                "source_document_url": "",
                "announcement_title": "",
                "product_main_business_rows": 3,
                "manifest_rows": 0,
                "join_status": "product_rows_without_manifest",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "product_rows_available_no_official_manifest"
    assert row["recommended_action"] == "extend_or_fix_manifest_source"


def test_manifest_query_error_is_not_treated_as_genuine_no_data():
    candidates = pd.DataFrame([{"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "trade_date": "2025-05-09"}])
    errors = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "error_type": "TimeoutError",
                "error_message": "timed out",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=pd.DataFrame(),
        manifest_query_errors=errors,
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "manifest_query_error"
    assert row["manifest_query_error_count_for_asset"] == 1
    assert row["recommended_action"] == "rerun_manifest_source"


def test_status_summary_groups_overall_month_status_and_action():
    audit = pd.DataFrame(
        [
            {
                "run_id": "unit",
                "asset_id": "CN:SZ:000001",
                "candidate_trade_date": pd.Timestamp("2025-05-09").date(),
                "alignment_status": "pit_safe_product_evidence_available",
                "recommended_action": "use_for_readiness",
            },
            {
                "run_id": "unit",
                "asset_id": "CN:SZ:000002",
                "candidate_trade_date": pd.Timestamp("2025-04-18").date(),
                "alignment_status": "joinable_but_future_disclosure",
                "recommended_action": "shift_test_window_later",
            },
        ]
    )

    summary = build_alignment_status_summary(audit, run_id="unit")

    assert summary.columns.tolist() == ALIGNMENT_STATUS_SUMMARY_COLUMNS
    overall = summary[(summary["group"] == "overall") & (summary["group_value"] == "all")].iloc[0].to_dict()
    assert overall["candidate_rows"] == 2
    assert overall["candidate_assets"] == 2
    assert overall["pit_safe_rows"] == 1
    assert overall["future_disclosure_rows"] == 1
    assert overall["missing_product_period_rows"] == 0
    assert overall["manifest_query_error_rows"] == 0
    assert set(summary["group"]) == {"overall", "candidate_month", "alignment_status", "recommended_action"}


def test_write_alignment_audit_artifacts_creates_csv_json_and_markdown(tmp_path):
    audit = pd.DataFrame(
        [
            {
                "run_id": "unit",
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "candidate_trade_date": pd.Timestamp("2025-04-18").date(),
                "as_of_date": pd.Timestamp("2025-04-18").date(),
                "alignment_status": "joinable_but_future_disclosure",
                "alignment_reason": "official product evidence exists but publish_date is after candidate as_of_date",
                "has_pit_safe_product_evidence": False,
                "safe_product_evidence_count": 0,
                "unsafe_product_evidence_count": 1,
                "best_report_period": pd.Timestamp("2024-12-31").date(),
                "best_publish_date": pd.Timestamp("2025-04-25").date(),
                "best_disclosure_type": "annual",
                "best_source_document_id": "121999",
                "best_source_document_url": "http://example.com/report.pdf",
                "best_source_title": "2024年年度报告",
                "best_product_main_business_rows": 3,
                "best_manifest_rows": 1,
                "manifest_rows_for_asset": 1,
                "product_main_business_rows_for_asset": 3,
                "joinable_report_periods_for_asset": 1,
                "manifest_query_error_count_for_asset": 0,
                "max_safe_report_period": None,
                "min_future_publish_date": pd.Timestamp("2025-04-25").date(),
                "days_until_first_future_disclosure": 7,
                "recommended_action": "shift_test_window_later",
            }
        ],
        columns=ALIGNMENT_AUDIT_COLUMNS,
    )

    result = write_alignment_audit_artifacts(audit=audit, output_dir=tmp_path, run_id="unit")

    assert result.output_dir == tmp_path
    assert result.candidate_rows == 1
    assert result.candidate_assets == 1
    assert result.pit_safe_rows == 0
    assert result.future_disclosure_rows == 1
    assert result.manifest_query_error_rows == 0
    assert (tmp_path / "alignment_audit.csv").exists()
    assert (tmp_path / "alignment_audit.json").exists()
    assert (tmp_path / "alignment_status_summary.csv").exists()
    assert (tmp_path / "alignment_summary.md").exists()
    assert pd.read_csv(tmp_path / "alignment_audit.csv").columns.tolist() == ALIGNMENT_AUDIT_COLUMNS
    assert pd.read_csv(tmp_path / "alignment_status_summary.csv").columns.tolist() == ALIGNMENT_STATUS_SUMMARY_COLUMNS
    records = json.loads((tmp_path / "alignment_audit.json").read_text(encoding="utf-8"))
    assert records[0]["stock_name"] == "平安银行"
    markdown = (tmp_path / "alignment_summary.md").read_text(encoding="utf-8")
    assert "shift_test_window_later" in markdown
    assert "joinable_but_future_disclosure" in markdown
    assert "official product evidence exists but publish_date is after candidate as_of_date" in markdown
    assert "2025-04" in markdown


def test_write_alignment_audit_artifacts_handles_empty_audit(tmp_path):
    audit = pd.DataFrame(columns=ALIGNMENT_AUDIT_COLUMNS)

    result = write_alignment_audit_artifacts(audit=audit, output_dir=tmp_path, run_id="unit")

    assert result.candidate_rows == 0
    assert result.candidate_assets == 0
    assert result.pit_safe_rows == 0
    assert result.future_disclosure_rows == 0
    assert result.manifest_query_error_rows == 0
    assert json.loads((tmp_path / "alignment_audit.json").read_text(encoding="utf-8")) == []
