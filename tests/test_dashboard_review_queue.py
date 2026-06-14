from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import review_queue


def _score(asset_id, rank, score_total=80.0):
    return {
        "trade_date": "2026-06-08",
        "asset_id": asset_id,
        "rank": rank,
        "score_total": score_total,
        "score_version": "manual_v1",
        "score_components": {},
    }


def _digest(asset_id, *, bucket="strong", score=80, facts=None, risks=None, warnings=None):
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "trade_date": "2026-06-08",
        "title": f"{bucket} evidence",
        "score": score,
        "bucket": bucket,
        "facts": facts
        if facts is not None
        else [
            {"kind": "strategy", "label": "TopN candidate"},
            {"kind": "news", "label": "Recent news"},
        ],
        "risk_flags": risks or [],
        "source_refs": {"strategy_asset_id": asset_id},
        "next_actions": [
            {
                "key": "review_stock",
                "label": "Review Stock",
                "workspace": "stock",
                "asset_id": asset_id,
                "query": asset_id,
            },
            {
                "key": "open_news",
                "label": "Open News",
                "workspace": "news",
                "asset_id": asset_id,
                "query": asset_id,
            },
        ],
        "warnings": warnings or [],
    }


def test_build_review_queue_groups_all_buckets_and_sorts(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {
            "latest_market_date": "2026-06-08",
            "topn_preview": [
                _score("000003.SZ", 3, 70),
                _score("000001.SZ", 1, 90),
                _score("000002.SZ", 2, 60),
            ],
        },
    )
    digests = {
        "000001.SZ": _digest("000001.SZ", bucket="mixed", score=62),
        "000002.SZ": _digest("000002.SZ", bucket="strong", score=81),
        "000003.SZ": _digest("000003.SZ", bucket="thin", score=30, facts=[]),
    }
    monkeypatch.setattr(review_queue, "build_evidence_digest", lambda asset_id, **kwargs: digests[asset_id])

    payload = review_queue.build_review_queue(trade_date="2026-06-08", score_version="manual_v1", limit=20)

    assert payload["trade_date"] == "2026-06-08"
    assert [group["bucket"] for group in payload["groups"]] == ["strong", "mixed", "risk_heavy", "thin"]
    assert [group["count"] for group in payload["groups"]] == [1, 1, 0, 1]
    strong_item = payload["groups"][0]["items"][0]
    assert strong_item["queue_id"] == "2026-06-08:manual_v1:000002.SZ"
    assert strong_item["rank"] == 2
    assert strong_item["source_kinds"] == ["strategy", "news"]
    assert strong_item["next_action_count"] == 2


def test_build_review_queue_degrades_digest_failure_to_thin_item(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-08", "topn_preview": [_score("000001.SZ", 1, 90)]},
    )

    def fail_digest(asset_id, **kwargs):
        raise RuntimeError("digest unavailable")

    monkeypatch.setattr(review_queue, "build_evidence_digest", fail_digest)

    payload = review_queue.build_review_queue(trade_date="2026-06-08", score_version="manual_v1", limit=20)

    thin = next(group for group in payload["groups"] if group["bucket"] == "thin")
    assert thin["count"] == 1
    item = thin["items"][0]
    assert item["asset_id"] == "000001.SZ"
    assert item["warning_count"] == 1
    assert "digest unavailable" in item["digest"]["warnings"][0]
    assert any("digest unavailable" in warning for warning in payload["warnings"])


def test_build_review_queue_bounds_limit_and_uses_latest_market_date(monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {"latest_market_date": "2026-06-08", "topn_preview": []}

    monkeypatch.setattr(review_queue, "load_platform_summary", fake_summary)

    payload = review_queue.build_review_queue(trade_date=None, score_version="manual_v1", limit=999, lookback_days=999)

    assert captured["top_n"] == 50
    assert payload["trade_date"] == "2026-06-08"
    assert payload["warnings"] == []


def test_review_queue_endpoint_forwards_query(monkeypatch):
    captured = {}

    def fake_queue(*, trade_date=None, score_version="manual_v1", limit=20, lookback_days=90):
        captured.update(
            {
                "trade_date": trade_date,
                "score_version": score_version,
                "limit": limit,
                "lookback_days": lookback_days,
            }
        )
        return {"trade_date": trade_date, "score_version": score_version, "generated_at": "", "groups": [], "warnings": []}

    monkeypatch.setattr(dashboard_app, "build_review_queue", fake_queue)
    client = TestClient(dashboard_app.app)

    response = client.get(
        "/api/review-queue",
        params={"trade_date": "2026-06-08", "score_version": "manual_v2", "limit": 12, "lookback_days": 45},
    )

    assert response.status_code == 200
    assert captured == {
        "trade_date": "2026-06-08",
        "score_version": "manual_v2",
        "limit": 12,
        "lookback_days": 45,
    }
