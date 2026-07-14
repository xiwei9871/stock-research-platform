import json
from pathlib import Path

import pytest

from stock_research.ai_power_source_pack import (
    AI_POWER_SOURCE_PACK_DIR,
    AI_POWER_THEME_ARTIFACT,
    AiPowerEvidenceValidationError,
    cli,
    load_ai_power_evidence_pack,
    summarize_ai_power_evidence_pack,
    validate_theme_evidence_sources,
)


def test_sample_ai_power_evidence_pack_loads_and_summarizes():
    package = load_ai_power_evidence_pack()

    summary = summarize_ai_power_evidence_pack(package)

    assert summary == {
        "accepted_source_count": 15,
        "claim_count": 10,
        "claims_by_review_decision": {
            "blocked": 2,
            "draft": 1,
            "reviewed": 7,
        },
        "matrix_nodes_by_evidence_gap_status": {
            "covered": 13,
        },
        "needs_full_text_source_count": 1,
        "node_count": 13,
        "source_count": 18,
        "sources_by_reliability_level": {
            "S0": 8,
            "S1": 7,
            "S2": 1,
            "S3": 1,
            "S4": 1,
        },
        "sources_by_review_status": {
            "accepted": 15,
            "lead_only": 2,
            "needs_full_text": 1,
        },
        "theme_id": "ai_power_value_capture_v1",
    }


def test_accepted_sources_have_traceable_excerpt_level_evidence():
    package = load_ai_power_evidence_pack()

    accepted_sources = [
        source for source in package["sources"] if source["review_status"] == "accepted"
    ]

    assert accepted_sources
    for source in accepted_sources:
        assert source["url"].startswith("https://")
        assert source["document_status"] in {
            "official_page_reviewed",
            "full_text_reviewed",
            "primary_source_reviewed",
        }
        assert source["evidence_locator"]
        assert source["evidence_summary"]
        assert source["limitations"]


def test_public_theme_evidence_source_validator_returns_sources_by_id():
    package = load_ai_power_evidence_pack()
    canonical_node_ids = {
        node["node_id"] for node in package["canonical_theme"]["nodes"]
    }

    source_by_id = validate_theme_evidence_sources(
        package["sources"], canonical_node_ids
    )

    assert set(source_by_id) == {source["source_id"] for source in package["sources"]}


def test_public_theme_evidence_source_validator_rejects_non_https_accepted_source():
    package = load_ai_power_evidence_pack()
    sources = [dict(source) for source in package["sources"]]
    accepted = next(source for source in sources if source["review_status"] == "accepted")
    accepted["url"] = "http://example.com/source"

    with pytest.raises(AiPowerEvidenceValidationError) as exc_info:
        validate_theme_evidence_sources(
            sources,
            {node["node_id"] for node in package["canonical_theme"]["nodes"]},
        )

    assert exc_info.value.code == "ACCEPTED_SOURCE_REQUIRES_PUBLIC_URL"


def test_reviewed_claims_use_accepted_sources():
    package = load_ai_power_evidence_pack()
    source_by_id = {source["source_id"]: source for source in package["sources"]}

    reviewed_claims = [
        claim for claim in package["claim_reviews"] if claim["review_decision"] == "reviewed"
    ]

    assert reviewed_claims
    for claim in reviewed_claims:
        assert claim["accepted_source_ids"]
        assert all(
            source_by_id[source_id]["review_status"] == "accepted"
            for source_id in claim["accepted_source_ids"]
        )


def test_node_matrix_covers_every_canonical_ai_power_node():
    package = load_ai_power_evidence_pack()
    canonical_node_ids = {node["node_id"] for node in package["canonical_theme"]["nodes"]}
    matrix_node_ids = {row["node_id"] for row in package["node_evidence_matrix"]}

    assert matrix_node_ids == canonical_node_ids


def test_accepted_source_without_locator_is_rejected(tmp_path):
    artifact_dir, theme_path = _copy_sample_pack(tmp_path)
    source_pack_path = artifact_dir / "ai_power_source_pack_v1.json"
    source_pack = _read_json(source_pack_path)
    accepted_source = next(
        source for source in source_pack["sources"] if source["review_status"] == "accepted"
    )
    accepted_source["evidence_locator"] = ""
    _write_json(source_pack_path, source_pack)

    error = _load_invalid_pack(artifact_dir, theme_path)

    assert error.code == "ACCEPTED_SOURCE_REQUIRES_EVIDENCE_LOCATOR"


def test_reviewed_claim_without_accepted_source_is_rejected(tmp_path):
    artifact_dir, theme_path = _copy_sample_pack(tmp_path)
    claim_review_path = artifact_dir / "ai_power_claim_review_v1.json"
    claim_review = _read_json(claim_review_path)
    reviewed_claim = next(
        claim for claim in claim_review["claim_reviews"] if claim["review_decision"] == "reviewed"
    )
    reviewed_claim["accepted_source_ids"] = []
    _write_json(claim_review_path, claim_review)

    error = _load_invalid_pack(artifact_dir, theme_path)

    assert error.code == "REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE"


def test_missing_node_matrix_row_is_rejected(tmp_path):
    artifact_dir, theme_path = _copy_sample_pack(tmp_path)
    matrix_path = artifact_dir / "ai_power_node_evidence_matrix_v1.json"
    matrix = _read_json(matrix_path)
    matrix["node_evidence_matrix"].pop()
    _write_json(matrix_path, matrix)

    error = _load_invalid_pack(artifact_dir, theme_path)

    assert error.code == "NODE_MATRIX_COVERAGE_MISMATCH"


def test_cli_validate_emits_structured_json(capsys):
    exit_code = cli(["validate"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["theme_id"] == "ai_power_value_capture_v1"
    assert payload["accepted_source_count"] == 15


def _copy_sample_pack(tmp_path: Path) -> tuple[Path, Path]:
    artifact_dir = tmp_path / "source_packs"
    artifact_dir.mkdir()
    for path in AI_POWER_SOURCE_PACK_DIR.glob("*.json"):
        _write_json(artifact_dir / path.name, _read_json(path))
    theme_path = tmp_path / AI_POWER_THEME_ARTIFACT.name
    _write_json(theme_path, _read_json(AI_POWER_THEME_ARTIFACT))
    return artifact_dir, theme_path


def _load_invalid_pack(
    artifact_dir: Path,
    theme_path: Path,
) -> AiPowerEvidenceValidationError:
    with pytest.raises(AiPowerEvidenceValidationError) as exc_info:
        load_ai_power_evidence_pack(artifact_dir, theme_path)
    return exc_info.value


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
