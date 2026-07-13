import json

from stock_research import cli
from stock_research import research_evidence_backfill


class _Context:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_backfill_dry_run_scans_without_upsert(monkeypatch, tmp_path):
    upserts = []

    def fake_fetch_all(_conn, sql, params=None):
        if "FROM ops.evidence_digest_snapshot" not in sql:
            return []
        return [
            {
                "snapshot_id": "evidence_digest_snapshot:abc",
                "asset_id": "CN:SZ:000001",
                "trade_date": "2026-07-06",
                "digest_key": "digest:1",
                "payload_hash": "hash123",
                "digest_payload": {"title": "Strong evidence"},
            }
        ]

    monkeypatch.setattr(research_evidence_backfill, "connect", lambda service: _Context())
    monkeypatch.setattr(research_evidence_backfill, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        research_evidence_backfill,
        "upsert_evidence_artifact",
        lambda evidence, service: upserts.append(evidence),
    )

    summary = research_evidence_backfill.run_research_evidence_backfill(
        trade_date="2026-07-06",
        source_type="evidence_digest_snapshot",
        dry_run=True,
        limit=10,
        output_dir=tmp_path,
        service="research",
    )

    assert summary["trade_date"] == "2026-07-06"
    assert summary["source_type"] == "evidence_digest_snapshot"
    assert summary["scanned"] == 1
    assert summary["inserted_or_updated"] == 0
    assert summary["skipped"] == 0
    assert summary["errors"] == []
    assert summary["dry_run"] is True
    assert upserts == []
    assert (tmp_path / "research_evidence_backfill_summary.json").exists()
    assert (tmp_path / "research_evidence_backfill_summary.md").exists()
    persisted = json.loads((tmp_path / "research_evidence_backfill_summary.json").read_text(encoding="utf-8"))
    assert persisted["scanned"] == 1


def test_backfill_all_sources_upserts_evidence(monkeypatch, tmp_path):
    upserts = []

    def fake_fetch_all(_conn, sql, params=None):
        if "FROM ops.evidence_digest_snapshot" in sql:
            return [
                {
                    "snapshot_id": "evidence_digest_snapshot:abc",
                    "asset_id": "CN:SZ:000001",
                    "trade_date": "2026-07-06",
                    "digest_key": "digest:1",
                    "payload_hash": "hash123",
                    "digest_payload": {"title": "Strong evidence"},
                }
            ]
        if "FROM ops.review_item_snapshot" in sql:
            return [
                {
                    "snapshot_id": "review_item_snapshot:def",
                    "asset_id": "CN:SZ:000001",
                    "trade_date": "2026-07-06",
                    "digest_key": "digest:1",
                    "payload_hash": "hash456",
                    "review_item_payload": {"display_name": "平安银行"},
                }
            ]
        return []

    monkeypatch.setattr(research_evidence_backfill, "connect", lambda service: _Context())
    monkeypatch.setattr(research_evidence_backfill, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        research_evidence_backfill,
        "upsert_evidence_artifact",
        lambda evidence, service: upserts.append(evidence["evidence_id"]) or evidence["evidence_id"],
    )

    summary = research_evidence_backfill.run_research_evidence_backfill(
        trade_date="2026-07-06",
        source_type="all",
        dry_run=False,
        limit=10,
        output_dir=tmp_path,
        service="research",
    )

    assert summary["scanned"] == 2
    assert summary["inserted_or_updated"] == 2
    assert upserts == [
        "evidence_artifact:evidence_digest_snapshot:abc",
        "evidence_artifact:review_item_snapshot:def",
    ]


def test_backfill_limit_is_clamped(monkeypatch, tmp_path):
    captured = []

    def fake_fetch_all(_conn, sql, params=None):
        captured.append(params)
        return []

    monkeypatch.setattr(research_evidence_backfill, "connect", lambda service: _Context())
    monkeypatch.setattr(research_evidence_backfill, "fetch_all", fake_fetch_all)

    research_evidence_backfill.run_research_evidence_backfill(
        source_type="review_item_snapshot",
        limit=5000,
        output_dir=tmp_path,
        service="research",
    )

    assert captured[0][-1] == 1000


def test_backfill_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "trade_date": kwargs["trade_date"],
            "source_type": kwargs["source_type"],
            "scanned": 0,
            "inserted_or_updated": 0,
            "skipped": 0,
            "errors": [],
            "dry_run": kwargs["dry_run"],
            "json_path": str(tmp_path / "summary.json"),
            "markdown_path": str(tmp_path / "summary.md"),
        }

    monkeypatch.setattr(cli, "run_research_evidence_backfill", fake_run)

    cli.main_for_args(
        [
            "research-evidence-backfill",
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
