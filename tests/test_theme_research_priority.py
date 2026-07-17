from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from stock_research.theme_research_priority import (
    THEME_RESEARCH_PRIORITY_POLICY_DIR,
    ThemeResearchPriorityValidationError,
    build_human_review_queue,
    cli,
    list_company_research_priorities,
    list_evidence_gap_priorities,
    list_theme_node_priorities,
    load_company_priority_details,
    load_theme_research_priority_package,
    summarize_theme_research_priority_package,
)


def _contains_forbidden_token(value: str, token: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", value) is not None


def test_priority_package_scores_all_nodes_and_company_mappings_once():
    package = load_theme_research_priority_package()
    summary = summarize_theme_research_priority_package(package)
    canonical_node_keys = {
        (row["theme_id"], row["node_id"])
        for row in package["theme_package"]["nodes"]
    }
    priority_node_keys = {
        (row["theme_id"], row["node_id"])
        for row in package["node_priorities"]
    }
    canonical_mapping_ids = {
        row["mapping_id"]
        for row in package["mapping_package"]["company_mappings"]
    }
    priority_mapping_ids = {
        row["mapping_id"] for row in package["company_priorities"]
    }

    assert summary["theme_count"] == len(package["theme_package"]["themes"])
    assert summary["node_priority_count"] == len(canonical_node_keys)
    assert summary["company_priority_count"] == len(canonical_mapping_ids)
    assert summary["unique_company_count"] == len(
        {row["company_code"] for row in package["company_priorities"]}
    )
    assert summary["linked_company_count"] == sum(
        row["integration_status"] == "linked_existing_universe"
        for row in package["company_priorities"]
    )
    assert summary["coverage_gap_company_count"] == sum(
        row["integration_status"] == "coverage_gap"
        for row in package["company_priorities"]
    )
    assert priority_node_keys == canonical_node_keys
    assert priority_mapping_ids == canonical_mapping_ids
    assert sum(
        row["theme_id"] == "ai_power_value_capture_v1"
        for row in package["node_priorities"]
    ) == 13
    assert sum(
        row["theme_id"] == "ai_power_value_capture_v1"
        for row in package["company_priorities"]
    ) == 8


def test_low_evidence_structural_node_becomes_evidence_collection_priority():
    rows = list_evidence_gap_priorities()
    transformer = next(row for row in rows if row["node_id"] == "transformer")

    assert transformer["evidence_strength"] == 2
    assert transformer["evidence_gap_score"] == 3
    assert transformer["evidence_gap_priority_score"] == 73.0
    assert transformer["priority_class"] == "evidence_collection_priority"
    assert transformer["recommended_action"] == "collect_node_evidence"
    assert transformer["affected_mapping_count"] == 0
    assert transformer["affected_company_mappings"] == []


def test_evidence_gap_priority_lists_affected_company_mappings():
    rows = list_evidence_gap_priorities()
    server_power = next(row for row in rows if row["node_id"] == "server_power_supply")

    assert server_power["affected_mapping_count"] == 1
    assert [row["company_code"] for row in server_power["affected_company_mappings"]] == [
        "300870.SZ",
    ]
    assert all(
        row["integration_status"] == "coverage_gap"
        for row in server_power["affected_company_mappings"]
    )


def test_strong_evidence_structural_node_becomes_deep_research_priority():
    rows = list_theme_node_priorities()
    liquid_cooling = next(row for row in rows if row["node_id"] == "liquid_cooling")

    assert liquid_cooling["deep_research_priority_score"] == 77.0
    assert liquid_cooling["priority_class"] == "deep_research_priority"
    assert liquid_cooling["recommended_action"] == "deep_node_research"
    assert "strong_evidence" in liquid_cooling["rationale_codes"]


def test_company_priority_arithmetic_and_order_are_stable():
    rows = [
        row
        for row in list_company_research_priorities()
        if row["theme_id"] == "ai_power_value_capture_v1"
        and row["company_code"] in {
            "002335.SZ",
            "002364.SZ",
            "002837.SZ",
            "300870.SZ",
        }
    ]

    assert [row["company_code"] for row in rows] == [
        "002837.SZ",
        "002364.SZ",
        "300870.SZ",
        "002335.SZ",
    ]
    expected = {
        "002837.SZ": (78.8, "high", 4.7, 3),
        "002364.SZ": (77.2, "high", 4.8, 4),
        "300870.SZ": (75.6, "high", 4.9, 4),
        "002335.SZ": (68.4, "medium", 4.6, 4),
    }
    for row in rows:
        score, band, relevance, materiality = expected[row["company_code"]]
        assert row["company_research_priority_score"] == score
        assert row["priority_band"] == band
        assert row["company_relevance_score"] == relevance
        assert row["business_materiality_score"] == materiality
        assert sum(row["weighted_components"].values()) == pytest.approx(score)


def test_integration_status_is_not_a_score_component():
    rows = list_company_research_priorities()

    linked = next(
        row
        for row in rows
        if row["mapping_id"] == "ai_power_liquid_cooling_002837_v1"
    )
    theme_only = next(
        row for row in rows if row["mapping_id"] == "cloud_dc_map_002837_v1"
    )
    gap = next(row for row in rows if row["company_code"] == "300870.SZ")
    assert linked["integration_status"] == "linked_existing_universe"
    assert theme_only["integration_status"] == "theme_only"
    assert gap["integration_status"] == "coverage_gap"
    envicool_rows = [row for row in rows if row["company_code"] == "002837.SZ"]
    assert envicool_rows == sorted(
        envicool_rows,
        key=lambda row: (
            -row["company_research_priority_score"],
            row["company_code"],
            row["mapping_id"],
        ),
    )
    assert [row["mapping_id"] for row in envicool_rows] == [
        "cloud_dc_map_002837_v1",
        "ai_power_liquid_cooling_002837_v1",
    ]
    for row in (linked, theme_only, gap):
        assert "integration_status" not in row["score_components"]
        assert "integration_status" not in row["weighted_components"]


def test_existing_tech_bottleneck_review_state_is_context_only():
    rows = list_company_research_priorities()

    linked = next(
        row
        for row in rows
        if row["mapping_id"] == "ai_power_liquid_cooling_002837_v1"
    )
    theme_only = next(
        row for row in rows if row["mapping_id"] == "cloud_dc_map_002837_v1"
    )
    gap = next(row for row in rows if row["company_code"] == "300870.SZ")
    assert linked["existing_review_context"] == {
        "status": "pending_review",
        "reviewer_decision": "",
    }
    assert theme_only["existing_review_context"] == {
        "status": "not_crosswalked",
        "reviewer_decision": "",
    }
    assert gap["existing_review_context"] == {
        "status": "not_in_existing_universe",
        "reviewer_decision": "",
    }
    assert "existing_review_context" not in linked["score_components"]


def test_integration_and_existing_review_context_do_not_change_merit_score(monkeypatch):
    import stock_research.theme_research_priority as priority_module

    baseline = {
        row["mapping_id"]: row["company_research_priority_score"]
        for row in list_company_research_priorities()
    }
    original = priority_module._integration_by_mapping

    def altered_integration(package):
        result = original(package)
        for row in result.values():
            row["integration_status"] = (
                "coverage_gap"
                if row["integration_status"] == "linked_existing_universe"
                else "linked_existing_universe"
            )
            row["existing_review_context"] = {
                "status": "reviewed",
                "reviewer_decision": "changed_for_test",
            }
        return result

    monkeypatch.setattr(priority_module, "_integration_by_mapping", altered_integration)
    altered = {
        row["mapping_id"]: row["company_research_priority_score"]
        for row in list_company_research_priorities()
    }

    assert altered == baseline


def test_review_queue_is_pending_human_work_not_an_automated_decision():
    queue = build_human_review_queue()

    assert queue
    assert all(row["human_review_status"] == "pending_human_review" for row in queue)
    assert all(row["used_for_signal"] is False for row in queue)
    assert all(row["used_for_admission"] is False for row in queue)
    actions = {row["recommended_action"] for row in queue}
    assert "collect_node_evidence" in actions
    assert "deep_node_research" in actions
    assert "strengthen_node_evidence_for_company" in actions
    assert "deep_company_research" in actions
    assert "review_crosswalk_coverage_gap" in actions
    gap_items = [row for row in queue if row["integration_status"] == "coverage_gap"]
    assert {row["company_code"] for row in gap_items} == {"002364.SZ", "300870.SZ"}


@pytest.mark.parametrize("value", ["price", "market_price", "price_signal"])
def test_forbidden_market_token_detection_rejects_price_inputs(value):
    assert _contains_forbidden_token(value, "price") is True


@pytest.mark.parametrize(
    "value",
    ["prices", "quotas_prices_export_customer_validation"],
)
def test_forbidden_market_token_detection_allows_catalog_price_plural(value):
    assert _contains_forbidden_token(value, "price") is False


def test_outputs_do_not_expose_market_or_trading_inputs():
    package = load_theme_research_priority_package()
    serialized = json.dumps(
        {
            "nodes": package["node_priorities"],
            "companies": package["company_priorities"],
            "queue": package["review_queue"],
        },
        ensure_ascii=False,
        sort_keys=True,
    ).lower()

    for forbidden in (
        "price",
        "valuation",
        "return",
        "momentum",
        "freshness",
        "low_position",
        "buy",
        "sell",
    ):
        assert _contains_forbidden_token(serialized, forbidden) is False


def test_company_detail_resolves_priority_mapping_node_and_crosswalk():
    details = load_company_priority_details("002837.SZ")

    assert len(details) == 2
    assert [row["mapping_id"] for row in details] == [
        "cloud_dc_map_002837_v1",
        "ai_power_liquid_cooling_002837_v1",
    ]
    by_mapping = {row["mapping_id"]: row for row in details}
    linked = by_mapping["ai_power_liquid_cooling_002837_v1"]
    assert linked["theme_node_id"] == "liquid_cooling"
    assert linked["company_mapping"]["mapping_id"] == linked["mapping_id"]
    assert linked["theme_node"]["node_id"] == "liquid_cooling"
    assert linked["crosswalk"]["status"] == "linked"

    theme_only = by_mapping["cloud_dc_map_002837_v1"]
    assert theme_only["theme_node_id"] == "thermal_liquid_cooling_systems"
    assert theme_only["company_mapping"]["mapping_id"] == theme_only["mapping_id"]
    assert theme_only["theme_node"]["node_id"] == "thermal_liquid_cooling_systems"
    assert theme_only["crosswalk"] == {
        "status": "theme_only",
        "mapping_id": "cloud_dc_map_002837_v1",
        "theme_id": "cloud_data_center_infrastructure_value_chain_v1",
        "company_code": "002837.SZ",
        "integration_status": "theme_only",
        "existing_review_context": {
            "status": "not_crosswalked",
            "reviewer_decision": "",
        },
    }


def test_company_lookup_respects_exchange_suffix():
    with pytest.raises(ThemeResearchPriorityValidationError) as exc_info:
        load_company_priority_details("002837.US")

    assert exc_info.value.code == "COMPANY_PRIORITY_NOT_FOUND"


def test_invalid_weight_sum_is_rejected(tmp_path: Path):
    policy_dir = _copy_policy(tmp_path)
    path = _only_policy(policy_dir)
    payload = _read_json(path)
    payload["company_priority_weights"]["business_materiality"] = 0.10
    _write_json(path, payload)

    error = _load_invalid_policy(policy_dir)

    assert error.code == "INVALID_WEIGHT_SUM"


def test_forbidden_market_dimension_is_rejected(tmp_path: Path):
    policy_dir = _copy_policy(tmp_path)
    path = _only_policy(policy_dir)
    payload = _read_json(path)
    payload["company_priority_weights"].pop("business_materiality")
    payload["company_priority_weights"]["low_position"] = 0.15
    _write_json(path, payload)

    error = _load_invalid_policy(policy_dir)

    assert error.code == "FORBIDDEN_PRIORITY_DIMENSION"


def test_incomplete_materiality_mapping_is_rejected(tmp_path: Path):
    policy_dir = _copy_policy(tmp_path)
    path = _only_policy(policy_dir)
    payload = _read_json(path)
    payload["business_materiality_scores"].pop("core_business")
    _write_json(path, payload)

    error = _load_invalid_policy(policy_dir)

    assert error.code == "INCOMPLETE_MATERIALITY_MAPPING"


def test_write_enabled_guardrail_is_rejected(tmp_path: Path):
    policy_dir = _copy_policy(tmp_path)
    path = _only_policy(policy_dir)
    payload = _read_json(path)
    payload["guardrails"]["used_for_signal"] = True
    _write_json(path, payload)

    error = _load_invalid_policy(policy_dir)

    assert error.code == "PRIORITY_GUARDRAIL_VIOLATION"


def test_unknown_policy_field_is_rejected(tmp_path: Path):
    policy_dir = _copy_policy(tmp_path)
    path = _only_policy(policy_dir)
    payload = _read_json(path)
    payload["automatic_recommendation"] = True
    _write_json(path, payload)

    error = _load_invalid_policy(policy_dir)

    assert error.code == "UNEXPECTED_FIELD"


@pytest.mark.parametrize(
    ("field_path", "error_code"),
    [
        (("classification_thresholds", "deep_research_min"), "INVALID_NORMALIZED_SCORE"),
        (("business_materiality_scores", "core_business"), "INVALID_COMPONENT_SCORE"),
    ],
)
def test_non_finite_policy_scores_are_rejected(tmp_path: Path, field_path, error_code):
    policy_dir = _copy_policy(tmp_path)
    path = _only_policy(policy_dir)
    payload = _read_json(path)
    payload[field_path[0]][field_path[1]] = float("nan")
    _write_json(path, payload)

    error = _load_invalid_policy(policy_dir)

    assert error.code == error_code


def test_boolean_score_scale_is_rejected(tmp_path: Path):
    policy_dir = _copy_policy(tmp_path)
    path = _only_policy(policy_dir)
    payload = _read_json(path)
    payload["score_scale"]["component_min"] = False
    _write_json(path, payload)

    error = _load_invalid_policy(policy_dir)

    assert error.code == "INVALID_SCORE_SCALE"


def test_cli_commands_emit_structured_json(capsys):
    expected_summary = summarize_theme_research_priority_package(
        load_theme_research_priority_package()
    )

    assert cli(["validate"]) == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["status"] == "ok"
    assert {
        key: validate_payload[key] for key in expected_summary
    } == expected_summary

    assert cli(["summary"]) == 0
    summary_payload = json.loads(capsys.readouterr().out)
    assert summary_payload == expected_summary

    for command in ("theme-nodes", "companies", "evidence-gaps", "review-queue"):
        assert cli([command]) == 0
        assert json.loads(capsys.readouterr().out)

    assert cli(["show-company", "--company-code", "002837.SZ"]) == 0
    company_payload = json.loads(capsys.readouterr().out)
    assert [row["company_research_priority_score"] for row in company_payload] == [
        84.2,
        78.8,
    ]
    assert [row["integration_status"] for row in company_payload] == [
        "theme_only",
        "linked_existing_universe",
    ]


def test_cli_converts_upstream_loader_failures_to_structured_json(tmp_path: Path, capsys):
    missing_dir = tmp_path / "missing-theme-artifacts"

    assert cli(["--theme-artifact-dir", str(missing_dir), "validate"]) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_code"]
    assert "Traceback" not in captured.err


def _copy_policy(tmp_path: Path) -> Path:
    policy_dir = tmp_path / "priority_policies"
    policy_dir.mkdir()
    for path in THEME_RESEARCH_PRIORITY_POLICY_DIR.glob("*.json"):
        _write_json(policy_dir / path.name, _read_json(path))
    return policy_dir


def _only_policy(policy_dir: Path) -> Path:
    paths = sorted(policy_dir.glob("*.json"))
    assert len(paths) == 1
    return paths[0]


def _load_invalid_policy(policy_dir: Path) -> ThemeResearchPriorityValidationError:
    with pytest.raises(ThemeResearchPriorityValidationError) as exc_info:
        load_theme_research_priority_package(policy_dir=policy_dir)
    return exc_info.value


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
