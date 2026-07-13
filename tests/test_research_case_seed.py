import json
from decimal import Decimal

from stock_research import cli
from stock_research import research_case_seed


class _Context:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def _review_row(snapshot_id="review_item_snapshot:abc", digest_key="digest:1"):
    return {
        "snapshot_id": snapshot_id,
        "run_id": "run:1",
        "trade_date": "2026-07-06",
        "asset_id": "CN:SZ:000001",
        "stock_name": "平安银行",
        "digest_key": digest_key,
        "source_type": "score_topn",
        "source_name": "manual_v1_topn",
        "source_rank": 3,
        "topn_rank": 3,
        "score": Decimal("88"),
        "evidence_status": "partial",
        "missing_evidence_count": 1,
        "partial_evidence_count": 2,
        "warnings_count": 1,
        "payload_hash": "review_hash",
        "review_item_payload": {
            "display_name": "平安银行",
            "summary": "资金强度进入复盘队列",
            "source_name": "manual_v1_topn",
            "score": 88,
        },
    }


def _digest_row(snapshot_id="evidence_digest_snapshot:def", digest_key="digest:1"):
    return {
        "snapshot_id": snapshot_id,
        "run_id": "run:1",
        "trade_date": "2026-07-06",
        "asset_id": "CN:SZ:000001",
        "stock_name": "平安银行",
        "digest_key": digest_key,
        "overall_status": "partial",
        "missing_evidence": ["research_report"],
        "partial_evidence": ["news"],
        "sections_status": {"news": "partial"},
        "payload_hash": "digest_hash",
        "digest_payload": {
            "title": "Strong evidence",
            "bucket": "strong",
            "score": 81,
            "summary": "证据摘要显示资金和新闻均需复核",
        },
    }


def test_review_item_snapshot_maps_to_case_and_claims():
    case = research_case_seed.case_from_review_snapshot(_review_row())
    claims = research_case_seed.claims_from_review_snapshot(_review_row(), case["case_id"])

    assert case["source_type"] == "review_item_snapshot"
    assert case["source_id"] == "review_item_snapshot:abc"
    assert case["asset_id"] == "CN:SZ:000001"
    assert case["theme"] == "score_topn"
    assert case["title"] == "平安银行 · manual_v1_topn"
    assert case["priority"] == 3
    json.dumps(case["metadata"], ensure_ascii=False)
    assert case["metadata"]["score"] == 88.0
    assert {claim["claim_type"] for claim in claims} >= {"summary", "opportunity", "risk"}
    assert claims[0]["case_id"] == case["case_id"]
    assert any("资金强度进入复盘队列" in claim["claim_text"] for claim in claims)
    assert any(claim["confidence"] == 0.88 for claim in claims if claim["claim_type"] == "opportunity")


def test_digest_snapshot_maps_to_supplement_claims_only():
    case_id = research_case_seed.case_id_from_review_snapshot(_review_row())
    claims = research_case_seed.claims_from_digest_snapshot(_digest_row(), case_id)

    assert {claim["claim_type"] for claim in claims} >= {"summary", "opportunity", "risk"}
    assert all(claim["case_id"] == case_id for claim in claims)
    assert any("证据摘要显示资金和新闻均需复核" in claim["claim_text"] for claim in claims)


def test_case_seed_dry_run_matches_digest_without_writes(monkeypatch, tmp_path):
    writes = []

    def fake_fetch_all(_conn, sql, params=None):
        if "FROM ops.review_item_snapshot" in sql:
            return [_review_row()]
        if "FROM ops.evidence_digest_snapshot" in sql:
            return [_digest_row(), _digest_row("evidence_digest_snapshot:unmatched", "digest:missing")]
        return []

    monkeypatch.setattr(research_case_seed, "connect", lambda service: _Context())
    monkeypatch.setattr(research_case_seed, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(research_case_seed, "upsert_research_case", lambda *args, **kwargs: writes.append("case"))
    monkeypatch.setattr(research_case_seed, "upsert_research_claim", lambda *args, **kwargs: writes.append("claim"))
    monkeypatch.setattr(research_case_seed, "upsert_evidence_artifact", lambda *args, **kwargs: writes.append("evidence"))
    monkeypatch.setattr(research_case_seed, "upsert_evidence_link", lambda *args, **kwargs: writes.append("link"))

    summary = research_case_seed.run_research_case_seed(
        trade_date="2026-07-06",
        source_type="all",
        dry_run=True,
        limit=10,
        output_dir=tmp_path,
        service="research",
    )

    assert summary["dry_run"] is True
    assert summary["scanned"] == {"review_item_snapshot": 1, "evidence_digest_snapshot": 2}
    assert summary["cases_planned"] == 1
    assert summary["digest_matched_cases"] == 1
    assert summary["skipped"]["unmatched_digest"] == 1
    assert summary["unmatched_digest_samples"][0]["digest_key"] == "digest:missing"
    assert summary["cases_upserted"] == 0
    assert writes == []
    assert (tmp_path / "research_case_seed_summary.json").exists()
    assert (tmp_path / "research_case_seed_summary.md").exists()
    persisted = json.loads((tmp_path / "research_case_seed_summary.json").read_text(encoding="utf-8"))
    assert persisted["cases_planned"] == 1


def test_case_seed_writes_case_claims_evidence_and_links(monkeypatch, tmp_path):
    writes = []

    def fake_fetch_all(_conn, sql, params=None):
        if "FROM ops.review_item_snapshot" in sql:
            return [_review_row()]
        if "FROM ops.evidence_digest_snapshot" in sql:
            return [_digest_row()]
        return []

    monkeypatch.setattr(research_case_seed, "connect", lambda service: _Context())
    monkeypatch.setattr(research_case_seed, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(research_case_seed, "upsert_research_case", lambda payload, service: writes.append(("case", payload["case_id"])) or payload["case_id"])
    monkeypatch.setattr(research_case_seed, "upsert_research_claim", lambda payload, service: writes.append(("claim", payload["claim_type"])) or payload["claim_id"])
    monkeypatch.setattr(research_case_seed, "upsert_evidence_artifact", lambda payload, service: writes.append(("evidence", payload["evidence_id"])) or payload["evidence_id"])
    monkeypatch.setattr(research_case_seed, "upsert_evidence_link", lambda payload, service: writes.append(("link", payload["target_type"])) or "evidence_link:1")

    summary = research_case_seed.run_research_case_seed(
        trade_date="2026-07-06",
        source_type="all",
        dry_run=False,
        limit=10,
        output_dir=tmp_path,
        service="research",
    )

    assert summary["cases_upserted"] == 1
    assert summary["claims_upserted"] == summary["claims_planned"]
    assert summary["evidence_links_upserted"] == summary["evidence_links_planned"]
    assert writes[0][0] == "case"
    assert ("evidence", "evidence_artifact:review_item_snapshot:abc") in writes
    assert ("evidence", "evidence_artifact:evidence_digest_snapshot:def") in writes
    assert any(item == ("link", "research_case") for item in writes)
    assert any(item == ("link", "research_claim") for item in writes)


def test_case_seed_limit_is_clamped(monkeypatch, tmp_path):
    captured = []

    def fake_fetch_all(_conn, sql, params=None):
        captured.append(params)
        return []

    monkeypatch.setattr(research_case_seed, "connect", lambda service: _Context())
    monkeypatch.setattr(research_case_seed, "fetch_all", fake_fetch_all)

    research_case_seed.run_research_case_seed(
        source_type="review_item_snapshot",
        limit=5000,
        output_dir=tmp_path,
        service="research",
    )

    assert captured[0][-1] == 1000


def test_case_seed_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "trade_date": kwargs["trade_date"],
            "source_type": kwargs["source_type"],
            "scanned": {"review_item_snapshot": 0, "evidence_digest_snapshot": 0},
            "cases_planned": 0,
            "cases_upserted": 0,
            "claims_planned": 0,
            "claims_upserted": 0,
            "evidence_links_planned": 0,
            "evidence_links_upserted": 0,
            "digest_matched_cases": 0,
            "skipped": {"unmatched_digest": 0, "missing_claim_text": 0},
            "errors": [],
            "dry_run": kwargs["dry_run"],
        }

    monkeypatch.setattr(cli, "run_research_case_seed", fake_run)

    cli.main_for_args(
        [
            "research-case-seed",
            "--trade-date",
            "2026-07-06",
            "--source-type",
            "all",
            "--dry-run",
            "--limit",
            "50",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-07-06"
    assert captured["source_type"] == "all"
    assert captured["dry_run"] is True
    assert captured["limit"] == 50
    assert captured["output_dir"] == tmp_path


def test_research_case_seed_idempotency_audit_runs_seed_and_writes_summary(monkeypatch, tmp_path):
    count_rows = [
        {
            "research_case_count": 100,
            "research_claim_count": 600,
            "evidence_artifact_count": 200,
            "evidence_link_count": 800,
            "distinct_case_id_count": 100,
            "distinct_claim_id_count": 600,
            "distinct_evidence_id_count": 200,
            "distinct_link_id_count": 800,
            "duplicate_case_logical_keys_count": 0,
            "duplicate_claim_logical_keys_count": 0,
            "duplicate_evidence_logical_keys_count": 0,
            "duplicate_link_logical_keys_count": 0,
        },
        {
            "research_case_count": 100,
            "research_claim_count": 600,
            "evidence_artifact_count": 200,
            "evidence_link_count": 800,
            "distinct_case_id_count": 100,
            "distinct_claim_id_count": 600,
            "distinct_evidence_id_count": 200,
            "distinct_link_id_count": 800,
            "duplicate_case_logical_keys_count": 0,
            "duplicate_claim_logical_keys_count": 0,
            "duplicate_evidence_logical_keys_count": 0,
            "duplicate_link_logical_keys_count": 0,
        },
    ]

    monkeypatch.setattr(research_case_seed, "_load_audit_counts", lambda service: count_rows.pop(0))
    monkeypatch.setattr(
        research_case_seed,
        "run_research_case_seed",
        lambda **kwargs: {
            "cases_planned": 100,
            "cases_upserted": 100,
            "claims_planned": 600,
            "claims_upserted": 600,
            "evidence_links_planned": 800,
            "evidence_links_upserted": 800,
            "scanned": {"review_item_snapshot": 100, "evidence_digest_snapshot": 100},
            "skipped": {"unmatched_digest": 0, "missing_claim_text": 0},
            "errors": [],
            "dry_run": False,
        },
    )

    summary = research_case_seed.run_research_case_seed_idempotency_audit(
        source_type="all",
        limit=100,
        output_dir=tmp_path,
        service="research",
    )

    assert summary["before"]["research_case_count"] == 100
    assert summary["after"]["research_case_count"] == 100
    assert summary["count_delta"]["research_case_count"] == 0
    assert summary["duplicate_logical_keys"]["evidence_link"] == 0
    assert summary["second_run"]["inserted"]["research_case"] == 0
    assert summary["second_run"]["updated_or_existing"]["research_case"] == 100
    assert summary["second_run"]["skipped"]["unmatched_digest"] == 0
    assert summary["second_run"]["errors"] == []
    assert (tmp_path / "research_case_seed_idempotency_audit_summary.json").exists()
    assert (tmp_path / "research_case_seed_idempotency_audit_summary.md").exists()


def test_research_case_seed_idempotency_audit_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "before": {},
            "after": {},
            "count_delta": {},
            "distinct_counts": {},
            "duplicate_logical_keys": {},
            "second_run": {"inserted": {}, "updated_or_existing": {}, "skipped": {}, "errors": []},
            "json_path": str(tmp_path / "summary.json"),
            "markdown_path": str(tmp_path / "summary.md"),
        }

    monkeypatch.setattr(cli, "run_research_case_seed_idempotency_audit", fake_run)

    cli.main_for_args(
        [
            "research-case-seed-idempotency-audit",
            "--source-type",
            "all",
            "--limit",
            "100",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["source_type"] == "all"
    assert captured["limit"] == 100
    assert captured["output_dir"] == tmp_path
