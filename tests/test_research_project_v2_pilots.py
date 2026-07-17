from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

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
    validate_schema_payload("research_version_v2", valid)
    validate_version_semantics(valid)
    assert evaluate_gate(valid, "design").status in {"pass", "pass_with_warnings"}

    semantic_failures = {
        "question_dependency_cycle.json": "RESEARCH_PROJECT_QUESTION_DEPENDENCY_CYCLE",
        "duplicate_claim_id.json": "RESEARCH_PROJECT_DUPLICATE_OBJECT_ID",
        "unmarked_causal_cycle.json": "RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE",
    }
    for name, code in semantic_failures.items():
        with pytest.raises(ResearchProjectV2Error) as exc_info:
            validate_version_semantics(_json(FIXTURES / "invalid" / name))
        assert exc_info.value.code == code

    missing = _json(FIXTURES / "invalid/missing_reference.json")
    assert audit_references(missing)["issues"] == [
        {"reference_id": "reference:fixture:missing", "status": "missing"}
    ]
    mismatch = _json(FIXTURES / "invalid/hash_mismatch.json")
    assert mismatch["content_hash"] != content_sha256(mismatch, excluded_paths={("content_hash",)})

    for name in (
        "premature_supported_claim.json",
        "evidence_assessment_in_research_design.json",
        "company_capture_in_research_design.json",
    ):
        invalid = _json(FIXTURES / "invalid" / name)
        with pytest.raises(ResearchProjectV2Error) as exc_info:
            validate_schema_payload("research_version_v2", invalid)
        assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"

    invalid_layout = ResearchProjectLayout(FIXTURES / "invalid/invalid_version_manifest")
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=invalid_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"


def test_rebuild_index_is_dry_run_safe_write_idempotent_and_tamper_strict(tmp_path, capsys):
    dry_layout = ResearchProjectLayout(ARTIFACT_ROOT)
    before = _bytes_under(ARTIFACT_ROOT)
    assert cli(["rebuild-index"], layout=dry_layout) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["status"] == "planned"
    assert set(planned["projects"]) == SLUGS
    assert _bytes_under(ARTIFACT_ROOT) == before

    copied_root = tmp_path / "v2"
    shutil.copytree(ARTIFACT_ROOT, copied_root)
    layout = ResearchProjectLayout(copied_root)
    slug = sorted(SLUGS)[0]
    manifest_path = layout.project_dir(slug) / "version_manifest.jsonl"
    version_path = layout.project_dir(slug) / "versions/v0.1.0.json"
    manifest_path.write_bytes(b"")
    raw = _json(version_path)
    raw["content_hash"] = "0" * 64
    version_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert cli(["rebuild-index", "--write"], layout=layout) == 0
    capsys.readouterr()
    rebuilt = load_version(slug, "0.1.0", layout=layout)
    assert rebuilt["content_hash"] != "0" * 64
    first = _bytes_under(copied_root)
    assert cli(["rebuild-index", "--write"], layout=layout) == 0
    capsys.readouterr()
    assert _bytes_under(copied_root) == first

    rebuilt["change_summary"] += " tampered"
    version_path.write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
