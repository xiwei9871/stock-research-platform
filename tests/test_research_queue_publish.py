import json
from pathlib import Path

import pytest

from stock_research import cli
from stock_research import research_queue_publish


def _package(status: str = "blocked") -> dict:
    publishable = status == "research_ready"
    return {
        "trade_date": "2026-07-03",
        "package_id": f"research_publication_package:{status}",
        "publishable": publishable,
        "actual_publish_enabled": False,
        "gate": {
            "status": status,
            "research_ready_for_publication": publishable,
            "actual_publish_enabled": False,
        },
        "summary": {
            "case_count": 15,
            "claim_count": 90,
            "evidence_count": 30,
            "evidence_link_count": 120,
            "gap_count": 0 if publishable else 15,
            "reviewed_gap_count": 15 if publishable else 0,
            "pending_gap_count": 0 if publishable else 14,
            "request_more_evidence_count": 0 if publishable else 1,
            "deferred_gap_count": 0,
            "unmatched_digest_count": 0,
            "error_count": 0,
        },
        "sections": [
            {
                "section_type": "blocked_cases",
                "title": "发布阻塞项",
                "items": [{"case_id": "research_case:alpha", "payload": {"must_not": "leak"}}],
            }
        ],
        "warnings": [
            {
                "code": "external_delivery_not_connected",
                "message": "External research delivery is not connected",
                "count": 1,
            }
        ],
        "blockers": []
        if publishable
        else [
            {"code": "pending_gap", "message": "14 gap cases have not been reviewed", "count": 14},
            {"code": "external_delivery_not_connected", "message": "External research delivery is not connected", "count": 1},
        ],
    }


def test_publish_research_queue_dry_run_blocked_does_not_write_snapshot(monkeypatch, tmp_path):
    writes = []
    monkeypatch.setattr(research_queue_publish, "build_research_publication_package", lambda *args, **kwargs: _package("blocked"))
    monkeypatch.setattr(research_queue_publish, "record_publication_snapshot", lambda *args, **kwargs: writes.append(kwargs) or "never")

    result = research_queue_publish.publish_research_queue(
        "2026-07-03",
        output_dir=tmp_path,
    )

    assert result["status"] == "blocked"
    assert result["publishable"] is False
    assert result["snapshot_written"] is False
    assert result["publication_snapshot_id"] is None
    assert result["actual_external_delivery_enabled"] is False
    assert writes == []
    assert Path(result["artifact_paths"]["result_json"]).exists()
    assert Path(result["artifact_paths"]["summary_markdown"]).exists()


def test_publish_research_queue_commit_blocked_does_not_write_snapshot(monkeypatch, tmp_path):
    writes = []
    monkeypatch.setattr(research_queue_publish, "build_research_publication_package", lambda *args, **kwargs: _package("blocked"))
    monkeypatch.setattr(research_queue_publish, "record_publication_snapshot", lambda *args, **kwargs: writes.append(kwargs) or "never")

    result = research_queue_publish.publish_research_queue(
        "2026-07-03",
        commit_snapshot=True,
        confirm_internal_publication=True,
        output_dir=tmp_path,
    )

    assert result["status"] == "blocked"
    assert result["mode"] == "snapshot_commit"
    assert result["snapshot_written"] is False
    assert result["blockers"][0]["code"] == "pending_gap"
    assert writes == []


def test_publish_research_queue_commit_requires_confirm(monkeypatch, tmp_path):
    monkeypatch.setattr(research_queue_publish, "build_research_publication_package", lambda *args, **kwargs: _package("research_ready"))

    with pytest.raises(ValueError, match="confirm_internal_publication_required"):
        research_queue_publish.publish_research_queue(
            "2026-07-03",
            commit_snapshot=True,
            confirm_internal_publication=False,
            output_dir=tmp_path,
        )


def test_publish_research_queue_ready_dry_run_does_not_write_snapshot(monkeypatch, tmp_path):
    writes = []
    monkeypatch.setattr(research_queue_publish, "build_research_publication_package", lambda *args, **kwargs: _package("research_ready"))
    monkeypatch.setattr(research_queue_publish, "record_publication_snapshot", lambda *args, **kwargs: writes.append(kwargs) or "never")

    result = research_queue_publish.publish_research_queue(
        "2026-07-03",
        output_dir=tmp_path,
    )

    assert result["status"] == "dry_run_ready"
    assert result["publishable"] is True
    assert result["snapshot_written"] is False
    assert result["publication_snapshot_id"] is None
    assert result["warnings"][0]["code"] == "external_delivery_not_connected"
    assert writes == []


def test_publish_research_queue_ready_commit_records_internal_snapshot(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(research_queue_publish, "build_research_publication_package", lambda *args, **kwargs: _package("research_ready"))

    def fake_record(payload, service="research"):
        captured.update(payload)
        return "publication_snapshot:internal:abc"

    monkeypatch.setattr(research_queue_publish, "record_publication_snapshot", fake_record)
    monkeypatch.setattr(research_queue_publish, "publish_strategy_eod", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("strategy publish called")), raising=False)
    monkeypatch.setattr(research_queue_publish, "send_openclaw_feishu_message", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("notification called")), raising=False)

    result = research_queue_publish.publish_research_queue(
        "2026-07-03",
        commit_snapshot=True,
        confirm_internal_publication=True,
        output_dir=tmp_path,
    )

    assert result["status"] == "snapshot_recorded"
    assert result["snapshot_written"] is True
    assert result["publication_snapshot_id"] == "publication_snapshot:internal:abc"
    assert captured["channel"] == "research_queue_internal"
    assert captured["payload"]["package_id"] == "research_publication_package:research_ready"
    serialized = json.dumps(captured, ensure_ascii=False)
    assert "payload" not in captured["payload"]["sections"][0]["items"][0]
    assert "auto_trade" not in serialized
    assert "strategy_eod_publish" not in serialized


def test_research_queue_publish_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_publish(**kwargs):
        captured.update(kwargs)
        return {
            "trade_date": "2026-07-03",
            "run_id": "research_queue_publish:abc",
            "status": "blocked",
            "publishable": False,
            "snapshot_written": False,
            "artifact_paths": {},
        }

    monkeypatch.setattr(cli, "publish_research_queue", fake_publish)

    cli.main_for_args(
        [
            "research-queue-publish",
            "--trade-date",
            "2026-07-03",
            "--commit-snapshot",
            "--confirm-internal-publication",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-07-03"
    assert captured["commit_snapshot"] is True
    assert captured["confirm_internal_publication"] is True
    assert captured["dry_run"] is False
    assert captured["output_dir"] == tmp_path
