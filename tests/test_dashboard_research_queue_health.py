from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import research_queue_health


def test_research_queue_health_route_returns_whitelisted_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_research_queue_health",
        lambda **kwargs: {
            "trade_date": "2026-07-07",
            "status": "healthy",
            "can_review": True,
            "can_publish_research_queue": False,
            "summary": {
                "case_count": 100,
                "open_case_count": 100,
                "claim_count": 600,
                "evidence_artifact_count": 200,
                "evidence_link_count": 800,
                "evidence_gap_count": 0,
                "unmatched_digest_count": 0,
                "error_count": 0,
            },
            "last_refresh": {
                "run_id": "research_queue_refresh:1",
                "finished_at": "2026-07-07T10:00:00+08:00",
                "manifest_path": "outputs/research/research_queue_refresh_v1/2026-07-07/research_queue_refresh_manifest.json",
                "raw_manifest": {"must_not": "leak"},
            },
            "publish_gate_status": "research_ready",
            "research_ready_for_publication": True,
            "actual_publish_enabled": False,
            "top_gap_cases": [
                {
                    "case_id": "research_case:abc",
                    "title": "Bank reversal candidate",
                    "asset_id": "CN:SZ:000001",
                    "theme": "bank_reversal",
                    "gap_reasons": ["partial_evidence"],
                    "gap_summary": "partial evidence signal found",
                    "payload": {"must_not": "leak"},
                }
            ],
            "warnings": [],
            "payload": {"must_not": "leak"},
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/queue/health?trade_date=2026-07-07")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["can_review"] is True
    assert payload["can_publish_research_queue"] is False
    assert payload["publish_gate_status"] == "research_ready"
    assert payload["research_ready_for_publication"] is True
    assert payload["actual_publish_enabled"] is False
    assert payload["summary"]["case_count"] == 100
    assert payload["top_gap_cases"][0]["gap_reasons"] == ["partial_evidence"]
    assert "payload" not in payload["top_gap_cases"][0]
    assert "payload" not in payload
    assert "raw_manifest" not in payload["last_refresh"]


def test_load_research_queue_health_statuses_from_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        research_queue_health,
        "load_research_queue_counts",
        lambda **kwargs: {
            "cases": 10,
            "open_cases": 10,
            "claims": 60,
            "evidence_artifacts": 20,
            "evidence_links": 80,
            "evidence_gap_count": 0,
        },
    )
    monkeypatch.setattr(
        research_queue_health,
        "load_latest_refresh_manifest",
        lambda **kwargs: {
            "run_id": "research_queue_refresh:1",
            "finished_at": "2026-07-07T10:00:00+08:00",
            "artifact_paths": {"manifest_json": str(tmp_path / "manifest.json")},
            "counts": {"unmatched_digest": 0, "errors": 0},
            "status": "success",
        },
    )
    monkeypatch.setattr(
        research_queue_health,
        "list_research_queue_gaps",
        lambda **kwargs: {
            "items": [
                {
                    "case_id": "research_case:abc",
                    "title": "Bank reversal candidate",
                    "asset_id": "CN:SZ:000001",
                    "theme": "bank_reversal",
                    "gap_reasons": ["partial_evidence"],
                    "gap_summary": "partial evidence signal found",
                }
            ],
            "summary": {
                "gap_case_count": 1,
                "no_evidence_count": 0,
                "missing_evidence_count": 0,
                "partial_evidence_count": 1,
                "incomplete_evidence_status_count": 0,
                "unknown_gap_count": 0,
                "reviewed_gap_count": 0,
                "pending_gap_count": 0,
                "deferred_gap_count": 0,
                "request_more_evidence_count": 1,
            },
        },
    )

    health = research_queue_health.load_research_queue_health(
        trade_date="2026-07-07",
        output_root=tmp_path,
        service="research",
    )

    assert health["status"] == "healthy"
    assert health["can_review"] is True
    assert health["can_publish_research_queue"] is False
    assert health["publish_gate_status"] == "blocked"
    assert health["research_ready_for_publication"] is False
    assert health["actual_publish_enabled"] is False
    assert health["summary"]["claim_count"] == 60
    assert health["summary"]["partial_evidence_count"] == 1
    assert health["summary"]["request_more_evidence_count"] == 1
    assert health["top_gap_cases"][0]["case_id"] == "research_case:abc"
    assert health["last_refresh"]["run_id"] == "research_queue_refresh:1"


def test_load_research_queue_health_marks_partial_for_gaps_and_unmatched(monkeypatch, tmp_path):
    monkeypatch.setattr(
        research_queue_health,
        "load_research_queue_counts",
        lambda **kwargs: {
            "cases": 10,
            "open_cases": 10,
            "claims": 60,
            "evidence_artifacts": 20,
            "evidence_links": 80,
            "evidence_gap_count": 2,
        },
    )
    monkeypatch.setattr(
        research_queue_health,
        "load_latest_refresh_manifest",
        lambda **kwargs: {
            "run_id": "research_queue_refresh:1",
            "finished_at": "2026-07-07T10:00:00+08:00",
            "artifact_paths": {"manifest_json": str(tmp_path / "manifest.json")},
            "counts": {"unmatched_digest": 1, "errors": 0},
            "status": "partial",
        },
    )
    monkeypatch.setattr(
        research_queue_health,
        "list_research_queue_gaps",
        lambda **kwargs: {
            "items": [],
            "summary": {
                "gap_case_count": 2,
                "no_evidence_count": 0,
                "missing_evidence_count": 0,
                "partial_evidence_count": 2,
                "incomplete_evidence_status_count": 0,
                "unknown_gap_count": 0,
            },
        },
    )

    health = research_queue_health.load_research_queue_health(
        trade_date="2026-07-07",
        output_root=tmp_path,
        service="research",
    )

    assert health["status"] == "partial"
    assert health["publish_gate_status"] == "blocked"
    assert health["research_ready_for_publication"] is False
    assert health["summary"]["evidence_gap_count"] == 2
    assert health["summary"]["unmatched_digest_count"] == 1
    assert "evidence_gap_count=2" in health["warnings"]


def test_load_research_queue_health_marks_empty_without_cases(monkeypatch, tmp_path):
    monkeypatch.setattr(
        research_queue_health,
        "load_research_queue_counts",
        lambda **kwargs: {
            "cases": 0,
            "open_cases": 0,
            "claims": 0,
            "evidence_artifacts": 0,
            "evidence_links": 0,
            "evidence_gap_count": 0,
        },
    )
    monkeypatch.setattr(research_queue_health, "load_latest_refresh_manifest", lambda **kwargs: None)
    monkeypatch.setattr(
        research_queue_health,
        "list_research_queue_gaps",
        lambda **kwargs: {
            "items": [],
            "summary": {
                "gap_case_count": 0,
                "no_evidence_count": 0,
                "missing_evidence_count": 0,
                "partial_evidence_count": 0,
                "incomplete_evidence_status_count": 0,
                "unknown_gap_count": 0,
            },
        },
    )

    health = research_queue_health.load_research_queue_health(
        trade_date="2026-07-07",
        output_root=tmp_path,
        service="research",
    )

    assert health["status"] == "empty"
    assert health["publish_gate_status"] == "empty"
    assert health["research_ready_for_publication"] is False
    assert health["can_review"] is False
    assert health["last_refresh"] is None


def test_load_latest_refresh_manifest_prefers_exact_trade_date(tmp_path):
    exact_dir = tmp_path / "2026-07-07"
    latest_dir = tmp_path / "2026-07-03"
    exact_dir.mkdir()
    latest_dir.mkdir()
    exact_path = exact_dir / "research_queue_refresh_manifest.json"
    latest_path = latest_dir / "research_queue_refresh_manifest.json"
    exact_path.write_text('{"run_id":"exact","artifact_paths":{},"finished_at":"2026-07-07"}', encoding="utf-8")
    latest_path.write_text('{"run_id":"latest","artifact_paths":{},"finished_at":"2026-07-08"}', encoding="utf-8")

    manifest = research_queue_health.load_latest_refresh_manifest(trade_date="2026-07-07", output_root=tmp_path)

    assert manifest is not None
    assert manifest["run_id"] == "exact"
