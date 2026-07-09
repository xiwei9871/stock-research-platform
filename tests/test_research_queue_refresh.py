import json
from pathlib import Path

from stock_research import cli
from stock_research import research_queue_refresh


def test_research_queue_refresh_runs_steps_and_writes_manifest(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(research_queue_refresh, "apply_research_object_schema", lambda service="research": calls.append(("schema", service)))
    monkeypatch.setattr(
        research_queue_refresh,
        "run_research_evidence_backfill",
        lambda **kwargs: calls.append(("evidence", kwargs))
        or {
            "scanned": 2,
            "inserted_or_updated": 2,
            "skipped": 0,
            "errors": [],
            "json_path": str(tmp_path / "research_evidence_backfill_summary.json"),
            "markdown_path": str(tmp_path / "research_evidence_backfill_summary.md"),
        },
    )
    monkeypatch.setattr(
        research_queue_refresh,
        "run_research_case_seed",
        lambda **kwargs: calls.append(("seed", kwargs))
        or {
            "cases_upserted": 1,
            "claims_upserted": 2,
            "evidence_links_upserted": 3,
            "digest_matched_cases": 1,
            "skipped": {"unmatched_digest": 0, "missing_claim_text": 0},
            "errors": [],
            "json_path": str(tmp_path / "research_case_seed_summary.json"),
            "markdown_path": str(tmp_path / "research_case_seed_summary.md"),
        },
    )
    monkeypatch.setattr(
        research_queue_refresh,
        "run_research_case_seed_idempotency_audit",
        lambda **kwargs: calls.append(("audit", kwargs))
        or {
            "duplicate_logical_keys": {"research_case": 0, "research_claim": 0, "evidence_artifact": 0, "evidence_link": 0},
            "second_run": {"errors": [], "skipped": {"unmatched_digest": 0}},
            "json_path": str(tmp_path / "research_case_seed_idempotency_audit_summary.json"),
            "markdown_path": str(tmp_path / "research_case_seed_idempotency_audit_summary.md"),
        },
    )
    monkeypatch.setattr(
        research_queue_refresh,
        "load_research_queue_counts",
        lambda trade_date=None, service="research": {
            "cases": 1,
            "open_cases": 1,
            "claims": 2,
            "evidence_artifacts": 2,
            "evidence_links": 3,
            "evidence_gap_count": 0,
        },
    )
    monkeypatch.setattr(
        research_queue_refresh,
        "write_publication_entrypoint_discovery",
        lambda output_dir, repo_root=None: str(Path(output_dir) / "publication_entrypoint_discovery.md"),
    )

    manifest = research_queue_refresh.run_research_queue_refresh(
        trade_date="2026-07-07",
        limit=100,
        output_dir=tmp_path,
        service="research",
    )

    assert [call[0] for call in calls] == ["schema", "evidence", "seed", "audit"]
    assert manifest["status"] == "success"
    assert manifest["trade_date"] == "2026-07-07"
    assert manifest["dry_run"] is False
    assert manifest["counts"]["cases"] == 1
    assert manifest["counts"]["unmatched_digest"] == 0
    assert manifest["artifact_paths"]["manifest_json"].endswith("research_queue_refresh_manifest.json")
    assert (tmp_path / "research_queue_refresh_manifest.json").exists()
    assert (tmp_path / "research_queue_refresh_summary.md").exists()
    persisted = json.loads((tmp_path / "research_queue_refresh_manifest.json").read_text(encoding="utf-8"))
    assert persisted["run_id"] == manifest["run_id"]


def test_research_queue_refresh_dry_run_skips_schema_and_audit(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(research_queue_refresh, "apply_research_object_schema", lambda service="research": calls.append("schema"))
    monkeypatch.setattr(
        research_queue_refresh,
        "run_research_evidence_backfill",
        lambda **kwargs: calls.append(("evidence", kwargs["dry_run"])) or {"scanned": 1, "inserted_or_updated": 0, "skipped": 0, "errors": []},
    )
    monkeypatch.setattr(
        research_queue_refresh,
        "run_research_case_seed",
        lambda **kwargs: calls.append(("seed", kwargs["dry_run"]))
        or {"cases_upserted": 0, "claims_upserted": 0, "evidence_links_upserted": 0, "skipped": {"unmatched_digest": 0}, "errors": []},
    )
    monkeypatch.setattr(research_queue_refresh, "run_research_case_seed_idempotency_audit", lambda **kwargs: calls.append("audit"))
    monkeypatch.setattr(
        research_queue_refresh,
        "load_research_queue_counts",
        lambda **kwargs: {"cases": 0, "open_cases": 0, "claims": 0, "evidence_artifacts": 0, "evidence_links": 0, "evidence_gap_count": 0},
    )
    monkeypatch.setattr(research_queue_refresh, "write_publication_entrypoint_discovery", lambda output_dir, repo_root=None: "")

    manifest = research_queue_refresh.run_research_queue_refresh(
        trade_date="2026-07-07",
        dry_run=True,
        output_dir=tmp_path,
        service="research",
    )

    assert calls == [("evidence", True), ("seed", True)]
    assert manifest["dry_run"] is True
    assert manifest["schema_status"] == "skipped_dry_run"
    assert manifest["idempotency_audit"]["status"] == "skipped_dry_run"


def test_research_queue_refresh_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "success", "artifact_paths": {}, "counts": {}, "warnings": []}

    monkeypatch.setattr(cli, "run_research_queue_refresh", fake_run)

    cli.main_for_args(
        [
            "research-queue-refresh",
            "--trade-date",
            "2026-07-07",
            "--limit",
            "100",
            "--dry-run",
            "--skip-idempotency-audit",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-07-07"
    assert captured["limit"] == 100
    assert captured["dry_run"] is True
    assert captured["skip_idempotency_audit"] is True
    assert captured["output_dir"] == tmp_path
