from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from stock_research import cli as root_cli
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1 import cli


PROJECT = "ai_compute_pcb_industry_bottleneck"
VERSION = "0.1.0"


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    exit_code = cli.run_research_project_v2_1_cli(argv)
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def test_help_lists_all_eleven_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.run_research_project_v2_1_cli(["--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    for command in (
        "list", "show", "validate", "gate", "search-plan", "discover",
        "snapshot", "parse", "assess", "audit", "rebuild-index",
    ):
        assert command in output


def test_root_cli_delegates_raw_argv_before_main_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(
        root_cli,
        "run_research_project_v2_1_cli",
        lambda argv: seen.append(argv) or 37,
    )
    assert root_cli.main(["research-project-v2-1", "list"]) == 37
    assert seen == [["list"]]


def test_list_show_validate_gate_and_search_plan_are_deterministic_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, listed = _run(["list"], capsys)
    assert code == 0
    assert [row["project_slug"] for row in listed["projects"]] == sorted(
        row["project_slug"] for row in listed["projects"]
    )
    assert all(row["research_layer"] == "industry_research" for row in listed["projects"])

    code, shown = _run(
        ["show", "--project", PROJECT, "--version", VERSION], capsys
    )
    assert code == 0
    assert shown["version_id"] == f"research_version:{PROJECT}:{VERSION}"

    code, validated = _run(["validate", "--all"], capsys)
    assert code == 0
    assert validated["status"] == "pass"
    assert len(validated["validated"]) == 4

    code, gate = _run(
        [
            "gate", "--project", PROJECT, "--version", VERSION,
            "--gate", "industry-design",
        ],
        capsys,
    )
    assert code == 0
    assert gate["status"] == "pass"
    assert gate["verified"] is True

    code, plans = _run(
        ["search-plan", "--project", PROJECT, "--version", VERSION], capsys
    )
    assert code == 0
    assert plans["status"] == "pass"
    assert plans["coverage"]["uncovered_requirement_ids"] == []


@pytest.mark.parametrize(
    ("error_code", "expected"),
    [
        ("RESEARCH_PROJECT_V2_1_SCHEMA_INVALID", 2),
        ("RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID", 3),
        ("RESEARCH_PROJECT_V2_1_GATE_FAILED", 4),
        ("RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION", 5),
        ("RESEARCH_PROJECT_V2_1_VERSION_NOT_FOUND", 6),
        ("RESEARCH_PROJECT_V2_1_DISCOVERY_PROVIDER_FAILED", 8),
        ("RESEARCH_PROJECT_V2_1_PARSE_INVALID", 9),
    ],
)
def test_domain_errors_have_stable_json_and_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_code: str,
    expected: int,
) -> None:
    monkeypatch.setattr(
        cli,
        "_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ResearchProjectV2Error("boom", code=error_code, details={"z": 1})
        ),
    )
    code, payload = _run(["list"], capsys)
    assert code == expected
    assert payload == {
        "error": {"code": error_code, "details": {"z": 1}, "message": "boom"}
    }


def test_unexpected_error_is_runtime_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_dispatch", lambda *_: 1 / 0)
    code, payload = _run(["list"], capsys)
    assert code == 10
    assert payload["error"]["code"] == "RESEARCH_PROJECT_V2_1_RUNTIME_ERROR"
    assert payload["error"]["details"] == {"exception_type": "ZeroDivisionError"}


def test_domain_error_details_with_paths_remain_json_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_dispatch",
        lambda *_: (_ for _ in ()).throw(
            ResearchProjectV2Error(
                "unsafe",
                code="RESEARCH_PROJECT_V2_1_PATH_VIOLATION",
                details={"path": Path("evidence/raw")},
            )
        ),
    )
    code, payload = _run(["list"], capsys)
    assert code == 5
    assert payload["error"]["details"]["path"] == "evidence/raw"


def test_invalid_cli_arguments_use_schema_exit_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, payload = _run(["show", "--project", PROJECT], capsys)
    assert code == 2
    assert payload["error"]["code"] == "RESEARCH_PROJECT_V2_1_CLI_ARGUMENT_INVALID"


def test_discover_preview_does_not_write_and_write_returns_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "plan.json"
    results_path = tmp_path / "results.json"
    plan_path.write_text(json.dumps({"search_plan_id": "search_plan:test"}), encoding="utf-8")
    results_path.write_text(json.dumps({"results": []}), encoding="utf-8")
    batch = {"search_plan_id": "search_plan:test", "candidates": [], "content_hash": "a" * 64}
    monkeypatch.setattr(cli, "_discover", lambda *_args, **_kwargs: batch)
    writes: list[dict] = []
    monkeypatch.setattr(cli, "write_discovery_batch", lambda value: writes.append(value) or Path("saved.json"))

    code, preview = _run(
        ["discover", "--search-plan", str(plan_path), "--results", str(results_path)], capsys
    )
    assert code == 0 and preview["written"] is False and writes == []
    code, written = _run(
        ["discover", "--search-plan", str(plan_path), "--results", str(results_path), "--write"], capsys
    )
    assert code == 0 and written["written"] is True and writes == [batch]


def test_gate_failure_and_audit_failure_use_distinct_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_gate", lambda *_: {"status": "fail", "checks": []})
    code, _ = _run(
        ["gate", "--project", PROJECT, "--version", VERSION, "--gate", "industry-design"], capsys
    )
    assert code == 4
    monkeypatch.setattr(cli, "_audit", lambda *_: {"status": "fail", "findings": ["x"]})
    code, _ = _run(["audit", "--project", PROJECT, "--version", VERSION], capsys)
    assert code == 3


def test_snapshot_result_paths_are_json_safe_and_preview_paths_are_not_claimed_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidate_id": "source_candidate:" + "a" * 24,
                "provenance": {"created_at": "2026-07-18T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "snapshot_candidate",
        lambda *_args, **_kwargs: {
            "artifact": {"artifact_id": "evidence_artifact:" + "b" * 24},
            "raw_path": Path("raw/file.html"),
            "metadata_path": Path("metadata/file.json"),
        },
    )
    code, payload = _run(["snapshot", "--candidate", str(candidate_path)], capsys)
    assert code == 0
    assert payload["written"] is False
    assert payload["raw_path"] is None
    assert payload["metadata_path"] is None


def test_invalid_assessment_is_semantic_validation_exit_two(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_dispatch",
        lambda *_: (_ for _ in ()).throw(
            ResearchProjectV2Error(
                "invalid assessment",
                code="RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID",
            )
        ),
    )
    code, _ = _run(["list"], capsys)
    assert code == 2


def test_parse_missing_artifact_uses_not_found_exit_six(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, payload = _run(
        ["parse", "--artifact-id", "evidence_artifact:" + "0" * 24], capsys
    )
    assert code == 6
    assert payload["error"]["code"] == "RESEARCH_PROJECT_V2_1_ARTIFACT_NOT_FOUND"


def test_audit_reports_missing_raw_metadata_document_and_assessment_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = cli.LayeredResearchLayout(tmp_path / "v2_1")
    artifact_id = "evidence_artifact:" + "1" * 24
    document_id = "normalized_document:" + "2" * 24
    assessment_id = "industry_evidence_assessment:" + "3" * 24
    version = {
        "snapshot": {
            "evidence_requirements": [],
            "search_plans": [],
            "evidence_artifacts": [
                {
                    "artifact_id": artifact_id,
                    "raw_path": "evidence/raw/00/" + "0" * 64 + ".html",
                    "content_sha256": "0" * 64,
                }
            ],
            "normalized_documents": [
                {"document_id": document_id, "artifact_id": artifact_id, "sections": []}
            ],
            "industry_evidence_assessments": [
                {
                    "assessment_id": assessment_id,
                    "artifact_id": artifact_id,
                    "normalized_document_id": document_id,
                    "locator": "html:p[1]",
                }
            ],
        }
    }
    monkeypatch.setattr(cli, "load_layered_project", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cli, "load_industry_version", lambda *_args, **_kwargs: version)
    monkeypatch.setattr(cli, "validate_search_plans", lambda *_args: None)
    monkeypatch.setattr(
        cli,
        "evaluate_industry_design_gate",
        lambda *_args, **_kwargs: {"status": "pass", "verified": True},
    )
    args = argparse.Namespace(project="p", version="0.1.0")
    payload = cli._audit(args, layout)
    assert payload["status"] == "fail"
    assert {finding["code"] for finding in payload["findings"]} >= {
        "RAW_ARTIFACT_NOT_FOUND",
        "ARTIFACT_METADATA_NOT_FOUND",
        "NORMALIZED_DOCUMENT_NOT_FOUND",
        "ASSESSMENT_NOT_FOUND",
        "LOCATOR_NOT_FOUND",
    }
