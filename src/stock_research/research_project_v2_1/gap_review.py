from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.cognition import validate_cognition_package
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    read_layered_bytes,
    read_layered_canonical_json,
)


FIXED_GAP_GROUPS = {
    "GAP-SIGNAL": "group_a_signal_transmission",
    "GAP-LOSS": "group_a_signal_transmission",
    "GAP-LAYERS": "group_a_signal_transmission",
    "GAP-LAMINATE": "group_b_material_capability",
    "GAP-BACKDRILL": "group_c_manufacturing_testing",
    "GAP-LAMINATION": "group_c_manufacturing_testing",
    "GAP-THERMAL": "group_c_manufacturing_testing",
    "GAP-TEST": "group_c_manufacturing_testing",
    "GAP-YIELD": "group_c_manufacturing_testing",
    "GAP-CAPACITY": "group_d_bottleneck_effective_capacity",
}


def _error(message: str, *, code: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def validate_gap_universe(
    gap_reviews: list[dict[str, Any]],
    expected_groups: dict[str, str],
) -> list[str]:
    if not all(isinstance(row, dict) for row in gap_reviews):
        raise _error(
            "Gap reviews must contain objects",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
        )
    ids = [row.get("gap_id") for row in gap_reviews]
    if len(ids) != len(set(ids)):
        raise _error(
            "Gap review IDs must be unique",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
        )
    if set(ids) != set(expected_groups):
        raise _error(
            "Gap review universe differs from the frozen cognition gaps",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
            missing=sorted(set(expected_groups) - set(ids)),
            unexpected=sorted(set(ids) - set(expected_groups)),
        )
    wrong = sorted(
        gap_id
        for gap_id, expected_group in expected_groups.items()
        if next(row for row in gap_reviews if row["gap_id"] == gap_id).get("gap_group")
        != expected_group
    )
    if wrong:
        raise _error(
            "Gap review group assignment differs from the frozen design",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_INVALID",
            gap_ids=wrong,
        )
    return sorted(ids)


def validate_input_bindings(
    artifact: dict[str, Any],
    *,
    layout: LayeredResearchLayout,
) -> dict[str, Any]:
    bindings = artifact.get("input_bindings")
    if not isinstance(bindings, dict):
        raise _error(
            "Gap review input bindings are missing",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
        )
    package = read_layered_canonical_json(
        str(bindings.get("cognition_package_path")), layout=layout
    )
    if package.get("content_hash") != bindings.get("cognition_package_hash"):
        raise _error(
            "Cognition package binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="cognition_package_hash",
        )
    validate_cognition_package(package, layout=layout)

    audit = read_layered_canonical_json(
        str(bindings.get("cognition_audit_path")), layout=layout
    )
    if audit.get("content_hash") != bindings.get("cognition_audit_hash"):
        raise _error(
            "Cognition audit binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="cognition_audit_hash",
        )
    report = read_layered_bytes(
        str(bindings.get("cognition_report_path")), layout=layout
    )
    if sha256(report).hexdigest() != bindings.get("cognition_report_hash"):
        raise _error(
            "Cognition report binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="cognition_report_hash",
        )
    checkpoint_id = bindings.get("acquisition_checkpoint_id")
    checkpoint = read_layered_canonical_json(
        f"acquisition/checkpoints/{checkpoint_id}.json", layout=layout
    ).get("acquisition_checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("content_hash") != bindings.get(
        "acquisition_checkpoint_hash"
    ):
        raise _error(
            "Acquisition checkpoint binding drifted",
            code="RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT",
            field="acquisition_checkpoint_hash",
        )
    return package


__all__ = ["FIXED_GAP_GROUPS", "validate_gap_universe", "validate_input_bindings"]
