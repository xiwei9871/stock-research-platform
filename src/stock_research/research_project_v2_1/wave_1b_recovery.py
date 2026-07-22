from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.acquisition_contracts import validate_acquisition_attempt


AUTHORIZED_ERS = {"PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02", "PCB-ER-A02"}
DOWNSTREAM_FLAGS = (
    "automatic_assessment_authorized", "cognition_update_authorized",
    "wave_2_authorized", "company_mapping_authorized", "stage_a2_authorized",
    "stage_b_authorized",
)


def _invalid(message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_WAVE_1B_RECOVERY_INVALID",
        details=details,
    )


def _validate_hash(payload: dict[str, Any], *, label: str) -> None:
    if payload.get("content_hash") != content_sha256(
        payload, excluded_paths={("content_hash",)}
    ):
        raise _invalid(f"{label} hash mismatch")


def recovery_identity_matches(
    *, target_id: str, expected_title: str, document_title: str | None,
    document_text: str, resolved_url: str,
) -> bool:
    title = (document_title or "").casefold()
    text = document_text.casefold()
    expected = expected_title.casefold()
    if ":b02:usc_repository_alternative:" in target_id:
        return expected in title or expected in text[:5000]
    if ":b01:panasonic_bounded_retry:" in target_id:
        return "megtron 6" in title or "megtron 6" in text[:5000]
    if ":a02:ieee_802_3ck_index_to_fulltext:" in target_id:
        return (
            "ieee802.org/3/ck/public/" in resolved_url.casefold()
            and ("802.3ck" in title or "802.3ck" in text[:10000])
        )
    return expected in title or expected in text[:5000]


def validate_recovery_authorization(
    authorization: dict[str, Any], *, gate: dict[str, Any],
    layout: LayeredResearchLayout | None = None, validate_upstreams: bool = True,
) -> dict[str, Any]:
    copied = deepcopy(authorization)
    _validate_hash(copied, label="Recovery execution authorization")
    _validate_hash(gate, label="Recovery Pilot Gate")
    if (
        copied.get("authorization_status") != "frozen"
        or copied.get("execution_authorized") is not True
        or copied.get("authorization_scope") != "exact_candidate_and_action_list_only"
        or copied.get("authorization_consumed") is not False
    ):
        raise _invalid("Recovery execution authorization is not executable")
    targets = copied.get("authorized_targets") or []
    if (
        copied.get("authorized_target_count") != 7
        or copied.get("maximum_total_formal_attempts") != 7
        or len(targets) != 7
        or len({row.get("recovery_target_id") for row in targets}) != 7
    ):
        raise _invalid("Recovery authorization target or attempt limit drifted")
    if any(copied.get(field) is not False for field in DOWNSTREAM_FLAGS):
        raise _invalid("Recovery authorization enables a prohibited downstream action")
    if any(
        copied.get(field) is not False
        for field in (
            "unlisted_target_authorized", "target_substitution_authorized",
            "automatic_scope_expansion_authorized",
        )
    ):
        raise _invalid("Recovery authorization is not exact-list fail-closed")
    gate_targets = {row["recovery_target_id"]: row for row in gate.get("selected_targets") or []}
    if set(gate_targets) != {row.get("recovery_target_id") for row in targets}:
        raise _invalid("Recovery target binding differs from the frozen Gate")
    for row in targets:
        frozen = gate_targets[row["recovery_target_id"]]
        expected = {
            "original_candidate_id": frozen["original_candidate_id"],
            "authorized_er_id": frozen["authorized_er_id"],
            "authorized_recovery_action": frozen["authorized_recovery_action"],
            "same_failed_url_retry_allowed": frozen["same_failed_url_retry_allowed"],
            "maximum_formal_attempts": frozen["maximum_attempts"],
        }
        if any(row.get(key) != value for key, value in expected.items()):
            raise _invalid("Recovery target binding drifted", target_id=row.get("recovery_target_id"))
        if row.get("formal_acquisition_authorized") is not True:
            raise _invalid("Recovery target is not formally authorized", target_id=row.get("recovery_target_id"))
        if row.get("authorized_er_id") not in AUTHORIZED_ERS:
            raise _invalid("Recovery target ER is outside the authorized scope")
    bindings = copied.get("input_bindings") or {}
    if (
        bindings.get("recovery_pilot_gate_id") != gate.get("decision_id")
        or bindings.get("recovery_pilot_gate_hash") != gate.get("content_hash")
    ):
        raise _invalid("Recovery Gate binding drifted")
    if validate_upstreams:
        effective = layout or LayeredResearchLayout.default()
        paths = {
            "capability_checkpoint_hash": effective.root / "acquisition/capability_hardening_v1/capability_checkpoint.json",
            "wave_1b_checkpoint_hash": effective.root / "acquisition/wave_1b/acquisition_checkpoint.json",
        }
        for field, path in paths.items():
            actual = json.loads(path.read_text(encoding="utf-8"))["content_hash"]
            if bindings.get(field) != actual:
                raise _invalid("Recovery upstream binding drifted", field=field)
    return copied


def build_recovery_checkpoint(
    *, gate: dict[str, Any], authorization: dict[str, Any],
    attempts: list[dict[str, Any]], inventory: list[dict[str, Any]],
    created_at: str, preflight_discovery_request_count: int = 0,
) -> dict[str, Any]:
    target_ids = [row["recovery_target_id"] for row in authorization["authorized_targets"]]
    attempt_ids = [row["recovery_target_id"] for row in attempts]
    statuses = Counter(row["status"] for row in attempts)
    content_hashes = [row["content_hash"] for row in inventory]
    core = {
        "acquisition_wave": "wave_1b_recovery_pilot_acquisition",
        "project_id": authorization["project_id"],
        "recovery_pilot_gate_id": gate["decision_id"],
        "recovery_pilot_gate_hash": gate["content_hash"],
        "execution_authorization_id": authorization["authorization_id"],
        "execution_authorization_hash": authorization["content_hash"],
        "authorization_scope": authorization["authorization_scope"],
        "authorized_target_ids": target_ids,
        "executed_target_ids": attempt_ids,
        "authorization_consumed": True,
        "formal_attempt_count": len(attempts),
        "preflight_discovery_request_count": preflight_discovery_request_count,
        "acquired_count": statuses.get("acquired", 0),
        "blocked_count": statuses.get("blocked", 0),
        "failed_count": statuses.get("failed", 0),
        "raw_artifact_count": len(inventory),
        "unique_raw_hash_count": len(set(content_hashes)),
        "normalized_artifact_count": sum(row.get("normalization_status") == "normalized" for row in inventory),
        "normalized_representation_count": len({
            document_id
            for row in inventory
            for document_id in row.get("normalized_representation_ids", [])
        }),
        "duplicate_normalization_groups": [
            row["normalized_representation_ids"]
            for row in inventory
            if len(row.get("normalized_representation_ids", [])) > 1
        ],
        "normalization_failure_count": sum(row.get("normalization_status") == "failed" for row in inventory),
        "per_target_status": {row["recovery_target_id"]: row["status"] for row in attempts},
        "per_er_attempt_count": dict(sorted(Counter(row["authorized_er_id"] for row in attempts).items())),
        "security_policy_blocked_count": sum(row.get("failure_code") == "security_policy_blocked" for row in attempts),
        "scope_violations": [],
        "security_violations": [],
        "assessment_started": False,
        "cognition_update_started": False,
        "automatic_assessment_authorized": False,
        "cognition_update_authorized": False,
        "wave_2_authorized": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "created_at": created_at,
        "created_by": "Codex",
    }
    checkpoint_id = f"wave_1b_recovery_checkpoint:{sha256(canonical_bytes(core)).hexdigest()[:24]}"
    payload = {"checkpoint_id": checkpoint_id, **core, "content_hash": ""}
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    return payload


def validate_recovery_checkpoint(
    checkpoint: dict[str, Any], *, gate: dict[str, Any], authorization: dict[str, Any],
) -> dict[str, Any]:
    copied = deepcopy(checkpoint)
    _validate_hash(copied, label="Recovery checkpoint")
    expected_id = f"wave_1b_recovery_checkpoint:{sha256(canonical_bytes({key: value for key, value in copied.items() if key not in {'checkpoint_id', 'content_hash'}})).hexdigest()[:24]}"
    if copied.get("checkpoint_id") != expected_id:
        raise _invalid("Recovery checkpoint ID mismatch")
    if copied.get("recovery_pilot_gate_hash") != gate.get("content_hash"):
        raise _invalid("Recovery checkpoint Gate binding drifted")
    if copied.get("execution_authorization_hash") != authorization.get("content_hash"):
        raise _invalid("Recovery checkpoint authorization binding drifted")
    target_ids = [row["recovery_target_id"] for row in authorization["authorized_targets"]]
    if copied.get("authorized_target_ids") != target_ids or copied.get("executed_target_ids") != target_ids:
        raise _invalid("Recovery checkpoint target execution drifted")
    if (
        copied.get("authorization_consumed") is not True
        or copied.get("formal_attempt_count") != 7
        or copied.get("formal_attempt_count") > authorization.get("maximum_total_formal_attempts", 0)
    ):
        raise _invalid("Recovery checkpoint formal attempt or consumption state is invalid")
    if copied.get("scope_violations") or copied.get("security_violations"):
        raise _invalid("Recovery checkpoint contains scope or security violations")
    if copied.get("assessment_started") is not False or copied.get("cognition_update_started") is not False:
        raise _invalid("Recovery checkpoint started an unauthorized downstream stage")
    if any(copied.get(field) is not False for field in DOWNSTREAM_FLAGS):
        raise _invalid("Recovery checkpoint authorizes a prohibited downstream action")
    return copied


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_recovery_repository_bundle(
    *, layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    effective = layout or LayeredResearchLayout.default()
    bundle = effective.root / "acquisition/wave_1b_recovery_pilot"
    gate = json.loads(
        (effective.governance_dir / "ai_pcb_wave_1b_recovery_pilot_gate_decision_v1.json").read_text(encoding="utf-8")
    )
    authorization = json.loads(
        (effective.governance_dir / "ai_pcb_wave_1b_recovery_pilot_execution_authorization_v1.json").read_text(encoding="utf-8")
    )
    validate_recovery_authorization(
        authorization, gate=gate, layout=effective, validate_upstreams=True
    )
    checkpoint = json.loads((bundle / "acquisition_checkpoint.json").read_text(encoding="utf-8"))
    validate_recovery_checkpoint(checkpoint, gate=gate, authorization=authorization)
    attempts = _jsonl(bundle / "attempts.jsonl")
    if len(attempts) != 7 or len({row["recovery_target_id"] for row in attempts}) != 7:
        raise _invalid("Recovery bundle attempt universe is invalid")
    for row in attempts:
        wrapper = json.loads(
            (effective.acquisition_attempts_dir / f"{row['attempt_id']}.json").read_text(encoding="utf-8")
        )
        persisted = validate_acquisition_attempt(wrapper["acquisition_attempt"])
        if persisted.get("status") != row.get("status") or persisted.get("raw_artifact_id") != row.get("raw_artifact_id"):
            raise _invalid("Recovery bundle attempt projection drifted", attempt_id=row["attempt_id"])
    inventory = json.loads((bundle / "evidence_inventory.json").read_text(encoding="utf-8"))
    items = inventory.get("items") or []
    if inventory.get("content_hash") != content_sha256(items):
        raise _invalid("Recovery inventory hash mismatch")
    for item in items:
        raw = effective.root / item["raw_artifact_path"]
        if not raw.is_file() or sha256(raw.read_bytes()).hexdigest() != item["content_hash"]:
            raise _invalid("Recovery raw artifact hash mismatch", artifact_id=item["artifact_id"])
        if item.get("identity_match") is False and item.get("eligible_for_assessment") is not False:
            raise _invalid("Identity-mismatched recovery artifact became assessment eligible")
        for document_id in item.get("normalized_representation_ids") or []:
            path = effective.evidence_normalized_dir / f"{document_id}.json"
            document = json.loads(path.read_text(encoding="utf-8"))["normalized_document"]
            if document.get("document_id") != document_id:
                raise _invalid("Recovery normalized representation identity drifted")
    return {
        "status": "pass",
        "checkpoint_id": checkpoint["checkpoint_id"],
        "checkpoint_hash": checkpoint["content_hash"],
        "formal_attempt_count": checkpoint["formal_attempt_count"],
        "raw_artifact_count": checkpoint["raw_artifact_count"],
        "normalized_representation_count": checkpoint["normalized_representation_count"],
        "eligible_for_assessment_count": inventory["eligible_for_assessment_count"],
    }
