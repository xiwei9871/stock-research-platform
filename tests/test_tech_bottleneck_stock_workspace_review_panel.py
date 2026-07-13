from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


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
    assert summary["frontend_dataset_count"] == 378
    assert summary["evidence_index_row_count"] == 8583
    assert summary["source_index_row_count"] == 1071
    assert summary["remaining_evidence_gap_count"] == 0
    assert summary["readonly_page"] is True
    assert summary["reviewer_decision_write_enabled"] is False
    assert summary["database_write_enabled"] is False
    assert summary["csv_writeback_enabled"] is False
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert stocks["total"] == 378
    assert len(stocks["items"]) == 378
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
    assert evidence["stock_code"] == stock_code
    assert evidence["items"]
    assert all(item["citation_quality"] == "page_level" for item in evidence["items"])
    assert sources["items"]
    assert all(item["source_file"] for item in sources["items"])
    assert "review_universe_source" in filters
    assert "v7_proposal_new" in filters["review_universe_source"]


def test_tech_bottleneck_review_universe_filters_and_strategy_diff_clean() -> None:
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/research/tech-bottleneck/review-universe/stocks"
        "?review_universe_source=v5_targeted_hydrated&primary_source_supported=true&limit=100"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 29
    assert all(item["review_universe_source"] == "v5_targeted_hydrated" for item in payload["items"])
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
