from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path

import pytest

from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairRunSummary,
    RepairStatus,
)


def _report_module():
    return importlib.import_module("stock_research.eod_auto_repair_report")


def _publication(strategy_id: str) -> dict[str, object]:
    return {
        "strategyId": strategy_id,
        "tradeDate": "2026-07-20",
        "publishId": f"{strategy_id}-publish",
        "contractId": f"{strategy_id}:balanced:v1",
        "publishStartedAt": "2026-07-20T08:00:00+00:00",
        "artifactVersion": "strategy-publication/v1",
        "totalReturnPct": 12.5,
    }


def _summary(
    *,
    status: RepairStatus = RepairStatus.SUCCESS,
    message: str = "ready",
    artifact_paths: list[str] | None = None,
) -> RepairRunSummary:
    run_id = "strategy-eod-2026-07-20-local"
    browser = RepairActionResult(
        "dashboard_browser_acceptance",
        RepairStatus.DEGRADED if status == RepairStatus.DEGRADED else status,
        message,
        metrics={"run_id": run_id},
        artifact_paths=list(artifact_paths or []),
        validation_result={
            "evidence": {
                "candidate_publications": [
                    _publication(strategy_id)
                    for strategy_id in ("lhb_shortline", "mid_trend", "tech_bottleneck")
                ],
                "report_paths": list(artifact_paths or []),
                "parsed_result": {
                    "run_id": run_id,
                    "status": "degraded" if status == RepairStatus.DEGRADED else status.value,
                    "attempts": [
                        {"attempt_number": 1, "status": "failed", "message": "runtime retry"},
                        {"attempt_number": 2, "status": "success", "message": "rerun passed"},
                    ],
                },
            }
        },
    )
    blockers = ["dashboard_browser_acceptance"] if status in {RepairStatus.FAILED, RepairStatus.BLOCKED} else []
    return RepairRunSummary(
        trade_date="2026-07-20",
        mode="loop",
        final_status=status,
        checks_before=[RepairCheckResult("data_stage", RepairStatus.SUCCESS, "data ready")],
        actions=[browser],
        checks_after=[
            RepairCheckResult(
                "dashboard_browser_acceptance",
                browser.status,
                message,
                blocker=bool(blockers),
            )
        ],
        remaining_blockers=blockers,
        loop_stop_reason="ready_with_no_blockers" if not blockers else "blocked",
    )


@pytest.mark.parametrize(
    ("status", "banner"),
    [
        (RepairStatus.SUCCESS, "official"),
        (RepairStatus.FAILED, "blocked"),
        (RepairStatus.DEGRADED, "degraded"),
    ],
)
def test_html_report_uses_only_canonical_status_banners(tmp_path, status, banner):
    report = _report_module()

    html = report.render_html_report(_summary(status=status), tmp_path)

    assert f'data-status="{banner}"' in html
    assert "data-status=\"success\"" not in html


def test_report_escapes_html_and_renders_canonical_browser_evidence(tmp_path):
    report = _report_module()
    evidence = tmp_path / "browser" / "attempt-2" / "trace.zip"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"trace")
    summary = _summary(
        message='<script>alert("x")</script>',
        artifact_paths=[str(evidence), "../outside/secret.zip"],
    )

    html = report.render_html_report(summary, tmp_path)
    markdown = report.render_markdown_report(summary, tmp_path)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "browser/attempt-2/trace.zip" in html
    assert "../outside" not in html
    assert "trace.zip" not in html.replace("browser/attempt-2/trace.zip", "")
    assert "strategy-eod-2026-07-20-local" in markdown
    assert "lhb_shortline-publish" in markdown
    assert "mid_trend-publish" in markdown
    assert "tech_bottleneck-publish" in markdown
    assert "Attempt 1" in markdown and "Attempt 2" in markdown
    assert "rerun passed" in markdown


def test_report_rendering_is_deterministic_for_same_summary(tmp_path):
    report = _report_module()
    summary = _summary()

    assert report.render_markdown_report(summary, tmp_path) == report.render_markdown_report(summary, tmp_path)
    assert report.render_html_report(summary, tmp_path) == report.render_html_report(summary, tmp_path)
    assert report.summary_json_bytes(summary) == report.summary_json_bytes(summary)


def test_html_failure_preserves_json_markdown_and_returns_failed_summary(tmp_path):
    report = _report_module()
    (tmp_path / "run_report.html").write_text("stale official report", encoding="utf-8")

    def fail_html(_summary, _output_dir):
        raise OSError("html unavailable")

    result = report.write_summary_files(
        _summary(),
        tmp_path,
        html_renderer=fail_html,
    )

    assert (tmp_path / "run_summary.json").stat().st_size > 0
    assert (tmp_path / "run_report.md").stat().st_size > 0
    assert not (tmp_path / "run_report.html").exists()
    assert result.final_status == RepairStatus.FAILED
    assert any("html" in issue for issue in result.infrastructure_issues)
    payload = json.loads((tmp_path / "run_summary.json").read_text())
    assert payload["final_status"] == "failed"
    assert payload["infrastructure_issues"]
    assert os.stat(tmp_path / "run_summary.json").st_mode & 0o777 == 0o600
    assert os.stat(tmp_path / "run_report.md").st_mode & 0o777 == 0o600


def test_writer_rejects_symlink_output_directory(tmp_path):
    report = _report_module()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_output = tmp_path / "linked-output"
    linked_output.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        report.write_summary_files(_summary(), linked_output)

    assert list(outside.iterdir()) == []


def _write_retention_summary(path: Path, *, status: str, run_id: str = "run-1", **extra):
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "trade_date": path.name,
        "final_status": status,
        "remaining_blockers": [] if status == "success" else ["blocked"],
        "browser_acceptance": {"action": {"metrics": {"run_id": run_id}}},
        **extra,
    }
    (path / "run_summary.json").write_text(json.dumps(payload), encoding="utf-8")
    (path / "browser").mkdir()
    (path / "run_report.md").write_text("report", encoding="utf-8")
    (path / "run_report.html").write_text("report", encoding="utf-8")


def test_retention_removes_only_old_official_and_preserves_safety_boundaries(tmp_path):
    report = _report_module()
    root = tmp_path / "daily"
    outside = tmp_path / "outside"
    outside.mkdir()
    _write_retention_summary(root / "2026-04-20", status="success")
    _write_retention_summary(root / "2026-04-21", status="success")  # exactly 90 days
    _write_retention_summary(root / "2026-04-19", status="failed")
    _write_retention_summary(root / "2026-04-18", status="degraded")
    _write_retention_summary(root / "2026-04-17", status="success", run_id="pv-initial-baseline")
    _write_retention_summary(root / "2026-04-16", status="success", trusted_initial_baseline=True)
    _write_retention_summary(root / "2026-07-20", status="success")
    (root / "not-a-date").mkdir()
    (root / "2026-04-15").symlink_to(outside, target_is_directory=True)

    removed = report.prune_report_retention(
        root,
        current_run_dir=root / "2026-07-20",
        now=datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
    )

    assert removed == [root / "2026-04-20"]
    assert not (root / "2026-04-20").exists()
    for name in (
        "2026-04-21",
        "2026-04-19",
        "2026-04-18",
        "2026-04-17",
        "2026-04-16",
        "2026-07-20",
        "not-a-date",
        "2026-04-15",
    ):
        assert (root / name).exists() or (root / name).is_symlink()


def test_retention_dry_run_reports_candidate_without_deleting(tmp_path):
    report = _report_module()
    root = tmp_path / "daily"
    target = root / "2026-04-20"
    _write_retention_summary(target, status="success")

    removed = report.prune_report_retention(
        root,
        current_run_dir=root / "2026-07-20",
        now=datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
        dry_run=True,
    )

    assert removed == [target]
    assert target.exists()
