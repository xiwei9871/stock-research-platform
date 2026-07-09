from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import tech_bottleneck_review_decisions as decisions


FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _client_with_tmp_overlay(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(decisions, "OVERLAY_DIR", tmp_path)
    decisions.load_ledger.cache_clear()
    decisions.load_current_overlay.cache_clear()
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "secret")
    return TestClient(dashboard_app.create_app())


def _valid_payload(**overrides):
    payload = {
        "stock_code": "000777",
        "stock_name": "中核科技",
        "reviewer_decision": "need_more_evidence",
        "reviewer": "operator",
        "review_comment": "需要补充收入占比、客户验证和核心环节一手证据。",
        "rubric_flags": {
            "hard_tech": True,
            "bottleneck_role": True,
            "business_relevance": "unclear",
            "primary_source_evidence": "partial",
            "page_level_evidence": True,
            "value_capture": "unclear",
            "route_around_risk": "medium",
            "disconfirmation_risk": "medium",
        },
        "evidence_checked": True,
        "source_context": {"from": "tech_bottleneck_review_universe_page"},
    }
    payload.update(overrides)
    return payload


def test_manual_decision_write_requires_dashboard_write_token(monkeypatch, tmp_path):
    client = _client_with_tmp_overlay(monkeypatch, tmp_path)

    response = client.post("/api/research/tech-bottleneck/review-universe/decisions", json=_valid_payload())

    assert response.status_code == 403
    assert response.json()["detail"] == "missing_dashboard_write_token"
    assert not (tmp_path / "manual_decision_ledger.jsonl").exists()


def test_manual_decision_records_append_only_ledger_and_current_overlay(monkeypatch, tmp_path):
    client = _client_with_tmp_overlay(monkeypatch, tmp_path)

    response = client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers={"X-Dashboard-Write-Token": "secret"},
        json=_valid_payload(),
    )
    second = client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers={"X-Dashboard-Write-Token": "secret"},
        json=_valid_payload(reviewer_decision="hold", review_comment="供应链角色仍需人工确认。"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "recorded"
    assert response.json()["reviewed_at"]
    assert second.status_code == 200
    ledger_lines = (tmp_path / "manual_decision_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger_lines) == 2
    current_overlay = json.loads((tmp_path / "manual_decision_current_overlay.json").read_text(encoding="utf-8"))
    assert current_overlay["000777"]["reviewer_decision"] == "hold"
    assert current_overlay["000777"]["decision_source"] == "manual_overlay"


def test_manual_decision_validation_rejects_invalid_stock_keep_and_forbidden_fields(monkeypatch, tmp_path):
    client = _client_with_tmp_overlay(monkeypatch, tmp_path)
    headers = {"X-Dashboard-Write-Token": "secret"}

    invalid_decision = client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers=headers,
        json=_valid_payload(reviewer_decision="approve"),
    )
    unknown_stock = client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers=headers,
        json=_valid_payload(stock_code="999999"),
    )
    decision_without_comment = client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers=headers,
        json=_valid_payload(review_comment=""),
    )
    decision_without_evidence = client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers=headers,
        json=_valid_payload(evidence_checked=False),
    )
    forbidden_signal = client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers=headers,
        json=_valid_payload(used_for_signal=True),
    )

    assert invalid_decision.status_code == 400
    assert invalid_decision.json()["detail"] == "invalid_reviewer_decision"
    assert unknown_stock.status_code == 400
    assert unknown_stock.json()["detail"] == "stock_not_in_review_universe"
    assert decision_without_comment.status_code == 400
    assert decision_without_comment.json()["detail"] == "review_comment_required"
    assert decision_without_evidence.status_code == 400
    assert decision_without_evidence.json()["detail"] == "evidence_checked_required"
    assert forbidden_signal.status_code == 400
    assert forbidden_signal.json()["detail"] == "manual_decision_forbidden_field"


def test_decision_summary_and_stocks_overlay_manual_decisions(monkeypatch, tmp_path):
    client = _client_with_tmp_overlay(monkeypatch, tmp_path)
    headers = {"X-Dashboard-Write-Token": "secret"}
    client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers=headers,
        json=_valid_payload(reviewer_decision="reject", review_comment="证据不支持核心卡点。"),
    )

    summary = client.get("/api/research/tech-bottleneck/review-universe/decision-summary").json()
    detail = client.get("/api/research/tech-bottleneck/review-universe/stocks/000777").json()
    decisions_response = client.get("/api/research/tech-bottleneck/review-universe/decisions?stock_code=000777")

    assert summary["total_review_universe_count"] == 378
    assert summary["reviewed_count"] == 1
    assert summary["pending_count"] == 377
    assert summary["reject_count"] == 1
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["frozen_v7_generated"] is False
    assert detail["reviewer_decision"] == "reject"
    assert detail["review_status"] == "reviewed"
    assert detail["decision_source"] == "manual_overlay"
    assert decisions_response.status_code == 200
    assert decisions_response.json()["items"][0]["reviewer_decision"] == "reject"


def test_manual_overlay_does_not_mutate_frontend_dataset(monkeypatch, tmp_path):
    client = _client_with_tmp_overlay(monkeypatch, tmp_path)
    dataset = Path(
        "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
        "tech_bottleneck_review_universe_frontend_dataset.csv"
    )
    before = dataset.read_bytes()

    client.post(
        "/api/research/tech-bottleneck/review-universe/decisions",
        headers={"X-Dashboard-Write-Token": "secret"},
        json=_valid_payload(),
    )

    assert dataset.read_bytes() == before
