from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

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
    ("case_name", "expected"),
    [
        ("missing_research_layer", "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"),
        ("company_capture_layer", "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"),
        ("missing_upstream_r1_version", "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID"),
        ("upstream_content_hash_drift", "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID"),
        ("duplicate_query_id", "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID"),
        ("forbidden_company_capability_collection", "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"),
        ("manifest_hash_mismatch", "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION"),
    ],
)
def test_invalid_storage_fixture_reports_intended_error(tmp_path: Path, case_name: str, expected: str) -> None:
    root = tmp_path / "v2_1"
    shutil.copytree(R2A / "schema", root / "schema")
    fixture = R2A / "fixtures/invalid" / case_name
    slug = json.loads((fixture / "project.json").read_text())["project_slug"]
    shutil.copytree(fixture, root / "projects" / slug)
    layout = LayeredResearchLayout(root)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_industry_version(slug, layout=layout)
    assert exc_info.value.code == expected


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
    assert expected_check in failed
