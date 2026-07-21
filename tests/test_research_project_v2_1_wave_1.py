from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.wave_1 import (
    AUTHORIZED_ER_IDS,
    INTERNAL_EXECUTION_ORDER,
    build_wave_checkpoint,
    build_wave_attempt_record,
    to_provider_candidate,
    validate_gate_decision,
    validate_wave_candidate,
    validate_wave_checkpoint,
    validate_wave_repository_bundle,
)


def _gate() -> dict:
    gate = {
        "schema_version": "1.0.0",
        "artifact_type": "targeted_acquisition_gate_decision",
        "decision_id": "targeted_acquisition_gate_decision:ai_pcb:v1",
        "decision_status": "frozen",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "gate_decision": "approved_with_revisions",
        "authorized_for_targeted_acquisition": list(AUTHORIZED_ER_IDS),
        "authorization": {
            "targeted_acquisition_authorized": True,
            "authorization_scope": "exact_list_only",
            "unlisted_er_authorized": False,
        },
        "execution_order": [list(group) for group in INTERNAL_EXECUTION_ORDER],
        "acquisition_started": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "input_binding": {
            "gap_review_artifact_path": "analysis/gap.json",
            "gap_review_artifact_hash": "0" * 64,
        },
    }
    from stock_research.research_project_v2.canonical import content_sha256

    gate["content_hash"] = content_sha256(
        gate, excluded_paths=(("content_hash",),)
    )
    return gate


def _candidate(*er_ids: str) -> dict:
    from stock_research.research_project_v2_1.discovery import source_candidate_id

    title = "Test source"
    url = "https://example.com/test.pdf"
    return {
        "candidate_id": source_candidate_id(url, title),
        "authorized_er_ids": list(er_ids),
        "source_title": title,
        "provider_source_title": title,
        "source_owner": "Standards body",
        "source_class": "technical_standard",
        "source_url": url,
        "expected_evidence_role": "definition",
        "eligibility_reason": "Defines a scoped comparison method.",
        "known_limitations": ["Does not establish manufacturing capacity."],
        "publication_date_status": "unknown",
        "candidate_status": "eligible",
        "internal_phase": 1,
    }


def _named_candidate(name: str, *er_ids: str, phase: int | None = None) -> dict:
    from stock_research.research_project_v2_1.discovery import source_candidate_id

    row = _candidate(*er_ids)
    row["provider_source_title"] = f"Test source [{name}]"
    row["candidate_id"] = source_candidate_id(row["source_url"], row["provider_source_title"])
    if phase is not None:
        row["internal_phase"] = phase
    return row


def test_gate_enforces_frozen_exact_list_and_hash() -> None:
    validated = validate_gate_decision(_gate())
    assert tuple(validated["authorized_for_targeted_acquisition"]) == AUTHORIZED_ER_IDS

    drifted = deepcopy(_gate())
    drifted["stage_b_authorized"] = True
    with pytest.raises(ResearchProjectV2Error, match="hash"):
        validate_gate_decision(drifted)


def test_candidate_rejects_unlisted_er_and_wrong_phase() -> None:
    gate = validate_gate_decision(_gate())
    assert validate_wave_candidate(_candidate("PCB-ER-A01"), gate)["internal_phase"] == 1

    with pytest.raises(ResearchProjectV2Error, match="not authorized"):
        validate_wave_candidate(_candidate("PCB-ER-A05"), gate)

    wrong_phase = _candidate("PCB-ER-B02")
    with pytest.raises(ResearchProjectV2Error, match="phase"):
        validate_wave_candidate(wrong_phase, gate)


def test_provider_candidate_and_attempt_record_preserve_scope_and_network_mode() -> None:
    gate = validate_gate_decision(_gate())
    candidate = validate_wave_candidate(_candidate("PCB-ER-A01"), gate)
    provider = to_provider_candidate(
        candidate,
        discovered_at="2026-07-21T10:00:00Z",
        provenance={
            "created_by": "Codex",
            "actor_type": "codex",
            "agent_run_id": "wave-1",
            "created_at": "2026-07-21T10:00:00Z",
            "created_in_version": "research_version:test:0.2.1",
            "review_status": "unreviewed",
        },
    )
    assert provider["candidate_id"] == candidate["candidate_id"]
    assert provider["publish_date"] is None
    assert provider["normalized_url"] == candidate["source_url"]

    attempt = build_wave_attempt_record(
        candidate=candidate,
        provider_attempt={
            "attempt_id": "acquisition_attempt:test",
            "status": "acquired",
            "failure_code": None,
            "http_status": 200,
            "raw_artifact_id": "evidence_artifact:test",
            "content_type": "application/pdf",
            "bytes_received": 42,
            "attempted_at": "2026-07-21T10:00:00Z",
            "completed_at": "2026-07-21T10:00:01Z",
            "elapsed_ms": 1000,
            "retry_count": 0,
            "resolved_url": candidate["source_url"],
            "diagnostic_summary": "ok",
        },
        artifact={"evidence_artifact_id": "evidence_artifact:test", "content_hash": "1" * 64},
        normalization_status="normalized",
        normalized_document_id="normalized_document:test",
    )
    assert attempt["authorized_er_ids"] == ["PCB-ER-A01"]
    assert attempt["network_mode"] == "direct_http"
    assert attempt["proxy_mode"] == "direct"
    assert attempt["trust_env"] is False
    assert attempt["assessment_started"] is False


def test_checkpoint_counts_attempts_acquired_duplicates_and_unknown_dates() -> None:
    gate = validate_gate_decision(_gate())
    candidates = [
        _named_candidate("c1", "PCB-ER-A01"),
        _named_candidate("c2", "PCB-ER-A04"),
        _named_candidate("c3", "PCB-ER-B01"),
        _named_candidate("c4", "PCB-ER-A03", phase=2),
        _named_candidate("c5", "PCB-ER-B02", phase=3),
        _named_candidate("c6", "PCB-ER-A02", phase=2),
    ]
    ids = [row["candidate_id"] for row in candidates]
    attempts = [
        {"attempt_id": "a1", "candidate_id": ids[0], "authorized_er_ids": ["PCB-ER-A01"], "status": "acquired", "raw_artifact_id": "r1", "content_hash": "1" * 64},
        {"attempt_id": "a2", "candidate_id": ids[1], "authorized_er_ids": ["PCB-ER-A04"], "status": "blocked", "raw_artifact_id": None, "content_hash": None},
        {"attempt_id": "a3", "candidate_id": ids[2], "authorized_er_ids": ["PCB-ER-B01"], "status": "acquired", "raw_artifact_id": "r2", "content_hash": "1" * 64},
        {"attempt_id": "a4", "candidate_id": ids[3], "authorized_er_ids": ["PCB-ER-A03"], "status": "failed", "raw_artifact_id": None, "content_hash": None},
        {"attempt_id": "a5", "candidate_id": ids[4], "authorized_er_ids": ["PCB-ER-B02"], "status": "acquired", "raw_artifact_id": "r3", "content_hash": "2" * 64},
        {"attempt_id": "a6", "candidate_id": ids[5], "authorized_er_ids": ["PCB-ER-A02"], "status": "acquired", "raw_artifact_id": "r1", "content_hash": "1" * 64},
    ]
    inventory = [
        {"artifact_id": "r1", "content_hash": "1" * 64, "content_type": "text/html", "publication_date_status": "unknown", "normalized_document_id": "n1"},
        {"artifact_id": "r2", "content_hash": "1" * 64, "content_type": "application/pdf", "publication_date_status": "known", "normalized_document_id": "n2"},
        {"artifact_id": "r3", "content_hash": "2" * 64, "content_type": "application/pdf", "publication_date_status": "unknown", "normalized_document_id": None},
    ]
    checkpoint = build_wave_checkpoint(
        gate=gate,
        candidates=candidates,
        attempts=attempts,
        inventory=inventory,
        created_at="2026-07-21T10:00:00Z",
        suspected_common_origin_groups=[["r1", "r3"]],
    )
    assert checkpoint["attempt_count"] == 6
    assert checkpoint["acquired_count"] == 4
    assert checkpoint["blocked_count"] == 1
    assert checkpoint["failed_count"] == 1
    assert checkpoint["raw_artifact_count"] == 3
    assert checkpoint["unique_raw_hash_count"] == 2
    assert checkpoint["duplicate_groups"] == [["r1", "r2"]]
    assert checkpoint["evidence_chain_count"] == 1
    assert checkpoint["unknown_publication_date_count"] == 2
    assert checkpoint["per_er_attempt_coverage"]["PCB-ER-A04"] == 1
    assert checkpoint["per_er_acquired_coverage"]["PCB-ER-A04"] == 0
    assert checkpoint["assessment_started"] is False
    assert checkpoint["engineering_preflight_attempt_count"] == 0
    validate_wave_checkpoint(checkpoint, gate=gate)


def test_checkpoint_rejects_downstream_or_unauthorized_coverage() -> None:
    gate = validate_gate_decision(_gate())
    checkpoint = build_wave_checkpoint(
        gate=gate,
        candidates=[_candidate("PCB-ER-A01")],
        attempts=[{"attempt_id": "a1", "candidate_id": _candidate("PCB-ER-A01")["candidate_id"], "authorized_er_ids": ["PCB-ER-A01"], "status": "blocked", "raw_artifact_id": None, "content_hash": None}],
        inventory=[],
        created_at="2026-07-21T10:00:00Z",
    )
    checkpoint["stage_b_authorized"] = True
    with pytest.raises(ResearchProjectV2Error, match="downstream"):
        validate_wave_checkpoint(checkpoint, gate=gate)

    checkpoint = build_wave_checkpoint(
        gate=gate,
        candidates=[_candidate("PCB-ER-A01")],
        attempts=[{"attempt_id": "a1", "candidate_id": _candidate("PCB-ER-A01")["candidate_id"], "authorized_er_ids": ["PCB-ER-A01", "PCB-ER-A05"], "status": "blocked", "raw_artifact_id": None, "content_hash": None}],
        inventory=[],
        created_at="2026-07-21T10:00:00Z",
    )
    with pytest.raises(ResearchProjectV2Error, match="unauthorized"):
        validate_wave_checkpoint(checkpoint, gate=gate)


def test_materialized_wave_1_bundle_is_fail_closed_and_traceable() -> None:
    result = validate_wave_repository_bundle()
    assert result["valid"] is True
    assert result["candidate_count"] == 16
    assert result["attempt_count"] == 16
    assert result["raw_artifact_count"] == 11


def test_wave_1_exact_allowlist_covers_all_changes_and_forbids_downstream_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "artifacts/research_projects/v2_1/acquisition/wave_1_exact_allowlist.json").read_text(encoding="utf-8")
    )
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", f"{payload['baseline_commit']}..HEAD"],
            cwd=root,
            text=True,
        ).splitlines()
    )
    for line in subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-uall"], cwd=root, text=True
    ).splitlines():
        path = line[3:]
        changed.add(path.split(" -> ", 1)[-1])
    assert changed <= set(payload["paths"])
    assert not any(path.startswith(tuple(payload["forbidden_prefixes"])) for path in changed)
