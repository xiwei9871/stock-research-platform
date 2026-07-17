from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.cli import cli
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.layout import ResearchProjectLayout
from stock_research.research_project_v2.summary import summarize_version


CREATED_AT = "2026-07-17T10:00:00+08:00"


def _provenance(slug: str, version: str) -> dict[str, object]:
    return {
        "created_by": "fixture-author",
        "actor_type": "human",
        "agent_run_id": None,
        "created_at": CREATED_AT,
        "created_in_version": f"research_version:{slug}:{version}",
        "review_status": "unreviewed",
    }


def _version(
    slug: str,
    version: str = "0.1.0",
    *,
    parent_version_id: str | None = None,
) -> dict[str, object]:
    provenance = _provenance(slug, version)
    question = f"Can the {slug} thesis be validated?"
    payload: dict[str, object] = {
        "artifact_version": "2.0.0",
        "version_id": f"research_version:{slug}:{version}",
        "project_id": f"research_project:{slug}",
        "semantic_version": version,
        "parent_version_id": parent_version_id,
        "creation_stage": "research_design",
        "created_at": CREATED_AT,
        "created_by": "fixture-author",
        "change_summary": "Create a complete research design.",
        "change_reason": "Exercise the V2 CLI.",
        "incorporated_event_ids": [],
        "content_hash": "0" * 64,
        "snapshot": {
            "project_lifecycle_state": "research_ready",
            "evidence_stage": "requirements_defined",
            "conclusion_status": "unavailable",
            "investment_status": "not_assessed",
            "scope": {
                "primary_question": question,
                "research_object": f"{slug} technology",
                "included_scope": ["Primary system"],
                "excluded_scope": ["Unrelated systems"],
                "geography": ["Global"],
                "time_horizon": "2026-2030",
                "industry_boundary": "Fixture industry",
                "company_universe_boundary": "Public fixture companies",
                "decision_context": "CLI validation",
                "assumptions": [],
                "known_unknowns": [],
                "stop_conditions": [],
            },
            "router_decision": {
                "primary_method": "system_architecture",
                "secondary_methods": [],
                "routing_reasons": ["System dependencies drive outcomes"],
                "required_research_modules": ["architecture"],
                "excluded_modules": [],
                "confidence": 0.8,
                "manual_override": False,
                "override_reason": None,
                "decided_by": "fixture-author",
                "decided_at": CREATED_AT,
            },
            "questions": [
                {
                    "question_id": f"question:{slug}:primary",
                    "question_type": "primary",
                    "question_text": question,
                    "priority": 1,
                    "required_for_gate": True,
                    "answer_status": "unanswered",
                    "linked_claim_ids": [f"claim:{slug}:primary"],
                    "linked_requirement_ids": [f"requirement:{slug}:primary"],
                    "provenance": provenance,
                    "lifecycle_status": "active",
                },
                {
                    "question_id": f"question:{slug}:counter",
                    "question_type": "counterfactual",
                    "question_text": "What would disprove it?",
                    "priority": 2,
                    "required_for_gate": True,
                    "answer_status": "unanswered",
                    "linked_claim_ids": [f"claim:{slug}:counter"],
                    "linked_requirement_ids": [f"requirement:{slug}:counter"],
                    "provenance": provenance,
                    "lifecycle_status": "active",
                },
            ],
            "question_tree_nodes": [
                {"tree_node_id": f"tree:{slug}:primary", "tree_id": f"tree:{slug}", "question_id": f"question:{slug}:primary", "parent_tree_node_id": None, "order": 1, "branch_role": "root", "dependency_question_ids": []},
                {"tree_node_id": f"tree:{slug}:counter", "tree_id": f"tree:{slug}", "question_id": f"question:{slug}:counter", "parent_tree_node_id": f"tree:{slug}:primary", "order": 2, "branch_role": "counterfactual", "dependency_question_ids": [f"question:{slug}:primary"]},
            ],
            "claims": [
                {"claim_id": f"claim:{slug}:primary", "claim_kind": "primary", "epistemic_type": "hypothesis", "claim_text": "The mechanism creates value.", "claim_status": "hypothesis", "lifecycle_status": "active", "confidence": 0.4, "importance": 1.0, "linked_question_ids": [f"question:{slug}:primary"], "context_reference_ids": [], "created_in_version": f"research_version:{slug}:{version}", "supersedes_claim_id": None, "validation_metric_ids": [f"metric:{slug}:primary"], "invalidation_condition_ids": [f"condition:{slug}:primary"], "provenance": provenance},
                {"claim_id": f"claim:{slug}:counter", "claim_kind": "counter", "epistemic_type": "hypothesis", "claim_text": "A constraint prevents value.", "claim_status": "under_test", "lifecycle_status": "active", "confidence": 0.3, "importance": 0.8, "linked_question_ids": [f"question:{slug}:counter"], "context_reference_ids": [], "created_in_version": f"research_version:{slug}:{version}", "supersedes_claim_id": None, "validation_metric_ids": [], "invalidation_condition_ids": [], "provenance": provenance},
            ],
            "claim_relations": [
                {"relation_id": f"relation:{slug}:counter", "from_claim_id": f"claim:{slug}:counter", "to_claim_id": f"claim:{slug}:primary", "relation_type": "challenges", "relation_summary": "The constraint challenges the thesis.", "created_in_version": f"research_version:{slug}:{version}", "provenance": provenance}
            ],
            "evidence_requirements": [
                {"requirement_id": f"requirement:{slug}:primary", "target_type": "research_question", "target_id": f"question:{slug}:primary", "question_to_resolve": "Can the primary question be answered?", "requirement_type": "validation", "required_source_classes": ["primary"], "required_independence": "independent", "required_freshness": "within_12_months", "required_scope": "global", "minimum_coverage": 1, "conflict_search_required": True, "primary_source_required": True, "collection_status": "not_started", "satisfaction_status": "unsatisfied", "provenance": provenance},
                {"requirement_id": f"requirement:{slug}:counter", "target_type": "research_question", "target_id": f"question:{slug}:counter", "question_to_resolve": "Can the counter question be answered?", "requirement_type": "counterevidence", "required_source_classes": ["primary"], "required_independence": "independent", "required_freshness": "within_12_months", "required_scope": "global", "minimum_coverage": 1, "conflict_search_required": True, "primary_source_required": True, "collection_status": "not_started", "satisfaction_status": "unsatisfied", "provenance": provenance},
            ],
            "references": [],
            "evidence_assessments": [],
            "causal_nodes": [
                {"causal_node_id": f"node:{slug}:mechanism", "node_kind": "mechanism", "node_text": "Mechanism", "lifecycle_status": "active", "provenance": provenance},
                {"causal_node_id": f"node:{slug}:outcome", "node_kind": "outcome", "node_text": "Outcome", "lifecycle_status": "active", "provenance": provenance},
            ],
            "causal_edges": [
                {"causal_edge_id": f"edge:{slug}:primary", "from_causal_node_id": f"node:{slug}:mechanism", "to_causal_node_id": f"node:{slug}:outcome", "relation_type": "causes", "mechanism_text": "The mechanism changes the outcome.", "effect_polarity": "positive", "strength": 0.5, "confidence": 0.4, "time_lag": "12 months", "boundary_condition": None, "feedback_loop_id": None, "supporting_claim_ids": [f"claim:{slug}:primary"], "validation_metric_ids": [f"metric:{slug}:primary"], "lifecycle_status": "active", "provenance": provenance}
            ],
            "validation_metrics": [
                {"metric_id": f"metric:{slug}:primary", "target_type": "research_claim", "target_id": f"claim:{slug}:primary", "metric_name": "Primary metric", "metric_definition": "Measures the outcome.", "data_source_plan": "Collect primary data.", "unit": "percent", "baseline_value": None, "baseline_as_of": None, "comparison_operator": ">=", "observation_window": "12 months", "aggregation_method": "median", "expected_range": "10-20", "confirmation_threshold": 10, "warning_threshold": 5, "data_freshness_requirement": "quarterly", "observation_frequency": "quarterly", "status": "planned", "provenance": provenance}
            ],
            "invalidation_conditions": [
                {"condition_id": f"condition:{slug}:primary", "target_type": "research_claim", "target_id": f"claim:{slug}:primary", "condition_text": "Metric stays below threshold.", "observable_test": "Observe metric.", "comparison_operator": "<", "threshold_value": 5, "unit": "percent", "persistence_window": "2 quarters", "minimum_observations": 2, "recovery_condition": None, "severity": "critical", "status": "active", "triggered_at": None, "provenance": provenance}
            ],
            "company_capture_assessments": [],
        },
    }
    _rehash(payload)
    return payload


def _rehash(version: dict[str, object]) -> None:
    version["content_hash"] = content_sha256(
        version, excluded_paths={("content_hash",)}
    )


def _identity(slug: str, current: str = "0.1.0") -> dict[str, object]:
    return {
        "project_id": f"research_project:{slug}",
        "project_slug": slug,
        "title": f"{slug.title()} 中文研究",
        "purpose": "Exercise the research project V2 CLI.",
        "created_at": CREATED_AT,
        "created_by": "fixture-author",
        "current_lifecycle_state": "research_ready",
        "current_version": f"research_version:{slug}:{current}",
        "latest_reviewed_version": None,
        "latest_published_version": None,
    }


def _manifest_row(version: dict[str, object]) -> dict[str, object]:
    semantic_version = str(version["semantic_version"])
    return {
        "version_id": version["version_id"],
        "semantic_version": semantic_version,
        "parent_version_id": version["parent_version_id"],
        "relative_path": f"versions/v{semantic_version}.json",
        "content_hash": version["content_hash"],
        "created_at": version["created_at"],
    }


def _write_project(
    layout: ResearchProjectLayout,
    slug: str,
    versions: list[dict[str, object]] | None = None,
    *,
    current: str | None = None,
) -> None:
    selected = versions or [_version(slug)]
    current = current or str(selected[-1]["semantic_version"])
    project_dir = layout.project_dir(slug)
    (project_dir / "versions").mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(
        json.dumps(_identity(slug, current), ensure_ascii=False), encoding="utf-8"
    )
    for version in selected:
        semantic_version = version["semantic_version"]
        (project_dir / f"versions/v{semantic_version}.json").write_text(
            json.dumps(version, ensure_ascii=False), encoding="utf-8"
        )
    (project_dir / "version_manifest.jsonl").write_text(
        "".join(json.dumps(_manifest_row(version)) + "\n" for version in selected),
        encoding="utf-8",
    )


@pytest.fixture
def layout(tmp_path: Path) -> ResearchProjectLayout:
    result = ResearchProjectLayout(tmp_path / "research-projects-v2")
    for slug in ("zeta", "demo", "beta", "alpha"):
        _write_project(result, slug)
    return result


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_list_outputs_four_projects_sorted_by_slug(layout, capsys):
    assert cli(["list"], layout=layout) == 0
    result = _payload(capsys)
    assert [item["project_slug"] for item in result["projects"]] == [
        "alpha", "beta", "demo", "zeta"
    ]
    assert all(item["question_count"] == 2 for item in result["projects"])


def test_list_binds_summary_to_the_first_loaded_identity_pointer(
    layout, capsys, monkeypatch
):
    import stock_research.research_project_v2.cli as cli_module

    identity = _identity("demo", "0.1.0")
    seen_versions = []
    monkeypatch.setattr(cli_module, "list_project_slugs", lambda **kwargs: ["demo"])
    monkeypatch.setattr(cli_module, "load_project", lambda *args, **kwargs: identity)

    def load_selected_version(slug, version=None, **kwargs):
        seen_versions.append(version)
        return _version(slug, "0.1.0")

    monkeypatch.setattr(cli_module, "load_version", load_selected_version)

    assert cli(["list"], layout=layout) == 0
    project = _payload(capsys)["projects"][0]
    assert project["current_version"] == "research_version:demo:0.1.0"
    assert project["semantic_version"] == "0.1.0"
    assert seen_versions == ["0.1.0"]


def test_show_without_version_loads_current_pointer(layout, capsys):
    newer = _version("demo", "0.2.0", parent_version_id="research_version:demo:0.1.0")
    _write_project(layout, "demo", [_version("demo"), newer], current="0.2.0")
    assert cli(["show", "--project", "demo"], layout=layout) == 0
    assert _payload(capsys)["semantic_version"] == "0.2.0"


def test_validate_invalid_schema_exits_two(layout, capsys):
    path = layout.project_dir("demo") / "versions/v0.1.0.json"
    version = json.loads(path.read_text(encoding="utf-8"))
    version["snapshot"].pop("project_lifecycle_state")
    path.write_text(json.dumps(version), encoding="utf-8")
    assert cli(["validate", "--project", "demo"], layout=layout) == 2
    assert _payload(capsys)["error"]["code"] == "RESEARCH_PROJECT_SCHEMA_INVALID"


def test_audit_missing_reference_exits_three(layout, capsys):
    path = layout.project_dir("demo") / "versions/v0.1.0.json"
    version = json.loads(path.read_text(encoding="utf-8"))
    version["snapshot"]["references"] = [{
        "reference_id": "ref:missing",
        "reference_namespace": "theme_research_v1",
        "reference_type": "v1_theme_node",
        "reference_object_id": "missing-theme-node",
        "reference_role": "background",
        "reference_version": None,
        "reference_content_hash": None,
        "hash_scope": "entire_object",
        "referenced_at": CREATED_AT,
        "locator": None,
        "scope_note": None,
        "resolution_status": "missing",
        "provenance": _provenance("demo", "0.1.0"),
    }]
    _rehash(version)
    _write_project(layout, "demo", [version])
    assert cli(["audit-references", "--project", "demo"], layout=layout) == 3
    result = _payload(capsys)
    assert result["status"] == "fail"
    assert result["issues"] == [{"reference_id": "ref:missing", "status": "missing"}]


def test_failed_design_gate_exits_four(layout, capsys):
    version = _version("demo")
    version["snapshot"]["scope"]["excluded_scope"] = []
    _rehash(version)
    _write_project(layout, "demo", [version])
    assert cli(["gate", "--project", "demo", "--version", "0.1.0", "--gate", "design"], layout=layout) == 4
    assert _payload(capsys)["status"] == "fail"


def test_gate_requires_explicit_version(layout, capsys):
    assert cli(["gate", "--project", "demo", "--gate", "design"], layout=layout) == 2
    assert "--version" in capsys.readouterr().err


def test_invalid_diff_ancestry_exits_seven(layout, capsys):
    before = _version("demo")
    after = _version("demo", "0.2.0", parent_version_id=None)
    _write_project(layout, "demo", [before, after], current="0.2.0")
    assert cli(["diff", "--project", "demo", "--from", "0.1.0", "--to", "0.2.0"], layout=layout) == 7
    assert _payload(capsys)["error"]["code"] == "RESEARCH_PROJECT_DIFF_ANCESTRY_INVALID"


def test_root_cli_delegates_raw_remaining_arguments(monkeypatch):
    import stock_research.cli as root_cli

    calls = []
    monkeypatch.setattr(root_cli, "run_research_project_v2_cli", lambda args: calls.append(args) or 37)
    assert root_cli.main_for_args(["research-project-v2", "list"]) == 37
    assert calls == [["list"]]


def test_validate_all_and_summary_are_deterministic(layout, capsys):
    assert cli(["validate", "--all"], layout=layout) == 0
    validated = _payload(capsys)["validated"]
    assert [item["project_id"] for item in validated] == [
        "research_project:alpha", "research_project:beta",
        "research_project:demo", "research_project:zeta",
    ]
    assert cli(["summary", "--project", "demo"], layout=layout) == 0
    summary = _payload(capsys)
    assert summary["project_stage"] == "research_ready"
    assert summary["reference_count"] == 0


def test_validate_all_reports_project_with_no_versions(layout, capsys):
    empty_dir = layout.project_dir("empty")
    empty_dir.mkdir(parents=True)
    (empty_dir / "project.json").write_text(
        json.dumps(_identity("empty")), encoding="utf-8"
    )
    assert cli(["validate", "--all"], layout=layout) == 6
    error = _payload(capsys)["error"]
    assert error["code"] == "RESEARCH_PROJECT_VERSION_NOT_FOUND"
    assert error["details"] == {"project": "empty", "version": None}


def test_validate_empty_layout_is_not_a_vacuous_pass(tmp_path, capsys):
    empty_layout = ResearchProjectLayout(tmp_path / "empty-research-projects")
    assert cli(["validate"], layout=empty_layout) == 6
    assert _payload(capsys)["error"] == {
        "code": "RESEARCH_PROJECT_NOT_FOUND",
        "message": "Research projects not found",
        "details": {"artifact": "projects"},
    }


def test_later_gate_not_applicable_is_success(layout, capsys):
    assert cli(["gate", "--project", "demo", "--version", "0.1.0", "--gate", "evidence"], layout=layout) == 0
    assert _payload(capsys)["status"] == "not_applicable"


def test_gate_pass_with_warnings_is_success(layout, capsys, monkeypatch):
    from stock_research.research_project_v2.gates import GateCheck, GateResult
    import stock_research.research_project_v2.cli as cli_module

    monkeypatch.setattr(
        cli_module,
        "evaluate_gate",
        lambda version, gate: GateResult(
            gate,
            "pass_with_warnings",
            (GateCheck("FIXTURE_WARNING", "warning", "Review this result."),),
        ),
    )
    assert cli(["gate", "--project", "demo", "--version", "0.1.0", "--gate", "design"], layout=layout) == 0
    assert _payload(capsys)["status"] == "pass_with_warnings"


def test_summary_field_order_and_read_only_contract():
    version = _version("demo")
    original = deepcopy(version)
    result = summarize_version(version)
    assert list(result) == [
        "project_id", "version_id", "semantic_version", "creation_stage",
        "project_stage", "evidence_stage", "conclusion_status", "investment_status",
        "question_count", "claim_count", "requirement_count", "assessment_count",
        "reference_count", "causal_edge_count",
    ]
    assert version == original


def test_immutability_not_found_and_runtime_exit_codes(layout, capsys, monkeypatch):
    path = layout.project_dir("demo") / "versions/v0.1.0.json"
    version = json.loads(path.read_text(encoding="utf-8"))
    version["change_summary"] = "tampered"
    path.write_text(json.dumps(version), encoding="utf-8")
    assert cli(["show", "--project", "demo"], layout=layout) == 5
    assert _payload(capsys)["error"]["code"] == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"

    assert cli(["show", "--project", "missing"], layout=layout) == 6
    assert _payload(capsys)["error"]["code"] == "RESEARCH_PROJECT_NOT_FOUND"

    import stock_research.research_project_v2.cli as cli_module
    monkeypatch.setattr(cli_module, "load_project", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk offline")))
    assert cli(["list"], layout=layout) == 10
    assert _payload(capsys)["error"] == {
        "code": "RESEARCH_PROJECT_RUNTIME_ERROR",
        "message": "disk offline",
        "details": {},
    }


def test_domain_error_exit_mapping_uses_code_family_not_command(layout, capsys, monkeypatch):
    import stock_research.research_project_v2.cli as cli_module

    monkeypatch.setattr(
        cli_module,
        "load_version",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ResearchProjectV2Error(
                "reference failed",
                code="RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE",
            )
        ),
    )
    assert cli(["show", "--project", "demo"], layout=layout) == 3
    assert _payload(capsys)["error"]["code"] == "RESEARCH_PROJECT_REFERENCE_UNRESOLVABLE"


def test_help_lists_all_r1_commands(capsys):
    assert cli(["--help"]) == 0
    output = capsys.readouterr().out
    for command in ("list", "show", "validate", "summary", "audit-references", "diff", "gate"):
        assert command in output
    assert "rebuild-index" not in output


def test_json_keeps_chinese_and_sorts_keys(layout, capsys):
    assert cli(["list"], layout=layout) == 0
    output = capsys.readouterr().out
    assert "中文研究" in output
    assert "\\u4e2d" not in output
    assert output.index('"projects"') < output.index('"title"')
