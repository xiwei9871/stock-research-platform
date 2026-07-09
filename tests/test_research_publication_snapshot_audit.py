import json
from pathlib import Path

from stock_research import cli
from stock_research import research_publication_snapshot_audit


def _snapshot() -> dict:
    return {
        "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
        "trade_date": "2026-07-06",
        "channel": "research_queue_internal",
        "title": "Research Queue Internal Snapshot 2026-07-06",
        "created_by": "research_queue_publish",
        "created_at": "2026-07-08T10:00:00+08:00",
        "package_id": "research_publication_package:abc",
        "gate_status": "research_ready",
        "research_ready_for_publication": True,
        "actual_external_delivery_enabled": False,
        "case_count": 2,
        "claim_count": 3,
        "evidence_count": 4,
        "gap_count": 0,
        "blocker_count": 0,
    }


def test_snapshot_audit_no_snapshots_writes_success_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(research_publication_snapshot_audit, "list_publication_snapshots", lambda **kwargs: [])

    result = research_publication_snapshot_audit.run_research_publication_snapshot_audit(
        trade_date="2026-07-03",
        output_dir=tmp_path,
        service="research",
    )

    assert result["trade_date"] == "2026-07-03"
    assert result["snapshot_count"] == 0
    assert result["latest_snapshot_id"] is None
    assert result["external_delivery_enabled"] is False
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
    persisted = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert persisted["snapshot_count"] == 0
    assert "snapshot_count=0" in Path(result["markdown_path"]).read_text(encoding="utf-8")


def test_snapshot_audit_with_fixture_snapshot_writes_latest_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(research_publication_snapshot_audit, "list_publication_snapshots", lambda **kwargs: [_snapshot()])

    result = research_publication_snapshot_audit.run_research_publication_snapshot_audit(
        trade_date="2026-07-06",
        output_dir=tmp_path,
        service="research",
    )

    assert result["snapshot_count"] == 1
    assert result["latest_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"
    assert result["channels"] == ["research_queue_internal"]
    assert result["latest_gate_status"] == "research_ready"
    assert result["latest_package_summary"]["case_count"] == 2
    assert result["external_delivery_enabled"] is False


def test_snapshot_audit_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "trade_date": "2026-07-06",
            "snapshot_count": 0,
            "json_path": str(tmp_path / "research_publication_snapshot_audit.json"),
            "markdown_path": str(tmp_path / "research_publication_snapshot_audit.md"),
        }

    monkeypatch.setattr(cli, "run_research_publication_snapshot_audit", fake_run)

    cli.main_for_args(
        [
            "research-publication-snapshot-audit",
            "--trade-date",
            "2026-07-06",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-07-06"
    assert captured["output_dir"] == tmp_path
