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
