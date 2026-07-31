from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from stock_research import theme_research_report_manifest as manifest_module
from stock_research.theme_research_report_manifest import (
    ReportManifestError,
    ReportManifestLimits,
    load_report_manifest,
    metadata_to_jsonable,
)


DEFAULT_LIMITS = ReportManifestLimits(
    max_manifest_bytes=16_384,
    max_markdown_bytes=8_192,
    max_pdf_bytes=16_384,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_package(
    tmp_path: Path,
    *,
    theme_id: str = "ai-power",
    version: str = "2026-07-31-v1",
    markdown: bytes = b"# AI power\n",
    pdf: bytes | None = None,
    overrides: dict[str, object] | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    report_root = tmp_path / "reports" / "theme-research"
    version_dir = report_root / theme_id / version
    version_dir.mkdir(parents=True)
    (version_dir / "report.md").write_bytes(markdown)
    artifacts: dict[str, object] = {
        "markdown": {"path": "report.md", "sha256": _sha256(markdown)},
    }
    if pdf is not None:
        (version_dir / "report.pdf").write_bytes(pdf)
        artifacts["pdf"] = {"path": "report.pdf", "sha256": _sha256(pdf)}
    manifest: dict[str, object] = {
        "schema_version": "theme_research_report_manifest_v1",
        "theme_id": theme_id,
        "version": version,
        "title": "AI Power Theme",
        "summary": "A concise summary.",
        "generated_at": "2026-07-31T08:30:00+08:00",
        "generator": {"name": "theme-worker", "version": "2.4.1"},
        "artifacts": artifacts,
        "metadata": {"source": {"kind": "production"}},
    }
    if overrides:
        manifest.update(overrides)
    manifest_path = version_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return report_root, manifest_path, manifest


def _assert_error(
    manifest_path: Path,
    report_root: Path,
    expected_code: str,
    *,
    limits: ReportManifestLimits = DEFAULT_LIMITS,
) -> ReportManifestError:
    with pytest.raises(ReportManifestError) as exc_info:
        load_report_manifest(manifest_path, report_root=report_root, limits=limits)
    assert exc_info.value.code == expected_code
    assert str(exc_info.value)
    return exc_info.value


def test_loads_valid_markdown_only_manifest_with_real_hashes(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)

    result = load_report_manifest(manifest_path, report_root=report_root, limits=DEFAULT_LIMITS)

    assert result.theme_id == "ai-power"
    assert result.version == "2026-07-31-v1"
    assert result.title == "AI Power Theme"
    assert result.summary == "A concise summary."
    assert result.generated_at.isoformat() == "2026-07-31T08:30:00+08:00"
    assert result.generator_name == "theme-worker"
    assert result.generator_version == "2.4.1"
    assert result.markdown.relative_path == "report.md"
    assert result.markdown.sha256 == _sha256(b"# AI power\n")
    assert result.markdown.size_bytes == len(b"# AI power\n")
    assert result.pdf is None
    assert result.manifest_relative_path == "ai-power/2026-07-31-v1/manifest.json"
    assert result.manifest_sha256 == _sha256(manifest_path.read_bytes())
    assert result.metadata == {"source": {"kind": "production"}}


def test_loads_valid_markdown_and_pdf_manifest(tmp_path: Path) -> None:
    pdf = b"%PDF-1.7\nreal bytes\n%%EOF\n"
    report_root, manifest_path, _ = _write_package(tmp_path, pdf=pdf)

    result = load_report_manifest(manifest_path, report_root=report_root, limits=DEFAULT_LIMITS)

    assert result.pdf is not None
    assert result.pdf.relative_path == "report.pdf"
    assert result.pdf.sha256 == _sha256(pdf)
    assert result.pdf.size_bytes == len(pdf)


def test_returned_models_and_nested_metadata_are_immutable_snapshots(tmp_path: Path) -> None:
    report_root, manifest_path, manifest = _write_package(
        tmp_path,
        overrides={
            "metadata": {
                "source": {
                    "kind": "production",
                    "tags": ["primary", {"name": "audited"}],
                }
            }
        },
    )
    result = load_report_manifest(manifest_path, report_root=report_root, limits=DEFAULT_LIMITS)

    manifest["metadata"] = {"source": {"kind": "mutated"}}

    source = result.metadata["source"]
    assert isinstance(source, Mapping)
    tags = source["tags"]
    assert isinstance(tags, tuple)
    assert isinstance(tags[1], Mapping)
    with pytest.raises(TypeError):
        result.metadata["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        source["kind"] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        tags[0] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        tags[1]["name"] = "mutated"  # type: ignore[index]
    with pytest.raises(AttributeError):
        tags.append("mutated")
    assert result.metadata == {
        "source": {
            "kind": "production",
            "tags": ("primary", {"name": "audited"}),
        }
    }
    with pytest.raises(FrozenInstanceError):
        result.theme_id = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.markdown.relative_path = "other.md"  # type: ignore[misc]


def test_metadata_to_jsonable_returns_detached_dicts_and_lists(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(
        tmp_path,
        overrides={
            "metadata": {
                "source": {
                    "kind": "production",
                    "tags": ["primary", {"name": "audited"}],
                }
            }
        },
    )
    result = load_report_manifest(manifest_path, report_root=report_root, limits=DEFAULT_LIMITS)

    jsonable = metadata_to_jsonable(result.metadata)

    assert type(jsonable) is dict
    assert type(jsonable["source"]) is dict
    assert type(jsonable["source"]["tags"]) is list
    assert json.loads(json.dumps(jsonable)) == jsonable
    jsonable["source"]["kind"] = "mutated"
    jsonable["source"]["tags"].append("mutated")
    jsonable["source"]["tags"][1]["name"] = "mutated"
    assert result.metadata["source"]["kind"] == "production"
    assert result.metadata["source"]["tags"] == (
        "primary",
        {"name": "audited"},
    )


@pytest.mark.parametrize("value", [0, -1])
def test_limits_require_positive_values(value: int) -> None:
    with pytest.raises(ValueError):
        ReportManifestLimits(value, 1, 1)
    with pytest.raises(ValueError):
        ReportManifestLimits(1, value, 1)
    with pytest.raises(ValueError):
        ReportManifestLimits(1, 1, value)


def test_rejects_oversized_manifest(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    limits = ReportManifestLimits(8, 8_192, 16_384)

    _assert_error(manifest_path, report_root, "MANIFEST_TOO_LARGE", limits=limits)


def test_rejects_invalid_utf8_manifest(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    manifest_path.write_bytes(b"\xff\xfe")

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID_UTF8")


def test_rejects_malformed_json_manifest(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    manifest_path.write_bytes(b'{"schema_version":')

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID_JSON")


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_json_numeric_constants(tmp_path: Path, constant: str) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            '"metadata": {"source": {"kind": "production"}}',
            f'"metadata": {{"value": {constant}}}',
        ),
        encoding="utf-8",
    )

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID_JSON")


def test_rejects_non_object_json_manifest(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    manifest_path.write_bytes(b"[]")

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID_SHAPE")


@pytest.mark.parametrize("nested_field", ["metadata", "schema_version"])
def test_rejects_json_beyond_supported_nesting_depth(
    tmp_path: Path, nested_field: str
) -> None:
    report_root, manifest_path, manifest = _write_package(tmp_path)
    nested: object = "leaf"
    for _ in range(70):
        nested = {"child": nested}
    manifest[nested_field] = nested
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _assert_error(manifest_path, report_root, "MANIFEST_TOO_DEEPLY_NESTED")


def test_parser_recursion_error_has_stable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)

    def failing_loads(*_args: object, **_kwargs: object) -> object:
        raise RecursionError("simulated parser recursion limit")

    monkeypatch.setattr(manifest_module.json, "loads", failing_loads)

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID_JSON")


def test_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path, overrides={"schema_version": "2"})

    _assert_error(manifest_path, report_root, "UNSUPPORTED_SCHEMA_VERSION")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("theme_id", ""),
        ("theme_id", "   "),
        ("version", ""),
        ("title", ""),
        ("title", 7),
    ],
)
def test_rejects_invalid_required_text_fields(tmp_path: Path, field: str, value: object) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path, overrides={field: value})

    _assert_error(manifest_path, report_root, "FIELD_INVALID")


@pytest.mark.parametrize(
    "generator",
    [
        None,
        [],
        {"name": "", "version": "1"},
        {"name": "worker", "version": "   "},
        {"name": 1, "version": "1"},
    ],
)
def test_rejects_invalid_generator_fields(tmp_path: Path, generator: object) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path, overrides={"generator": generator})

    _assert_error(manifest_path, report_root, "FIELD_INVALID")


@pytest.mark.parametrize(
    "generated_at",
    ["", "2026-07-31", "2026-07-31T08:30:00", "not-a-date", 123],
)
def test_generated_at_must_be_timezone_aware_iso8601(tmp_path: Path, generated_at: object) -> None:
    report_root, manifest_path, _ = _write_package(
        tmp_path, overrides={"generated_at": generated_at}
    )

    _assert_error(manifest_path, report_root, "GENERATED_AT_INVALID")


def test_rejects_missing_markdown_entry(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path, overrides={"artifacts": {}})

    _assert_error(manifest_path, report_root, "MARKDOWN_REQUIRED")


@pytest.mark.parametrize(
    "artifacts",
    [
        None,
        [],
        {"markdown": "report.md"},
        {"markdown": {"path": 1, "sha256": "a" * 64}},
        {"markdown": {"path": "report.md", "sha256": 1}},
        {"markdown": {"path": "report.md", "sha256": "a" * 63}},
        {"markdown": {"path": "report.md", "sha256": "g" * 64}},
        {"markdown": {"path": "report.md", "sha256": "A" * 64}},
        {
            "markdown": {"path": "report.md", "sha256": _sha256(b"# AI power\n")},
            "pdf": [],
        },
        {
            "markdown": {"path": "report.md", "sha256": _sha256(b"# AI power\n")},
            "pdf": None,
        },
    ],
)
def test_rejects_invalid_artifact_entries(tmp_path: Path, artifacts: object) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path, overrides={"artifacts": artifacts})

    _assert_error(manifest_path, report_root, "ARTIFACT_ENTRY_INVALID")


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/report.md",
        "../report.md",
        "./report.md",
        "nested/report.md",
        "nested//report.md",
        "",
    ],
)
def test_rejects_absolute_traversal_dot_empty_and_nested_artifact_paths(
    tmp_path: Path, path: str
) -> None:
    report_root, manifest_path, manifest = _write_package(tmp_path)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    markdown = artifacts["markdown"]
    assert isinstance(markdown, dict)
    markdown["path"] = path
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _assert_error(manifest_path, report_root, "ARTIFACT_PATH_INVALID")


def test_rejects_missing_declared_file(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    manifest_path.with_name("report.md").unlink()

    _assert_error(manifest_path, report_root, "ARTIFACT_MISSING")


def test_rejects_checksum_mismatch(tmp_path: Path) -> None:
    report_root, manifest_path, manifest = _write_package(tmp_path)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    markdown = artifacts["markdown"]
    assert isinstance(markdown, dict)
    markdown["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _assert_error(manifest_path, report_root, "ARTIFACT_CHECKSUM_MISMATCH")


@pytest.mark.parametrize(
    ("kind", "limit"),
    [("markdown", 4), ("pdf", 8)],
)
def test_rejects_oversized_artifacts(tmp_path: Path, kind: str, limit: int) -> None:
    report_root, manifest_path, _ = _write_package(
        tmp_path,
        markdown=b"markdown bytes",
        pdf=b"%PDF oversized bytes",
    )
    limits = ReportManifestLimits(
        max_manifest_bytes=16_384,
        max_markdown_bytes=limit if kind == "markdown" else 8_192,
        max_pdf_bytes=limit if kind == "pdf" else 16_384,
    )

    _assert_error(manifest_path, report_root, "ARTIFACT_TOO_LARGE", limits=limits)


def test_rejects_manifest_symlink(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    real_manifest = manifest_path.with_name("real-manifest.json")
    manifest_path.rename(real_manifest)
    manifest_path.symlink_to(real_manifest.name)

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID")


def test_rejects_non_regular_manifest(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    manifest_path.unlink()
    manifest_path.mkdir()

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID")


def test_rejects_symlinked_report_root(tmp_path: Path) -> None:
    real_root, manifest_path, _ = _write_package(tmp_path / "real")
    report_root = tmp_path / "theme-research-link"
    report_root.symlink_to(real_root, target_is_directory=True)
    linked_manifest = report_root / manifest_path.relative_to(real_root)

    _assert_error(linked_manifest, report_root, "REPORT_ROOT_INVALID")


def test_directory_fd_prevents_version_directory_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path / "trusted")
    _, evil_manifest, _ = _write_package(
        tmp_path / "evil",
        overrides={"title": "Untrusted replacement"},
    )
    version_dir = manifest_path.parent
    saved_version_dir = version_dir.with_name("saved-version")
    original_open = manifest_module.os.open
    swapped = False

    def swapping_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal swapped
        if not swapped and Path(os.fspath(path)).name == "manifest.json":
            swapped = True
            version_dir.rename(saved_version_dir)
            version_dir.symlink_to(evil_manifest.parent, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(manifest_module.os, "open", swapping_open)

    result = load_report_manifest(manifest_path, report_root=report_root, limits=DEFAULT_LIMITS)

    assert swapped is True
    assert result.title == "AI Power Theme"


def test_manifest_read_error_has_stable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)

    def failing_read(_fd: int, _size: int) -> bytes:
        raise OSError("simulated read failure")

    monkeypatch.setattr(manifest_module.os, "read", failing_read)

    _assert_error(manifest_path, report_root, "MANIFEST_INVALID")


def test_artifact_read_error_has_stable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    artifact_inode = manifest_path.with_name("report.md").stat().st_ino
    original_read = manifest_module.os.read

    def selectively_failing_read(fd: int, size: int) -> bytes:
        if os.fstat(fd).st_ino == artifact_inode:
            raise OSError("simulated artifact read failure")
        return original_read(fd, size)

    monkeypatch.setattr(manifest_module.os, "read", selectively_failing_read)

    _assert_error(manifest_path, report_root, "ARTIFACT_FILE_INVALID")


@pytest.mark.parametrize("symlink_level", ["theme", "version"])
def test_rejects_symlinked_theme_or_version_directory(
    tmp_path: Path, symlink_level: str
) -> None:
    real_root, real_manifest, _ = _write_package(tmp_path / "real")
    report_root = tmp_path / "reports" / "theme-research"
    report_root.mkdir(parents=True)
    if symlink_level == "theme":
        (report_root / "ai-power").symlink_to(real_root / "ai-power", target_is_directory=True)
        manifest_path = report_root / "ai-power" / "2026-07-31-v1" / "manifest.json"
    else:
        theme_dir = report_root / "ai-power"
        theme_dir.mkdir()
        (theme_dir / "2026-07-31-v1").symlink_to(
            real_manifest.parent, target_is_directory=True
        )
        manifest_path = theme_dir / "2026-07-31-v1" / "manifest.json"

    _assert_error(manifest_path, report_root, "DIRECTORY_INVALID")


def test_rejects_symlinked_artifact(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path)
    artifact_path = manifest_path.with_name("report.md")
    real_artifact = artifact_path.with_name("real.md")
    artifact_path.rename(real_artifact)
    artifact_path.symlink_to(real_artifact.name)

    _assert_error(manifest_path, report_root, "ARTIFACT_FILE_INVALID")


def test_rejects_non_regular_artifact(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable")
    report_root, manifest_path, _ = _write_package(tmp_path)
    artifact_path = manifest_path.with_name("report.md")
    artifact_path.unlink()
    os.mkfifo(artifact_path)

    _assert_error(manifest_path, report_root, "ARTIFACT_FILE_INVALID")


@pytest.mark.parametrize(
    ("directory_theme", "directory_version", "manifest_theme", "manifest_version"),
    [
        ("ai-power", "2026-v1", "other-theme", "2026-v1"),
        ("ai-power", "2026-v1", "ai-power", "2026-v2"),
    ],
)
def test_manifest_identity_must_match_directory_names(
    tmp_path: Path,
    directory_theme: str,
    directory_version: str,
    manifest_theme: str,
    manifest_version: str,
) -> None:
    report_root, manifest_path, _ = _write_package(
        tmp_path,
        theme_id=directory_theme,
        version=directory_version,
        overrides={"theme_id": manifest_theme, "version": manifest_version},
    )

    _assert_error(manifest_path, report_root, "DIRECTORY_MISMATCH")


def test_rejects_manifest_outside_report_root(tmp_path: Path) -> None:
    report_root, _, _ = _write_package(tmp_path / "inside")
    _, outside_manifest, _ = _write_package(tmp_path / "outside")

    _assert_error(outside_manifest, report_root, "MANIFEST_OUTSIDE_ROOT")


def test_metadata_must_be_an_object(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path, overrides={"metadata": []})

    _assert_error(manifest_path, report_root, "METADATA_INVALID")


def test_unknown_top_level_fields_are_rejected_predictably(tmp_path: Path) -> None:
    report_root, manifest_path, _ = _write_package(tmp_path, overrides={"future_field": 1})

    error = _assert_error(manifest_path, report_root, "UNKNOWN_TOP_LEVEL_FIELD")
    assert error.details == {"fields": ["future_field"]}
