from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from types import SimpleNamespace

import pytest

from stock_research.theme_research_report_manifest import ReportManifestLimits
from stock_research.theme_research_report_store import ThemeResearchReportError
import stock_research.theme_research_report_index as report_index


LIMITS = ReportManifestLimits(64 * 1024, 1024 * 1024, 1024 * 1024)


def _write_report(
    root: Path,
    theme: str,
    version: str,
    *,
    markdown: bytes = b"# report\n",
    checksum: str | None = None,
) -> Path:
    version_dir = root / theme / version
    version_dir.mkdir(parents=True)
    markdown_path = version_dir / "report.md"
    markdown_path.write_bytes(markdown)
    payload = {
        "schema_version": "theme_research_report_manifest_v1",
        "theme_id": theme,
        "version": version,
        "title": f"{theme} {version}",
        "summary": "summary",
        "generated_at": "2026-07-31T00:00:00Z",
        "generator": {"name": "test", "version": "1"},
        "artifacts": {
            "markdown": {
                "path": "report.md",
                "sha256": checksum or hashlib.sha256(markdown).hexdigest(),
            }
        },
        "metadata": {},
    }
    manifest_path = version_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path


def _error_codes(result: report_index.ReportScanResult) -> list[str]:
    return [error["code"] for error in result.errors]


def test_missing_root_is_valid_empty_state_without_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "missing-secret-root"

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert result.to_dict()["discovered"] == 0
    assert (result.indexed, result.unchanged, result.invalid) == (0, 0, 0)
    assert result.errors == ()
    assert str(root) not in json.dumps(result.to_dict())


def test_valid_reports_are_registered_in_posix_relative_path_order(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    _write_report(root, "z-theme", "v1")
    _write_report(root, "a-theme", "v2")
    calls: list[tuple[str, str, str]] = []

    def register(manifest, *, service):
        calls.append((manifest.manifest_relative_path, manifest.theme_id, service))
        return {"result": "indexed" if manifest.theme_id == "a-theme" else "unchanged"}

    monkeypatch.setattr(report_index, "register_report_manifest", register)
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS, service="runtime")

    assert calls == [
        ("a-theme/v2/manifest.json", "a-theme", "runtime"),
        ("z-theme/v1/manifest.json", "z-theme", "runtime"),
    ]
    assert (result.discovered, result.indexed, result.unchanged, result.invalid) == (2, 1, 1, 0)


def test_bad_checksum_does_not_block_valid_report_and_error_is_sanitized(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "absolute-secret-root"
    bad = _write_report(root, "bad-theme", "v1", checksum="0" * 64)
    _write_report(root, "good-theme", "v2")
    monkeypatch.setattr(
        report_index,
        "register_report_manifest",
        lambda manifest, *, service: {"result": "indexed"},
    )

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.discovered, result.indexed, result.invalid) == (2, 1, 1)
    assert result.errors == (
        {
            "code": "ARTIFACT_CHECKSUM_MISMATCH",
            "manifest_path": "bad-theme/v1/manifest.json",
            "theme_id": "bad-theme",
            "version": "v1",
        },
    )
    encoded = json.dumps(result.to_dict())
    assert str(root) not in encoded
    assert str(bad) not in encoded


def test_invalid_manifest_only_includes_identity_when_safely_known(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    manifest = _write_report(root, "safe-theme", "v1")
    manifest.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(report_index, "register_report_manifest", lambda *args, **kwargs: pytest.fail())

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert result.errors == (
        {
            "code": "MANIFEST_INVALID_JSON",
            "manifest_path": "safe-theme/v1/manifest.json",
        },
    )


@pytest.mark.parametrize(
    ("store_error", "expected_code"),
    [
        (ThemeResearchReportError("THEME_REPORT_VERSION_CONTENT_CONFLICT", "db row conflict", {"sql": "secret"}), "THEME_REPORT_VERSION_CONTENT_CONFLICT"),
        (ThemeResearchReportError("THEME_REPORT_THEME_NOT_FOUND", "unknown theme"), "THEME_REPORT_THEME_NOT_FOUND"),
        (ThemeResearchReportError("THEME_REPORT_STORE_UNAVAILABLE", "postgres secret"), "THEME_REPORT_STORE_UNAVAILABLE"),
    ],
)
def test_real_store_errors_are_isolated_and_sanitized(tmp_path: Path, monkeypatch, store_error, expected_code) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")
    _write_report(root, "b-theme", "v1")
    calls = 0

    def register(manifest, *, service):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise store_error
        return {"result": "indexed"}

    monkeypatch.setattr(report_index, "register_report_manifest", register)
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.indexed, result.invalid) == (1, 1)
    assert _error_codes(result) == [expected_code]
    encoded = json.dumps(result.to_dict()).lower()
    assert "postgres" not in encoded
    assert "secret" not in encoded
    assert "sql" not in encoded


def test_unknown_exception_becomes_stable_error_and_scan_continues(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    root = tmp_path / "absolute-secret-reports"
    _write_report(root, "a-theme", "v1")
    _write_report(root, "b-theme", "v1")

    def register(manifest, *, service):
        if manifest.theme_id == "a-theme":
            raise RuntimeError("database password=secret")
        return {"result": "indexed"}

    monkeypatch.setattr(report_index, "register_report_manifest", register)
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.indexed, result.invalid) == (1, 1)
    assert _error_codes(result) == ["INDEX_UNEXPECTED_ERROR"]
    assert "secret" not in json.dumps(result.to_dict())
    assert "INDEX_UNEXPECTED_ERROR" in caplog.text
    assert "password=secret" not in caplog.text
    assert str(root) not in caplog.text


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt(), SystemExit(9)])
def test_process_interrupts_are_not_swallowed(tmp_path: Path, monkeypatch, interrupt: BaseException) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")

    def register(manifest, *, service):
        raise interrupt

    monkeypatch.setattr(report_index, "register_report_manifest", register)
    with pytest.raises(type(interrupt)):
        report_index.scan_theme_research_report_root(root, limits=LIMITS)


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_invalid_root_is_reported_stably(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "root"
    if kind == "file":
        root.write_text("not a directory", encoding="utf-8")
    else:
        target = tmp_path / "target"
        target.mkdir()
        root.symlink_to(target, target_is_directory=True)

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.discovered, result.invalid) == (0, 1)
    assert result.errors == ({"code": "REPORT_ROOT_INVALID"},)
    assert str(root) not in json.dumps(result.to_dict())


@pytest.mark.parametrize("exc", [PermissionError("denied"), ValueError("bad path")])
def test_discovery_failure_is_stable(monkeypatch, tmp_path: Path, exc: Exception) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    original = Path.iterdir

    def broken_iterdir(path: Path):
        if path == root:
            raise exc
        return original(path)

    monkeypatch.setattr(Path, "iterdir", broken_iterdir)
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert result.invalid == 1
    assert result.errors == ({"code": "REPORT_DISCOVERY_ERROR"},)


def test_manifest_disappearing_after_discovery_is_isolated(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    vanished = _write_report(root, "a-theme", "v1")
    _write_report(root, "b-theme", "v1")
    real_load = report_index.load_report_manifest

    def load(path, *, report_root, limits):
        if Path(path) == vanished:
            vanished.unlink()
        return real_load(path, report_root=report_root, limits=limits)

    monkeypatch.setattr(report_index, "load_report_manifest", load)
    monkeypatch.setattr(report_index, "register_report_manifest", lambda *args, **kwargs: {"result": "indexed"})
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.discovered, result.indexed, result.invalid) == (2, 1, 1)
    assert _error_codes(result) == ["MANIFEST_INVALID"]


def test_version_directory_disappearing_during_discovery_is_stable(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    manifest = _write_report(root, "a-theme", "v1")
    version_dir = manifest.parent
    real_lstat = Path.lstat

    def lstat(path: Path):
        if path == version_dir:
            raise FileNotFoundError("vanished")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.discovered, result.invalid) == (0, 1)
    assert result.errors == (
        {
            "code": "REPORT_DISCOVERY_ERROR",
            "manifest_path": "a-theme/v1/manifest.json",
            "theme_id": "a-theme",
            "version": "v1",
        },
    )


def test_only_finalized_strict_two_level_manifests_are_discovered(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    _write_report(root, "real-theme", "v1")
    _write_report(root, ".hidden-theme", "v1")
    _write_report(root, "draft.tmp", "v1")
    _write_report(root, "real-theme", ".tmp-v2")
    _write_report(root, "real-theme", "v3.tmp")
    deep = root / "real-theme" / "v1" / "nested" / "manifest.json"
    deep.parent.mkdir()
    deep.write_text("{}", encoding="utf-8")
    temporary = root / "manifest.json"
    temporary.write_text("{}", encoding="utf-8")
    seen: list[str] = []

    def register(manifest, *, service):
        seen.append(manifest.manifest_relative_path)
        return {"result": "indexed"}

    monkeypatch.setattr(report_index, "register_report_manifest", register)
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert result.discovered == 1
    assert seen == ["real-theme/v1/manifest.json"]


def test_errors_are_deterministic_bounded_but_invalid_counts_all(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    for index in reversed(range(105)):
        path = _write_report(root, f"theme-{index:03d}", "v1")
        path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(report_index, "register_report_manifest", lambda *args, **kwargs: pytest.fail())

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.discovered, result.invalid, len(result.errors)) == (105, 105, 100)
    assert [error["manifest_path"] for error in result.errors] == [
        f"theme-{index:03d}/v1/manifest.json" for index in range(100)
    ]


def test_discovery_and_manifest_errors_share_global_relative_path_order(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "reports"
    bad_manifest = _write_report(root, "a-theme", "v1")
    bad_manifest.write_text("{}", encoding="utf-8")
    z_manifest = _write_report(root, "z-theme", "v1")
    real_lstat = Path.lstat

    def lstat(path: Path):
        if path == z_manifest.parent:
            raise PermissionError("denied")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert [error["manifest_path"] for error in result.errors] == [
        "a-theme/v1/manifest.json",
        "z-theme/v1/manifest.json",
    ]


def test_result_timestamps_and_to_dict_are_safe_and_detached() -> None:
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)
    completed = datetime(2026, 7, 31, 0, 0, 1, tzinfo=timezone.utc)
    source_error = {"code": "X", "manifest_path": "a/v/manifest.json"}

    result = report_index.ReportScanResult(1, 0, 0, 1, (source_error,), started, completed)
    source_error["code"] = "MUTATED"
    first = result.to_dict()
    first["errors"][0]["code"] = "CHANGED"

    assert result.errors[0]["code"] == "X"
    assert result.to_dict()["errors"][0]["code"] == "X"
    assert result.started_at.tzinfo is not None
    assert result.completed_at >= result.started_at
    json.dumps(result.to_dict())
    with pytest.raises(TypeError):
        result.errors[0]["code"] = "NOPE"
    with pytest.raises(ValueError):
        replace(result, completed_at=started.replace(year=2025))
    with pytest.raises(ValueError):
        report_index.ReportScanResult(
            0,
            0,
            0,
            1,
            ({"code": "X", "unsafe": Path("not-json-safe")},),
            started,
            completed,
        )


def test_result_rejects_tzinfo_that_is_not_actually_aware() -> None:
    class NaiveTz(tzinfo):
        def utcoffset(self, dt):
            return None

        def dst(self, dt):
            return None

    timestamp = datetime(2026, 7, 31, tzinfo=NaiveTz())

    with pytest.raises(ValueError):
        report_index.ReportScanResult(0, 0, 0, 0, (), timestamp, timestamp)


def test_limits_from_settings_maps_and_validates_fields() -> None:
    settings = SimpleNamespace(
        theme_research_report_max_manifest_bytes=11,
        theme_research_report_max_markdown_bytes=22,
        theme_research_report_max_pdf_bytes=33,
    )
    assert report_index.limits_from_settings(settings) == ReportManifestLimits(11, 22, 33)
    settings.theme_research_report_max_pdf_bytes = 0
    with pytest.raises(ValueError):
        report_index.limits_from_settings(settings)


def test_cli_prints_json_and_uses_requested_root_service(monkeypatch, tmp_path: Path, capsys) -> None:
    captured = {}
    now = datetime.now(timezone.utc)

    def scan(root, *, limits, service):
        captured.update(root=root, limits=limits, service=service)
        return report_index.ReportScanResult(1, 1, 0, 0, (), now, now)

    monkeypatch.setattr(report_index, "scan_theme_research_report_root", scan)
    exit_code = report_index.main(["--root", str(tmp_path), "--service", "runtime-test"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["indexed"] == 1
    assert captured["root"] == tmp_path
    assert captured["service"] == "runtime-test"
    assert captured["limits"] == report_index.limits_from_settings(
        report_index._load_settings()
    )


@pytest.mark.parametrize(("code", "expected_exit"), [("MANIFEST_INVALID_JSON", 2), ("REPORT_ROOT_INVALID", 3)])
def test_cli_exit_codes_are_stable_and_stdout_has_no_traceback(monkeypatch, capsys, code: str, expected_exit: int) -> None:
    now = datetime.now(timezone.utc)
    result = report_index.ReportScanResult(0, 0, 0, 1, ({"code": code},), now, now)
    monkeypatch.setattr(report_index, "scan_theme_research_report_root", lambda *args, **kwargs: result)

    assert report_index.main([]) == expected_exit
    output = capsys.readouterr().out
    json.loads(output)
    assert "Traceback" not in output


def test_cli_treats_only_root_level_discovery_failure_as_exit_three(monkeypatch, capsys) -> None:
    now = datetime.now(timezone.utc)
    result = report_index.ReportScanResult(
        0,
        0,
        0,
        1,
        ({"code": "REPORT_DISCOVERY_ERROR", "theme_id": "a-theme"},),
        now,
        now,
    )
    monkeypatch.setattr(report_index, "scan_theme_research_report_root", lambda *args, **kwargs: result)

    assert report_index.main([]) == 2
    json.loads(capsys.readouterr().out)


def test_cli_invalid_settings_returns_root_configuration_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(report_index, "limits_from_settings", lambda settings: (_ for _ in ()).throw(ValueError("secret")))

    assert report_index.main([]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"error": {"code": "REPORT_INDEX_CONFIGURATION_ERROR"}}
    assert "secret" not in json.dumps(payload)


def test_module_cli_invalid_environment_returns_safe_json_exit_three(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    secret_root = tmp_path / "absolute-secret-root"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root / "src")
    environment["THEME_RESEARCH_REPORT_MAX_PDF_BYTES"] = "0"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_research.theme_research_report_index",
            "--root",
            str(secret_root),
        ],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3
    assert len(completed.stdout.splitlines()) == 1
    assert json.loads(completed.stdout) == {
        "error": {"code": "REPORT_INDEX_CONFIGURATION_ERROR"}
    }
    assert completed.stderr == ""
    combined = completed.stdout + completed.stderr
    assert "Traceback" not in combined
    assert str(secret_root) not in combined


def test_module_cli_missing_root_still_returns_empty_json_exit_zero(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    missing_root = tmp_path / "missing-root"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root / "src")
    environment.pop("THEME_RESEARCH_REPORT_MAX_PDF_BYTES", None)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_research.theme_research_report_index",
            "--root",
            str(missing_root),
        ],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["discovered"] == 0
    assert payload["invalid"] == 0
    assert payload["errors"] == []
    assert completed.stderr == ""
