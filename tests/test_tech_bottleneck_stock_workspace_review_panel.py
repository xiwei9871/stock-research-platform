from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
FRONTEND_DATA_DIR = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1"
)
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_tech_bottleneck_review_universe_summary_and_stocks_are_readonly() -> None:
    client = TestClient(dashboard_app.create_app())

    summary_response = client.get("/api/research/tech-bottleneck/review-universe/summary")
    stocks_response = client.get("/api/research/tech-bottleneck/review-universe/stocks?limit=500")

    assert summary_response.status_code == 200
    assert stocks_response.status_code == 200
    summary = summary_response.json()
    stocks = stocks_response.json()
    assert summary["frontend_dataset_count"] == (
        summary["base_frontend_dataset_count"]
        + summary["omission_rescue_review_count"]
    )
    evidence_rows = len(
        pd.read_csv(FRONTEND_DATA_DIR / "tech_bottleneck_review_universe_frontend_evidence_index.csv")
    )
    source_rows = len(
        pd.read_csv(FRONTEND_DATA_DIR / "tech_bottleneck_review_universe_frontend_source_index.csv")
    )
    assert summary["evidence_index_row_count"] >= evidence_rows
    assert summary["source_index_row_count"] >= source_rows
    assert summary["remaining_evidence_gap_count"] == 0
    assert summary["readonly_page"] is True
    assert summary["reviewer_decision_write_enabled"] is False
    assert summary["database_write_enabled"] is False
    assert summary["csv_writeback_enabled"] is False
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert stocks["total"] == summary["frontend_dataset_count"]
    assert len(stocks["items"]) == summary["frontend_dataset_count"]
    assert all(item["frontend_review_status"] == "pending_review" for item in stocks["items"])
    assert all(item["used_for_signal"] is False for item in stocks["items"])
    assert all(item["used_for_admission"] is False for item in stocks["items"])


def test_tech_bottleneck_review_universe_stock_detail_evidence_sources_and_filters() -> None:
    client = TestClient(dashboard_app.create_app())
    stock_code = "000777"

    detail_response = client.get(f"/api/research/tech-bottleneck/review-universe/stocks/{stock_code}")
    evidence_response = client.get(f"/api/research/tech-bottleneck/review-universe/stocks/{stock_code}/evidence")
    source_response = client.get(f"/api/research/tech-bottleneck/review-universe/stocks/{stock_code}/sources")
    filters_response = client.get("/api/research/tech-bottleneck/review-universe/filter-options")

    assert detail_response.status_code == 200
    assert evidence_response.status_code == 200
    assert source_response.status_code == 200
    assert filters_response.status_code == 200
    detail = detail_response.json()
    evidence = evidence_response.json()
    sources = source_response.json()
    filters = filters_response.json()
    assert detail["stock_code"] == stock_code
    assert detail["review_universe_source"] == "v7_proposal_new"
    assert "quality_reassessment_tier" in detail
    assert evidence["stock_code"] == stock_code
    assert evidence["items"]
    assert all(item["citation_quality"] == "page_level" for item in evidence["items"])
    assert sources["items"]
    assert all(item["source_file"] for item in sources["items"])
    assert "review_universe_source" in filters
    assert "v7_proposal_new" in filters["review_universe_source"]
    assert "quality_reassessment_tier" in filters
    assert "tier_1_core_review_priority" in filters["quality_reassessment_tier"]
    assert "bottleneck_relevance" not in filters


def test_tech_bottleneck_review_universe_includes_omission_rescue_candidates() -> None:
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/tech-bottleneck/review-universe/stocks?q=002384&limit=20")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    dongshan = next(item for item in payload["items"] if item["stock_code"] == "002384")
    assert dongshan["review_universe_source"].startswith("omission_rescue")
    assert dongshan["quality_reassessment_tier"] in {
        "tier_2_strong_review_candidate",
        "tier_3_quality_or_value_capture_gap",
        "tier_4_downgrade_or_reject_review",
    }

    evidence = client.get("/api/research/tech-bottleneck/review-universe/stocks/002384/evidence").json()
    sources = client.get("/api/research/tech-bottleneck/review-universe/stocks/002384/sources").json()
    assert evidence["total"] > 0
    assert sources["total"] > 0
    assert all(item["citation_quality"] == "page_level" for item in evidence["items"])


def test_tech_bottleneck_review_universe_filters_and_strategy_diff_clean() -> None:
    client = TestClient(dashboard_app.create_app())
    reassessment = pd.read_csv(
        PROJECT_ROOT
        / "outputs/research/tech_bottleneck_review_universe_quality_reassessment_v2/review_universe_quality_reassessment_v2.csv",
        dtype={"stock_code": str},
    )
    tier_1_count = int(reassessment["quality_reassessment_tier"].eq("tier_1_core_review_priority").sum())

    response = client.get(
        "/api/research/tech-bottleneck/review-universe/stocks"
        "?review_universe_source=v5_targeted_hydrated&primary_source_supported=true&limit=100"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 29
    assert all(item["review_universe_source"] == "v5_targeted_hydrated" for item in payload["items"])
    tier_response = client.get(
        "/api/research/tech-bottleneck/review-universe/stocks"
        "?quality_reassessment_tier=tier_1_core_review_priority&limit=500"
    )
    assert tier_response.status_code == 200
    tier_payload = tier_response.json()
    assert tier_payload["total"] == tier_1_count
    assert tier_1_count > 0
    assert all(item["quality_reassessment_tier"] == "tier_1_core_review_priority" for item in tier_payload["items"])
    assert any(item["stock_code"] == "300308" for item in tier_payload["items"])
    assert any(item["stock_code"] == "002463" for item in tier_payload["items"])
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
