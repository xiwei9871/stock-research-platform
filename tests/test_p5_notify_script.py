import json
import subprocess
from pathlib import Path


def test_run_p5_notify_p4_smoke_script_writes_notification_and_feishu_preview(
    tmp_path: Path,
) -> None:
    smoke_log = tmp_path / "p4_smoke.log"
    smoke_log.write_text(
        "\n".join(
            [
                "p4_read_model_smoke|status|blocked|trade_date|2026-05-29|blockers|1|warnings|0",
                "p4_read_model_smoke_check|p2_review_run|blocked|latest_trade_date|2026-05-28",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/run_p5_notify_p4_smoke.py",
            "--smoke-log",
            str(smoke_log),
            "--output-dir",
            str(tmp_path / "p5"),
            "--source-command",
            "stock-research p4-read-model-smoke --trade-date 2026-05-29",
            "--feishu-preview",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = completed.stdout.splitlines()
    assert lines[0].startswith(
        "p5_p4_smoke_notification|status|dry_run|trade_date|2026-05-29|severity|critical"
    )
    assert lines[1].startswith(
        "p5_p4_smoke_feishu_preview|status|dry_run|trade_date|2026-05-29|items|1"
    )

    notification_preview = tmp_path / "p5" / "p5_p4_smoke_notification_preview.json"
    feishu_preview = tmp_path / "p5" / "feishu" / "p5_p4_smoke_feishu_preview.json"
    assert notification_preview.exists()
    assert feishu_preview.exists()
    assert json.loads(notification_preview.read_text(encoding="utf-8"))["severity"] == "critical"
    assert json.loads(feishu_preview.read_text(encoding="utf-8"))["items"][0]["severity"] == "critical"


def test_p4_scheduler_wrapper_has_disabled_p5_notification_hook() -> None:
    script = Path("scripts/run_p4_scheduler_daily.sh").read_text(encoding="utf-8")

    assert 'P5_NOTIFY="${P5_NOTIFY:-0}"' in script
    assert "run_p5_notify_p4_smoke.py" in script
    assert "P5_NOTIFY_FEISHU_PREVIEW" in script
    assert "p4_scheduler_wrapper|p5_notify|disabled" in script
