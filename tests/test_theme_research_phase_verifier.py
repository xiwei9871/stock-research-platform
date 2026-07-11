from __future__ import annotations

import json
from pathlib import Path

from stock_research import cli as stock_research_cli
from stock_research.theme_research_phase_verifier import (
    _runtime_privileges_are_constrained,
    build_verification_report,
    render_verification_markdown,
    verify_theme_research_phases,
    write_verification_report,
)


def _phase(phase: str, status: str) -> dict:
    return {
        "phase": phase,
        "title": f"Phase {phase}",
        "status": status,
        "requirements": [
            {
                "requirement": "sample requirement",
                "status": "passed" if status != "failed" else "failed",
                "evidence": "sample evidence",
            }
        ],
    }


def test_report_status_distinguishes_complete_declared_gap_and_failure() -> None:
    complete = build_verification_report([_phase("1", "complete")])
    declared = build_verification_report(
        [_phase("1", "complete"), _phase("2B", "declared_evidence_gap")]
    )
    failed = build_verification_report(
        [_phase("1", "complete"), _phase("4", "failed")]
    )

    assert complete["overall_status"] == "complete"
    assert declared["overall_status"] == "complete_with_declared_evidence_gap"
    assert failed["overall_status"] == "failed"
    assert failed["failed_phase_count"] == 1


def test_verifier_runs_real_phase_checks_with_injected_database_probe() -> None:
    report = verify_theme_research_phases(
        database_probe=lambda: {
            "phase": "9",
            "title": "Database productionization",
            "status": "complete",
            "requirements": [
                {
                    "requirement": "schema and package parity",
                    "status": "passed",
                    "evidence": "test database current and package matched",
                }
            ],
        }
    )

    assert report["overall_status"] == "complete_with_declared_evidence_gap"
    assert report["phase_count"] == 12
    by_phase = {row["phase"]: row for row in report["phases"]}
    assert by_phase["1"]["status"] == "complete"
    assert by_phase["2A"]["status"] == "complete"
    assert by_phase["2B"]["status"] == "declared_evidence_gap"
    assert by_phase["9"]["status"] == "complete"
    assert by_phase["10"]["status"] == "complete"
    assert by_phase["10"]["requirements"]


def test_report_writers_are_stable_and_machine_readable(tmp_path: Path) -> None:
    report = build_verification_report(
        [_phase("1", "complete"), _phase("2B", "declared_evidence_gap")]
    )

    paths = write_verification_report(report, tmp_path)

    stored = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert stored["overall_status"] == "complete_with_declared_evidence_gap"
    assert markdown == render_verification_markdown(report)
    assert "Phase 2B" in markdown
    assert "sample evidence" in markdown


def test_shared_cli_delegates_theme_research_verifier(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        stock_research_cli,
        "run_theme_research_phase_verifier_cli",
        lambda argv: calls.append(argv) or 0,
    )

    result = stock_research_cli.main_for_args(
        ["theme-research", "verify-p1-p10", "--output-dir", "/tmp/theme-report"]
    )

    assert result == 0
    assert calls == [["verify-p1-p10", "--output-dir", "/tmp/theme-report"]]


def test_runtime_privilege_check_allows_controlled_review_writes_only() -> None:
    allowed = {
        "can_select": True,
        "can_insert": True,
        "can_update": True,
        "can_delete": False,
        "can_truncate": False,
        "can_create_schema_objects": False,
        "history_update": False,
        "history_truncate": False,
        "snapshot_update": False,
        "snapshot_truncate": False,
    }

    assert _runtime_privileges_are_constrained(allowed) is True
    assert _runtime_privileges_are_constrained({**allowed, "can_delete": True}) is False
    assert _runtime_privileges_are_constrained({**allowed, "history_update": True}) is False
    assert _runtime_privileges_are_constrained({**allowed, "can_create_schema_objects": True}) is False
