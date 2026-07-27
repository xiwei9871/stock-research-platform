from pathlib import Path

import pytest

from stock_research.runtime_provenance import (
    build_runtime_provenance,
    runtime_provenance,
)


def test_build_runtime_provenance_rejects_package_outside_release_root(tmp_path):
    release_root = tmp_path / "release"
    package_file = tmp_path / "release-old" / "src" / "stock_research" / "__init__.py"

    with pytest.raises(RuntimeError, match="python package root does not match release root"):
        build_runtime_provenance(
            release_root=release_root,
            release_id="release-1",
            frontend_build_id="release-1",
            package_file=package_file,
        )


def test_build_runtime_provenance_rejects_import_root_symlink_escape(tmp_path):
    release_root = tmp_path / "release"
    external_package_root = tmp_path / "old-release" / "src" / "stock_research"
    external_package_root.mkdir(parents=True)
    package_file = external_package_root / "__init__.py"
    package_file.touch()
    (release_root / "src").mkdir(parents=True)
    (release_root / "src" / "stock_research").symlink_to(
        external_package_root,
        target_is_directory=True,
    )

    with pytest.raises(RuntimeError, match="python package root does not match release root"):
        build_runtime_provenance(
            release_root=release_root,
            release_id="release-1",
            frontend_build_id="release-1",
            package_file=package_file,
        )


def test_build_runtime_provenance_allows_release_root_symlink(tmp_path):
    real_release_root = tmp_path / "releases" / "release-1"
    package_root = real_release_root / "src" / "stock_research"
    package_root.mkdir(parents=True)
    package_file = package_root / "__init__.py"
    package_file.touch()
    release_link = tmp_path / "current"
    release_link.symlink_to(real_release_root, target_is_directory=True)

    payload = build_runtime_provenance(
        release_root=release_link,
        release_id="release-1",
        frontend_build_id="release-1",
        package_file=package_file,
    )

    assert payload["source_root"] == str(real_release_root.resolve())
    assert payload["python_package_root"] == str(package_root.resolve())


def test_build_runtime_provenance_rejects_nonempty_release_id_mismatch(tmp_path):
    package_file = tmp_path / "src" / "stock_research" / "__init__.py"

    with pytest.raises(RuntimeError, match="release IDs do not match"):
        build_runtime_provenance(
            release_root=tmp_path,
            release_id="api-release",
            frontend_build_id="frontend-release",
            package_file=package_file,
        )


def test_build_runtime_provenance_returns_resolved_runtime_identity(tmp_path):
    package_file = tmp_path / "src" / "stock_research" / "__init__.py"

    payload = build_runtime_provenance(
        release_root=tmp_path,
        release_id="release-1",
        frontend_build_id="release-1",
        package_file=package_file,
    )

    assert payload == {
        "release_id": "release-1",
        "source_root": str(tmp_path.resolve()),
        "python_package_root": str(package_file.parent.resolve()),
        "frontend_build_id": "release-1",
    }


def test_runtime_provenance_reads_environment_and_allows_empty_development_ids(
    monkeypatch,
    tmp_path,
):
    package_file = tmp_path / "src" / "stock_research" / "__init__.py"
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ROOT", str(tmp_path))
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ID", "")
    monkeypatch.setenv("STOCK_RESEARCH_FRONTEND_BUILD_ID", "")

    payload = runtime_provenance(package_file=package_file)

    assert payload["source_root"] == str(tmp_path.resolve())
    assert payload["release_id"] == ""
    assert payload["frontend_build_id"] == ""


def test_runtime_provenance_defaults_release_root_from_module_location(monkeypatch):
    monkeypatch.delenv("STOCK_RESEARCH_RELEASE_ROOT", raising=False)
    monkeypatch.delenv("STOCK_RESEARCH_RELEASE_ID", raising=False)
    monkeypatch.delenv("STOCK_RESEARCH_FRONTEND_BUILD_ID", raising=False)

    payload = runtime_provenance()

    expected_root = Path(__file__).resolve().parents[1]
    assert payload["source_root"] == str(expected_root)


def test_runtime_provenance_reads_frontend_build_id_from_dist_metadata(monkeypatch, tmp_path):
    package_file = tmp_path / "src" / "stock_research" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    metadata_file = tmp_path / "dashboard" / "dist" / "release.json"
    metadata_file.parent.mkdir(parents=True)
    metadata_file.write_text('{"release_id":"release-1"}', encoding="utf-8")
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ROOT", str(tmp_path))
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ID", "release-1")
    monkeypatch.setenv("STOCK_RESEARCH_FRONTEND_BUILD_ID", "release-1")

    payload = runtime_provenance(package_file=package_file)

    assert payload["frontend_build_id"] == "release-1"


def test_runtime_provenance_rejects_old_dist_with_new_api_release(monkeypatch, tmp_path):
    package_file = tmp_path / "src" / "stock_research" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    metadata_file = tmp_path / "dashboard" / "dist" / "release.json"
    metadata_file.parent.mkdir(parents=True)
    metadata_file.write_text('{"release_id":"old-release"}', encoding="utf-8")
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ROOT", str(tmp_path))
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ID", "new-release")
    monkeypatch.setenv("STOCK_RESEARCH_FRONTEND_BUILD_ID", "new-release")

    with pytest.raises(RuntimeError, match="frontend release metadata does not match"):
        runtime_provenance(package_file=package_file)


def test_runtime_provenance_requires_metadata_for_declared_frontend_release(monkeypatch, tmp_path):
    package_file = tmp_path / "src" / "stock_research" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ROOT", str(tmp_path))
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ID", "release-1")
    monkeypatch.setenv("STOCK_RESEARCH_FRONTEND_BUILD_ID", "release-1")

    with pytest.raises(RuntimeError, match="frontend release metadata is missing"):
        runtime_provenance(package_file=package_file)


def test_runtime_provenance_allows_empty_development_metadata(monkeypatch, tmp_path):
    package_file = tmp_path / "src" / "stock_research" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    metadata_file = tmp_path / "dashboard" / "dist" / "release.json"
    metadata_file.parent.mkdir(parents=True)
    metadata_file.write_text('{"release_id":""}', encoding="utf-8")
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ROOT", str(tmp_path))
    monkeypatch.setenv("STOCK_RESEARCH_RELEASE_ID", "")
    monkeypatch.setenv("STOCK_RESEARCH_FRONTEND_BUILD_ID", "")

    payload = runtime_provenance(package_file=package_file)

    assert payload["frontend_build_id"] == ""
