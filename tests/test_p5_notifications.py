import json
from pathlib import Path

import pytest

from stock_research.p5.notifications import (
    P5NotificationError,
    parse_p4_smoke_notification,
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
