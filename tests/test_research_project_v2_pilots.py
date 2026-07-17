from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.cli import cli
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.gates import evaluate_gate
from stock_research.research_project_v2.layout import ResearchProjectLayout
from stock_research.research_project_v2.loader import (
    list_project_slugs,
    load_index,
    load_project,
    load_version,
    validate_schema_payload,
)
from stock_research.research_project_v2.references import audit_references
from stock_research.research_project_v2.semantic import validate_version_semantics


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/research_projects/v2"
FIXTURES = ARTIFACT_ROOT / "fixtures"
SLUGS = {
    "ai_compute_pcb_value_migration",
    "humanoid_robot_scale_up_bottlenecks",
    "new_energy_storage_route_competition",
    "high_end_medical_device_commercialization",
}
EXPECTED = {
    "ai_compute_pcb_value_migration": (
        "AI服务器架构升级如何改变PCB及上游材料的价值分配？",
        "system_architecture",
        ["manufacturing_process"],
    ),
    "humanoid_robot_scale_up_bottlenecks": (
        "人形机器人从样机走向量产，首先受限于哪些部件与工程化环节？",
        "complex_system",
        ["engineering_scale_up"],
    ),
    "new_energy_storage_route_competition": (
        "新型储能的路线竞争最终由性能、制造成本、系统经济性还是基础设施约束决定？",
        "technology_route",
        ["infrastructure_economics"],
    ),
    "high_end_medical_device_commercialization": (
        "高端医疗器械从技术验证走向规模商业化，关键瓶颈在产品性能、监管准入、临床采用还是供应链与服务能力？",
        "lifecycle",
        ["regulation", "system_architecture"],
    ),
}
PROHIBITED = ("buy", "sell", "买入", "卖出", "推荐", "目标价")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bytes_under(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _rehash(payload: dict[str, object]) -> None:
    payload["content_hash"] = content_sha256(
        payload, excluded_paths={("content_hash",)}
    )


def test_four_pilot_artifacts_are_complete_research_designs():
    assert set(list_project_slugs()) == SLUGS
    index = load_index()
    assert [row["project_slug"] for row in index["projects"]] == sorted(SLUGS)
    assert index["artifact_version"] == "2.0.0"

    for slug in sorted(SLUGS):
        identity = load_project(slug)
        version = load_version(slug, "0.1.0")
        snapshot = version["snapshot"]
        question, primary_method, secondary_methods = EXPECTED[slug]
        assert identity["current_version"] == f"research_version:{slug}:0.1.0"
        assert identity["latest_reviewed_version"] is None
        assert identity["latest_published_version"] is None
        assert identity["current_lifecycle_state"] == "research_ready"
        assert version["content_hash"] == content_sha256(
            version, excluded_paths={("content_hash",)}
        )
        validate_version_semantics(version)
        assert audit_references(version) == {
            "status": "pass",
            "total": 2,
            "resolved": 2,
            "issues": [],
        }
        assert evaluate_gate(version, "design").status in {"pass", "pass_with_warnings"}
        assert evaluate_gate(version, "evidence").status == "not_applicable"
        assert evaluate_gate(version, "publication").status == "not_applicable"
        assert snapshot["scope"]["primary_question"] == question
        assert snapshot["router_decision"]["primary_method"] == primary_method
        assert snapshot["router_decision"]["secondary_methods"] == secondary_methods
        assert snapshot["router_decision"]["manual_override"] is False
        assert snapshot["router_decision"]["override_reason"] is None
        questions = snapshot["questions"]
        assert len(questions) >= 7
        assert {item["question_type"] for item in questions} == {
            "primary", "mechanism", "constraint", "economics", "company_capture",
            "counterfactual", "validation",
        }
        assert sum(item["required_for_gate"] for item in questions) >= 6
        requirement_targets = {
            (item["target_type"], item["target_id"])
            for item in snapshot["evidence_requirements"]
        }
        assert all(
            ("research_question", item["question_id"]) in requirement_targets
            for item in questions if item["required_for_gate"]
        )
        primary_claim = next(item for item in snapshot["claims"] if item["claim_kind"] == "primary")
        assert ("research_claim", primary_claim["claim_id"]) in requirement_targets
        assert primary_claim["importance"] >= 0.9
        assert primary_claim["validation_metric_ids"]
        assert primary_claim["invalidation_condition_ids"]
        assert all(item["epistemic_type"] == "hypothesis" for item in snapshot["claims"])
        assert all(item["claim_status"] in {"hypothesis", "under_test"} for item in snapshot["claims"])
        assert all(0.25 <= item["confidence"] <= 0.45 for item in snapshot["claims"])
        assert snapshot["evidence_assessments"] == []
        assert snapshot["company_capture_assessments"] == []
        assert 4 <= len(snapshot["causal_nodes"]) <= 6
        assert snapshot["validation_metrics"] and snapshot["invalidation_conditions"]
        assert all(item["status"] == "planned" for item in snapshot["validation_metrics"])
        assert all(item["triggered_at"] is None for item in snapshot["invalidation_conditions"])
        assert not any(word in json.dumps(version, ensure_ascii=False).lower() for word in PROHIBITED)
        project_dir = ARTIFACT_ROOT / "projects" / slug
        assert (project_dir / "events/events.jsonl").read_bytes() == b""
        manifest = [json.loads(line) for line in (project_dir / "version_manifest.jsonl").read_text().splitlines()]
        assert manifest == [{
            "version_id": version["version_id"],
            "semantic_version": "0.1.0",
            "parent_version_id": None,
            "relative_path": "versions/v0.1.0.json",
            "content_hash": version["content_hash"],
            "created_at": version["created_at"],
        }]


def test_static_valid_and_invalid_fixtures_have_exact_failures():
    valid = _json(FIXTURES / "valid/research_design_minimal_v2.json")
    assert valid["content_hash"] == content_sha256(
        valid, excluded_paths={("content_hash",)}
    )
    validate_schema_payload("research_version_v2", valid)
    validate_version_semantics(valid)
    assert evaluate_gate(valid, "design").status in {"pass", "pass_with_warnings"}

    semantic_failures = {
        "question_dependency_cycle.json": "RESEARCH_PROJECT_QUESTION_DEPENDENCY_CYCLE",
        "duplicate_claim_id.json": "RESEARCH_PROJECT_DUPLICATE_OBJECT_ID",
        "unmarked_causal_cycle.json": "RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE",
    }
    for name, code in semantic_failures.items():
        invalid = _json(FIXTURES / "invalid" / name)
        assert invalid["content_hash"] == content_sha256(
            invalid, excluded_paths={("content_hash",)}
        )
        validate_schema_payload("research_version_v2", invalid)
        with pytest.raises(ResearchProjectV2Error) as exc_info:
            validate_version_semantics(invalid)
        assert exc_info.value.code == code

    missing = _json(FIXTURES / "invalid/missing_reference.json")
    assert missing["content_hash"] == content_sha256(
        missing, excluded_paths={("content_hash",)}
    )
    validate_schema_payload("research_version_v2", missing)
    validate_version_semantics(missing)
    assert audit_references(missing)["issues"] == [
        {
            "reference_id": "reference:ai_compute_pcb_value_migration:background",
            "status": "missing",
        }
    ]
    mismatch = _json(FIXTURES / "invalid/hash_mismatch.json")
    assert mismatch["content_hash"] != content_sha256(mismatch, excluded_paths={("content_hash",)})

    for name in (
        "premature_supported_claim.json",
        "evidence_assessment_in_research_design.json",
        "company_capture_in_research_design.json",
    ):
        invalid = _json(FIXTURES / "invalid" / name)
        assert invalid["content_hash"] == content_sha256(
            invalid, excluded_paths={("content_hash",)}
        )
        with pytest.raises(ResearchProjectV2Error) as exc_info:
            validate_schema_payload("research_version_v2", invalid)
        assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"

    invalid_layout = ResearchProjectLayout(FIXTURES / "invalid/invalid_version_manifest")
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=invalid_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"


def test_hash_mismatch_fixture_exercises_loader_and_cli_exit_five(tmp_path, capsys):
    version = _json(FIXTURES / "invalid/hash_mismatch.json")
    slug = version["project_id"].split(":", 1)[1]
    layout = ResearchProjectLayout(tmp_path / "hash-mismatch-layout")
    project_dir = layout.project_dir(slug)
    identity = _json(ARTIFACT_ROOT / "projects" / slug / "project.json")
    _write_json(project_dir / "project.json", identity)
    _write_json(project_dir / "versions/v0.1.0.json", version)
    manifest = {
        "version_id": version["version_id"],
        "semantic_version": version["semantic_version"],
        "parent_version_id": version["parent_version_id"],
        "relative_path": "versions/v0.1.0.json",
        "content_hash": version["content_hash"],
        "created_at": version["created_at"],
    }
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "version_manifest.jsonl").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version(slug, "0.1.0", layout=layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"
    for command in (
        ["show", "--project", slug, "--version", "0.1.0"],
        ["validate", "--project", slug, "--version", "0.1.0"],
    ):
        assert cli(command, layout=layout) == 5
        assert json.loads(capsys.readouterr().out)["error"]["code"] == (
            "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"
        )


def test_rebuild_index_is_dry_run_safe_write_idempotent_and_tamper_strict(tmp_path, capsys):
    dry_layout = ResearchProjectLayout(ARTIFACT_ROOT)
    before = _bytes_under(ARTIFACT_ROOT)
    assert cli(["rebuild-index"], layout=dry_layout) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["status"] == "planned"
    assert set(planned["projects"]) == SLUGS
    assert _bytes_under(ARTIFACT_ROOT) == before

    copied_root = tmp_path / "v2"
    layout = ResearchProjectLayout(copied_root)
    slug = "ai_compute_pcb_value_migration"
    project_dir = layout.project_dir(slug)
    manifest_path = layout.project_dir(slug) / "version_manifest.jsonl"
    old_version_path = project_dir / "versions/v0.0.0.json"
    new_version_path = project_dir / "versions/v0.1.0.json"
    identity = _json(ARTIFACT_ROOT / "projects" / slug / "project.json")
    current = _json(ARTIFACT_ROOT / "projects" / slug / "versions/v0.1.0.json")
    old_version = json.loads(
        json.dumps(current, ensure_ascii=False).replace(":0.1.0", ":0.0.0")
    )
    old_version.update(
        semantic_version="0.0.0",
        parent_version_id=None,
        created_at="2026-07-16T00:00:00Z",
    )
    _rehash(old_version)
    new_version = deepcopy(current)
    new_version["parent_version_id"] = old_version["version_id"]
    new_version["content_hash"] = "0" * 64
    _write_json(project_dir / "project.json", identity)
    _write_json(old_version_path, old_version)
    _write_json(new_version_path, new_version)
    old_row = {
        "version_id": old_version["version_id"],
        "semantic_version": "0.0.0",
        "parent_version_id": None,
        "relative_path": "versions/v0.0.0.json",
        "content_hash": old_version["content_hash"],
        "created_at": old_version["created_at"],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(old_row, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    old_manifest_bytes = manifest_path.read_bytes()
    old_version_bytes = old_version_path.read_bytes()
    assert cli(["rebuild-index", "--write"], layout=layout) == 0
    capsys.readouterr()
    rebuilt = load_version(slug, "0.1.0", layout=layout)
    assert rebuilt["content_hash"] != "0" * 64
    assert old_version_path.read_bytes() == old_version_bytes
    rebuilt_manifest = manifest_path.read_bytes()
    assert rebuilt_manifest.startswith(old_manifest_bytes)
    assert len(rebuilt_manifest.splitlines()) == len(old_manifest_bytes.splitlines()) + 1
    index = load_index(layout=layout)
    assert index == {
        "artifact_version": "2.0.0",
        "generated_at": "2026-07-17T00:00:00Z",
        "projects": [
            {
                "project_id": identity["project_id"],
                "project_slug": slug,
                "title": identity["title"],
                "current_lifecycle_state": "research_ready",
                "current_version": identity["current_version"],
                "latest_reviewed_version": None,
                "latest_published_version": None,
                "relative_path": f"projects/{slug}/project.json",
            }
        ],
    }
    validate_schema_payload("research_project_index_v2", index)
    first = _bytes_under(copied_root)
    assert cli(["rebuild-index", "--write"], layout=layout) == 0
    capsys.readouterr()
    assert _bytes_under(copied_root) == first

    old_version["change_summary"] += " tampered"
    _write_json(old_version_path, old_version)
    before_tamper_check = _bytes_under(copied_root)
    assert cli(["rebuild-index", "--write"], layout=layout) == 5
    error = json.loads(capsys.readouterr().out)
    assert error["error"]["code"] == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"
    assert _bytes_under(copied_root) == before_tamper_check


def test_cli_acceptance_for_seeded_pilots_and_rebuild_help(capsys):
    assert cli(["--help"]) == 0
    assert "rebuild-index" in capsys.readouterr().out
    assert cli(["list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["project_slug"] for item in listed["projects"]] == sorted(SLUGS)
    assert cli(["validate", "--all"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"
    assert cli([
        "gate", "--project", "ai_compute_pcb_value_migration",
        "--version", "0.1.0", "--gate", "design",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] in {"pass", "pass_with_warnings"}
