from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import threading

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2_1.gates import evaluate_industry_design_gate
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    list_layered_project_slugs,
    load_industry_version,
    load_layered_project,
    resolve_upstream_r1_version,
)
from stock_research.research_project_v2_1.maintenance import rebuild_layered_index
from stock_research.research_project_v2_1 import maintenance as maintenance_module


ROOT = Path(__file__).resolve().parents[1]
R1 = ROOT / "artifacts/research_projects/v2"
R2A = ROOT / "artifacts/research_projects/v2_1"
EXPECTED = {
    "ai_compute_pcb_industry_bottleneck": "ai_compute_pcb_value_migration",
    "humanoid_robot_industry_bottleneck": "humanoid_robot_scale_up_bottlenecks",
    "new_energy_storage_industry_bottleneck": "new_energy_storage_route_competition",
    "high_end_medical_device_industry_bottleneck": "high_end_medical_device_commercialization",
}


def test_rebuild_layered_index_public_api_exists() -> None:
    assert callable(rebuild_layered_index)


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode())
        digest.update(file_path.read_bytes())
    return digest.hexdigest()


def _copy_layout(tmp_path: Path, slug: str | None = None) -> LayeredResearchLayout:
    root = tmp_path / "v2_1"
    shutil.copytree(R2A / "schema", root / "schema")
    (root / ".maintenance.lock").touch(mode=0o600)
    (root / "projects").mkdir()
    selected = list(EXPECTED) if slug is None else [slug]
    for project_slug in selected:
        shutil.copytree(R2A / "projects" / project_slug, root / "projects" / project_slug)
    return LayeredResearchLayout(root)


def test_four_layered_projects_resolve_exact_r1_baselines_and_pass_gate() -> None:
    layout = LayeredResearchLayout.default()
    assert list_layered_project_slugs(layout=layout) == sorted(EXPECTED)
    assert sorted(path.name for path in (R1 / "projects").iterdir()) == sorted(EXPECTED.values())
    for slug, upstream_slug in EXPECTED.items():
        identity = load_layered_project(slug, layout=layout)
        version = load_industry_version(slug, layout=layout)
        reference = version["snapshot"]["upstream_research_refs"][0]
        upstream = resolve_upstream_r1_version(reference)
        assert upstream["project_id"] == f"research_project:{upstream_slug}"
        assert upstream["version_id"] == f"research_version:{upstream_slug}:0.1.0"
        assert upstream["content_hash"] == reference["upstream_content_hash"]
        assert evaluate_industry_design_gate(identity, version)["status"] == "pass"


def test_pilots_are_design_only_and_have_no_downstream_outputs() -> None:
    empty = {
        "source_candidates", "source_relationships", "evidence_artifacts",
        "normalized_documents", "industry_evidence_assessments", "conflict_summaries",
    }
    forbidden = {"candidate_companies", "company_capture_assessments", "stock_rating", "company_capability_collection"}
    for slug in EXPECTED:
        version = load_industry_version(slug)
        snapshot = version["snapshot"]
        assert len(snapshot["questions"]) >= 4
        assert len(snapshot["evidence_requirements"]) >= 4
        assert snapshot["search_plans"]
        assert all(snapshot[key] == [] for key in empty)
        assert all(claim["epistemic_type"] == "hypothesis" for claim in snapshot["claims"])
        assert all(claim["claim_status"] in {"hypothesis", "under_test"} for claim in snapshot["claims"])
        serialized = json.dumps(version, ensure_ascii=False)
        assert all(f'"{key}"' not in serialized for key in forbidden)


def test_pilot_provenance_is_bound_to_current_version_and_real_agent_run() -> None:
    for slug in EXPECTED:
        version = load_industry_version(slug)
        seen = 0
        stack: list[object] = [version["snapshot"]]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                provenance = value.get("provenance")
                if isinstance(provenance, dict):
                    seen += 1
                    assert provenance["created_in_version"] == version["version_id"]
                    assert provenance["agent_run_id"] == "research-project-v2-1-r2a-pilots"
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
        assert seen > 0


def test_rebuild_is_preview_safe_idempotent_and_does_not_touch_r1(tmp_path: Path) -> None:
    layout = _copy_layout(tmp_path)
    before_r1 = _tree_hash(R1)
    before = _tree_hash(layout.root)
    preview = rebuild_layered_index(False, layout)
    assert preview["status"] == "planned"
    assert _tree_hash(layout.root) == before
    rebuild_layered_index(True, layout)
    first = _tree_hash(layout.root)
    rebuild_layered_index(True, layout)
    assert _tree_hash(layout.root) == first
    assert _tree_hash(R1) == before_r1


def test_rebuild_bootstraps_placeholder_and_preserves_manifest_prefix(tmp_path: Path) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    project = layout.project_dir(slug)
    version_path = project / "versions/v0.1.0.json"
    version = json.loads(version_path.read_text())
    version["content_hash"] = "0" * 64
    version_path.write_text(json.dumps(version, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    manifest = project / "version_manifest.jsonl"
    manifest.write_bytes(b"")
    rebuild_layered_index(True, layout)
    assert json.loads(version_path.read_text())["content_hash"] != "0" * 64
    prefix = manifest.read_bytes()
    rebuild_layered_index(True, layout)
    assert manifest.read_bytes() == prefix


@pytest.mark.parametrize("write", [False, True])
def test_rebuild_rejects_unmanifested_filename_semver_mismatch_without_writes(
    tmp_path: Path,
    write: bool,
) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    project = layout.project_dir(slug)
    version_path = project / "versions/v0.1.0.json"
    version = json.loads(version_path.read_text())
    version["semantic_version"] = "9.9.9"
    version["content_hash"] = "0" * 64
    version_path.write_text(json.dumps(version, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    (project / "version_manifest.jsonl").write_bytes(b"")
    before = _tree_hash(layout.root)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        rebuild_layered_index(write, layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION"
    assert exc_info.value.details["reason"] == "version semantic_version mismatch"
    assert _tree_hash(layout.root) == before


def test_rebuild_generated_at_uses_rfc3339_instant_order(tmp_path: Path) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    project = layout.project_dir(slug)
    identity_path = project / "project.json"
    version_path = project / "versions/v0.1.0.json"
    identity = json.loads(identity_path.read_text())
    version = json.loads(version_path.read_text())
    identity["created_at"] = "2026-07-18T10:00:00+08:00"
    version["created_at"] = "2026-07-18T03:00:00Z"
    version["content_hash"] = content_sha256(version, excluded_paths={("content_hash",)})
    row = {
        "version_id": version["version_id"],
        "semantic_version": version["semantic_version"],
        "parent_version_id": version["parent_version_id"],
        "relative_path": "versions/v0.1.0.json",
        "content_hash": version["content_hash"],
        "created_at": version["created_at"],
    }
    identity_path.write_text(json.dumps(identity, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    version_path.write_text(json.dumps(version, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    (project / "version_manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )

    rebuild_layered_index(True, layout)

    assert json.loads(layout.index_path.read_text())["generated_at"] == "2026-07-18T03:00:00Z"


def test_rebuild_rejects_symlink(tmp_path: Path) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    target = layout.project_dir(slug) / "versions/v0.1.0.json"
    original = target.read_bytes()
    target.unlink()
    target.symlink_to(tmp_path / "outside.json")
    (tmp_path / "outside.json").write_bytes(original)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        rebuild_layered_index(False, layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION"


def test_rebuild_allows_only_the_stable_lock_at_layered_root(tmp_path: Path) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    assert rebuild_layered_index(False, layout)["status"] == "planned"
    unexpected = layout.root / ".unexpected"
    unexpected.write_text("x", encoding="utf-8")

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        rebuild_layered_index(False, layout)

    assert exc_info.value.details["reason"] == "unexpected layered root entry"
    assert exc_info.value.details["path"] == str(unexpected)


def test_rebuild_rolls_back_all_files_on_atomic_failure(tmp_path: Path, monkeypatch) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    project = layout.project_dir(slug)
    version_path = project / "versions/v0.1.0.json"
    version = json.loads(version_path.read_text())
    version["content_hash"] = "0" * 64
    version_path.write_text(json.dumps(version, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    (project / "version_manifest.jsonl").write_bytes(b"")
    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
    real = maintenance_module._atomic_write
    def fail_index(path: Path, data: bytes) -> None:
        if path == layout.index_path:
            path.parent.mkdir(parents=True, exist_ok=True)
            raise OSError("injected")
        real(path, data)
    monkeypatch.setattr(maintenance_module, "_atomic_write", fail_index)
    with pytest.raises(OSError, match="injected"):
        rebuild_layered_index(True, layout)
    assert {path: path.read_bytes() for path in project.rglob("*") if path.is_file()} == before
    assert not layout.index_path.exists()
    assert not layout.index_path.parent.exists()


def test_rebuild_detects_post_write_target_rebinding_and_rolls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    _prepare_unmanifested(layout, slug)
    version_path = layout.project_dir(slug) / "versions/v0.1.0.json"
    original = version_path.read_bytes()
    outside = tmp_path / "outside-version.json"
    outside.write_bytes(b"outside")
    real_write = maintenance_module._atomic_write
    swapped = False

    def swap_after_write(path: Path, data: bytes) -> None:
        nonlocal swapped
        real_write(path, data)
        if path == version_path and not swapped:
            swapped = True
            path.unlink()
            path.symlink_to(outside)

    monkeypatch.setattr(maintenance_module, "_atomic_write", swap_after_write)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        rebuild_layered_index(True, layout)

    assert exc_info.value.details["reason"] == "unsafe managed path"
    assert not version_path.is_symlink()
    assert version_path.read_bytes() == original


def _prepare_unmanifested(layout: LayeredResearchLayout, slug: str) -> None:
    project = layout.project_dir(slug)
    version_path = project / "versions/v0.1.0.json"
    version = json.loads(version_path.read_text())
    version["content_hash"] = "0" * 64
    version_path.write_text(json.dumps(version, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    (project / "version_manifest.jsonl").write_bytes(b"")


def test_reader_blocks_during_mid_commit_and_then_loads_consistent_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    _prepare_unmanifested(layout, slug)
    paused = threading.Event()
    release = threading.Event()
    reader_done = threading.Event()
    errors: list[BaseException] = []
    real_write = maintenance_module._atomic_write
    first = True

    def pause_after_first_write(path: Path, data: bytes) -> None:
        nonlocal first
        real_write(path, data)
        if first:
            first = False
            paused.set()
            assert release.wait(5)

    def writer() -> None:
        try:
            rebuild_layered_index(True, layout)
        except BaseException as exc:
            errors.append(exc)

    def reader() -> None:
        try:
            load_industry_version(slug, layout=layout)
        except BaseException as exc:
            errors.append(exc)
        finally:
            reader_done.set()

    monkeypatch.setattr(maintenance_module, "_atomic_write", pause_after_first_write)
    writer_thread = threading.Thread(target=writer)
    writer_thread.start()
    assert paused.wait(5)
    reader_thread = threading.Thread(target=reader)
    reader_thread.start()
    assert not reader_done.wait(0.2)
    release.set()
    writer_thread.join(5)
    reader_thread.join(5)
    assert not errors
    assert reader_done.is_set()


def test_two_writers_serialize_before_second_manifest_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    slug = next(iter(EXPECTED))
    layout = _copy_layout(tmp_path, slug)
    _prepare_unmanifested(layout, slug)
    paused = threading.Event()
    release = threading.Event()
    second_manifest_read = threading.Event()
    errors: list[BaseException] = []
    real_write = maintenance_module._atomic_write
    real_manifest = maintenance_module._manifest
    manifest_reads = 0
    first_write = True

    def observe_manifest(path: Path, project_slug: str):
        nonlocal manifest_reads
        manifest_reads += 1
        if manifest_reads >= 2:
            second_manifest_read.set()
        return real_manifest(path, project_slug)

    def pause_writer(path: Path, data: bytes) -> None:
        nonlocal first_write
        real_write(path, data)
        if first_write:
            first_write = False
            paused.set()
            assert release.wait(5)

    def run_writer() -> None:
        try:
            rebuild_layered_index(True, layout)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(maintenance_module, "_manifest", observe_manifest)
    monkeypatch.setattr(maintenance_module, "_atomic_write", pause_writer)
    first_thread = threading.Thread(target=run_writer)
    second_thread = threading.Thread(target=run_writer)
    first_thread.start()
    assert paused.wait(5)
    second_thread.start()
    assert not second_manifest_read.wait(0.2)
    release.set()
    first_thread.join(5)
    second_thread.join(5)
    assert not errors
    assert second_manifest_read.is_set()


@pytest.mark.parametrize(
    "case_name",
    [
        "missing_research_layer", "company_capture_layer", "missing_upstream_r1_version",
        "upstream_content_hash_drift", "plan_missing_counter", "plan_stock_terms",
        "duplicate_query_id", "forbidden_company_capability_collection", "manifest_hash_mismatch",
    ],
)
def test_invalid_fixture_has_a_self_consistent_embedded_hash(case_name: str) -> None:
    fixture = R2A / "fixtures/invalid" / case_name
    version = json.loads((fixture / "versions/v0.1.0.json").read_text())
    assert version["content_hash"] == content_sha256(version, excluded_paths={("content_hash",)})


@pytest.mark.parametrize(
    ("case_name", "expected", "expected_reason"),
    [
        ("missing_research_layer", "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID", None),
        ("company_capture_layer", "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID", None),
        ("missing_upstream_r1_version", "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID", "version could not be loaded: RESEARCH_PROJECT_VERSION_NOT_FOUND"),
        ("upstream_content_hash_drift", "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID", "content_hash mismatch"),
        ("duplicate_query_id", "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID", "duplicate query id"),
        ("forbidden_company_capability_collection", "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID", None),
        ("manifest_hash_mismatch", "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION", "manifest content_hash mismatch"),
    ],
)
def test_invalid_storage_fixture_reports_intended_error(
    tmp_path: Path,
    case_name: str,
    expected: str,
    expected_reason: str | None,
) -> None:
    root = tmp_path / "v2_1"
    shutil.copytree(R2A / "schema", root / "schema")
    fixture = R2A / "fixtures/invalid" / case_name
    slug = json.loads((fixture / "project.json").read_text())["project_slug"]
    shutil.copytree(fixture, root / "projects" / slug)
    layout = LayeredResearchLayout(root)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_industry_version(slug, layout=layout)
    assert exc_info.value.code == expected
    if expected_reason is not None:
        assert exc_info.value.details["reason"] == expected_reason


@pytest.mark.parametrize(
    ("case_name", "expected_check"),
    [
        ("plan_missing_counter", "INDUSTRY_COUNTER_SEARCH_PRESENT"),
        ("plan_stock_terms", "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS"),
    ],
)
def test_invalid_gate_fixture_reports_intended_check(case_name: str, expected_check: str) -> None:
    fixture = R2A / "fixtures/invalid" / case_name
    identity = json.loads((fixture / "project.json").read_text())
    version = json.loads((fixture / "versions/v0.1.0.json").read_text())
    result = evaluate_industry_design_gate(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert failed == {expected_check}
