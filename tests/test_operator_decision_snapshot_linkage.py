import json

from stock_research.operator_decision import snapshot_linkage


def _review_snapshot(**overrides):
    row = {
        "snapshot_id": "review_item_snapshot:abc",
        "run_id": "eod-2026-06-12-local",
        "digest_key": "2026-06-12:manual_v1:000001.SZ",
        "asset_id": "000001.SZ",
        "payload_hash": "review-hash",
        "created_at": "2026-06-12T18:00:00+08:00",
        "review_item_payload": {
            "source_type": "score_topn",
            "source_name": "manual_v1_topn",
        },
    }
    row.update(overrides)
    return row


def _digest_snapshot(**overrides):
    row = {
        "snapshot_id": "evidence_digest_snapshot:def",
        "run_id": "eod-2026-06-12-local",
        "digest_key": "2026-06-12:manual_v1:000001.SZ",
        "asset_id": "000001.SZ",
        "payload_hash": "digest-hash",
        "created_at": "2026-06-12T18:01:00+08:00",
    }
    row.update(overrides)
    return row


def test_resolve_decision_snapshot_linkage_uses_explicit_snapshot_ids(monkeypatch):
    monkeypatch.setattr(
        snapshot_linkage,
        "load_review_item_snapshot",
        lambda snapshot_id, service="stock_research": _review_snapshot(snapshot_id=snapshot_id),
    )
    monkeypatch.setattr(
        snapshot_linkage,
        "load_evidence_digest_snapshot",
        lambda snapshot_id, service="stock_research": _digest_snapshot(snapshot_id=snapshot_id),
    )

    result = snapshot_linkage.resolve_decision_snapshot_linkage(
        {
            "source_context": '{"source_context_label":"dashboard_topn","custom":"keep"}',
            "review_item_snapshot_id": "review_item_snapshot:abc",
            "evidence_digest_snapshot_id": "evidence_digest_snapshot:def",
        }
    )

    assert result["snapshot_linkage_status"] == "linked"
    assert result["review_item_snapshot_id"] == "review_item_snapshot:abc"
    assert result["evidence_digest_snapshot_id"] == "evidence_digest_snapshot:def"
    assert result["review_item_payload_hash"] == "review-hash"
    assert result["evidence_digest_payload_hash"] == "digest-hash"
    assert result["custom"] == "keep"
    assert result["snapshot_linkage_warnings"] == []


def test_resolve_decision_snapshot_linkage_finds_by_run_id_and_digest_key(monkeypatch):
    captured = {}

    def list_review(**kwargs):
        captured["review"] = kwargs
        return [_review_snapshot()]

    def list_digest(**kwargs):
        captured["digest"] = kwargs
        return [_digest_snapshot()]

    monkeypatch.setattr(snapshot_linkage, "list_review_item_snapshots", list_review)
    monkeypatch.setattr(snapshot_linkage, "list_evidence_digest_snapshots", list_digest)

    result = snapshot_linkage.resolve_decision_snapshot_linkage(
        {
            "source_context": "dashboard_topn",
            "run_id": "eod-2026-06-12-local",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "asset_id": "000001.SZ",
        }
    )

    assert captured["review"]["run_id"] == "eod-2026-06-12-local"
    assert captured["review"]["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert captured["digest"]["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert result["source_context_label"] == "dashboard_topn"
    assert result["snapshot_linkage_status"] == "linked"
    assert result["source_type"] == "score_topn"
    assert result["source_name"] == "manual_v1_topn"


def test_resolve_decision_snapshot_linkage_falls_back_to_run_id_and_asset_id(monkeypatch):
    monkeypatch.setattr(
        snapshot_linkage,
        "list_review_item_snapshots",
        lambda **kwargs: [_review_snapshot(digest_key="digest-from-review")],
    )
    monkeypatch.setattr(
        snapshot_linkage,
        "list_evidence_digest_snapshots",
        lambda **kwargs: [_digest_snapshot(digest_key="digest-from-review")],
    )

    result = snapshot_linkage.resolve_decision_snapshot_linkage(
        {"run_id": "eod-2026-06-12-local", "asset_id": "000001.SZ"}
    )

    assert result["snapshot_linkage_status"] == "linked"
    assert result["digest_key"] == "digest-from-review"


def test_resolve_decision_snapshot_linkage_missing_does_not_fail(monkeypatch):
    monkeypatch.setattr(snapshot_linkage, "list_review_item_snapshots", lambda **kwargs: [])
    monkeypatch.setattr(snapshot_linkage, "list_evidence_digest_snapshots", lambda **kwargs: [])

    result = snapshot_linkage.resolve_decision_snapshot_linkage(
        {
            "source_context": '{"run_id":"eod-2026-06-12-local","digest_key":"digest-1"}',
            "asset_id": "000001.SZ",
        }
    )

    assert result["run_id"] == "eod-2026-06-12-local"
    assert result["digest_key"] == "digest-1"
    assert result["snapshot_linkage_status"] == "missing"
    assert result["review_item_snapshot_id"] == ""
    assert result["evidence_digest_snapshot_id"] == ""
    assert result["snapshot_linkage_warnings"] == [
        "No review_item_snapshot found for run_id + digest_key",
        "No evidence_digest_snapshot found for run_id + digest_key",
    ]


def test_merge_source_context_preserves_json_and_plain_text():
    merged_json = snapshot_linkage.merge_source_context(
        '{"run_id":"old-run","custom":"keep"}',
        {"run_id": "new-run", "snapshot_linkage_status": "linked"},
    )
    merged_plain = snapshot_linkage.merge_source_context(
        "dashboard_topn",
        {"run_id": "new-run"},
    )

    assert json.loads(merged_json) == {
        "run_id": "new-run",
        "custom": "keep",
        "snapshot_linkage_status": "linked",
    }
    assert json.loads(merged_plain) == {
        "source_context_label": "dashboard_topn",
        "run_id": "new-run",
    }
