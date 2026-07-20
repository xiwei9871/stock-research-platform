from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from stock_research.research_project_v2_1 import cli


PROJECT = "ai_compute_pcb_industry_bottleneck"
VERSION = "0.2.1"


def run(argv, capsys):
    code = cli.run_research_project_v2_1_cli(argv)
    captured = capsys.readouterr()
    assert captured.err == ""
    return code, json.loads(captured.out)


def test_help_exposes_one_acquisition_command_group(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.run_research_project_v2_1_cli(["--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "acquisition" in output


def test_acquisition_doctor_dry_run_is_machine_readable_and_non_mutating(capsys) -> None:
    code, payload = run(
        [
            "acquisition",
            "doctor",
            "--project",
            PROJECT,
            "--version",
            VERSION,
            "--dry-run",
        ],
        capsys,
    )
    assert code == 0
    assert payload["status"] == "pass"
    assert payload["written"] is False
    assert payload["provider_diagnostic"]["direct_html_status"] == "not_run"


def test_acquisition_smoke_is_not_run_without_explicit_online_flag(capsys) -> None:
    code, payload = run(
        [
            "acquisition",
            "smoke",
            "--project",
            PROJECT,
            "--version",
            VERSION,
            "--dry-run",
        ],
        capsys,
    )
    assert code == 0
    assert payload == {
        "status": "not_run",
        "reason": "online acquisition smoke requires separate Phase C approval",
    }


def test_acquisition_fetch_returns_nonzero_for_structured_blocked_attempt(
    tmp_path, monkeypatch, capsys
) -> None:
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidate_id": "source_candidate:blocked",
                "provenance": {
                    "created_by": "Codex",
                    "actor_type": "codex",
                    "agent_run_id": "run:blocked-cli",
                    "created_at": "2026-07-21T00:00:00Z",
                    "created_in_version": f"research_version:{PROJECT}:{VERSION}",
                    "review_status": "unreviewed",
                },
            }
        ),
        encoding="utf-8",
    )

    class BlockedProvider:
        def acquire(self, *_args, **_kwargs):
            return SimpleNamespace(
                attempt={"status": "blocked", "failure_code": "security_policy_blocked"},
                artifact=None,
            )

    monkeypatch.setattr(cli, "DirectHttpProvider", BlockedProvider)
    code, payload = run(
        [
            "acquisition",
            "fetch",
            "--project",
            PROJECT,
            "--version",
            VERSION,
            "--requirement",
            "requirement:ai_compute_pcb_industry_bottleneck:r2b_er01",
            "--candidate",
            str(candidate_path),
            "--proxy-mode",
            "direct",
        ],
        capsys,
    )
    assert code == 8
    assert payload["acquisition_attempt"]["failure_code"] == "security_policy_blocked"
