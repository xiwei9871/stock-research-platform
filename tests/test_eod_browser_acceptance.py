from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import hashlib
from datetime import date, datetime, timezone

import pytest

from stock_research.eod_auto_repair_models import RepairStatus
from stock_research.eod_browser_acceptance import (
    BrowserAcceptanceError,
    classify_browser_failures,
    load_previous_official_publications,
    parse_browser_acceptance_report,
    run_browser_acceptance,
)
import stock_research.eod_browser_acceptance as acceptance


TRADE_DATE = "2026-07-20"
RUN_ID = "eod-20260720"
REVISION = "abc123"
GATE_IDS = (
    "candidate-consistency",
    "publication-consistency",
    "runtime-deep-links",
)
STRATEGY_IDS = ("lhb_shortline", "mid_trend", "tech_bottleneck")


def _publication(strategy_id: str, *, trade_date: str = TRADE_DATE, hour: int = 1):
    return {
        "strategyId": strategy_id,
        "tradeDate": trade_date,
        "totalReturnPct": 52.4 + hour,
        "contractId": f"{strategy_id}:balanced:v1",
        "publishId": f"{strategy_id}-publish-{trade_date}",
        "publishStartedAt": f"{trade_date}T{hour:02d}:00:00+00:00",
        "artifactVersion": "strategy-publication/v1",
    }


def _report(
    *,
    status: str = "success",
    run_id: str = RUN_ID,
    trade_date: str = TRADE_DATE,
    failures: list[str] | None = None,
    failed_gate: str | None = None,
    severity: str = "blocker-consistency",
):
    tests = []
    for gate_id in GATE_IDS:
        failed = gate_id == failed_gate
        tests.append(
            {
                "testId": f"test-{gate_id}",
                "title": f"@eod @eod-gate-{gate_id} gate {gate_id}",
                "projectName": "eod-chromium",
                "retry": 0,
                "status": "failed" if failed else "passed",
                "durationMs": 25,
                "failures": list(failures or []) if failed else [],
                "attachments": [],
                "severity": severity if failed else "blocker-consistency",
                "attemptHistory": [
                    {
                        "retry": 0,
                        "status": "failed" if failed else "passed",
                        "durationMs": 25,
                        "failures": list(failures or []) if failed else [],
                        "attachments": [],
                    }
                ],
            }
        )
    snapshot = {
        "schemaVersion": "playwright-eod-candidate-snapshot/v1",
        "tradeDate": trade_date,
        "publications": [
            _publication(strategy_id, trade_date=trade_date, hour=index + 1)
            for index, strategy_id in enumerate(STRATEGY_IDS)
        ],
    }
    snapshot_digest = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "schemaVersion": "playwright-eod-browser-acceptance/v1",
        "runId": run_id,
        "tradeDate": trade_date,
        "revision": REVISION,
        "startedAt": f"{trade_date}T08:00:00+00:00",
        "endedAt": f"{trade_date}T08:00:02+00:00",
        "durationSeconds": 2.0,
        "contractOnly": False,
        "status": status,
        "tests": tests,
        "failures": list(failures or []),
        "attachments": [
            {
                "test": "runtime",
                "retry": 0,
                "name": "trace",
                "contentType": "application/zip",
                "path": "test-results/eod/trace.zip",
            }
        ],
        "candidateSnapshot": snapshot,
        "candidateSnapshotSha256": snapshot_digest,
    }


def _write_report(path: Path, **kwargs) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_report(**kwargs)), encoding="utf-8")
    return path


def _previous_json():
    return {
        "schemaVersion": "playwright-eod-previous-publications/v1",
        "publications": [
            _publication(strategy_id, trade_date="2026-07-19", hour=index + 1)
            for index, strategy_id in enumerate(STRATEGY_IDS)
        ],
    }


def test_parse_report_accepts_success_and_collects_safe_artifacts(tmp_path):
    report_path = _write_report(tmp_path / "attempt-1" / "eod-browser-acceptance.json")

    result = parse_browser_acceptance_report(
        report_path,
        expected_run_id=RUN_ID,
        expected_trade_date=TRADE_DATE,
        exit_code=0,
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.snapshot["tradeDate"] == TRADE_DATE
    assert result.failure_classes == ()
    assert str(report_path) in result.artifact_paths
    assert "test-results/eod/trace.zip" in result.artifact_paths


def test_parse_report_maps_warning_only_failure_to_degraded(tmp_path):
    report_path = _write_report(
        tmp_path / "eod-browser-acceptance.json",
        status="degraded",
        failures=["optional chart label drift"],
        failed_gate=None,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["tests"].append(
        {
            "testId": "warning-test",
            "title": "@eod @warning optional chart",
            "projectName": "eod-chromium",
            "retry": 0,
            "status": "failed",
            "durationMs": 1,
            "failures": ["optional chart label drift"],
            "attachments": [],
            "severity": "warning",
            "attemptHistory": [],
        }
    )
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = parse_browser_acceptance_report(
        report_path,
        expected_run_id=RUN_ID,
        expected_trade_date=TRADE_DATE,
        exit_code=0,
    )

    assert result.status == RepairStatus.DEGRADED
    assert result.warnings == ("optional chart label drift",)


def test_parse_report_validates_digest_against_reported_snapshot_before_timestamp_normalization(
    tmp_path,
):
    payload = _report()
    payload["candidateSnapshot"]["publications"][0]["publishStartedAt"] = (
        "2026-07-20T01:00:00Z"
    )
    payload["candidateSnapshotSha256"] = hashlib.sha256(
        json.dumps(
            payload["candidateSnapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    path = tmp_path / "eod-browser-acceptance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = parse_browser_acceptance_report(
        path,
        expected_run_id=RUN_ID,
        expected_trade_date=TRADE_DATE,
        exit_code=0,
    )

    assert result.snapshot["publications"][0]["publishStartedAt"].endswith("+00:00")


def test_success_report_requires_every_required_gate_to_have_passed(tmp_path):
    payload = _report()
    payload["tests"][0]["status"] = "skipped"
    payload["tests"][0]["attemptHistory"][0]["status"] = "skipped"
    path = tmp_path / "eod-browser-acceptance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BrowserAcceptanceError, match="gate_status"):
        parse_browser_acceptance_report(
            path,
            expected_run_id=RUN_ID,
            expected_trade_date=TRADE_DATE,
            exit_code=0,
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda payload: payload.update(schemaVersion="wrong"), "schema_version"),
        (lambda payload: payload.update(runId="wrong"), "run_id"),
        (lambda payload: payload.update(tradeDate="2026-07-19"), "trade_date"),
        (lambda payload: payload.pop("status"), "schema"),
        (lambda payload: payload["tests"].pop(), "gate"),
        (lambda payload: payload.update(candidateSnapshot=None), "candidate_snapshot"),
        (
            lambda payload: payload["attachments"][0].update(path="../../secret"),
            "artifact_path",
        ),
    ],
)
def test_parse_report_fails_closed_on_invalid_contract(tmp_path, mutation, code):
    payload = _report()
    mutation(payload)
    path = tmp_path / "eod-browser-acceptance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BrowserAcceptanceError, match=code):
        parse_browser_acceptance_report(
            path,
            expected_run_id=RUN_ID,
            expected_trade_date=TRADE_DATE,
            exit_code=0,
        )


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [("success", 2), ("degraded", 1), ("failed", 0)],
)
def test_parse_report_rejects_exit_status_mismatch(tmp_path, status, exit_code):
    path = _write_report(
        tmp_path / "eod-browser-acceptance.json",
        status=status,
        failures=["pageerror"] if status == "failed" else [],
        failed_gate="runtime-deep-links" if status == "failed" else None,
        severity="blocker-runtime",
    )

    with pytest.raises(BrowserAcceptanceError, match="exit_status_mismatch"):
        parse_browser_acceptance_report(
            path,
            expected_run_id=RUN_ID,
            expected_trade_date=TRADE_DATE,
            exit_code=exit_code,
        )


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("pageerror: white screen", "presentation_runtime"),
        ("critical_request_http_status:/api/foo:503", "critical_request_transport"),
        ("stale_cache: old selector payload", "stale_cache"),
        ("api_ui_mismatch: 52.40 vs 175.29", "api_ui_mismatch"),
        ("publish_id mismatch", "publication_identity"),
        ("performance date regression", "date_regression"),
        ("total return unit regression 175.29%", "return_unit"),
        ("contract_mismatch", "contract_mismatch"),
        ("publication rollback", "publish_rollback"),
        ("something new", "unknown"),
    ],
)
def test_failure_classification_is_fixed_and_unknown_is_nonrepairable(failure, expected):
    assert classify_browser_failures([failure]) == (expected,)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            "@eod-gate-publication-consistency: expect(received).toBe(expected)",
            "publication_identity",
        ),
        (
            "@eod-gate-candidate-consistency: expect(received).toBe(expected)",
            "api_ui_mismatch",
        ),
        (
            "@eod-gate-runtime-deep-links: locator did not become visible",
            "presentation_runtime",
        ),
        ("eod_candidate_performance_date_mismatch", "date_regression"),
    ],
)
def test_failure_classification_uses_gate_context_as_a_fail_closed_fallback(failure, expected):
    assert classify_browser_failures([failure]) == (expected,)


class FakeProcess:
    next_pid = 60000

    def __init__(self, kwargs, callback=None, *, exit_code=0, timeout=False):
        self.kwargs = kwargs
        self.callback = callback
        self.returncode = None
        self.exit_code = exit_code
        self.timeout = timeout
        self.pid = FakeProcess.next_pid
        FakeProcess.next_pid += 1
        self.wait_timeouts: list[float | None] = []

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if self.timeout:
            raise subprocess.TimeoutExpired(["pnpm", "test:e2e:eod"], timeout)
        if self.callback:
            self.callback(self.kwargs)
        self.returncode = self.exit_code
        return self.exit_code


def test_runner_uses_exact_command_isolated_env_nonreuse_and_private_logs(tmp_path):
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))

        def write_success(call_kwargs):
            _write_report(
                Path(call_kwargs["env"]["PLAYWRIGHT_EOD_OUTPUT_DIR"])
                / "eod-browser-acceptance.json"
            )

        return FakeProcess(kwargs, write_success)

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=popen,
        runtime_checker=lambda _dashboard: None,
        base_env={"PLAYWRIGHT_EOD_CONTRACT_ONLY": "true", "TOKEN": "secret"},
    )

    assert result.status == RepairStatus.SUCCESS
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == ["pnpm", "test:e2e:eod"]
    assert kwargs["cwd"].name == "dashboard"
    assert kwargs["start_new_session"] is True
    env = kwargs["env"]
    assert env["PLAYWRIGHT_PROFILE"] == "eod"
    assert env["PLAYWRIGHT_EOD_TRADE_DATE"] == TRADE_DATE
    assert env["PLAYWRIGHT_EOD_RUN_ID"] == RUN_ID
    assert env["PLAYWRIGHT_EOD_REVISION"] == REVISION
    assert json.loads(env["PLAYWRIGHT_EOD_PREVIOUS_PUBLICATIONS_JSON"]) == _previous_json()
    assert env["PLAYWRIGHT_DASHBOARD_PORT"] == "5176"
    assert env["PLAYWRIGHT_API_PORT"] == "8768"
    assert env["PLAYWRIGHT_REUSE_EXISTING"] == "false"
    assert "PLAYWRIGHT_EOD_CONTRACT_ONLY" not in env
    assert env["PLAYWRIGHT_JSON_OUTPUT_NAME"].endswith("attempt-1/playwright-results.json")
    assert Path(env["PLAYWRIGHT_EOD_OUTPUT_DIR"]).name == "attempt-1"
    for name in ("stdout.log", "stderr.log"):
        path = tmp_path / "attempt-1" / name
        assert path.exists()
        assert path.stat().st_mode & 0o777 == 0o600


def test_missing_runtime_is_an_infrastructure_blocker_without_starting_process(tmp_path):
    starts = []

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=lambda *args, **kwargs: starts.append((args, kwargs)),
        runtime_checker=lambda _dashboard: (_ for _ in ()).throw(
            RuntimeError("pnpm runtime missing")
        ),
    )

    assert result.status == RepairStatus.FAILED
    assert result.failure_classes == ("infrastructure",)
    assert "pnpm runtime missing" in result.message
    assert starts == []


def test_default_runtime_checker_distinguishes_pnpm_node_and_browser_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: None)
    with pytest.raises(BrowserAcceptanceError, match="pnpm_missing"):
        acceptance._default_runtime_checker(tmp_path)

    monkeypatch.setattr(
        acceptance.shutil, "which", lambda name: "/bin/pnpm" if name == "pnpm" else None
    )
    with pytest.raises(BrowserAcceptanceError, match="node_missing"):
        acceptance._default_runtime_checker(tmp_path)

    monkeypatch.setattr(acceptance.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        acceptance.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 3),
    )
    with pytest.raises(BrowserAcceptanceError, match="chromium_runtime_missing"):
        acceptance._default_runtime_checker(tmp_path)


def test_runner_refuses_a_preexisting_attempt_directory_to_avoid_stale_report_reuse(tmp_path):
    stale = tmp_path / "attempt-1"
    _write_report(stale / "eod-browser-acceptance.json")
    starts = []

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=lambda *args, **kwargs: starts.append((args, kwargs)),
        runtime_checker=lambda _dashboard: None,
    )

    assert result.status == RepairStatus.FAILED
    assert result.failure_classes == ("infrastructure",)
    assert "attempt_output_exists" in result.message
    assert starts == []


def test_runner_validates_explicit_previous_publication_schema_before_process_start(tmp_path):
    starts = []
    loader_calls = []

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications={},
        previous_publication_loader=lambda: loader_calls.append("called") or _previous_json(),
        popen=lambda *args, **kwargs: starts.append((args, kwargs)),
        runtime_checker=lambda _dashboard: None,
    )

    assert result.status == RepairStatus.FAILED
    assert result.failure_classes == ("infrastructure",)
    assert "previous_publication" in result.message
    assert loader_calls == []
    assert starts == []


def test_timeout_terminates_then_kills_process_group_and_keeps_logs(tmp_path, monkeypatch):
    events = []
    process = FakeProcess({}, timeout=True)

    def killpg(pgid, signum):
        events.append((pgid, signum))
        if signum == signal.SIGTERM:
            process.timeout = True
        elif signum == signal.SIGKILL:
            process.timeout = False
            process.returncode = -9

    monkeypatch.setattr(os, "killpg", killpg)

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=lambda *args, **kwargs: process,
        runtime_checker=lambda _dashboard: None,
        timeout_seconds=1,
        termination_grace_seconds=0.01,
    )

    assert result.status == RepairStatus.FAILED
    assert result.failure_classes == ("infrastructure",)
    assert events == [(process.pid, signal.SIGTERM), (process.pid, signal.SIGKILL)]
    assert (tmp_path / "attempt-1" / "stdout.log").exists()
    assert (tmp_path / "attempt-1" / "stderr.log").exists()


def test_repairable_failure_clears_cache_once_and_reruns_same_command(tmp_path):
    calls = []
    repairs = []

    def popen(command, **kwargs):
        attempt = len(calls) + 1
        calls.append((command, kwargs))

        def write_report(call_kwargs):
            report_dir = Path(call_kwargs["env"]["PLAYWRIGHT_EOD_OUTPUT_DIR"])
            if attempt == 1:
                _write_report(
                    report_dir / "eod-browser-acceptance.json",
                    status="failed",
                    failures=["pageerror: stale rendered bundle"],
                    failed_gate="runtime-deep-links",
                    severity="blocker-runtime",
                )
            else:
                _write_report(report_dir / "eod-browser-acceptance.json")

        return FakeProcess(kwargs, write_report, exit_code=1 if attempt == 1 else 0)

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=popen,
        runtime_checker=lambda _dashboard: None,
        cache_clearer=lambda: repairs.append("cleared"),
    )

    assert result.status == RepairStatus.SUCCESS
    assert repairs == ["cleared"]
    assert [command for command, _ in calls] == [
        ["pnpm", "test:e2e:eod"],
        ["pnpm", "test:e2e:eod"],
    ]
    assert len(result.attempts) == 2
    assert result.attempts[0].failure_classes == ("presentation_runtime",)
    assert result.attempts[1].status == RepairStatus.SUCCESS
    assert (tmp_path / "attempt-1" / "eod-browser-acceptance.json").exists()
    assert (tmp_path / "attempt-2" / "eod-browser-acceptance.json").exists()


@pytest.mark.parametrize(
    "failures",
    [
        ["api_ui_mismatch: total return differs"],
        ["pageerror", "publish_id mismatch"],
        ["publication rollback"],
    ],
)
def test_nonrepairable_or_mixed_failures_never_clear_cache(tmp_path, failures):
    repairs = []
    starts = []

    def popen(command, **kwargs):
        starts.append(command)

        def write_failure(call_kwargs):
            _write_report(
                Path(call_kwargs["env"]["PLAYWRIGHT_EOD_OUTPUT_DIR"])
                / "eod-browser-acceptance.json",
                status="failed",
                failures=failures,
                failed_gate="candidate-consistency",
            )

        return FakeProcess(kwargs, write_failure, exit_code=1)

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=popen,
        runtime_checker=lambda _dashboard: None,
        cache_clearer=lambda: repairs.append("cleared"),
    )

    assert result.status == RepairStatus.FAILED
    assert repairs == []
    assert len(starts) == 1


def test_cache_clear_failure_blocks_without_second_attempt(tmp_path):
    starts = []

    def popen(command, **kwargs):
        starts.append(command)

        def write_failure(call_kwargs):
            _write_report(
                Path(call_kwargs["env"]["PLAYWRIGHT_EOD_OUTPUT_DIR"])
                / "eod-browser-acceptance.json",
                status="failed",
                failures=["stale_cache"],
                failed_gate="runtime-deep-links",
                severity="blocker-runtime",
            )

        return FakeProcess(kwargs, write_failure, exit_code=1)

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=popen,
        runtime_checker=lambda _dashboard: None,
        cache_clearer=lambda: (_ for _ in ()).throw(RuntimeError("cache denied")),
    )

    assert result.status == RepairStatus.FAILED
    assert result.failure_classes == ("infrastructure",)
    assert "cache denied" in result.message
    assert len(starts) == 1


def test_runner_redacts_stderr_tail_secrets_and_absolute_paths(tmp_path):
    secret_path = "/Users/alice/private/secrets.txt"

    def popen(command, **kwargs):
        kwargs["stderr"].write(
            (
                "Cookie: session=abcdef\n"
                "Authorization: Bearer hidden-token\n"
                "password=super-secret token=api-secret\n"
                f"failed at {secret_path}\n"
            ).encode()
        )
        kwargs["stderr"].flush()
        return FakeProcess(kwargs, exit_code=2)

    result = run_browser_acceptance(
        trade_date=TRADE_DATE,
        run_id=RUN_ID,
        revision=REVISION,
        output_dir=tmp_path,
        previous_publications=_previous_json(),
        popen=popen,
        runtime_checker=lambda _dashboard: None,
    )

    assert result.status == RepairStatus.FAILED
    assert "abcdef" not in result.message
    assert "hidden-token" not in result.message
    assert "super-secret" not in result.message
    assert "api-secret" not in result.message
    assert secret_path not in result.message
    assert "<redacted>" in result.message
    raw_stderr = (tmp_path / "attempt-1" / "stderr.log").read_text(encoding="utf-8")
    assert "hidden-token" in raw_stderr


def _manifest_row(
    strategy_id: str,
    *,
    trade_date: str,
    started_at: str,
    publish_id: str,
    status: str = "success",
    total_return: float = 0.524,
):
    return {
        "module": f"strategy_{strategy_id}",
        "source": "strategy_daily_eod",
        "status": status,
        "trade_date": trade_date,
        "latest_trade_date": trade_date,
        "started_at": started_at,
        "ended_at": started_at,
        "run_id": f"run-{publish_id}",
        "metadata": {
            "publish_id": publish_id,
            "artifact_version": "strategy-publication/v1",
            "publication_identity": {
                "strategy_id": strategy_id,
                "contract_id": f"{strategy_id}:balanced:v1",
            },
            "summary": {
                "total_return": total_return,
                "publish_id": publish_id,
                "artifact_version": "strategy-publication/v1",
                "publication_identity": {
                    "strategy_id": strategy_id,
                    "contract_id": f"{strategy_id}:balanced:v1",
                },
            },
        },
    }


def test_previous_publication_loader_selects_latest_successful_identity_without_path_inference():
    rows = []
    for index, strategy_id in enumerate(STRATEGY_IDS):
        rows.extend(
            [
                _manifest_row(
                    strategy_id,
                    trade_date="2026-07-18",
                    started_at=f"2026-07-18T0{index + 1}:00:00+00:00",
                    publish_id=f"{strategy_id}-old",
                ),
                _manifest_row(
                    strategy_id,
                    trade_date="2026-07-19",
                    started_at=f"2026-07-19T0{index + 1}:00:00+00:00",
                    publish_id=f"{strategy_id}-latest",
                ),
                _manifest_row(
                    strategy_id,
                    trade_date="2026-07-20",
                    started_at=f"2026-07-20T0{index + 1}:00:00+00:00",
                    publish_id=f"{strategy_id}-failed",
                    status="failed",
                ),
            ]
        )

    payload = load_previous_official_publications(reader=lambda: rows)

    assert payload["schemaVersion"] == "playwright-eod-previous-publications/v1"
    assert [item["strategyId"] for item in payload["publications"]] == list(STRATEGY_IDS)
    assert [item["publishId"] for item in payload["publications"]] == [
        f"{strategy_id}-latest" for strategy_id in STRATEGY_IDS
    ]
    assert all(item["tradeDate"] == "2026-07-19" for item in payload["publications"])
    assert payload["publications"][0]["totalReturnPct"] == pytest.approx(52.4)


@pytest.mark.parametrize("prior_trade_date", ["2026-07-19", TRADE_DATE])
def test_previous_loader_excludes_the_newest_candidate_version_for_the_runner(prior_trade_date):
    rows = []
    for index, strategy_id in enumerate(STRATEGY_IDS):
        rows.extend(
            [
                _manifest_row(
                    strategy_id,
                    trade_date=prior_trade_date,
                    started_at=f"{prior_trade_date}T0{index + 1}:00:00+00:00",
                    publish_id=f"{strategy_id}-official",
                ),
                _manifest_row(
                    strategy_id,
                    trade_date=TRADE_DATE,
                    started_at=f"{TRADE_DATE}T1{index + 1}:00:00+00:00",
                    publish_id=f"{strategy_id}-candidate",
                ),
            ]
        )

    payload = load_previous_official_publications(
        reader=lambda: rows,
        candidate_trade_date=TRADE_DATE,
    )

    assert [item["publishId"] for item in payload["publications"]] == [
        f"{strategy_id}-official" for strategy_id in STRATEGY_IDS
    ]
    assert all(item["tradeDate"] == prior_trade_date for item in payload["publications"])


def test_previous_loader_accepts_native_database_date_timestamp_and_decimal_like_values():
    rows = [
        _manifest_row(
            strategy_id,
            trade_date="2026-07-19",
            started_at=f"2026-07-19T0{index + 1}:00:00+00:00",
            publish_id=f"{strategy_id}-latest",
        )
        for index, strategy_id in enumerate(STRATEGY_IDS)
    ]
    rows[0]["trade_date"] = date(2026, 7, 19)
    rows[0]["latest_trade_date"] = date(2026, 7, 19)
    rows[0]["started_at"] = datetime(2026, 7, 19, 1, tzinfo=timezone.utc)

    payload = load_previous_official_publications(reader=lambda: rows)

    assert payload["publications"][0]["tradeDate"] == "2026-07-19"
    assert payload["publications"][0]["publishStartedAt"] == "2026-07-19T01:00:00+00:00"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda row: row["metadata"].pop("publish_id"),
        lambda row: row.update(started_at="2026-07-19T01:00:00"),
        lambda row: row.update(trade_date="not-a-date", latest_trade_date="not-a-date"),
        lambda row: row["metadata"].update(publish_id="different"),
    ],
)
def test_previous_publication_loader_fails_closed_on_missing_or_conflicting_identity(mutator):
    rows = [
        _manifest_row(
            strategy_id,
            trade_date="2026-07-19",
            started_at=f"2026-07-19T0{index + 1}:00:00+00:00",
            publish_id=f"{strategy_id}-latest",
        )
        for index, strategy_id in enumerate(STRATEGY_IDS)
    ]
    mutator(rows[0])

    with pytest.raises(BrowserAcceptanceError, match="previous_publication"):
        load_previous_official_publications(reader=lambda: rows)


def test_previous_loader_supports_injected_connection_and_does_not_infer_publish_id_from_path():
    rows = [
        _manifest_row(
            strategy_id,
            trade_date="2026-07-19",
            started_at=f"2026-07-19T0{index + 1}:00:00+00:00",
            publish_id=f"{strategy_id}-latest",
        )
        for index, strategy_id in enumerate(STRATEGY_IDS)
    ]
    rows[0]["artifact_path"] = "/strategy_runs/lhb_shortline/path-derived-id/review.csv"

    payload = load_previous_official_publications(
        connection=object(),
        connection_reader=lambda _connection, _sql: rows,
    )

    assert payload["publications"][0]["publishId"] == "lhb_shortline-latest"
