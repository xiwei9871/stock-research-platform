from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import evidence_registry


def test_evidence_registry_route_filters_by_asset(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_evidence_artifacts",
        lambda **kwargs: [
            {
                "evidence_id": "evidence_artifact:evidence_digest_snapshot:abc",
                "source_type": "evidence_digest_snapshot",
                "source_id": "evidence_digest_snapshot:abc",
                "asset_id": "CN:SZ:000001",
                "trade_date": "2026-07-06",
                "title": "Strong evidence",
                "uri": "",
                "content_hash": "hash123",
                "allowed_metadata": {"digest_key": "digest:1"},
                "payload": {"must_not": "leak"},
                "metadata": {"must_not": "leak"},
            }
        ],
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/evidence?asset_id=CN%3ASZ%3A000001&limit=500")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["title"] == "Strong evidence"
    assert item["allowed_metadata"] == {"digest_key": "digest:1"}
    assert "payload" not in item
    assert "metadata" not in item


def test_list_evidence_artifacts_clamps_limit_and_whitelists_fields(monkeypatch):
    captured = {}

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(_conn, sql, params=None):
        captured["params"] = params
        return [
            {
                "evidence_id": "evidence_artifact:abc",
                "source_type": "evidence_digest_snapshot",
                "source_id": "abc",
                "asset_id": "CN:SZ:000001",
                "trade_date": "2026-07-06",
                "title": "Strong evidence",
                "uri": "",
                "content_hash": "hash123",
                "allowed_metadata": {"digest_key": "digest:1"},
                "payload": {"must_not": "leak"},
            }
        ]

    monkeypatch.setattr(evidence_registry, "connect", lambda service: _Context())
    monkeypatch.setattr(evidence_registry, "fetch_all", fake_fetch_all)

    rows = evidence_registry.list_evidence_artifacts(asset_id="CN:SZ:000001", limit=500, service="research")

    assert captured["params"][-1] == 100
    assert rows == [
        {
            "evidence_id": "evidence_artifact:abc",
            "source_type": "evidence_digest_snapshot",
            "source_id": "abc",
            "asset_id": "CN:SZ:000001",
            "trade_date": "2026-07-06",
            "title": "Strong evidence",
            "uri": "",
            "content_hash": "hash123",
            "allowed_metadata": {"digest_key": "digest:1"},
        }
    ]
