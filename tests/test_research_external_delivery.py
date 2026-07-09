import json
from pathlib import Path

import pytest

from stock_research import cli
from stock_research import research_external_delivery


def _snapshot_detail() -> dict:
    return {
        "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
        "trade_date": "2026-07-06",
        "channel": "research_queue_internal",
        "title": "Research Queue Internal Snapshot 2026-07-06",
        "created_by": "research_queue_publish",
        "created_at": "2026-07-08T10:00:00+08:00",
        "package_id": "research_publication_package:abc",
        "gate": {
            "status": "research_ready",
            "research_ready_for_publication": True,
            "actual_publish_enabled": False,
            "internal_snapshot_enabled": True,
            "external_delivery_enabled": False,
        },
        "summary": {
            "case_count": 2,
            "claim_count": 3,
            "evidence_count": 4,
            "evidence_link_count": 5,
            "gap_count": 0,
            "reviewed_gap_count": 0,
            "pending_gap_count": 0,
            "request_more_evidence_count": 0,
            "deferred_gap_count": 0,
            "unmatched_digest_count": 0,
            "error_count": 0,
        },
        "sections": [
            {
                "section_type": "research_queue_summary",
                "title": "研究队列摘要",
                "items": [
                    {
                        "case_count": 2,
                        "claim_count": 3,
                        "payload": {"must_not": "leak"},
                        "internal_metadata": {"must_not": "leak"},
                        "webhook_url": "https://example.invalid/secret",
                    }
                ],
            }
        ],
        "blockers": [],
        "warnings": [{"code": "external_delivery_not_connected", "message": "External delivery is not connected", "count": 1}],
        "source_trace_summary": {
            "run_id": "research_queue_publish:abc",
            "channel": "research_queue_internal",
            "package_id": "research_publication_package:abc",
            "token": "secret",
        },
        "raw_payload": {"must_not": "leak"},
    }


def _assert_no_forbidden_fields(plan: dict) -> None:
    encoded = json.dumps(plan, ensure_ascii=False, sort_keys=True).lower()
    for forbidden in (
        "raw_payload",
        "payload",
        "internal_metadata",
        "webhook",
        "token",
        "secret",
        "auto_trade",
        "buy",
        "sell",
    ):
        assert forbidden not in encoded


def test_build_external_delivery_plan_from_snapshot_read_model(monkeypatch):
    monkeypatch.setattr(research_external_delivery, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: _snapshot_detail())

    plan = research_external_delivery.build_research_external_delivery_plan(
        "publication_snapshot:research_queue_internal:abc",
        channel="feishu_preview",
        service="research",
    )

    assert plan["status"] == "preview_ready"
    assert plan["delivery_plan_id"].startswith("research_external_delivery_plan:")
    assert plan["publication_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"
    assert plan["trade_date"] == "2026-07-06"
    assert plan["channel"] == "feishu_preview"
    assert plan["dry_run"] is True
    assert plan["external_send_enabled"] is False
    assert plan["message"]["title"] == "Research Queue Snapshot 2026-07-06"
    assert "Cases 2, claims 3, evidence 4, gaps 0" in plan["message"]["summary"]
    assert plan["message"]["sections"][0]["title"] == "研究队列摘要"
    assert plan["source"]["package_id"] == "research_publication_package:abc"
    assert plan["source"]["gate_status"] == "research_ready"
    assert plan["source"]["snapshot_channel"] == "research_queue_internal"
    assert "External delivery is not connected in this version." in plan["warnings"]
    _assert_no_forbidden_fields(plan)


@pytest.mark.parametrize("channel", ["feishu_preview", "email_preview", "markdown_export"])
def test_supported_delivery_channels_generate_preview(monkeypatch, channel):
    monkeypatch.setattr(research_external_delivery, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: _snapshot_detail())

    plan = research_external_delivery.build_research_external_delivery_plan(
        "publication_snapshot:research_queue_internal:abc",
        channel=channel,
        service="research",
    )

    assert plan["status"] == "preview_ready"
    assert plan["channel"] == channel
    assert plan["external_send_enabled"] is False


def test_unsupported_channel_returns_controlled_plan(monkeypatch):
    monkeypatch.setattr(research_external_delivery, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: _snapshot_detail())

    plan = research_external_delivery.build_research_external_delivery_plan(
        "publication_snapshot:research_queue_internal:abc",
        channel="live_feishu",
        service="research",
    )

    assert plan["status"] == "unsupported_channel"
    assert plan["external_send_enabled"] is False
    assert plan["message"]["sections"] == []


def test_snapshot_not_found_returns_controlled_plan(monkeypatch):
    monkeypatch.setattr(research_external_delivery, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: None)

    plan = research_external_delivery.build_research_external_delivery_plan(
        "publication_snapshot:missing",
        channel="feishu_preview",
        service="research",
    )

    assert plan["status"] == "snapshot_not_found"
    assert plan["external_send_enabled"] is False
    assert plan["message"]["title"] == ""


def test_delivery_plan_never_calls_notification_or_strategy_publish(monkeypatch):
    monkeypatch.setattr(research_external_delivery, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: _snapshot_detail())
    monkeypatch.setattr(
        research_external_delivery,
        "send_openclaw_feishu_message",
        lambda *args, **kwargs: pytest.fail("must not call Feishu sender"),
        raising=False,
    )
    monkeypatch.setattr(
        research_external_delivery,
        "publish_strategy_eod",
        lambda *args, **kwargs: pytest.fail("must not call strategy publish"),
        raising=False,
    )

    plan = research_external_delivery.build_research_external_delivery_plan(
        "publication_snapshot:research_queue_internal:abc",
        channel="feishu_preview",
        service="research",
    )

    assert plan["status"] == "preview_ready"


def test_run_external_delivery_plan_writes_json_and_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(research_external_delivery, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: _snapshot_detail())

    result = research_external_delivery.run_research_external_delivery_plan(
        publication_snapshot_id="publication_snapshot:research_queue_internal:abc",
        channel="feishu_preview",
        output_dir=tmp_path,
        service="research",
    )

    assert result["status"] == "preview_ready"
    assert result["dry_run"] is True
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
    persisted = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert persisted["external_send_enabled"] is False
    assert "External delivery is not connected" in Path(result["markdown_path"]).read_text(encoding="utf-8")


def test_external_delivery_boundary_report_written(tmp_path):
    path = research_external_delivery.write_external_delivery_boundary_report(tmp_path)

    content = Path(path).read_text(encoding="utf-8")
    assert "p5/notifications.py" in content
    assert "strategy_eod_publish.py" in content
    assert "dry-run" in content
    assert "External delivery must run after internal publication snapshot" in content


def test_external_delivery_plan_cli_wires_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": "preview_ready",
            "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
            "json_path": str(tmp_path / "research_external_delivery_plan.json"),
            "markdown_path": str(tmp_path / "research_external_delivery_plan.md"),
        }

    monkeypatch.setattr(cli, "run_research_external_delivery_plan", fake_run)

    cli.main_for_args(
        [
            "research-external-delivery-plan",
            "--publication-snapshot-id",
            "publication_snapshot:research_queue_internal:abc",
            "--channel",
            "feishu_preview",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["publication_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"
    assert captured["channel"] == "feishu_preview"
    assert captured["output_dir"] == tmp_path
    assert captured["dry_run"] is True
