from __future__ import annotations

import builtins
import errno
import hashlib
import json
import os
import shutil
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


def test_missing_root_is_explicit_configuration_error_without_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "missing-secret-root"

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert result.to_dict()["discovered"] == 0
    assert (result.indexed, result.unchanged, result.invalid) == (0, 0, 0)
    assert result.errors == ()
    assert result.root_exists is False
    assert result.root_readable is False
    assert result.error_code == "REPORT_ROOT_MISSING"
    assert str(root) not in json.dumps(result.to_dict())


def test_empty_root_is_healthy_and_readable(tmp_path: Path) -> None:
    result = report_index.scan_theme_research_report_root(tmp_path, limits=LIMITS)

    assert (result.discovered, result.indexed, result.unchanged, result.invalid) == (0, 0, 0, 0)
    assert result.errors == ()
    assert result.root_exists is True
    assert result.root_readable is True
    assert result.error_code is None


def test_non_directory_root_is_explicit_configuration_error(tmp_path: Path) -> None:
    root = tmp_path / "report-root"
    root.write_text("not a directory", encoding="utf-8")

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert result.root_exists is True
    assert result.root_readable is False
    assert result.error_code == "REPORT_ROOT_NOT_DIRECTORY"
    assert str(root) not in json.dumps(result.to_dict())


def test_unreadable_root_is_explicit_configuration_error(tmp_path: Path, monkeypatch) -> None:
    real_open = os.open

    def deny_root(path, flags, *args, **kwargs):
        if Path(path) == tmp_path:
            raise PermissionError(errno.EACCES, "secret root")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", deny_root)
    result = report_index.scan_theme_research_report_root(tmp_path, limits=LIMITS)

    assert result.root_exists is True
    assert result.root_readable is False
    assert result.error_code == "REPORT_ROOT_UNREADABLE"
    assert str(tmp_path) not in json.dumps(result.to_dict())


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

    assert (result.discovered, result.invalid) == (0, 0)
    assert result.errors == ()
    assert result.root_exists is True
    assert result.root_readable is False
    assert result.error_code == "REPORT_ROOT_NOT_DIRECTORY"
    assert str(root) not in json.dumps(result.to_dict())


@pytest.mark.parametrize("exc", [PermissionError("denied"), ValueError("bad path")])
def test_discovery_failure_is_stable(monkeypatch, tmp_path: Path, exc: Exception) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    original = os.listdir

    def broken_listdir(path):
        if isinstance(path, int):
            raise exc
        return original(path)

    monkeypatch.setattr(os, "listdir", broken_listdir)
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
    real_stat = os.stat

    def stat_path(path, *args, **kwargs):
        if path == version_dir.name and kwargs.get("dir_fd") is not None:
            raise FileNotFoundError("vanished")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat_path)
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
    z_theme_inode = os.stat(z_manifest.parents[1]).st_ino
    real_open = os.open

    def open_path(path, flags, mode=0o777, *, dir_fd=None):
        if (
            path == "v1"
            and dir_fd is not None
            and os.fstat(dir_fd).st_ino == z_theme_inode
        ):
            raise PermissionError("denied")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", open_path)
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


def test_cli_returns_configuration_error_for_missing_root(monkeypatch, capsys) -> None:
    now = datetime.now(timezone.utc)
    result = report_index.ReportScanResult(
        0,
        0,
        0,
        0,
        (),
        now,
        now,
        root_exists=False,
        root_readable=False,
        error_code="REPORT_ROOT_MISSING",
    )
    monkeypatch.setattr(report_index, "scan_theme_research_report_root", lambda *args, **kwargs: result)

    assert report_index.main([]) == 3
    assert json.loads(capsys.readouterr().out)["error_code"] == "REPORT_ROOT_MISSING"


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


def test_module_cli_missing_root_returns_safe_json_exit_three(tmp_path: Path) -> None:
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

    assert completed.returncode == 3
    payload = json.loads(completed.stdout)
    assert payload["discovered"] == 0
    assert payload["invalid"] == 0
    assert payload["errors"] == []
    assert payload["root_exists"] is False
    assert payload["root_readable"] is False
    assert payload["error_code"] == "REPORT_ROOT_MISSING"
    assert completed.stderr == ""


@pytest.mark.parametrize("swap_level", ["theme", "version"])
def test_directory_swap_to_symlink_is_not_followed_during_discovery(
    tmp_path: Path, monkeypatch, caplog, swap_level: str
) -> None:
    root = tmp_path / "reports"
    manifest = _write_report(root, "safe-theme", "v1")
    external = tmp_path / "absolute-secret-external"
    if swap_level == "theme":
        _write_report(external, "outside-theme", "outside-v")
        target = manifest.parents[1]
        replacement = external / "outside-theme"
        watched_name = "safe-theme"
    else:
        _write_report(external, "outside-theme", "outside-v")
        target = manifest.parent
        replacement = external / "outside-theme" / "outside-v"
        watched_name = "v1"
    original = target.with_name(f"{target.name}-original")
    real_open = os.open
    swapped = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if not swapped and dir_fd is not None and path == watched_name:
            swapped = True
            target.rename(original)
            target.symlink_to(replacement, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(os, "open", racing_open)
    monkeypatch.setattr(
        report_index,
        "register_report_manifest",
        lambda *args, **kwargs: pytest.fail("external report must not be registered"),
    )

    result = report_index.scan_theme_research_report_root(
        root, limits=LIMITS, service="runtime"
    )

    assert swapped is True
    assert result.discovered == 0
    assert result.invalid == 1
    assert str(external) not in caplog.text


@pytest.mark.parametrize("boundary", ["loader", "store"])
def test_memory_error_from_report_boundary_is_re_raised(
    tmp_path: Path, monkeypatch, boundary: str
) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")

    def exhaust(*args, **kwargs):
        raise MemoryError("out of memory")

    if boundary == "loader":
        monkeypatch.setattr(report_index, "load_report_manifest", exhaust)
    else:
        monkeypatch.setattr(report_index, "register_report_manifest", exhaust)

    with pytest.raises(MemoryError):
        report_index.scan_theme_research_report_root(
            root, limits=LIMITS, service="runtime"
        )


def test_memory_error_while_classifying_boundary_error_is_re_raised(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")
    real_import = builtins.__import__

    def fail_store(*args, **kwargs):
        raise RuntimeError("ordinary store failure")

    def import_with_oom(name, *args, **kwargs):
        if name == "stock_research.theme_research_report_store":
            raise MemoryError("out of memory")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(report_index, "register_report_manifest", fail_store)
    monkeypatch.setattr(builtins, "__import__", import_with_oom)

    with pytest.raises(MemoryError):
        report_index.scan_theme_research_report_root(
            root, limits=LIMITS, service="runtime"
        )


def test_memory_error_during_directory_listing_is_re_raised(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    real_listdir = os.listdir

    def exhaust(path):
        if isinstance(path, int):
            raise MemoryError("out of memory")
        return real_listdir(path)

    monkeypatch.setattr(os, "listdir", exhaust)

    with pytest.raises(MemoryError):
        report_index.scan_theme_research_report_root(
            root, limits=LIMITS, service="runtime"
        )


def test_directory_fds_close_when_theme_listing_raises_memory_error(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "reports"
    (root / "a-theme").mkdir(parents=True)
    real_names = report_index._sorted_directory_names
    real_close = report_index._safe_close
    listing_calls = 0
    closed: list[int] = []

    def list_names(directory_fd: int):
        nonlocal listing_calls
        listing_calls += 1
        if listing_calls == 2:
            raise MemoryError("out of memory")
        return real_names(directory_fd)

    def close_fd(descriptor: int | None):
        if descriptor is not None:
            closed.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(report_index, "_sorted_directory_names", list_names)
    monkeypatch.setattr(report_index, "_safe_close", close_fd)

    with pytest.raises(MemoryError):
        report_index.scan_theme_research_report_root(
            root, limits=LIMITS, service="runtime"
        )

    assert listing_calls == 2
    assert len(closed) == 2


def test_first_report_is_registered_before_later_theme_discovery(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")
    _write_report(root, "z-theme", "v1")
    events: list[str] = []
    real_open = os.open

    def ordered_open(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is not None and path == "z-theme":
            events.append("discover-z")
            raise PermissionError("denied")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def register(manifest, *, service):
        events.append(f"register-{manifest.theme_id}")
        return {"result": "indexed"}

    monkeypatch.setattr(os, "open", ordered_open)
    monkeypatch.setattr(report_index, "register_report_manifest", register)

    result = report_index.scan_theme_research_report_root(
        root, limits=LIMITS, service="runtime"
    )

    assert events[:2] == ["register-a-theme", "discover-z"]
    assert (result.discovered, result.indexed, result.invalid) == (1, 1, 1)


def test_default_runtime_service_is_resolved_once_per_scan(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")
    _write_report(root, "b-theme", "v1")
    settings_calls = 0
    services: list[str] = []

    def load_settings():
        nonlocal settings_calls
        settings_calls += 1
        return SimpleNamespace(theme_research_runtime_service="runtime-once")

    def register(manifest, *, service):
        services.append(service)
        return {"result": "indexed"}

    monkeypatch.setattr(report_index, "_load_settings", load_settings)
    monkeypatch.setattr(report_index, "register_report_manifest", register)

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert result.indexed == 2
    assert settings_calls == 1
    assert services == ["runtime-once", "runtime-once"]


def test_log_context_escapes_newlines_from_directory_names(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    root = tmp_path / "reports"
    manifest = _write_report(root, "bad\ninjected", "v1")
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        report_index,
        "register_report_manifest",
        lambda *args, **kwargs: pytest.fail(),
    )

    result = report_index.scan_theme_research_report_root(
        root, limits=LIMITS, service="runtime"
    )

    assert result.invalid == 1
    messages = [record.getMessage() for record in caplog.records]
    assert messages
    assert all(len(message.splitlines()) == 1 for message in messages)
    assert "bad\\ninjected" in messages[0]


@pytest.mark.parametrize("swap_level", ["root", "theme", "version"])
@pytest.mark.parametrize("restore_before_postcheck", [False, True])
def test_real_directory_replacement_after_discovery_never_registers_changed_manifest(
    tmp_path: Path,
    monkeypatch,
    caplog,
    swap_level: str,
    restore_before_postcheck: bool,
) -> None:
    root = tmp_path / "reports"
    _write_report(root, "safe-theme", "v1", markdown=b"# trusted\n")
    malicious_root = tmp_path / "absolute-secret-malicious"
    _write_report(
        malicious_root,
        "safe-theme",
        "v1",
        markdown=b"# malicious replacement\n",
    )
    real_load = report_index.load_report_manifest
    stored: list[str] = []

    def swapping_load(path, *, report_root, limits):
        if swap_level == "root":
            trusted_target = root
            malicious_target = malicious_root
        elif swap_level == "theme":
            trusted_target = root / "safe-theme"
            malicious_target = malicious_root / "safe-theme"
        else:
            trusted_target = root / "safe-theme" / "v1"
            malicious_target = malicious_root / "safe-theme" / "v1"
        original = trusted_target.with_name(f"{trusted_target.name}-original")
        used = malicious_target.with_name(f"{malicious_target.name}-used")
        trusted_target.rename(original)
        malicious_target.rename(trusted_target)
        manifest = real_load(path, report_root=report_root, limits=limits)
        if restore_before_postcheck:
            trusted_target.rename(used)
            original.rename(trusted_target)
        return manifest

    def register(manifest, *, service):
        stored.append(manifest.manifest_sha256)
        return {"result": "indexed"}

    monkeypatch.setattr(report_index, "load_report_manifest", swapping_load)
    monkeypatch.setattr(report_index, "register_report_manifest", register)

    result = report_index.scan_theme_research_report_root(
        root, limits=LIMITS, service="runtime"
    )

    assert stored == []
    assert (result.discovered, result.indexed, result.invalid) == (1, 0, 1)
    assert _error_codes(result) == ["MANIFEST_DISCOVERY_CHANGED"]
    assert str(malicious_root) not in json.dumps(result.to_dict())
    assert str(malicious_root) not in caplog.text


def test_byte_identical_root_aba_after_discovery_may_register(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    _write_report(root, "safe-theme", "v1", markdown=b"# identical\n")
    replacement = tmp_path / "replacement"
    shutil.copytree(root, replacement)
    original = tmp_path / "reports-original"
    used = tmp_path / "replacement-used"
    real_load = report_index.load_report_manifest
    stored: list[str] = []

    def swapping_load(path, *, report_root, limits):
        root.rename(original)
        replacement.rename(root)
        manifest = real_load(path, report_root=report_root, limits=limits)
        root.rename(used)
        original.rename(root)
        return manifest

    def register(manifest, *, service):
        stored.append(manifest.manifest_sha256)
        return {"result": "indexed"}

    monkeypatch.setattr(report_index, "load_report_manifest", swapping_load)
    monkeypatch.setattr(report_index, "register_report_manifest", register)

    result = report_index.scan_theme_research_report_root(
        root, limits=LIMITS, service="runtime"
    )

    assert len(stored) == 1
    assert (result.indexed, result.invalid) == (1, 0)


def test_manifest_disappearing_after_loader_is_discovery_changed(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "reports"
    manifest_path = _write_report(root, "safe-theme", "v1")
    real_load = report_index.load_report_manifest
    stored: list[str] = []

    def disappearing_load(path, *, report_root, limits):
        manifest = real_load(path, report_root=report_root, limits=limits)
        manifest_path.unlink()
        return manifest

    def register(manifest, *, service):
        stored.append(manifest.manifest_sha256)
        return {"result": "indexed"}

    monkeypatch.setattr(report_index, "load_report_manifest", disappearing_load)
    monkeypatch.setattr(report_index, "register_report_manifest", register)

    result = report_index.scan_theme_research_report_root(
        root, limits=LIMITS, service="runtime"
    )

    assert stored == []
    assert _error_codes(result) == ["MANIFEST_DISCOVERY_CHANGED"]


def test_missing_root_does_not_resolve_default_service(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "missing"

    def bad_settings():
        raise ValueError("invalid settings")

    monkeypatch.setattr(report_index, "_load_settings", bad_settings)

    result = report_index.scan_theme_research_report_root(root, limits=LIMITS)

    assert (result.discovered, result.invalid) == (0, 0)
    assert result.errors == ()


@pytest.mark.parametrize(
    ("boundary", "resource_errno"),
    [
        ("root_open", errno.EMFILE),
        ("root_listdir", errno.ENFILE),
        ("theme_open", errno.ENOMEM),
        ("version_open", errno.EMFILE),
        ("manifest_stat", errno.ENFILE),
        ("fingerprint_open", errno.ENOMEM),
    ],
)
def test_discovery_resource_exhaustion_is_re_raised_without_logging_or_store(
    tmp_path: Path,
    monkeypatch,
    caplog,
    boundary: str,
    resource_errno: int,
) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")
    real_open = os.open
    real_listdir = os.listdir
    real_stat = os.stat
    store_calls: list[str] = []

    def exhausted() -> OSError:
        return OSError(resource_errno, "resource exhausted secret")

    def open_path(path, flags, mode=0o777, *, dir_fd=None):
        matches = (
            (boundary == "root_open" and dir_fd is None and Path(path) == root)
            or (boundary == "theme_open" and dir_fd is not None and path == "a-theme")
            or (boundary == "version_open" and dir_fd is not None and path == "v1")
            or (
                boundary == "fingerprint_open"
                and dir_fd is not None
                and path == "manifest.json"
            )
        )
        if matches:
            raise exhausted()
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def listdir_path(path):
        if boundary == "root_listdir" and isinstance(path, int):
            raise exhausted()
        return real_listdir(path)

    def stat_path(path, *args, **kwargs):
        if (
            boundary == "manifest_stat"
            and path == "manifest.json"
            and kwargs.get("dir_fd") is not None
        ):
            raise exhausted()
        return real_stat(path, *args, **kwargs)

    def register(manifest, *, service):
        store_calls.append(manifest.theme_id)
        return {"result": "indexed"}

    monkeypatch.setattr(os, "open", open_path)
    monkeypatch.setattr(os, "listdir", listdir_path)
    monkeypatch.setattr(os, "stat", stat_path)
    monkeypatch.setattr(report_index, "register_report_manifest", register)

    with pytest.raises(OSError) as exc_info:
        report_index.scan_theme_research_report_root(
            root, limits=LIMITS, service="runtime"
        )

    assert exc_info.value.errno == resource_errno
    assert store_calls == []
    assert caplog.records == []


@pytest.mark.parametrize("resource_errno", [errno.EMFILE, errno.ENFILE, errno.ENOMEM])
def test_store_resource_exhaustion_is_re_raised(
    tmp_path: Path, monkeypatch, caplog, resource_errno: int
) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")

    def register(manifest, *, service):
        raise OSError(resource_errno, "resource exhausted secret")

    monkeypatch.setattr(report_index, "register_report_manifest", register)

    with pytest.raises(OSError) as exc_info:
        report_index.scan_theme_research_report_root(
            root, limits=LIMITS, service="runtime"
        )

    assert exc_info.value.errno == resource_errno
    assert caplog.records == []


def test_cli_resource_exhaustion_returns_safe_scan_level_json(monkeypatch, capsys) -> None:
    def exhaust(*args, **kwargs):
        raise OSError(errno.EMFILE, "absolute-secret-resource-text")

    monkeypatch.setattr(report_index, "scan_theme_research_report_root", exhaust)

    assert report_index.main([]) == 3
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "error": {"code": "REPORT_INDEX_RESOURCE_EXHAUSTED"}
    }
    assert "absolute-secret" not in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("boundary", ["root_open", "manifest_stat"])
def test_file_not_found_wrapper_does_not_hide_resource_exhaustion(
    tmp_path: Path, monkeypatch, boundary: str
) -> None:
    root = tmp_path / "reports"
    _write_report(root, "a-theme", "v1")
    real_open = os.open
    real_stat = os.stat

    def wrapped_missing() -> FileNotFoundError:
        try:
            raise OSError(errno.EMFILE, "resource exhausted")
        except OSError as resource_error:
            try:
                raise FileNotFoundError(errno.ENOENT, "missing") from resource_error
            except FileNotFoundError as missing_error:
                return missing_error

    def open_path(path, flags, mode=0o777, *, dir_fd=None):
        if boundary == "root_open" and dir_fd is None and Path(path) == root:
            raise wrapped_missing()
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def stat_path(path, *args, **kwargs):
        if (
            boundary == "manifest_stat"
            and path == "manifest.json"
            and kwargs.get("dir_fd") is not None
        ):
            raise wrapped_missing()
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_path)
    monkeypatch.setattr(os, "stat", stat_path)

    with pytest.raises(OSError) as exc_info:
        report_index.scan_theme_research_report_root(
            root, limits=LIMITS, service="runtime"
        )

    assert exc_info.value.errno == errno.EMFILE


@pytest.mark.parametrize("wrapped", [False, True])
def test_cli_config_resource_exhaustion_uses_resource_error_json(
    monkeypatch, capsys, wrapped: bool
) -> None:
    def load_settings():
        resource_error = OSError(errno.ENFILE, "absolute-secret-resource")
        if wrapped:
            raise ValueError("bad config") from resource_error
        raise resource_error

    monkeypatch.setattr(report_index, "_load_settings", load_settings)

    assert report_index.main([]) == 3
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "error": {"code": "REPORT_INDEX_RESOURCE_EXHAUSTED"}
    }
    assert captured.err == ""
    assert "absolute-secret" not in captured.out
