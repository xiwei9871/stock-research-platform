from __future__ import annotations

import json

import pandas as pd
import pytest

from stock_research.tech_bottleneck_evidence_backfill import (
    EVIDENCE_COLUMNS,
    classify_text_evidence,
    normalize_evidence_rows,
    normalize_evidence_candidates,
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
