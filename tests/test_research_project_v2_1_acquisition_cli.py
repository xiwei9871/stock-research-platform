from __future__ import annotations

import json

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
