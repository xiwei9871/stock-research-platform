from __future__ import annotations

import datetime as dt
from decimal import Decimal
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.tech_bottleneck_evidence_backfill import (
    EVIDENCE_COLUMNS,
    build_evidence_backfill,
    classify_text_evidence,
    normalize_evidence_rows,
    normalize_evidence_candidates,
    write_evidence_artifacts,
)


def test_normalize_evidence_candidates_requires_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        normalize_evidence_candidates(
            pd.DataFrame([{"stock_name": "缺代码"}]),
            run_date="2026-06-06",
            start_date=None,
            end_date=None,
            lookback_days=365,
        )


def test_normalize_evidence_candidates_preserves_trade_date_as_as_of_date() -> None:
    rows = normalize_evidence_candidates(
        pd.DataFrame(
            [
                {"asset_id": "CN:SH:688001", "stock_name": "示例科技", "trade_date": "2025-01-10", "rank": 1},
                {"asset_id": "CN:SZ:300001", "trade_date": "2025-02-10", "rank": 2},
            ]
        ),
        run_date="2026-06-06",
        start_date="2025-01-01",
        end_date="2025-01-31",
        lookback_days=365,
    )

    assert rows["asset_id"].tolist() == ["CN:SH:688001"]
    assert rows.iloc[0]["as_of_date"] == "2025-01-10"
    assert rows.iloc[0]["lookback_days"] == 365
    assert rows.iloc[0]["rank"] == "1"


def test_normalize_evidence_candidates_preserves_timezone_bound_calendar_date() -> None:
    rows = normalize_evidence_candidates(
        pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688000",
                    "trade_date": "2024-12-31",
                },
                {
                    "asset_id": "CN:SH:688001",
                    "trade_date": "2025-01-01",
                },
            ]
        ),
        run_date="2026-06-06",
        start_date="2025-01-01T00:00:00+08:00",
        end_date=None,
        lookback_days=365,
    )

    assert rows["asset_id"].tolist() == ["CN:SH:688001"]
    assert rows.iloc[0]["as_of_date"] == "2025-01-01"


def test_normalize_evidence_rows_outputs_contract_and_json_metadata() -> None:
    evidence = normalize_evidence_rows(
        pd.DataFrame(
            [
                {
                    "run_id": "unit",
                    "asset_id": "CN:SH:688001",
                    "stock_name": "示例科技",
                    "candidate_trade_date": "2025-01-10",
                    "as_of_date": "2025-01-10",
                    "evidence_date": "2024-12-31",
                    "source_type": "finance.main_business_composition",
                    "source_id": "CN:SH:688001:2024-12-31:AI材料",
                    "source_title": "主营构成",
                    "evidence_type": "product_revenue_exposure",
                    "matched_keyword": "",
                    "evidence_snippet": "AI材料收入占比45%",
                    "source_confidence": "strong",
                    "is_proxy": False,
                    "as_of_safe": True,
                    "metadata_json": {"revenue_ratio": 45},
                }
            ]
        )
    )

    assert list(evidence.columns) == EVIDENCE_COLUMNS
    assert json.loads(evidence.iloc[0]["metadata_json"]) == {"revenue_ratio": 45}
    assert evidence.iloc[0]["is_proxy"] is False
    assert evidence.iloc[0]["as_of_safe"] is True


def test_normalize_evidence_rows_treats_unknown_bool_strings_as_false() -> None:
    evidence = normalize_evidence_rows(
        pd.DataFrame(
            [
                {
                    "is_proxy": "unknown",
                    "as_of_safe": "unknown",
                }
            ]
        )
    )

    assert evidence.iloc[0]["is_proxy"] is False
    assert evidence.iloc[0]["as_of_safe"] is False


def test_normalize_evidence_rows_serializes_pandas_and_numpy_metadata_values() -> None:
    np = pytest.importorskip("numpy")

    evidence = normalize_evidence_rows(
        pd.DataFrame(
            [
                {
                    "metadata_json": {
                        "date": pd.Timestamp("2025-01-01"),
                        "count": np.int64(45),
                        "ratio": np.float64(12.5),
                    }
                }
            ]
        )
    )

    assert json.loads(evidence.iloc[0]["metadata_json"]) == {
        "date": "2025-01-01",
        "count": 45,
        "ratio": 12.5,
    }


def test_normalize_evidence_rows_serializes_common_db_metadata_scalars() -> None:
    evidence = normalize_evidence_rows(
        pd.DataFrame(
            [
                {
                    "metadata_json": {
                        "date": dt.date(2025, 1, 1),
                        "datetime": dt.datetime(2025, 1, 1, 9, 30, 15),
                        "decimal": Decimal("45.5"),
                    }
                }
            ]
        )
    )

    assert json.loads(evidence.iloc[0]["metadata_json"]) == {
        "date": "2025-01-01",
        "datetime": "2025-01-01T09:30:15",
        "decimal": 45.5,
    }


def test_classify_text_evidence_emits_expected_evidence_types() -> None:
    matches = classify_text_evidence(
        text="关键材料国产替代加速，扩产爬坡，客户认证推进，技术壁垒高，风险是需求不及预期。",
        source_type="research.stock_report_event",
        source_id="r1",
        source_title="关键材料跟踪",
        source_date="2025-01-05",
    )

    evidence_types = {row["evidence_type"] for row in matches}
    assert {
        "bottleneck_keyword",
        "capacity",
        "customer_certification",
        "technical_barrier",
        "invalidation",
    }.issubset(evidence_types)


def test_build_evidence_backfill_extracts_product_and_text_evidence() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例科技",
                "trade_date": "2025-01-10",
                "candidate_source": "top50",
                "rank": 1,
            }
        ]
    )
    result = build_evidence_backfill(
        candidates=candidates,
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2024-12-31",
                    "classify_type": "按产品分类",
                    "item_name": "AI关键材料",
                    "revenue": 100,
                    "revenue_ratio": 45,
                    "gross_margin": 35,
                }
            ]
        ),
        reports=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_id": "r1",
                    "report_date": "2025-01-05",
                    "report_title": "国产替代加速",
                    "raw_summary": "扩产爬坡，客户认证推进，技术壁垒高。",
                }
            ]
        ),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    evidence_types = set(result.evidence["evidence_type"])
    assert "product_revenue_exposure" in evidence_types
    assert "bottleneck_keyword" in evidence_types
    assert "capacity" in evidence_types
    assert "customer_certification" in evidence_types
    assert "technical_barrier" in evidence_types
    assert bool(result.evidence[result.evidence["evidence_type"].eq("product_revenue_exposure")].iloc[0]["as_of_safe"])


def test_build_evidence_backfill_sorts_evidence_stably_from_shuffled_frames() -> None:
    result = build_evidence_backfill(
        candidates=pd.DataFrame(
            [
                {"asset_id": "CN:SH:688002", "trade_date": "2025-01-11"},
                {"asset_id": "CN:SH:688001", "trade_date": "2025-01-10"},
            ]
        ),
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688002",
                    "report_period": "2024-12-30",
                    "classify_type": "按产品分类",
                    "item_name": "Z材料",
                },
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2024-12-31",
                    "classify_type": "按产品分类",
                    "item_name": "A材料",
                },
            ]
        ),
        reports=pd.DataFrame(),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    sort_columns = [
        "candidate_trade_date",
        "asset_id",
        "evidence_date",
        "evidence_type",
        "source_type",
        "source_id",
        "matched_keyword",
        "evidence_snippet",
    ]
    expected = result.evidence.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)
    pd.testing.assert_frame_equal(result.evidence.reset_index(drop=True), expected)
    assert result.evidence["asset_id"].tolist() == ["CN:SH:688001", "CN:SH:688002"]


def test_build_evidence_backfill_extracts_report_risk_summary_evidence() -> None:
    result = build_evidence_backfill(
        candidates=pd.DataFrame([{"asset_id": "CN:SH:688001", "trade_date": "2025-01-10"}]),
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(),
        reports=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_id": "r1",
                    "report_date": "2025-01-05",
                    "report_title": "",
                    "raw_summary": "",
                    "company_view": "",
                    "industry_view": "",
                    "risk_summary": "风险是需求不及预期。",
                }
            ]
        ),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    assert "invalidation" in set(result.evidence["evidence_type"])


def test_build_evidence_backfill_requires_exact_product_classification_and_item_name() -> None:
    result = build_evidence_backfill(
        candidates=pd.DataFrame([{"asset_id": "CN:SH:688001", "trade_date": "2025-01-10"}]),
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2024-12-31",
                    "classify_type": "按行业分类",
                    "item_name": "半导体",
                },
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2024-12-31",
                    "classify_type": "按产品分类",
                    "item_name": "",
                },
            ]
        ),
        reports=pd.DataFrame(),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    assert "product_revenue_exposure" not in set(result.evidence["evidence_type"])


def test_future_evidence_is_written_as_unsafe() -> None:
    result = build_evidence_backfill(
        candidates=pd.DataFrame([{"asset_id": "CN:SH:688001", "trade_date": "2025-01-10"}]),
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2025-06-30",
                    "classify_type": "按产品分类",
                    "item_name": "未来产品",
                }
            ]
        ),
        reports=pd.DataFrame(),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    assert len(result.evidence) == 1
    assert result.evidence.iloc[0]["as_of_safe"] is False


def test_write_evidence_artifacts(tmp_path: Path) -> None:
    result = build_evidence_backfill(
        candidates=pd.DataFrame([{"asset_id": "CN:SH:688001", "trade_date": "2025-01-10"}]),
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(),
        reports=pd.DataFrame(),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    paths = write_evidence_artifacts(result=result, output_dir=tmp_path)
    assert paths["csv"].name == "evidence.csv"
    assert paths["json"].name == "evidence.json"
    assert paths["summary"].name == "coverage_summary.md"
    assert paths["source_gap_report"].name == "source_gap_report.csv"
