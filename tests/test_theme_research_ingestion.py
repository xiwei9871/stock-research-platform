from __future__ import annotations

import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import stock_research.theme_research_ingestion as ingestion_module
from stock_research.theme_research_ingestion import (
    IngestionValidationError,
    RUN_VERSION,
    append_review_event,
    build_promotion_preview,
    create_ingestion_run,
    file_sha256,
    load_run,
    normalize_input,
    promote_run,
    validate_run,
)
from stock_research.cli import main_for_args
from stock_research.theme_research_ingestion import cli as ingestion_cli


def _theme_artifact() -> dict:
    return {
        "artifact_version": "theme_decomposition_v1_5",
        "theme": {
            "theme_id": "ai_power_value_capture_v1",
            "theme_name": "AI power value capture",
            "theme_type": "ai_power",
            "summary": "test theme",
            "status": "draft",
            "created_from": "mixed",
            "last_updated": "2026-07-11",
        },
        "sources": [],
        "claims": [],
        "nodes": [
            {
                "node_id": "server_power_supply",
                "theme_id": "ai_power_value_capture_v1",
                "parent_node_id": "",
                "node_name": "Server power supply",
                "node_type": "core_component",
                "description": "Power conversion for AI servers",
                "value_capture_score": 4,
                "bottleneck_score": 3,
                "localization_gap_score": 3,
                "supply_tightness_score": 3,
                "evidence_strength": 2,
                "node_review_status": "needs_evidence",
                "key_metrics": ["power density", "conversion efficiency"],
                "overseas_leaders": [],
                "domestic_players": [],
                "related_stock_codes": [],
            }
        ],
        "value_capture_assessments": [],
        "decomposition_templates": [],
    }


def _write_theme(tmp_path: Path) -> tuple[Path, Path]:
    artifact_dir = tmp_path / "themes"
    artifact_dir.mkdir()
    artifact_path = artifact_dir / "ai_power_value_capture_v1.json"
    artifact_path.write_text(json.dumps(_theme_artifact()), encoding="utf-8")
    return artifact_dir, artifact_path


def _manual_payload(*, reliability: str = "S1", source_type: str = "official_article") -> dict:
    return {
        "source": {
            "source_type": source_type,
            "title": "AI server power density note",
            "publisher": "Example Research",
            "author": "Analyst",
            "publish_date": "2026-07-11",
            "url_or_ref": "local:ai-power-note",
            "access_level": "public",
            "reliability_level": reliability,
            "notes": "Local reviewed input.",
        },
        "claims": [
            {
                "claim_text": "AI server power supply demand rises as rack power density increases.",
                "claim_type": "demand_shock",
                "affected_theme_nodes": ["server_power_supply"],
            }
        ],
    }


def _write_manual(tmp_path: Path, **kwargs: str) -> Path:
    path = tmp_path / "manual.json"
    path.write_text(json.dumps(_manual_payload(**kwargs)), encoding="utf-8")
    return path


def test_normalize_manual_claim_json_is_deterministic(tmp_path: Path) -> None:
    path = _write_manual(tmp_path)

    first = normalize_input(path, "manual_claim_json")
    second = normalize_input(path, "manual_claim_json")

    assert first == second
    assert first["content_sha256"]
    assert first["source_item"]["source_id"].startswith("theme_source:")
    assert first["source_item"]["review_status"] == "unknown"
    assert first["manual_claims"][0]["claim_type"] == "demand_shock"


@pytest.mark.parametrize(
    ("name", "body", "expected"),
    [
        ("note.md", "# Power\nServer power supply demand increases.", "Server power supply demand increases."),
        ("note.txt", "Server power supply demand increases.", "Server power supply demand increases."),
        ("note.html", "<h1>Power</h1><p>Server <b>power supply</b> demand increases.</p>", "Server power supply demand increases."),
    ],
)
def test_normalize_text_documents(tmp_path: Path, name: str, body: str, expected: str) -> None:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")

    normalized = normalize_input(
        path,
        "text_document",
        source_metadata={"title": "Power note", "source_type": "media_article"},
    )

    assert expected in normalized["text"]
    assert normalized["source_item"]["reliability_level"] == "S3"
    assert normalized["provenance"]["adapter_version"] == "text_document_v1"


def test_normalize_docling_document_uses_existing_parser_contract(tmp_path: Path) -> None:
    path = tmp_path / "report.pdf"
    path.write_bytes(b"fake pdf")

    normalized = normalize_input(
        path,
        "docling_document",
        source_metadata={"title": "Full report", "source_type": "official_report"},
        docling_parser=lambda _: {
            "status": "parsed",
            "parser": "docling",
            "markdown": "# Report\nServer power supply efficiency is a bottleneck.",
            "json": {"pages": 1},
            "tables": [],
            "error_type": "",
            "error_message": "",
        },
    )

    assert "efficiency is a bottleneck" in normalized["text"]
    assert normalized["source_item"]["reliability_level"] == "S0"
    assert normalized["provenance"]["parser"] == "docling"


def test_docling_parse_error_is_structured(tmp_path: Path) -> None:
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"bad")

    with pytest.raises(IngestionValidationError) as exc_info:
        normalize_input(
            path,
            "docling_document",
            docling_parser=lambda _: {
                "status": "parse_error",
                "parser": "docling",
                "error_type": "RuntimeError",
                "error_message": "cannot parse",
            },
        )

    assert exc_info.value.code == "DOCLING_PARSE_FAILED"


def test_malformed_docling_result_is_structured(tmp_path: Path) -> None:
    path = tmp_path / "bad-contract.pdf"
    path.write_bytes(b"bad")

    with pytest.raises(IngestionValidationError) as exc_info:
        normalize_input(path, "docling_document", docling_parser=lambda _: None)  # type: ignore[arg-type]

    assert exc_info.value.code == "DOCLING_PARSE_FAILED"


def test_existing_record_adapter_preserves_record_provenance(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text(
        json.dumps(
            {
                "record_id": "daily-review-1",
                "title": "Daily review lead",
                "content": "Server power supply capacity may be constrained.",
                "source_type": "media_article",
                "publisher": "Daily Review",
            }
        ),
        encoding="utf-8",
    )

    normalized = normalize_input(path, "existing_record")

    assert normalized["provenance"]["record_id"] == "daily-review-1"
    assert normalized["source_item"]["url_or_ref"] == "existing_record:daily-review-1"


def test_create_run_extracts_claims_matches_nodes_and_is_idempotent(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    input_path = _write_manual(tmp_path)
    runs_dir = tmp_path / "runs"

    first = create_ingestion_run(
        input_path,
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=runs_dir,
    )
    second = create_ingestion_run(
        input_path,
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=runs_dir,
    )

    assert first["run_id"] == second["run_id"]
    assert len([path for path in runs_dir.iterdir() if path.is_dir()]) == 1
    run = load_run(first["run_dir"])
    claim = run["claim_candidates"][0]
    assert claim["proposed_claim"]["platform_use_status"] == "research_lead"
    assert claim["proposed_claim"]["affected_theme_nodes"] == ["server_power_supply"]
    assert run["theme_node_matches"][0]["node_id"] == "server_power_supply"
    assert run["normalized_sources"][0]["normalized_text"].startswith("AI server power supply")
    assert claim["extraction_span"]["end"] > claim["extraction_span"]["start"]
    assert validate_run(first["run_dir"])["status"] == "ok"
    assert set(path.name for path in Path(first["run_dir"]).iterdir()) == {
        "manifest.json",
        "normalized_sources.json",
        "claim_candidates.json",
        "theme_node_matches.json",
        "review_queue.json",
        "review_events.jsonl",
        "review_ledger_head.json",
        "promotion_preview.json",
    }


def test_rule_extractor_never_creates_reviewed_claim(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    path = tmp_path / "note.txt"
    path.write_text(
        "Server power supply is a bottleneck. Domestic substitution may accelerate.",
        encoding="utf-8",
    )

    result = create_ingestion_run(
        path,
        input_type="text_document",
        source_metadata={"title": "Power note", "source_type": "media_article"},
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    claims = load_run(result["run_dir"])["claim_candidates"]

    assert {row["proposed_claim"]["claim_type"] for row in claims} == {"bottleneck", "localization"}
    assert {row["proposed_claim"]["platform_use_status"] for row in claims} == {"research_lead"}


def test_duplicate_claims_are_deduplicated_before_run_publication(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    payload = _manual_payload()
    payload["claims"].append(copy.deepcopy(payload["claims"][0]))
    path = tmp_path / "duplicates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = create_ingestion_run(
        path,
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )

    assert len(load_run(result["run_dir"])["claim_candidates"]) == 1
    assert validate_run(result["run_dir"])["status"] == "ok"


def test_review_events_are_append_only_and_latest_decision_wins(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run = load_run(result["run_dir"])
    source_id = run["normalized_sources"][0]["candidate_id"]

    first = append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="defer",
        reviewer="reviewer-a",
        comment="Check the full text.",
        reviewed_at="2026-07-11T10:00:00+08:00",
    )
    second = append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Full text checked.",
        reviewed_at="2026-07-11T10:05:00+08:00",
    )

    assert first["event_id"] != second["event_id"]
    preview = build_promotion_preview(result["run_dir"])
    assert preview["latest_decisions"][source_id]["decision"] == "accept_draft"
    assert len(Path(result["run_dir"], "review_events.jsonl").read_text().splitlines()) == 2


def test_review_requires_reviewer_and_comment(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    candidate_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]

    with pytest.raises(IngestionValidationError) as exc_info:
        append_review_event(
            result["run_dir"], candidate_id=candidate_id, decision="accept_draft", reviewer="", comment=""
        )

    assert exc_info.value.code == "REVIEWER_AND_COMMENT_REQUIRED"


def test_s4_source_cannot_be_accepted(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path, reliability="S4", source_type="video_claim"),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    candidate_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]

    with pytest.raises(IngestionValidationError) as exc_info:
        append_review_event(
            result["run_dir"],
            candidate_id=candidate_id,
            decision="accept_draft",
            reviewer="reviewer-a",
            comment="Do not allow this.",
        )

    assert exc_info.value.code == "S4_SOURCE_CANNOT_BE_ACCEPTED"


def test_reviewed_claim_requires_accepted_non_s4_source(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run = load_run(result["run_dir"])
    claim_id = run["claim_candidates"][0]["candidate_id"]

    with pytest.raises(IngestionValidationError) as exc_info:
        append_review_event(
            result["run_dir"],
            candidate_id=claim_id,
            decision="accept_reviewed",
            reviewer="reviewer-a",
            comment="Premature.",
        )

    assert exc_info.value.code == "REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE"


def test_draft_claim_is_blocked_until_its_source_is_promotable(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    claim_id = load_run(result["run_dir"])["claim_candidates"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=claim_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Keep as a draft only.",
    )

    preview = build_promotion_preview(result["run_dir"], target_artifact=artifact_path)

    assert preview["promotable_claims"] == []
    assert preview["blocked_candidates"] == [
        {"candidate_id": claim_id, "reason": "claim source is not present or promotable"}
    ]


def test_atomic_promotion_adds_only_sources_and_claims(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    original = json.loads(artifact_path.read_text())
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run = load_run(result["run_dir"])
    source_candidate = run["normalized_sources"][0]
    claim_candidate = run["claim_candidates"][0]
    append_review_event(
        result["run_dir"],
        candidate_id=source_candidate["candidate_id"],
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    append_review_event(
        result["run_dir"],
        candidate_id=claim_candidate["candidate_id"],
        decision="accept_reviewed",
        reviewer="reviewer-a",
        comment="Claim and source checked.",
    )
    expected_hash = file_sha256(artifact_path)

    promoted = promote_run(
        result["run_dir"], target_artifact=artifact_path, expected_sha256=expected_hash
    )
    updated = json.loads(artifact_path.read_text())

    assert promoted["status"] == "promoted"
    assert promoted["added_source_count"] == 1
    assert promoted["added_claim_count"] == 1
    assert updated["sources"][0]["review_status"] == "accepted"
    assert updated["claims"][0]["platform_use_status"] == "reviewed"
    assert updated["nodes"] == original["nodes"]
    assert updated["value_capture_assessments"] == original["value_capture_assessments"]
    assert list(artifact_path.parent.glob(f"{artifact_path.name}.backup-*"))

    repeated = promote_run(
        result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )
    assert repeated["added_source_count"] == 0
    assert repeated["added_claim_count"] == 0


def test_promotion_hash_mismatch_leaves_artifact_unchanged(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    before = artifact_path.read_bytes()

    with pytest.raises(IngestionValidationError) as exc_info:
        promote_run(result["run_dir"], target_artifact=artifact_path, expected_sha256="0" * 64)

    assert exc_info.value.code == "CANONICAL_HASH_MISMATCH"
    assert artifact_path.read_bytes() == before


def test_promotion_rejects_target_outside_the_run_theme(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    other = _theme_artifact()
    other["theme"]["theme_id"] = "other_theme_v1"
    other["theme"]["theme_type"] = "other"
    other["nodes"] = []
    other_path = theme_dir / "other_theme_v1.json"
    other_path.write_text(json.dumps(other), encoding="utf-8")
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    source_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )

    with pytest.raises(IngestionValidationError) as exc_info:
        promote_run(
            result["run_dir"],
            target_artifact=other_path,
            expected_sha256=file_sha256(other_path),
        )

    assert exc_info.value.code == "PROMOTION_THEME_MISMATCH"


def test_manifest_checksum_tampering_is_detected(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    claim_path = Path(result["run_dir"], "claim_candidates.json")
    claims = json.loads(claim_path.read_text())
    claims["items"][0]["proposed_claim"]["claim_text"] = "tampered"
    claim_path.write_text(json.dumps(claims), encoding="utf-8")

    with pytest.raises(IngestionValidationError) as exc_info:
        validate_run(result["run_dir"])

    assert exc_info.value.code == "RUN_CHECKSUM_MISMATCH"


def test_manifest_cannot_authorize_mutated_candidate_content(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run_dir = Path(result["run_dir"])
    claim_path = run_dir / "claim_candidates.json"
    claims = json.loads(claim_path.read_text())
    claims["items"][0]["proposed_claim"]["claim_text"] = "A different but valid claim."
    claim_path.write_text(json.dumps(claims), encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["immutable_file_sha256"]["claim_candidates.json"] = hashlib.sha256(
        claim_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(IngestionValidationError) as exc_info:
        validate_run(run_dir)

    assert exc_info.value.code == "CONTENT_ADDRESSED_RUN_MISMATCH"


def test_forged_minimal_review_event_is_rejected(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    candidate_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    Path(result["run_dir"], "review_events.jsonl").write_text(
        json.dumps(
            {
                "event_type": "candidate_review",
                "candidate_id": candidate_id,
                "decision": "accept_draft",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(IngestionValidationError) as exc_info:
        validate_run(result["run_dir"])

    assert exc_info.value.code == "INVALID_REVIEW_EVENT"


def test_review_ledger_head_detects_tail_truncation(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    source_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="defer",
        reviewer="reviewer-a",
        comment="First event.",
    )
    append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Second event.",
    )
    ledger = Path(result["run_dir"], "review_events.jsonl")
    ledger.write_text(ledger.read_text().splitlines()[0] + "\n", encoding="utf-8")

    with pytest.raises(IngestionValidationError) as exc_info:
        validate_run(result["run_dir"])

    assert exc_info.value.code == "REVIEW_LEDGER_HEAD_MISMATCH"


def test_valid_ledger_suffix_repairs_a_stale_head(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    source_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    event = append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="defer",
        reviewer="reviewer-a",
        comment="Durable event, stale head simulation.",
    )
    head_path = Path(result["run_dir"], "review_ledger_head.json")
    head_path.write_text(
        json.dumps(
            {
                "run_version": RUN_VERSION,
                "run_id": result["run_id"],
                "event_count": 0,
                "last_event_sha256": event["previous_event_sha256"],
            }
        ),
        encoding="utf-8",
    )

    assert validate_run(result["run_dir"])["status"] == "ok"
    repaired = json.loads(head_path.read_text())
    assert repaired["event_count"] == 1
    assert repaired["last_event_sha256"] == event["event_sha256"]


def test_concurrent_identical_ingestion_returns_one_run(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    input_path = _write_manual(tmp_path)
    runs_dir = tmp_path / "runs"

    def ingest() -> dict:
        return create_ingestion_run(
            input_path,
            input_type="manual_claim_json",
            theme_hint="ai_power_value_capture_v1",
            theme_artifact_dir=theme_dir,
            runs_dir=runs_dir,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: ingest(), range(2)))

    assert {row["run_id"] for row in results} == {results[0]["run_id"]}
    assert sum(bool(row["created"]) for row in results) == 1
    assert len([path for path in runs_dir.iterdir() if path.is_dir()]) == 1


def test_failed_validation_does_not_replace_canonical_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run = load_run(result["run_dir"])
    source_id = run["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    before = artifact_path.read_bytes()

    def fail_validation(_: Path, **__: object) -> None:
        raise IngestionValidationError("forced", code="PROMOTION_VALIDATION_FAILED")

    monkeypatch.setattr("stock_research.theme_research_ingestion._validate_candidate_artifact", fail_validation)
    with pytest.raises(IngestionValidationError) as exc_info:
        promote_run(
            result["run_dir"],
            target_artifact=artifact_path,
            expected_sha256=file_sha256(artifact_path),
        )

    assert exc_info.value.code == "PROMOTION_VALIDATION_FAILED"
    assert artifact_path.read_bytes() == before


def test_candidate_is_frozen_after_successful_promotion(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run = load_run(result["run_dir"])
    source_candidate_id = run["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_candidate_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    promote_run(
        result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )

    with pytest.raises(IngestionValidationError) as exc_info:
        append_review_event(
            result["run_dir"],
            candidate_id=source_candidate_id,
            decision="reject",
            reviewer="reviewer-a",
            comment="Late reversal must use a corrective run.",
        )

    assert exc_info.value.code == "CANDIDATE_ALREADY_PROMOTED"


def test_audit_commit_failure_rolls_back_canonical_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    source_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    before = artifact_path.read_bytes()
    real_append = ingestion_module._append_ledger_event

    def fail_commit(run_dir: Path, event: dict) -> dict:
        if event.get("promotion_status") == "committed":
            raise OSError("forced audit failure")
        return real_append(run_dir, event)

    monkeypatch.setattr(ingestion_module, "_append_ledger_event", fail_commit)

    with pytest.raises(IngestionValidationError) as exc_info:
        promote_run(
            result["run_dir"],
            target_artifact=artifact_path,
            expected_sha256=file_sha256(artifact_path),
        )

    assert exc_info.value.code == "PROMOTION_AUDIT_COMMIT_FAILED"
    assert artifact_path.read_bytes() == before


def test_latest_rolled_back_terminal_state_does_not_freeze_candidate(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    source_candidate_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_candidate_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    promoted = promote_run(
        result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )
    events = load_run(result["run_dir"])["review_events"]
    prepared = next(event for event in events if event.get("promotion_status") == "prepared")
    ingestion_module._restore_file_atomically(Path(promoted["backup_path"]), artifact_path)
    ingestion_module._append_promotion_terminal_event(Path(result["run_dir"]), prepared, "rolled_back")

    event = append_review_event(
        result["run_dir"],
        candidate_id=source_candidate_id,
        decision="reject",
        reviewer="reviewer-a",
        comment="Rollback permits a corrective review state.",
    )

    assert event["decision"] == "reject"


def test_stale_committed_event_after_rollback_is_reconciled(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    source_candidate_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_candidate_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    promoted = promote_run(
        result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )
    run = load_run(result["run_dir"])
    prepared = next(event for event in run["review_events"] if event.get("promotion_status") == "prepared")
    ingestion_module._restore_file_atomically(Path(promoted["backup_path"]), artifact_path)
    Path(result["run_dir"], "review_ledger_head.json").write_text(
        json.dumps(
            {
                "run_version": RUN_VERSION,
                "run_id": result["run_id"],
                "event_count": len(run["review_events"]) - 1,
                "last_event_sha256": prepared["event_sha256"],
            }
        ),
        encoding="utf-8",
    )
    assert validate_run(result["run_dir"])["status"] == "ok"

    review = append_review_event(
        result["run_dir"],
        candidate_id=source_candidate_id,
        decision="reject",
        reviewer="reviewer-a",
        comment="Canonical rows were rolled back.",
    )
    assert review["decision"] == "reject"

    retry = promote_run(
        result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )
    assert retry["status"] == "no_changes"
    assert any(
        event.get("promotion_status") == "rolled_back"
        for event in load_run(result["run_dir"])["review_events"]
    )


def test_concurrent_promotions_cannot_overwrite_each_other(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    runs = []
    for index in range(2):
        payload = _manual_payload()
        payload["source"]["title"] = f"Source {index}"
        payload["source"]["url_or_ref"] = f"local:source-{index}"
        payload["claims"][0]["claim_text"] = f"AI server power supply demand rises, case {index}."
        input_path = tmp_path / f"manual-{index}.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        result = create_ingestion_run(
            input_path,
            input_type="manual_claim_json",
            theme_hint="ai_power_value_capture_v1",
            theme_artifact_dir=theme_dir,
            runs_dir=tmp_path / "runs",
        )
        source_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
        append_review_event(
            result["run_dir"],
            candidate_id=source_id,
            decision="accept_draft",
            reviewer="reviewer-a",
            comment="Source checked.",
        )
        runs.append(result["run_dir"])
    expected_hash = file_sha256(artifact_path)

    def promote(run_dir: str) -> str:
        try:
            return promote_run(
                run_dir,
                target_artifact=artifact_path,
                expected_sha256=expected_hash,
            )["status"]
        except IngestionValidationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(promote, runs))

    assert sorted(outcomes) == ["CANONICAL_HASH_MISMATCH", "promoted"]
    assert len(json.loads(artifact_path.read_text())["sources"]) == 1


def test_package_lock_serializes_promotions_to_different_theme_files(tmp_path: Path) -> None:
    theme_dir, first_path = _write_theme(tmp_path)
    second = _theme_artifact()
    second["theme"]["theme_id"] = "other_theme_v1"
    second["theme"]["theme_type"] = "other"
    second["nodes"][0]["theme_id"] = "other_theme_v1"
    second["nodes"][0]["node_id"] = "other_power_supply"
    second_path = theme_dir / "other_theme_v1.json"
    second_path.write_text(json.dumps(second), encoding="utf-8")
    run_specs = [
        ("ai_power_value_capture_v1", "server_power_supply", first_path),
        ("other_theme_v1", "other_power_supply", second_path),
    ]
    promotions: list[tuple[str, Path, str]] = []
    for index, (theme_id, node_id, target) in enumerate(run_specs):
        payload = _manual_payload()
        payload["source"]["source_id"] = "shared_source_id"
        payload["claims"][0]["theme_id"] = theme_id
        payload["claims"][0]["affected_theme_nodes"] = [node_id]
        path = tmp_path / f"package-lock-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = create_ingestion_run(
            path,
            input_type="manual_claim_json",
            theme_hint=theme_id,
            theme_artifact_dir=theme_dir,
            runs_dir=tmp_path / "runs",
        )
        source_candidate_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
        append_review_event(
            result["run_dir"],
            candidate_id=source_candidate_id,
            decision="accept_draft",
            reviewer="reviewer-a",
            comment="Source checked.",
        )
        promotions.append((result["run_dir"], target, file_sha256(target)))

    def promote(spec: tuple[str, Path, str]) -> str:
        run_dir, target, expected_hash = spec
        try:
            return promote_run(
                run_dir,
                target_artifact=target,
                expected_sha256=expected_hash,
            )["status"]
        except IngestionValidationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(promote, promotions))

    assert sorted(outcomes) == ["PROMOTION_VALIDATION_FAILED", "promoted"]
    package_sources = sum(
        len(json.loads(path.read_text())["sources"]) for path in (first_path, second_path)
    )
    assert package_sources == 1


def test_prepared_promotion_matching_canonical_hash_freezes_and_recovers(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    source_candidate_id = load_run(result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        result["run_dir"],
        candidate_id=source_candidate_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    promote_run(
        result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )
    ledger_path = Path(result["run_dir"], "review_events.jsonl")
    lines = ledger_path.read_text().splitlines()
    prepared = json.loads(lines[-2])
    ledger_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    Path(result["run_dir"], "review_ledger_head.json").write_text(
        json.dumps(
            {
                "run_version": RUN_VERSION,
                "run_id": result["run_id"],
                "event_count": len(lines) - 1,
                "last_event_sha256": prepared["event_sha256"],
            }
        ),
        encoding="utf-8",
    )
    assert validate_run(result["run_dir"])["status"] == "ok"

    with pytest.raises(IngestionValidationError) as exc_info:
        append_review_event(
            result["run_dir"],
            candidate_id=source_candidate_id,
            decision="reject",
            reviewer="reviewer-a",
            comment="Must remain frozen during recovery.",
        )
    assert exc_info.value.code == "CANDIDATE_ALREADY_PROMOTED"

    recovered = promote_run(
        result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )
    assert recovered["status"] == "no_changes"
    assert any(
        event.get("promotion_status") == "committed"
        for event in load_run(result["run_dir"])["review_events"]
    )


def test_package_promotion_recovers_prior_prepared_run_before_new_update(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    first_result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    first_source_id = load_run(first_result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        first_result["run_dir"],
        candidate_id=first_source_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="First source checked.",
    )
    promote_run(
        first_result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )
    first_ledger = Path(first_result["run_dir"], "review_events.jsonl")
    first_lines = first_ledger.read_text().splitlines()
    prepared = json.loads(first_lines[-2])
    first_ledger.write_text("\n".join(first_lines[:-1]) + "\n", encoding="utf-8")
    Path(first_result["run_dir"], "review_ledger_head.json").write_text(
        json.dumps(
            {
                "run_version": RUN_VERSION,
                "run_id": first_result["run_id"],
                "event_count": len(first_lines) - 1,
                "last_event_sha256": prepared["event_sha256"],
            }
        ),
        encoding="utf-8",
    )

    second_payload = _manual_payload()
    second_payload["source"]["title"] = "Second source"
    second_payload["source"]["url_or_ref"] = "local:second-source"
    second_path = tmp_path / "second-source.json"
    second_path.write_text(json.dumps(second_payload), encoding="utf-8")
    second_result = create_ingestion_run(
        second_path,
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    second_source_id = load_run(second_result["run_dir"])["normalized_sources"][0]["candidate_id"]
    append_review_event(
        second_result["run_dir"],
        candidate_id=second_source_id,
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Second source checked.",
    )
    second_promotion = promote_run(
        second_result["run_dir"],
        target_artifact=artifact_path,
        expected_sha256=file_sha256(artifact_path),
    )

    assert second_promotion["status"] == "promoted"
    assert any(
        event.get("promotion_status") == "committed"
        for event in load_run(first_result["run_dir"])["review_events"]
    )
    with pytest.raises(IngestionValidationError) as exc_info:
        append_review_event(
            first_result["run_dir"],
            candidate_id=first_source_id,
            decision="reject",
            reviewer="reviewer-a",
            comment="Recovered promotion remains frozen.",
        )
    assert exc_info.value.code == "CANDIDATE_ALREADY_PROMOTED"


def test_full_package_validation_detects_cross_artifact_duplicate_source(tmp_path: Path) -> None:
    theme_dir, artifact_path = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run = load_run(result["run_dir"])
    source_candidate = run["normalized_sources"][0]
    append_review_event(
        result["run_dir"],
        candidate_id=source_candidate["candidate_id"],
        decision="accept_draft",
        reviewer="reviewer-a",
        comment="Source checked.",
    )
    other = _theme_artifact()
    other["theme"]["theme_id"] = "other_theme_v1"
    other["theme"]["theme_type"] = "other"
    other["nodes"] = []
    duplicate = copy.deepcopy(source_candidate["proposed_source"])
    duplicate["review_status"] = "accepted"
    other["sources"] = [duplicate]
    (theme_dir / "other_theme_v1.json").write_text(json.dumps(other), encoding="utf-8")

    with pytest.raises(IngestionValidationError) as exc_info:
        promote_run(
            result["run_dir"],
            target_artifact=artifact_path,
            expected_sha256=file_sha256(artifact_path),
        )

    assert exc_info.value.code == "PROMOTION_VALIDATION_FAILED"


def test_invalid_utf8_is_reported_as_structured_cli_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"\xff\xfe")

    exit_code = ingestion_cli(
        [
            "--theme-artifact-dir",
            str(theme_dir),
            "ingest",
            "--input",
            str(path),
            "--input-type",
            "text_document",
            "--theme-hint",
            "ai_power_value_capture_v1",
        ]
    )

    error = json.loads(capsys.readouterr().err)
    assert exit_code == 2
    assert error["error_code"] == "INPUT_READ_FAILED"


def test_source_candidate_payload_is_not_mutated_by_preview(tmp_path: Path) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    result = create_ingestion_run(
        _write_manual(tmp_path),
        input_type="manual_claim_json",
        theme_hint="ai_power_value_capture_v1",
        theme_artifact_dir=theme_dir,
        runs_dir=tmp_path / "runs",
    )
    run = load_run(result["run_dir"])
    before = copy.deepcopy(run["normalized_sources"])

    build_promotion_preview(result["run_dir"])

    assert load_run(result["run_dir"])["normalized_sources"] == before


def test_module_cli_ingest_validate_and_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    input_path = _write_manual(tmp_path)
    runs_dir = tmp_path / "runs"

    exit_code = ingestion_cli(
        [
            "--runs-dir",
            str(runs_dir),
            "--theme-artifact-dir",
            str(theme_dir),
            "ingest",
            "--input",
            str(input_path),
            "--input-type",
            "manual_claim_json",
            "--theme-hint",
            "ai_power_value_capture_v1",
        ]
    )
    ingest_output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert ingest_output["created"] is True

    assert ingestion_cli(["summary", "--run", ingest_output["run_dir"]]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["source_candidate_count"] == 1
    assert summary["claim_candidate_count"] == 1


def test_shared_cli_registers_theme_research_ingestion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    theme_dir, _ = _write_theme(tmp_path)
    input_path = _write_manual(tmp_path)

    exit_code = main_for_args(
        [
            "theme-research-ingestion",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--theme-artifact-dir",
            str(theme_dir),
            "ingest",
            "--input",
            str(input_path),
            "--input-type",
            "manual_claim_json",
            "--theme-hint",
            "ai_power_value_capture_v1",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
