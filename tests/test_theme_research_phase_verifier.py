from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_research import cli as stock_research_cli
from stock_research import theme_research_phase_verifier as phase_verifier
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

    assert report["overall_status"] == "complete"
    assert report["phase_count"] == 12
    by_phase = {row["phase"]: row for row in report["phases"]}
    assert by_phase["1"]["status"] == "complete"
    assert by_phase["2A"]["status"] == "complete"
    assert by_phase["2B"]["status"] == "complete"
    assert by_phase["4"]["status"] == "complete"
    assert by_phase["6"]["status"] == "complete"
    assert by_phase["7"]["status"] == "complete"
    assert by_phase["9"]["status"] == "complete"
    assert by_phase["10"]["status"] == "complete"
    assert by_phase["10"]["requirements"]


def _configure_phase_2b_state(
    monkeypatch,
    tmp_path: Path,
    *,
    present_file_count: int,
    theme_status: str,
) -> None:
    source_pack_root = tmp_path / "artifacts" / "theme_decomposition" / "source_packs"
    source_pack_root.mkdir(parents=True)
    filenames = [
        "humanoid_robotics_source_pack_v1.json",
        "humanoid_robotics_claim_review_v1.json",
        "humanoid_robotics_node_evidence_matrix_v1.json",
    ]
    for filename in filenames[:present_file_count]:
        (source_pack_root / filename).write_text(
            '{"items": ["evidence"]}', encoding="utf-8"
        )
    monkeypatch.setattr(phase_verifier, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        phase_verifier,
        "load_theme_package",
        lambda: {
            "themes": [
                {
                    "theme_id": "humanoid_robotics_head_to_toe_v1",
                    "status": theme_status,
                }
            ]
        },
    )


def test_phase_2b_is_complete_when_all_source_pack_files_are_valid_and_theme_reviewed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_phase_2b_state(
        monkeypatch,
        tmp_path,
        present_file_count=3,
        theme_status="reviewed",
    )

    result = phase_verifier._verify_phase_2b()

    assert result["status"] == "complete"
    assert all(row["status"] == "passed" for row in result["requirements"])


def test_phase_2b_declares_gap_when_all_source_pack_files_are_missing_and_theme_draft(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_phase_2b_state(
        monkeypatch,
        tmp_path,
        present_file_count=0,
        theme_status="draft",
    )

    result = phase_verifier._verify_phase_2b()

    assert result["status"] == "declared_evidence_gap"
    assert all(row["status"] == "declared_gap" for row in result["requirements"])


@pytest.mark.parametrize(
    ("present_file_count", "theme_status"),
    [(1, "reviewed"), (1, "draft"), (3, "draft"), (0, "reviewed")],
)
def test_phase_2b_fails_for_partial_or_status_mismatched_state(
    monkeypatch,
    tmp_path: Path,
    present_file_count: int,
    theme_status: str,
) -> None:
    _configure_phase_2b_state(
        monkeypatch,
        tmp_path,
        present_file_count=present_file_count,
        theme_status=theme_status,
    )

    result = phase_verifier._verify_phase_2b()

    assert result["status"] == "failed"
    assert any(row["status"] == "failed" for row in result["requirements"])


@pytest.mark.parametrize("file_content", ["not-json", "{}"])
def test_phase_2b_fails_when_a_present_source_pack_file_is_unreadable_or_empty(
    monkeypatch,
    tmp_path: Path,
    file_content: str,
) -> None:
    _configure_phase_2b_state(
        monkeypatch,
        tmp_path,
        present_file_count=3,
        theme_status="reviewed",
    )
    source_pack = (
        tmp_path
        / "artifacts"
        / "theme_decomposition"
        / "source_packs"
        / "humanoid_robotics_source_pack_v1.json"
    )
    source_pack.write_text(file_content, encoding="utf-8")

    result = phase_verifier._verify_phase_2b()

    assert result["status"] == "failed"
    assert any(row["status"] == "failed" for row in result["requirements"])


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
