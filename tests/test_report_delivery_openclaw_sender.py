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


def _write_export_with_multiple_items(tmp_path: Path) -> tuple[Path, Path]:
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
                "item_count": 3,
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
        "\n".join(
            [
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
                ),
                json.dumps(
                    {
                        "item_id": "openclaw:2",
                        "artifact_id": "factor_eval_report:2026-05-20:def",
                        "report_type": "factor_eval_report",
                        "title": "Factor Eval",
                        "summary": "Factor eval summary",
                        "severity": "high",
                        "requires_attention": False,
                        "delivery_priority": 20,
                        "tags": ["factor", "eval"],
                        "source_paths": ["outputs/report_delivery/2026-05-20/artifacts/factor.md"],
                        "evidence_paths": [],
                        "run_card_path": None,
                        "recommended_action": "review_factor_eval",
                        "openclaw_route": "research_validation",
                        "payload": {"title": "Factor Eval"},
                    },
                    ensure_ascii=True,
                ),
                json.dumps(
                    {
                        "item_id": "openclaw:3",
                        "artifact_id": "risk_alert_report:2026-05-20:ghi",
                        "report_type": "risk_alert_report",
                        "title": "Risk Alert",
                        "summary": "Risk alert summary",
                        "severity": "critical",
                        "requires_attention": True,
                        "delivery_priority": 30,
                        "tags": ["risk", "alert"],
                        "source_paths": ["outputs/report_delivery/2026-05-20/artifacts/risk.md"],
                        "evidence_paths": [],
                        "run_card_path": None,
                        "recommended_action": "review_risk_alert",
                        "openclaw_route": "research_alert",
                        "payload": {"title": "Risk Alert"},
                    },
                    ensure_ascii=True,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path, items_path


def _write_export_with_unknown_severity_item(tmp_path: Path) -> tuple[Path, Path]:
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
                "artifact_id": "generic_report:2026-05-20:xyz",
                "report_type": "generic_report",
                "title": "Generic Report",
                "summary": "Generic summary",
                "severity": "mystery",
                "requires_attention": False,
                "delivery_priority": 10,
                "tags": ["generic"],
                "source_paths": ["outputs/report_delivery/2026-05-20/artifacts/generic.md"],
                "evidence_paths": [],
                "run_card_path": None,
                "recommended_action": "review_report",
                "openclaw_route": "daily_research",
                "payload": {"title": "Generic Report"},
            },
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path, items_path


def _write_export_with_mixed_severity_items(tmp_path: Path) -> tuple[Path, Path]:
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
                "item_count": 2,
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
        "\n".join(
            [
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
                ),
                json.dumps(
                    {
                        "item_id": "openclaw:2",
                        "artifact_id": "generic_report:2026-05-20:xyz",
                        "report_type": "generic_report",
                        "title": "Generic Report",
                        "summary": "Generic summary",
                        "severity": "mystery",
                        "requires_attention": False,
                        "delivery_priority": 10,
                        "tags": ["generic"],
                        "source_paths": ["outputs/report_delivery/2026-05-20/artifacts/generic.md"],
                        "evidence_paths": [],
                        "run_card_path": None,
                        "recommended_action": "review_report",
                        "openclaw_route": "daily_research",
                        "payload": {"title": "Generic Report"},
                    },
                    ensure_ascii=True,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path, items_path


class _FailingNonDryTransport:
    def __init__(self) -> None:
        self.calls = 0

    def send(self, payload: dict[str, object], config: object) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("dry_run sender must not invoke non-dry transport")


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


def test_preview_does_not_retain_raw_endpoint_string(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    endpoint = "https://tenant-123.openclaw.example.test/send?secret=abc"
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint=endpoint,
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

    preview_text = Path(result.preview_path).read_text(encoding="utf-8")
    preview_record = json.loads(preview_text)

    assert preview_record["endpoint_host"] == "tenant-123.openclaw.example.test"
    assert "endpoint" not in preview_record
    assert endpoint not in preview_text


def test_openclaw_sender_dry_run_does_not_invoke_non_dry_transport(tmp_path: Path) -> None:
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
    transport = _FailingNonDryTransport()
    sender = report_delivery_openclaw_sender.OpenClawSender(transport=transport)

    result = sender.send_batch(
        manifest_path=manifest_path,
        items_path=items_path,
        config=config,
    )

    assert result.dry_run is True
    assert transport.calls == 0


def test_fake_transport_can_simulate_success() -> None:
    transport = report_delivery_openclaw_sender.FakeOpenClawTransport()
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint="https://openclaw.example.test/send",
        token="token",
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir="/tmp/openclaw-send",
        limit=1,
        allow_live_send=True,
        route_allowlist=["daily_research"],
        severity_max="info",
        test_mode=True,
    )

    result = transport.send(
        {
            "items": [
                {
                    "item_id": "openclaw:1",
                    "payload": {
                        "openclaw_transport_result": "success",
                    },
                }
            ]
        },
        config,
    )

    assert result["status"] == "sent"
    assert result["sent_count"] == 1
    assert result["failed_count"] == 0
    assert result["item_results"] == [{"item_id": "openclaw:1", "status": "sent"}]


def test_fake_transport_can_simulate_partial_failure() -> None:
    transport = report_delivery_openclaw_sender.FakeOpenClawTransport()
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint="https://openclaw.example.test/send",
        token="token",
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir="/tmp/openclaw-send",
        limit=2,
        allow_live_send=True,
        route_allowlist=["daily_research"],
        severity_max="info",
        test_mode=True,
    )

    result = transport.send(
        {
            "items": [
                {
                    "item_id": "openclaw:1",
                    "payload": {
                        "openclaw_transport_result": "success",
                    },
                },
                {
                    "item_id": "openclaw:2",
                    "payload": {
                        "openclaw_transport_result": "failure",
                        "openclaw_transport_error": "simulated transport failure",
                    },
                },
            ]
        },
        config,
    )

    assert result["status"] == "partial_failure"
    assert result["sent_count"] == 1
    assert result["failed_count"] == 1
    assert result["item_results"] == [
        {"item_id": "openclaw:1", "status": "sent"},
        {
            "item_id": "openclaw:2",
            "status": "failed",
            "error": "simulated transport failure",
        },
    ]


def test_send_log_excludes_token_and_auth_headers(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint="https://openclaw.example.test/send",
        token="super-secret-token",
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=1,
        allow_live_send=True,
        route_allowlist=["daily_research"],
        severity_max="info",
        test_mode=True,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.FakeOpenClawTransport()
    )

    result = sender.send_batch(
        manifest_path=manifest_path,
        items_path=items_path,
        config=config,
    )

    send_log_text = Path(result.send_log_path).read_text(encoding="utf-8")
    send_log_record = json.loads(send_log_text)

    assert send_log_record["endpoint_host"] == "openclaw.example.test"
    assert "endpoint" not in send_log_record
    assert "super-secret-token" not in send_log_text
    assert "Authorization" not in send_log_text


def test_live_send_with_zero_deliverable_items_fails_clearly(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint="https://openclaw.example.test/send",
        token="token",
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=1,
        allow_live_send=True,
        route_allowlist=["research_validation"],
        severity_max="info",
        test_mode=True,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.FakeOpenClawTransport()
    )

    with pytest.raises(ValueError, match="at least one deliverable item after filtering"):
        sender.send_batch(
            manifest_path=manifest_path,
            items_path=items_path,
            config=config,
        )


def test_dry_run_transport_never_accesses_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_network_access(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry-run transport must not access the network")

    monkeypatch.setattr("socket.create_connection", _fail_network_access)

    transport = report_delivery_openclaw_sender.DryRunOpenClawTransport()
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint=None,
        token=None,
        timeout_seconds=5,
        dry_run=True,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir="/tmp/openclaw-send",
        limit=None,
        allow_live_send=False,
        route_allowlist=[],
        severity_max=None,
        test_mode=False,
    )

    result = transport.send({"items": []}, config)

    assert result["dry_run"] is True
    assert result["status"] == "dry_run"


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


def test_live_send_requires_allow_live_send(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint="https://openclaw.example.test/send",
        token="token",
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=1,
        allow_live_send=False,
        route_allowlist=["daily_research"],
        severity_max="info",
        test_mode=True,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.HttpOpenClawTransport()
    )

    with pytest.raises(ValueError, match="allow_live_send"):
        sender.send_batch(
            manifest_path=manifest_path,
            items_path=items_path,
            config=config,
        )


def test_live_send_requires_limit_one(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint="https://openclaw.example.test/send",
        token="token",
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=2,
        allow_live_send=True,
        route_allowlist=["daily_research"],
        severity_max="info",
        test_mode=True,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.HttpOpenClawTransport()
    )

    with pytest.raises(ValueError, match="limit == 1"):
        sender.send_batch(
            manifest_path=manifest_path,
            items_path=items_path,
            config=config,
        )


def test_live_send_rejects_severity_max_critical(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint="https://openclaw.example.test/send",
        token="token",
        timeout_seconds=5,
        dry_run=False,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=1,
        allow_live_send=True,
        route_allowlist=["daily_research"],
        severity_max="critical",
        test_mode=True,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.HttpOpenClawTransport()
    )

    with pytest.raises(ValueError, match="severity_max.*critical"):
        sender.send_batch(
            manifest_path=manifest_path,
            items_path=items_path,
            config=config,
        )


def test_route_allowlist_filters_items(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export_with_multiple_items(tmp_path)
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
        route_allowlist=["research_validation"],
        severity_max="critical",
        test_mode=False,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.DryRunOpenClawTransport()
    )

    payload = sender.build_send_payload(sender.load_export(manifest_path, items_path), config)

    assert payload["item_count"] == 1
    assert [item["openclaw_route"] for item in payload["items"]] == ["research_validation"]


def test_severity_max_filters_items(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export_with_multiple_items(tmp_path)
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
        route_allowlist=["daily_research", "research_validation", "research_alert"],
        severity_max="medium",
        test_mode=False,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.DryRunOpenClawTransport()
    )

    payload = sender.build_send_payload(sender.load_export(manifest_path, items_path), config)

    assert payload["item_count"] == 1
    assert [item["severity"] for item in payload["items"]] == ["info"]


def test_build_send_payload_excludes_unknown_severity_items_under_cap(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export_with_mixed_severity_items(tmp_path)
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
        route_allowlist=["daily_research"],
        severity_max="info",
        test_mode=False,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.DryRunOpenClawTransport()
    )

    payload = sender.build_send_payload(sender.load_export(manifest_path, items_path), config)

    assert payload["item_count"] == 1
    assert [item["severity"] for item in payload["items"]] == ["info"]


def test_test_mode_marks_payload_metadata(tmp_path: Path) -> None:
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
        test_mode=True,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.DryRunOpenClawTransport()
    )

    payload = sender.build_send_payload(sender.load_export(manifest_path, items_path), config)

    assert payload["payload"]["metadata"] == {
        "source": "stock_research_openclaw_smoke_test",
        "test_mode": True,
    }


def test_live_send_rejects_unknown_severity_item(tmp_path: Path) -> None:
    manifest_path, items_path = _write_export_with_unknown_severity_item(tmp_path)
    config = report_delivery_openclaw_sender.OpenClawSendConfig(
        endpoint=None,
        token=None,
        timeout_seconds=5,
        dry_run=True,
        retry_count=0,
        retry_backoff_seconds=0,
        outbox_dir=str(tmp_path / "send"),
        limit=1,
        allow_live_send=False,
        route_allowlist=["daily_research"],
        severity_max="info",
        test_mode=False,
    )
    sender = report_delivery_openclaw_sender.OpenClawSender(
        transport=report_delivery_openclaw_sender.DryRunOpenClawTransport()
    )

    payload = sender.build_send_payload(sender.load_export(manifest_path, items_path), config)

    assert payload["item_count"] == 0
    assert payload["items"] == []
