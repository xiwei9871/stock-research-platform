from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

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


def _wave_a_theme_ids() -> set[str]:
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "theme_decomposition"
            / "batch_manifests"
            / "next_fifteen_industry_chain_themes_v1.json"
        ).read_text(encoding="utf-8")
    )
    return {
        manifest["themes"][chain_id]["theme_id"]
        for chain_id in manifest["waves"]["wave_a"]
    }


@pytest.mark.parametrize(
    "probe",
    [
        phase_verifier._verify_phase_1,
        phase_verifier._verify_phase_4,
        phase_verifier._verify_phase_6,
        phase_verifier._verify_phase_7,
    ],
)
def test_wave_a_rollout_gates_are_complete_for_canonical_packages(probe) -> None:
    assert probe()["status"] == "complete"


def test_phase_1_fails_when_theme_loader_drops_one_wave_a_theme(monkeypatch) -> None:
    missing_theme_id = sorted(_wave_a_theme_ids())[0]
    package = deepcopy(phase_verifier.load_theme_package())
    package["themes"] = [
        row for row in package["themes"] if row["theme_id"] != missing_theme_id
    ]
    monkeypatch.setattr(phase_verifier, "load_theme_package", lambda: package)

    result = phase_verifier._verify_phase_1()

    assert result["status"] == "failed"
    assert any(missing_theme_id in row["evidence"] for row in result["requirements"])


def test_phase_4_fails_when_mapping_loader_drops_one_wave_a_theme(monkeypatch) -> None:
    missing_theme_id = sorted(_wave_a_theme_ids())[0]
    package = deepcopy(phase_verifier.load_theme_company_mapping_package())
    package["company_mappings"] = [
        row
        for row in package["company_mappings"]
        if row["theme_id"] != missing_theme_id
    ]
    monkeypatch.setattr(
        phase_verifier,
        "load_theme_company_mapping_package",
        lambda: package,
    )

    result = phase_verifier._verify_phase_4()

    assert result["status"] == "failed"
    assert any(missing_theme_id in row["evidence"] for row in result["requirements"])


def test_phase_6_fails_when_priority_loader_drops_one_wave_a_theme(monkeypatch) -> None:
    missing_theme_id = sorted(_wave_a_theme_ids())[0]
    package = deepcopy(phase_verifier.load_theme_research_priority_package())
    package["node_priorities"] = [
        row
        for row in package["node_priorities"]
        if row["theme_id"] != missing_theme_id
    ]
    package["company_priorities"] = [
        row
        for row in package["company_priorities"]
        if row["theme_id"] != missing_theme_id
    ]
    monkeypatch.setattr(
        phase_verifier,
        "load_theme_research_priority_package",
        lambda: package,
    )

    result = phase_verifier._verify_phase_6()

    assert result["status"] == "failed"
    assert any(missing_theme_id in row["evidence"] for row in result["requirements"])


def test_phase_7_fails_when_dashboard_loader_drops_one_wave_a_theme(monkeypatch) -> None:
    missing_theme_id = sorted(_wave_a_theme_ids())[0]
    theme_package = deepcopy(phase_verifier.load_theme_package())
    theme_package["themes"] = [
        row
        for row in theme_package["themes"]
        if row["theme_id"] != missing_theme_id
    ]
    dashboard_payload = deepcopy(
        phase_verifier.list_theme_research_themes(read_source="artifact")
    )
    dashboard_payload["items"] = [
        row
        for row in dashboard_payload["items"]
        if row["theme_id"] != missing_theme_id
    ]
    dashboard_payload["total"] = len(dashboard_payload["items"])
    monkeypatch.setattr(phase_verifier, "load_theme_package", lambda: theme_package)
    monkeypatch.setattr(
        phase_verifier,
        "list_theme_research_themes",
        lambda *, read_source: dashboard_payload,
    )

    result = phase_verifier._verify_phase_7()

    assert result["status"] == "failed"
    assert any(missing_theme_id in row["evidence"] for row in result["requirements"])


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


def test_phase_2b_rejects_truthy_but_structurally_invalid_source_pack_files(
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

    assert result["status"] == "failed"
    assert any("artifact_version" in row["evidence"] for row in result["requirements"])


def _configure_valid_phase_2b_state(monkeypatch, tmp_path: Path) -> Path:
    canonical_root = phase_verifier.REPOSITORY_ROOT
    canonical_package = phase_verifier.load_theme_package()
    source_pack_root = tmp_path / "artifacts" / "theme_decomposition" / "source_packs"
    source_pack_root.mkdir(parents=True)
    for filename in (
        "humanoid_robotics_source_pack_v1.json",
        "humanoid_robotics_claim_review_v1.json",
        "humanoid_robotics_node_evidence_matrix_v1.json",
    ):
        shutil.copyfile(
            canonical_root / "artifacts" / "theme_decomposition" / "source_packs" / filename,
            source_pack_root / filename,
        )
    monkeypatch.setattr(phase_verifier, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(phase_verifier, "load_theme_package", lambda: canonical_package)
    return source_pack_root


def test_phase_2b_is_complete_for_canonical_valid_pack(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_valid_phase_2b_state(monkeypatch, tmp_path)

    result = phase_verifier._verify_phase_2b()

    assert result["status"] == "complete"
    assert all(row["status"] == "passed" for row in result["requirements"])


@pytest.mark.parametrize(
    ("filename", "mutation", "expected_error"),
    [
        (
            "humanoid_robotics_source_pack_v1.json",
            lambda payload: payload.update({"theme_id": "wrong_theme"}),
            "theme_id",
        ),
        (
            "humanoid_robotics_claim_review_v1.json",
            lambda payload: payload["claim_reviews"][0].update(
                {"accepted_source_ids": ["missing_source"]}
            ),
            "missing_source",
        ),
        (
            "humanoid_robotics_node_evidence_matrix_v1.json",
            lambda payload: payload["node_evidence_matrix"][0].update(
                {"node_id": "missing_node"}
            ),
            "node matrix",
        ),
    ],
)
def test_phase_2b_fails_for_cross_artifact_mismatch(
    monkeypatch,
    tmp_path: Path,
    filename: str,
    mutation,
    expected_error: str,
) -> None:
    source_pack_root = _configure_valid_phase_2b_state(monkeypatch, tmp_path)
    artifact = source_pack_root / filename
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    mutation(payload)
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    result = phase_verifier._verify_phase_2b()

    assert result["status"] == "failed"
    assert any(expected_error in row["evidence"] for row in result["requirements"])


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
