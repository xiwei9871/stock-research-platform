import json
from pathlib import Path

import pytest

from stock_research.p5.notifications import (
    P5NotificationError,
    P5FeishuSendConfig,
    P5FeishuSender,
    parse_p4_smoke_notification,
    write_p4_smoke_feishu_preview,
    write_p4_smoke_notification_artifacts,
)


def test_parse_p4_smoke_notification_maps_pass_to_ok() -> None:
    notification = parse_p4_smoke_notification(
        [
            "p4_read_model_smoke|status|pass|trade_date|2026-05-29|blockers|0|warnings|0",
            "p4_read_model_smoke_check|operator_export_files|pass",
            "p4_read_model_smoke_check|operator_export_row_counts|pass",
        ],
        source_command="stock-research p4-read-model-smoke --trade-date 2026-05-29",
    )

    assert notification["status"] == "pass"
    assert notification["severity"] == "ok"
    assert notification["trade_date"] == "2026-05-29"
    assert notification["blocker_count"] == 0
    assert notification["warning_count"] == 0
    assert notification["failed_checks"] == []
    assert notification["source_command"].endswith("--trade-date 2026-05-29")
    assert notification["message"] == (
        "[ok] P4 read-model smoke pass for 2026-05-29\n"
        "blockers: 0\n"
        "warnings: 0\n"
        "action: no immediate action"
    )


def test_parse_p4_smoke_notification_maps_warning_and_preserves_check_detail() -> None:
    notification = parse_p4_smoke_notification(
        [
            "p4_read_model_smoke|status|warning|trade_date|2026-05-29|blockers|0|warnings|1",
            "p4_read_model_smoke_check|operator_export_row_counts|warning|zero_count_datasets|review_runs",
            "p4_read_model_smoke_check|p2_review_run|pass",
        ],
        source_log_path="logs/p4_scheduler_daily.log",
    )

    assert notification["severity"] == "warning"
    assert notification["failed_checks"] == [
        {
            "name": "operator_export_row_counts",
            "status": "warning",
            "details": {"zero_count_datasets": "review_runs"},
        }
    ]
    assert notification["source_log_path"] == "logs/p4_scheduler_daily.log"
    assert "operator_export_row_counts: warning" in notification["message"]
    assert "zero_count_datasets=review_runs" in notification["message"]
    assert "action: review warning checks before trusting the scheduled run" in notification["message"]


def test_parse_p4_smoke_notification_maps_blocked_to_critical() -> None:
    notification = parse_p4_smoke_notification(
        [
            "p4_read_model_smoke|status|blocked|trade_date|2026-05-29|blockers|1|warnings|0",
            "p4_read_model_smoke_check|p2_review_run|blocked|latest_trade_date|2026-05-28",
            "p4_read_model_smoke_check|virtual_portfolio_state|pass",
        ],
    )

    assert notification["severity"] == "critical"
    assert notification["failed_checks"] == [
        {
            "name": "p2_review_run",
            "status": "blocked",
            "details": {"latest_trade_date": "2026-05-28"},
        }
    ]
    assert "[critical] P4 read-model smoke blocked for 2026-05-29" in notification["message"]
    assert "action: rerun P4 orchestration and investigate blocked checks" in notification["message"]


def test_parse_p4_smoke_notification_rejects_empty_or_malformed_output() -> None:
    with pytest.raises(P5NotificationError, match="missing p4_read_model_smoke status line"):
        parse_p4_smoke_notification([])

    with pytest.raises(P5NotificationError, match="malformed p4_read_model_smoke status line"):
        parse_p4_smoke_notification(["p4_read_model_smoke|status|pass|trade_date"])

    with pytest.raises(P5NotificationError, match="unsupported p4 smoke status"):
        parse_p4_smoke_notification(
            [
                "p4_read_model_smoke|status|unknown|trade_date|2026-05-29|blockers|0|warnings|0",
            ]
        )


def test_write_p4_smoke_notification_artifacts_are_dry_run_and_traceable(
    tmp_path: Path,
) -> None:
    result = write_p4_smoke_notification_artifacts(
        [
            "p4_read_model_smoke|status|blocked|trade_date|2026-05-29|blockers|1|warnings|0",
            "p4_read_model_smoke_check|p2_review_run|blocked|latest_trade_date|2026-05-28",
        ],
        output_dir=tmp_path / "p5",
        source_command="stock-research p4-read-model-smoke --trade-date 2026-05-29",
    )

    preview = json.loads(Path(result["preview_path"]).read_text(encoding="utf-8"))
    log_records = [
        json.loads(line)
        for line in Path(result["delivery_log_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert result["status"] == "dry_run"
    assert result["severity"] == "critical"
    assert result["item_count"] == 1
    assert preview["channel"] == "p5_p4_smoke_notification"
    assert preview["dry_run"] is True
    assert preview["trade_date"] == "2026-05-29"
    assert preview["notification"]["severity"] == "critical"
    assert preview["notification"]["source_command"].endswith("--trade-date 2026-05-29")
    assert "token" not in json.dumps(preview).lower()
    assert "webhook" not in json.dumps(preview).lower()
    assert log_records == [
        {
            "channel": "p5_p4_smoke_notification",
            "status": "dry_run",
            "dry_run": True,
            "trade_date": "2026-05-29",
            "severity": "critical",
            "item_count": 1,
            "preview_path": result["preview_path"],
        }
    ]


def test_write_p4_smoke_feishu_preview_maps_notification_to_single_text_payload(
    tmp_path: Path,
) -> None:
    notification_result = write_p4_smoke_notification_artifacts(
        [
            "p4_read_model_smoke|status|warning|trade_date|2026-05-29|blockers|0|warnings|1",
            "p4_read_model_smoke_check|operator_export_row_counts|warning|zero_count_datasets|review_runs",
        ],
        output_dir=tmp_path / "p5",
    )

    result = write_p4_smoke_feishu_preview(
        notification_result["preview_path"],
        output_dir=tmp_path / "feishu",
    )

    preview = json.loads(Path(result["preview_path"]).read_text(encoding="utf-8"))
    item = preview["items"][0]

    assert result["status"] == "dry_run"
    assert result["item_count"] == 1
    assert preview["channel"] == "feishu"
    assert preview["source_preview_path"] == notification_result["preview_path"]
    assert item["artifact_id"] == "p5_p4_smoke_notification:2026-05-29"
    assert item["report_type"] == "p4_smoke_notification"
    assert item["severity"] == "warning"
    assert item["operational_severity"] == "warning"
    assert item["requires_attention"] is True
    assert item["feishu_payload"]["msg_type"] == "text"
    assert "operator_export_row_counts: warning" in item["feishu_payload"]["content"]["text"]


class _FailingTransport:
    def send(self, payload, config):
        raise AssertionError("dry-run P5 sender must not invoke live transport")


def test_p5_feishu_sender_dry_run_writes_outbox_without_transport(tmp_path: Path) -> None:
    notification_result = write_p4_smoke_notification_artifacts(
        ["p4_read_model_smoke|status|pass|trade_date|2026-05-29|blockers|0|warnings|0"],
        output_dir=tmp_path / "p5",
    )
    feishu_result = write_p4_smoke_feishu_preview(
        notification_result["preview_path"],
        output_dir=tmp_path / "feishu",
    )

    result = P5FeishuSender(transport=_FailingTransport()).send_preview(
        preview_path=feishu_result["preview_path"],
        config=P5FeishuSendConfig(
            webhook_url=None,
            dry_run=True,
            outbox_dir=str(tmp_path / "outbox"),
            allow_live_send=False,
            limit=None,
            test_mode=False,
        ),
    )

    send_preview = json.loads(Path(result["send_preview_path"]).read_text(encoding="utf-8"))
    send_log = json.loads(Path(result["send_log_path"]).read_text(encoding="utf-8").splitlines()[0])

    assert result["status"] == "dry_run"
    assert result["sent_count"] == 0
    assert send_preview["dry_run"] is True
    assert send_preview["item_count"] == 1
    assert send_log["status"] == "dry_run"
    assert send_log["webhook_host"] == ""


class _RecordingTransport:
    def __init__(self) -> None:
        self.payloads = []

    def send(self, payload, config):
        self.payloads.append((payload, config))
        return {
            "status": "sent",
            "sent_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "warnings": [],
            "errors": [],
        }


def test_p5_feishu_sender_requires_live_safety_gates(tmp_path: Path) -> None:
    notification_result = write_p4_smoke_notification_artifacts(
        ["p4_read_model_smoke|status|blocked|trade_date|2026-05-29|blockers|1|warnings|0"],
        output_dir=tmp_path / "p5",
    )
    feishu_result = write_p4_smoke_feishu_preview(
        notification_result["preview_path"],
        output_dir=tmp_path / "feishu",
    )
    sender = P5FeishuSender(transport=_RecordingTransport())

    with pytest.raises(ValueError, match="allow_live_send must be True"):
        sender.send_preview(
            preview_path=feishu_result["preview_path"],
            config=P5FeishuSendConfig(
                webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/super-secret",
                dry_run=False,
                outbox_dir=str(tmp_path / "outbox"),
                allow_live_send=False,
                limit=1,
                test_mode=True,
            ),
        )


def test_p5_feishu_sender_can_send_single_live_test_message(tmp_path: Path) -> None:
    notification_result = write_p4_smoke_notification_artifacts(
        ["p4_read_model_smoke|status|blocked|trade_date|2026-05-29|blockers|1|warnings|0"],
        output_dir=tmp_path / "p5",
    )
    feishu_result = write_p4_smoke_feishu_preview(
        notification_result["preview_path"],
        output_dir=tmp_path / "feishu",
    )
    transport = _RecordingTransport()

    result = P5FeishuSender(transport=transport).send_preview(
        preview_path=feishu_result["preview_path"],
        config=P5FeishuSendConfig(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/super-secret",
            dry_run=False,
            outbox_dir=str(tmp_path / "outbox"),
            allow_live_send=True,
            limit=1,
            test_mode=True,
        ),
    )

    send_log = [
        json.loads(line)
        for line in Path(result["send_log_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert result["status"] == "sent"
    assert result["sent_count"] == 1
    assert len(transport.payloads) == 1
    assert transport.payloads[0][0]["webhook_host"] == "open.feishu.cn"
    assert transport.payloads[0][0]["items"][0]["severity"] == "critical"
    assert send_log[0]["status"] == "sent"
    assert send_log[0]["webhook_host"] == "open.feishu.cn"
