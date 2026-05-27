from __future__ import annotations

import json
from pathlib import Path

import pytest

import stock_research.report_delivery_feishu as report_delivery_feishu


def _artifact(
    *,
    artifact_id: str,
    report_type: str,
    title: str,
    severity: str = "info",
    recommended_channels: list[str] | None = None,
    requires_attention: bool = False,
) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "report_type": report_type,
        "title": title,
        "trade_date": "2026-05-25",
        "generated_at": "2026-05-25T08:00:00Z",
        "markdown_path": f"artifacts/{artifact_id}.md",
        "json_path": f"artifacts/{artifact_id}.json",
        "csv_paths": [f"artifacts/{artifact_id}.csv"],
        "run_card_path": f"artifacts/{artifact_id}_run_card.json",
        "evidence_dir": f"artifacts/{artifact_id}_evidence",
        "warnings": [],
        "severity": severity,
        "summary": f"{title} summary",
        "tags": [report_type],
        "recommended_channels": list(recommended_channels or ["local"]),
        "requires_attention": requires_attention,
        "delivery_priority": 10,
        "metadata": {},
    }


def _write_manifest(tmp_path: Path, artifacts: list[dict[str, object]]) -> Path:
    manifest = {
        "generated_at": "2026-05-25T08:10:00Z",
        "trade_date": "2026-05-25",
        "channel": "local",
        "artifact_count": len(artifacts),
        "report_types": sorted({str(artifact["report_type"]) for artifact in artifacts}),
        "requires_attention_count": sum(1 for artifact in artifacts if artifact["requires_attention"]),
        "high_severity_count": sum(
            1 for artifact in artifacts if artifact["severity"] in {"high", "critical"}
        ),
        "artifacts": artifacts,
        "warnings": [],
        "errors": [],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def test_feishu_dry_run_selects_feishu_or_attention_artifacts(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                artifact_id="watchlist",
                report_type="watchlist_report",
                title="Watchlist",
                recommended_channels=["local", "feishu"],
            ),
            _artifact(
                artifact_id="risk",
                report_type="risk_alert_report",
                title="Risk Alert",
                severity="high",
                recommended_channels=["local"],
                requires_attention=True,
            ),
            _artifact(
                artifact_id="archive",
                report_type="generic_report",
                title="Archive",
                recommended_channels=["local"],
            ),
        ],
    )

    adapter = report_delivery_feishu.FeishuDryRunAdapter()
    result = adapter.render_preview(manifest_path, output_dir=tmp_path / "feishu")

    preview = json.loads(Path(result.preview_path).read_text(encoding="utf-8"))
    log_record = json.loads(Path(result.delivery_log_path).read_text(encoding="utf-8").splitlines()[0])

    assert result.status == "dry_run"
    assert result.item_count == 2
    assert [item["artifact_id"] for item in preview["items"]] == ["watchlist", "risk"]
    assert preview["channel"] == "feishu"
    assert preview["dry_run"] is True
    assert "token" not in json.dumps(preview).lower()
    assert log_record["channel"] == "feishu"
    assert log_record["status"] == "dry_run"
    assert log_record["item_count"] == 2


def test_feishu_dry_run_items_include_feishu_text_payload(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                artifact_id="daily_topn",
                report_type="daily_topn_report",
                title="Daily TopN",
                severity="medium",
                recommended_channels=["local", "feishu"],
                requires_attention=True,
            ),
        ],
    )

    result = report_delivery_feishu.FeishuDryRunAdapter().render_preview(
        manifest_path,
        output_dir=tmp_path / "feishu",
    )

    preview = json.loads(Path(result.preview_path).read_text(encoding="utf-8"))
    item = preview["items"][0]

    assert preview["message_count"] == 1
    assert item["feishu_payload"] == {
        "msg_type": "text",
        "content": {
            "text": (
                "[medium] Daily TopN\n"
                "type: daily_topn_report\n"
                "action: attention required\n"
                "summary: Daily TopN summary\n"
                "artifact_id: daily_topn\n"
                "paths: artifacts/daily_topn.md, artifacts/daily_topn.json, "
                "artifacts/daily_topn_run_card.json, artifacts/daily_topn_evidence, "
                "artifacts/daily_topn.csv"
            )
        },
    }


def test_feishu_dry_run_include_all_and_min_severity(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                artifact_id="info",
                report_type="generic_report",
                title="Info",
                severity="info",
                recommended_channels=["local", "feishu"],
            ),
            _artifact(
                artifact_id="medium",
                report_type="generic_report",
                title="Medium",
                severity="medium",
                recommended_channels=["local"],
            ),
            _artifact(
                artifact_id="critical",
                report_type="risk_alert_report",
                title="Critical",
                severity="critical",
                recommended_channels=["local"],
            ),
        ],
    )

    result = report_delivery_feishu.FeishuDryRunAdapter().render_preview(
        manifest_path,
        output_dir=tmp_path / "feishu",
        include_all=True,
        min_severity="medium",
    )

    preview = json.loads(Path(result.preview_path).read_text(encoding="utf-8"))

    assert result.item_count == 2
    assert [item["artifact_id"] for item in preview["items"]] == ["medium", "critical"]


def test_feishu_dry_run_rejects_invalid_manifest_shape(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"artifacts": {}}\n', encoding="utf-8")

    with pytest.raises(report_delivery_feishu.FeishuManifestError, match="artifacts.*list"):
        report_delivery_feishu.FeishuDryRunAdapter().render_preview(
            manifest_path,
            output_dir=tmp_path / "feishu",
        )


def _write_feishu_preview(tmp_path: Path, *, severity: str = "info") -> Path:
    preview_path = tmp_path / "feishu_preview.json"
    preview_path.write_text(
        json.dumps(
            {
                "channel": "feishu",
                "status": "dry_run",
                "dry_run": True,
                "generated_at": "2026-05-28T08:00:00Z",
                "trade_date": "2026-05-28",
                "source_manifest_path": "outputs/report_delivery/2026-05-28/manifest.json",
                "item_count": 1,
                "message_count": 1,
                "items": [
                    {
                        "artifact_id": "daily_topn",
                        "report_type": "daily_topn_report",
                        "title": "Daily TopN",
                        "summary": "Daily TopN summary",
                        "severity": severity,
                        "requires_attention": False,
                        "delivery_priority": 10,
                        "message": "[info] Daily TopN",
                        "feishu_payload": {
                            "msg_type": "text",
                            "content": {"text": "[info] Daily TopN"},
                        },
                        "source_paths": ["outputs/report_delivery/2026-05-28/artifacts/topn.md"],
                    }
                ],
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return preview_path


class _FailingFeishuTransport:
    def __init__(self) -> None:
        self.calls = 0

    def send(self, payload: dict[str, object], config: object) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("dry_run sender must not invoke live Feishu transport")


def test_feishu_sender_dry_run_writes_preview_and_log_without_live_transport(tmp_path: Path) -> None:
    preview_path = _write_feishu_preview(tmp_path)
    transport = _FailingFeishuTransport()
    config = report_delivery_feishu.FeishuSendConfig(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/super-secret",
        dry_run=True,
        outbox_dir=str(tmp_path / "send"),
        limit=None,
        allow_live_send=False,
        severity_max=None,
        test_mode=False,
    )

    result = report_delivery_feishu.FeishuSender(transport=transport).send_preview(
        preview_path=preview_path,
        config=config,
    )

    assert result.status == "dry_run"
    assert result.item_count == 1
    assert result.sent_count == 0
    assert transport.calls == 0
    send_preview_text = Path(result.send_preview_path).read_text(encoding="utf-8")
    send_log_text = Path(result.send_log_path).read_text(encoding="utf-8")
    assert "super-secret" not in send_preview_text
    assert "super-secret" not in send_log_text
    assert "open.feishu.cn" in send_log_text


def test_feishu_live_send_requires_safety_gate(tmp_path: Path) -> None:
    preview_path = _write_feishu_preview(tmp_path)
    config = report_delivery_feishu.FeishuSendConfig(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/super-secret",
        dry_run=False,
        outbox_dir=str(tmp_path / "send"),
        limit=1,
        allow_live_send=False,
        severity_max="info",
        test_mode=True,
    )

    with pytest.raises(ValueError, match="allow_live_send"):
        report_delivery_feishu.FeishuSender(
            transport=report_delivery_feishu.FakeFeishuTransport()
        ).send_preview(preview_path=preview_path, config=config)


def test_feishu_fake_transport_can_simulate_live_send(tmp_path: Path) -> None:
    preview_path = _write_feishu_preview(tmp_path)
    config = report_delivery_feishu.FeishuSendConfig(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/super-secret",
        dry_run=False,
        outbox_dir=str(tmp_path / "send"),
        limit=1,
        allow_live_send=True,
        severity_max="info",
        test_mode=True,
    )

    result = report_delivery_feishu.FeishuSender(
        transport=report_delivery_feishu.FakeFeishuTransport()
    ).send_preview(preview_path=preview_path, config=config)

    assert result.status == "sent"
    assert result.item_count == 1
    assert result.sent_count == 1
    send_log_records = [
        json.loads(line)
        for line in Path(result.send_log_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert send_log_records[0]["channel"] == "feishu"
    assert send_log_records[0]["webhook_host"] == "open.feishu.cn"
    assert send_log_records[1]["artifact_id"] == "daily_topn"
