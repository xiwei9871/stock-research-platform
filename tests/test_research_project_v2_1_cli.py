from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from stock_research import cli as root_cli
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2_1 import cli
from stock_research.research_project_v2_1.discovery import source_candidate_id
from stock_research.research_project_v2_1.snapshot import FetchResponse
from stock_research.research_project_v2_1.snapshot import evidence_artifact_id_for_event


PROJECT = "ai_compute_pcb_industry_bottleneck"
VERSION = "0.1.0"


def _stored_provenance() -> dict:
    return {
        "created_by": "test",
        "actor_type": "automated_pipeline",
        "agent_run_id": "run:test",
        "created_at": "2026-07-19T00:00:00Z",
        "created_in_version": "research_version:test:0.1.0",
        "review_status": "unreviewed",
    }


def _stored_artifact(raw: bytes = b"x") -> dict:
    digest = sha256(raw).hexdigest()
    candidate_id = "source_candidate:" + "a" * 24
    artifact = {
        "candidate_id": candidate_id,
        "evidence_channel": "industry",
        "original_url": "https://example.com/source.txt",
        "final_url": "https://example.com/source.txt",
        "redirect_chain": [],
        "status_code": 200,
        "response_headers": {"content-type": "text/plain"},
        "media_type": "text/plain",
        "byte_count": len(raw),
        "content_sha256": digest,
        "fetched_at": "2026-07-19T00:00:00Z",
        "raw_path": f"evidence/raw/{digest[:2]}/{digest}.txt",
        "provenance": _stored_provenance(),
    }
    return {"artifact_id": evidence_artifact_id_for_event(artifact), **artifact}


def _stored_document(artifact_id: str, locator: str) -> dict:
    section = {
        "section_id": f"section:{artifact_id}:0001",
        "heading": None,
        "locator": locator,
        "text": "x",
        "page_start": None,
        "page_end": None,
    }
    section["section_hash"] = content_sha256(
        {key: section[key] for key in ("heading", "locator", "text")}
    )
    core = {
        "artifact_id": artifact_id,
        "parser": "text",
        "parser_version": "1.0.0",
        "media_type": "text/plain",
        "title": None,
        "sections": [section],
        "warnings": [],
        "parsed_at": "2026-07-19T00:01:00Z",
        "provenance": _stored_provenance(),
    }
    digest = content_sha256(core)
    identity = sha256(f"{artifact_id}\n{digest}".encode()).hexdigest()[:24]
    return {
        "document_id": f"normalized_document:{identity}",
        **core,
        "document_hash": digest,
    }


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


def test_cognition_commands_are_read_only_deterministic_projections(
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = Path("artifacts/research_projects/v2_1")
    package = base / "analysis/ai_pcb_industry_cognition_package_v1.json"
    audit = base / "analysis/ai_pcb_industry_cognition_audit_v1.json"
    report = base / "reports/ai_pcb_industry_cognition_report_v1.md"

    for command in ("validate", "show", "audit"):
        code, payload = _run(
            [
                "cognition",
                command,
                "--package",
                str(package),
                "--report",
                str(report),
                "--audit",
                str(audit),
            ],
            capsys,
        )
        assert code == 0
        assert payload["status"] == "pass"

    code = cli.run_research_project_v2_1_cli(
        [
            "cognition",
            "render",
            "--package",
            str(package),
            "--report",
            str(report),
            "--audit",
            str(audit),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert captured.out.encode("utf-8") == report.read_bytes()


def test_cognition_cli_runs_full_scope_validation_before_projection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_scope(*args: object, **kwargs: object) -> dict:
        raise ResearchProjectV2Error(
            "scope violation",
            code="RESEARCH_PROJECT_V2_1_COGNITION_SCOPE_VIOLATION",
        )

    monkeypatch.setattr(cli, "validate_cognition_package", reject_scope)
    base = Path("artifacts/research_projects/v2_1")
    code = cli.run_research_project_v2_1_cli(
        [
            "cognition",
            "validate",
            "--package",
            str(base / "analysis/ai_pcb_industry_cognition_package_v1.json"),
            "--report",
            str(base / "reports/ai_pcb_industry_cognition_report_v1.md"),
            "--audit",
            str(base / "analysis/ai_pcb_industry_cognition_audit_v1.json"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 4
    assert payload["error"]["code"] == "RESEARCH_PROJECT_V2_1_COGNITION_SCOPE_VIOLATION"


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
    expected_version_count = sum(
        len(cli.list_layered_versions(row["project_slug"]))
        for row in listed["projects"]
    )
    assert len(validated["validated"]) == expected_version_count

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
    ("argv", "error_code", "expected"),
    [
        (["validate", "--all"], "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID", 2),
        (
            ["gate", "--project", PROJECT, "--version", VERSION, "--gate", "industry-design"],
            "RESEARCH_PROJECT_V2_1_GATE_FAILED",
            4,
        ),
        (["show", "--project", PROJECT, "--version", VERSION], "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION", 5),
        (["show", "--project", PROJECT, "--version", VERSION], "RESEARCH_PROJECT_V2_1_VERSION_NOT_FOUND", 6),
        (["discover", "--search-plan", "p", "--results", "r"], "RESEARCH_PROJECT_V2_1_DISCOVERY_PROVIDER_FAILED", 8),
        (["parse", "--artifact-id", "evidence_artifact:" + "0" * 24], "RESEARCH_PROJECT_V2_1_PARSE_INVALID", 9),
    ],
)
def test_domain_errors_have_stable_json_and_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
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
    code, payload = _run(argv, capsys)
    assert code == expected
    assert payload == {
        "error": {"code": error_code, "details": {"z": 1}, "message": "boom"}
    }


@pytest.mark.parametrize(
    ("command", "error_code", "expected"),
    [
        ("validate", "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID", 2),
        ("gate", "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID", 4),
        ("gate", "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID", 2),
        ("gate", "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID", 2),
        ("gate", "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION", 5),
        ("audit", "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID", 3),
        ("assess", "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID", 2),
        ("parse", "RESEARCH_PROJECT_V2_1_NORMALIZE_STORAGE_FAILED", 10),
        ("discover", "RESEARCH_PROJECT_V2_1_DISCOVERY_PLAN_INVALID", 8),
        ("snapshot", "RESEARCH_PROJECT_V2_1_FETCH_DNS_ERROR", 8),
        ("snapshot", "RESEARCH_PROJECT_V2_1_SNAPSHOT_STORAGE_FAILED", 10),
        ("snapshot", "RESEARCH_PROJECT_V2_1_SNAPSHOT_IMMUTABILITY_VIOLATION", 5),
        ("snapshot", "RESEARCH_PROJECT_V2_1_SNAPSHOT_PATH_VIOLATION", 5),
        ("discover", "RESEARCH_PROJECT_V2_1_DISCOVERY_IMMUTABILITY_VIOLATION", 5),
        ("discover", "RESEARCH_PROJECT_V2_1_DISCOVERY_PATH_VIOLATION", 5),
        ("discover", "RESEARCH_PROJECT_V2_1_DISCOVERY_STORAGE_FAILED", 10),
        ("assess", "RESEARCH_PROJECT_V2_1_EVIDENCE_STORAGE_FAILED", 10),
        ("assess", "RESEARCH_PROJECT_V2_1_EVIDENCE_PATH_VIOLATION", 5),
        ("parse", "RESEARCH_PROJECT_V2_1_PARSE_UNSUPPORTED_MEDIA", 9),
        ("parse", "RESEARCH_PROJECT_V2_1_NORMALIZE_PATH_VIOLATION", 5),
        ("show", "RESEARCH_PROJECT_V2_1_STORAGE_ERROR", 5),
        ("list", "RESEARCH_PROJECT_V2_1_READ_ERROR", 10),
        ("validate", "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID", 2),
        ("search-plan", "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID", 3),
    ],
)
def test_exit_mapping_uses_explicit_code_and_command_context(
    command: str,
    error_code: str,
    expected: int,
) -> None:
    error = ResearchProjectV2Error("x", code=error_code)
    assert cli._exit_for_domain_error(error, command=command) == expected


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


def test_operations_use_new_clocked_provenance_not_upstream_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = {
        "search_plan_id": "search_plan:test",
        "provenance": {
            "created_by": "old",
            "actor_type": "codex",
            "agent_run_id": "old-run",
            "created_at": "2025-01-01T00:00:00Z",
            "created_in_version": "research_version:test:0.1.0",
            "review_status": "pending_review",
        },
    }
    plan_path = tmp_path / "plan.json"
    results_path = tmp_path / "results.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    results_path.write_text(json.dumps({"results": []}), encoding="utf-8")
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "ImportedJsonDiscoveryProvider", lambda _path: object())

    def fake_discover(_plan, _provider, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(cli, "discover_sources", fake_discover)
    clock = lambda: datetime(2026, 7, 19, 8, 9, 10, tzinfo=timezone.utc)
    assert cli._discover(
        str(plan_path), str(results_path), clock=clock, agent_run_id=None
    ) == {"ok": True}
    assert captured["discovered_at"] == "2026-07-19T08:09:10Z"
    provenance = captured["provenance"]
    assert provenance["created_at"] == "2026-07-19T08:09:10Z"
    assert provenance["agent_run_id"].startswith("research-project-v2-1-cli:discover:")
    assert provenance["created_in_version"] == "research_version:test:0.1.0"
    assert provenance["created_by"] != "old"


def test_explicit_operation_time_and_run_id_override_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = argparse.Namespace(
        candidate="unused.json",
        write=False,
        fetched_at="2026-07-19T09:00:00Z",
        agent_run_id="manual-run",
    )
    candidate = {
        "provenance": {
            "created_in_version": "research_version:test:0.1.0",
        }
    }
    monkeypatch.setattr(cli, "_read_json", lambda *_args, **_kwargs: candidate)
    monkeypatch.setattr(cli, "_unwrap", lambda payload, _key: payload)
    captured = {}

    def fake_snapshot(_candidate, **kwargs):
        captured.update(kwargs)
        return {
            "artifact": {},
            "raw_path": Path("raw"),
            "metadata_path": Path("metadata"),
        }

    monkeypatch.setattr(cli, "snapshot_candidate", fake_snapshot)
    monkeypatch.setattr(cli, "_temporary_layout", lambda: (None, cli.LayeredResearchLayout(Path("/tmp/x"))))
    cli._snapshot(
        args,
        clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    assert captured["fetched_at"] == "2026-07-19T09:00:00Z"
    assert captured["provenance"]["agent_run_id"] == "manual-run"
    assert captured["provenance"]["created_at"] == "2026-07-19T09:00:00Z"


def test_parse_uses_new_parse_time_and_operation_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = {
        "artifact_id": "evidence_artifact:" + "a" * 24,
        "provenance": _stored_provenance(),
    }
    monkeypatch.setattr(cli, "_artifact_from_metadata", lambda *_args: artifact)
    captured = {}

    def fake_normalize(_artifact, **kwargs):
        captured.update(kwargs)
        return {"document_id": "normalized_document:" + "b" * 24}

    monkeypatch.setattr(cli, "normalize_artifact", fake_normalize)
    args = argparse.Namespace(
        artifact_id=artifact["artifact_id"],
        write=False,
        parsed_at=None,
        agent_run_id=None,
    )
    cli._parse(
        args,
        cli.LayeredResearchLayout(Path("/tmp/unused")),
        clock=lambda: datetime(2026, 7, 19, 11, 0, tzinfo=timezone.utc),
    )
    assert captured["parsed_at"] == "2026-07-19T11:00:00Z"
    assert captured["provenance"]["created_at"] == "2026-07-19T11:00:00Z"
    assert captured["provenance"]["created_by"] == "research-project-v2-1-cli"


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
                "provenance": {
                    "created_at": "2026-07-18T00:00:00Z",
                    "created_in_version": "research_version:test:0.1.0",
                },
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


def test_snapshot_cli_wires_transport_resolver_and_closes_response_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://example.com/source.txt"
    title = "Industry source"
    candidate = {
        "candidate_id": source_candidate_id(url, title),
        "search_plan_id": "search_plan:test",
        "query_id": "query:test",
        "normalized_url": url,
        "original_url": url,
        "title": title,
        "snippet": "evidence",
        "publisher": "Example",
        "publish_date": "2026-07-19",
        "source_class": "primary",
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": url,
        "provenance": _stored_provenance(),
    }
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    closed = False

    def chunks():
        nonlocal closed
        try:
            yield b"evidence"
        finally:
            closed = True

    class FakeTransport:
        def get(self, requested_url: str, *, timeout_seconds: float):
            assert requested_url == url
            assert timeout_seconds == 20.0
            return FetchResponse(
                200,
                {"Content-Type": "text/plain"},
                chunks(),
                url,
                "93.184.216.34",
            )

    class FakeResolver:
        def resolve(self, hostname: str):
            assert hostname == "example.com"
            return ("93.184.216.34",)

    transport = FakeTransport()
    resolver = FakeResolver()
    monkeypatch.setattr(cli, "RequestsFetchTransport", lambda: transport)
    monkeypatch.setattr(cli, "SystemAddressResolver", lambda: resolver)
    args = argparse.Namespace(
        candidate=str(candidate_path),
        write=False,
        fetched_at="2026-07-19T10:00:00Z",
        agent_run_id="snapshot-wire-test",
    )
    result = cli._snapshot(args, clock=lambda: datetime.now(timezone.utc))
    assert result["status"] == "pass"
    assert result["written"] is False
    assert closed is True


def test_snapshot_cli_write_preserves_two_fetch_events_for_same_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://example.com/source.txt"
    title = "Industry source"
    candidate = {
        "candidate_id": source_candidate_id(url, title),
        "search_plan_id": "search_plan:test",
        "query_id": "query:test",
        "normalized_url": url,
        "original_url": url,
        "title": title,
        "snippet": "evidence",
        "publisher": "Example",
        "publish_date": "2026-07-19",
        "source_class": "primary",
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": url,
        "provenance": _stored_provenance(),
    }
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    class FakeTransport:
        def get(self, requested_url: str, *, timeout_seconds: float):
            return FetchResponse(
                200,
                {"Content-Type": "text/plain"},
                [b"evidence"],
                requested_url,
                "93.184.216.34",
            )

    class FakeResolver:
        def resolve(self, _hostname: str):
            return ("93.184.216.34",)

    effective = cli.LayeredResearchLayout((tmp_path / "managed").resolve())
    shutil.copytree(
        cli.LayeredResearchLayout.default().schema_dir,
        effective.schema_dir,
    )
    monkeypatch.setattr(
        cli.LayeredResearchLayout,
        "default",
        classmethod(lambda _cls: effective),
    )
    monkeypatch.setattr(cli, "RequestsFetchTransport", FakeTransport)
    monkeypatch.setattr(cli, "SystemAddressResolver", FakeResolver)
    first = cli._snapshot(
        argparse.Namespace(
            candidate=str(candidate_path),
            write=True,
            fetched_at="2026-07-19T12:00:00Z",
            agent_run_id="fetch:first",
        ),
        clock=lambda: datetime.now(timezone.utc),
    )
    second = cli._snapshot(
        argparse.Namespace(
            candidate=str(candidate_path),
            write=True,
            fetched_at="2026-07-19T13:00:00Z",
            agent_run_id="fetch:second",
        ),
        clock=lambda: datetime.now(timezone.utc),
    )
    assert first["artifact"]["artifact_id"] != second["artifact"]["artifact_id"]
    assert first["raw_path"] == second["raw_path"]
    assert first["metadata_path"] != second["metadata_path"]
    assert len(list(effective.evidence_metadata_dir.glob("*.json"))) == 2
    assert len(list(effective.evidence_raw_dir.rglob("*.txt"))) == 1


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
                        "byte_count": 0,
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
        "ARTIFACT_METADATA_INVALID",
        "NORMALIZED_DOCUMENT_NOT_FOUND",
        "ASSESSMENT_NOT_FOUND",
        "DOCUMENT_NOT_FOUND",
    }


def test_audit_validates_persisted_wrappers_and_uses_persisted_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = cli.LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _stored_artifact()
    snapshot_document = _stored_document(artifact["artifact_id"], "section:snapshot")
    persisted_document = deepcopy(snapshot_document)
    persisted_document["sections"][0]["locator"] = "section:persisted"
    assessment = {
        "assessment_id": "industry_evidence_assessment:" + "b" * 24,
        "artifact_id": artifact["artifact_id"],
        "normalized_document_id": snapshot_document["document_id"],
        "locator": "section:snapshot",
    }
    version = {
        "snapshot": {
            "evidence_requirements": [],
            "search_plans": [],
            "evidence_artifacts": [artifact],
            "normalized_documents": [snapshot_document],
            "industry_evidence_assessments": [assessment],
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
    monkeypatch.setattr(cli, "read_layered_bytes", lambda *_args, **_kwargs: b"x")

    def read_json(path, **_kwargs):
        path = str(path)
        if "metadata" in path:
            drifted = dict(artifact, artifact_id="evidence_artifact:" + "0" * 24)
            return {"schema_version": "2.1.0", "artifact_kind": "evidence_artifact", "evidence_artifact": drifted}
        if "normalized" in path:
            return {"schema_version": "2.1.0", "artifact_kind": "normalized_document", "normalized_document": persisted_document}
        return {"industry_evidence_assessment": assessment, "content_hash": "0" * 64}

    monkeypatch.setattr(cli, "read_layered_canonical_json", read_json)
    monkeypatch.setattr(cli, "validate_v2_1_schema_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "validate_industry_evidence_assessment", lambda wrapper: wrapper["industry_evidence_assessment"])
    payload = cli._audit(argparse.Namespace(project="p", version="0.1.0"), layout)
    codes = {finding["code"] for finding in payload["findings"]}
    assert payload["status"] == "fail"
    assert "ARTIFACT_METADATA_INVALID" in codes
    assert "NORMALIZED_DOCUMENT_NOT_FOUND" in codes
    assert "LOCATOR_UNVERIFIED" in codes


def test_audit_turns_corrupt_json_and_unsafe_parent_into_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = cli.LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _stored_artifact()
    version = {"snapshot": {"evidence_requirements": [], "search_plans": [], "evidence_artifacts": [artifact], "normalized_documents": [], "industry_evidence_assessments": []}}
    monkeypatch.setattr(cli, "load_layered_project", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cli, "load_industry_version", lambda *_args, **_kwargs: version)
    monkeypatch.setattr(cli, "validate_search_plans", lambda *_args: None)
    monkeypatch.setattr(cli, "evaluate_industry_design_gate", lambda *_args, **_kwargs: {"status": "pass", "verified": True})
    monkeypatch.setattr(cli, "read_layered_bytes", lambda *_args, **_kwargs: b"x")
    monkeypatch.setattr(
        cli,
        "read_layered_canonical_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ResearchProjectV2Error("corrupt", code="RESEARCH_PROJECT_V2_1_READ_ERROR")
        ),
    )
    payload = cli._audit(argparse.Namespace(project="p", version="0.1.0"), layout)
    assert payload["status"] == "fail"
    assert {row["code"] for row in payload["findings"]} == {"ARTIFACT_METADATA_INVALID"}
