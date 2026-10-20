from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import company_intelligence as ci


def _write_dossier(root: Path, code: str = "002837") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    dossier = {
        "company_code": code,
        "company_name": "英维克",
        "as_of": "2026-10-20",
        "generated_at": "2026-10-20T09:00:00+00:00",
        "provenance": {"code_sha": "abc1234"},
        "conclusion": {"overall_verdict": "contested", "confidence": 0.35},
        "dimensions": {},
        "claims": [],
        "evidence_pool": [],
    }
    path = root / f"{code}_dossier.json"
    path.write_text(json.dumps(dossier, ensure_ascii=False), encoding="utf-8")
    (root / f"{code}_dossier.md").write_text("# dossier\n", encoding="utf-8")
    return path


@pytest.fixture()
def dossier_dir(tmp_path, monkeypatch):
    root = tmp_path / "company_intelligence"
    monkeypatch.setenv("STOCK_RESEARCH_COMPANY_INTELLIGENCE_DIR", str(root))
    return root


@pytest.fixture()
def client():
    return TestClient(dashboard_app.create_app())


def test_list_dossiers_empty(dossier_dir, client):
    response = client.get("/api/research/company-intelligence/dossiers")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_list_dossiers_and_get_dossier(dossier_dir, client):
    _write_dossier(dossier_dir)
    listing = client.get("/api/research/company-intelligence/dossiers").json()
    assert listing["items"][0]["stock_code"] == "002837"
    assert listing["items"][0]["overall_verdict"] == "contested"

    dossier = client.get("/api/research/company-intelligence/stocks/002837/dossier").json()
    assert dossier["company_name"] == "英维克"
    assert dossier["markdown_available"] is True
    assert dossier["reviews"] == []


def test_dossier_404_for_unknown_code(dossier_dir, client):
    response = client.get("/api/research/company-intelligence/stocks/999999/dossier")
    assert response.status_code == 404


def test_markdown_export(dossier_dir, client):
    _write_dossier(dossier_dir)
    response = client.get("/api/research/company-intelligence/stocks/002837/dossier.md")
    assert response.status_code == 200
    assert "# dossier" in response.text


def test_stock_code_sanitized(dossier_dir, client):
    response = client.get("/api/research/company-intelligence/stocks/..%2F..%2Fetc/dossier")
    assert response.status_code == 404


def test_record_review_requires_guard_when_enabled(dossier_dir, client, monkeypatch):
    _write_dossier(dossier_dir)
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "tok")
    payload = {
        "claim_id": "c_tech_full_chain",
        "review_status": "disagreed",
        "reviewer": "operator",
        "comment": "全链条不等于独家",
    }
    denied = client.post("/api/research/company-intelligence/stocks/002837/reviews", json=payload)
    assert denied.status_code in {401, 403}
    allowed = client.post(
        "/api/research/company-intelligence/stocks/002837/reviews",
        json=payload,
        headers={"X-Dashboard-Write-Token": "tok"},
    )
    assert allowed.status_code == 200
    reviews = client.get("/api/research/company-intelligence/stocks/002837/reviews").json()["items"]
    assert len(reviews) == 1
    assert reviews[0]["review_status"] == "disagreed"


def test_record_review_persists_to_sidecar(dossier_dir, client):
    _write_dossier(dossier_dir)
    payload = {
        "claim_id": "c_fin_traceable",
        "review_status": "needs_more_evidence",
        "reviewer": "analyst",
        "comment": "液冷收入拆分需等年报分部披露",
        "dimension": "financial_realization",
    }
    response = client.post("/api/research/company-intelligence/stocks/002837/reviews", json=payload)
    assert response.status_code == 200
    sidecar = (dossier_dir / "002837_reviews.jsonl").read_text(encoding="utf-8")
    assert "needs_more_evidence" in sidecar
    assert "analyst" in sidecar


def test_record_review_rejects_bad_status_and_missing_fields(dossier_dir, client):
    _write_dossier(dossier_dir)
    bad = client.post(
        "/api/research/company-intelligence/stocks/002837/reviews",
        json={"claim_id": "x", "review_status": "bogus", "reviewer": "r", "comment": "c"},
    )
    assert bad.status_code == 400
    missing = client.post(
        "/api/research/company-intelligence/stocks/002837/reviews",
        json={"claim_id": "x"},
    )
    assert missing.status_code == 400


def test_record_review_404_without_dossier(dossier_dir, client):
    response = client.post(
        "/api/research/company-intelligence/stocks/000001/reviews",
        json={"claim_id": "x", "review_status": "accepted", "reviewer": "r", "comment": "c"},
    )
    assert response.status_code == 404


def test_read_model_roundtrip(tmp_path, monkeypatch):
    root = tmp_path / "ci"
    monkeypatch.setenv("STOCK_RESEARCH_COMPANY_INTELLIGENCE_DIR", str(root))
    _write_dossier(root, "688686")
    assert ci.load_company_intelligence_dossier("688686")["company_name"] == "英维克"
    assert ci.load_company_intelligence_dossier("000000") is None
    assert ci.load_company_intelligence_markdown("688686") == "# dossier\n"
