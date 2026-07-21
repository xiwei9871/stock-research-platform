from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import read_layered_canonical_json
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


REQUIRED_GLOBAL_ENTITIES = {
    "NVIDIA",
    "Intel / Habana",
    "Cisco",
    "Broadcom",
    "Lightmatter",
    "Supermicro",
}
REQUIRED_FORBIDDEN_OUTPUTS = {
    "company_score",
    "stock_recommendation",
    "signal",
    "admission",
    "portfolio",
    "strategy",
    "trade",
}


def _scope_error(
    message: str,
    *,
    field: str,
    actual: object,
) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_SCOPE_CORRECTION_INVALID",
        details={"field": field, "actual": actual},
    )


def validate_stage_a_scope_correction(
    payload: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    copied = deepcopy(payload)
    validate_v2_1_schema_payload(
        "stage_a_scope_correction_v2_4",
        copied,
        layout=layout,
    )

    expected_hash = content_sha256(copied, excluded_paths={("content_hash",)})
    if copied["content_hash"] != expected_hash:
        raise _scope_error(
            "Scope correction content hash mismatch",
            field="content_hash",
            actual=copied["content_hash"],
        )

    effective = LayeredResearchLayout.default() if layout is None else layout
    reference = copied["decision"]["original_checkpoint"]
    relative_path = (
        Path("acquisition/checkpoints") / f"{reference['checkpoint_id']}.json"
    )
    checkpoint_path = effective.root / relative_path
    checkpoint_wrapper = read_layered_canonical_json(
        relative_path,
        layout=effective,
    )
    checkpoint = checkpoint_wrapper.get("acquisition_checkpoint")
    if not isinstance(checkpoint, dict):
        raise _scope_error(
            "Original checkpoint payload is missing",
            field="original_checkpoint",
            actual=checkpoint_wrapper.get("artifact_kind"),
        )
    if checkpoint.get("checkpoint_id") != reference["checkpoint_id"]:
        raise _scope_error(
            "Original checkpoint ID mismatch",
            field="original_checkpoint.checkpoint_id",
            actual=checkpoint.get("checkpoint_id"),
        )
    if checkpoint.get("content_hash") != reference["canonical_content_hash"]:
        raise _scope_error(
            "Original checkpoint canonical hash mismatch",
            field="original_checkpoint.canonical_content_hash",
            actual=checkpoint.get("content_hash"),
        )
    file_hash = sha256(checkpoint_path.read_bytes()).hexdigest()
    if file_hash != reference["file_sha256"]:
        raise _scope_error(
            "Original checkpoint file hash mismatch",
            field="original_checkpoint.file_sha256",
            actual=file_hash,
        )

    entities = {
        item["entity_name"]: item
        for item in copied["decision"]["entity_classifications"]
    }
    if set(entities) != REQUIRED_GLOBAL_ENTITIES:
        raise _scope_error(
            "Global reference entity set mismatch",
            field="entity_classifications",
            actual=sorted(entities),
        )

    forbidden_outputs = set(
        copied["decision"]["stage_a2_plan"]["forbidden_outputs"]
    )
    if forbidden_outputs != REQUIRED_FORBIDDEN_OUTPUTS:
        raise _scope_error(
            "Stage A2 downstream prohibitions mismatch",
            field="stage_a2_plan.forbidden_outputs",
            actual=sorted(forbidden_outputs),
        )
    return copied
