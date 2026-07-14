import json
from pathlib import Path

import pytest

from stock_research.theme_company_mapping import (
    THEME_COMPANY_MAPPING_DIR,
    ThemeCompanyMappingValidationError,
    cli,
    load_company_theme_mapping_details,
    load_company_theme_mappings,
    load_theme_company_mapping_package,
    load_theme_company_mappings,
    summarize_theme_company_mapping_package,
    validate_theme_company_mapping_artifact,
)


def test_ai_power_company_mapping_package_loads_and_summarizes():
    package = load_theme_company_mapping_package()

    summary = summarize_theme_company_mapping_package(package)

    assert summary["artifact_count"] == 5
    assert summary["theme_count"] == 5
    assert summary["company_count"] == 39
    assert summary["mapping_count"] == 40
    assert summary["source_count"] == 40
    assert summary["evidence_count"] == 48
    assert summary["mappings_by_review_status"] == {"reviewed": 40}
    assert summary["mappings_by_business_stage"] == {"primary_business": 40}
    assert summary["mappings_by_node"]["liquid_cooling"] == 4
    assert summary["mappings_by_node"]["storage_cells_materials"] == 3


def test_public_single_mapping_artifact_validator_accepts_canonical_artifact():
    artifact = _read_json(
        THEME_COMPANY_MAPPING_DIR / "ai_power_company_mapping_v1.json"
    )
    theme_artifact = _read_json(
        THEME_COMPANY_MAPPING_DIR.parent / "ai_power_value_capture_v1.json"
    )

    validate_theme_company_mapping_artifact(artifact, theme_artifact)


@pytest.mark.parametrize(
    ("collection", "field"),
    [("sources", "author"), ("evidence_items", "excerpt_locator")],
)
def test_public_single_mapping_artifact_validator_requires_canonical_provenance(
    collection: str,
    field: str,
):
    artifact = _read_json(
        THEME_COMPANY_MAPPING_DIR / "ai_power_company_mapping_v1.json"
    )
    theme_artifact = _read_json(
        THEME_COMPANY_MAPPING_DIR.parent / "ai_power_value_capture_v1.json"
    )
    artifact[collection][0].pop(field)

    with pytest.raises(ThemeCompanyMappingValidationError) as exc_info:
        validate_theme_company_mapping_artifact(artifact, theme_artifact)

    assert exc_info.value.code == "MISSING_REQUIRED_FIELD"


def test_theme_and_company_lookup_preserve_node_relationship():
    theme_mappings = load_theme_company_mappings("ai_power_value_capture_v1")
    company_mappings = load_company_theme_mappings("300870.SZ")

    assert {row["company_code"] for row in theme_mappings} == {
        "002335.SZ",
        "002364.SZ",
        "002837.SZ",
        "000811.SZ",
        "300442.SZ",
        "300499.SZ",
        "300870.SZ",
        "301018.SZ",
    }
    assert company_mappings == [
        next(row for row in theme_mappings if row["company_code"] == "300870.SZ")
    ]
    assert company_mappings[0]["mapped_node_id"] == "server_power_supply"
    assert company_mappings[0]["mapping_type"] == "direct_product"
    assert company_mappings[0]["revenue_relevance"] == "material"


def test_reviewed_mapping_requires_evidence(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0]["evidence_ids"] = []
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "REVIEWED_MAPPING_REQUIRES_EVIDENCE"


def test_draft_mapping_still_requires_evidence(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0]["review_status"] = "draft"
    payload["company_mappings"][0]["evidence_ids"] = []
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "MAPPING_REQUIRES_EVIDENCE"


def test_company_mention_only_cannot_support_reviewed_mapping(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][0]
    for evidence in payload["evidence_items"]:
        if evidence["evidence_id"] in mapping["evidence_ids"]:
            evidence["evidence_type"] = "company_mention"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "REVIEWED_MAPPING_REQUIRES_DIRECT_RELATIONSHIP"


def test_reviewed_mapping_cannot_use_nonaccepted_source(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    source_id = payload["evidence_items"][0]["source_id"]
    source = next(row for row in payload["sources"] if row["source_id"] == source_id)
    source["review_status"] = "needs_full_text"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "REVIEWED_MAPPING_REQUIRES_ACCEPTED_SOURCE"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("title", ""),
        ("publisher", 42),
        ("publish_date", {"year": 2026}),
        ("url_or_ref", ""),
    ],
)
def test_accepted_source_requires_usable_metadata(
    tmp_path: Path, field: str, invalid_value: object
):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["sources"][0][field] = invalid_value
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_STRING_FIELD"


def test_reviewed_mapping_allows_weaker_supplemental_source(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][0]
    payload["sources"].append(
        {
            "source_id": "supplemental_media_reference",
            "source_type": "media_article",
            "title": "Supplemental reference",
            "publisher": "Example Publisher",
            "author": "Example Author",
            "publish_date": "2026-01-01",
            "url_or_ref": "https://example.com/reference",
            "access_level": "public",
            "reliability_level": "S3",
            "review_status": "lead_only",
            "notes": "Supplemental context only.",
        }
    )
    payload["evidence_items"].append(
        {
            "evidence_id": "supplemental_company_mention",
            "source_id": "supplemental_media_reference",
            "evidence_type": "company_mention",
            "excerpt_locator": "article body",
            "evidence_summary": "Secondary mention retained as context only.",
            "related_company_codes": [mapping["company_code"]],
            "related_node_ids": [mapping["mapped_node_id"]],
        }
    )
    mapping["evidence_ids"].append("supplemental_company_mention")
    _write_json(path, payload)

    package = load_theme_company_mapping_package(artifact_dir)

    assert len(package["company_mappings"]) == 40


def test_reviewed_material_claim_requires_materiality_evidence(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][0]
    mapping.update(
        {
            "revenue_relevance": "material",
            "business_materiality": "core_business",
            "evidence_ids": [mapping["evidence_ids"][0]],
        }
    )
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "REVIEWED_MAPPING_REQUIRES_MATERIALITY_EVIDENCE"


def test_reviewed_limited_revenue_claim_requires_materiality_evidence(
    tmp_path: Path,
):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][0]
    mapping.update(
        {
            "revenue_relevance": "limited",
            "business_materiality": "emerging_segment",
            "evidence_ids": [mapping["evidence_ids"][0]],
        }
    )
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "REVIEWED_MAPPING_REQUIRES_MATERIALITY_EVIDENCE"


def test_concept_exposure_cannot_be_reviewed(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0].update(
        {
            "business_stage": "concept_exposure",
            "business_materiality": "concept_only",
            "revenue_relevance": "none",
        }
    )
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "CONCEPT_EXPOSURE_CANNOT_BE_REVIEWED"


def test_concept_exposure_cannot_claim_material_business(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0].update(
        {
            "business_stage": "concept_exposure",
            "business_materiality": "core_business",
            "revenue_relevance": "material",
            "review_status": "draft",
        }
    )
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "CONCEPT_EXPOSURE_MATERIALITY_MISMATCH"


def test_reserve_stage_must_not_claim_material_business(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0].update(
        {
            "business_stage": "reserve_stage",
            "business_materiality": "meaningful_segment",
            "revenue_relevance": "material",
            "review_status": "draft",
        }
    )
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "RESERVE_STAGE_MATERIALITY_MISMATCH"


def test_invalid_cn_company_code_is_rejected(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0]["company_code"] = "2837"
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_COMPANY_CODE"


def test_evidence_scope_must_match_mapping_company_and_node(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][0]
    evidence = next(
        row for row in payload["evidence_items"] if row["evidence_id"] == mapping["evidence_ids"][0]
    )
    evidence["related_company_codes"] = ["999999.SZ"]
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "MAPPING_EVIDENCE_SCOPE_MISMATCH"


def test_duplicate_mapping_id_is_rejected(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][1]["mapping_id"] = payload["company_mappings"][0]["mapping_id"]
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "DUPLICATE_MAPPING_ID"


def test_mapping_must_belong_to_its_artifact_theme(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][0]
    mapping["theme_id"] = "humanoid_robotics_head_to_toe_v1"
    mapping["mapped_node_id"] = "head_vision"
    for evidence in payload["evidence_items"]:
        if evidence["evidence_id"] in mapping["evidence_ids"]:
            evidence["related_node_ids"] = ["head_vision"]
    _write_json(path, payload)
    _write_json(
        artifact_dir / "humanoid_robotics_company_mapping_v1.json",
        {
            "artifact_version": "theme_company_mapping_v1",
            "theme_id": "humanoid_robotics_head_to_toe_v1",
            "sources": [],
            "evidence_items": [],
            "company_mappings": [],
        },
    )

    error = _load_invalid_package(artifact_dir)

    assert error.code == "MAPPING_THEME_OWNERSHIP_MISMATCH"


def test_evidence_cannot_borrow_source_from_another_artifact(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    borrowed_source = payload["sources"].pop(0)
    _write_json(path, payload)
    _write_json(
        artifact_dir / "ai_power_supplemental_company_mapping_v1.json",
        {
            "artifact_version": "theme_company_mapping_v1",
            "theme_id": "ai_power_value_capture_v1",
            "sources": [borrowed_source],
            "evidence_items": [],
            "company_mappings": [],
        },
    )

    error = _load_invalid_package(artifact_dir)

    assert error.code == "EVIDENCE_SOURCE_OWNERSHIP_MISMATCH"


def test_mapping_cannot_borrow_evidence_from_another_artifact(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    mapping = payload["company_mappings"][0]
    borrowed_ids = set(mapping["evidence_ids"])
    borrowed_evidence = [
        evidence
        for evidence in payload["evidence_items"]
        if evidence["evidence_id"] in borrowed_ids
    ]
    borrowed_source_ids = {evidence["source_id"] for evidence in borrowed_evidence}
    borrowed_sources = [
        source for source in payload["sources"] if source["source_id"] in borrowed_source_ids
    ]
    payload["evidence_items"] = [
        evidence
        for evidence in payload["evidence_items"]
        if evidence["evidence_id"] not in borrowed_ids
    ]
    payload["sources"] = [
        source for source in payload["sources"] if source["source_id"] not in borrowed_source_ids
    ]
    _write_json(path, payload)
    _write_json(
        artifact_dir / "ai_power_supplemental_company_mapping_v1.json",
        {
            "artifact_version": "theme_company_mapping_v1",
            "theme_id": "ai_power_value_capture_v1",
            "sources": borrowed_sources,
            "evidence_items": borrowed_evidence,
            "company_mappings": [],
        },
    )

    error = _load_invalid_package(artifact_dir)

    assert error.code == "MAPPING_EVIDENCE_OWNERSHIP_MISMATCH"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("related_company_codes", {"002837.SZ": True}),
        ("related_node_ids", {"liquid_cooling": True}),
    ],
)
def test_evidence_scope_fields_must_be_string_lists(
    tmp_path: Path, field: str, invalid_value: object
):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["evidence_items"][0][field] = invalid_value
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_LIST_FIELD"


def test_mapping_evidence_ids_must_be_string_list(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0]["evidence_ids"] = {
        payload["company_mappings"][0]["evidence_ids"][0]: True
    }
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_LIST_FIELD"


def test_boolean_confidence_is_rejected(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0]["confidence"] = True
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_MAPPING_CONFIDENCE"


def test_non_finite_confidence_is_rejected(tmp_path: Path):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0]["confidence"] = float("nan")
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_MAPPING_CONFIDENCE"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("company_name", {"name": "invalid"}),
        ("product_or_service", 123),
        ("relationship_summary", ""),
    ],
)
def test_mapping_description_fields_must_be_non_empty_strings(
    tmp_path: Path, field: str, invalid_value: object
):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["company_mappings"][0][field] = invalid_value
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_STRING_FIELD"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("excerpt_locator", 123),
        ("evidence_summary", {"text": "not a scalar string"}),
    ],
)
def test_evidence_text_fields_must_be_non_empty_strings(
    tmp_path: Path, field: str, invalid_value: object
):
    artifact_dir = _copy_mapping_package(tmp_path)
    path = artifact_dir / "ai_power_company_mapping_v1.json"
    payload = _read_json(path)
    payload["evidence_items"][0][field] = invalid_value
    _write_json(path, payload)

    error = _load_invalid_package(artifact_dir)

    assert error.code == "INVALID_STRING_FIELD"


def test_company_detail_resolves_excerpt_evidence_and_source():
    details = load_company_theme_mapping_details("300870.SZ")

    assert len(details) == 1
    assert details[0]["mapped_node_id"] == "server_power_supply"
    assert len(details[0]["evidence"]) == 2
    assert details[0]["evidence"][0]["excerpt_locator"]
    assert details[0]["evidence"][0]["source"]["reliability_level"] == "S0"


def test_cli_validate_summary_and_company_lookup_emit_json(capsys):
    validate_exit = cli(["validate"])
    validate_payload = json.loads(capsys.readouterr().out)

    summary_exit = cli(["summary"])
    summary_payload = json.loads(capsys.readouterr().out)

    company_exit = cli(["show-company", "--company-code", "002837.SZ"])
    company_payload = json.loads(capsys.readouterr().out)

    assert validate_exit == 0
    assert validate_payload["status"] == "ok"
    assert validate_payload["mapping_count"] == 40
    assert summary_exit == 0
    assert summary_payload["company_count"] == 39
    assert company_exit == 0
    assert company_payload[0]["mapped_node_id"] == "liquid_cooling"
    assert company_payload[0]["evidence"][0]["source"]["review_status"] == "accepted"


def _copy_mapping_package(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "company_mappings"
    artifact_dir.mkdir()
    for path in THEME_COMPANY_MAPPING_DIR.glob("*.json"):
        _write_json(artifact_dir / path.name, _read_json(path))
    return artifact_dir


def _load_invalid_package(artifact_dir: Path) -> ThemeCompanyMappingValidationError:
    with pytest.raises(ThemeCompanyMappingValidationError) as exc_info:
        load_theme_company_mapping_package(artifact_dir)
    return exc_info.value


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
