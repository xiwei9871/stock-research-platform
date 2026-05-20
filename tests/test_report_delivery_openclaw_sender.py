from __future__ import annotations

import json
from pathlib import Path

import pytest

import stock_research.report_delivery_openclaw_sender as report_delivery_openclaw_sender


def _write_export(tmp_path: Path) -> tuple[Path, Path]:
    manifest_path = tmp_path / "openclaw_manifest.json"
    items_path = tmp_path / "openclaw_items.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-21T09:00:00Z",
                "trade_date": "2026-05-20",
                "channel": "openclaw",
                "dry_run": True,
                "source_manifest_path": "outputs/report_delivery/2026-05-20/manifest.json",
                "item_count": 1,
                "items": [],
                "warnings": [],
                "errors": [],
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    items_path.write_text(
        json.dumps(
            {
                "item_id": "openclaw:1",
                "artifact_id": "daily_topn_report:2026-05-20:abc",
                "report_type": "daily_topn_report",
                "title": "Daily TopN",
                "summary": "Daily TopN summary",
                "severity": "info",
                "requires_attention": False,
                "delivery_priority": 10,
                "tags": ["daily", "topn"],
                "source_paths": ["outputs/report_delivery/2026-05-20/artifacts/topn.md"],
                "evidence_paths": [],
                "run_card_path": None,
                "recommended_action": "review_topn_candidates",
                "openclaw_route": "daily_research",
                "payload": {"title": "Daily TopN"},
            },
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path, items_path


def test_openclaw_sender_dry_run_writes_preview_and_log(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint=None,
        token=None,
        timeout_seconds=5,
        dry_run=True,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=None,
        allow_live_send=False,
        route_allowlist=[],
        severity_max=None,
        test_mode=False,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.DryRunOpenClawTransport()
    )

    result = sender.send_batch(
        manifest_path=manifest_path,
        items_path=items_path,
        config=config,
    )

    assert result.dry_run is True
    assert result.item_count == 1
    assert result.sent_count == 0
    assert result.failed_count == 0
    assert result.skipped_count == 0
    assert Path(result.preview_path).exists()
    assert Path(result.send_log_path).exists()


def test_openclaw_sender_no_dry_run_without_endpoint_fails_clearly(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint=None,
        token=None,
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=None,
        allow_live_send=False,
        route_allowlist=[],
        severity_max=None,
        test_mode=False,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.HttpOpenClawTransport()
    )

    with pytest.raises(ValueError, match="endpoint is required when dry_run is False"):
        sender.send_batch(
            manifest_path=manifest_path,
            items_path=items_path,
            config=config,
        )
