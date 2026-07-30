from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "theme_research_checkpoint_import_guard.py"
)
SPEC = importlib.util.spec_from_file_location(
    "theme_research_checkpoint_import_guard",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
evaluate_restore_gate = MODULE.evaluate_restore_gate


EXISTING_THEME_IDS = {
    "ai_power_value_capture_v1",
    "humanoid_robotics_head_to_toe_v1",
}
EXPECTED_THEME_IDS = EXISTING_THEME_IDS | {
    f"checkpoint_theme_{index:02d}" for index in range(1, 24)
}
FAMILIES = (
    "themes",
    "nodes",
    "sources",
    "theme_sources",
    "claims",
    "claim_sources",
    "claim_nodes",
    "assessments",
    "assessment_evidence",
    "company_mappings",
    "mapping_evidence_items",
    "company_mapping_evidence",
)


def _safe_diff() -> dict:
    missing = sorted(EXPECTED_THEME_IDS - EXISTING_THEME_IDS)
    families = {
        family: {
            "insert": missing if family == "themes" else [],
            "update": [],
            "deactivate": [],
            "no_change": sorted(EXISTING_THEME_IDS) if family == "themes" else [],
        }
        for family in FAMILIES
    }
    return {
        "has_changes": True,
        "summary": {
            "insert": len(missing),
            "update": 0,
            "deactivate": 0,
            "no_change": len(EXISTING_THEME_IDS),
        },
        "families": families,
    }


def test_restore_gate_allows_exactly_23_inserts_without_mutations() -> None:
    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=_safe_diff(),
    )

    assert result["allowed"] is True
    assert result["violations"] == []
    assert result["theme_counts"] == {
        "expected": 25,
        "current": 2,
        "insert": 23,
        "update": 0,
        "deactivate": 0,
    }


def test_restore_gate_rejects_any_update() -> None:
    diff = deepcopy(_safe_diff())
    diff["families"]["nodes"]["update"] = ["existing-node"]

    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=diff,
    )

    assert result["allowed"] is False
    assert "updates_present:nodes:1" in result["violations"]


def test_restore_gate_rejects_any_deactivation() -> None:
    diff = deepcopy(_safe_diff())
    diff["families"]["sources"]["deactivate"] = ["existing-source"]

    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=diff,
    )

    assert result["allowed"] is False
    assert "deactivations_present:sources:1" in result["violations"]


def test_restore_gate_rejects_unexpected_current_theme_set() -> None:
    result = evaluate_restore_gate(
        expected_theme_ids=EXPECTED_THEME_IDS,
        current_theme_ids={"unexpected_theme"},
        semantic_diff=_safe_diff(),
    )

    assert result["allowed"] is False
    assert "current_theme_ids_mismatch" in result["violations"]


def test_restore_gate_rejects_wrong_expected_theme_count() -> None:
    result = evaluate_restore_gate(
        expected_theme_ids=set(sorted(EXPECTED_THEME_IDS)[:-1]),
        current_theme_ids=EXISTING_THEME_IDS,
        semantic_diff=_safe_diff(),
    )

    assert result["allowed"] is False
    assert "expected_theme_count:24" in result["violations"]
